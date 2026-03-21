---
name: parse-pdf
description: Parse a PDF file into structured sections JSON. Use when starting a new translation project to extract text blocks, headings, definitions, theorems, and other structural elements from a technical/academic PDF.
---

# parse-pdf

Extracts structured content from a PDF and saves to `workspace/sections.json`.

## Usage

```
/parse-pdf <pdf_path> [--pages START-END] [--workspace <dir>]
```

**Examples:**
```
/parse-pdf princeton.pdf --pages 1-50
/parse-pdf arxiv_paper.pdf
/parse-pdf textbook.pdf --pages 100-150 --workspace workspace/ch5
```

## Steps

1. Run the parser script:
   ```bash
   python skills/parse-pdf/scripts/pdf_parser.py "<pdf_path>" [--pages START-END] [--output workspace/sections.json]
   ```

2. If `--pages` is not specified, parse pages 1-20 as a preview and ask the user to confirm the range.

3. Report the results:
   - Total sections extracted
   - Breakdown by type (text, section, definition, theorem, etc.)
   - Show 3 example sections as preview
   - Flag any parsing issues (e.g., garbled text, likely scanned image pages)

4. If the output looks wrong (e.g., all text in one block, no structure detected), suggest alternatives:
   - Try a different page range
   - Warn if the PDF appears to be a scanned image (no text layer)

## Output: `workspace/sections.json`

```json
{
  "source_pdf": "princeton.pdf",
  "pages": "1-50",
  "extracted_at": "2026-03-21T10:00:00",
  "sections": [
    {
      "id": "p001_s001",
      "page": 1,
      "type": "section",
      "label": "",
      "content": "1.1 Introduction to Category Theory"
    },
    {
      "id": "p001_s002",
      "page": 1,
      "type": "definition",
      "label": "Definition 1.1",
      "content": "A category C consists of a collection of objects..."
    },
    {
      "id": "p001_s003",
      "page": 1,
      "type": "text",
      "label": "",
      "content": "The notion of a category was introduced by..."
    }
  ]
}
```

**Block types:**
| type | description |
|------|-------------|
| `section` | Chapter/section heading (e.g., "1.2 Functors") |
| `subsection` | Subsection heading |
| `definition` | Formal definition block |
| `theorem` | Theorem statement |
| `lemma` | Lemma statement |
| `corollary` | Corollary |
| `proof` | Proof block |
| `example` | Worked example |
| `remark` | Remark or note |
| `text` | Regular prose |

## Next Step

After parsing, run `/build-glossary` to extract domain terminology.
