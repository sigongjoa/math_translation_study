"""
Tests for #14 PaperSynthesizer.

All LLM and Wikipedia HTTP calls are mocked — runs without Ollama or network.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pcm.core.paper_synthesizer import (
    ConceptMap,
    ConceptMapAgent,
    HistoryAgent,
    IntuitionAgent,
    PaperSynthesizer,
    VisualizationAgent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GROUP_SECTION = {
    "section_id": "1.1",
    "title": "군(Group)",
    "text": (
        "Definition 1.1 (Group). A group is a set $G$ together with a binary "
        "operation satisfying associativity, identity, and inverses."
    ),
    "final_ko": (
        "정의 1.1 (군). 군은 결합법칙, 항등원, 역원을 만족하는 이항 연산이 "
        "주어진 집합 $G$이다."
    ),
    "domain": "algebra",
    "block_type": "definition",
}

CATEGORY_SECTION = {
    "section_id": "3.1",
    "title": "함자(Functor)",
    "text": "A functor F: C -> D is a mapping between categories.",
    "final_ko": "함자 F: C → D는 범주 사이의 사상이다.",
    "domain": "category_theory",
    "block_type": "definition",
}

MINIMAL_SECTION = {
    "section_id": "0.1",
    "text": "A set is a collection of objects.",
}


def _mock_ollama_response(text: str):
    """Return a mock requests.Response for Ollama."""
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"response": text}
    return m


def _mock_wiki_response(text: str):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"extract": text}
    return m


# ---------------------------------------------------------------------------
# HistoryAgent tests
# ---------------------------------------------------------------------------

class TestHistoryAgent(unittest.TestCase):

    def setUp(self):
        self.agent = HistoryAgent(use_wikipedia=False)

    @patch("requests.post")
    def test_returns_nonempty_string(self, mock_post):
        mock_post.return_value = _mock_ollama_response("군론은 19세기 갈루아가...")
        result = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)

    @patch("requests.post")
    def test_fallback_on_llm_failure(self, mock_post):
        mock_post.side_effect = Exception("LLM down")
        result = self.agent.generate(GROUP_SECTION)
        self.assertIn("군(Group)", result)

    @patch("requests.get")
    @patch("requests.post")
    def test_wikipedia_integration(self, mock_post, mock_get):
        mock_get.return_value = _mock_wiki_response("In mathematics, a group is...")
        mock_post.return_value = _mock_ollama_response("군의 역사는...")
        agent = HistoryAgent(use_wikipedia=True)
        result = agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, str)
        self.assertTrue(mock_get.called)

    @patch("requests.get")
    @patch("requests.post")
    def test_wikipedia_failure_graceful(self, mock_post, mock_get):
        mock_get.side_effect = Exception("Network error")
        mock_post.return_value = _mock_ollama_response("군의 역사는...")
        agent = HistoryAgent(use_wikipedia=True)
        result = agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, str)

    def test_key_term_extraction(self):
        agent = HistoryAgent(use_wikipedia=False)
        term = agent._extract_key_term("Definition 1.1 (Group). A group is...")
        self.assertEqual(term, "Group")

    def test_key_term_fallback(self):
        agent = HistoryAgent(use_wikipedia=False)
        term = agent._extract_key_term("plain text without capitalisation.")
        self.assertIsInstance(term, str)


# ---------------------------------------------------------------------------
# IntuitionAgent tests
# ---------------------------------------------------------------------------

class TestIntuitionAgent(unittest.TestCase):

    def setUp(self):
        self.agent = IntuitionAgent()

    @patch("requests.post")
    def test_returns_nonempty_string(self, mock_post):
        mock_post.return_value = _mock_ollama_response(
            "첫째: 군은 닫혀 있는 집합입니다.\n둘째: 항등원이 있습니다."
        )
        result = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)

    @patch("requests.post")
    def test_fallback_on_llm_failure(self, mock_post):
        mock_post.side_effect = Exception("LLM down")
        result = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 5)

    @patch("requests.post")
    def test_uses_domain_in_prompt(self, mock_post):
        mock_post.return_value = _mock_ollama_response("범주론 관점에서...")
        self.agent.generate(CATEGORY_SECTION)
        call_args = mock_post.call_args
        prompt = call_args[1]["json"]["prompt"]
        self.assertIn("category_theory", prompt)


# ---------------------------------------------------------------------------
# VisualizationAgent tests
# ---------------------------------------------------------------------------

class TestVisualizationAgent(unittest.TestCase):

    def setUp(self):
        self.agent = VisualizationAgent()

    def test_strategy_selection_algebra(self):
        strategy = self.agent._get_strategy("algebra")
        self.assertEqual(strategy, "graphviz")

    def test_strategy_selection_category_theory(self):
        strategy = self.agent._get_strategy("category_theory")
        self.assertEqual(strategy, "tikzcd")

    def test_strategy_selection_default(self):
        strategy = self.agent._get_strategy("unknown_domain")
        self.assertEqual(strategy, "default")

    @patch("requests.post")
    def test_returns_code_and_strategy(self, mock_post):
        mock_post.return_value = _mock_ollama_response(
            "digraph G { A -> B }"
        )
        code, strategy = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(code, str)
        self.assertIsInstance(strategy, str)
        self.assertGreater(len(code), 5)

    @patch("requests.post")
    def test_fallback_on_empty_llm_response(self, mock_post):
        mock_post.return_value = _mock_ollama_response("")
        code, strategy = self.agent.generate(GROUP_SECTION)
        self.assertGreater(len(code), 10)
        self.assertIn("군(Group)", code)

    @patch("requests.post")
    def test_fallback_on_llm_failure(self, mock_post):
        mock_post.side_effect = Exception("LLM down")
        code, strategy = self.agent.generate(CATEGORY_SECTION)
        self.assertIn("tikzcd", code)

    @patch("requests.post")
    def test_tikzcd_strategy_for_category(self, mock_post):
        mock_post.return_value = _mock_ollama_response("\\begin{tikzcd} A \\end{tikzcd}")
        code, strategy = self.agent.generate(CATEGORY_SECTION)
        self.assertEqual(strategy, "tikzcd")


# ---------------------------------------------------------------------------
# ConceptMapAgent tests
# ---------------------------------------------------------------------------

class TestConceptMapAgent(unittest.TestCase):

    def setUp(self):
        self.agent = ConceptMapAgent()

    @patch("requests.post")
    def test_valid_json_parsed(self, mock_post):
        payload = json.dumps({
            "prerequisites": ["집합론", "이항 연산"],
            "applications": ["암호학", "물리학"],
            "generalizations": ["모노이드", "반군"],
            "special_cases": ["순환군", "대칭군"],
        })
        mock_post.return_value = _mock_ollama_response(payload)
        result = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, ConceptMap)
        self.assertIn("집합론", result.prerequisites)
        self.assertIn("암호학", result.applications)

    @patch("requests.post")
    def test_fallback_on_invalid_json(self, mock_post):
        mock_post.return_value = _mock_ollama_response("not json at all")
        result = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, ConceptMap)
        self.assertGreater(len(result.prerequisites), 0)

    @patch("requests.post")
    def test_fallback_on_llm_failure(self, mock_post):
        mock_post.side_effect = Exception("LLM down")
        result = self.agent.generate(GROUP_SECTION)
        self.assertIsInstance(result, ConceptMap)
        self.assertGreater(len(result.prerequisites), 0)

    @patch("requests.post")
    def test_lists_capped_at_4(self, mock_post):
        payload = json.dumps({
            "prerequisites": ["a", "b", "c", "d", "e", "f"],
            "applications": ["x", "y"],
            "generalizations": ["g"],
            "special_cases": ["s1", "s2"],
        })
        mock_post.return_value = _mock_ollama_response(payload)
        result = self.agent.generate(GROUP_SECTION)
        self.assertLessEqual(len(result.prerequisites), 4)

    @patch("requests.post")
    def test_minimum_two_prerequisites(self, mock_post):
        result = self.agent._fallback("군(Group)")
        self.assertGreaterEqual(len(result.prerequisites), 2)
        self.assertGreaterEqual(len(result.applications), 2)


# ---------------------------------------------------------------------------
# PaperSynthesizer integration tests
# ---------------------------------------------------------------------------

class TestPaperSynthesizer(unittest.TestCase):

    def _make_synth(self):
        return PaperSynthesizer(use_wikipedia=False)

    @patch("requests.post")
    def test_synthesize_returns_result(self, mock_post):
        mock_post.return_value = _mock_ollama_response("테스트 응답")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertEqual(result.section_id, "1.1")
        self.assertEqual(result.title, "군(Group)")

    @patch("requests.post")
    def test_typst_source_nonempty(self, mock_post):
        mock_post.return_value = _mock_ollama_response("응답 텍스트")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertGreater(len(result.typst_source), 100)

    @patch("requests.post")
    def test_typst_contains_section_id(self, mock_post):
        mock_post.return_value = _mock_ollama_response("내용")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertIn("1.1", result.typst_source)

    @patch("requests.post")
    def test_typst_contains_title(self, mock_post):
        mock_post.return_value = _mock_ollama_response("내용")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertIn("군(Group)", result.typst_source)

    @patch("requests.post")
    def test_typst_has_required_sections(self, mock_post):
        mock_post.return_value = _mock_ollama_response("내용")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        for heading in ["역사적 배경", "직관적 이해", "개념 시각화", "연관 개념 지도"]:
            self.assertIn(heading, result.typst_source,
                          f"Missing heading: {heading}")

    @patch("requests.post")
    def test_typst_has_abstract(self, mock_post):
        mock_post.return_value = _mock_ollama_response("초록 내용")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertIn("초록", result.typst_source)

    @patch("requests.post")
    def test_concept_map_nonempty(self, mock_post):
        concept_json = json.dumps({
            "prerequisites": ["집합론"],
            "applications": ["암호학"],
            "generalizations": ["모노이드"],
            "special_cases": ["순환군"],
        })
        mock_post.return_value = _mock_ollama_response(concept_json)
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertGreater(len(result.concept_map.prerequisites), 0)

    @patch("requests.post")
    def test_visualization_strategy_set(self, mock_post):
        mock_post.return_value = _mock_ollama_response("digraph G {}")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        self.assertEqual(result.visualization_strategy, "graphviz")

    @patch("requests.post")
    def test_minimal_section_works(self, mock_post):
        mock_post.return_value = _mock_ollama_response("응답")
        synth = self._make_synth()
        result = synth.synthesize(MINIMAL_SECTION)
        self.assertIsInstance(result.typst_source, str)
        self.assertGreater(len(result.typst_source), 50)

    @patch("requests.post")
    def test_title_inferred_from_text(self, mock_post):
        mock_post.return_value = _mock_ollama_response("응답")
        synth = self._make_synth()
        section = {
            "section_id": "2.1",
            "text": "Definition 2.1 (Ring). A ring is an abelian group with multiplication.",
            "final_ko": "정의 2.1 (환). 환은 곱셈이 추가된 아벨 군이다.",
            "domain": "algebra",
        }
        result = synth.synthesize(section)
        # _infer_title checks final_ko first → extracts Korean term "환" or fallback
        self.assertTrue(
            "Ring" in result.title or "환" in result.title,
            f"Expected 'Ring' or '환' in title, got: {result.title}",
        )

    @patch("requests.post")
    def test_save_writes_file(self, mock_post, tmp_path=None):
        mock_post.return_value = _mock_ollama_response("내용")
        synth = self._make_synth()
        result = synth.synthesize(GROUP_SECTION)
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "test_output.typ")
            saved = synth.save(result, path)
            self.assertTrue(saved.exists())
            content = saved.read_text(encoding="utf-8")
            self.assertIn("군(Group)", content)

    @patch("requests.post")
    def test_category_theory_uses_tikzcd(self, mock_post):
        mock_post.return_value = _mock_ollama_response(
            "\\begin{tikzcd} A \\end{tikzcd}"
        )
        synth = self._make_synth()
        result = synth.synthesize(CATEGORY_SECTION)
        self.assertEqual(result.visualization_strategy, "tikzcd")

    @patch("requests.post")
    def test_all_llm_calls_made(self, mock_post):
        """Synthesize should call LLM at least 4 times (one per sub-agent + abstract)."""
        mock_post.return_value = _mock_ollama_response("응답")
        synth = self._make_synth()
        synth.synthesize(GROUP_SECTION)
        self.assertGreaterEqual(mock_post.call_count, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
