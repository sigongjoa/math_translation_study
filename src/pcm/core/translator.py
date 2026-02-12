#!/usr/bin/env python3
"""
Translator module using Ollama with quality checks and polishing
"""

import requests
import json
import re
import time
from typing import Dict, List, Optional
from pathlib import Path
from tqdm import tqdm

# Standard math terminology mapping (English → Korean)
MATH_GLOSSARY = {
    "group": "군",
    "ring": "환",
    "field": "체",
    "vector space": "벡터 공간",
    "manifold": "다양체",
    "topology": "위상수학",
    "topological": "위상적",
    "homeomorphism": "위상동형사상",
    "isomorphism": "동형사상",
    "homomorphism": "준동형사상",
    "automorphism": "자기동형사상",
    "endomorphism": "자기준동형사상",
    "Abelian": "아벨",
    "abelian": "아벨",
    "commutative": "가환",
    "associative": "결합",
    "distributive": "분배",
    "identity element": "항등원",
    "inverse": "역원",
    "subgroup": "부분군",
    "normal subgroup": "정규 부분군",
    "quotient group": "몫군",
    "kernel": "핵",
    "image": "상",
    "surjective": "전사",
    "injective": "단사",
    "bijective": "전단사",
    "polynomial": "다항식",
    "eigenvalue": "고유값",
    "eigenvector": "고유벡터",
    "determinant": "행렬식",
    "matrix": "행렬",
    "trace": "대각합",
    "linear": "선형",
    "nonlinear": "비선형",
    "continuous": "연속",
    "differentiable": "미분가능",
    "integrable": "적분가능",
    "holomorphic": "정칙",
    "meromorphic": "유리형",
    "analytic": "해석적",
    "compact": "컴팩트",
    "open set": "열린집합",
    "closed set": "닫힌집합",
    "bounded": "유계",
    "convergent": "수렴",
    "divergent": "발산",
    "sequence": "수열",
    "series": "급수",
    "limit": "극한",
    "derivative": "도함수",
    "integral": "적분",
    "measure": "측도",
    "probability": "확률",
    "random variable": "확률변수",
    "theorem": "정리",
    "lemma": "보조정리",
    "corollary": "따름정리",
    "conjecture": "추측",
    "proof": "증명",
    "axiom": "공리",
    "definition": "정의",
    "proposition": "명제",
    "prime": "소수",
    "irrational": "무리수",
    "rational": "유리수",
    "integer": "정수",
    "real number": "실수",
    "complex number": "복소수",
    "natural number": "자연수",
    "finite": "유한",
    "infinite": "무한",
    "countable": "가산",
    "uncountable": "비가산",
    "dimension": "차원",
    "degree": "차수",
    "order": "위수",
    "finitely generated": "유한 생성",
    "equivalence": "동치",
    "invariant": "불변량",
    "symmetry": "대칭",
    "permutation": "순열",
    "combination": "조합",
}


