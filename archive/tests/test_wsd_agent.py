#!/usr/bin/env python3
import sys
import os
import pytest
import json
import requests
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from pcm.core.wsd_agent import DomainClassifier, WSDGuideGenerator, WSDAgent

# Fixtures
@pytest.fixture
def domain_classifier():
    return DomainClassifier()

@pytest.fixture
def wsd_guide_generator():
    # Use actual ambiguous_terms.json or a temp one if needed.
    # The requirement says to use the existing code, so we use the default path.
    return WSDGuideGenerator()

@pytest.fixture
def wsd_agent():
    return WSDAgent()

class TestDomainClassifier:
    
    @patch("requests.post")
    def test_classify_algebra(self, mock_post, domain_classifier):
        # Mock successful LLM response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "algebra"}
        mock_post.return_value = mock_response
        
        text = "The ring of integers is a field. Every homomorphism preserves the structure."
        result = domain_classifier.classify(text)
        
        assert result == "algebra"
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_classify_fallback_on_ollama_error(self, mock_post, domain_classifier):
        # Mock requests exception to trigger fallback
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        # Text with clear algebra keywords
        text = "This text contains group, ring, and field which are algebraic structures."
        result = domain_classifier.classify(text)
        
        # Should fallback to keyword matching
        assert result == "algebra"

    @patch("requests.post")
    def test_classify_returns_valid_domain(self, mock_post, domain_classifier):
        # Mock response that is not in the list but contains a valid domain
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "I think this text is about topology."}
        mock_post.return_value = mock_response
        
        result = domain_classifier.classify("some topological text")
        
        assert result in domain_classifier.DOMAINS or result == "general"
        assert result == "topology"

class TestWSDGuideGenerator:

    def test_extract_ambiguous_terms_field(self, wsd_guide_generator):
        text = "Consider a vector field over a finite field."
        # field exists in ambiguous_terms.json
        terms = wsd_guide_generator.extract_ambiguous_terms(text, "algebra")
        
        # Check if 'field' is extracted
        found = [t for t in terms if t["term"] == "field"]
        assert len(found) > 0
        assert found[0]["translation"] == "체(體)"

    def test_extract_case_insensitive(self, wsd_guide_generator):
        text = "The KERNEL of the map is trivial. Kernel is important."
        terms = wsd_guide_generator.extract_ambiguous_terms(text, "algebra")
        
        # Check if 'kernel' is extracted despite casing
        found = [t for t in terms if t["term"] == "kernel"]
        assert len(found) > 0
        assert found[0]["translation"] == "핵(核)"

    def test_generate_guide_structure(self, wsd_guide_generator):
        text = "A ring is an algebraic structure."
        guide = wsd_guide_generator.generate_guide(text, "algebra")
        
        assert "domain" in guide
        assert "terms" in guide
        assert "prompt_constraint" in guide
        assert guide["domain"] == "algebra"
        assert any(t["term"] == "ring" for t in guide["terms"])

    def test_generate_guide_algebra_field(self, wsd_guide_generator):
        text = "The elements of the field are scalars."
        guide = wsd_guide_generator.generate_guide(text, "algebra")
        
        # Find 'field' in terms
        field_term = next((t for t in guide["terms"] if t["term"] == "field"), None)
        assert field_term is not None
        assert field_term["translation"] == "체(體)"
        assert "체(體)" in guide["prompt_constraint"]

    def test_prompt_constraint_not_empty(self, wsd_guide_generator):
        text = "The kernel of this transformation is non-empty."
        guide = wsd_guide_generator.generate_guide(text, "algebra")
        
        assert guide["prompt_constraint"] != ""
        assert "kernel" in guide["prompt_constraint"].lower()

class TestWSDAgent:

    @patch("requests.post")
    def test_analyze_returns_required_keys(self, mock_post, wsd_agent):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "algebra"}
        mock_post.return_value = mock_response
        
        text = "A ring of integers."
        result = wsd_agent.analyze(text)
        
        assert "domain" in result
        assert "guide" in result
        assert "prompt_injection" in result
        assert result["domain"] == "algebra"

    @patch("requests.post")
    def test_inject_to_prompt(self, mock_post, wsd_agent):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "algebra"}
        mock_post.return_value = mock_response
        
        base_prompt = "Translate the following. English text: Hello world"
        section_text = "The field of complex numbers."
        
        injected = wsd_agent.inject_to_prompt(base_prompt, section_text)
        
        assert "체(體)" in injected
        assert "English text: Hello world" in injected
        # Check if it was injected before "English text:"
        assert injected.index("체(體)") < injected.index("English text:")

    @patch("requests.post")
    def test_inject_to_prompt_preserves_original(self, mock_post, wsd_agent):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "algebra"}
        mock_post.return_value = mock_response
        
        base_prompt = "Please translate accurately."
        section_text = "A simple sentence with ring."
        
        injected = wsd_agent.inject_to_prompt(base_prompt, section_text)
        
        assert base_prompt in injected
        assert "ring" in injected.lower()
