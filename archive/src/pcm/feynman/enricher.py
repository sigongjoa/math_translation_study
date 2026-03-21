import json
import os
import requests
import re
from tqdm import tqdm

class FeynmanEnricher:
    def __init__(self, model_name: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = f"{base_url}/api/generate"

    def clean_filler(self, text: str) -> str:
        """Remove LLM conversational filler."""
        if not text: return ""
        text = re.sub(r"^(물론이죠\!?\s*|당연하죠\!?\s*|알겠습니다\!?\s*|준비되었나요\?\s*|시작해볼게요\!?\s*|번역해드릴게요:?\s*|다음은.*?입니다:?\s*|이것은.*?입니다:?\s*)", "", text, flags=re.IGNORECASE)
        lines = text.strip().splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^(물론이죠|당연하죠|알겠습니다|준비되었|시작해볼|오늘의 수업|오늘의 주제|궁금한 점|언제든지 물어)", stripped):
                continue
            cleaned.append(line)
        text = "\n".join(cleaned).strip()
        # For titles, take only first meaningful line
        return text

    def enrich_item(self, item: dict) -> dict:
        """
        Ask LLM if this paragraph should be a special box or if we should add a note.
        """
        if item["type"] == "figure":
            item["caption_ko"] = self.clean_filler(item.get("caption_ko", ""))
            return item
            
        if item["type"] != "paragraph":
            return item

        text_ko = item.get("text_ko", "")
        text_en = item.get("text", "")
        if not text_ko:
            return item

        prompt = f"""You are a senior physics editor for a luxury edition of the Feynman Lectures.
Your goal is to inject "Premium Metadata" (Notes, Quotes, Deep Dives) to make the book feel like a high-end lecture companion.

PARAGRAPH (Korean): "{text_ko}"
PARAGRAPH (Original English): "{text_en}"

ASSIGN ONE CATEGORY AND GENERATE METADATA IF APPLICABLE:

1. "feynmansays": If the text contains a profound, core philosophical point or a witty Feynman-esque insight.
   - Example insight: "Nature has a great simplicity and therefore a great beauty."
   - Content: The core quote (can be slightly polished for impact).

2. "translatornote": If the text mentions historical figures (Dirac, Newton), specific dates, or complex terminology that a Korean reader might need context for.
   - Content: A helpful, academic yet friendly note.

3. "deepresearch": If the text mentions a concept (Atoms, Pressure, Entropy, Quarks, Heat) that deserves a detailed technical side-bar.
   - Title: A catchy title for the sidebar.
   - Content: 2-3 sentences of advanced technical or historical context.

4. "keyconcept": If the paragraph defines a major law of physics.
   - Title: The name of the concept.

5. "normal": Most paragraphs should be normal.

Output ONLY a JSON object:
{{
  "category": "feynmansays" | "translatornote" | "deepresearch" | "keyconcept" | "normal",
  "title": "required if deepresearch or keyconcept, else null",
  "extra": "the generated note/research/concept text, else null"
}}
"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.5}
        }

        try:
            r = requests.post(self.base_url, json=payload, timeout=60)
            res = r.json().get("response", "{}")
            enrichment = json.loads(res)
            
            cat = enrichment.get("category")
            if cat == "feynmansays":
                item["box_type"] = "feynmansays"
            elif cat == "translatornote" and enrichment.get("extra"):
                item["sub_items"] = [{"type": "translatornote", "text": enrichment["extra"]}]
            elif cat == "deepresearch" and enrichment.get("extra"):
                item["sub_items"] = [{"type": "deepresearch", "title": enrichment.get("title") or "심층 해설", "text": enrichment["extra"]}]
            elif cat == "keyconcept" and enrichment.get("extra"):
                 item["sub_items"] = [{"type": "deepresearch", "title": enrichment.get("title") or "핵심 개념", "text": enrichment["extra"]}]
            
            return item
        except Exception as e:
            print(f"[WARN] Enrichment failed for item: {e}")
            return item

    def process_json(self, json_path, output_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"[LOG] Enriching {data['chapter_title']}...")
        
        # Clean Chapter Title
        data["chapter_title_ko"] = self.clean_filler(data.get("chapter_title_ko") or data.get("chapter_title"))
        
        for section in tqdm(data["sections"], desc="Enriching Sections"):
            # Clean Section Title
            section["title_ko"] = self.clean_filler(section.get("title_ko") or section.get("title"))
            
            enriched_content = []
            for item in tqdm(section["content"], desc="Items", leave=False):
                item = self.enrich_item(item)
                enriched_content.append(item)
            
            section["content"] = enriched_content
            # Periodic save
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[LOG] Saved section progress to {output_path}")

        print(f"[OK] Completed enrichment! Saved to {output_path}")

if __name__ == "__main__":
    enricher = FeynmanEnricher()
    if not os.path.exists("feynman_translated"):
        os.makedirs("feynman_translated")
    enricher.process_json("feynman_translated/I_01_translated.json", "feynman_translated/I_01_enriched.json")
