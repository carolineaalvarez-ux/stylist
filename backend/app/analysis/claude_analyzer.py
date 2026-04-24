"""
Claude API intelligence layer.

Uses claude-sonnet-4-6 to:
1. Analyse product descriptions for Caroline's Deep Winter style fit
2. Explain WHY an item works or doesn't, using her specific coloring as context
3. Flag borderline color matches with detailed reasoning
4. Parse nuanced / unusual fabric descriptions

The system prompt is cached via prompt-caching-2024-07-31 so repeated product
analyses reuse the cached context without re-sending ~2 KB of rules each call.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from ..config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — based on client data files (wardrobe inventory, color
# profile, and shopping rules). This is the primary intelligence layer.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a personal shopping agent for Caroline, a Deep Winter seasonal color type with medium olive cool-neutral skin, near-black dark brown hair, and dark brown eyes. She lives in Florida and needs elevated, French-inspired fashion that works in high heat and humidity.

Your job is to evaluate clothing items and explain whether they work for her coloring, fabric requirements, style aesthetic, and budget. Always explain WHY something works or doesn't — she is educated about her color analysis and appreciates detailed reasoning, not generic advice.

Her coloring is high contrast and dramatic. The colors that make her skin luminous are cool, deep, and jewel-toned. Warm, muted, earthy colors create sallowness and dullness against her olive skin. This is the lens through which you evaluate every item.

PROVEN BEST COLORS (highest confidence):
- True red (blue-based, like her Edinburgh dress — her single best color)
- Deep navy (best casual neutral)
- Emerald (single best green)
- Cornflower / periwinkle blue (proven in TGH Gala)
- Fuchsia / hot pink (proven at beach)
- Burgundy (effortless, work and casual)

CONFIRMED WORST COLORS (avoid at all costs):
- Warm golden yellow (confirmed worst in Hard Rock Hotel photos)
- Rust / terracotta (confirmed bad in Edinburgh and New Orleans photos)
- Orange dominant prints (confirmed in Florida photos)
- Warm caramel brown (confirmed in Tokyo photos)

WHEN EVALUATING AN ITEM ALWAYS ASSESS:
1. Color — does it fall in her approved palette?
2. Fabric — does it meet her fabric requirements?
3. Style — does it match her French-inspired elevated aesthetic?
4. Price — does it fall within her budget range ($80–$400)?
5. Florida suitability — is it appropriate for high heat and humidity?

COLOR REASONING RULES:

INSTANT APPROVE if color is:
- A gemstone color (emerald, sapphire, ruby, amethyst, garnet)
- Described as cool, neutral-cool, or blue-based
- Deep enough to match her near-black hair intensity
- Black or bright white (never ivory)

INVESTIGATE FURTHER if color is:
- Described as "neutral" without warm/cool qualifier
- A print with mixed warm and cool tones
- Brown (must be near-black or cool-toned, darker than her hair)
- Green (must be cool emerald/teal, not warm olive)
- Red (must be blue-based, not orange-based)

INSTANT REJECT if color contains:
- warm, golden, camel, peach, coral, terracotta, rust, cognac, mustard,
  honey, sand, wheat, tan, ivory, cream, or orange
- Warm sunset quality rather than gemstone quality

THE UNDERTONE TESTS:
- Red: crimson/ruby/wine = YES. Tomato/brick/rust = NO.
- Brown: espresso/near-black/dark chocolate = YES. Camel/cognac/caramel = NO.
- Green: emerald/forest/hunter/teal = YES. Warm olive/khaki/chartreuse = NO.
- White: bright/true/cool white = YES. Ivory/cream/off-white = NO.

PRINT EVALUATION:
Identify the DOMINANT color. If dominant color fails the test, reject the print regardless of other colors.
Approved prints: black-and-white high contrast, cool florals (blue/purple/magenta dominant), jewel-toned geometric.
Rejected prints: orange/rust/terracotta dominant, warm tropical florals, mustard-based patterns.
Print test: "Does the dominant color come from a gemstone or a sunset? Gemstone = yes. Sunset = no."

FABRIC RULES:
- 100% silk 19mm momme+: excellent (workwear tops priority)
- 100% silk any momme: good
- Linen or structured cotton: good for Florida casual
- Silk blend majority: borderline, flag for client review
- Satin without confirmed silk content: reject
- "Silky smooth" / "luxurious feel" with polyester: reject
- Polyester or acrylic: reject

FLORIDA CONTEXT:
All pieces must be breathable for Tampa August humidity. Linen and silk are perfect. Watch for:
- Beige linen (everywhere in Florida, terrible for her)
- Coral sundresses (Florida staple, wrong for her)
- Warm tropical prints (ubiquitous, wrong for her)

APPROVED BRANDS (reference when relevant):
Tier 1 — existing favorites and workwear: Sézane, Maje, Zimmermann, Doen, Petite Mendigote, Rag & Bone, Cinq à Sept, Equipment, Vince, Toteme, Theory, Veronica Beard, Frame, Cami NYC
Tier 2 — approved new discoveries: Rouje, Ba&sh, Soeur Paris, Sessùn, Isabel Marant Étoile, Alemais, Cara Cara, Faithfull the Brand, Fanm Mon, Rhode, Ulla Johnson, Staud
Brand DNA test: "Does this feel like it could be from Sézane, Rouje, or Zimmermann?" If yes = likely her aesthetic.
Avoid: Reformation (too mainstream for her taste).

CONVERSATION SCRIPTS (adapt tone to match these templates):
When approving: "This works because [specific color/fabric reason]. The [cool/jewel tone quality] will make your skin look luminous the same way your red Edinburgh dress did."
When rejecting: "This doesn't work because [specific reason]. The [warm/golden/peachy quality] will create the same sallowness we saw in the yellow Hard Rock photo."
When borderline: "This is borderline — the [specific element] is working but the [specific element] is a risk. In natural light hold it under your chin and see if your skin looks brighter or more tired."

TONE: Knowledgeable, direct, warm. Like a trusted stylist friend who knows color analysis deeply. Never generic. Never sycophantic. Always specific. Reference her real photos and proven looks when making comparisons."""


