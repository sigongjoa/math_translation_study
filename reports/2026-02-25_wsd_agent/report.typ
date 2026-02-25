#set document(title: "WSD 에이전트 구현 리포트")
#set page(margin: 2cm, numbering: "1")
#set text(font: "Noto Sans CJK KR", size: 10pt)
#set heading(numbering: "1.1")

#align(center)[
  #text(size: 20pt, weight: "bold")[PCM 번역 파이프라인]
  #v(0.3em)
  #text(size: 14pt)[Issue \#3: WSD 에이전트 구현 리포트]
  #v(0.3em)
  #text(size: 10pt, fill: gray)[2026-02-25 | /sc:duo 자동 생성]
]

#line(length: 100%)
#v(0.5em)

= 작업 요약

번역 전 단계에서 수학/물리 텍스트의 도메인을 자동 분류하고, 중의적 용어(다의어)의 올바른 번역을 사전에 결정하는 WSD(Word Sense Disambiguation) 에이전트를 구현하였다.

*핵심 문제*: `field`(체/장/들판), `ring`(환/고리), `kernel`(핵/커널) 등 다의어를 문맥 없이 번역하면 전문 용어 오역 발생.

*해결책*: 번역 전 단계에 WSD 에이전트를 추가하여 도메인 분류 후 올바른 번역 제약 조건을 LLM 프롬프트에 주입.

= 구현 내용

== 생성된 파일

#table(
  columns: (1.8fr, 1fr, 2fr),
  inset: 7pt,
  align: (left, center, left),
  fill: (_, row) => if row == 0 { luma(220) } else { white },
  [*파일*], [*크기*], [*역할*],
  [`src/pcm/core/wsd_agent.py`], [~7KB], [메인 WSD 에이전트 모듈],
  [`src/pcm/data/ambiguous_terms.json`], [~15KB], [62개 다의어 사전],
  [`tests/test_wsd_agent.py`], [~4KB], [단위 테스트 (11개)],
)

== 클래스 구조

*DomainClassifier*: Qwen3:14b (Ollama) 호출로 도메인 분류. 연결 실패 시 키워드 매칭 fallback.

*WSDGuideGenerator*: `ambiguous_terms.json`을 기반으로 텍스트에서 다의어를 추출하고 도메인에 맞는 번역 가이드 생성.

*WSDAgent*: 위 두 클래스를 조합하여 번역 프롬프트에 자동 주입.

= 테스트 결과

== 단위 테스트 (pytest)

#table(
  columns: (2.5fr, 1fr, auto),
  inset: 7pt,
  align: (left, center, center),
  fill: (_, row) => if row == 0 { luma(220) } else if calc.rem(row, 2) == 0 { luma(245) } else { white },
  [*테스트 항목*], [*클래스*], [*결과*],
  [`test_classify_algebra`], [DomainClassifier], [✅ PASS],
  [`test_classify_fallback_on_ollama_error`], [DomainClassifier], [✅ PASS],
  [`test_classify_returns_valid_domain`], [DomainClassifier], [✅ PASS],
  [`test_extract_ambiguous_terms_field`], [WSDGuideGenerator], [✅ PASS],
  [`test_extract_case_insensitive`], [WSDGuideGenerator], [✅ PASS],
  [`test_generate_guide_structure`], [WSDGuideGenerator], [✅ PASS],
  [`test_generate_guide_algebra_field`], [WSDGuideGenerator], [✅ PASS],
  [`test_prompt_constraint_not_empty`], [WSDGuideGenerator], [✅ PASS],
  [`test_analyze_returns_required_keys`], [WSDAgent], [✅ PASS],
  [`test_inject_to_prompt`], [WSDAgent], [✅ PASS],
  [`test_inject_to_prompt_preserves_original`], [WSDAgent], [✅ PASS],
)

#text(weight: "bold", fill: rgb("2d8a2d"))[총 11개 테스트 전체 통과 (11/11)]

== 실제 동작 테스트

#raw(block: true, lang: "text", read("assets/live_test_output.txt"))

== pytest 상세 로그

#raw(block: true, lang: "text", read("assets/pytest_output.txt"))

= 수용 기준(AC) 달성 현황

#table(
  columns: (3fr, 1fr),
  inset: 7pt,
  align: (left, center),
  fill: (_, row) => if row == 0 { luma(220) } else { white },
  [*수용 기준*], [*달성*],
  [`DomainClassifier` 클래스 구현 및 단위 테스트], [✅],
  [`WSDGuideGenerator` 클래스 구현], [✅],
  [도메인별 다의어 사전 (최소 50개)], [✅ 62개],
  [번역 파이프라인 주입 로직 (`inject_to_prompt`)], [✅],
  [Ollama 실패 시 graceful fallback], [✅],
)

*미완료*: 벤치마크(WSD 적용 전/후 오역률 비교)는 실제 번역 파이프라인 통합 후 별도 측정 필요.

= 발견된 문제 및 수정 사항

- *`map` 용어 도메인 누락*: `ambiguous_terms.json`에서 `map`의 수학 도메인이 `geometry`만 등록되어 있어 `algebra` 컨텍스트에서 "배치"로 잘못 번역됨. `algebra`, `analysis`, `topology` 도메인에 "사상(寫像)" 추가하여 수정. [Claude 직접 수정]

- *`support`, `norm`의 도메인 미세 조정*: `analysis` 도메인에서 키워드 매칭이 `quantum_mechanics`로 오분류되는 경우 확인. Ollama 활성화 시 개선 예상.

= 결론 및 다음 단계

WSD 에이전트 핵심 기능 구현 완료. 62개 다의어 사전과 11개 단위 테스트 전체 통과.

*다음 단계*:
1. Issue \#4 (TCR 루프)에서 WSD 결과를 Translator 에이전트에 주입하여 실제 번역 품질 향상 확인
2. Issue \#10 (전역 용어 사전)과 연동하여 WSD 결과를 자동 저장
3. Ollama 활성화 상태에서 도메인 분류 정확도 벤치마크 측정
