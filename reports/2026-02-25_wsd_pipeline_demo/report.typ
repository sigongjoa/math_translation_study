#set page(
  paper: "a4",
  margin: (x: 2.2cm, y: 2.5cm),
  numbering: "1",
)
#set text(font: ("Noto Sans CJK KR", "Noto Sans"), size: 10pt, lang: "ko")
#set heading(numbering: "1.")
#show heading.where(level: 1): it => block(
  fill: rgb("#1a237e"),
  inset: 8pt,
  radius: 4pt,
  width: 100%,
  text(fill: white, size: 13pt, weight: "bold", it.body)
)
#show heading.where(level: 2): it => block(
  fill: rgb("#e8eaf6"),
  inset: 6pt,
  radius: 3pt,
  width: 100%,
  text(fill: rgb("#1a237e"), size: 11pt, weight: "bold", it.body)
)

// 색상 정의
#let clr_domain = rgb("#4CAF50")
#let clr_term = rgb("#2196F3")
#let clr_warn = rgb("#FF9800")
#let clr_bg_code = rgb("#f5f5f5")
#let clr_border = rgb("#9E9E9E")

// ─── 타이틀 페이지 ─────────────────────────────────────────────────────
#align(center)[
  #v(2cm)
  #text(size: 22pt, weight: "bold", fill: rgb("#1a237e"))[WSD Agent 파이프라인 통합 데모]
  #v(0.4cm)
  #text(size: 14pt, fill: rgb("#424242"))[Seven Sketches in Compositionality — 3섹션 분석]
  #v(0.3cm)
  #text(size: 11pt, fill: rgb("#757575"))[Issue \#3 후속 작업: 결론 및 다음 단계 이행]
  #v(0.6cm)
  #line(length: 80%, stroke: 2pt + rgb("#1a237e"))
  #v(0.4cm)
  #grid(
    columns: (1fr, 1fr, 1fr),
    gutter: 1cm,
    align(center)[
      #text(weight: "bold")[날짜]\ 2026-02-25
    ],
    align(center)[
      #text(weight: "bold")[사전 크기]\ 2,989개 용어
    ],
    align(center)[
      #text(weight: "bold")[분석 섹션]\ 3개
    ],
  )
]

#pagebreak()

// ─── 1. 개요 ──────────────────────────────────────────────────────────
= 이행 내용 요약

본 리포트는 Issue \#3 WSD Agent의 *결론 및 다음 단계*에서 제시된 두 가지 항목의 이행 결과를 담고 있습니다.

#block(
  fill: rgb("#e8f5e9"),
  inset: 10pt,
  radius: 4pt,
  width: 100%,
)[
  *✅ 완료된 항목*
  + *사전 보강*: 62개 → *2,989개* (한국물리학회 phys_kr 2,872개 + 수동 55개)
  + *누락 도메인 해결*: `topology`, `number_theory`, `combinatorics`, `probability`, `quantum_mechanics` 모두 10개 이상 달성
  + *translator.py WSD 통합*: `use_wsd=True` 옵션으로 자동 도메인 감지 + 프롬프트 주입
  + *파이프라인 데모*: 3개 실섹션 WSD 분석 완료
]

#v(0.5cm)

== 사전 품질 변화 비교

#table(
  columns: (auto, 1fr, 1fr),
  stroke: 0.5pt + clr_border,
  fill: (col, row) => if row == 0 { rgb("#e8eaf6") } else { none },
  [*항목*], [*이전 (62개)*], [*이후 (2,989개)*],
  [총 용어 수], [62], [*2,989*],
  [품질 점수], [70.7/100], [*77/100*],
  [topology], [4개 ❌], [*22개 ✅*],
  [number_theory], [0개 ❌], [*15개 ✅*],
  [combinatorics], [0개 ❌], [*14개 ✅*],
  [probability], [0개 ❌], [*13개 ✅*],
  [quantum_mechanics], [0개 ❌], [*12개 ✅*],
  [소스 다양성], [unknown 1종], [*phys_kr + manual + original 3종*],
)

#pagebreak()

// ─── 2. 섹션별 WSD 분석 ───────────────────────────────────────────────
= 3섹션 WSD 분석 결과

== 섹션 1.1: More than the sum of their parts

