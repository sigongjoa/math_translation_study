"""
Cross-Reference Narrative for PCM Translation Pipeline.

Analyzes a list of document sections and generates:
  - Backward Links: "앞서 X절에서 배운 Y 개념을 떠올려보세요."
  - Forward Links:  "여기서 배운 Z는 W절에서 핵심 역할을 합니다."

The generated text is formatted as LaTeX tcolorbox environments
(linkbox, previewbox).

Usage:
    analyzer = LinkageAnalyzer()
    sections = [
        SectionInfo(id="1.2", title="군(Group)", key_concepts=["군", "항등원", "역원"]),
        SectionInfo(id="2.1", title="환(Ring)", key_concepts=["환", "군", "분배법칙"]),
    ]
    analyzer.build_reference_map(sections)
    backward = analyzer.generate_backward_link("2.1")
    forward  = analyzer.generate_forward_link("1.2")
"""

from __future__ import annotations

import re
import requests
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SectionInfo:
    """Metadata for a single document section."""

    id: str                        # "2.3"
    title: str                     # "위상 공간"
    key_concepts: List[str]        # ["위상 공간", "열린집합", "위상"]
    text_snippet: str = ""         # First ~500 chars of section text (for LLM context)


@dataclass
class ReferenceLink:
    """A directional reference between two sections."""

    source_section_id: str
    target_section_id: str
    target_section_title: str
    shared_concepts: List[str]     # Concepts that appear in both sections
    direction: str                 # "backward" | "forward"


# ---------------------------------------------------------------------------
# Concept extractor (regex-based, no LLM needed)
# ---------------------------------------------------------------------------

# Common Korean math terms that indicate a significant concept
_CONCEPT_PATTERNS = [
    r"[가-힣]+(?:공간|집합|함수|사상|변환|구조|연산|관계|체계|군|환|체|위상|다양체|함자|범주|모듈|대수)",
    r"[가-힣]+(이즘|모픽|동형|연속|미분|적분|수렴|발산|수열|급수)",
    r"[A-Za-z][A-Za-z\s-]+-(?:체|군|환|위상|공간|함수|사상)",  # e.g. "Hilbert-공간"
    # Transliteration-form math terms (qwen2.5 often uses English loanwords)
    r"\b(?:그룹|링|필드|모노이드|부분그룹|정규부분그룹|아이디얼|호모모피즘|아이소모피즘)\b",
    # Standalone Korean math root terms NOT preceded by Korean (e.g. "군 $(G)$", "아벨 환")
    r"(?<![가-힣])(군|환|체|링|아이디얼|모노이드|범주|모듈|위상)",
]

# Mathematical root terms: compound like "부분군" → also yield root "군"
# Enables cross-section linking even when sections use different compound forms
_MATH_ROOTS = ["군", "환", "체", "공간", "집합", "함수", "사상", "변환", "위상", "대수", "모듈", "범주"]

# English math terms to extract from mixed-language text
_EN_CONCEPT_PATTERNS = [
    r"\b(?:Theorem|Lemma|Definition|Corollary)\s+[\d.]+",
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b",  # Capitalized multi-word terms
    # Common lowercase math nouns — reliable for concept overlap detection
    r"\b(?:group|ring|field|module|algebra|ideal|kernel|image|subgroup|quotient|"
    r"morphism|homomorphism|isomorphism|functor|category|topology|lattice|monoid|"
    r"vector\s+space|inner\s+product|metric\s+space|manifold|tensor)\b",
]


def extract_concepts_from_text(text: str, max_concepts: int = 20) -> List[str]:
    """
    Extract key mathematical concept names from section text.

    Returns a list of unique concept strings (Korean + English).
    """
    concepts: set = set()

    for pattern in _CONCEPT_PATTERNS:
        matches = re.findall(pattern, text)
        concepts.update(m.strip() for m in matches if len(m.strip()) >= 2)

    for i, pattern in enumerate(_EN_CONCEPT_PATTERNS):
        # Last pattern (lowercase math nouns) uses case-insensitive matching
        flags = re.IGNORECASE if i == len(_EN_CONCEPT_PATTERNS) - 1 else 0
        matches = re.findall(pattern, text, flags=flags)
        concepts.update(m.strip().lower() if i == len(_EN_CONCEPT_PATTERNS) - 1 else m.strip()
                        for m in matches if len(m.strip()) >= 3)

    # Root normalization: compound "부분군" → also add "군"
    # Enables cross-section matching when sections use different compound forms
    roots_to_add: set = set()
    for concept in concepts:
        for root in _MATH_ROOTS:
            if concept.endswith(root) and len(concept) > len(root):
                roots_to_add.add(root)
                break
    concepts.update(roots_to_add)

    # Deduplicate and trim
    result = sorted(concepts)[:max_concepts]
    return result


