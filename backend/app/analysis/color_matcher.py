"""
Color matching engine.

Pipeline:
1. Send product image to Google Vision API → dominant colors (SRGB)
2. For each dominant color, compute Delta-E 2000 distance against every
   color in the Deep Winter palette
3. Classify color into tier1 / tier2 / tier3 / hard_avoid based on:
   a) Keyword match on color_name (most reliable signal)
   b) Proximity to tier1 or tier2 palette in Lab space
4. Compute a weighted score 0–100 based on Delta-E coverage
5. Return score + tier + closest palette match + reasoning

The 0–100 raw score from this module feeds the color_match_score field.
The tier feeds _compute_color_points() in jobs.py (0–40 scale).
"""
from __future__ import annotations

import base64
import logging
import math
from dataclasses import dataclass, field
from typing import Optional
import re

import httpx
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class ColorMatchResult:
    score: int                           # 0–100 Delta-E based raw score
    color_tier: str                      # "tier1" | "tier2" | "tier3" | "hard_avoid" | "unknown"
    closest_palette_hex: str
    closest_palette_name: str
    dominant_colors: list[dict]          # [{hex, percentage}]
    is_excluded_color: bool              # True if hard_avoid keyword or warm-hue veto
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
    "#000080": "Navy",
    "#580f41": "Deep Plum",
    "#ff0090": "Fuchsia",
    "#0047ab": "Cobalt",
    "#36454f": "Charcoal",
    "#008080": "Teal",
    "#3c1f1f": "Mahogany",
    "#ffb6c1": "Icy Pink",
    "#301934": "Deep Purple",
}

# Pre-convert palettes to Lab for efficient scoring
_PALETTE_LAB: list[tuple[str, LabColor]] = []
_TIER1_LAB: list[tuple[str, LabColor]] = []
_TIER2_LAB: list[tuple[str, LabColor]] = []


def _build_lab_cache() -> None:
    global _PALETTE_LAB, _TIER1_LAB, _TIER2_LAB
    if _PALETTE_LAB:
        return
    for hex_color in settings.deep_winter_palette:
        rgb = _hex_to_srgb(hex_color)
        lab = convert_color(rgb, LabColor)
        _PALETTE_LAB.append((hex_color.lower(), lab))
    for hex_color in settings.tier1_palette:
        rgb = _hex_to_srgb(hex_color)
        lab = convert_color(rgb, LabColor)
        _TIER1_LAB.append((hex_color.lower(), lab))
    for hex_color in settings.tier2_palette:
        rgb = _hex_to_srgb(hex_color)
        lab = convert_color(rgb, LabColor)
        _TIER2_LAB.append((hex_color.lower(), lab))


def _hex_to_srgb(hex_color: str) -> sRGBColor:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return sRGBColor(r / 255.0, g / 255.0, b / 255.0)


def score_color_against_palette(hex_color: str) -> tuple[float, str]:
    """Return (best_delta_e, closest_palette_hex)."""
    _build_lab_cache()
    srgb = _hex_to_srgb(hex_color)
    lab = convert_color(srgb, LabColor)
    best_de = math.inf
    best_hex = _PALETTE_LAB[0][0]
    for pal_hex, pal_lab in _PALETTE_LAB:
        de = delta_e_cie2000(lab, pal_lab)
        if de < best_de:
            best_de = de
            best_hex = pal_hex
    return best_de, best_hex


