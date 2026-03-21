"""
Semantic Chunker for PCM Translation Pipeline.

Groups TextBlocks into KnowledgeUnits for optimal translation chunking.
Each KnowledgeUnit represents a semantically coherent piece of the document
(e.g. a theorem together with its proof, or a definition with examples).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from src.pcm.core.layout_parser import TextBlock


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeUnit:
    """A semantically coherent unit for translation."""

    id: str                    # "unit_015_001"
    unit_type: str             # "theorem_with_proof" / "definition_with_example" /
                               # "body" / "remark_cluster" / "figure" / "standalone"
    blocks: List[TextBlock]
    primary_block: TextBlock   # the "main" block (theorem or definition)
    context_text: str          # combined text for translation
    section_id: str            # e.g. "2.3"
    abstraction_score: float   # 0.0-1.0, based on latex density + term frequency


# ---------------------------------------------------------------------------
# Semantic Chunker
# ---------------------------------------------------------------------------

class SemanticChunker:
    """
    Groups TextBlocks into KnowledgeUnits for optimal translation chunking.

    Rules
    -----
    - Theorem/Lemma/Corollary + its following Proof → one unit
      (type: "theorem_with_proof")
    - Definition + following Example(s) → one unit
      (type: "definition_with_example")
    - Multiple consecutive Remarks → one unit (type: "remark_cluster")
    - Body paragraphs between major blocks → one unit per paragraph cluster
      (type: "body")
    - Figure/Table → standalone unit (type: "figure")
    - Footnote → standalone unit (type: "footnote")
    - Lone Corollary or Lemma (no following proof) → "standalone"

    abstraction_score is computed from LaTeX density + known math term
    frequency (via KnowledgeManager when available).
    """

    # Block types that can "anchor" a grouped unit
    _THEOREM_TYPES = {"theorem", "lemma", "corollary"}
    _DEFINITION_TYPES = {"definition"}
    _REMARK_TYPES = {"remark"}
    _STANDALONE_TYPES = {"figure", "table", "footnote"}

    def __init__(self):
        try:
            from src.pcm.core.knowledge_manager import KnowledgeManager
            self.km = KnowledgeManager()
        except Exception:
            self.km = None

        self._unit_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(self, blocks: List[TextBlock], section_id: str = "unknown") -> List[KnowledgeUnit]:
        """
        Main method: groups blocks into KnowledgeUnits.

        Iterates through blocks with a look-ahead strategy:
        once an "anchor" block is identified, subsequent compatible blocks
        are absorbed into the same unit until a boundary is detected.
        """
        if not blocks:
            return []

        units: List[KnowledgeUnit] = []
        i = 0

        while i < len(blocks):
            block = blocks[i]
            btype = block.block_type

            # ----------------------------------------------------------
            # Standalone types: figure, table, footnote
            # ----------------------------------------------------------
            if btype in self._STANDALONE_TYPES:
                unit = self._make_unit(
                    unit_type=btype,
                    group=[block],
                    primary=block,
                    section_id=section_id,
                )
                units.append(unit)
                i += 1
                continue

            # ----------------------------------------------------------
            # Theorem / Lemma / Corollary — absorb following proof
            # ----------------------------------------------------------
            if btype in self._THEOREM_TYPES:
                group = [block]
                j = i + 1
                while j < len(blocks) and blocks[j].block_type == "proof":
                    group.append(blocks[j])
                    j += 1
                unit_type = "theorem_with_proof" if len(group) > 1 else "standalone"
                unit = self._make_unit(
                    unit_type=unit_type,
                    group=group,
                    primary=block,
                    section_id=section_id,
                )
                units.append(unit)
                i = j
                continue

            # ----------------------------------------------------------
            # Definition — absorb following examples
            # ----------------------------------------------------------
            if btype in self._DEFINITION_TYPES:
                group = [block]
                j = i + 1
                while j < len(blocks) and blocks[j].block_type == "example":
                    group.append(blocks[j])
                    j += 1
                unit_type = "definition_with_example" if len(group) > 1 else "standalone"
                unit = self._make_unit(
                    unit_type=unit_type,
                    group=group,
                    primary=block,
                    section_id=section_id,
                )
                units.append(unit)
                i = j
                continue

            # ----------------------------------------------------------
            # Remark / Note / Observation — cluster consecutive ones
            # ----------------------------------------------------------
            if btype in self._REMARK_TYPES:
                group = [block]
                j = i + 1
                while j < len(blocks) and blocks[j].block_type in self._REMARK_TYPES:
                    group.append(blocks[j])
                    j += 1
                unit = self._make_unit(
                    unit_type="remark_cluster",
                    group=group,
                    primary=block,
                    section_id=section_id,
                )
                units.append(unit)
                i = j
                continue

            # ----------------------------------------------------------
            # Example (standalone, not following a definition)
            # ----------------------------------------------------------
            if btype == "example":
                unit = self._make_unit(
                    unit_type="standalone",
                    group=[block],
                    primary=block,
                    section_id=section_id,
                )
                units.append(unit)
                i += 1
                continue

            # ----------------------------------------------------------
            # Proof (orphaned — no theorem precedes it)
            # ----------------------------------------------------------
            if btype == "proof":
                unit = self._make_unit(
                    unit_type="standalone",
                    group=[block],
                    primary=block,
                    section_id=section_id,
                )
                units.append(unit)
                i += 1
                continue

            # ----------------------------------------------------------
            # Body text — cluster consecutive body blocks
            # ----------------------------------------------------------
            group = [block]
            j = i + 1
            while j < len(blocks) and blocks[j].block_type == "body":
                group.append(blocks[j])
                j += 1
            unit = self._make_unit(
                unit_type="body",
                group=group,
                primary=block,
                section_id=section_id,
            )
            units.append(unit)
            i = j

        return units

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_unit(
        self,
        unit_type: str,
        group: List[TextBlock],
        primary: TextBlock,
        section_id: str,
    ) -> KnowledgeUnit:
        self._unit_counter += 1
        page = primary.page
        unit_id = f"unit_{page:03d}_{self._unit_counter:03d}"
        context_text = self._combine_text(group)
        abstraction_score = self._compute_abstraction_score(context_text)
        return KnowledgeUnit(
            id=unit_id,
            unit_type=unit_type,
            blocks=group,
            primary_block=primary,
            context_text=context_text,
            section_id=section_id,
            abstraction_score=abstraction_score,
        )

    def _compute_abstraction_score(self, text: str) -> float:
        """
        Counts LaTeX density and math term frequency.

        Score = min(1.0, formula_count * 0.1 + term_count * 0.05)
        """
        # Count both inline ($...$) and display ($$...$$) formulas
        # Use a simple non-overlapping approach: find $$ first, then $
        formula_count = len(re.findall(r'\$\$[^$]+\$\$', text))
        # Remaining text after removing $$...$$ for inline count
        inline_text = re.sub(r'\$\$[^$]+\$\$', '', text)
        formula_count += len(re.findall(r'\$[^$]+\$', inline_text))

        term_count = 0
        if self.km is not None:
            all_terms: set = set()
            for domain in ("algebra", "analysis", "topology", "category_theory",
                           "general", "number_theory", "geometry"):
                try:
                    all_terms.update(self.km.get_all_for_domain(domain).keys())
                except Exception:
                    pass
            text_lower = text.lower()
            term_count = sum(1 for t in all_terms if t.lower() in text_lower)

        return min(1.0, formula_count * 0.1 + term_count * 0.05)

    def _combine_text(self, blocks: List[TextBlock]) -> str:
        """Joins block contents with appropriate separators."""
        if not blocks:
            return ""
        parts: List[str] = []
        for block in blocks:
            content = block.content.strip()
            if content:
                parts.append(content)
        return "\n\n".join(parts)
