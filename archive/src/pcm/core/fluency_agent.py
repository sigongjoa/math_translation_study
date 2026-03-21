"""
FluencyAgent — G-Eval style multi-dimensional translation quality scorer.

Replaces the unreliable single-score TCR evaluator with a rubric-based
approach that prevents random high scores for untranslated text.

Dimensions scored 1-10 each:
  - accuracy:   Meaning preserved from English original
  - fluency:    Natural, grammatically correct Korean
  - tone:       Appropriate academic / technical register
  - terminology: Correct use of required glossary terms
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from src.pcm.core.llm_client import OllamaClient, _DEFAULT_MODEL, _DEFAULT_BASE_URL


@dataclass
class FluencyScore:
    accuracy: int = 0       # 1-10: meaning preserved
    fluency: int = 0        # 1-10: natural Korean
    tone: int = 0           # 1-10: academic register
    terminology: int = 0    # 1-10: glossary compliance
    critique: str = ""
    language_ok: bool = True   # False if not Korean

    @property
    def total(self) -> float:
        """Weighted total out of 100."""
        return round(
            self.accuracy * 3.0
            + self.fluency * 3.0
            + self.tone * 2.0
            + self.terminology * 2.0,
            1,
        )

    @property
    def passed(self) -> bool:
        return self.total >= 70 and self.language_ok


class FluencyAgent:
    """
    Multi-dimensional Korean translation quality evaluator.

    Uses G-Eval style chain-of-thought with few-shot examples anchored
    at score 1, 5, and 10 to prevent score drift.
    """

    _FEW_SHOT = """\
Scoring examples (use these as anchors):

[Score 10] 완벽: "범주론은 수학적 구조들 사이의 관계를 연구하는 분야입니다. 함자는 두 범주 사이의 구조 보존 사상입니다."
[Score 5]  보통: "범주론은 수학 구조의 관계를 연구 합니다. 함수는 두 카테고리 사이 사상입니다."  (spacing error, loan word)
[Score 1]  불가: "Category theory is the study of..." (not translated) or "范畴论是..." (Chinese)
"""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
    ):
        self._client = OllamaClient(model=model, base_url=base_url)

    def score(self, original_en: str, translated_ko: str, glossary: dict) -> FluencyScore:
        """Evaluate translation quality. Returns FluencyScore."""
        # Fast language check before calling LLM
        if not self._is_korean(translated_ko):
            return FluencyScore(
                accuracy=1, fluency=1, tone=1, terminology=1,
                critique="번역 결과가 한국어가 아닙니다.",
                language_ok=False,
            )

        glossary_str = (
            "\n".join(f"  {k} → {v}" for k, v in list(glossary.items())[:8])
            if glossary else "  (없음)"
        )

        prompt = f"""{self._FEW_SHOT}

[원문 영어]
{original_en[:600]}

[번역 한국어]
{translated_ko[:600]}

[필수 용어집]
{glossary_str}

위 번역을 4개 기준으로 평가하세요. 각 기준에서 1-10점을 부여하기 전에 반드시 이유를 먼저 쓰세요.

1. accuracy (정확성): 원문 의미가 완전히 전달됐는가?
2. fluency (유창성): 자연스러운 한국어인가? 어색한 직역 표현이 없는가?
3. tone (문체): 학술/기술 문서에 적합한 격식체인가?
4. terminology (용어): 용어집의 용어를 올바르게 사용했는가?

반드시 다음 JSON 형식으로만 출력하세요:
{{"reasoning": "간단한 근거", "accuracy": <1-10>, "fluency": <1-10>, "tone": <1-10>, "terminology": <1-10>, "critique": "개선 필요사항 (없으면 PASS)"}}"""

        raw = self._client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            timeout=120,
            json_format=True,
        )

        return self._parse(raw)

    def _parse(self, raw: str) -> FluencyScore:
        try:
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(cleaned)
            return FluencyScore(
                accuracy=max(1, min(10, int(data.get("accuracy", 5)))),
                fluency=max(1, min(10, int(data.get("fluency", 5)))),
                tone=max(1, min(10, int(data.get("tone", 5)))),
                terminology=max(1, min(10, int(data.get("terminology", 5)))),
                critique=str(data.get("critique", "")),
                language_ok=True,
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return FluencyScore(
                accuracy=5, fluency=5, tone=5, terminology=5,
                critique="평가 파싱 실패",
            )

    @staticmethod
    def _is_korean(text: str) -> bool:
        """Return True if text has substantial Korean content."""
        if not text or len(text.split()) < 3:
            return True  # too short to judge
        korean = sum(1 for c in text if "\uAC00" <= c <= "\uD7A3")
        chinese = sum(1 for c in text if "\u4E00" <= c <= "\u9FFF")
        alpha = sum(1 for c in text if c.isalpha()) or 1
        # Reject if Chinese dominates or Korean is absent in long texts
        if chinese / alpha > 0.15:
            return False
        if len(text.split()) > 15 and korean / alpha < 0.08:
            return False
        return True
