"""
NaturalnessEditor — detects and rewrites unnatural Korean translation patterns.

Common issues in qwen2.5:7b Korean output:
  1. 직역체 (literal translation): "~하는 것을 하기 위해서" instead of "~하려고"
  2. 과도한 명사화: "~의 수행을 통해" instead of "~을 수행함으로써"
  3. 영어 어순 유지: "이것은 우리가 보여주는 것이다 ~을"
  4. 어색한 존댓말 혼용: 합쇼체/해요체 혼재
  5. 불필요한 직역 괄호: "에이전트(agent)"가 이미 익숙한 단어인데 병기
  6. 조사 오류: "을를", "이가" 혼동
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.pcm.core.llm_client import OllamaClient, _DEFAULT_MODEL, _DEFAULT_BASE_URL


@dataclass
class EditResult:
    original: str
    edited: str
    changed: bool
    issues_found: list[str]


class NaturalnessEditor:
    """
    Two-phase Korean naturalness improvement:
    1. Rule-based quick fixes (no LLM call)
    2. LLM-based rewrite for complex unnatural patterns
    """

    # Rule-based fixes: (pattern, replacement, description)
    _RULES: list[tuple[str, str, str]] = [
        # Remove redundant English glosses for common terms
        (r"에이전트\(agent\)", "에이전트", "중복 괄호 제거"),
        (r"모델\(model\)", "모델", "중복 괄호 제거"),
        (r"데이터\(data\)", "데이터", "중복 괄호 제거"),
        # Fix doubled particles
        (r"을를\b", "을", "조사 중복"),
        (r"이가\b", "이", "조사 중복"),
        (r"은는\b", "은", "조사 중복"),
        # Fix overly verbose patterns
        (r"하는 것을 통해서", "을 통해", "간결화"),
        (r"하는 것을 위해서", "하기 위해", "간결화"),
        (r"을 수행하는 것이 가능하다", "을 수행할 수 있다", "간결화"),
        (r"이루어지는 것이다", "이루어진다", "간결화"),
        # Fix spacing around math (preserve $ delimiters)
        (r"\$\s+", "$", "수식 공백"),
        (r"\s+\$", "$", "수식 공백"),
    ]

    # Patterns that indicate unnatural translation needing LLM rewrite
    _UNNATURAL_SIGNALS = [
        r"하는 것을 하기 위하여",
        r"에 의해서 수행되어지",
        r"으로 인하여 발생되어",
        r"이/가\s",
        r"을/를\s",
        r"Certainly[,.]",
        r"Here is (an? |the )?improved",
        r"As requested",
        r"Based on.*standards",
    ]

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        use_llm: bool = True,
    ):
        self._client = OllamaClient(model=model, base_url=base_url) if use_llm else None
        self._unnatural_re = re.compile(
            "|".join(self._UNNATURAL_SIGNALS), re.IGNORECASE
        )

    def edit(self, korean_text: str, original_en: str = "") -> EditResult:
        """Apply rule-based fixes, then LLM rewrite if unnatural patterns detected."""
        issues: list[str] = []

        # Phase 1: rule-based
        text = korean_text
        for pattern, replacement, desc in self._RULES:
            new_text = re.sub(pattern, replacement, text)
            if new_text != text:
                issues.append(desc)
                text = new_text

        # Phase 2: LLM rewrite if unnatural signals detected
        if self._client and self._unnatural_re.search(text):
            issues.append("LLM 자연스러움 교정")
            text = self._llm_rewrite(text, original_en) or text

        return EditResult(
            original=korean_text,
            edited=text,
            changed=text != korean_text,
            issues_found=issues,
        )

    def _llm_rewrite(self, text: str, original_en: str) -> str:
        prompt = f"""다음 한국어 번역에서 어색한 표현을 자연스럽게 고쳐주세요.

규칙:
1. 의미는 절대 바꾸지 마세요.
2. 직역체를 자연스러운 한국어로 바꿔주세요.
3. 수식($...$)은 그대로 유지하세요.
4. 격식체(합쇼체)를 일관되게 유지하세요.
5. 번역 결과만 출력하세요. 설명이나 머리말 없이.
6. 반드시 한국어로만 출력하세요.

원문 영어 (참고용):
{original_en[:300]}

교정할 한국어:
{text[:800]}

교정 결과:"""

        result = self._client.chat_or_fallback(
            messages=[{"role": "user", "content": prompt}],
            fallback=text,
            temperature=0.1,
            timeout=90,
        )

        # Reject if result is not Korean
        korean = sum(1 for c in result if "\uAC00" <= c <= "\uD7A3")
        alpha = sum(1 for c in result if c.isalpha()) or 1
        if korean / alpha < 0.15:
            return text  # keep original if LLM returned non-Korean
        return result
