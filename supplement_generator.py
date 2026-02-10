#!/usr/bin/env python3
"""
Supplement generator: auto-generate learning materials for translated math sections.
Uses Ollama (qwen2.5-coder:7b) to create summaries, TikZ diagrams, examples,
exercises with solutions, and glossary tables.
"""

import requests
import json
import re
import time
from typing import Dict, List, Optional


class SupplementGenerator:
    def __init__(self, model_name: str = "qwen2.5-coder:7b",
                 base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"

    def _call_ollama(self, prompt: str, temperature: float = 0.4,
                     max_tokens: int = 4096) -> str:
        """Call Ollama API and return the response text."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "repeat_penalty": 1.2,
                "top_k": 40,
                "top_p": 0.9,
            }
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=300)
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except requests.exceptions.RequestException as e:
            print(f"  Ollama error: {e}")
            return ""

    def generate_summary(self, content: str, title: str = "") -> str:
        """Generate a concise Korean summary of the section."""
        prompt = f"""다음은 수학 교과서의 한국어 번역문입니다. 이 내용의 핵심을 3~5문장으로 요약해주세요.

규칙:
- 한국어로만 작성
- 수학 기호와 공식은 그대로 유지
- 핵심 개념과 주요 결과만 간결하게
- 요약문만 출력 (설명이나 제목 없이)

제목: {title}

내용:
{content[:3000]}

핵심 요약:"""

        result = self._call_ollama(prompt, temperature=0.3)
        return self._clean_output(result)

    def generate_tikz_diagram(self, content: str, title: str = "") -> str:
        """Generate a TikZ diagram illustrating the key concept."""
        prompt = f"""You are a LaTeX/TikZ expert. Create a meaningful TikZ diagram that visually illustrates the key mathematical concept or relationship from this section.

Rules:
- Output ONLY the TikZ code (starting with \\begin{{tikzpicture}} and ending with \\end{{tikzpicture}})
- FOCUS on the core concept (e.g., if it's about sets, show a Venn diagram; if it's about transformations, show before/after; if it's about coordinates, show a graph)
- AVOID generic flowcharts (like V -> E -> F) unless it's the specific topic.
- Use relative positioning (e.g., [right=of node], [above=of node]) instead of large absolute coordinates.
- Label nodes in natural Korean where appropriate, use math symbols ($...$) for formulas.
- Use simple, professional shapes: rectangles, circles, arrows.
- Keep it clean and readable: max 12 nodes.
- Use black and white only (no colors).
- Do NOT use any extra package imports or custom styles outside the environment.
- Available TikZ libraries: arrows.meta, positioning, shapes, calc, decorations.pathreplacing

Section title: {title}

Content summary:
{content[:2000]}

TikZ code:"""

        result = self._call_ollama(prompt, temperature=0.3, max_tokens=2048)
        return self._extract_tikz(result)

    def generate_examples(self, content: str, title: str = "") -> List[str]:
        """Generate 2-3 concrete examples illustrating the concepts."""
        prompt = f"""다음 수학 내용에 대한 구체적인 예시를 2~3개 만들어주세요.

규칙:
- 한국어로 작성
- 각 예시는 "예시 N:" 으로 시작
- 수학 기호는 LaTeX 형식 사용 ($x^2$, $\\sum$ 등)
- 각 예시는 개념을 직관적으로 이해할 수 있도록
- 예시만 출력 (다른 설명 없이)

제목: {title}

내용:
{content[:2500]}

예시:"""

        result = self._call_ollama(prompt, temperature=0.5)
        return self._parse_numbered_items(result, prefix_pattern=r'예시\s*\d+\s*[:：]')

    def generate_exercises(self, content: str, title: str = "") -> List[str]:
        """Generate 2-4 practice exercises."""
        prompt = f"""다음 수학 내용에 대한 연습 문제를 2~3개 만들어주세요.

규칙:
- 한국어로 작성
- 각 문제는 "문제 N:" 으로 시작
- 난이도: 기초 1개, 중급 1~2개
- 수학 기호는 LaTeX 형식 사용
- 문제만 출력 (풀이 없이)

제목: {title}

내용:
{content[:2500]}

연습 문제:"""

        result = self._call_ollama(prompt, temperature=0.5)
        return self._parse_numbered_items(result, prefix_pattern=r'문제\s*\d+\s*[:：]')

    def generate_solutions(self, exercises: List[str], content: str = "") -> str:
        """Generate solutions for the exercises."""
        if not exercises:
            return ""

        exercises_text = "\n".join([f"{i+1}. {ex}" for i, ex in enumerate(exercises)])

        prompt = f"""다음 수학 연습 문제들의 풀이를 작성해주세요.

규칙:
- 한국어로 작성
- 각 풀이는 "풀이 N:" 으로 시작
- 핵심 풀이 과정을 간결하게
- 수학 기호는 LaTeX 형식 사용

문제:
{exercises_text}

풀이:"""

        result = self._call_ollama(prompt, temperature=0.3)
        return self._clean_output(result)

    def generate_glossary(self, content: str, original_content: str = "") -> List[List[str]]:
        """Extract key terms and provide Korean translations/definitions."""
        # Use the original English content if available for better term extraction
        source = original_content if original_content else content

        prompt = f"""Extract 5-8 key mathematical terms from this text and provide Korean translations.

Rules:
- Output format: exactly "English term | Korean translation (brief definition)"
- One term per line
- Only mathematical/technical terms
- Korean definitions should be concise (under 15 characters)

Text:
{source[:2500]}

Terms:"""

        result = self._call_ollama(prompt, temperature=0.2)
        return self._parse_glossary(result)

    def generate_all_supplements(self, section_data: Dict) -> Dict:
        """Generate all supplement types for a section."""
        title = section_data.get("title_translated", section_data.get("title_original", ""))
        content = section_data.get("content_translated", "")
        original = section_data.get("content_original", "")

        if not content or len(content) < 100:
            return {}

        supplements = {}

        # 1. Summary
        print(f"    Generating summary...")
        summary = self.generate_summary(content, title)
        if summary and len(summary) > 30:
            supplements["summary"] = summary
        time.sleep(0.3)

        # 2. TikZ diagram
        print(f"    Generating TikZ diagram...")
        tikz = self.generate_tikz_diagram(content, title)
        if tikz and "\\begin{tikzpicture}" in tikz:
            supplements["tikz_diagram"] = tikz
        time.sleep(0.3)

        # 3. Examples
        print(f"    Generating examples...")
        examples = self.generate_examples(content, title)
        if examples:
            supplements["examples"] = examples
        time.sleep(0.3)

        # 4. Exercises
        print(f"    Generating exercises...")
        exercises = self.generate_exercises(content, title)
        if exercises:
            supplements["exercises"] = exercises
            time.sleep(0.3)

            # 5. Solutions
            print(f"    Generating solutions...")
            solutions = self.generate_solutions(exercises, content)
            if solutions:
                supplements["solutions"] = solutions
        time.sleep(0.3)

        # 6. Glossary
        print(f"    Generating glossary...")
        glossary = self.generate_glossary(content, original)
        if glossary:
            supplements["glossary"] = glossary

        return supplements

    # ─── Helper methods ───

    def _clean_output(self, text: str) -> str:
        """Remove meta-comments and clean up output."""
        if not text:
            return ""

        # Remove common meta-comments
        text = re.sub(r'(Here is|Here are|Below is|I\'ll|Let me|Note:).*?\n', '', text)
        text = re.sub(r'(다음은|아래는|참고:).*?\n', '', text)

        # Remove markdown formatting
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)

        # Clean whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)

        return text.strip()

    def _extract_tikz(self, text: str) -> str:
        """Extract TikZ code from response."""
        if not text:
            return ""

        # Try to find tikzpicture environment
        match = re.search(
            r'(\\begin\{tikzpicture\}.*?\\end\{tikzpicture\})',
            text, re.DOTALL
        )
        if match:
            tikz_code = match.group(1)
            # Basic validation
            if tikz_code.count('\\begin{') == tikz_code.count('\\end{'):
                return tikz_code

        return ""

    def _parse_numbered_items(self, text: str, prefix_pattern: str) -> List[str]:
        """Parse numbered items from text."""
        if not text:
            return []

        # Split by the prefix pattern
        parts = re.split(prefix_pattern, text)
        items = []

        for part in parts:
            cleaned = part.strip()
            if cleaned and len(cleaned) > 10:
                # Remove leading numbers/dots
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', cleaned)
                cleaned = self._clean_output(cleaned)
                if cleaned:
                    items.append(cleaned)

        # Fallback: try splitting by numbered lines
        if not items:
            lines = text.strip().split('\n')
            current_item = []
            for line in lines:
                if re.match(r'^\d+[\.\)]\s+', line.strip()):
                    if current_item:
                        item_text = ' '.join(current_item).strip()
                        if len(item_text) > 10:
                            items.append(self._clean_output(item_text))
                    current_item = [re.sub(r'^\d+[\.\)]\s+', '', line.strip())]
                elif line.strip():
                    current_item.append(line.strip())
            if current_item:
                item_text = ' '.join(current_item).strip()
                if len(item_text) > 10:
                    items.append(self._clean_output(item_text))

        return items[:4]  # Max 4 items

    def _parse_glossary(self, text: str) -> List[List[str]]:
        """Parse glossary entries from 'English | Korean' format."""
        if not text:
            return []

        entries = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Remove leading numbers/bullets
            line = re.sub(r'^[\d\.\-\*]+\s*', '', line)

            # Try pipe separator
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    eng = parts[0].strip()
                    kor = parts[1].strip()
                    if eng and kor:
                        entries.append([eng, kor])
            # Try dash/colon separator
            elif ' - ' in line or ': ' in line:
                sep = ' - ' if ' - ' in line else ': '
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    eng = parts[0].strip()
                    kor = parts[1].strip()
                    if eng and kor:
                        entries.append([eng, kor])

        return entries[:8]  # Max 8 terms

    def test_connection(self) -> bool:
        """Test if the model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]

            if self.model_name in model_names:
                print(f"Supplement model '{self.model_name}' is available")
                return True
            else:
                print(f"Supplement model '{self.model_name}' not found.")
                print(f"Available: {', '.join(model_names[:5])}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Cannot connect to Ollama: {e}")
            return False


def main():
    """Test the supplement generator."""
    gen = SupplementGenerator()

    if not gen.test_connection():
        print("Please ensure Ollama is running with qwen2.5-coder:7b")
        return

    # Test with sample content
    test_section = {
        "title_translated": "가설 약화 및 결론 강화",
        "title_original": "Weakening Hypotheses and Strengthening Conclusions",
        "content_translated": "숫자 1729는 두 가지 다른 방식으로 세제곱의 합으로 나타날 수 있다는 점에서 유명합니다.",
        "content_original": "The number 1729 is famous for being expressible as the sum of two cubes in two different ways.",
    }

    print("\nGenerating supplements...")
    supplements = gen.generate_all_supplements(test_section)
    print(f"\nGenerated {len(supplements)} supplement types:")
    for key in supplements:
        val = supplements[key]
        if isinstance(val, list):
            print(f"  {key}: {len(val)} items")
        else:
            print(f"  {key}: {len(str(val))} chars")


if __name__ == "__main__":
    main()
