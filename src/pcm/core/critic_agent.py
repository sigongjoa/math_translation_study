import json
import re
import requests

class CriticAgent:
    """
    Expert Critic that reviews translations for mathematical accuracy, 
    terminology consistency, and contextual nuance.
    """
    
    def __init__(self, model="qwen2.5:7b"):
        self.model = model
        self.ollama_url = "http://localhost:11434/api/chat"

    def critique(self, original_en, translated_ko, glossary):
        """Generates a critical review of the translation."""
        glossary_str = json.dumps(glossary, ensure_ascii=False, indent=2)
        
        prompt = f"""You are a senior mathematics professor and professional translator. 
Critically review the following translation from English to Korean.

[ORIGINAL ENGLISH]
{original_en}

[TRANSLATED KOREAN]
{translated_ko}

[STRICT GLOSSARY]
{glossary_str}

CRITIQUE CRITERIA:
1. Did the translation use the [STRICT GLOSSARY] correctly? (e.g. Preorder -> 전순서)
2. Are there any contextual mistranslations? (Check 'necessarily', 'sum of parts', etc.)
3. Is the academic tone appropriate and are there spacing (띄어쓰기) issues?
4. Are mathematical formulas ($...$) preserved exactly?

If there are issues, list them clearly. If it is perfect, say 'PASS'.
Output your critique in Korean."""

        try:
            resp = requests.post(self.ollama_url, json={
                "model": self.model,
                "messages": [{"role": "system", "content": "You are a perfectionist math translator critic."}, 
                             {"role": "user", "content": prompt}],
                "stream": False, "options": {"temperature": 0.1}
            }, timeout=120)
            return resp.json()["message"]["content"].strip()
        except:
            return "Critique failed."

    def refine(self, original_en, translated_ko, critique, glossary):
        """Refines the translation based on the critique."""
        if "PASS" in critique.upper() and len(critique) < 10:
            return translated_ko

        prompt = f"""Refine the following Korean translation based on the provided critique.

[ORIGINAL ENGLISH]
{original_en}

[PREVIOUS TRANSLATION]
{translated_ko}

[CRITIQUE]
{critique}

[STRICT GLOSSARY]
{json.dumps(glossary, ensure_ascii=False, indent=2)}

RULES:
1. Apply all corrections suggested in the critique.
2. Ensure strict adherence to the glossary.
3. Keep mathematical formulas exactly as-is.
4. Final output should be only the refined Korean text."""

        try:
            resp = requests.post(self.ollama_url, json={
                "model": self.model,
                "messages": [{"role": "system", "content": "You are an expert editor refining a math textbook."}, 
                             {"role": "user", "content": prompt}],
                "stream": False, "options": {"temperature": 0.1}
            }, timeout=120)
            return resp.json()["message"]["content"].strip()
        except:
            return translated_ko
