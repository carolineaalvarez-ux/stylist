"""
Fabric content parser.

Extracts fiber composition from raw product description text using:
1. Regex patterns for "XX% Fiber" style content labels
2. Keyword matching for exclusion/preference logic
3. Scoring 0–100 based on fiber mix relative to preferences

Deep Winter preferences:
  Preferred:  100% silk (19mm+), linen, structured cotton
  Excluded:   polyester, acrylic, "satin" without silk content
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FiberEntry:
    fiber: str      # normalised lowercase name, e.g. "silk", "polyester"
    percentage: float  # 0.0–100.0


@dataclass
class FabricParseResult:
    fibers: list[FiberEntry]
    score: int              # 0–100
    has_excluded: bool
    has_preferred: bool
    exclusion_reason: str
    summary: str            # human-readable, e.g. "100% Silk"


# Canonical fibre names — maps variant spellings to canonical form
FIBER_ALIASES: dict[str, str] = {
    # Preferred
    "silk": "silk",
    "soie": "silk",           # French
    "seide": "silk",          # German
    "seta": "silk",           # Italian
    "linen": "linen",
    "lin": "linen",
    "flax": "linen",
    "cotton": "cotton",
    "cotone": "cotton",
    "coton": "cotton",
    "baumwolle": "cotton",
    # Excluded
    "polyester": "polyester",
    "poly": "polyester",
    "pet": "polyester",
    "acrylic": "acrylic",
    "acrylique": "acrylic",
    "nylon": "nylon",
    "elastane": "elastane",
    "spandex": "elastane",
    "lycra": "elastane",
    "viscose": "viscose",
    "rayon": "viscose",
    "modal": "modal",
    "lyocell": "lyocell",
    "tencel": "lyocell",
    "wool": "wool",
    "cashmere": "cashmere",
    "angora": "angora",
}

PREFERRED_FIBERS = {"silk", "linen", "cotton"}
EXCLUDED_FIBERS = {"polyester", "acrylic"}

# Satin without silk mention → excluded
_SATIN_PATTERN = re.compile(r'\bsatin\b', re.I)
_SILK_PATTERN = re.compile(r'\bsilk\b', re.I)

# Main percentage-fiber regex:  "100% Silk" or "100 percent cotton"
_FIBER_REGEX = re.compile(
    r'(\d{1,3}(?:\.\d+)?)\s*%\s*([A-Za-zÀ-ÿ\s]{2,20}?)(?=\s*[,%&/\n\r]|$|\d)',
    re.I,
)
# Also handle "Silk 100%" order
_FIBER_REGEX_REVERSE = re.compile(
    r'([A-Za-zÀ-ÿ\s]{2,20}?)\s*(\d{1,3}(?:\.\d+)?)\s*%',
    re.I,
)


class FabricParser:

    def parse(self, raw_text: str) -> FabricParseResult:
        if not raw_text or not raw_text.strip():
            return FabricParseResult([], 0, False, False, "No fabric information available.", "Unknown")

        text = raw_text.strip()
        fibers = self._extract_fibers(text)

        if not fibers:
            # No percentage breakdown — try keyword-only detection
            fibers = self._keyword_fallback(text)

        has_excluded = any(f.fiber in EXCLUDED_FIBERS for f in fibers)
        has_preferred = any(f.fiber in PREFERRED_FIBERS for f in fibers)

        exclusion_reason = ""
        if has_excluded:
            excluded_list = [f"{f.percentage:.0f}% {f.fiber}" for f in fibers if f.fiber in EXCLUDED_FIBERS]
            exclusion_reason = f"Contains excluded fiber(s): {', '.join(excluded_list)}"

        # Satin veto
        if _SATIN_PATTERN.search(text) and not _SILK_PATTERN.search(text):
            has_excluded = True
            exclusion_reason = "Listed as 'satin' without confirmed silk content"

        score = self._compute_score(fibers, has_excluded, text)
        summary = self._build_summary(fibers, text)

        return FabricParseResult(
            fibers=fibers,
            score=score,
            has_excluded=has_excluded,
            has_preferred=has_preferred,
            exclusion_reason=exclusion_reason,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract_fibers(self, text: str) -> list[FiberEntry]:
        fibers: list[FiberEntry] = []
        seen: set[str] = set()

        for m in _FIBER_REGEX.finditer(text):
            pct = float(m.group(1))
            raw_fiber = m.group(2).strip().lower().rstrip(',. ')
            canonical = self._canonicalize(raw_fiber)
            if canonical and canonical not in seen and 0 < pct <= 100:
                fibers.append(FiberEntry(fiber=canonical, percentage=pct))
                seen.add(canonical)

        if not fibers:
            for m in _FIBER_REGEX_REVERSE.finditer(text):
                raw_fiber = m.group(1).strip().lower().rstrip(',. ')
                pct = float(m.group(2))
                canonical = self._canonicalize(raw_fiber)
                if canonical and canonical not in seen and 0 < pct <= 100:
                    fibers.append(FiberEntry(fiber=canonical, percentage=pct))
                    seen.add(canonical)

        return fibers

    def _keyword_fallback(self, text: str) -> list[FiberEntry]:
        """When no percentages are given, infer likely fibers from keywords."""
        fibers = []
        lower = text.lower()
        for alias, canonical in FIBER_ALIASES.items():
            if alias in lower and canonical not in {f.fiber for f in fibers}:
                # Assign 100% if it's the only keyword found, else unknown %
                fibers.append(FiberEntry(fiber=canonical, percentage=0.0))
        return fibers

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_score(self, fibers: list[FiberEntry], has_excluded: bool, text: str) -> int:
        if has_excluded:
            return 10

        if not fibers:
            return 0

        # Silk bonus: 100% silk → max score
        silk_pct = sum(f.percentage for f in fibers if f.fiber == "silk")
        linen_pct = sum(f.percentage for f in fibers if f.fiber == "linen")
        cotton_pct = sum(f.percentage for f in fibers if f.fiber == "cotton")
        preferred_pct = silk_pct + linen_pct + cotton_pct

        if silk_pct >= 95:
            return 100
        if silk_pct >= 70:
            return 90
        if linen_pct >= 95 or cotton_pct >= 95:
            return 85
        if preferred_pct >= 70:
            return 75
        if preferred_pct >= 40:
            return 55
        if preferred_pct > 0:
            return 35
        # Unknown composition with no excluded fibers
        return 40

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _canonicalize(self, raw: str) -> str:
        raw = raw.strip().lower()
        # Direct lookup
        if raw in FIBER_ALIASES:
            return FIBER_ALIASES[raw]
        # Partial match
        for alias, canonical in FIBER_ALIASES.items():
            if alias in raw:
                return canonical
        # Unknown fiber — keep if it looks like a word
        if re.match(r'^[a-z]{3,}$', raw):
            return raw
        return ""

    @staticmethod
    def _build_summary(fibers: list[FiberEntry], raw_text: str) -> str:
        if not fibers:
            return raw_text[:60] if raw_text else "Unknown"
        parts = []
        for f in sorted(fibers, key=lambda x: -x.percentage):
            if f.percentage > 0:
                parts.append(f"{f.percentage:.0f}% {f.fiber.title()}")
            else:
                parts.append(f.fiber.title())
        return ", ".join(parts)
