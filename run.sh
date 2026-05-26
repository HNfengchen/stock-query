#!/bin/bash
# 模型训练脚本
# 用法:
#   bash run.sh              # 增量训练(仅训练缺失/过期模型)
#   bash run.sh --force      # 强制全量重训
#   bash run.sh --hmm-only   # 仅重训HMM

FORCE=0
HMM_ONLY=0

for arg in "$@"; do
    case $arg in
        --force)   FORCE=1 ;;
        --hmm-only) HMM_ONLY=1 ;;
    esac
done

if [ "$HMM_ONLY" = 1 ]; then
    echo "仅重训HMM模型..."
    python -m scripts.train_hmm
    exit 0
fi

if [ "$FORCE" = 1 ]; then
    echo "强制全量重训..."
    rm -rf models/
    python -m scripts.train_model --watchlist
    python -m scripts.train_hmm
else
    echo "增量训练(跳过已存在且未过期的模型)..."
    python -m scripts.train_model --watchlist --skip-existing
    # HMM仅在模型文件不存在时训练
    if [ ! -f "models/hmm_regime.pkl" ]; then
        echo "HMM模型不存在，训练..."
        python -m scripts.train_hmm
    else
        echo "HMM模型已存在，跳过(如需重训: bash run.sh --hmm-only)"
    fi
fi
