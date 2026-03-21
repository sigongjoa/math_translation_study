#set document(title: "Seven Sketches 번역 파이프라인 테스트 리포트")
#set page(margin: 2cm, numbering: "1")
#set text(font: "Noto Sans CJK KR", size: 10pt)
#set heading(numbering: "1.1")

#align(center)[
  #text(size: 20pt, weight: "bold")[Seven Sketches 번역 파이프라인]
  #v(0.3em)
  #text(size: 14pt)[100페이지 파이프라인 테스트 리포트]
  #v(0.3em)
  #text(size: 10pt, fill: gray)[2026-02-18 | /sc:duo 자동 생성]
]

#line(length: 100%)

= 작업 요약

"Seven Sketches in Compositionality: An Invitation to Applied Category Theory" (Brendan Fong & David I. Spivak) PDF의 첫 100페이지를 한국어로 번역하는 파이프라인을 구축하고 실행했다.

*파이프라인 구조:*
```
PDF Parse → Diagram Extract → Translate (gemma2:9b) → LaTeX Gen → PDF Compile
```

*주요 파라미터:*
- 소스 PDF: 353페이지 중 0~99페이지 (100페이지)
- 번역 모델: gemma2:9b (Ollama, localhost:11434)
- 다이어그램 추출: PyMuPDF pixmap 250 DPI (벡터 그래픽 → 래스터 변환)
- LaTeX 엔진: XeLaTeX 2-pass (Noto Serif CJK KR)
- 디자인 시스템: tcolorbox 기반 (sample.tex 프리앰블)

= 산출물 현황

#table(
  columns: (auto, 1fr, auto),
  inset: 8pt,
  align: (center, left, center),
  [*항목*], [*경로*], [*수량/크기*],
  [섹션 JSON], [seven\_sketches/sections/\*.json], [46개],
  [다이어그램], [seven\_sketches/images/\*.png], [46개],
  [파싱 메타], [seven_sketches/parsed_sections.json], [270KB],
  [LaTeX 소스], [seven_sketches/latex/main.tex], [1,454줄],
  [최종 PDF], [seven_sketches/latex/main.pdf], [432KB],
)

= 테스트 결과

