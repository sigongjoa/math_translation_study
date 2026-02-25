#set page(paper: "a4", margin: (x: 2.2cm, y: 2.5cm), numbering: "1")
#set text(font: ("Noto Sans CJK KR", "Noto Sans"), size: 10pt, lang: "ko")
#set heading(numbering: "1.")
#show heading.where(level: 1): it => block(
  fill: rgb("#1a237e"), inset: 8pt, radius: 4pt, width: 100%,
  text(fill: white, size: 13pt, weight: "bold", it.body)
)
#show heading.where(level: 2): it => block(
  fill: rgb("#e8eaf6"), inset: 6pt, radius: 3pt, width: 100%,
  text(fill: rgb("#1a237e"), size: 11pt, weight: "bold", it.body)
)

#let win = text(fill: rgb("#2e7d32"), weight: "bold")[✅ 개선]
#let lose = text(fill: rgb("#c62828"), weight: "bold")[⚠️ 이슈]
#let same = text(fill: rgb("#757575"))[— 동일]

// ─── 타이틀 ─────────────────────────────────────────────────────────────
#align(center)[
  #v(1.5cm)
  #text(size: 20pt, weight: "bold", fill: rgb("#1a237e"))[WSD Agent 번역 품질 비교]
  #v(0.3cm)
  #text(size: 13pt, fill: rgb("#424242"))[Before vs After — 실제 gemma2:9b 번역 결과]
  #v(0.3cm)
  #line(length: 70%, stroke: 2pt + rgb("#1a237e"))
  #v(0.4cm)
  #grid(
    columns: (1fr, 1fr, 1fr),
    gutter: 1cm,
    align(center)[#text(weight:"bold")[번역 모델]\ gemma2:9b],
    align(center)[#text(weight:"bold")[분류 모델]\ qwen3:14b (fallback)],
    align(center)[#text(weight:"bold")[사전 크기]\ 2,989개 용어],
  )
]
#pagebreak()

// ─── 1. 요약 ──────────────────────────────────────────────────────────
= 벤치마크 요약

#table(
  columns: (auto, auto, 1fr, 1fr, auto),
  stroke: 0.5pt + rgb("#9E9E9E"),
  fill: (col, row) => if row == 0 { rgb("#e8eaf6") } else if calc.rem(row,2)==0 { rgb("#fafafa") } else { none },
  [*섹션*], [*도메인*], [*WSD 없음 (주요 오류)*], [*WSD 포함 (개선)*], [*평가*],
  [1.1], [analysis], [정보손실적, 합성 연산], [동일 수준], [#same],
  [1.1.2], [algebra\*(오감지)], [map→함수, 순서→순서], [map→사상 ✅\ order→위수 ⚠️], [부분개선],
  [1.2.1], [analysis], [domain→도메인\ image→이미지 (외래어)], [domain→*정의역* ✅\ image→*상(像)* ✅], [#win],
)

#block(
  fill: rgb("#e8f5e9"), inset: 10pt, radius: 4pt, stroke: 0.5pt + rgb("#81C784"),
)[
  *핵심 성과:* Section 1.2.1에서 `domain`→"정의역", `image`→"상(像)"으로 올바른 수학 용어 사용.
  WSD 없는 번역은 두 용어를 외래어("도메인", "이미지")로 그대로 음역하는 반면, WSD는 표준 수학 용어로 유도.
]

#block(
  fill: rgb("#fff3e0"), inset: 10pt, radius: 4pt, stroke: 0.5pt + rgb("#FFB74D"),
)[
  *한계:* Section 1.1.2의 `order`가 algebra 도메인 오감지로 "위수(位數)"로 번역됨.
  실제 컨텍스트는 category_theory이므로 "순서(관계)"가 올바름. 도메인 분류기 개선 필요.
]

#pagebreak()

// ─── 2. 섹션별 상세 비교 ─────────────────────────────────────────────
= 섹션별 상세 번역 비교

