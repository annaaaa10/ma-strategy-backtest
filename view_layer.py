import csv
from pathlib import Path
from config import FAST, SLOW, BENCH_NAME, STOCK_NAME, START, END, COMMISSION, SPLIT
from data_layer import _parse
from calc_layer import trade_points
# =============================================================================
# ④ 结果输出
# =============================================================================
def fmt_pct(x):
    return f"{x * 100:+.2f}%"


def print_table(res: dict, segs: dict, name: str = STOCK_NAME):
    print("\n" + "=" * 72)
    print(f"双均线择时（MA{FAST}/MA{SLOW}）回测结果   标的：{name}   基准：{BENCH_NAME}")
    print("=" * 72)
    hdr = f"{'区间':<10}{'累计收益':>12}{'年化收益':>12}{'最大回撤':>12}{'夏普比率':>10}{'超额收益':>12}"
    print(hdr)
    print("-" * 72)
    for tag, m in segs.items():
        if not m:
            continue
        print(f"{tag:<10}{fmt_pct(m['total']):>12}{fmt_pct(m['annual']):>12}"
              f"{fmt_pct(m['mdd']):>12}{m['sharpe']:>10.2f}{fmt_pct(m['excess']):>12}")
    print("-" * 72)
    print("基准买入持有（全程）：累计 %s / 年化 %s" %
          (fmt_pct(segs["全程"]["b_total"]), fmt_pct(segs["全程"]["b_annual"])))
    pts = trade_points(res["dates"], res["closes"], res["position"])
    buys = sum(1 for p in pts if p["side"] == "buy")
    print(f"交易次数：买入 {buys} 次 / 卖出 {len(pts) - buys} 次；"
          f"平均仓位 {sum(res['position']) / len(res['position']):.1%}")


def write_csv(res: dict, segs: dict, path: Path):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["区间", "累计收益率", "年化收益率", "最大回撤", "夏普比率",
                    "基准累计", "超额收益", "交易日数"])
        for tag, m in segs.items():
            if m:
                w.writerow([tag, m["total"], m["annual"], m["mdd"], m["sharpe"],
                            m["b_total"], m["excess"], m["days"]])
        w.writerow([])
        w.writerow(["日期", "收盘价", "信号", "仓位", "策略净值", "基准净值"])
        for i, d in enumerate(res["dates"]):
            w.writerow([d.isoformat(), res["closes"][i], res["signal"][i],
                        res["position"][i], res["nav"][i], res["bnav"][i]])


