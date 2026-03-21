"""
Tests for #20 — LLM abstraction layer (OllamaClient) + Stage2 parallel processing.

All network calls are mocked — runs without Ollama.
"""

import json
import os
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, call, patch

from src.pcm.core.llm_client import LLMClient, OllamaClient, _DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama_generate_response(text: str):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"response": text}
    return m


def _ollama_chat_response(text: str):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"message": {"content": text}}
    return m


# ---------------------------------------------------------------------------
# LLMClient interface tests
# ---------------------------------------------------------------------------

class TestLLMClientInterface(unittest.TestCase):

    def test_abstract_generate_raises(self):
        client = LLMClient()
        with self.assertRaises(NotImplementedError):
            client.generate("hello")

    def test_abstract_chat_raises(self):
        client = LLMClient()
        with self.assertRaises(NotImplementedError):
            client.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# OllamaClient unit tests
# ---------------------------------------------------------------------------

class TestOllamaClientGenerate(unittest.TestCase):

    def setUp(self):
        self.client = OllamaClient(model="test-model", base_url="http://localhost:11434")

    @patch("requests.post")
    def test_generate_returns_text(self, mock_post):
        mock_post.return_value = _ollama_generate_response("번역 결과")
        result = self.client.generate("Translate this")
        self.assertEqual(result, "번역 결과")

    @patch("requests.post")
    def test_generate_strips_whitespace(self, mock_post):
        mock_post.return_value = _ollama_generate_response("  결과  \n")
        result = self.client.generate("prompt")
        self.assertEqual(result, "결과")

    @patch("requests.post")
    def test_generate_returns_empty_on_network_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.RequestException("connection refused")
        result = self.client.generate("prompt")
        self.assertEqual(result, "")

    @patch("requests.post")
    def test_generate_returns_empty_on_key_error(self, mock_post):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {}   # missing "response" key
        mock_post.return_value = m
        result = self.client.generate("prompt")
        self.assertEqual(result, "")

    @patch("requests.post")
    def test_generate_passes_temperature(self, mock_post):
        mock_post.return_value = _ollama_generate_response("ok")
        self.client.generate("prompt", temperature=0.9)
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["options"]["temperature"], 0.9)

    @patch("requests.post")
    def test_generate_passes_num_predict(self, mock_post):
        mock_post.return_value = _ollama_generate_response("ok")
        self.client.generate("prompt", num_predict=500)
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["options"]["num_predict"], 500)

    @patch("requests.post")
    def test_generate_calls_generate_endpoint(self, mock_post):
        mock_post.return_value = _ollama_generate_response("ok")
        self.client.generate("prompt")
        url = mock_post.call_args[0][0]
        self.assertIn("/api/generate", url)


class TestOllamaClientChat(unittest.TestCase):

    def setUp(self):
        self.client = OllamaClient(model="test-model", base_url="http://localhost:11434")

    @patch("requests.post")
    def test_chat_returns_text(self, mock_post):
        mock_post.return_value = _ollama_chat_response("비평 결과")
        messages = [{"role": "user", "content": "critique this"}]
        result = self.client.chat(messages)
        self.assertEqual(result, "비평 결과")

    @patch("requests.post")
    def test_chat_returns_empty_on_failure(self, mock_post):
        import requests as req
        mock_post.side_effect = req.RequestException("timeout")
        result = self.client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(result, "")

    @patch("requests.post")
    def test_chat_json_format_flag(self, mock_post):
        mock_post.return_value = _ollama_chat_response("{}")
        self.client.chat([], json_format=True)
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload.get("format"), "json")

    @patch("requests.post")
    def test_chat_no_json_format_by_default(self, mock_post):
        mock_post.return_value = _ollama_chat_response("ok")
        self.client.chat([])
        payload = mock_post.call_args[1]["json"]
        self.assertNotIn("format", payload)

    @patch("requests.post")
    def test_chat_calls_chat_endpoint(self, mock_post):
        mock_post.return_value = _ollama_chat_response("ok")
        self.client.chat([])
        url = mock_post.call_args[0][0]
        self.assertIn("/api/chat", url)


class TestOllamaClientFallbacks(unittest.TestCase):

    def setUp(self):
        self.client = OllamaClient()

    @patch("requests.post")
    def test_generate_or_fallback_returns_result_when_ok(self, mock_post):
        mock_post.return_value = _ollama_generate_response("결과")
        r = self.client.generate_or_fallback("prompt", "FB")
        self.assertEqual(r, "결과")

    @patch("requests.post")
    def test_generate_or_fallback_uses_fallback_on_empty(self, mock_post):
        mock_post.return_value = _ollama_generate_response("")
        r = self.client.generate_or_fallback("prompt", "FALLBACK")
        self.assertEqual(r, "FALLBACK")

    @patch("requests.post")
    def test_chat_or_fallback_uses_fallback_on_failure(self, mock_post):
        import requests as req
        mock_post.side_effect = req.RequestException("down")
        r = self.client.chat_or_fallback([], "DEFAULT")
        self.assertEqual(r, "DEFAULT")


