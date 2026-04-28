#!/bin/bash

# 股票分析报告生成脚本
# 用法: ./analyze_report.sh 股票代码 [已持有|未持有] [持仓成本] [选项]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STOCK_NAME="${1:-}"
POSITION="${2:-未持有}"
COST="${3:-}"
CONFIG_FLAG=""
OUTPUT_DIR_FLAG=""
BACKTEST_FLAG=""

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
        --backtest|-b)
            BACKTEST_FLAG="--backtest"
            shift
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$STOCK_NAME" ]]; then
    echo "用法: $0 <股票代码> [已持有|未持有] [持仓成本] [--config <配置文件>] [--output-dir <输出目录>] [--backtest]"
    echo "示例:"
    echo "  $0 000001 未持有"
    echo "  $0 603956 已持有 15.60"
    echo "  $0 603956 已持有 15.60 --backtest"
    exit 1
fi

COST_ARG=""
if [[ "$POSITION" == "已持有" && -n "$COST" ]]; then
    COST_ARG="$COST"
fi

python -m scripts.cli "$STOCK_NAME" "$POSITION" $COST_ARG $CONFIG_FLAG $OUTPUT_DIR_FLAG $BACKTEST_FLAG
