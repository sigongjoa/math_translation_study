#set document(title: "PCM Translation Pipeline - Phase 2 Roadmap")
#set page(margin: 2cm, numbering: "1")
#set text(font: "Noto Sans CJK KR", size: 10pt, lang: "ko")
#set heading(numbering: "1.1")

#align(center)[
  #text(size: 20pt, weight: "bold")[PCM 번역 파이프라인]
  #v(0.3em)
  #text(size: 14pt)[Phase 2 구현 로드맵]
  #v(0.3em)
  #text(size: 10pt, fill: gray)[2026-03-10 | /sc:duo auto-generated]
]
#v(1em)
#line(length: 100%)
#v(0.5em)

== 프로젝트 개요
"프린스턴 수학 가이드(Princeton Companion to Mathematics)"의 자동화된 한국어 번역 및 배포를 위한 LLM 에이전트 기반 파이프라인 프로젝트입니다. Phase 1에서 구축된 안정적인 파이프라인 인프라를 바탕으로, Phase 2에서는 **"번역 품질 고도화 레이어(Translation Quality Layer)"** 구축에 집중합니다.

== Phase 1 완료 보고 (기초 인프라)
지난 개발 단계를 통해 다음과 같은 핵심 모듈과 성과가 달성되었습니다.

- *MasterPipeline:* 5단계(Orientation → Draft → TCR → Validation → Evolution) 오케스트레이션 구축.
- *Persistence:* SQLite 기반의 계층적 데이터 저장 (Job, Stage, Section, Iteration, AgentLog) 및 복구 시스템.
- *Knowledge:* 대수학, 해석학, 위상수학 등 200개 이상의 전문 도메인 용어 사전 구축.
- *Human-in-the-loop:* 전문가 수정을 수집하고 반영하는 FeedbackLoop 및 ImpactScorer 구현.
- *검증 결과:* 37개의 자동화 테스트 케이스 100% 통과, 57,000라인 이상의 코드 기여.

== Phase 2 주요 이슈 로드맵

#let priority_box(level, color) = {
  box(fill: color.lighten(80%), stroke: color, inset: 3pt, radius: 2pt)[#text(size: 8pt, weight: "bold", fill: color)[#level]]
}

#let issue_card(title, priority, complexity, color, body) = {
  block(
    fill: luma(250),
    stroke: luma(200),
    inset: 10pt,
    radius: 4pt,
    width: 100%
  )[
    #stack(dir: ltr, spacing: 1fr,
      [*#title*],
      stack(dir: ltr, spacing: 5pt,
        priority_box(priority, color),
        box(fill: gray.lighten(80%), inset: 3pt, radius: 2pt)[#text(size: 8pt)[난이도: #complexity]]
      )
    )
    #v(0.5em)
    #body
  ]
}

#issue_card("이슈 #11: 레이아웃 인식 파서 (Layout-aware Parser)", "P1", "High", red)[
  - *현상:* 기존 PyMuPDF 파서의 구조 소실로 인한 정리(Theorem)/증명(Proof) 블록 혼선.
  - *해결:* `marker-pdf` 라이브러리를 도입하여 10종 이상의 블록 타입(Definition, Proof 등) 식별.
  - *기대 효과:* 다단(Multi-column) 구조의 정확한 읽기 순서 보정 및 메타데이터 추출.
]

#v(0.5em)
#issue_card("이슈 #6: 의미론적 청킹 (Semantic Chunking)", "P1", "Medium", red)[
  - *현상:* 평면적인 텍스트 분할로 인해 논리적 흐름(정리→증명)이 단절됨.
  - *해결:* 파서의 블록 타입을 활용하여 논리적으로 연결된 지식 단위(Knowledge Unit)별로 그룹화.
  - *기대 효과:* 번역 에이전트에게 맥락이 유지된 최적의 텍스트 청크 제공 (응집도 > 85%).
]

#v(0.5em)
#issue_card("이슈 #4: TCR 완전 통합 (TCR Full Integration)", "P2", "Low", orange)[
  - *현상:* CriticAgent가 루프 내부에 매몰되어 용어 주입 성능 검증이 미비함.
  - *해결:* CriticAgent를 독립 모듈화하고, `inject_to_prompt()`를 통해 용어 가이드와 피드백을 직접 주입.
  - *기대 효과:* 전문 용어 준수율 향상 및 비판 점수(Critic Score) 15점 이상 개선.
]

#v(0.5em)
#issue_card("이슈 #7: 직관 우선 동기 부여 블록 (Motivation Block)", "P2", "Medium", orange)[
  - *현상:* 원문 수학 텍스트의 높은 추상성으로 인해 개념 도입부의 가독성 저하.
  - *해결:* MotivationAgent가 주요 정의 이전에 해당 개념의 필요성을 설명하는 2-3문장 생성.
  - *기대 효과:* LaTeX `motivation` 환경 자동 삽입을 통한 한국어 독자 이해도 증진.
]

== 시스템 아키텍처 (Phase 2 개선안)

#block(
  fill: rgb("#F0F4F8"),
  inset: 15pt,
  radius: 5pt,
  width: 100%
)[
  *PDF Input*
  #v(0.3em)
  $arrow.b$ *Stage 1: 도메인 오리엔테이션*
  #h(1em) $dash.en$ [NEW] `LayoutParser` $arrow.r$ 블록 메타데이터(타입/BBox) 추출
  #h(1em) $dash.en$ `WSDAgent` $arrow.r$ 도메인 분류
  #v(0.3em)
  $arrow.b$ *Stage 2: 초안 번역 (Draft)*
  #h(1em) $dash.en$ [IMPROVED] `SemanticChunker` $arrow.r$ 논리 단위 청킹
  #h(1em) $dash.en$ 용어 사전(KnowledgeManager) 기반 초안 생성
  #v(0.3em)
  $arrow.b$ *Stage 3: TCR 교정 (Refinement)*
  #h(1em) $dash.en$ [IMPROVED] `CriticAgent` 독립 구동 및 용어 주입 최적화
  #v(0.3em)
  $arrow.b$ *Stage 4 & 5: 검증 및 진화*
  #h(1em) $dash.en$ [NEW] `MotivationAgent` $arrow.r$ 직관 설명 블록 삽입 및 최종 LaTeX 렌더링
]

== Phase 1 vs Phase 2 성능 비교

#table(
  columns: (1fr, 1.5fr, 1.5fr),
  inset: 8pt,
  align: horizon,
  fill: (x, y) => if y == 0 { gray.lighten(60%) } else { white },
  [*비교 항목*], [*Phase 1 (기존)*], [*Phase 2 (목표)*],
  [PDF 파싱], [단순 텍스트 추출], [레이아웃/블록 타입 인식],
  [데이터 단위], [문단/섹션 기반 분할], [의미론적 지식 단위(Chunk)],
  [용어 관리], [단순 텍스트 치환], [프롬프트 맥락 주입 (Few-shot)],
  [부가 가치], [원문 충실도 위주], [직관적 이해(Motivation) 추가],
  [검증 체계], [룰 기반 자동 체크], [에이전트 비판 + 전문가 피드백]
)

== 향후 일정
- *2026-03-20:* 이슈 #11 및 #6 (레이아웃 엔진) 통합 완료
- *2026-03-30:* 이슈 #4 (TCR 성능 고도화) 벤치마크 완료
- *2026-04-10:* 이슈 #7 (Motivation 엔진) 적용 및 최종 샘플 출력
