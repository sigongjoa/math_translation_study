---
name: build-glossary
description: Extract technical terms from sections.json and create a Korean glossary file. Use after /parse-pdf and before /translate-section. Also use when you want to review or fix terminology before translation.
---

# build-glossary

Reads `workspace/sections.json`, identifies domain-specific technical terms, and creates `workspace/glossary.json` with Korean translations.

## Usage

```
/build-glossary [--domain mathematics|physics|cs|biology|economics|engineering] [--workspace <dir>]
```

**Examples:**
```
/build-glossary --domain mathematics
/build-glossary --domain cs
/build-glossary --workspace workspace/ch5 --domain physics
```

## Steps

1. Read `workspace/sections.json` (required — run `/parse-pdf` first if missing).

2. Scan all section content. Identify technical/domain-specific terms:
   - Nouns that are specific to the domain
   - Named theorems, lemmas, conjectures (e.g., "Zorn's Lemma", "Cauchy-Schwarz")
   - Technical jargon unlikely to be known to a general Korean reader

3. For each identified term, determine the best Korean translation using these rules:

   **Mathematics:**
   - Use established Korean mathematical terminology (대한수학회 용어집 기준)
   - functor → 함자, morphism → 사상, category → 범주, manifold → 다양체
   - group → 군, ring → 환, field → 체, module → 가군
   - isomorphism → 동형사상, homomorphism → 준동형사상
   - topology → 위상수학 (field) or 위상 (structure)

   **Computer Science:**
   - Use transliteration for widely-used English terms: algorithm → 알고리즘, tensor → 텐서
   - But translate conceptual terms: graph → 그래프, tree → 트리

   **General Rule:**
   - If a standard Korean term exists and is used in Korean textbooks → use it
   - If no standard term exists → transliteration in 한글
   - Never mix: pick one and apply consistently

4. Save `workspace/glossary.json`.

5. Report: N terms extracted. Print the full list for review.

6. Ask: "수정할 용어가 있으면 glossary.json을 직접 편집하세요. 번역을 시작할까요?"

## Output: `workspace/glossary.json`

```json
{
  "domain": "mathematics",
  "source_pdf": "princeton.pdf",
  "terms": {
    "functor":        { "ko": "함자",       "note": "범주 사이의 구조 보존 사상" },
    "morphism":       { "ko": "사상",       "note": "대상 사이의 구조 보존 함수" },
    "category":       { "ko": "범주",       "note": "" },
    "isomorphism":    { "ko": "동형사상",   "note": "" },
    "homomorphism":   { "ko": "준동형사상", "note": "" },
    "endomorphism":   { "ko": "자기준동형사상", "note": "" },
    "automorphism":   { "ko": "자기동형사상",   "note": "" }
  }
}
```

## Editing the Glossary

Edit `workspace/glossary.json` directly to:
- Fix wrong translations
- Add terms the extractor missed
- Add context notes

The glossary is injected into every translation call, so accuracy here directly affects output quality.

## Next Step

Run `/translate-section --page 1` to begin translation.
