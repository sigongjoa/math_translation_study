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

    # ── 4. Escape special chars (outside math mode) ──
    text = _escape_outside_math(text)

    # ── 5. Clean artifacts ──
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)

    return text.strip()


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
    # Don't escape _ and ^ as they might be intentional math
    # Only escape isolated ones not near letters/digits
    text = re.sub(r'(?<![a-zA-Z0-9\\])_(?![a-zA-Z0-9{])', '\\_', text)

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
\XeTeXlinebreakskip 0pt plus 1pt
\emergencystretch 3em

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


def generate_section_latex(section_data: Dict) -> str:
    """Generate LaTeX for a single section with supplements."""
    sec_id = section_data.get("section_id", "")
    title_kr = section_data.get("title_translated", "")
    title_en = section_data.get("title_original", "")
    content = section_data.get("content_translated", "")
    level = section_data.get("level", "subsection")
    font_size = section_data.get("font_size", 8.1)
    supplements = section_data.get("supplements", {})

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
