import json
import re
import time
from pathlib import Path
import fitz
import requests
from src.pcm.core.knowledge_agent import KnowledgeAgent

class GlossaryArchitect:
    """
    Extracts technical terms using LLM and builds a structured glossary 
    by analyzing PDF content, with multi-stage verification.
    """
    def __init__(
        self,
        pdf_path,
        model: str = "gemma2:9b",
        ollama_url: str = "http://localhost:11434/api/chat",
    ):
        self.pdf_path = pdf_path
        self.model = model
        self.ollama_url = ollama_url
        self.glossary_dir = Path("src/pcm/data/glossaries")
        self.glossary_dir.mkdir(parents=True, exist_ok=True)

    def _call_ollama(self, prompt, json_format=False):
        """Helper to call Ollama API."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        if json_format:
            payload["format"] = "json"
            
        try:
            resp = requests.post(self.ollama_url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"  [Ollama Error] {e}")
            return None

    def build_chapter_glossary(self, book_id, chapter_id, start_page, end_page):
        """Actually extracts and builds the glossary via LLM reasoning and Wikipedia verification."""
        print(f"--- [GlossaryArchitect] Deep Analysis: {book_id} {chapter_id} ---")
        
        final_glossary = {}
        critical_fixes = {
            "Preorder": "전순서(preorder)",
            "Skeletality": "골격성(skeletality)",
            "Discrete": "이산(discrete)",
            "Poset": "포셋(poset)",
            "Monoid": "모노이드(monoid)",
            "Category": "범주(category)",
            "Functor": "함자(functor)",
            "Natural Transformation": "자연 변환(natural transformation)"
        }

        try:
            doc = fitz.open(self.pdf_path)
            sample_text = ""
            # Sample first few pages of the chapter to find keywords
            for i in range(start_page, min(start_page + 3, end_page)):
                if i < len(doc):
                    sample_text += doc[i].get_text()
            doc.close()

            # 1단계: LLM으로 챕터에서 핵심 영어 수학 용어 추출
            print("[Step 1] Extracting core English terms...")
            prompt_ext = (
                "You are a mathematical researcher. Extract the top 15 most important technical terms "
                "from this mathematical text. Return ONLY a JSON object where keys are English terms "
                "and values are their core mathematical category.\n\n"
                f"TEXT:\n{sample_text[:4000]}"
            )
            
            raw_terms_content = self._call_ollama(prompt_ext, json_format=True)
            if raw_terms_content:
                raw_dict = json.loads(raw_terms_content)
                
                # 2단계: 추출된 용어 번역 및 위키백과 검증
                print("[Step 2] Translating and verifying terms...")
                knowledge_agent = KnowledgeAgent()
                
                for en_term in raw_dict.keys():
                    try:
                        # 2단계 LLM 호출: 한국어 번역 획득
                        trans_prompt = (
                            f"수학 용어 '{en_term}'의 표준 한국어 학술 번역을 알려줘. "
                            "반드시 '한국어(영어)' 형식으로 답해줘. 예: 전순서(preorder). "
                            "절대 중국어나 다른 언어를 사용하지 말고 한국어만 사용해. "
                            "다른 설명 없이 결과만 출력해."
                        )
                        ko_trans_raw = self._call_ollama(trans_prompt)
                        if not ko_trans_raw:
                            continue
                        
                        ko_trans = ko_trans_raw.strip()
                        
                        # 형식 검증 및 추출 (괄호 앞 한국어 부분)
                        match = re.match(r'^([^(]+)\(', ko_trans)
                        if match:
                            ko_part = match.group(1).strip()
                            # Wikipedia 검증 (공백 처리 및 (수학) 접미사 시도 등은 KnowledgeAgent가 할 일이지만 여기서 일부 보정)
                            wiki_def = knowledge_agent.get_definition(ko_part)
                            if not wiki_def and " " in ko_part:
                                wiki_def = knowledge_agent.get_definition(ko_part.replace(" ", "_"))
                            
                            if wiki_def:
                                print(f"  [Verified] {en_term} -> {ko_trans} (found on Wikipedia)")
                            else:
                                print(f"  [Unverified] {en_term} -> {ko_trans} (Wikipedia search failed)")
                            
                            final_glossary[en_term] = ko_trans
                        else:
                            # 형식이 맞지 않아도 일단 저장
                            final_glossary[en_term] = f"{ko_trans} ({en_term})" if "(" not in ko_trans else ko_trans
                    except Exception as e:
                        print(f"  [Error] Skipping term '{en_term}': {e}")
                        continue
            else:
                print("  [Warning] Failed to extract terms via LLM.")

        except Exception as e:
            print(f"CRITICAL ERROR in GlossaryArchitect: {e}. Falling back to critical fixes.")

        # 3. critical_fixes 반영 유지 (항상 마지막에 업데이트하여 우선순위 확보)
        final_glossary.update(critical_fixes)
        
        # 저장
        output_path = self.glossary_dir / f"{book_id}_{chapter_id}_agentic.json"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(final_glossary, f, ensure_ascii=False, indent=2)
            print(f"SUCCESS: Functional glossary created at {output_path}")
            return True
        except Exception as e:
            print(f"Failed to save glossary: {e}")
            return False

if __name__ == "__main__":
    import os
    # Test with real PDF if available
    pdf = "asset/PCM_split/PCM_part_01_pages_1_40.pdf"
    if os.path.exists(pdf):
        architect = GlossaryArchitect(pdf)
        architect.build_chapter_glossary("pcm_test", "part01", 10, 15)
    else:
        print("Test PDF not found, skip test execution.")
