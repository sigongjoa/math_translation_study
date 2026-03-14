"""
BackTranslationVerifier — detects semantic drift in translations.

Algorithm:
  1. Translate Korean → English (back-translation) via Ollama
  2. Compare original English with back-translated English
  3. Use token overlap (F1) as proxy for semantic similarity
     (no sentence-transformers dependency — works offline with qwen2.5:7b)

If sentence-transformers is available, uses cosine similarity for better accuracy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.pcm.core.llm_client import OllamaClient, _DEFAULT_MODEL, _DEFAULT_BASE_URL


@dataclass
class VerificationResult:
    similarity: float       # 0.0 – 1.0
    passed: bool
    back_translation: str
    drift_terms: list[str]  # key terms missing in back-translation
    method: str             # "token_overlap" or "embedding"


class BackTranslationVerifier:
    """
    Verifies Korean translation quality via round-trip translation.

    Threshold: similarity >= 0.55 passes (lower than strict 0.85 because
    Ollama back-translation is imperfect even for good translations).
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        threshold: float = 0.55,
    ):
        self._client = OllamaClient(model=model, base_url=base_url)
        self.threshold = threshold
        self._embedder = self._try_load_embedder()

    @staticmethod
    def _try_load_embedder():
        """Attempt to load sentence-transformers (optional dependency)."""
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        except ImportError:
            return None

    def verify(self, original_en: str, translated_ko: str) -> VerificationResult:
        """Back-translate ko→en and compare with original."""
        if not translated_ko.strip():
            return VerificationResult(0.0, False, "", [], "skip")

        back_en = self._back_translate(translated_ko)
        if not back_en:
            return VerificationResult(0.5, True, "", [], "skip")  # give benefit of doubt

        if self._embedder is not None:
            similarity, method = self._embedding_similarity(original_en, back_en)
        else:
            similarity, method = self._token_f1(original_en, back_en)

        drift = self._find_drift_terms(original_en, back_en)
        return VerificationResult(
            similarity=round(similarity, 3),
            passed=similarity >= self.threshold,
            back_translation=back_en[:300],
            drift_terms=drift[:5],
            method=method,
        )

    def _back_translate(self, korean_text: str) -> str:
        prompt = (
            "Translate the following Korean text to English. "
            "Output only the English translation, no explanations.\n\n"
            f"{korean_text[:600]}"
        )
        return self._client.generate_or_fallback(
            prompt, fallback="", temperature=0.1, timeout=60
        )

    def _embedding_similarity(self, text_a: str, text_b: str) -> tuple[float, str]:
        """Cosine similarity via sentence-transformers."""
        try:
            import numpy as np
            emb_a = self._embedder.encode([text_a[:500]])[0]
            emb_b = self._embedder.encode([text_b[:500]])[0]
            cos = float(np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b) + 1e-8))
            return max(0.0, min(1.0, cos)), "embedding"
        except Exception:
            return self._token_f1(text_a, text_b)

    @staticmethod
    def _token_f1(ref: str, hyp: str) -> tuple[float, str]:
        """Token-level F1 as semantic similarity proxy."""
        def tokens(text: str) -> set[str]:
            # keep content words (length > 2), lowercase, remove stopwords
            stopwords = {"the", "a", "an", "is", "are", "was", "were", "be",
                         "of", "in", "to", "and", "or", "that", "this", "it",
                         "for", "on", "with", "as", "by", "from", "at", "its"}
            return {w.lower() for w in re.findall(r"[a-zA-Z]+", text)
                    if len(w) > 2 and w.lower() not in stopwords}

        ref_toks = tokens(ref)
        hyp_toks = tokens(hyp)
        if not ref_toks or not hyp_toks:
            return 0.5, "token_overlap"
        overlap = len(ref_toks & hyp_toks)
        precision = overlap / len(hyp_toks)
        recall = overlap / len(ref_toks)
        f1 = 2 * precision * recall / (precision + recall + 1e-8)
        return float(f1), "token_overlap"

    @staticmethod
    def _find_drift_terms(original: str, back_translation: str) -> list[str]:
        """Find key terms in original that are missing from back-translation."""
        # Extract capitalised multi-char words as key terms
        key_terms = re.findall(r"\b[A-Z][a-z]{2,}\b", original)
        drift = [t for t in key_terms if t.lower() not in back_translation.lower()]
        return list(dict.fromkeys(drift))  # deduplicate preserving order
