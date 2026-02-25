#!/usr/bin/env python3
"""
WSD (Word Sense Disambiguation) Agent for PCM Translation Pipeline.
Classifies the domain of a text and provides translation guides for ambiguous terms.
"""

import requests
import json
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

class DomainClassifier:
    """Classifies a given text into one of the predefined mathematical domains."""
    
    DOMAINS = [
        "classical_mechanics", 
        "quantum_mechanics", 
        "algebra", 
        "topology", 
        "differential_geometry", 
        "category_theory", 
        "analysis", 
        "number_theory", 
        "combinatorics", 
        "geometry"
    ]

    # Keyword mapping for fallback classification
    DOMAIN_KEYWORDS = {
        "classical_mechanics": ["force", "mass", "acceleration", "momentum", "lagrangian", "hamiltonian", "newton", "velocity"],
        "quantum_mechanics": ["schrodinger", "wavefunction", "observable", "hilbert space", "operator", "spin", "particle", "quantum"],
        "algebra": ["group", "ring", "field", "module", "ideal", "isomorphism", "homomorphism", "linear", "vector"],
        "topology": ["open set", "closed set", "compact", "connected", "homeomorphism", "manifold", "continuity", "metric space"],
        "differential_geometry": ["curvature", "metric tensor", "connection", "bundle", "differential form", "riemannian", "geodesic"],
        "category_theory": ["category", "functor", "natural transformation", "morphism", "adjoint", "limit", "colimit"],
        "analysis": ["derivative", "integral", "measure", "convergence", "limit", "sequence", "series", "function", "complex"],
        "number_theory": ["prime", "integer", "divisibility", "congruence", "zeta function", "modular", "arithmetic"],
        "combinatorics": ["graph", "permutation", "combination", "counting", "enumeration", "partition", "algorithm"],
        "geometry": ["point", "line", "plane", "angle", "surface", "volume", "triangle", "polygon", "euclidean"]
    }

    def __init__(self, model_name: str = "qwen3:14b", ollama_url: str = "http://localhost:11434/api/generate"):
        self.model_name = model_name
        self.ollama_url = ollama_url

    def classify(self, section_text: str) -> str:
        """
        Classifies the section text into a domain using Ollama.
        Falls back to keyword matching if LLM fails.
        """
        if not section_text.strip():
            return "general"

        prompt = f"""Identify the primary mathematical or physical domain of the following text.
Choose ONLY ONE from this list: {', '.join(self.DOMAINS)}, or "general".

Rules:
- Output ONLY the domain name.
- If unsure, output "general".

Text:
{section_text[:2000]}

Domain:"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 100,
                "temperature": 0.0
            }
        }

        try:
            response = requests.post(self.ollama_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            raw_response = result.get("response", "").strip()
            
            # Remove <think>...</think> tags if present (common in qwen/reasoning models)
            cleaned_response = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL).strip().lower()
            
            # Extract the first word or check if any domain is mentioned
            for domain in self.DOMAINS:
                if domain in cleaned_response:
                    return domain
            
            return "general"

        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            # Fallback to keyword matching
            return self._fallback_classify(section_text)

    def _fallback_classify(self, text: str) -> str:
        """Simple keyword-based classification fallback."""
        text_lower = text.lower()
        counts = {domain: 0 for domain in self.DOMAINS}
        
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    counts[domain] += 1
        
        best_domain = max(counts, key=counts.get)
        if counts[best_domain] > 0:
            return best_domain
        return "general"


class WSDGuideGenerator:
    """Generates translation guides for ambiguous terms based on the detected domain."""

    # Alias mapping for domains to match JSON keys
    DOMAIN_ALIASES = {
        "classical_mechanics": ["physics"],
        "quantum_mechanics": ["physics"],
        "differential_geometry": ["geometry"],
        "analysis": ["calculus", "statistics"],
        "topology": ["geometry"]
    }

    def __init__(self, terms_path: str = None):
        if terms_path is None:
            # Default path relative to project root
            terms_path = str(Path(__file__).parent.parent / "data" / "ambiguous_terms.json")
        
        self.terms_path = terms_path
        self.ambiguous_terms = self._load_terms()

    def _load_terms(self) -> List[Dict]:
        """Loads the ambiguous terms dictionary from JSON."""
        try:
            with open(self.terms_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def extract_ambiguous_terms(self, text: str, domain: str) -> List[Dict]:
        """Extracts ambiguous terms that appear in the text."""
        found_terms = []
        text_lower = text.lower()
        
        # Determine relevant domain keys to search in JSON
        target_domains = [domain]
        if domain in self.DOMAIN_ALIASES:
            target_domains.extend(self.DOMAIN_ALIASES[domain])
        
        for item in self.ambiguous_terms:
            term = item.get("term", "")
            if not term:
                continue
                
            # Use word boundaries to avoid partial matches
            pattern = rf'\b{re.escape(term.lower())}\b'
            if re.search(pattern, text_lower):
                # Determine translation based on domain or aliases
                domains_map = item.get("domains", {})
                translation = None
                
                for d in target_domains:
                    if d in domains_map:
                        translation = domains_map[d]
                        break
                
                if not translation:
                    translation = domains_map.get("general") or list(domains_map.values())[0]
                
                # Get definition for the specific domain, aliases, or general
                definition = ""
                defs_map = item.get("definition", {})
                for d in target_domains:
                    if d in defs_map:
                        definition = defs_map[d]
                        break
                if not definition:
                    definition = defs_map.get("general", "")
                
                found_terms.append({
                    "term": term,
                    "translation": translation,
                    "definition": definition,
                    "wrong_translations": item.get("wrong_translations", [])
                })
        
        return found_terms

    def generate_guide(self, text: str, domain: str) -> Dict[str, Any]:
        """Generates a structured WSD guide and a prompt constraint string."""
        terms = self.extract_ambiguous_terms(text, domain)
        
        if not terms:
            return {
                "domain": domain,
                "terms": [],
                "prompt_constraint": ""
            }
        
        constraint_lines = [f"- 이 텍스트의 도메인은 '{domain}'입니다."]
        constraint_lines.append("- 다음 용어들은 문맥에 맞춰 아래와 같이 번역해야 합니다:")
        
        for t in terms:
            line = f"  * {t['term']} → {t['translation']}"
            if t['definition']:
                line += f" ({t['definition']})"
            if t['wrong_translations']:
                line += f" [주의: {', '.join(t['wrong_translations'])} 등으로 번역하지 말 것]"
            constraint_lines.append(line)
            
        prompt_constraint = "번역 시 다음 용어 규칙을 준수하세요:\n" + "\n".join(constraint_lines)
        
        return {
            "domain": domain,
            "terms": terms,
            "prompt_constraint": prompt_constraint
        }


class WSDAgent:
    """Orchestrates domain classification and translation guide generation."""

    def __init__(self, model_name: str = "qwen3:14b", terms_path: str = None):
        self.classifier = DomainClassifier(model_name=model_name)
        self.guide_gen = WSDGuideGenerator(terms_path=terms_path)

    def analyze(self, section_text: str) -> Dict[str, Any]:
        """Performs full WSD analysis on the given text."""
        domain = self.classifier.classify(section_text)
        guide = self.guide_gen.generate_guide(section_text, domain)
        
        return {
            "domain": domain,
            "guide": guide,
            "prompt_injection": guide["prompt_constraint"]
        }

    def inject_to_prompt(self, base_prompt: str, section_text: str) -> str:
        """Injects WSD constraints into the translation prompt."""
        analysis = self.analyze(section_text)
        injection = analysis["prompt_injection"]
        
        if not injection:
            return base_prompt
            
        # Insert injection before the main text
        if "English text:" in base_prompt:
            parts = base_prompt.split("English text:")
            return parts[0] + injection + "\n\nEnglish text:" + parts[1]
        
        return base_prompt + "\n\n" + injection


if __name__ == "__main__":
    # Quick test
    agent = WSDAgent()
    sample_text = "The ring of integers is a fundamental object in algebra. The kernel of the map is nontrivial."
    result = agent.analyze(sample_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))
