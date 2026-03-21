#set document(title: "Issue #5 & #16 Fix Report")
#set page(margin: 2cm, numbering: "1")
#set text(font: "Noto Sans CJK KR", size: 10pt)
#set heading(numbering: "1.1")

#align(center)[
  #text(size: 20pt, weight: "bold")[PCM 번역 파이프라인]
  #v(0.3em)
  #text(size: 14pt)[Issue \#5 & \#16 구현 개선 리포트]
  #v(0.3em)
  #text(size: 10pt, fill: gray)[2026-02-26 | /sc:duo 자동 생성]
]

#line(length: 100%)
#v(0.5em)

= 작업 요약

이전 평가에서 두 이슈의 구현이 얕은 수준임이 발견되어 실질적인 개선을 수행하였다.

#table(
  columns: (auto, 1fr, auto),
  inset: 8pt,
  align: (center, left, center),
  fill: (_, row) => if row == 0 { luma(230) } else { white },
  [*이슈*], [*문제*], [*처리*],
  [\#16], [GlossaryArchitect — 번역이 `"Preorder (원어)"` 플레이스홀더], [✅ 수정],
  [\#5],  [WolframVerifier — string 비교, 상수 3개, API 미호출], [✅ 수정],
)

= 수정 내용

== Issue \#16: GlossaryArchitect (`glossary_architect.py`)

*변경 전:* 추출된 영어 용어를 `f"{en} (원어)"` 형태로만 저장 (번역 없음)

*변경 후:*

- *2단계 LLM 호출 도입*: 1단계(용어 추출 JSON) → 2단계(개별 용어 한국어 번역 획득)
- *Wikipedia 교차검증*: `KnowledgeAgent.get_definition()`으로 한국어 위키백과에서 번역어 확인. 확인되면 `[Verified]` 로그 출력
- *`한국어(english)` 형식 강제*: LLM에게 형식 명시 요청
- *critical\_fixes 우선 적용 유지*: Preorder, Poset, Category 등 8개 핵심 용어는 항상 덮어쓰기
- *Graceful fallback*: Ollama 없어도 critical\_fixes만으로 정상 저장

== Issue \#5: WolframVerifier (`wolfram_verifier.py`)

*변경 전:* `verify_formula()`가 단순 문자열 비교, 물리 상수 3개, 단위 검사 너무 단순

*변경 후:*

#table(
  columns: (1fr, 1fr),
  inset: 8pt,
  align: left,
  fill: (_, row) => if row == 0 { luma(230) } else { white },
  [*항목*], [*구현 내용*],
  [물리 상수], [3개 → *20개* (c, h, G, ℏ, k_B, ε₀, μ₀, e, m_e, m_p, N_A, R, σ, α, a₀, Ry, eV, atm, cal, amu)],
  [수식 검증], [중괄호 균형 `{}`, 달러 기호 `$` 쌍, 주요 LaTeX 명령어 수 일치],
  [단위 검사], [비-SI 단위 감지 (cm, inch, erg...), 정규식 기반 숫자+단위 패턴 추출],
  [API fallback], [`app_id=None` 시 `logging.warning` 명시적 출력],
  [상수 업데이트], [기존 파일에 `symbol` 필드 없으면 자동 재생성],
)

= 테스트 결과

*총 20개 테스트, 전원 통과 (기존 11개 포함)*

#table(
  columns: (auto, 1fr, auto),
  inset: 8pt,
  align: (center, left, center),
  fill: (_, row) => if row == 0 { luma(230) } else { white },
  [*\#*], [*테스트 항목*], [*결과*],
  [1], [test_constants_are_20_or_more], [✅ PASS],
  [2], [test_verify_formula_valid], [✅ PASS],
  [3], [test_verify_formula_brace_mismatch], [✅ PASS],
  [4], [test_verify_formula_command_mismatch], [✅ PASS],
  [5], [test_check_unit_non_si], [✅ PASS],
  [6], [test_warning_logged_without_app_id], [✅ PASS],
  [7], [test_critical_fixes_always_applied], [✅ PASS],
  [8], [test_ollama_failure_graceful], [✅ PASS],
  [9], [test_two_stage_llm_calls], [✅ PASS],
  [10-20], [기존 WSD Agent 테스트 11개], [✅ PASS],
)

#raw(block: true, lang: "text", read("assets/pytest_output.txt"))

= 이슈 완료 현황 (전체)

#table(
  columns: (auto, 1fr, auto),
  inset: 8pt,
  align: (center, left, center),
  fill: (_, row) => if row == 0 { luma(230) } else { white },
  [*이슈*], [*내용*], [*상태*],
  [\#3],  [WSD Agent], [✅ 완료],
  [\#4],  [TCR Loop (threshold + iterations)], [✅ 완료],
  [\#5],  [Wolfram/Wikipedia 검증], [✅ 완료],
  [\#10], [KnowledgeManager (thread-safe)], [✅ 완료],
  [\#15], [Structural Layer (색상 기반 파싱)], [✅ 완료],
  [\#16], [GlossaryArchitect (2단계 LLM + Wikipedia)], [✅ 완료],
  [\#17], [Layout Template Engine], [✅ 완료],
)

= 결론

Issue \#5와 \#16의 구현을 실질적인 수준으로 끌어올렸다. 전체 테스트 20개 통과. 이슈 \#5, \#16 닫기 가능.