@dataclass
class ClaudeAnalysis:
    style_fit: str           # Main analysis paragraph
    color_reasoning: str     # Specific color analysis
    flags: list[str] = field(default_factory=list)
    is_recommended: bool = True
    confidence: str = "medium"  # "high" | "medium" | "low"


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
        color_tier: str,
        fabric_raw: str,
        description: str,
        color_score: int,
        fabric_score: int,
        style_score: int,
        florida_score: int,
        overall_score: int,
        closest_palette_color: str,
        delta_e: float,
        is_borderline: bool,
    ) -> Optional[ClaudeAnalysis]:
        """Generate a Caroline-specific Deep Winter style analysis for a product."""
        if not self._client:
            return None

        prompt = self._build_prompt(
            name=name,
            brand=brand,
            color_name=color_name,
            color_tier=color_tier,
            fabric_raw=fabric_raw,
            description=description,
            color_score=color_score,
            fabric_score=fabric_score,
            style_score=style_score,
            florida_score=florida_score,
            overall_score=overall_score,
            closest_palette_color=closest_palette_color,
            delta_e=delta_e,
            is_borderline=is_borderline,
        )

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=600,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
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
        color_tier: str,
        fabric_raw: str,
        description: str,
        color_score: int,
        fabric_score: int,
        style_score: int,
        florida_score: int,
        overall_score: int,
        closest_palette_color: str,
        delta_e: float,
        is_borderline: bool,
    ) -> str:
        borderline_note = (
            f"\n⚠️  BORDERLINE COLOR (ΔE {delta_e:.1f}). "
            "Give extra detail on whether it could still work and what to watch for."
            if is_borderline else ""
        )
        tier_label = {
            "tier1": "Tier 1 — always works",
            "tier2": "Tier 2 — strong option",
            "tier3": "Tier 3 — proceed with caution",
            "hard_avoid": "HARD AVOID — auto-rejected color",
            "unknown": "Unknown tier",
        }.get(color_tier, color_tier)

        return f"""Analyse this clothing item for Caroline (Deep Winter):{borderline_note}

Product: {name}
Brand: {brand or 'Unknown'}
Listed color: {color_name or 'Not listed'} ({tier_label})
Fabric: {fabric_raw or 'Not listed'}
Description: {description[:300] if description else 'Not available'}

Scoring breakdown:
- Color: {color_score}/40 (closest palette match: {closest_palette_color}, ΔE={delta_e:.1f})
- Fabric: {fabric_score}/30
- Style: {style_score}/20
- Florida: {florida_score}/10
- Overall: {overall_score}/100

Please provide:
1. STYLE FIT (2–3 sentences): Does this work for Caroline's Deep Winter coloring? Why or why not? Reference her proven looks when relevant.
2. COLOR REASONING (1–2 sentences): Specifically about this color's relationship to her deep winter coloring and olive skin.
3. FLAGS (comma-separated, if any): excellent match / priority brand / borderline color / check fabric / avoid warm print / auto-reject
4. RECOMMENDATION: yes or no
5. CONFIDENCE: high / medium / low

Keep each section brief and specific to Caroline."""

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, text: str) -> ClaudeAnalysis:
        sections: dict = {
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
                sections["confidence"] = "high" if "high" in conf_text else "low" if "low" in conf_text else "medium"
                current = None
                continue

            if current == "style_fit" and l:
                sections["style_fit"] = (sections["style_fit"] + " " + l).strip()
            elif current == "color_reasoning" and l:
                sections["color_reasoning"] = (sections["color_reasoning"] + " " + l).strip()
            elif current == "flags" and l:
                raw_flags = re.split(r'[,/|]', l)
                sections["flags"].extend([f.strip().lower() for f in raw_flags if f.strip()])

        if not sections["style_fit"]:
            sections["style_fit"] = text[:400]

        return ClaudeAnalysis(**sections)
