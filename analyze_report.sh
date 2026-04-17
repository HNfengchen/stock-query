#!/bin/bash

# 股票分析报告生成脚本
# 用法：./analyze_report.sh 股票代码 [已持有|未持有] [选项]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STOCK_NAME="${1:-}"
POSITION="${2:-未持有}"
CONFIG_FLAG=""
OUTPUT_DIR_FLAG=""

shift 2
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
    echo "用法：$0 <股票代码> [已持有|未持有] [--config <配置文件>] [--output-dir <输出目录>]"
    echo "示例:"
    echo "  $0 000001 未持有"
    echo "  $0 000001 已持有"
    echo "  $0 603956 未持有 --output-dir ./my_reports"
    exit 1
fi

python -m scripts.cli "$STOCK_NAME" "$POSITION" $CONFIG_FLAG $OUTPUT_DIR_FLAG