class OllamaTranslator:
    def __init__(self, model_name: str = "gemma2:9b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self.glossary = MATH_GLOSSARY

    def _build_glossary_hint(self, text: str) -> str:
        """Build glossary hints for terms found in the text."""
        hints = []
        text_lower = text.lower()
        for eng, kor in self.glossary.items():
            if eng.lower() in text_lower:
                hints.append(f"  {eng} → {kor}")
        if hints:
            return "수학 용어 참조:\n" + "\n".join(hints[:15])  # max 15 terms
        return ""

    def translate_text(self, text: str, context: str = "") -> str:
        """Translate English text to Korean with quality controls."""
        if not text.strip():
            return ""

        glossary_hint = self._build_glossary_hint(text)

        prompt = f"""You are a professional Korean translator specializing in mathematics. Translate the following English text into natural Korean.

STRICT RULES:
- Output ONLY the Korean translation. No explanations, comments, or English text.
- Preserve all math symbols, formulas, variables exactly as-is
- Use standard Korean math terminology
- Do NOT use markdown formatting (no **, *, #, etc.)
- Do NOT use HTML tags (no <sup>, <sub>, etc.)
- Do NOT write in Chinese or Japanese
- Do NOT explain what the text means - just translate it
- Write superscripts as LaTeX: x^n, not x<sup>n</sup>
- Write subscripts as LaTeX: a_i, not a<sub>i</sub>

{glossary_hint}

English text:
{text}

Korean translation:"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 4096,
                "repeat_penalty": 1.3,
                "repeat_last_n": 256,
                "top_k": 40,
                "top_p": 0.9,
            }
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=300)
            response.raise_for_status()
            result = response.json()
            translated = result.get("response", "").strip()
            return self._quality_check(translated)
        except requests.exceptions.RequestException as e:
            print(f"Translation error: {e}")
            return f"[TRANSLATION ERROR: {str(e)}]"

    def _quality_check(self, text: str) -> str:
        """Post-translation quality check: remove CJK noise, English blocks, repetitions."""
        # 1. Remove Chinese characters
        text = re.sub(r'[\u4e00-\u9fff]+', '', text)
        text = re.sub(r'[\u3400-\u4dbf]+', '', text)

        # 2. Remove Japanese characters
        text = re.sub(r'[\u3040-\u309f]+', '', text)
        text = re.sub(r'[\u30a0-\u30ff]+', '', text)

        # 3. Remove meta-comments
        text = re.sub(r'(以下是|翻译|번역문|Translation|Note:|Let me know|Let\'s break down).*?\n', '', text)

        # 4. Remove markdown formatting artifacts
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold** → bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)       # *italic* → italic
        text = re.sub(r'^\s*[*\-]\s+', '', text, flags=re.MULTILINE)  # bullet points
        text = re.sub(r'^\s*#+\s+', '', text, flags=re.MULTILINE)     # ## headers

        # 5. Remove HTML tags
        text = re.sub(r'<sup>(.*?)</sup>', r'^{\1}', text)
        text = re.sub(r'<sub>(.*?)</sub>', r'_{\1}', text)
        text = re.sub(r'<[^>]+>', '', text)

        # 6. Detect and remove English-heavy paragraphs (translation failure)
        text = self._remove_english_blocks(text)

        # 7. Remove repetitions
        text = self._remove_repetitions(text)

        # 8. Clean up
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)

        return text.strip()

    def _remove_english_blocks(self, text: str) -> str:
        """Remove paragraphs that are mostly English (translation failure)."""
        paragraphs = text.split('\n\n')
        result = []
        for para in paragraphs:
            clean = para.strip()
            if not clean:
                continue
            # Count Korean vs ASCII characters
            korean = len(re.findall(r'[\uac00-\ud7af]', clean))
            ascii_alpha = len(re.findall(r'[a-zA-Z]', clean))
            total = korean + ascii_alpha
            if total == 0:
                result.append(clean)
            elif korean / max(total, 1) < 0.15 and len(clean) > 100:
                # Less than 15% Korean in a long paragraph = likely untranslated
                continue
            else:
                result.append(clean)
        return '\n\n'.join(result)

    def _remove_repetitions(self, text: str) -> str:
        """Detect and remove repeated paragraphs/sentences."""
        paragraphs = text.split('\n\n')
        if len(paragraphs) <= 1:
            return text

        seen = []
        result = []
        for para in paragraphs:
            clean = para.strip()
            if not clean:
                continue
            # Check if this paragraph is too similar to one we've seen
            is_duplicate = False
            for seen_para in seen:
                if len(clean) > 30 and clean[:30] == seen_para[:30]:
                    is_duplicate = True
                    break
            if not is_duplicate:
                seen.append(clean)
                result.append(clean)

        return '\n\n'.join(result)

    def polish_text(self, translated: str, original: str = "") -> str:
        """Second pass: polish the translated text for readability."""
        if not translated.strip():
            return ""

        prompt = f"""다음 한국어 번역문을 다듬어 주세요. 수학 교과서의 번역문입니다.

다듬기 규칙:
- 어색한 표현을 자연스러운 한국어로 수정
- 수학 용어가 일관되게 사용되는지 확인
- 수학 기호와 공식은 절대 변경하지 마세요
- 다듬어진 번역문만 출력 (설명 없이)

번역문:
{translated}

다듬어진 번역문:"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 4096,
                "repeat_penalty": 1.3,
                "repeat_last_n": 256,
            }
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=300)
            response.raise_for_status()
            result = response.json()
            polished = result.get("response", "").strip()
            polished = self._quality_check(polished)
            # If polishing made it worse (much shorter), keep original
            if len(polished) < len(translated) * 0.5:
                return translated
            return polished
        except requests.exceptions.RequestException:
            return translated  # fallback to unpolished

    def translate_section(self, section_data: Dict, do_polish: bool = True) -> Dict:
        """Translate a complete section with optional polishing."""
        print(f"Translating section {section_data.get('section_id', 'unknown')}...")

        # Translate title
        if section_data.get("title_original"):
            print(f"  Translating title...")
            section_data["title_translated"] = self.translate_text(
                section_data["title_original"],
                context="section title"
            )
            time.sleep(0.5)

        # Translate content
        if section_data.get("content_original"):
            content = section_data["content_original"]
            print(f"  Translating content ({len(content)} chars)...")

            max_chunk_size = 2000  # smaller chunks for better quality
            if len(content) > max_chunk_size:
                chunks = self._split_into_chunks(content, max_chunk_size)
                translated_chunks = []

                for chunk in tqdm(chunks, desc="  Chunks", leave=False):
                    translated_chunk = self.translate_text(chunk)
                    translated_chunks.append(translated_chunk)
                    time.sleep(0.5)

                translated = "\n\n".join(translated_chunks)
            else:
                translated = self.translate_text(content)

            # 2nd pass: polish
            if do_polish:
                print(f"  Polishing translation...")
                # Polish in chunks too if long
                if len(translated) > 2000:
                    polish_chunks = self._split_into_chunks(translated, 2000)
                    polished_chunks = []
                    for pc in polish_chunks:
                        polished_chunks.append(self.polish_text(pc))
                        time.sleep(0.5)
                    translated = "\n\n".join(polished_chunks)
                else:
                    translated = self.polish_text(translated)

            section_data["content_translated"] = translated

        return section_data

    def _split_into_chunks(self, text: str, max_size: int) -> List[str]:
        """Split text into chunks at paragraph boundaries."""
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para_size = len(para)
            if current_size + para_size > max_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def test_connection(self) -> bool:
        """Test if Ollama server is accessible."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            print(f"Connected to Ollama at {self.base_url}")

            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]

            if self.model_name in model_names:
                print(f"Model '{self.model_name}' is available")
                return True
            else:
                print(f"Model '{self.model_name}' not found.")
                print(f"Available: {', '.join(model_names[:5])}")
                # Try to find a suitable alternative
                for name in model_names:
                    if "gemma" in name or "eeve" in name or "llama" in name:
                        print(f"Suggestion: try --model {name}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"Cannot connect to Ollama: {e}")
            return False


def main():
    """Test the translator."""
    translator = OllamaTranslator(model_name="gemma2:9b")

    if not translator.test_connection():
        print("\nPlease ensure Ollama is running: ollama serve")
        return

    test_text = "A group G is called finitely generated if there is some finite set of elements of G such that all the rest can be written as products."
    print(f"\nOriginal: {test_text}")

    translated = translator.translate_text(test_text)
    print(f"Translated: {translated}")

    polished = translator.polish_text(translated)
    print(f"Polished: {polished}")


if __name__ == "__main__":
    main()
