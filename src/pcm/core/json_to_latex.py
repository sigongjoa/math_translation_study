#!/usr/bin/env python3
"""
Convert translated JSON sections to LaTeX files for XeLaTeX compilation.
Handles markdown artifacts, math notation, and supplement materials.
"""

import json
import re
from pathlib import Path
from typing import Dict, List


def clean_for_latex(text: str) -> str:
    """Clean translated text and convert to proper LaTeX."""
    if not text:
        return ""

    # ── 1. Convert markdown → LaTeX (before escaping) ──
    # Bold: **text** → \textbf{text}
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)
    # Italic: *text* → \textit{text}
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\\textit{\1}', text)
    # Bullet lists: wrap consecutive bullet items in itemize
    text = _wrap_bullet_lists(text)
    # Headers: ## text → \paragraph{text}
    text = re.sub(r'^\s*#{1,3}\s+(.+)$', r'\\paragraph{\1}', text, flags=re.MULTILINE)

    # ── 2. Convert HTML → LaTeX ──
    text = re.sub(r'<sup>(.*?)</sup>', r'\\textsuperscript{\1}', text)
    text = re.sub(r'<sub>(.*?)</sub>', r'\\textsubscript{\1}', text)
    text = re.sub(r'<br\s*/?>', r'\\\\', text)
    text = re.sub(r'<[^>]+>', '', text)  # remove remaining HTML

    # ── 3. Fix math notation ──
    # $$ ... $$ → \[ ... \] (display math)
    text = re.sub(r'\$\$(.+?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)

    # ── 4. Wrap bare math-like patterns in $ $ (before escaping) ──
    text = _wrap_bare_math(text)

    # ── 5. Escape special chars (outside math mode) ──
    text = _escape_outside_math(text)

    # ── 6. Insert line-break opportunities at CJK↔Latin boundaries ──
    text = _insert_cjk_breaks(text)

    # ── 7. Clean artifacts ──
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def _wrap_bare_math(text: str) -> str:
    """Wrap bare math-like expressions (outside existing $...$) in inline math.
    Targets patterns like a_1, x^2, R^n that would break LaTeX if left bare."""
    if not text:
        return text

    # Split on existing math regions to avoid double-wrapping
    math_pattern = r'(\$[^$]+?\$|\\\(.+?\\\)|\\\[.+?\\\])'
    parts = re.split(math_pattern, text, flags=re.DOTALL)

    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside existing math — keep as-is
            result.append(part)
        else:
            # Outside math — wrap bare subscript/superscript patterns
            # Pattern: letter(s)_something or letter(s)^something
            # e.g., a_1, a_{ij}, R^n, R^{24}, x^2
            part = re.sub(
                r'(?<!\$)(?<![\\a-zA-Z])([a-zA-Z][a-zA-Z0-9]*)([_^])(\{[^}]+\}|[a-zA-Z0-9]+)(?!\$)',
                r'$\1\2\3$', part
            )

            # Pattern: letter^(expr) — e.g., e^(2πiz), x^(a+b), 2^(5/7)
            part = re.sub(
                r'(?<!\$)([a-zA-Z0-9])[\^][\(]([^)]+)[\)]',
                r'$\1^{\2}$', part
            )

            # Pattern: letter ^ number.number — e.g., r ^1.4
            part = re.sub(
                r'(?<!\$)([a-zA-Z])\s*\^\s*([0-9]+\.?[0-9]*)(?!\$)',
                r'$\1^{\2}$', part
            )

            result.append(part)

    return ''.join(result)


def _insert_cjk_breaks(text: str) -> str:
    """Insert spaces at CJK↔Latin/digit boundaries for proper line breaking.
    Also breaks up long runs of CJK without spaces (poor LLM spacing)."""
    if not text:
        return text

    # CJK Unicode ranges (Korean Syllables + CJK Unified)
    CJK = r'[\uac00-\ud7af\u4e00-\u9fff\u3400-\u4dbf]'
    LATIN = r'[a-zA-Z0-9]'

    # Insert thin space at CJK→Latin boundary (e.g., "한글word" → "한글 word")
    text = re.sub(f'({CJK})({LATIN})', r'\1 \2', text)
    # Insert thin space at Latin→CJK boundary (e.g., "word한글" → "word 한글")
    text = re.sub(f'({LATIN})({CJK})', r'\1 \2', text)

    # Break long CJK runs (>12 chars without space) by inserting
    # zero-width break points every ~10 chars. This gives LaTeX
    # line-break opportunities without visible spacing changes.
    ZWSP = r'\hspace{0pt}'  # zero-width space = invisible break point

    def _break_long_cjk(match):
        run = match.group(0)
        if len(run) <= 12:
            return run
        # Insert break point every 10 characters
        parts = []
        for i in range(0, len(run), 10):
            parts.append(run[i:i+10])
        return ZWSP.join(parts)

    text = re.sub(f'[{chr(0xac00)}-{chr(0xd7af)}]{{10,}}', _break_long_cjk, text)

    # Prevent double spaces
    text = re.sub(r'  +', ' ', text)

    return text


def _wrap_bullet_lists(text: str) -> str:
    """Convert markdown bullets to LaTeX itemize environments."""
    lines = text.split('\n')
    result = []
    in_list = False

    for line in lines:
        is_bullet = bool(re.match(r'^\s*[*\-]\s+', line))
        if is_bullet:
            if not in_list:
                result.append('\\begin{itemize}')
                in_list = True
            item_text = re.sub(r'^\s*[*\-]\s+', '', line)
            result.append(f'\\item {item_text}')
        else:
            if in_list:
                result.append('\\end{itemize}')
                in_list = False
            result.append(line)

    if in_list:
        result.append('\\end{itemize}')

    return '\n'.join(result)


def _escape_outside_math(text: str) -> str:
    """Escape LaTeX special chars only outside of math delimiters."""
    # Split on math regions: $...$, \(...\), \[...\]
    pattern = r'(\$[^$]+\$|\\\(.+?\\\)|\\\[.+?\\\])'
    parts = re.split(pattern, text, flags=re.DOTALL)

    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside math - keep as-is
            result.append(part)
        else:
            # Outside math - escape special chars
            # But preserve already-converted LaTeX commands
            part = _safe_escape(part)
            result.append(part)
    return ''.join(result)


def _safe_escape(text: str) -> str:
    """Escape LaTeX specials while preserving existing LaTeX commands."""
    # Temporarily protect existing LaTeX commands
    protected = {}
    counter = [0]

    def protect(match):
        key = f"@@PROT{counter[0]}@@"
        protected[key] = match.group(0)
        counter[0] += 1
        return key

    # Protect \textbf{}, \textit{}, \textsuperscript{}, etc.
    text = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', protect, text)
    # Protect \\ (line breaks)
    text = re.sub(r'\\\\', protect, text)
    # Protect \item
    text = re.sub(r'\\item\b', protect, text)
    # Protect \paragraph{...}
    text = re.sub(r'\\paragraph\{[^}]*\}', protect, text)

    # Now escape
    text = text.replace('&', '\\&')
    text = text.replace('%', '\\%')
    text = text.replace('#', '\\#')
    # Escape ALL remaining bare _ and ^ outside math mode
    # (_wrap_bare_math already converted valid math patterns like a_1 → $a_1$)
    text = text.replace('_', '\\_')
    text = text.replace('^', '\\^{}')

    # Restore protected
    for key, val in protected.items():
        text = text.replace(key, val)

    return text


def generate_preamble() -> str:
    """Generate the LaTeX preamble."""
    return r"""\documentclass[10.5pt, a4paper, twoside, openany]{book}

% ─── 여백 ───
\usepackage[
  top=25mm,
  bottom=20mm,
  inner=30mm,
  outer=25mm,
  bindingoffset=5mm,
  headheight=14pt,
  headsep=12pt
]{geometry}

% ─── 한글 ───
\usepackage{kotex}
\usepackage{fontspec}

% ─── 폰트 ───
\setmainfont{Noto Serif CJK KR}[
  UprightFont={Noto Serif CJK KR},
  BoldFont={Noto Serif CJK KR Bold},
  Ligatures=TeX,
]
\setsansfont{Noto Sans CJK KR}[
  UprightFont={Noto Sans CJK KR},
  BoldFont={Noto Sans CJK KR Bold},
  Ligatures=TeX,
]
\setmonofont{Noto Sans Mono CJK KR}[Scale=0.85]

% ─── 수식 ───
\usepackage{amsmath, amssymb, amsthm}

% ─── 그래픽 ───
\usepackage{graphicx}
\usepackage{tikz}
\usetikzlibrary{arrows.meta, positioning, shapes, calc, decorations.pathreplacing}

% ─── 한글 줄바꿈 및 여백 최적화 ───
\XeTeXlinebreaklocale "ko"
\XeTeXlinebreakskip 0pt plus 3pt
\emergencystretch 5em
\tolerance=2000
\hyphenpenalty=50
\exhyphenpenalty=50
\doublehyphendemerits=10000
\finalhyphendemerits=5000
\setlength{\hfuzz}{2pt}

% ─── 행간 ───
\linespread{1.52}

% ─── 단락 ───
\setlength{\parindent}{1em}
\setlength{\parskip}{0pt}

% ─── 헤더/푸터 ───
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{{\small\sffamily\leftmark \hfill \thepage}}
\fancyhead[RO]{{\small\sffamily\thepage \hfill \rightmark}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}

\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\small\thepage}
  \renewcommand{\headrulewidth}{0pt}
}

% ─── 제목 스타일 ───
\usepackage{titlesec}

\titleformat{\chapter}[hang]
  {\sffamily\bfseries\LARGE}
  {\thechapter}{12pt}{}
  [\vspace{2pt}{\titlerule[0.8pt]}]
\titlespacing*{\chapter}{0pt}{-10pt}{24pt}

\titleformat{\section}[hang]
  {\sffamily\bfseries\Large}
  {\thesection}{8pt}{}
\titlespacing*{\section}{0pt}{20pt}{8pt}

\titleformat{\subsection}[hang]
  {\sffamily\bfseries\normalsize}
  {\thesubsection}{6pt}{}
\titlespacing*{\subsection}{0pt}{14pt}{6pt}

% ─── 보충 자료 박스 ───
\usepackage[most]{tcolorbox}

% 핵심 요약 박스
\newtcolorbox{summarybox}{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  title={\small 핵심 요약},
  breakable, sharp corners,
  boxrule=0.5pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}

% 예시 박스
\newtcolorbox{examplebox}[1][]{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  title={\small #1},
  breakable, sharp corners,
  boxrule=0.4pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}

% 연습 문제 박스
\newtcolorbox{exercisebox}{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  title={\small 연습 문제},
  breakable, sharp corners,
  boxrule=0.5pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}

% 용어 정리 박스
\newtcolorbox{glossarybox}{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  title={\small 용어 정리},
  breakable, sharp corners,
  boxrule=0.4pt,
  left=8pt, right=8pt, top=4pt, bottom=4pt
}

% 정의/정리 박스
\newtcolorbox{definitionbox}[1][]{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  title=#1,
  breakable, sharp corners,
  boxrule=0.5pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}

% 검증 리포트 박스
\newtcolorbox{verificationbox}{
  colback=white, colframe=black!60,
  fonttitle=\sffamily\bfseries,
  title={\small 번역 검증},
  breakable, sharp corners,
  boxrule=0.3pt,
  left=8pt, right=8pt, top=4pt, bottom=4pt
}

% 딥리서치 교육 콘텐츠 박스
\newtcolorbox{researchbox}[1][]{
  colback=blue!3!white, colframe=blue!40!black,
  fonttitle=\sffamily\bfseries,
  title={#1},
  breakable, sharp corners,
  boxrule=0.5pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}

% ─── 교차참조 ───
\usepackage{hyperref}
\hypersetup{
  colorlinks=false,
  pdfborder={0 0 0},
  bookmarksnumbered=true,
}

% ─── 목차 설정 ───
\setcounter{tocdepth}{2}

% ─── 열거 ───
\usepackage{enumitem}
"""


def _render_verification_report(verification: Dict) -> str:
    """Render verification report as a compact LaTeX box."""
    if not verification or verification.get("skipped"):
        return ""

    score = verification.get("score", 0)

    # Score label
    if score >= 90:
        label = "우수"
    elif score >= 70:
        label = "양호"
    elif score >= 50:
        label = "주의"
    else:
        label = "경고"

    # Module scores line
    modules = []
    for mod_name, mod_label in [("formula", "수식"), ("semantic", "의미"),
                                 ("logic", "논리"), ("research", "검증")]:
        mod = verification.get(mod_name, {})
        if not mod.get("skipped"):
            mod_score = mod.get("score", "-")
            issue_count = len(mod.get("issues", [])) + len(mod.get("flagged", []))
            if issue_count > 0:
                modules.append(f"{mod_label} {mod_score} ({issue_count}건)")
            else:
                modules.append(f"{mod_label} {mod_score}")

    modules_str = " \\quad ".join(modules)

    return f"""
\\begin{{verificationbox}}
\\textbf{{종합 점수: {score}/100 ({label})}} \\\\[2pt]
{{\\small {modules_str}}}
\\end{{verificationbox}}
\\vspace{{4pt}}
"""


def _render_enrichments(enrichments: List[Dict]) -> str:
    """Render deep research enrichment entries as educational content boxes."""
    if not enrichments:
        return ""

    latex_parts = []
    latex_parts.append("\n\\vspace{8pt}\n{\\large\\textbf{\\textsf{심층 해설 (Deep Research)}}}\n\\vspace{4pt}\n")

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

        latex_parts.append(f"""
\\begin{{researchbox}}[{title_ko}]
{explanation}{source_line}
\\end{{researchbox}}
\\vspace{{4pt}}
""")

    return "\n".join(latex_parts)


def generate_section_latex(section_data: Dict) -> str:
    """Generate LaTeX for a single section with supplements."""
    sec_id = section_data.get("section_id", "")
    title_kr = section_data.get("title_translated", "")
    title_en = section_data.get("title_original", "")
    content = section_data.get("content_translated", "")
    level = section_data.get("level", "subsection")
    font_size = section_data.get("font_size", 8.1)
    supplements = section_data.get("supplements", {})
    verification = section_data.get("verification", {})
    enrichments = section_data.get("enrichments", [])

    if not title_kr:
        title_kr = title_en

    # Heading level
    if font_size >= 9.0 or level == "section":
        heading = f"\\chapter{{{title_kr}}}"
    elif '.' in sec_id and sec_id.count('.') == 1:
        heading = f"\\section{{{title_kr}}}"
    else:
        heading = f"\\subsection{{{title_kr}}}"

    # Main body
    body = clean_for_latex(content)

    # Verification report (if present)
    verify_latex = _render_verification_report(verification)

    # Deep research enrichment content
    enrich_latex = _render_enrichments(enrichments)

    # Build supplement blocks
    supp_latex = ""

    if supplements.get("summary"):
        supp_latex += f"""
\\begin{{summarybox}}
{clean_for_latex(supplements['summary'])}
\\end{{summarybox}}
\\vspace{{8pt}}
"""

    if supplements.get("tikz_diagram"):
        tikz_code = supplements["tikz_diagram"]
        # TikZ code should be raw LaTeX, not escaped
        # Wrap in resizebox to prevent overflow
        supp_latex += f"""
\\begin{{center}}
\\resizebox{{\\textwidth}}{{!}}{{{tikz_code}}}
\\end{{center}}
\\vspace{{8pt}}
"""

    if supplements.get("examples"):
        for i, ex in enumerate(supplements["examples"], 1):
            supp_latex += f"""
\\begin{{examplebox}}[예시 {i}]
{clean_for_latex(ex)}
\\end{{examplebox}}
\\vspace{{4pt}}
"""

    if supplements.get("exercises"):
        exercises_text = ""
        for i, ex in enumerate(supplements["exercises"], 1):
            exercises_text += f"\\textbf{{{i}.}} {clean_for_latex(ex)}\\\\[4pt]\n"
        supp_latex += f"""
\\begin{{exercisebox}}
{exercises_text}
\\end{{exercisebox}}
\\vspace{{4pt}}
"""

    if supplements.get("glossary"):
        glossary_items = supplements["glossary"]
        rows = " \\\\\n".join([f"\\textbf{{{eng}}} --- {kor}" for eng, kor in glossary_items])
        supp_latex += f"""
\\begin{{glossarybox}}
{rows}
\\end{{glossarybox}}
"""

    if supplements.get("solutions"):
        supp_latex += f"""
\\paragraph{{풀이}}
{clean_for_latex(supplements['solutions'])}
"""

    return f"""
% ═══ Section {sec_id}: {title_en} ═══
{heading}
\\label{{sec:{sec_id.replace('.', '-')}}}

{body}

{enrich_latex}
{verify_latex}
{supp_latex}
"""


def generate_full_document(sections_dir: str, output_tex: str, part_label: str = "I"):
    """Generate a complete LaTeX document from translated JSON files."""
    sections_path = Path(sections_dir)
    json_files = sorted(sections_path.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {sections_dir}")
        return

    print(f"Found {len(json_files)} sections")

    sections = []
    for jf in json_files:
        with open(jf, 'r', encoding='utf-8') as f:
            sections.append(json.load(f))

    sections.sort(key=lambda s: [int(x) if x.isdigit() else x
                                  for x in re.split(r'[._]', s.get('section_id', '0'))])

    preamble = generate_preamble()

    body_parts = []
    body_parts.append(r"\begin{document}")
    body_parts.append("")

    # Title page
    body_parts.append(r"""
\begin{titlepage}
\centering
\vspace*{3cm}
{\sffamily\bfseries\Huge 프린스턴 수학 안내서\par}
\vspace{1cm}
{\sffamily\Large The Princeton Companion to Mathematics\par}
\vspace{2cm}
{\large 한국어 번역본\par}
\vspace{1cm}
{\normalsize Timothy Gowers 편저\par}
\vfill
{\small 번역: AI 보조 번역 시스템\par}
\end{titlepage}
""")

    body_parts.append(r"\tableofcontents")
    body_parts.append(r"\newpage")
    body_parts.append("")
    body_parts.append(f"\\part{{제 {part_label} 부: 소개}}")
    body_parts.append("")

    for section in sections:
        latex = generate_section_latex(section)
        body_parts.append(latex)

    body_parts.append(r"\end{document}")

    full_doc = preamble + "\n".join(body_parts)

    output_path = Path(output_tex)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_doc)

    print(f"LaTeX document written to {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert translated JSON to LaTeX")
    parser.add_argument("--sections-dir", default="output/sections")
    parser.add_argument("--output", default="latex/main.tex")
    parser.add_argument("--part", default="I")
    args = parser.parse_args()
    generate_full_document(args.sections_dir, args.output, args.part)


if __name__ == "__main__":
    main()
