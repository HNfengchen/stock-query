#!/bin/bash

# 股票分析报告生成脚本
# 用法：./analyze_report.sh 股票名称 [选项]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STOCK_NAME="${1:-}"
CONFIG_FLAG=""
OUTPUT_DIR_FLAG=""

shift
while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FLAG="--config $2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR_FLAG="--output-dir $2"
            shift 2
            ;;
        *)
            echo "未知参数：$1"
            exit 1
            ;;
    esac
done

if [[ -z "$STOCK_NAME" ]]; then
    echo "用法：$0 <股票名称或代码> [--config <配置文件>] [--output-dir <输出目录>]"
    echo "示例:"
    echo "  $0 威派格"
    echo "  $0 603956"
    echo "  $0 威派格 --config config/config.yaml"
    echo "  $0 威派格 --output-dir ./my_reports"
    exit 1
fi

python -m scripts.cli "$STOCK_NAME" $CONFIG_FLAG $OUTPUT_DIR_FLAG