== 섹션 1.2.1: Review of sets, relations, and functions (★ 최고 성과)

*원문*
#block(fill: rgb("#f5f5f5"), inset: 8pt, radius: 3pt, stroke: 0.5pt + rgb("#9E9E9E"))[
  #text(size: 9pt)[A function f from a set A to a set B assigns to each element a in A exactly one element f(a) in B. The set A is called the *domain* of f and the set B is called the codomain. The *image* of f is the set of all elements in B that are of the form f(a) for some a in A. If f is *injective*, then distinct elements of A *map* to distinct elements of B. If f is *surjective*, every element of B is in the image of f.]
]

#grid(
  columns: (1fr, 1fr),
  gutter: 0.8cm,
  [
    *WSD 없음*
    #block(fill: rgb("#ffebee"), inset: 8pt, radius: 3pt, stroke: 0.5pt + rgb("#EF9A9A"))[
      #text(size: 9pt)[집합 $A$에서 집합 $B$로의 함수 $f$는 각 원소 $a \in A$에 대해서 정확히 하나인 $B$ 속 원소 $f(a)$를 할당합니다. 집합 $A$를 $f$의 *#text(fill: rgb("#c62828"))[도메인]*, 그리고 집합 $B$를 $f$의 *#text(fill: rgb("#c62828"))[코도메인]*이라고 합니다. 함수 $f$의 *#text(fill: rgb("#c62828"))[이미지]*는 형태가 $f(a)$ ($a \in A$) 인 모든 $B$ 속 원소들의 집합입니다. 만약 $f$가 단사함수라면, $A$에서 서로 다른 원소들은 $B$에서 서로 다른 원소들에 대응됩니다.]
    ]
    *오류:* 외래어 음역 ("도메인", "코도메인", "이미지")
  ],
  [
    *WSD 포함*
    #block(fill: rgb("#e8f5e9"), inset: 8pt, radius: 3pt, stroke: 0.5pt + rgb("#81C784"))[
      #text(size: 9pt)[집합 $A$에서 집합 $B$로의 함수 $f$는 $A$에 속하는 각 원소 $a$에 대해 정확히 하나인 $B$의 원소 $f(a)$를 대응시킵니다. $A$를 $f$의 *#text(fill: rgb("#1b5e20"))[정의역]*이라고 하고, $B$를 *#text(fill: rgb("#1b5e20"))[치역 또는 공역]*이라고 합니다. 함수 $f$의 *#text(fill: rgb("#1b5e20"))[상]*은 $A$에서 어떤 $a$에 대해 형태가 $f(a)$인 모든 원소로 이루어진 집합입니다. 만약 $f$가 단사함수라면, $A$의 서로 다른 원소들은 $B$의 서로 다른 원소들과 대응됩니다.]
    ]
    *개선:* 정의역 ✅, 치역/공역 ✅, 상(像) ✅
  ]
)

