"""
Companion Explainer for PCM Translation Pipeline.

Generates a plain-language (平易語) side note alongside formal mathematical
text to serve both novice and expert readers simultaneously.

Layout strategy:
  - Uses a tcolorbox sidenote instead of paracol (simpler, portable)
  - Inserts inline after the formal block
  - Controls density: max MAX_PER_PAGE explanations per page

Activation gate:
  - abstraction_score >= threshold (default 0.4)
  - block must contain at least MIN_LATEX_COUNT LaTeX formulas
  - at most MAX_PER_PAGE explanations allowed per page

Output format:
  \\begin{plainexplain}
    <plain language text>
  \\end{plainexplain}

  Requires in LaTeX preamble:
    \\newtcolorbox{plainexplain}{...}  (see CompanionExplainer.latex_preamble())
"""

from __future__ import annotations

import re
import requests
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ExplanationResult:
    """Result of a companion explanation attempt."""

    formal_text: str       # The original formal text (unchanged)
    plain_text: str        # Generated plain explanation (empty if skipped)
    added: bool            # Whether an explanation was actually generated
    output: str            # Combined LaTeX (formal + optional plainexplain box)


# ---------------------------------------------------------------------------
# Companion Explainer
# ---------------------------------------------------------------------------

class CompanionExplainer:
    """
    Generates plain-language companion notes for formal math blocks.

    Parameters
    ----------
    model:
        Ollama model name.
    threshold:
        Minimum abstraction_score to trigger explanation generation.
    max_per_page:
        Maximum number of explanations to insert per page (density control).
    min_latex_count:
        Minimum number of LaTeX formulas required to trigger generation.
        Prevents explanations on purely textual paragraphs.
    """

    MIN_LATEX_COUNT = 1

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        ollama_url: str = "http://localhost:11434/api/generate",
        threshold: float = 0.4,
        max_per_page: int = 2,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.threshold = threshold
        self.max_per_page = max_per_page

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------

    def should_explain(
        self,
        formal_text: str,
        abstraction_score: float,
        page_explanation_count: int,
    ) -> bool:
        """
        Decide whether to generate a companion explanation.

        Returns False when:
          - abstraction_score < threshold
          - fewer than MIN_LATEX_COUNT formulas present
          - page_explanation_count >= max_per_page
        """
        if abstraction_score < self.threshold:
            return False
        if page_explanation_count >= self.max_per_page:
            return False
        latex_count = self._count_latex(formal_text)
        if latex_count < self.MIN_LATEX_COUNT:
            return False
        return True

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_plain(self, formal_text: str, domain: str = "mathematics") -> str:
        """
        Generate a 2-3 sentence plain-language explanation.

        Returns empty string on failure.
        """
        snippet = formal_text[:500]
        prompt = (
            f"다음 수학 텍스트({domain} 분야)를 수식 없이 일상 언어로 2-3문장으로 설명하세요.\n"
            f"- 전문 용어 대신 일상 언어를 사용하세요.\n"
            f"- 수식의 직관적 의미를 비유나 예시로 설명하세요.\n"
            f"- 독자에게 직접 말하는 어투(해설자 스타일)로 작성하세요.\n"
            f"- 한국어로 작성하세요.\n\n"
            f"수학 텍스트:\n{snippet}\n\n"
            f"평이한 설명:"
        )

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 150},
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Injection
    # ------------------------------------------------------------------

    def inject(self, formal_text: str, plain_text: str) -> str:
        """
        Append a LaTeX plainexplain box after the formal text.

        If plain_text is empty, returns formal_text unchanged.
        """
        if not plain_text:
            return formal_text
        return (
            f"{formal_text}\n\n"
            f"\\begin{{plainexplain}}\n"
            f"  {plain_text}\n"
            f"\\end{{plainexplain}}"
        )

    # ------------------------------------------------------------------
    # Convenience: full pipeline in one call
    # ------------------------------------------------------------------

    def process(
        self,
        formal_text: str,
        abstraction_score: float,
        domain: str = "mathematics",
        page_explanation_count: int = 0,
    ) -> ExplanationResult:
        """
        Full pipeline: gate → generate → inject.

        Parameters
        ----------
        formal_text:
            Already-translated formal Korean text.
        abstraction_score:
            Float 0.0-1.0 from SemanticChunker.
        domain:
            Mathematical domain string.
        page_explanation_count:
            How many explanations have already been added on this page.

        Returns
        -------
        ExplanationResult with .output ready to use in the document.
        """
        if not self.should_explain(formal_text, abstraction_score, page_explanation_count):
            return ExplanationResult(
                formal_text=formal_text,
                plain_text="",
                added=False,
                output=formal_text,
            )

        plain_text = self.generate_plain(formal_text, domain)
        output = self.inject(formal_text, plain_text)

        return ExplanationResult(
            formal_text=formal_text,
            plain_text=plain_text,
            added=bool(plain_text),
            output=output,
        )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def latex_preamble() -> str:
        """Returns the tcolorbox definition required in the LaTeX preamble."""
        return (
            "% Companion Explainer — plain language side note\n"
            "\\newtcolorbox{plainexplain}{\n"
            "  colback=yellow!8!white,\n"
            "  colframe=yellow!60!black,\n"
            "  title=\\faCommentAlt\\, 평이한 해설,\n"
            "  fonttitle=\\small\\bfseries,\n"
            "  breakable\n"
            "}\n"
        )

    @staticmethod
    def _count_latex(text: str) -> int:
        """Count the number of LaTeX formula occurrences in text."""
        display = len(re.findall(r'\$\$[^$]+\$\$', text))
        inline_text = re.sub(r'\$\$[^$]+\$\$', '', text)
        inline = len(re.findall(r'\$[^$\n]+\$', inline_text))
        env_count = len(re.findall(r'\\begin\{(?:equation|align|gather|multline)\*?\}', text))
        return display + inline + env_count