# ---------------------------------------------------------------------------
# Linkage Analyzer
# ---------------------------------------------------------------------------

class LinkageAnalyzer:
    """
    Builds a concept dependency map across document sections and generates
    LaTeX cross-reference narrative blocks.

    Reference map structure:
        _ref_map[section_id] = {
            "backward": [ReferenceLink, ...],  # sections BEFORE this one that share concepts
            "forward":  [ReferenceLink, ...],  # sections AFTER this one that share concepts
        }
    """

    LINKBOX_LATEX = (
        "\\newtcolorbox{{linkbox}}[1]{{\n"
        "  colback=blue!5!white, colframe=blue!40!black,\n"
        "  title=\\faLink\\, #1, fonttitle=\\bfseries, breakable\n"
        "}}\n"
    )
    PREVIEWBOX_LATEX = (
        "\\newtcolorbox{{previewbox}}[1]{{\n"
        "  colback=orange!5!white, colframe=orange!50!black,\n"
        "  title=\\faForward\\, #1, fonttitle=\\bfseries, breakable\n"
        "}}\n"
    )

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        ollama_url: str = "http://localhost:11434/api/generate",
        min_shared_concepts: int = 1,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.min_shared_concepts = min_shared_concepts
        self._sections: List[SectionInfo] = []
        self._ref_map: Dict[str, Dict[str, List[ReferenceLink]]] = {}

    # ------------------------------------------------------------------
    # Build phase
    # ------------------------------------------------------------------

    def build_reference_map(self, sections: List[SectionInfo]) -> None:
        """
        Analyse all sections and build the internal reference map.

        Must be called before generate_backward_link / generate_forward_link.
        """
        self._sections = sections
        self._ref_map = {s.id: {"backward": [], "forward": []} for s in sections}

        for i, sec in enumerate(sections):
            sec_concepts = set(c.lower() for c in sec.key_concepts)

            for j, other in enumerate(sections):
                if i == j:
                    continue
                other_concepts = set(c.lower() for c in other.key_concepts)
                shared = sec_concepts & other_concepts
                if len(shared) < self.min_shared_concepts:
                    continue

                shared_list = [c for c in sec.key_concepts if c.lower() in shared]

                if j < i:
                    # other is BEFORE sec → backward reference from sec
                    self._ref_map[sec.id]["backward"].append(
                        ReferenceLink(
                            source_section_id=sec.id,
                            target_section_id=other.id,
                            target_section_title=other.title,
                            shared_concepts=shared_list[:3],
                            direction="backward",
                        )
                    )
                else:
                    # other is AFTER sec → forward reference from sec
                    self._ref_map[sec.id]["forward"].append(
                        ReferenceLink(
                            source_section_id=sec.id,
                            target_section_id=other.id,
                            target_section_title=other.title,
                            shared_concepts=shared_list[:3],
                            direction="forward",
                        )
                    )

    # ------------------------------------------------------------------
    # Generation phase
    # ------------------------------------------------------------------

    def generate_backward_link(self, section_id: str) -> str:
        """
        Generate a LaTeX backward-link block for the given section.

        Returns empty string if no backward references exist.
        """
        links = self._ref_map.get(section_id, {}).get("backward", [])
        if not links:
            return ""

        # Pick the most relevant (most shared concepts)
        best = max(links, key=lambda l: len(l.shared_concepts))
        text = self._generate_link_text(section_id, best, direction="backward")
        if not text:
            return ""

        return (
            f"\\begin{{linkbox}}{{이전 내용과의 연결}}\n"
            f"  {text}\n"
            f"\\end{{linkbox}}\n"
        )

    def generate_forward_link(self, section_id: str) -> str:
        """
        Generate a LaTeX forward-link (preview) block for the given section.

        Returns empty string if no forward references exist.
        """
        links = self._ref_map.get(section_id, {}).get("forward", [])
        if not links:
            return ""

        best = max(links, key=lambda l: len(l.shared_concepts))
        text = self._generate_link_text(section_id, best, direction="forward")
        if not text:
            return ""

        return (
            f"\\begin{{previewbox}}{{앞으로 배울 내용}}\n"
            f"  {text}\n"
            f"\\end{{previewbox}}\n"
        )

    def get_all_links(self, section_id: str) -> Tuple[str, str]:
        """
        Convenience method: returns (backward_latex, forward_latex).
        Either may be empty string if no references exist.
        """
        return (
            self.generate_backward_link(section_id),
            self.generate_forward_link(section_id),
        )

    def validate_section_references(self, section_id: str) -> List[str]:
        """
        Validate that all referenced section IDs actually exist.

        Returns list of invalid section IDs (should be empty for correct docs).
        """
        existing_ids = {s.id for s in self._sections}
        invalid = []
        for direction in ("backward", "forward"):
            for link in self._ref_map.get(section_id, {}).get(direction, []):
                if link.target_section_id not in existing_ids:
                    invalid.append(link.target_section_id)
        return invalid

    # ------------------------------------------------------------------
    # LaTeX preamble helper
    # ------------------------------------------------------------------

    @staticmethod
    def latex_preamble() -> str:
        """Returns the tcolorbox definitions needed in the LaTeX preamble."""
        return (
            "% Cross-reference narrative boxes\n"
            "\\newtcolorbox{linkbox}[1]{\n"
            "  colback=blue!5!white, colframe=blue!40!black,\n"
            "  title=\\faLink\\, #1, fonttitle=\\bfseries, breakable\n"
            "}\n"
            "\\newtcolorbox{previewbox}[1]{\n"
            "  colback=orange!5!white, colframe=orange!50!black,\n"
            "  title=\\faForward\\, #1, fonttitle=\\bfseries, breakable\n"
            "}\n"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_link_text(
        self,
        current_section_id: str,
        link: ReferenceLink,
        direction: str,
    ) -> str:
        """
        Generate natural Korean prose for a cross-reference link using LLM.

        Falls back to a template string if LLM is unavailable.
        """
        current_info = self._get_section_info(current_section_id)
        current_title = current_info.title if current_info else current_section_id

        concepts_str = ", ".join(link.shared_concepts[:3])

        if direction == "backward":
            prompt = (
                f"수학 교재의 번역본에서 섹션 전환 문구를 한 문장으로 작성하세요.\n"
                f"현재 섹션: {current_title} ({current_section_id}절)\n"
                f"참조할 이전 섹션: {link.target_section_title} ({link.target_section_id}절)\n"
                f"공유 개념: {concepts_str}\n\n"
                f"형식: '앞서 [섹션번호]절에서 배운 [개념]을 떠올려보세요. [연결 문장]'\n"
                f"한국어로 한 문장만 출력하세요."
            )
            fallback = (
                f"앞서 \\textbf{{{link.target_section_id}절}}에서 다룬 "
                f"\\textit{{{link.shared_concepts[0] if link.shared_concepts else link.target_section_title}}}을(를) "
                f"떠올려보세요. 이번 절은 그 개념을 확장합니다."
            )
        else:
            prompt = (
                f"수학 교재의 번역본에서 섹션 예고 문구를 한 문장으로 작성하세요.\n"
                f"현재 섹션: {current_title} ({current_section_id}절)\n"
                f"연결될 다음 섹션: {link.target_section_title} ({link.target_section_id}절)\n"
                f"공유 개념: {concepts_str}\n\n"
                f"형식: '여기서 배운 [개념]은 [섹션번호]절에서 [역할]을 합니다.'\n"
                f"한국어로 한 문장만 출력하세요."
            )
            fallback = (
                f"여기서 정의한 "
                f"\\textit{{{link.shared_concepts[0] if link.shared_concepts else current_title}}}은(는) "
                f"\\textbf{{{link.target_section_id}절}} "
                f"\\textit{{{link.target_section_title}}}에서 핵심 역할을 합니다."
            )

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 80},
                },
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            # Sanitize: ensure single line, no markdown
            result = result.split("\n")[0].strip()
            return result if result else fallback
        except Exception:
            return fallback

    def _get_section_info(self, section_id: str) -> Optional[SectionInfo]:
        """Look up a SectionInfo by ID."""
        for s in self._sections:
            if s.id == section_id:
                return s
        return None
