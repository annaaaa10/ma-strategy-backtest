import argparse
from pathlib import Path
from config import STOCK_CODE, STOCK_NAME, SPLIT, SLOW
from data_layer import _parse, parse_codes, lookup_name, fetch_real_data, make_demo_data
from backtest_layer import backtest, metrics
from view_layer import print_table, write_csv, write_html, write_summary

ROOT = Path(__file__).resolve().parent
# =============================================================================
# 主流程
# =============================================================================
def run_one(code: str, name: str, explicit: bool = False) -> dict | None:
    """跑一只股票：拉数据 → 算信号 → 回测 → 输出独立报告，返回汇总指标。"""
    # real = fetch_real_data(code)
    real = None  # 强制使用演示数据，跳过联网
    if real:
        stock, bench = real
        source = f"akshare（{code} 前复权 / sh000300）· 真实数据"
    else:
        if explicit:
            raise RuntimeError(
                f"无法获取 {code}（{name}）的真实数据，已终止，未使用演示数据冒充。\n"
                f"  可能原因：未安装 akshare / 网络无法访问新浪财经 / 股票代码不存在或已退市。\n"
                f"  解决办法：pip install akshare，或换一个有效的 6 位 A 股代码重试。"
            )
        stock, bench = make_demo_data()
        source = "本地确定性演示数据（未安装 akshare 或联网失败；算法与真实数据完全一致）"

    assert len(stock) == len(bench) and len(stock) > SLOW + 5
    res = backtest(stock, bench)

    split_d = _parse(SPLIT)
    idx_in = [i for i, d in enumerate(res["dates"]) if d < split_d]
    idx_out = [i for i, d in enumerate(res["dates"]) if d >= split_d]
    if not idx_in or not idx_out:
        raise RuntimeError("切分日期不在数据区间内，请调整 SPLIT")

    a, b = idx_in[0], idx_in[-1] + 1
    c, d = idx_out[0], idx_out[-1] + 1
    segs = {"样本内": metrics(a, b, res), "样本外": metrics(c, d, res),
            "全程": metrics(0, len(res["dates"]), res)}

    print(f"[数据] {source}")
    print(f"[数据] 交易日 {len(stock)} 天：{stock[0]['date']} ~ {stock[-1]['date']}；"
          f"样本内 {b-a} 天 / 样本外 {d-c} 天")
    print_table(res, segs, name)

    if explicit:
        csv_path = ROOT / f"backtest_results_{code}.csv"
        html_path = ROOT / f"backtest_report_{code}.html"
    else:
        csv_path = ROOT / "backtest_results.csv"
        html_path = ROOT / "backtest_report.html"
    write_csv(res, segs, csv_path)
    write_html(res, segs, html_path, source, name)
    print(f"\n[输出] 指标表：{csv_path}")
    print(f"[输出] 净值报告：{html_path}（浏览器打开查看曲线与买卖点）")

    full = segs["全程"]
    return {"代码": code, "名称": name, "交易日数": len(stock),
            "样本内累计": segs["样本内"]["total"], "样本外累计": segs["样本外"]["total"],
            "全程累计": full["total"], "年化收益": full["annual"],
            "最大回撤": full["mdd"], "夏普比率": full["sharpe"],
            "超额收益": full["excess"], "基准累计": full["b_total"]}


def write_summary(rows: list[dict], path: Path):
    """多只股票横向对比汇总表。"""
    cols = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[汇总] {path}")


def run_codes(codes: list[str]):
    """处理一批股票代码。"""
    if not codes:
        # 与原版完全一致：默认跑茅台，允许演示数据兜底
        run_one(STOCK_CODE, STOCK_NAME, explicit=False)
        return

    print(f"[输入] 共 {len(codes)} 只股票：{', '.join(codes)}")
    summary = []
    for code in codes:
        name = lookup_name(code)
        print(f"\n{'#' * 72}")
        print(f"# 正在处理：{code} {name}")
        print('#' * 72)
        try:
            row = run_one(code, name, explicit=True)
        except RuntimeError as exc:
            print(f"[错误] {exc}")
            continue
        if row:
            summary.append(row)

    if summary:
        write_summary(summary, ROOT / "backtest_summary.csv")
        if len(summary) > 1:
            print("\n" + "=" * 72)
            print("多股票对比汇总（全程指标）")
            print("=" * 72)
            for r in summary:
                print(f"{r['代码']} {r['名称']:<8} 累计 {fmt_pct(r['全程累计']):>10}"
                      f"  年化 {fmt_pct(r['年化收益']):>9}  夏普 {r['夏普比率']:>6.2f}")
    else:
        print("\n[结果] 没有成功回测的股票，请检查代码与环境。")


def main():
    """命令行入口：解析参数后交给 run_codes。"""
    parser = argparse.ArgumentParser(
        description="双均线择时回测：输入股票代码自动拉数据、算指标、出报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python run_backtest_input.py\n"
               "  python run_backtest_input.py 000858\n"
               "  python run_backtest_input.py 000858,600519,300750\n"
               "  python run_backtest_input.py -i")
    parser.add_argument("codes", nargs="*", help="股票代码，6 位数字，可多个（逗号或空格分隔）；不填则弹出输入提示")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互式输入（不加参数时也会自动进入）")
    args = parser.parse_args()

    if args.codes:
        # 命令里带了代码 → 直接用，不再询问
        codes = parse_codes(args.codes)
    else:
        # 没带任何代码（包括双击、IDLE、直接 python xxx.py）→ 弹出输入提示
        codes = _ask_codes()
    run_codes(codes)


def _ask_codes() -> list[str]:
    """交互式读取股票代码。"""
    print("\n" + "=" * 60)
    print("请输入要回测的股票代码")
    print("=" * 60)
    print("  单只：000858")
    print("  多只：000858,600519,300750  （逗号或空格分隔）")
    print("  直接回车：跑默认的贵州茅台")
    try:
        raw = input("\n股票代码 > ").strip()
    except EOFError:
        raw = ""
    codes = parse_codes([raw]) if raw else []
    if not codes:
        print("[输入] 未输入代码，将使用默认的贵州茅台。")
    return codes


if __name__ == "__main__":
    main()