#grid(
  columns: (1fr, 1fr),
  gutter: 0.8cm,
  [
    *감지 도메인:* #text(fill: clr_domain, weight: "bold")[analysis]

    *발견된 다의어: 9개*

    #table(
      columns: (auto, auto, auto),
      stroke: 0.5pt + clr_border,
      fill: (col, row) => if row == 0 { rgb("#e3f2fd") } else if calc.rem(row, 2) == 0 { rgb("#fafafa") } else { none },
      [*영어*], [*한국어*], [*도메인 기반*],
      [order], [순서/차수], [analysis],
      [map], [사상(寫像)], [analysis],
      [category], [범주/카테고리], [analysis],
      [sum], [총합/금액], [analysis],
      [function], [\(1\)기능 \(2\)함수], [analysis],
      [complete], [완전한/완비], [analysis],
      [limit], [극한(極限)], [analysis],
      [convergence], [수렴(收斂)], [analysis],
      [work], [작업/작품/노동], [general],
    )
  ],
  [
    *WSD 프롬프트 주입 (일부)*

    #block(
      fill: clr_bg_code,
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + clr_border,
      width: 100%,
    )[
      #text(size: 8pt, font: "Noto Sans Mono")[
        번역 시 다음 용어 규칙을 준수하세요:\
        - 도메인: 'analysis'\
        - map → 사상(寫像)\
        - category → 범주/카테고리\
        - convergence → 수렴(收斂)\
        - limit → 극한(極限)\
        - complete → 완전한/완비\
        #text(fill: clr_warn)[\[주의: 지도, 지역으로 번역하지 말 것\]]
      ]
    ]

    *기존 번역 (일부)*
    #block(
      fill: rgb("#fff8e1"),
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + rgb("#FFD54F"),
      width: 100%,
    )[
      #text(size: 8pt)[이 첫 번째 장에서는 많은 실세계 구조들이 합성적(compositional)임을 주목하면서, 관찰 결과가 항상 합성적이지는 않다는 점을 동기로 삼는다...]
    ]
  ]
)

#v(0.5cm)

== 섹션 1.1.1: A first look at generative effects

#grid(
  columns: (1fr, 1fr),
  gutter: 0.8cm,
  [
    *감지 도메인:* #text(fill: clr_domain, weight: "bold")[geometry]

    *발견된 다의어: 11개*

    #table(
      columns: (auto, auto, auto),
      stroke: 0.5pt + clr_border,
      fill: (col, row) => if row == 0 { rgb("#e3f2fd") } else if calc.rem(row, 2) == 0 { rgb("#fafafa") } else { none },
      [*영어*], [*한국어*], [*특이사항*],
      [order], [순서, 차례], [다중 번역],
      [power], [권력/힘], [물리/일반],
      [point], [점(點)], [기하],
      [arc], [호(弧)], [기하],
      [simple], [간단한], [컨텍스트 의존],
      [complete], [완전한/완비], [분석],
      [graph], [그래프], [수학],
      [function], [\(1\)기능 \(2\)함수], [일반],
      [image], [상(像)], [대수],
      [map], [사상(寫像)], [대수],
      [limit], [극한(極限)], [해석학],
    )
  ],
  [
    *핵심 관찰*

    #block(
      fill: rgb("#fce4ec"),
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + rgb("#F48FB1"),
    )[
      *도메인 감지 이슈:* geometry로 감지되었지만 실제 내용은 범주론/시스템 관찰에 관한 것. 이는 WSD의 키워드 기반 도메인 분류기의 한계를 보여줌. Ollama 기반 LLM 분류기가 온라인이면 더 정확한 분류 가능.
    ]

    #v(0.3cm)

    #block(
      fill: rgb("#e8f5e9"),
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + rgb("#81C784"),
    )[
      *긍정적 결과:* `point`, `arc`, `map`, `graph` 등 수학 용어는 올바르게 번역 가이드를 생성함. 11개 다의어 모두 적절한 한국어 매핑 제공.
    ]
  ]
)

#pagebreak()

== 섹션 1.1.2: Ordering systems

#grid(
  columns: (1fr, 1fr),
  gutter: 0.8cm,
  [
    *감지 도메인:* #text(fill: clr_domain, weight: "bold")[category_theory ✅]

    *발견된 다의어: 6개*

    #table(
      columns: (auto, auto),
      stroke: 0.5pt + clr_border,
      fill: (col, row) => if row == 0 { rgb("#e3f2fd") } else if calc.rem(row, 2) == 0 { rgb("#fafafa") } else { none },
      [*영어*], [*한국어*],
      [order], [순서, 차례],
      [map], [사상(寫像)],
      [category], [범주(範疇)],
      [mean], [의미하다/비열한],
      [function], [\(1\)기능 \(2\)함수],
      [complete], [완전한/완비],
    )
  ],
  [
    *핵심 성과*

    #block(
      fill: rgb("#e8f5e9"),
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + rgb("#81C784"),
    )[
      *✅ 최고 성과 섹션*: 이 섹션의 내용("Category theory is all about organizing...")이 명시적 키워드를 포함해 `category_theory` 도메인이 정확히 감지됨.

      `category → 범주(範疇)` (일반 번역 "카테고리/종류"와 명확히 구분)

      `map → 사상(寫像)` (일반 번역 "지도/배치"와 명확히 구분)
    ]
  ]
)

