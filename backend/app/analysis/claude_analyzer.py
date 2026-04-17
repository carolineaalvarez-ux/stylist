"""
Claude API intelligence layer.

Uses claude-sonnet-4-6 to:
1. Analyse product descriptions for Deep Winter style fit
2. Explain WHY an item works or doesn't for Deep Winter coloring
3. Flag borderline color matches with detailed reasoning
4. Parse nuanced / unusual fabric descriptions
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import anthropic

from ..config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a personal stylist and color analyst specialising in seasonal color analysis,
specifically the Deep Winter palette. You help a client find clothing that maximises their natural
coloring through careful color and fabric analysis.

DEEP WINTER COLOR PROFILE
Best colors: Black, Bright White, Emerald, Royal Blue, True Red, Burgundy, Deep Plum, Fuchsia,
Cobalt, Charcoal, Navy, Teal, Mahogany.
All colors should be COOL-toned, CLEAR (not muted or dusty), and HIGH-CONTRAST.

COLORS TO AVOID: Camel, tan, beige, ivory, cream, mustard, warm yellow, peach, coral, orange,
warm terracotta, warm olive green. These warm, muted tones wash out Deep Winter coloring.

FABRIC PREFERENCES: 100% silk (19mm momme+), linen, structured cotton. Avoid polyester, acrylic,
and "satin" that isn't silk-based.

Respond concisely and practically. Focus on actionable styling insight.
"""


@dataclass
class ClaudeAnalysis:
    style_fit: str          # Main analysis paragraph
    color_reasoning: str    # Specific color analysis
    flags: list[str]        # ["borderline color", "check fabric", etc.]
    is_recommended: bool
    confidence: str         # "high" | "medium" | "low"


class ClaudeAnalyzer:
    def __init__(self):
        if settings.anthropic_api_key:
            self._client: Optional[anthropic.AsyncAnthropic] = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
            )
        else:
            self._client = None
            logger.warning("ANTHROPIC_API_KEY not set — Claude analysis will be skipped")

    async def analyze_product(
        self,
        name: str,
        brand: str,
        color_name: str,
        fabric_raw: str,
        description: str,
        color_score: int,
        closest_palette_color: str,
        delta_e: float,
        is_borderline: bool,
    ) -> Optional[ClaudeAnalysis]:
        """Generate a full Deep Winter style analysis for a product."""
        if not self._client:
            return None

        prompt = self._build_prompt(
            name=name,
            brand=brand,
            color_name=color_name,
            fabric_raw=fabric_raw,
            description=description,
            color_score=color_score,
            closest_palette_color=closest_palette_color,
            delta_e=delta_e,
            is_borderline=is_borderline,
        )

        try:
            response = await self._client.messages.create(  # type: ignore[union-attr]
                model="claude-sonnet-4-6",
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            )
            text = response.content[0].text
            return self._parse_response(text)
        except Exception as exc:
            logger.error("Claude analysis failed for '%s': %s", name, exc)
            return None

    async def parse_fabric(self, raw_description: str) -> str:
        """
        Use Claude to extract fabric/composition from a tricky description
        that the regex parser couldn't parse cleanly.
        """
        if not self._client:
            return raw_description

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Extract ONLY the fiber composition from this product description. "
                            f"Format: '80% Silk, 20% Cotton' style. If no composition is present, "
                            f"reply 'Unknown'.\n\nDescription: {raw_description[:500]}"
                        ),
                    }
                ],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.error("Claude fabric parse failed: %s", exc)
            return raw_description

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        name: str,
        brand: str,
        color_name: str,
        fabric_raw: str,
        description: str,
        color_score: int,
        closest_palette_color: str,
        delta_e: float,
        is_borderline: bool,
    ) -> str:
        borderline_note = (
            "\n⚠️  NOTE: This is a BORDERLINE color match (ΔE {:.1f}). "
            "Please give extra detail on whether it could still work.".format(delta_e)
            if is_borderline else ""
        )
        return f"""Analyse this clothing item for a Deep Winter client:{borderline_note}

Product: {name}
Brand: {brand}
Listed color: {color_name}
Fabric: {fabric_raw or 'Not listed'}
Description: {description[:300] if description else 'Not available'}

Color analysis score: {color_score}/100 (closest palette match: {closest_palette_color}, ΔE={delta_e:.1f})

Please provide:
1. STYLE FIT (2–3 sentences): Does this work for Deep Winter? Why or why not?
2. COLOR REASONING (1–2 sentences): Specifically about the color's relationship to Deep Winter.
3. FLAGS (comma-separated, if any): borderline color / check fabric / priority brand / excellent match / avoid
4. RECOMMENDATION: yes or no
5. CONFIDENCE: high / medium / low

Keep each section brief and practical."""

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, text: str) -> ClaudeAnalysis:
        import re

        sections = {
            "style_fit": "",
            "color_reasoning": "",
            "flags": [],
            "is_recommended": True,
            "confidence": "medium",
        }

        lines = text.strip().split("\n")
        current = None

        for line in lines:
            l = line.strip()
            if not l:
                continue
            if re.match(r'^1[\.\)]\s*STYLE FIT', l, re.I) or l.upper().startswith("STYLE FIT"):
                current = "style_fit"
                l = re.sub(r'^1[\.\)]\s*STYLE FIT[\s:]*', '', l, flags=re.I).strip()
            elif re.match(r'^2[\.\)]\s*COLOR REASONING', l, re.I) or l.upper().startswith("COLOR REASONING"):
                current = "color_reasoning"
                l = re.sub(r'^2[\.\)]\s*COLOR REASONING[\s:]*', '', l, flags=re.I).strip()
            elif re.match(r'^3[\.\)]\s*FLAGS', l, re.I) or l.upper().startswith("FLAGS"):
                current = "flags"
                l = re.sub(r'^3[\.\)]\s*FLAGS[\s:]*', '', l, flags=re.I).strip()
            elif re.match(r'^4[\.\)]\s*RECOMMENDATION', l, re.I) or l.upper().startswith("RECOMMENDATION"):
                rec_text = re.sub(r'^4[\.\)]\s*RECOMMENDATION[\s:]*', '', l, flags=re.I).strip().lower()
                sections["is_recommended"] = "yes" in rec_text or "recommend" in rec_text
                current = None
                continue
            elif re.match(r'^5[\.\)]\s*CONFIDENCE', l, re.I) or l.upper().startswith("CONFIDENCE"):
                conf_text = re.sub(r'^5[\.\)]\s*CONFIDENCE[\s:]*', '', l, flags=re.I).strip().lower()
                if "high" in conf_text:
                    sections["confidence"] = "high"
                elif "low" in conf_text:
                    sections["confidence"] = "low"
                else:
                    sections["confidence"] = "medium"
                current = None
                continue

            if current == "style_fit" and l:
                sections["style_fit"] = (sections["style_fit"] + " " + l).strip()
            elif current == "color_reasoning" and l:
                sections["color_reasoning"] = (sections["color_reasoning"] + " " + l).strip()
            elif current == "flags" and l:
                raw_flags = re.split(r'[,/|]', l)
                sections["flags"].extend([f.strip().lower() for f in raw_flags if f.strip()])

        # Fallback: if parsing failed, treat whole response as style_fit
        if not sections["style_fit"]:
            sections["style_fit"] = text[:400]

        return ClaudeAnalysis(**sections)
