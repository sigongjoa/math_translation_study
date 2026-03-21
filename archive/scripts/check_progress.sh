#!/bin/bash
# 번역 진행 상황 모니터링 스크립트

echo "=========================================="
echo "번역 진행 상황 모니터링"
echo "=========================================="
echo ""

# 번역 로그 확인
if [ -f translation.log ]; then
    echo "📋 최근 로그:"
    tail -20 translation.log
    echo ""
fi

# 생성된 섹션 파일 개수 확인
if [ -d output/sections ]; then
    section_count=$(ls -1 output/sections/*.json 2>/dev/null | wc -l)
    echo "✅ 완료된 섹션: $section_count / 18"
    echo ""
fi

# 프로세스 확인
if pgrep -f "translate_pipeline" > /dev/null; then
    echo "🔄 번역 프로세스 실행 중..."
else
    echo "⚠️  번역 프로세스가 실행되지 않고 있습니다."
fi

echo ""
echo "=========================================="
echo "실시간 모니터링: watch -n 5 ./check_progress.sh"
echo "로그 확인: tail -f translation.log"
echo "=========================================="