class TestOllamaClientEnvOverride(unittest.TestCase):

    def test_env_base_url_applied(self):
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://custom:9999"}):
            from importlib import reload
            import src.pcm.core.llm_client as mod
            reload(mod)
            client = mod.OllamaClient()
            self.assertIn("custom:9999", client._generate_url)
            reload(mod)  # restore

    def test_env_model_applied(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llama3:8b"}):
            from importlib import reload
            import src.pcm.core.llm_client as mod
            reload(mod)
            client = mod.OllamaClient()
            self.assertEqual(client.model, "llama3:8b")
            reload(mod)


# ---------------------------------------------------------------------------
# Stage2 parallel processing tests (mocked)
# ---------------------------------------------------------------------------

class TestStage2Parallel(unittest.TestCase):

    SECTIONS = [
        {"section_id": f"s{i}", "text": f"Section {i} text.", "domain": "algebra",
         "terminology_guide": "", "db_section_id": f"job_s{i}"}
        for i in range(6)
    ]
    JOB = {"id": "test_job"}

    def _make_stage(self):
        from src.pcm.pipeline.stages import Stage2_Drafting
        return Stage2_Drafting()

    def _make_mocks(self):
        db = MagicMock()
        db.add_iteration = MagicMock()
        db.update_section = MagicMock()
        logger = MagicMock()
        logger.bind.return_value = logger
        return db, logger

    @patch("src.pcm.core.llm_client.requests.post")
    def test_all_sections_processed(self, mock_post):
        mock_post.return_value = _ollama_generate_response("번역됨")
        stage = self._make_stage()
        db, logger = self._make_mocks()
        stage_rec = {"id": "stage_1"}

        result = stage.run(self.JOB, stage_rec, self.SECTIONS, db, logger)
        self.assertEqual(len(result["sections"]), 6)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_output_order_preserved(self, mock_post):
        """Sections must come back in the same order as input, despite parallel execution."""
        mock_post.return_value = _ollama_generate_response("번역됨")
        stage = self._make_stage()
        db, logger = self._make_mocks()
        stage_rec = {"id": "stage_1"}

        result = stage.run(self.JOB, stage_rec, self.SECTIONS, db, logger)
        ids_out = [s["section_id"] for s in result["sections"]]
        ids_in = [s["section_id"] for s in self.SECTIONS]
        self.assertEqual(ids_out, ids_in)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_failed_section_carries_forward(self, mock_post):
        """If LLM returns empty string, section still appears with original text."""
        mock_post.return_value = _ollama_generate_response("")   # empty → failure
        stage = self._make_stage()
        db, logger = self._make_mocks()
        stage_rec = {"id": "stage_1"}

        result = stage.run(self.JOB, stage_rec, self.SECTIONS[:1], db, logger)
        self.assertEqual(len(result["sections"]), 1)
        # Should fall back to original English
        self.assertEqual(result["sections"][0]["draft_ko"], "Section 0 text.")

    @patch("src.pcm.core.llm_client.requests.post")
    def test_parallel_calls_count(self, mock_post):
        """LLM must be called once per section."""
        mock_post.return_value = _ollama_generate_response("번역됨")
        stage = self._make_stage()
        db, logger = self._make_mocks()
        stage_rec = {"id": "stage_1"}

        stage.run(self.JOB, stage_rec, self.SECTIONS, db, logger)
        self.assertEqual(mock_post.call_count, len(self.SECTIONS))

    @patch("src.pcm.core.llm_client.requests.post")
    def test_thread_safety_no_data_races(self, mock_post):
        """Concurrent DB updates must not raise exceptions."""
        call_count = 0
        lock = threading.Lock()

        def side_effect(*args, **kwargs):
            nonlocal call_count
            with lock:
                call_count += 1
            return _ollama_generate_response(f"번역 {call_count}")

        mock_post.side_effect = side_effect
        stage = self._make_stage()
        db, logger = self._make_mocks()
        stage_rec = {"id": "stage_1"}

        # Should not raise
        result = stage.run(self.JOB, stage_rec, self.SECTIONS, db, logger)
        self.assertEqual(len(result["sections"]), 6)


# ---------------------------------------------------------------------------
# TCRLoop / CriticAgent now use OllamaClient
# ---------------------------------------------------------------------------

class TestTCRLoopUsesOllamaClient(unittest.TestCase):

    @patch("src.pcm.core.llm_client.requests.post")
    def test_tcr_run_returns_translation(self, mock_post):
        from src.pcm.core.tcr_loop import TCRLoop

        # First call: translation, second call: evaluation JSON
        mock_post.side_effect = [
            _ollama_chat_response("번역 결과"),
            _ollama_chat_response('{"score": 90, "critique": "좋음"}'),
        ]
        loop = TCRLoop()
        result, trace = loop.run("Hello", {}, "Translate to Korean")
        self.assertEqual(result, "번역 결과")
        self.assertEqual(trace["iterations"][0]["score"], 90)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_tcr_fallback_on_llm_failure(self, mock_post):
        from src.pcm.core.tcr_loop import TCRLoop
        import requests as req
        mock_post.side_effect = req.RequestException("down")
        loop = TCRLoop(max_iterations=1)
        result, _ = loop.run("Original text", {}, "prompt")
        self.assertEqual(result, "Original text")


class TestCriticAgentUsesOllamaClient(unittest.TestCase):

    @patch("src.pcm.core.llm_client.requests.post")
    def test_critique_returns_text(self, mock_post):
        from src.pcm.core.critic_agent import CriticAgent
        mock_post.return_value = _ollama_chat_response("용어가 잘못됨")
        agent = CriticAgent()
        result = agent.critique("text", "번역", {})
        self.assertEqual(result, "용어가 잘못됨")

    @patch("src.pcm.core.llm_client.requests.post")
    def test_refine_returns_fallback_on_failure(self, mock_post):
        from src.pcm.core.critic_agent import CriticAgent
        import requests as req
        mock_post.side_effect = req.RequestException("down")
        agent = CriticAgent()
        result = agent.refine("en", "ko_orig", "critique", {})
        self.assertEqual(result, "ko_orig")


if __name__ == "__main__":
    unittest.main(verbosity=2)