def classify_color_tier(hex_color: str, color_name: str = "") -> str:
    """
    Classify a color into one of five tiers using keyword detection first,
    then Lab-space proximity as fallback.

    Returns: "tier1" | "tier2" | "tier3" | "hard_avoid" | "unknown"
    """
    name_lower = color_name.strip().lower() if color_name else ""

    # 1. Keyword check — hard avoid (most important, checked first)
    for kw in settings.hard_avoid_keywords:
        if kw in name_lower:
            return "hard_avoid"

    # 2. Keyword check — tier 3 borderline
    if name_lower:
        for kw in settings.tier3_keywords:
            if kw in name_lower:
                return "tier3"

    # 3. Lab-space proximity fallback
    _build_lab_cache()
    if not hex_color or not re.match(r'^#?[0-9a-fA-F]{6}$', hex_color.strip()):
        return "unknown"

    h = hex_color.strip()
    if not h.startswith("#"):
        h = "#" + h

    try:
        srgb = _hex_to_srgb(h)
        lab = convert_color(srgb, LabColor)

        # Warm-hue veto (b* > 18 and a* > 5 → earthy/warm)
        if lab.lab_b > 18 and lab.lab_a > 5:
            return "hard_avoid"
        if lab.lab_b > 30:
            return "hard_avoid"

        # Check proximity to tier1
        best_de_t1 = min(delta_e_cie2000(lab, pal_lab) for _, pal_lab in _TIER1_LAB)
        if best_de_t1 <= settings.delta_e_good:
            return "tier1"

        # Check proximity to tier2
        best_de_t2 = min(delta_e_cie2000(lab, pal_lab) for _, pal_lab in _TIER2_LAB)
        if best_de_t2 <= settings.delta_e_good:
            return "tier2"

        # Acceptable range → tier3
        best_de_any, _ = score_color_against_palette(h)
        if best_de_any <= settings.delta_e_ok:
            return "tier3"

        return "hard_avoid"

    except Exception:
        return "unknown"


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

    async def analyze_image(self, image_url: str, color_name: str = "") -> ColorMatchResult:
        """
        Full pipeline: fetch image → Vision API → Delta-E scoring + tier classification.
        Falls back to a zero-score result if Vision API is unavailable.
        """
        if not settings.google_vision_api_key:
            logger.warning("GOOGLE_VISION_API_KEY not set — color scoring skipped")
            return ColorMatchResult(
                score=0,
                color_tier="unknown",
                closest_palette_hex="",
                closest_palette_name="",
                dominant_colors=[],
                is_excluded_color=False,
                delta_e_best=999.0,
                reasoning="Vision API key not configured.",
            )

        dominant_colors = await self._fetch_dominant_colors(image_url)
        return self._compute_match(dominant_colors, color_name=color_name)

    def analyze_hex(self, hex_color: str, color_name: str = "") -> ColorMatchResult:
        """Score a single known hex color (e.g. from retailer color swatch)."""
        h = hex_color.strip()
        if not re.match(r'^#?[0-9a-fA-F]{6}$', h):
            return ColorMatchResult(0, "unknown", "", "", [], False, 999.0, "Invalid hex")
        if not h.startswith("#"):
            h = "#" + h
        dominant = [{"hex": h, "percentage": 1.0}]
        return self._compute_match(dominant, color_name=color_name)

    # ------------------------------------------------------------------
    # Google Vision API
    # ------------------------------------------------------------------

    async def _fetch_dominant_colors(self, image_url: str) -> list[dict]:
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

    def _compute_match(self, dominant_colors: list[dict], color_name: str = "") -> ColorMatchResult:
        if not dominant_colors:
            return ColorMatchResult(0, "unknown", "", "", [], False, 999.0, "No dominant colors found.")

        _build_lab_cache()
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

            if self._is_excluded_warm(hex_c) and weight > 0.15:
                is_excluded = True

        final_score = round(weighted_score / total_weight) if total_weight > 0 else 0

        if is_excluded:
            final_score = min(final_score, 30)

        # Keyword-based hard avoid on color name overrides everything
        if color_name:
            name_lower = color_name.lower()
            for kw in settings.hard_avoid_keywords:
                if kw in name_lower:
                    is_excluded = True
                    final_score = 0
                    break

        # Classify tier using best matching hex + color name
        primary_hex = dominant_colors[0]["hex"] if dominant_colors else ""
        color_tier = classify_color_tier(primary_hex, color_name)

        closest_name = PALETTE_NAMES.get(best_palette_hex, best_palette_hex)
        reasoning = self._build_reasoning(final_score, best_de, best_palette_hex, closest_name, is_excluded, color_tier)

        return ColorMatchResult(
            score=final_score,
            color_tier=color_tier,
            closest_palette_hex=best_palette_hex,
            closest_palette_name=closest_name,
            dominant_colors=dominant_colors,
            is_excluded_color=is_excluded,
            delta_e_best=round(best_de, 2),
            reasoning=reasoning,
        )

    @staticmethod
    def _is_excluded_warm(hex_c: str) -> bool:
        """Lab-space heuristic for warm/earthy tones (camel, tan, peach, mustard, etc.)."""
        try:
            srgb = _hex_to_srgb(hex_c)
            lab = convert_color(srgb, LabColor)
            if lab.lab_b > 18 and lab.lab_a > 5:
                return True
            if lab.lab_b > 30:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _build_reasoning(
        score: int,
        best_de: float,
        pal_hex: str,
        pal_name: str,
        excluded: bool,
        color_tier: str,
    ) -> str:
        if excluded or color_tier == "hard_avoid":
            return (
                f"Hard-avoid color detected — warm/earthy tone that creates sallowness "
                f"against Caroline's olive skin (ΔE {best_de:.1f} to nearest palette color "
                f"{pal_name}). Compare to the yellow Hard Rock dress: same draining effect."
            )
        if score >= 85 or color_tier == "tier1":
            return (
                f"Excellent match for Caroline's Deep Winter palette — closest to {pal_name} "
                f"(ΔE {best_de:.1f}). Cool, jewel-toned colors like this create the same "
                "luminosity as her red Edinburgh dress."
            )
        if score >= 70 or color_tier == "tier2":
            return (
                f"Good color match — closest to {pal_name} (ΔE {best_de:.1f}). "
                "Cool undertones align with Deep Winter, though slightly less dramatic "
                "than her signature Tier 1 colors."
            )
        if score >= 50 or color_tier == "tier3":
            return (
                f"Borderline match — closest to {pal_name} (ΔE {best_de:.1f}). "
                "In natural light, hold against the chin: skin should look brighter, "
                "not more tired."
            )
        return (
            f"Poor color match for Deep Winter (ΔE {best_de:.1f} from {pal_name}). "
            "Likely has warm, muted, or dusty qualities that diminish Caroline's natural luminosity."
        )
