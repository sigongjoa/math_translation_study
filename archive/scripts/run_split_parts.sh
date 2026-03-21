#!/bin/bash
# Split PDF 파트들에 대한 번역 파이프라인 연속 실행 스크립트

PARTS=("02" "03" "04")
INPUT_DIR="PCM_split"

for PART in "${PARTS[@]}"; do
    FILE=$(ls ${INPUT_DIR}/PCM_part_${PART}_pages_*.pdf | head -n 1)
    OUTPUT_DIR="output_part_${PART}"
    
    echo "=========================================="
    echo "Part ${PART} 번역 시작: ${FILE}"
    echo "출력 디렉토리: ${OUTPUT_DIR}"
    echo "=========================================="
    
    # deepseek-r1:7b가 없으므로 research-model을 qwen2.5로 대체하거나 
    # 기본 모델을 사용하여 실행합니다. (기본적으로 verifier는 모델 없으면 skip 함)
    
    python3 translate_pipeline.py \
        --input "${FILE}" \
        --output "${OUTPUT_DIR}" \
        --model "gemma2:9b" \
        --supplement-model "qwen2.5-coder:7b" \
        --verify-model "qwen3:14b" \
        --research-model "qwen2.5:latest"
        
    echo "Part ${PART} 완료!"
    echo ""
done

echo "모든 작업이 완료되었습니다."
