"""
Color matching engine.

Pipeline:
1. Send product image to Google Vision API → dominant colors (SRGB)
2. For each dominant color, compute Delta-E 2000 distance against every
   color in the Deep Winter palette
3. Compute a weighted score 0–100 based on:
   - Best Delta-E match across palette
   - Coverage (what % of the image is in-palette colors)
4. Return score + closest palette match + reasoning
"""
from __future__ import annotations

import base64
import logging
import math
from dataclasses import dataclass
from typing import Optional
import re

import httpx
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from ..config import settings

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Excluded warm-tone heuristics (rough Lab-space bounding boxes).
# We use this as a secondary veto on top of the score.
# -----------------------------------------------------------------------
WARM_HUES = [
    (25, 55),    # orange-amber hue angle range (rough)
    (55, 75),    # yellow-mustard
    (0, 25),     # red-orange
]


@dataclass
class ColorMatchResult:
    score: int                          # 0–100
    closest_palette_hex: str
    closest_palette_name: str
    dominant_colors: list[dict]         # [{hex, percentage}]
    is_excluded_color: bool
    delta_e_best: float
    reasoning: str


# Map hex → friendly name for display
PALETTE_NAMES: dict[str, str] = {
    "#000000": "Black",
    "#ffffff": "Bright White",
    "#006b3c": "Emerald",
    "#4169e1": "Royal Blue",
    "#cc0000": "True Red",
    "#800020": "Burgundy",
    "#580f41": "Deep Plum",
    "#ff0090": "Fuchsia",
    "#0047ab": "Cobalt",
    "#36454f": "Charcoal",
    "#000080": "Navy",
    "#008080": "Teal",
    "#3c1f1f": "Mahogany",
}

# Pre-convert palette to Lab for efficiency
_PALETTE_LAB: list[tuple[str, LabColor]] = []


def _get_palette_lab() -> list[tuple[str, LabColor]]:
    global _PALETTE_LAB
    if not _PALETTE_LAB:
        for hex_color in settings.deep_winter_palette:
            rgb = _hex_to_srgb(hex_color)
            lab = convert_color(rgb, LabColor)
            _PALETTE_LAB.append((hex_color.lower(), lab))
    return _PALETTE_LAB


def _hex_to_srgb(hex_color: str) -> sRGBColor:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return sRGBColor(r / 255.0, g / 255.0, b / 255.0)


def _rgb_dict_to_srgb(rgb: dict) -> sRGBColor:
    return sRGBColor(
        rgb.get("red", 0) / 255.0,
        rgb.get("green", 0) / 255.0,
        rgb.get("blue", 0) / 255.0,
    )


def score_color_against_palette(hex_color: str) -> tuple[float, str]:
    """Return (best_delta_e, closest_palette_hex)."""
    palette = _get_palette_lab()
    srgb = _hex_to_srgb(hex_color)
    lab = convert_color(srgb, LabColor)
    best_de = math.inf
    best_hex = palette[0][0]
    for pal_hex, pal_lab in palette:
        de = delta_e_cie2000(lab, pal_lab)
        if de < best_de:
            best_de = de
            best_hex = pal_hex
    return best_de, best_hex


def delta_e_to_score(delta_e: float) -> int:
    """
    Convert Delta-E 2000 to a 0–100 confidence score.

    ΔE < 1   → imperceptible difference  (score ~100)
    ΔE < 5   → very close               (score ~90)
    ΔE < 15  → good match               (score ~75)
    ΔE < 25  → acceptable               (score ~55)
    ΔE ≥ 40  → poor match               (score ~0)
    """
    if delta_e <= 0:
        return 100
    if delta_e >= 40:
        return 0
    # Piecewise linear interpolation
    breakpoints = [(0, 100), (1, 98), (5, 90), (10, 82), (15, 72), (25, 50), (35, 20), (40, 0)]
    for i in range(len(breakpoints) - 1):
        d0, s0 = breakpoints[i]
        d1, s1 = breakpoints[i + 1]
        if d0 <= delta_e <= d1:
            t = (delta_e - d0) / (d1 - d0)
            return round(s0 + t * (s1 - s0))
    return 0


