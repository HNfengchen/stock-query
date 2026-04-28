"""
命令行入口点
"""

import sys
import os
import argparse
import yaml
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.core.data_fetcher import DataFetcher, InvalidStockCodeError
from scripts.core.analyzer import StockAnalyzer
from scripts.core.report_generator import ReportGenerator


def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "config.yaml"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="股票分析报告生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m scripts.cli 威派格
  python -m scripts.cli 603956 未持有
  python -m scripts.cli 603956 已持有 15.60
  python -m scripts.cli 威派格 --config config/config.yaml
  python -m scripts.cli 威派格 --output-dir ./my_reports
        """,
    )

    parser.add_argument("stock", help="股票代码或名称")
    parser.add_argument(
        "position",
        nargs="*",
        default=["未持有"],
        help="持仓状态：已持有/未持有 [持仓成本]",
    )
    parser.add_argument("--config", "-c", help="配置文件路径", default=None)
    parser.add_argument("--output-dir", "-o", help="输出目录", default=None)
    parser.add_argument(
        "--output",
        "-t",
        help="输出格式：html/markdown",
        default="html",
        choices=["html", "markdown"],
    )
    parser.add_argument("--no-charts", help="不生成图表", action="store_true")
    parser.add_argument(
        "--cost",
        "-k",
        type=float,
        help="持仓成本价（已持有时使用）",
        default=None,
    )
    parser.add_argument("--backtest", "-b", help="启用回测", action="store_true")

    args = parser.parse_args()

    if args.output == "markdown":
        print("注意：Markdown 格式暂未实现，将输出 HTML 格式")

    config = load_config(args.config)

    if args.no_charts:
        config["report"]["include_charts"] = False

    output_dir = args.output_dir or config.get("output", {}).get(
        "directory", "output/reports"
    )

    position_args = args.position
    position_status = position_args[0] if position_args else "未持有"
    cost_price = args.cost

    if position_status == "已持有" and len(position_args) > 1:
        try:
            cost_price = float(position_args[1])
        except (ValueError, IndexError):
            cost_price = args.cost

    print(f"正在分析股票：{args.stock} ({position_status}{' ' + str(cost_price) if cost_price else ''}) ...")

    try:
        fetcher = DataFetcher(config)
        data = fetcher.fetch_all_data(args.stock)

        print(f"股票：{data['stock_name']} ({data['stock_code']})")

        analyzer = StockAnalyzer(config)
        analysis = analyzer.generate_recommendation(
            data, position_status=position_status, cost_price=cost_price
        )

        signal = analysis["trading_signal"]
        print(f"交易信号：{signal['signal_text']} (评分：{signal['score']})")

        if args.backtest:
            history_df = data.get("history_data")
            stock_name = data.get("stock_name", "")
            if history_df is not None and not history_df.empty:
                print("正在运行回测...")
                from scripts.core.backtest import Backtester

                backtester = Backtester(stock_code=data.get("stock_code", ""), stock_name=stock_name)
                bt_result = backtester.run_backtest(history_df, data["stock_code"])
                if "error" not in bt_result:
                    stats = bt_result.get("statistics", {})
                    print(f"\n=== 回测结果 ===")
                    print(f"数据范围: {bt_result.get('data_range', 'N/A')}")
                    print(f"Day1预测命中率: {stats.get('day1_hit_rate', 'N/A')}%")
                    print(f"Day2预测命中率: {stats.get('day2_hit_rate', 'N/A')}%")
                    print(f"Day1趋势准确率: {stats.get('day1_trend_accuracy', 'N/A')}%")
                    print(f"Day2趋势准确率: {stats.get('day2_trend_accuracy', 'N/A')}%")
                else:
                    print(f"回测失败: {bt_result.get('error')}")

        generator = ReportGenerator(config)
        html = generator.generate_html_report(data, analysis, position_status=position_status)

        stock_code = data["stock_code"]
        output_path = generator.save_report(html, stock_code, output_dir)

        print(f"\n报告已生成：{output_path}")
        print(f"请在浏览器中打开查看。")

    except InvalidStockCodeError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"生成报告时出错：{e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
