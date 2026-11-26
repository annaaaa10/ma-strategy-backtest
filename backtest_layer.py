import math
import statistics
from config import COMMISSION, TRADING_DAYS
from calc_layer import generate_signals, build_position
# =============================================================================
# ③ 回测引擎
# =============================================================================
def backtest(stock: list, bench: list):
    """逐 bar 撮合：策略收益 = 仓位 × 标的收益 − 换手成本；基准 = 买入持有。"""
    closes = [b["close"] for b in stock]
    bcloses = [b["close"] for b in bench]
    dates = [b["date"] for b in stock]
    sig = generate_signals(closes)
    pos = build_position(sig)

    strat_ret, bench_ret, nav, bnav = [], [], [1.0], [1.0]
    for i in range(len(closes)):
        if i == 0:
            r, br = 0.0, 0.0
        else:
            r = closes[i] / closes[i - 1] - 1.0
            br = bcloses[i] / bcloses[i - 1] - 1.0
        turnover = abs(pos[i] - pos[i - 1]) if i > 0 else 0
        sr = pos[i] * r - turnover * COMMISSION
        strat_ret.append(sr)
        bench_ret.append(br)
        nav.append(nav[-1] * (1 + sr))
        bnav.append(bnav[-1] * (1 + br))
    return {"dates": dates, "closes": closes, "bcloses": bcloses,
            "signal": sig, "position": pos, "strat_ret": strat_ret,
            "bench_ret": bench_ret, "nav": nav[1:], "bnav": bnav[1:]}


def metrics(start: int, end: int, res: dict) -> dict:
    """计算作业要求的四项指标；[start, end) 为区间下标。"""
    nav, bnav = res["nav"], res["bnav"]
    rs = res["strat_ret"][start:end]
    if not rs:
        return {}
    total = nav[end - 1] / nav[start] - 1.0 if start > 0 else nav[end - 1] - 1.0
    btotal = bnav[end - 1] / bnav[start] - 1.0 if start > 0 else bnav[end - 1] - 1.0
    n = max(1, end - start)
    ann = (1 + total) ** (TRADING_DAYS / n) - 1 if total > -1 else -1.0
    bann = (1 + btotal) ** (TRADING_DAYS / n) - 1 if btotal > -1 else -1.0

    seg = nav[start:end]
    peak, mdd = seg[0], 0.0
    for v in seg:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)

    sd = statistics.pstdev(rs) if len(rs) > 1 else 0.0
    sharpe = (statistics.mean(rs) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    return {"total": total, "annual": ann, "mdd": mdd, "sharpe": sharpe,
            "b_total": btotal, "b_annual": bann, "excess": total - btotal,
            "days": n}