class ColorMatcher:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30.0)

    async def aclose(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_image(self, image_url: str) -> ColorMatchResult:
        """
        Full pipeline: fetch image → Vision API → Delta-E scoring.
        Falls back to a score of 0 with an empty dominant_colors list
        if Vision API is unavailable.
        """
        if not settings.google_vision_api_key:
            logger.warning("GOOGLE_VISION_API_KEY not set — color scoring skipped")
            return ColorMatchResult(
                score=0,
                closest_palette_hex="",
                closest_palette_name="",
                dominant_colors=[],
                is_excluded_color=False,
                delta_e_best=999.0,
                reasoning="Vision API key not configured.",
            )

        dominant_colors = await self._fetch_dominant_colors(image_url)
        return self._compute_match(dominant_colors)

    def analyze_hex(self, hex_color: str) -> ColorMatchResult:
        """Score a single known hex color (e.g. from retailer color swatch)."""
        h = hex_color.strip()
        if not re.match(r'^#?[0-9a-fA-F]{6}$', h):
            return ColorMatchResult(0, "", "", [], False, 999.0, "Invalid hex")
        if not h.startswith("#"):
            h = "#" + h
        dominant = [{"hex": h, "percentage": 1.0}]
        return self._compute_match(dominant)

    # ------------------------------------------------------------------
    # Google Vision API
    # ------------------------------------------------------------------

    async def _fetch_dominant_colors(self, image_url: str) -> list[dict]:
        """
        Call Vision API imageProperties feature.
        Returns list of {hex, percentage}.
        """
        endpoint = (
            f"https://vision.googleapis.com/v1/images:annotate"
            f"?key={settings.google_vision_api_key}"
        )
        payload = {
            "requests": [
                {
                    "image": {"source": {"imageUri": image_url}},
                    "features": [{"type": "IMAGE_PROPERTIES", "maxResults": 10}],
                }
            ]
        }
        try:
            resp = await self._client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            colors_raw = (
                data.get("responses", [{}])[0]
                .get("imagePropertiesAnnotation", {})
                .get("dominantColors", {})
                .get("colors", [])
            )
            result = []
            for c in colors_raw:
                rgb = c.get("color", {})
                score = c.get("score", 0)
                pixel_fraction = c.get("pixelFraction", 0)
                r = int(rgb.get("red", 0))
                g = int(rgb.get("green", 0))
                b = int(rgb.get("blue", 0))
                hex_c = f"#{r:02x}{g:02x}{b:02x}"
                result.append({"hex": hex_c, "percentage": round(pixel_fraction, 4)})
            return result
        except Exception as exc:
            logger.error("Vision API error for %s: %s", image_url, exc)
            return []

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_match(self, dominant_colors: list[dict]) -> ColorMatchResult:
        if not dominant_colors:
            return ColorMatchResult(0, "", "", [], False, 999.0, "No dominant colors found.")

        palette = _get_palette_lab()
        best_de = math.inf
        best_palette_hex = ""
        weighted_score = 0.0
        total_weight = 0.0
        is_excluded = False

        for color_entry in dominant_colors:
            hex_c = color_entry["hex"]
            weight = color_entry.get("percentage", 0.1)

            de, pal_hex = score_color_against_palette(hex_c)
            item_score = delta_e_to_score(de)

            weighted_score += item_score * weight
            total_weight += weight

            if de < best_de:
                best_de = de
                best_palette_hex = pal_hex

            # Check if this color falls in the excluded warm range
            if self._is_excluded_warm(hex_c) and weight > 0.15:
                is_excluded = True

        final_score = round(weighted_score / total_weight) if total_weight > 0 else 0

        # Penalise if primary color (highest % swatch) is excluded warm tone
        if is_excluded:
            final_score = min(final_score, 30)

        closest_name = PALETTE_NAMES.get(best_palette_hex, best_palette_hex)
        reasoning = self._build_reasoning(final_score, best_de, best_palette_hex, closest_name, is_excluded)

        return ColorMatchResult(
            score=final_score,
            closest_palette_hex=best_palette_hex,
            closest_palette_name=closest_name,
            dominant_colors=dominant_colors,
            is_excluded_color=is_excluded,
            delta_e_best=round(best_de, 2),
            reasoning=reasoning,
        )

    @staticmethod
    def _is_excluded_warm(hex_c: str) -> bool:
        """
        Quick Lab-space heuristic: high 'a' (red-green) and 'b' (yellow-blue)
        values indicate warm/earthy tones we want to exclude.
        """
        try:
            srgb = _hex_to_srgb(hex_c)
            lab = convert_color(srgb, LabColor)
            # Warm: high positive b* (yellow), moderate positive a* (red)
            # Camel/tan: L~60-75, a~5-12, b~15-30
            # Mustard: L~50-65, b~25-45
            # Peach/coral: a*>10 and b*>10 and L>50
            b_star = lab.lab_b
            a_star = lab.lab_a
            l_star = lab.lab_l
            if b_star > 18 and a_star > 5:
                return True
            if b_star > 30:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _build_reasoning(score: int, best_de: float, pal_hex: str, pal_name: str, excluded: bool) -> str:
        if excluded:
            return (
                f"Primary color is a warm/earthy tone that clashes with Deep Winter's "
                f"cool, clear palette (ΔE {best_de:.1f} to nearest palette color {pal_name}). "
                "Camel, tan, beige, mustard, and coral tones wash out Deep Winter coloring."
            )
        if score >= 85:
            return (
                f"Excellent color match for Deep Winter — closest to {pal_name} "
                f"(ΔE {best_de:.1f}). Clear, cool tones like this create high contrast "
                "and make the coloring pop."
            )
        if score >= 70:
            return (
                f"Good color match — closest to {pal_name} (ΔE {best_de:.1f}). "
                "The cool undertones align with Deep Winter's palette, though some "
                "secondary colors soften the overall effect."
            )
        if score >= 50:
            return (
                f"Borderline match — closest to {pal_name} (ΔE {best_de:.1f}). "
                "The dominant color has some warmth or muddiness that partially conflicts "
                "with Deep Winter's need for clear, saturated cool tones."
            )
        return (
            f"Poor color match for Deep Winter (ΔE {best_de:.1f} from {pal_name}). "
            "This color likely has warm, muted, or dusty qualities that diminish "
            "Deep Winter coloring."
        )