#table(
  columns: (auto, 1fr, auto, auto),
  inset: 8pt,
  align: (center, left, center, center),
  [*\#*], [*테스트 항목*], [*결과*], [*비고*],
  [1], [PDF 파싱 (섹션 감지)], [#text(fill: rgb("22c55e"), weight: "bold")[PASS]], [46섹션 검출],
  [2], [벡터 다이어그램 추출], [#text(fill: rgb("22c55e"), weight: "bold")[PASS]], [36개 추출],
  [3], [Ollama 번역 (46섹션)], [#text(fill: rgb("eab308"), weight: "bold")[PARTIAL]], [1섹션 미번역],
  [4], [LaTeX 생성], [#text(fill: rgb("22c55e"), weight: "bold")[PASS]], [1,454줄],
  [5], [XeLaTeX 컴파일], [#text(fill: rgb("22c55e"), weight: "bold")[PASS]], [432KB PDF],
  [6], [타이틀 페이지], [#text(fill: rgb("ef4444"), weight: "bold")[FAIL]], [제목/저자 미표시],
  [7], [목차 (TOC)], [#text(fill: rgb("ef4444"), weight: "bold")[FAIL]], [항목 비어있음],
  [8], [챕터 제목 매핑], [#text(fill: rgb("ef4444"), weight: "bold")[FAIL]], [책 제목이 Ch1 제목으로],
  [9], [수학 기호 렌더링], [#text(fill: rgb("eab308"), weight: "bold")[PARTIAL]], [·⊠ 박스 표시],
  [10], [tcolorbox 환경], [#text(fill: rgb("ef4444"), weight: "bold")[FAIL]], [미적용 (평문)],
  [11], [단락 구분], [#text(fill: rgb("eab308"), weight: "bold")[PARTIAL]], [일부 구간 밀집],
  [12], [한국어 줄바꿈], [#text(fill: rgb("22c55e"), weight: "bold")[PASS]], [정상 작동],
)

*요약: 12개 항목 중 PASS 4, PARTIAL 3, FAIL 4*

= 상세 분석

== 성공 항목

=== PDF 파싱 (섹션 감지)
TeXGyrePagellaX 폰트의 특성상 섹션 번호("1.1")와 제목("More than the sum...")이 별도 line 오브젝트로 분리되어 있었다. `pending_sec_num` 상태머신 패턴으로 해결하여 46개 섹션을 정확히 검출했다.

=== 벡터 다이어그램 추출
이 PDF는 TikZ/PGF 벡터 그래픽을 사용하므로 `page.get_images()`가 빈 결과를 반환한다. 텍스트 블록 간 갭(>=40pt)에서 `page.get_drawings()` 벡터 패스 존재 여부를 확인하고, `page.get_pixmap(dpi=250, clip=rect)`로 해당 영역을 래스터 이미지로 변환하는 방식으로 36개 다이어그램을 성공적으로 추출했다.

=== XeLaTeX 컴파일
2-pass 컴파일 정상 완료. 한국어 줄바꿈(`\XeTeXlinebreaklocale "ko"`)과 수학 모드 이스케이핑이 올바르게 작동하여 overfull hbox 경고 최소화.

== 실패 항목

=== 타이틀 페이지 (FAIL)
TikZ 타이틀 페이지의 텍스트 노드가 표시되지 않음. 배경색(ctdark)만 렌더링되고 제목/저자/부제목 텍스트가 누락. *원인 추정:* `generate_latex()`에서 sample.tex의 TikZ 타이틀 페이지 코드를 preamble로만 가져오고, 실제 `\begin{document}` 후 TikZ 블록을 삽입하지 않았을 가능성.

=== 목차 비어있음 (FAIL)
`\tableofcontents` 명령어가 있지만 항목이 0개. *원인:* `\chapter*`, `\section*` (별표 버전)을 사용하여 번호 없는 섹션으로 출력했거나, `\addcontentsline` 호출이 누락되었을 가능성.

=== 챕터 제목 매핑 (FAIL)
Chapter 1 제목이 "구성성의 일곱 개 스케치: 응용 범주론에 대한 초대장"으로 표시됨 — 이는 *책 전체의 제목*이며 Chapter 1 제목이 아님. *원인:* 파싱 시 level 0 섹션 (책 제목)이 Chapter 1로 매핑된 것으로 추정.

=== Section 1.2.1 미번역 (PARTIAL)
gemma2:9b가 한국어 번역 대신 영어 요약을 생성함: "This text provides a comprehensive introduction to sets, functions, relations, partitions, and equivalence relations. Let's break down the key concepts and examples:" — LLM 할루시네이션.

=== 수학 기호 (PARTIAL)
`·` (middle dot), `∗` (asterisk) 등의 유니코드 수학 기호가 `⊠` 박스로 렌더링됨. Noto Serif CJK KR 폰트에 해당 글리프가 없거나, LaTeX 이스케이핑에서 누락.

=== tcolorbox 미적용 (FAIL)
sample.tex에 정의된 exercisebox, definitionbox, examplebox 등의 tcolorbox 환경이 전혀 사용되지 않음. Exercise, Definition 등이 평문으로 출력됨. *원인:* `generate_latex()`에서 섹션 내용의 구조적 분류(연습문제/정의/예제 감지)를 수행하지 않고 전체를 일반 텍스트로 출력.

= 성능 측정

#table(
  columns: (auto, 1fr, auto),
  inset: 8pt,
  align: (center, left, center),
  [*단계*], [*설명*], [*소요시간*],
  [1], [PDF 파싱 + 다이어그램 추출], [~5초],
  [2], [번역 (46섹션, gemma2:9b)], [33분 05초],
  [3], [LaTeX 생성], [1초 미만],
  [4], [XeLaTeX 컴파일 (2-pass)], [~15초],
  [], [*총 소요시간*], [*~34분*],
)

번역 속도: 평균 43.16초/섹션 (gemma2:9b, RTX 3050 8GB)

= 결론 및 다음 단계

*파이프라인 아키텍처는 검증 완료.* PDF 파싱 → 벡터 다이어그램 추출 → Ollama 번역 → LaTeX → PDF 전체 흐름이 작동한다.

*품질 개선이 필요한 4개 영역:*

+ *타이틀 페이지 복원:* TikZ 타이틀 블록을 `\begin{document}` 직후에 삽입
+ *TOC 활성화:* `\chapter` / `\section` (별표 없는 버전) 사용 또는 `\addcontentsline` 추가
+ *tcolorbox 환경 적용:* 연습문제("Exercise"), 정의("Definition") 등의 키워드를 감지하여 적절한 환경으로 래핑
+ *수학 기호 폰트 폴백:* `\setmainfont`에 `FallbackFont` 또는 `\newfontfamily\mathsymbolfont` 추가

*선택적 개선:*
- gemma2:9b 할루시네이션 대응: 번역 결과가 영어인 경우 재시도 로직
- 챕터/섹션 매핑 정확도 향상 (level 0 = 책 제목 필터링)
- 단락 구분 개선 (빈 줄 감지 로직 강화)
