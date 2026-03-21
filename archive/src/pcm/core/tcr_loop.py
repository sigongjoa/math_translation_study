import json
import re

from src.pcm.core.llm_client import OllamaClient, _DEFAULT_BASE_URL, _DEFAULT_MODEL


class TCRLoop:
    """
    Manages the Generation-Critique-Refinement loop with scoring and retries.
    (Issue #4)
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        threshold: int = 80,
        max_iterations: int = 3,
        ollama_url: str = _DEFAULT_BASE_URL,
    ):
        self.threshold = threshold
        self.max_iterations = max_iterations
        self._client = OllamaClient(model=model, base_url=ollama_url)

    def run(self, original_en: str, glossary: dict, initial_prompt: str):
        """Runs the loop until score >= threshold or max_iterations reached."""
        current_ko = ""
        iteration = 0
        trace = {"original": original_en, "iterations": []}

        while iteration < self.max_iterations:
            iteration += 1
            current_ko = self._get_translation(original_en, current_ko, glossary, initial_prompt)
            score, critique = self._evaluate(original_en, current_ko, glossary)

            trace["iterations"].append({
                "iteration": iteration,
                "translated": current_ko,
                "score": score,
                "critique": critique,
            })

            if score >= self.threshold:
                break

        return current_ko, trace

    _KOREAN_ONLY = (
        "\n[필수] 반드시 한국어(Korean)로만 번역하세요. "
        "절대 중국어(Chinese)나 영어(English)로 번역하지 마세요. "
        "번역 결과만 출력하세요."
    )

    def _get_translation(self, en: str, prev_ko: str, glossary: dict, prompt: str) -> str:
        system_prompt = prompt + self._KOREAN_ONLY
        messages = [{"role": "system", "content": system_prompt}]
        user_content = f"Original: {en}\n"
        if prev_ko:
            user_content += f"Previous Translation: {prev_ko}\nPlease improve the Korean translation based on academic standards."
        else:
            user_content += "Translate this text into Korean."
        messages.append({"role": "user", "content": user_content})

        result = self._client.chat(messages, temperature=0.2, timeout=120)
        if not result:
            return prev_ko if prev_ko else en
        # Strip trailing Chinese bleed-through
        import re as _re
        result = _re.sub(r"[\u4E00-\u9FFF\uF900-\uFAFF]+\s*$", "", result).rstrip()
        # Reject if Chinese chars dominate
        chinese = sum(1 for c in result if "\u4E00" <= c <= "\u9FFF")
        korean = sum(1 for c in result if "\uAC00" <= c <= "\uD7A3")
        alpha = sum(1 for c in result if c.isalpha())
        if alpha > 0 and chinese / alpha > 0.2:
            return prev_ko if prev_ko else en
        # Reject if clearly not Korean (< 10% Korean chars, non-trivial length)
        if alpha > 0 and korean / alpha < 0.10 and len(result.split()) > 5:
            return prev_ko if prev_ko else en
        return result

    def _evaluate(self, en: str, ko: str, glossary: dict) -> tuple[int, str]:
        """Evaluates translation quality and returns (score, critique).

        Scoring rules enforced in the prompt:
        - If ko contains mostly English (not translated) → score ≤ 30
        - If academic tone is wrong → deduct points
        - If glossary terms are mistranslated → deduct points
        """
        glossary_str = (
            "\n".join(f"  {k} → {v}" for k, v in list(glossary.items())[:10])
            if glossary else "  (none)"
        )
        eval_prompt = f"""You are a strict translation quality evaluator.

[ORIGINAL ENGLISH]
{en[:800]}

[TRANSLATED TEXT]
{ko[:800]}

[REQUIRED GLOSSARY]
{glossary_str}

SCORING RULES (score 0-100):
1. CRITICAL: If the translated text is still in English (not Korean), score MUST be 0-20.
2. If more than 30% of content words are English, score MUST be below 40.
3. Deduct 10 pts for each required glossary term that is missing or mistranslated.
4. Deduct 5 pts for wrong academic tone or spacing issues.
5. Perfect Korean translation with correct glossary = 90-100.

Output ONLY valid JSON with no extra text:
{{"score": <integer 0-100>, "critique": "<brief reason in Korean>"}}"""

        raw = self._client.chat(
            [{"role": "user", "content": eval_prompt}],
            temperature=0.0,
            timeout=120,
            json_format=True,
        )

        # Extract JSON even if the LLM wraps it in markdown
        try:
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            res = json.loads(cleaned)
            score = int(res.get("score", 50))
            score = max(0, min(100, score))
            return score, res.get("critique", "")
        except (json.JSONDecodeError, ValueError, TypeError):
            # Heuristic fallback: penalise untranslated English
            korean_chars = sum(1 for c in ko if "\uAC00" <= c <= "\uD7A3")
            total_alpha = sum(1 for c in ko if c.isalpha())
            if total_alpha > 0 and korean_chars / total_alpha < 0.3:
                return 20, "번역 미완료 (한국어 비율 낮음)"
            return 50, "평가 실패 (JSON 파싱 오류)"
