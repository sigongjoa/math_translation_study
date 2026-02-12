import requests
import json
import re
import time
from typing import Dict, List, Optional
from tqdm import tqdm

# Physics Glossary for Vol I (English -> Korean)
PHYSICS_GLOSSARY = {
    "atom": "원자",
    "molecule": "분자",
    "particle": "입자",
    "matter": "물질",
    "motion": "운동",
    "heat": "열",
    "temperature": "온도",
    "pressure": "압력",
    "force": "힘",
    "energy": "에너지",
    "kinetic energy": "운동 에너지",
    "potential energy": "퍼텐셜 에너지",
    "conservation of energy": "에너지 보존",
    "gravity": "중력",
    "mass": "질량",
    "velocity": "속도",
    "acceleration": "가속도",
    "momentum": "운동량",
    "angular momentum": "각운동량",
    "quantum": "양자",
    "mechanics": "역학",
    "electromagnetic": "전자기",
    "oscillation": "진동",
    "wave": "파동",
    "liquid": "액체",
    "solid": "고체",
    "gas": "기체",
    "evaporation": "증발",
    "equilibrium": "평형",
    "symmetry": "대칭",
    "relativity": "상대성",
    "space-time": "시공간",
}

def strip_non_korean(text):
    import re
    cleaned = re.sub(r'[\u0600-\u06FF\u0750-\u077F]', '', text)
    cleaned = re.sub(r'[\u4E00-\u9FFF]', '', cleaned)
    cleaned = re.sub(r'[\u3040-\u309F\u30A0-\u30FF]', '', cleaned)
    cleaned = re.sub(r'[\u0400-\u04FF]', '', cleaned)
    cleaned = re.sub(r'[\u0E00-\u0E7F]', '', cleaned)
    return cleaned.strip()

class FeynmanTranslator:
    def __init__(self, model_name: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = f"{base_url}/api/chat"
        self.glossary = PHYSICS_GLOSSARY

    def _build_hint(self, text: str) -> str:
        hints = []
        text_lower = text.lower()
        for eng, kor in self.glossary.items():
            if eng in text_lower:
                hints.append(f"{eng} -> {kor}")
        return "\n".join(hints[:10])

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""

        glossary_hint = self._build_hint(text)
        system_prompt = (
            "You are translating Richard Feynman physics lectures into Korean.\n"
            "STYLE: Use polite Korean (해요체) with ~해요, ~죠, ~더라고요 endings. Preserve live lecture feel.\n"
            "RULES:\n"
            "1. Output ONLY the Korean translation. Nothing else.\n"
            "2. NO filler like Sure! or Here is the translation.\n"
            "3. Preserve all LaTeX math ($...$, $$...$$) exactly as-is.\n"
            "4. Use provided physics terminology.\n"
            + (f"\nPHYSICS GLOSSARY:\n{glossary_hint}" if glossary_hint else "")
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "If, in some cataclysm, all of scientific knowledge were to be destroyed, and only one sentence passed on to the next generation of creatures, what statement would contain the most information in the fewest words?"},
            {"role": "assistant", "content": "만약 어떤 대재앙으로 모든 과학 지식이 파괴되고, 단 한 문장만 다음 세대에게 전해진다면, 가장 적은 단어로 가장 많은 정보를 담은 문장은 무엇일까요?"},
            {"role": "user", "content": "All things are made of atoms—little particles that move around in perpetual motion, attracting each other when they are a little distance apart, but repelling upon being squeezed into one another."},
            {"role": "assistant", "content": "모든 것은 원자로 이루어져 있어요—영구적으로 움직이는 작은 입자들이죠. 서로 조금 떨어져 있으면 끌어당기고, 서로 밀착되면 반발해요."},
            {"role": "user", "content": "The $H_2O$ molecules are what we call water."},
            {"role": "assistant", "content": "$H_2O$ 분자가 바로 우리가 물이라고 부르는 거예요."},
            {"role": "user", "content": text}
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_k": 1,
                "top_p": 0.1,
                "num_predict": 4096,
            }
        }

        try:
            r = requests.post(self.base_url, json=payload, timeout=300)
            r.raise_for_status()
            result = r.json()["message"]["content"].strip()

            # Post-processing: Hemorrhage removal
            result = re.sub(r"^(이것은 번역입니다:?|번역:?|리처드 파인만 스타일 번역:?|Korean Translation:?|Translation:?)\s*", "", result, flags=re.IGNORECASE)
            result = result.strip('"' + "'")
            result = re.sub(r'^(물론이죠\!?\s*|물론이죠~\s*|당연하죠\!?\s*|알겠습니다\!?\s*)', '', result)
            result = re.sub(r'(궁금한 점이 있으면.*$|언제든지 물어봐주세요\!?.*$)', '', result, flags=re.MULTILINE)
            lines = result.strip().splitlines()
            cleaned = [l for l in lines if not re.match(r'^(물론이죠|당연하죠|알겠습니다|준비되었|시작해볼|오늘의 수업|오늘의 주제)', l.strip())]
            result = chr(10).join(cleaned)
            result = strip_non_korean(result)
            return result
        except Exception as e:
            return f"[TRANS ERROR: {e}]"

    def process_json(self, json_path, output_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"[LOG] Translating {data['chapter_title']}...")
        
        # Translate Chapter Title
        data["chapter_title_ko"] = self.translate(data["chapter_title"])
        
        for section in tqdm(data["sections"], desc="Sections"):
            section["title_ko"] = self.translate(section["title"])
            for item in tqdm(section["content"], desc="Items", leave=False):
                if item["type"] == "paragraph":
                    item["text_ko"] = self.translate(item["text"])
                elif item["type"] == "figure":
                    if item.get("caption"):
                        item["caption_ko"] = self.translate(item["caption"])

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Saved translated JSON to {output_path}")

if __name__ == "__main__":
    import os
    translator = FeynmanTranslator()
    
    # Process Chapter 1
    test_file = "feynman_json/I_01.json"
    if os.path.exists(test_file):
        if not os.path.exists("feynman_translated"):
            os.makedirs("feynman_translated")
        translator.process_json(test_file, "feynman_translated/I_01_translated.json")