#pagebreak()

// ─── 3. translator.py 통합 ─────────────────────────────────────────────
= translator.py WSD 통합 결과

== 통합 방식

#block(
  fill: clr_bg_code,
  inset: 10pt,
  radius: 4pt,
  stroke: 0.5pt + clr_border,
  width: 100%,
)[
  #text(size: 8.5pt, font: "Noto Sans Mono")[
    ```python
    # 기존 (정적 glossary만 사용)
    translator = OllamaTranslator()
    # → MATH_GLOSSARY 62개 용어, 도메인 구분 없음

    # 통합 후 (WSD 동적 주입)
    translator = OllamaTranslator(use_wsd=True)  # 기본값
    # → 2,989개 용어, 도메인 감지 후 다의어 규칙 프롬프트에 자동 주입
    ```
  ]
]

== 프롬프트 구조 비교

#grid(
  columns: (1fr, 1fr),
  gutter: 0.8cm,
  [
    *이전: 정적 Glossary*
    #block(
      fill: rgb("#ffebee"),
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + rgb("#EF9A9A"),
      width: 100%,
    )[
      #text(size: 8pt, font: "Noto Sans Mono")[
        수학 용어 참조:\
        \ \ field → 체\
        \ \ ring → 환\
        \ \ kernel → 핵\
        \ \ ...\
        \
        English text:\
        The kernel of a ring...\
        \
        Korean translation:
      ]
    ]
    *문제점:* 도메인 구분 없음, wrong_translations 가이드 없음
  ],
  [
    *이후: WSD 동적 주입*
    #block(
      fill: rgb("#e8f5e9"),
      inset: 8pt,
      radius: 3pt,
      stroke: 0.5pt + rgb("#81C784"),
      width: 100%,
    )[
      #text(size: 8pt, font: "Noto Sans Mono")[
        수학 용어 참조:\
        \ \ field → 체, ring → 환\
        \
        번역 시 다음 용어 규칙을 준수하세요:\
        - 도메인: 'algebra'\
        - field → 체(體) (사칙연산이 정의된 집합)\
        \ \ \[주의: 들판, 경기장 등으로 번역 금지\]\
        - ring → 환(環) (덧셈과 곱셈이 정의된 구조)\
        \ \ \[주의: 종소리, 전화벨 등으로 번역 금지\]\
        \
        English text:\
        The kernel of a ring...\
        \
        Korean translation:
      ]
    ]
    *개선점:* 도메인 명시, wrong_translations 규칙, 정의 포함
  ]
)

#pagebreak()

// ─── 4. 결론 ──────────────────────────────────────────────────────────
= 결론 및 향후 계획

== 성과 요약

#table(
  columns: (auto, 1fr, auto),
  stroke: 0.5pt + clr_border,
  fill: (col, row) => if row == 0 { rgb("#e8eaf6") } else { none },
  [*항목*], [*내용*], [*상태*],
  [사전 보강], [62개 → 2,989개 (×48 증가)], [✅],
  [도메인 커버리지], [5개 미달 도메인 모두 10개 이상 달성], [✅],
  [translator 통합], [OllamaTranslator에 use_wsd 파라미터 추가], [✅],
  [파이프라인 데모], [3섹션 WSD 분석 및 프롬프트 주입 검증], [✅],
  [build-term-dict 스킬], [analyze/merge/scrape 스크립트 완성], [✅],
  [실제 번역 비교], [Ollama 오프라인으로 before/after 번역 미완], [⏳],
)

== 다음 단계

#block(
  fill: rgb("#fff3e0"),
  inset: 10pt,
  radius: 4pt,
  stroke: 0.5pt + rgb("#FFB74D"),
)[
  1. *Ollama 온라인 시*: `python3 seven_sketches/pipeline.py --sections 1.1,1.1.1,1.1.2 --use-wsd` 실행하여 실제 번역 품질 비교
  2. *사전 품질 개선*: 품질 점수 77점 → 90점 목표 (statistics 도메인 보강, confidence 필드 추가)
  3. *Issue \#3 공식 종료*: 실제 번역 비교 결과 확인 후 close-issue 스킬로 종료
]
