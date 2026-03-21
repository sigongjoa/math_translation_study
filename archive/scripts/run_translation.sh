#!/bin/bash
# PDF 번역 실행 스크립트

echo "=========================================="
echo "PDF 번역 파이프라인 시작"
echo "=========================================="
echo ""
echo "총 페이지: 1057"
echo "모델: qwen2.5:latest"
echo "GPU: RTX 3050 x2"
echo ""
echo "예상 소요 시간: 약 15-30시간 (페이지당 1-2분)"
echo ""
echo "진행 상황은 tqdm 프로그레스 바로 확인할 수 있습니다."
echo ""
echo "=========================================="
echo ""

# 전체 문서 번역
python3 translate_pipeline.py --input PCM.pdf --output output

echo ""
echo "=========================================="
echo "번역 완료!"
echo "=========================================="
echo ""
echo "결과 확인:"
echo "  - JSON 파일: output/sections/"
echo "  - 이미지: output/images/"
echo "  - 메타데이터: output/metadata.json"