#table(
  columns: (auto, 1fr, 1fr, auto),
  stroke: 0.5pt + rgb("#9E9E9E"),
  fill: (col, row) => if row == 0 { rgb("#e8eaf6") } else { none },
  [*영어 원문*], [*WSD 없음*], [*WSD 포함*], [*평가*],
  [domain], [도메인 (외래어)], [*정의역(定義域)*], [#win],
  [codomain], [코도메인 (외래어)], [*치역 또는 공역*], [#win],
  [image], [이미지 (외래어)], [*상(像)*], [#win],
  [map], [대응], [대응], [#same],
)

#pagebreak()

== 섹션 1.1.2: Ordering systems (부분 개선)

*원문*
#block(fill: rgb("#f5f5f5"), inset: 8pt, radius: 3pt, stroke: 0.5pt + rgb("#9E9E9E"))[
  #text(size: 9pt)[Category theory is all about organizing and layering structures. ...how the operation of joining systems can be derived from a more basic structure: *order*. We will see that the notion of a preorder...is a simple but powerful concept. A *map* between preorders that preserves the *order* relation is called a monotone map.]
]

#grid(
  columns: (1fr, 1fr),
  gutter: 0.8cm,
  [
    *WSD 없음*
    #block(fill: rgb("#f5f5f5"), inset: 8pt, radius: 3pt)[
      #text(size: 9pt)[범주론은 구조를 조직하고 층을 만드는 데 관한 것입니다. ...시스템들을 결합하는 연산이 기본적인 구조인 *순서*에서 유도될 수 있다는 것을 설명합니다. ...사전순위 사이의 *함수*로써 순서관계를 보존하는 것은 단조함수라고 합니다.]
    ]
  ],
  [
    *WSD 포함 (domain: algebra 오감지)*
    #block(fill: rgb("#fff8e1"), inset: 8pt, radius: 3pt, stroke: 0.5pt + rgb("#FFB74D"))[
      #text(size: 9pt)[범주 이론은 구조를 조직하고 계층화하는 것입니다. ...시스템을 결합하는 연산이 기본적인 구조인 *#text(fill: rgb("#e65100"))[위수]*에서 유도될 수 있는 방법에 대해 설명합니다. ...순서관계를 보존하는 사전순서 사이의 *#text(fill: rgb("#1b5e20"))[사상]*은 단조 함수라고 합니다.]
    ]
  ]
)

#table(
  columns: (auto, 1fr, 1fr, auto),
  stroke: 0.5pt + rgb("#9E9E9E"),
  fill: (col, row) => if row == 0 { rgb("#e8eaf6") } else { none },
  [*영어 원문*], [*WSD 없음*], [*WSD 포함*], [*평가*],
  [map], [함수], [*사상(寫像)*], [#win],
  [order], [순서 (컨텍스트 적합)], [위수 (algebra 오감지)], [#lose],
  [category], [범주론], [범주 이론], [#same],
)

#block(
  fill: rgb("#fff3e0"), inset: 8pt, radius: 3pt, stroke: 0.5pt + rgb("#FFB74D"),
)[
  *원인 분석:* 이 텍스트에 "algebra" 키워드가 없는데도 algebra 도메인으로 감지됨.
  Ollama 기반 LLM 분류기가 작동하지 않아 fallback keyword 분류기 사용 중.
  `order`가 algebra 도메인에서 "위수(群의 원소 개수)"로 매핑되어 오번역 발생.
  *해결 방향:* algebra 도메인에서 ordering/relation 맥락의 order는 "순서"로 번역해야 함을 사전에 추가.
]

#pagebreak()

// ─── 3. 결론 ──────────────────────────────────────────────────────────
= 결론: Issue #3 WSD Agent 완료 평가

== 달성된 목표

#table(
  columns: (auto, 1fr, auto),
  stroke: 0.5pt + rgb("#9E9E9E"),
  fill: (col, row) => if row == 0 { rgb("#e8eaf6") } else { none },
  [*항목*], [*내용*], [*상태*],
  [WSD Agent 구현], [DomainClassifier + WSDGuideGenerator + WSDAgent], [✅ 완료],
  [테스트 (11개)], [모두 통과], [✅ 완료],
  [사전 보강], [62개 → 2,989개 (×48)], [✅ 완료],
  [translator 통합], [OllamaTranslator(use_wsd=True)], [✅ 완료],
  [실제 번역 비교], [3섹션 before/after 실측], [✅ *완료*],
  [개선 효과 확인], [domain→정의역, image→상(像) 수학용어 정확도 향상], [✅ *확인*],
)

== 향후 개선 사항 (Issue 별도 생성 권장)

+ *도메인 분류기 정확도 개선*: "order" + ordering/preorder 맥락 → category_theory/topology 감지 강화
+ *사전 품질 점수 향상*: 77/100 → 90점 (statistics 도메인 보강, confidence 필드 정비)
+ *Ollama LLM 분류기 안정화*: 키워드 fallback 의존도 감소, qwen3:14b 분류기 응답 신뢰성 개선
