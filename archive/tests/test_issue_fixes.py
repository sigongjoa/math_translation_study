import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import logging
import requests
from pathlib import Path

# Import targets
from src.pcm.core.wolfram_verifier import WolframVerifier
from src.pcm.core.glossary_architect import GlossaryArchitect

class TestWolframVerifier(unittest.TestCase):
    def setUp(self):
        # Initialize with a dummy app_id
        self.verifier = WolframVerifier(app_id="test_id")

    def test_constants_are_20_or_more(self):
        """Check if at least 20 constants are stored in physical_constants.json upon creation."""
        # _ensure_constants() is called during __init__
        with open(self.verifier.constants_path, "r", encoding="utf-8") as f:
            constants = json.load(f)
        self.assertGreaterEqual(len(constants), 20)
        self.assertIn("c", constants)
        self.assertIn("hbar", constants)

    def test_verify_formula_valid(self):
        """Confirm verify_formula returns (True, []) for identical formulas."""
        is_valid, issues = self.verifier.verify_formula("$x^2$", "$x^2$")
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_verify_formula_brace_mismatch(self):
        """Confirm verify_formula detects unbalanced braces."""
        is_valid, issues = self.verifier.verify_formula("{a}", "{a")
        self.assertFalse(is_valid)
        self.assertTrue(any("Braces" in issue for issue in issues))

    def test_verify_formula_command_mismatch(self):
        """Confirm verify_formula detects missing LaTeX commands in translation."""
        en_formula = r"\frac{a}{b}"
        ko_formula = "a/b"
        is_valid, issues = self.verifier.verify_formula(en_formula, ko_formula)
        self.assertFalse(is_valid)
        self.assertTrue(any(r"'\frac'" in issue for issue in issues))

    def test_check_unit_non_si(self):
        """Confirm non-SI units like 'cm' are detected."""
        text = "The speed is 3 cm/s."
        is_valid, issues = self.verifier.check_unit_consistency(text)
        self.assertFalse(is_valid)
        self.assertTrue(any("Non-SI unit 'cm'" in issue for issue in issues))

    def test_warning_logged_without_app_id(self):
        """Confirm a warning is logged when app_id is missing."""
        with self.assertLogs(level='WARNING') as cm:
            WolframVerifier(app_id=None)
        self.assertTrue(any("app_id 없음" in output for output in cm.output))

class TestGlossaryArchitect(unittest.TestCase):
    @patch("src.pcm.core.glossary_architect.Path.mkdir")
    def setUp(self, mock_mkdir):
        # Use a dummy path that won't be used for real I/O due to mocks
        self.architect = GlossaryArchitect(pdf_path="dummy.pdf")

    @patch("src.pcm.core.glossary_architect.fitz.open")
    @patch("src.pcm.core.glossary_architect.requests.post")
    @patch("src.pcm.core.glossary_architect.KnowledgeAgent.get_definition")
    def test_critical_fixes_always_applied(self, mock_wiki, mock_post, mock_fitz):
        """Confirm critical_fixes are applied even if Ollama calls fail."""
        # Simulate Ollama failure
        mock_post.side_effect = Exception("Connection Failed")
        
        # Mock PDF
        mock_doc = MagicMock()
        mock_fitz.return_value = mock_doc
        
        # Mock file writing to verify final content
        m = mock_open()
        with patch("builtins.open", m):
            success = self.architect.build_chapter_glossary("test_book", "ch1", 1, 5)
        
        self.assertTrue(success)
        
        # Verify written glossary contains critical fixes
        handle = m()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        glossary = json.loads(written_data)
        
        self.assertEqual(glossary["Preorder"], "전순서(preorder)")
        self.assertEqual(glossary["Category"], "범주(category)")

    @patch("src.pcm.core.glossary_architect.fitz.open")
    @patch("src.pcm.core.glossary_architect.requests.post")
    def test_ollama_failure_graceful(self, mock_post, mock_fitz):
        """Confirm graceful recovery (returning True) when requests.post raises ConnectionError."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Ollama is down")
        
        # Mock PDF
        mock_doc = MagicMock()
        mock_fitz.return_value = mock_doc
        
        with patch("builtins.open", mock_open()):
            success = self.architect.build_chapter_glossary("test_book", "ch1", 1, 5)
        
        self.assertTrue(success)

    @patch("src.pcm.core.glossary_architect.fitz.open")
    @patch("src.pcm.core.glossary_architect.requests.post")
    @patch("src.pcm.core.glossary_architect.KnowledgeAgent.get_definition")
    def test_two_stage_llm_calls(self, mock_wiki, mock_post, mock_fitz):
        """Confirm at least two stages of LLM calls (extraction and translation)."""
        # Stage 1 Response (Term extraction JSON)
        resp1 = MagicMock()
        resp1.json.return_value = {
            "message": {"content": json.dumps({"Functor": "Category Theory"})}
        }
        resp1.status_code = 200
        
        # Stage 2 Response (Translation)
        resp2 = MagicMock()
        resp2.json.return_value = {"message": {"content": "함자(functor)"}}
        resp2.status_code = 200

        mock_post.side_effect = [resp1, resp2]
        
        # Mock Wikipedia
        mock_wiki.return_value = "Verified"
        
        # Mock PDF
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Functors are mappings between categories."
        mock_doc.__len__.return_value = 10
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz.return_value = mock_doc

        with patch("builtins.open", mock_open()):
            self.architect.build_chapter_glossary("test_book", "ch1", 0, 1)
        
        # Should call at least twice: 1 for extraction, 1 for translation of "Functor"
        self.assertGreaterEqual(mock_post.call_count, 2)
        
        # Check first call has json format
        first_call_payload = mock_post.call_args_list[0].kwargs['json']
        self.assertEqual(first_call_payload['format'], 'json')

if __name__ == '__main__':
    unittest.main()
