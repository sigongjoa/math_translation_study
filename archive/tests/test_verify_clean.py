#!/usr/bin/env python3
"""
Clean test: generate LaTeX with verification boxes only (no supplements).
Strips problematic content to ensure clean PDF compilation.
"""

import sys
import json
import re
import subprocess
import shutil
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

SECTIONS_DIR = Path("output_test/sections")
LATEX_DIR = Path("output_test/latex_clean")


def clean_title(title: str) -> str:
    """Ensure title is a single line with no LaTeX-breaking chars."""
    if not title:
        return "제목 없음"
    # Take only first line
    title = title.split('\n')[0].strip()
    # Remove LaTeX special chars from title
    for ch in ['\\', '{', '}', '$', '&', '%', '#', '_', '^', '~']:
        title = title.replace(ch, '')
    return title[:80] if title else "제목 없음"


def render_verification(verification: dict) -> str:
    """Render verification box."""
    if not verification or verification.get("skipped"):
        return ""
    score = verification.get("score", 0)
    label = "우수" if score >= 90 else "양호" if score >= 70 else "주의" if score >= 50 else "경고"
    modules = []
    for mod_name, mod_label in [("formula", "수식"), ("semantic", "의미"),
                                 ("logic", "논리"), ("research", "검증")]:
        mod = verification.get(mod_name, {})
        if not mod.get("skipped"):
            ms = mod.get("score", "-")
            ic = len(mod.get("issues", [])) + len(mod.get("flagged", []))
            modules.append(f"{mod_label} {ms}" + (f" ({ic}건)" if ic else ""))
    modules_str = " \\quad ".join(modules)
    return f"""
\\begin{{verificationbox}}
\\textbf{{종합 점수: {score}/100 ({label})}} \\\\[2pt]
{{\\small {modules_str}}}
\\end{{verificationbox}}
\\vspace{{6pt}}
"""


def render_enrichments(enrichments: list) -> str:
    """Render deep research enrichment entries as educational content boxes."""
    if not enrichments:
        return ""
    from pcm.core.json_to_latex import clean_for_latex
    parts = []
    parts.append("\n\\vspace{8pt}\n{\\large\\textbf{\\textsf{심층 해설 (Deep Research)}}}\n\\vspace{4pt}\n")
    for entry in enrichments:
        title_ko = clean_for_latex(entry.get("title_ko", entry.get("term", "")))
        explanation = clean_for_latex(entry.get("explanation", ""))
        source = entry.get("source", "")
        if not explanation:
            continue
        source_line = ""
        if source:
            source_escaped = clean_for_latex(source)
            source_line = f"\n\\vspace{{2pt}}\n{{\\scriptsize \\textit{{출처: Wikipedia --- {source_escaped}}}}}"
        parts.append(f"""
\\begin{{researchbox}}[{title_ko}]
{explanation}{source_line}
\\end{{researchbox}}
\\vspace{{4pt}}
""")
    return "\n".join(parts)


def main():
    LATEX_DIR.mkdir(parents=True, exist_ok=True)

    # Load sections
    json_files = sorted(SECTIONS_DIR.glob("*.json"))
    sections = []
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            sections.append(json.load(f))

    sections.sort(key=lambda s: [int(x) if x.isdigit() else x
                                  for x in re.split(r'[._]', s.get('section_id', '0'))])

    print(f"Loaded {len(sections)} sections")

    # Build LaTeX
    from pcm.core.json_to_latex import generate_preamble, clean_for_latex

    preamble = generate_preamble()
    body = []
    body.append(r"\begin{document}")
    body.append(r"""
\begin{titlepage}
\centering
\vspace*{3cm}
{\sffamily\bfseries\Huge 프린스턴 수학 안내서\par}
\vspace{1cm}
{\sffamily\Large The Princeton Companion to Mathematics\par}
\vspace{2cm}
{\large 번역 검증 테스트\par}
\vfill
{\small 번역: AI 보조 번역 시스템\par}
\end{titlepage}
""")
    body.append(r"\tableofcontents")
    body.append(r"\newpage")
    body.append(r"\part{제 I 부: 소개}")

    for section in sections:
        sid = section.get("section_id", "")
        title_kr = clean_title(section.get("title_translated", ""))
        title_en = section.get("title_original", "")
        content = section.get("content_translated", "")
        verification = section.get("verification", {})
        enrichments = section.get("enrichments", [])

        # Determine heading level
        if section.get("font_size", 8.1) >= 9.0:
            heading = f"\\chapter{{{title_kr}}}"
        elif '.' in sid and sid.count('.') == 1:
            heading = f"\\section{{{title_kr}}}"
        else:
            heading = f"\\subsection{{{title_kr}}}"

        # Clean body (simplified - just escape the worst offenders)
        body_text = clean_for_latex(content) if content else ""

        # Verification box
        verify_tex = render_verification(verification)

        # Enrichment boxes
        enrich_tex = render_enrichments(enrichments)

        body.append(f"""
% ═══ Section {sid} ═══
{heading}
\\label{{sec:{sid.replace('.', '-')}}}

{body_text}

{enrich_tex}
{verify_tex}
""")

    body.append(r"\end{document}")

    full_doc = preamble + "\n".join(body)

    tex_file = LATEX_DIR / "main.tex"
    with open(tex_file, "w", encoding="utf-8") as f:
        f.write(full_doc)
    print(f"LaTeX written to {tex_file}")

    # Compile
    print("Compiling PDF...")
    for run in range(2):
        label = "1st pass" if run == 0 else "2nd pass (TOC)"
        print(f"  XeLaTeX {label}...")
        result = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            cwd=str(LATEX_DIR),
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            print(f"  XeLaTeX returned {result.returncode}")
            # Show last errors
            for line in result.stdout.split('\n')[-15:]:
                if line.strip():
                    print(f"    {line}")
            if run == 0:
                # Try without halt-on-error for 2nd attempt
                print("  Retrying without -halt-on-error...")
                result = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "main.tex"],
                    cwd=str(LATEX_DIR),
                    capture_output=True, text=True, timeout=180,
                )
            break

    pdf_file = LATEX_DIR / "main.pdf"
    if pdf_file.exists():
        final_pdf = Path("output_test") / "translated_verified.pdf"
        shutil.copy2(pdf_file, final_pdf)
        size_kb = final_pdf.stat().st_size / 1024
        print(f"\nPDF generated: {final_pdf} ({size_kb:.0f} KB)")
    else:
        print("PDF not generated. Check log.")
        log = LATEX_DIR / "main.log"
        if log.exists():
            with open(log) as f:
                lines = f.readlines()
            for line in lines[-30:]:
                print(f"  {line.rstrip()}")


if __name__ == "__main__":
    main()
