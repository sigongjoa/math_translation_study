"""
Motivation Agent for PCM Translation Pipeline.

Generates a 2-3 sentence "why this matters" motivation block
before high-abstraction theorem/definition blocks.

Output format:
  LaTeX:  \\begin{motivation}...\\end{motivation}
  Typst:  #motivation-block[...] (via inject_into_typst)

Only fires when:
  - block_type in ("theorem", "definition", "lemma")
  - abstraction_score >= threshold (default 0.6)
"""

from __future__ import annotations

import requests


class MotivationAgent:
    """
    Generates Korean motivation blocks for high-abstraction math concepts.

    Calls a local Ollama instance to produce the motivation text.
    All methods are safe to call even when Ollama is unavailable —
    failures return empty strings gracefully.
    """

    #: Block types that can receive motivation blocks
    SUPPORTED_TYPES = ("theorem", "definition", "lemma")

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        threshold: float = 0.6,
        ollama_url: str = "http://localhost:11434/api/generate",
    ):
        self.model = model
        self.threshold = threshold
        self.ollama_url = ollama_url

    # ------------------------------------------------------------------
    # Decision gate
    # ------------------------------------------------------------------

    def should_generate(self, block_type: str, abstraction_score: float) -> bool:
        """
        Returns True when a motivation block should be generated.

        Conditions:
          - block_type must be in SUPPORTED_TYPES
          - abstraction_score must be >= self.threshold
        """
        return (
            block_type in self.SUPPORTED_TYPES
            and abstraction_score >= self.threshold
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        unit_text: str,
        domain: str,
        section_title: str = "",
    ) -> str:
        """
        Generates motivation block text (Korean).

        Returns empty string on failure (network error, Ollama unavailable, etc.).

        Parameters
        ----------
        unit_text:
            The full text of the knowledge unit (used as context).
            Only the first 500 characters are sent to the model.
        domain:
            Mathematical domain string, e.g. "algebra", "analysis".
        section_title:
            Optional section title for extra context.
        """
        context_snippet = unit_text[:500]
        section_hint = f" ({section_title})" if section_title else ""

        prompt = (
            f"다음 수학 개념({domain} 분야{section_hint})에 대해 독자가 이해하기 전에 읽으면 좋을 "
            f"\"왜 이 개념이 필요한가?\"를 2-3문장으로 간략히 설명하세요.\n"
            f"- 수식 없이 자연어로만 설명하세요.\n"
            f"- 수학적 동기나 역사적 맥락을 담으세요.\n"
            f"- 한국어로 작성하세요.\n\n"
            f"개념:\n{context_snippet}\n\n동기 설명:"
        )

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 150,
                    },
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Injection helpers
    # ------------------------------------------------------------------

    def inject_into_translation(
        self,
        translated_text: str,
        motivation: str,
    ) -> str:
        """
        Prepends a LaTeX motivation block to the translated text.

        If *motivation* is empty, *translated_text* is returned unchanged.
        """
        if not motivation:
            return translated_text
        return (
            f"\\begin{{motivation}}\n{motivation}\n\\end{{motivation}}\n\n"
            f"{translated_text}"
        )

    def inject_into_typst(
        self,
        translated_text: str,
        motivation: str,
    ) -> str:
        """
        Prepends a Typst motivation block to the translated text.

        If *motivation* is empty, *translated_text* is returned unchanged.
        """
        if not motivation:
            return translated_text
        return f"#motivation-block[\n{motivation}\n]\n\n{translated_text}"

    # ------------------------------------------------------------------
    # Convenience: generate + inject in one call
    # ------------------------------------------------------------------

    def process(
        self,
        translated_text: str,
        unit_text: str,
        block_type: str,
        abstraction_score: float,
        domain: str,
        section_title: str = "",
        output_format: str = "latex",
    ) -> str:
        """
        Full pipeline: check gate → generate → inject.

        Parameters
        ----------
        translated_text:
            The already-translated Korean text.
        unit_text:
            Original (English) text of the unit, used for generation context.
        block_type:
            Classified block type.
        abstraction_score:
            Float 0.0-1.0 from SemanticChunker.
        domain:
            Mathematical domain.
        section_title:
            Optional section title for richer context.
        output_format:
            "latex" (default) or "typst".

        Returns
        -------
        str
            Translated text, possibly prepended with a motivation block.
        """
        if not self.should_generate(block_type, abstraction_score):
            return translated_text

        motivation = self.generate(unit_text, domain, section_title)
        if not motivation:
            return translated_text

        if output_format == "typst":
            return self.inject_into_typst(translated_text, motivation)
        return self.inject_into_translation(translated_text, motivation)