def write_html(res: dict, segs: dict, path: Path, source: str, name: str = STOCK_NAME):
    """生成内嵌 SVG 的 HTML 报告：归一化净值曲线 + 买卖点标注，无外部依赖。"""
    W, H, PAD = 900, 420, 55
    dates, nav, bnav = res["dates"], res["nav"], res["bnav"]
    n = len(nav)
    lo = min(min(nav), min(bnav)) * 0.97
    hi = max(max(nav), max(bnav)) * 1.03
    if hi <= lo:
        hi = lo + 1

    def X(i):
        return PAD + (W - 2 * PAD) * i / max(1, n - 1)

    def Y(v):
        return H - PAD - (H - 2 * PAD) * (v - lo) / (hi - lo)

    def poly(seq, color):
        return " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(seq))

    grid = []
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = Y(v)
        grid.append(f'<line x1="{PAD}" y1="{y:.1f}" x2="{W-PAD}" y2="{y:.1f}" '
                    f'stroke="#e5e7eb" stroke-width="1"/>'
                    f'<text x="{PAD-8}" y="{y+4:.1f}" font-size="11" fill="#6b7280" '
                    f'text-anchor="end">{v:.2f}</text>')

    pts = trade_points(dates, res["closes"], res["position"])
    markers = []
    for p in pts:
        i = dates.index(p["date"])
        is_buy = p["side"] == "buy"
        color = "#d92d20" if is_buy else "#12b76a"
        y = Y(nav[i])
        markers.append(f'<circle cx="{X(i):.1f}" cy="{y:.1f}" r="4" fill="{color}" '
                       f'stroke="#fff" stroke-width="1"><title>{p["date"]} '
                       f'{"买入" if is_buy else "卖出"} {p["price"]:.2f}</title></circle>')

    split_idx = next((i for i, d in enumerate(dates) if d >= _parse(SPLIT)), n)
    split_line = ""
    if 0 < split_idx < n:
        x = X(split_idx)
        split_line = (f'<line x1="{x:.1f}" y1="{PAD}" x2="{x:.1f}" y2="{H-PAD}" '
                      f'stroke="#f79009" stroke-dasharray="5 4" stroke-width="1.5"/>'
                      f'<text x="{x+6:.1f}" y="{PAD+14}" font-size="11" fill="#b54708">'
                      f'样本内/外切分</text>')

    def seg_row(tag):
        m = segs.get(tag)
        if not m:
            return ""
        return (f"<tr><td>{tag}</td><td>{fmt_pct(m['total'])}</td>"
                f"<td>{fmt_pct(m['annual'])}</td><td>{fmt_pct(m['mdd'])}</td>"
                f"<td>{m['sharpe']:.2f}</td><td>{fmt_pct(m['excess'])}</td></tr>")

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>双均线择时回测报告</title></head>
<body style="font-family:system-ui,'Microsoft YaHei',sans-serif;margin:32px;color:#111827">
<h2 style="font-size:18px;font-weight:600">双均线择时（MA{FAST}/MA{SLOW}）· {name} vs {BENCH_NAME}</h2>
<p style="color:#6b7280;font-size:13px">数据来源：{source} ｜ 区间 {START} — {END} ｜ 均归一化至 1.0 起算 ｜ 含 {COMMISSION*100:.2f}% 单边佣金</p>
<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;border:1px solid #e5e7eb;border-radius:8px">
{''.join(grid)}
{split_line}
<polyline points="{poly(bnav,'#667085')}" fill="none" stroke="#667085" stroke-width="1.8"/>
<polyline points="{poly(nav,'#d92d20')}" fill="none" stroke="#d92d20" stroke-width="2.2"/>
{''.join(markers)}
<rect x="{W-190}" y="20" width="176" height="52" rx="6" fill="#fff" fill-opacity="0.9" stroke="#e5e7eb"/>
<line x1="{W-178}" y1="38" x2="{W-150}" y2="38" stroke="#d92d20" stroke-width="2.5"/>
<text x="{W-142}" y="42" font-size="12" fill="#344054">策略净值</text>
<line x1="{W-178}" y1="58" x2="{W-150}" y2="58" stroke="#667085" stroke-width="2"/>
<text x="{W-142}" y="62" font-size="12" fill="#344054">基准净值</text>
<circle cx="{W-178}" cy="78" r="4" fill="#d92d20"/></svg>
<p style="font-size:12px;color:#d92d20">● 红点=买入　</p><p style="font-size:12px;color:#12b76a">● 绿点=卖出（鼠标悬停看日期与价格）</p>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-size:13px;margin-top:20px">
<tr style="background:#f9fafb"><th>区间</th><th>累计收益</th><th>年化收益</th><th>最大回撤</th><th>夏普比率</th><th>超额收益</th></tr>
{seg_row('样本内')}{seg_row('样本外')}{seg_row('全程')}</table>
<p style="font-size:12px;color:#6b7280;margin-top:20px">信号说明：第 t 日收盘后计算 MA{FAST}/MA{SLOW}，第 t+1 日按信号持仓；position[t]=signal[t−1]，无未来函数。</p>
</body></html>"""
    path.write_text(html, encoding="utf-8")
def write_summary(rows: list[dict], path: Path):
        """多只股票横向对比汇总表。"""
        cols = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"\n[汇总] {path}")