"""
Tests for the three new quality-checking agents:
  - FluencyAgent (G-Eval multi-dimensional scorer)
  - NaturalnessEditor (rule-based + LLM Korean naturalness)
  - BackTranslationVerifier (semantic drift detection)

All LLM calls are mocked — runs without Ollama.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# FluencyAgent
# ---------------------------------------------------------------------------

class TestFluencyAgentScore(unittest.TestCase):
    """FluencyAgent: parsing, scoring, language check."""

    def _make_agent(self, raw_response: str):
        from src.pcm.core.fluency_agent import FluencyAgent
        agent = FluencyAgent.__new__(FluencyAgent)
        mock_client = MagicMock()
        mock_client.chat.return_value = raw_response
        agent._client = mock_client
        return agent

    def test_parse_valid_json(self):
        from src.pcm.core.fluency_agent import FluencyAgent
        raw = '{"reasoning":"ok","accuracy":8,"fluency":7,"tone":9,"terminology":8,"critique":"PASS"}'
        agent = self._make_agent(raw)
        score = agent.score("Hello world text", "안녕하세요 세계", {})
        self.assertEqual(score.accuracy, 8)
        self.assertEqual(score.fluency, 7)
        self.assertEqual(score.tone, 9)
        self.assertEqual(score.terminology, 8)
        # total = 8*3 + 7*3 + 9*2 + 8*2 = 24+21+18+16 = 79
        self.assertAlmostEqual(score.total, 79.0, places=0)
        self.assertTrue(score.passed)  # total >= 70

    def test_total_weight_calculation(self):
        from src.pcm.core.fluency_agent import FluencyScore
        s = FluencyScore(accuracy=10, fluency=10, tone=10, terminology=10)
        self.assertEqual(s.total, 100.0)

    def test_fail_below_70(self):
        from src.pcm.core.fluency_agent import FluencyScore
        s = FluencyScore(accuracy=4, fluency=4, tone=4, terminology=4, language_ok=True)
        # total = 4*3+4*3+4*2+4*2 = 12+12+8+8 = 40
        self.assertFalse(s.passed)

    def test_language_check_rejects_english(self):
        from src.pcm.core.fluency_agent import FluencyAgent
        agent = self._make_agent("{}")
        # Long English text with no Korean → should be rejected before LLM call
        en_text = "This is a very long English text with many words that should be detected as non-Korean output from the translation stage and therefore rejected immediately without calling the LLM."
        score = agent.score("original", en_text, {})
        self.assertFalse(score.language_ok)
        self.assertEqual(score.accuracy, 1)

    def test_language_check_passes_korean(self):
        from src.pcm.core.fluency_agent import FluencyAgent
        raw = '{"accuracy":7,"fluency":7,"tone":7,"terminology":7,"critique":"PASS"}'
        agent = self._make_agent(raw)
        ko = "범주론은 수학적 구조들 사이의 관계를 연구하는 분야입니다. 함자는 두 범주 사이의 구조 보존 사상입니다."
        score = agent.score("Category theory studies relationships", ko, {})
        self.assertTrue(score.language_ok)

    def test_parse_fallback_on_bad_json(self):
        from src.pcm.core.fluency_agent import FluencyAgent
        agent = self._make_agent("not valid json at all")
        ko = "이것은 한국어 번역입니다. " * 5
        score = agent.score("original", ko, {})
        # fallback returns 5,5,5,5
        self.assertEqual(score.accuracy, 5)
        self.assertEqual(score.critique, "평가 파싱 실패")

    def test_parse_json_in_markdown_fence(self):
        from src.pcm.core.fluency_agent import FluencyAgent
        raw = '```json\n{"accuracy":9,"fluency":8,"tone":8,"terminology":9,"critique":"PASS"}\n```'
        agent = self._make_agent(raw)
        ko = "범주론은 수학적 구조들 사이의 관계를 연구하는 분야입니다. " * 3
        score = agent.score("original", ko, {})
        self.assertEqual(score.accuracy, 9)

    def test_clamp_scores_to_1_10(self):
        from src.pcm.core.fluency_agent import FluencyAgent
        raw = '{"accuracy":15,"fluency":0,"tone":5,"terminology":5,"critique":""}'
        agent = self._make_agent(raw)
        ko = "이것은 테스트입니다. " * 5
        score = agent.score("original", ko, {})
        self.assertEqual(score.accuracy, 10)   # clamped from 15
        self.assertEqual(score.fluency, 1)     # clamped from 0


# ---------------------------------------------------------------------------
# NaturalnessEditor
# ---------------------------------------------------------------------------

class TestNaturalnessEditorRules(unittest.TestCase):
    """NaturalnessEditor: rule-based fixes."""

    def _make_editor(self, llm_response: str = None):
        from src.pcm.core.naturalness_editor import NaturalnessEditor
        if llm_response is None:
            editor = NaturalnessEditor(use_llm=False)
        else:
            editor = NaturalnessEditor.__new__(NaturalnessEditor)
            import re
            editor._unnatural_re = re.compile(
                "|".join(NaturalnessEditor._UNNATURAL_SIGNALS), re.IGNORECASE
            )
            mock_client = MagicMock()
            mock_client.chat_or_fallback.return_value = llm_response
            editor._client = mock_client
        return editor

    def test_remove_duplicate_agent_gloss(self):
        editor = self._make_editor()
        result = editor.edit("에이전트(agent)가 실행됩니다.")
        self.assertEqual(result.edited, "에이전트가 실행됩니다.")
        self.assertIn("중복 괄호 제거", result.issues_found)
        self.assertTrue(result.changed)

    def test_remove_duplicate_model_gloss(self):
        editor = self._make_editor()
        result = editor.edit("모델(model)을 사용합니다.")
        self.assertEqual(result.edited, "모델을 사용합니다.")

    def test_fix_doubled_particle_eulleul(self):
        editor = self._make_editor()
        # The rule pattern is "을를\b" — test the exact pattern it handles
        result = editor.edit("결과을를 확인합니다.")
        self.assertNotIn("을를", result.edited)
        self.assertIn("조사 중복", result.issues_found)

    def test_fix_verbose_pattern(self):
        editor = self._make_editor()
        result = editor.edit("이것은 수행하는 것을 통해서 가능합니다.")
        self.assertNotIn("하는 것을 통해서", result.edited)

    def test_fix_math_spacing(self):
        editor = self._make_editor()
        # Rule removes all whitespace immediately adjacent to $
        result = editor.edit("수식 $ x+y $ 봐요.")
        self.assertNotIn("$ ", result.edited)
        self.assertNotIn(" $", result.edited)
        self.assertIn("수식 공백", result.issues_found)

    def test_no_change_clean_text(self):
        editor = self._make_editor()
        clean = "범주론은 수학적 구조를 연구합니다."
        result = editor.edit(clean)
        self.assertFalse(result.changed)
        self.assertEqual(result.issues_found, [])

    def test_detect_certainly_as_unnatural_signal(self):
        from src.pcm.core.naturalness_editor import NaturalnessEditor
        import re
        editor = self._make_editor()
        # Override _unnatural_re to check signal detection
        unnatural_re = re.compile(
            "|".join(NaturalnessEditor._UNNATURAL_SIGNALS), re.IGNORECASE
        )
        text = "Certainly, 이것은 번역입니다."
        self.assertIsNotNone(unnatural_re.search(text))


# ---------------------------------------------------------------------------
# BackTranslationVerifier
# ---------------------------------------------------------------------------

class TestBackTranslationVerifier(unittest.TestCase):
    """BackTranslationVerifier: token F1 and similarity checks."""

    def _make_verifier(self, back_translation_response: str):
        from src.pcm.core.back_translation_verifier import BackTranslationVerifier
        verifier = BackTranslationVerifier.__new__(BackTranslationVerifier)
        verifier.threshold = 0.55
        verifier._embedder = None  # use token F1, no sentence-transformers
        mock_client = MagicMock()
        mock_client.generate_or_fallback.return_value = back_translation_response
        verifier._client = mock_client
        return verifier

    def test_high_similarity_passes(self):
        # Back-translation closely matches original → should pass
        original = "The transformer model uses attention mechanisms to process text sequences."
        back = "The transformer model uses attention mechanisms to process text sequences."
        verifier = self._make_verifier(back)
        result = verifier.verify(original, "트랜스포머 모델은 어텐션 메커니즘을 사용합니다.")
        self.assertTrue(result.passed)
        self.assertGreater(result.similarity, 0.55)

    def test_low_similarity_fails(self):
        original = "The transformer model uses attention mechanisms to process sequences."
        back = "The cat sat on the mat outside the house yesterday morning."
        verifier = self._make_verifier(back)
        result = verifier.verify(original, "트랜스포머 모델입니다.")
        self.assertFalse(result.passed)
        self.assertLess(result.similarity, 0.55)

    def test_empty_korean_skipped(self):
        verifier = self._make_verifier("")
        result = verifier.verify("original text", "")
        self.assertFalse(result.passed)
        self.assertEqual(result.similarity, 0.0)
        self.assertEqual(result.method, "skip")

    def test_empty_back_translation_gives_benefit_of_doubt(self):
        verifier = self._make_verifier("")
        result = verifier.verify("original text", "한국어 번역입니다.")
        # Empty back-translation → benefit of doubt → similarity=0.5, passed=True
        self.assertTrue(result.passed)
        self.assertEqual(result.similarity, 0.5)

    def test_token_f1_method_label(self):
        original = "Category theory studies mathematical structures."
        back = "Category theory studies mathematical structures."
        verifier = self._make_verifier(back)
        result = verifier.verify(original, "범주론은 수학적 구조를 연구합니다.")
        self.assertEqual(result.method, "token_overlap")

    def test_drift_terms_detected(self):
        from src.pcm.core.back_translation_verifier import BackTranslationVerifier
        original = "The Transformer architecture uses Multi-Head Attention."
        back_translation = "The system uses some neural components."
        drift = BackTranslationVerifier._find_drift_terms(original, back_translation)
        # "Transformer" and "Multi" and "Head" and "Attention" should be detected
        self.assertIn("Transformer", drift)
        self.assertIn("Attention", drift)

    def test_similarity_clamped_to_0_1(self):
        from src.pcm.core.back_translation_verifier import BackTranslationVerifier
        # Token F1 should never exceed 1.0 or go below 0.0
        f1, method = BackTranslationVerifier._token_f1(
            "the quick brown fox", "the quick brown fox"
        )
        self.assertLessEqual(f1, 1.0)
        self.assertGreaterEqual(f1, 0.0)

    def test_back_translation_truncated_to_300(self):
        long_back = "word " * 200  # 1000 chars
        verifier = self._make_verifier(long_back)
        result = verifier.verify("some original text", "한국어 번역입니다.")
        # back_translation stored in result should be <= 300 chars
        self.assertLessEqual(len(result.back_translation), 300)


if __name__ == "__main__":
    unittest.main()
