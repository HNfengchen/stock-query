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
  python -m scripts.cli 603956
  python -m scripts.cli 威派格 --config config/config.yaml
  python -m scripts.cli 威派格 --output-dir ./my_reports
        """,
    )

    parser.add_argument("stock", help="股票代码或名称")
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

    args = parser.parse_args()

    if args.output == "markdown":
        print("注意：Markdown 格式暂未实现，将输出 HTML 格式")

    config = load_config(args.config)

    if args.no_charts:
        config["report"]["include_charts"] = False

    output_dir = args.output_dir or config.get("output", {}).get(
        "directory", "output/reports"
    )

    print(f"正在分析股票：{args.stock} ...")

    try:
        fetcher = DataFetcher(config)
        data = fetcher.fetch_all_data(args.stock)

        print(f"股票：{data['stock_name']} ({data['stock_code']})")

        analyzer = StockAnalyzer(config)
        analysis = analyzer.generate_recommendation(data)

        signal = analysis["trading_signal"]
        print(f"交易信号：{signal['signal_text']} (评分：{signal['score']})")

        generator = ReportGenerator(config)
        html = generator.generate_html_report(data, analysis)

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
