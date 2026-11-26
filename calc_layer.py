from config import FAST, SLOW
# =============================================================================
# ② 策略 / 信号模块
# =============================================================================
def sma(values: list[float], window: int) -> list[float | None]:
    """简单移动平均，前 window-1 个为 None（只用历史数据，无未来函数）。"""
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def generate_signals(closes: list[float]) -> list[int]:
    """signal[t] = 1 表示第 t 日收盘后判断为多头，0 表示空仓。"""
    fast, slow = sma(closes, FAST), sma(closes, SLOW)
    sig = []
    for i in range(len(closes)):
        if fast[i] is None or slow[i] is None:
            sig.append(0)
        else:
            sig.append(1 if fast[i] > slow[i] else 0)
    return sig


def build_position(signal: list[int]) -> list[int]:
    """position[t] = signal[t-1] —— 信号收盘后产生，次日才可成交。"""
    return [0] + signal[:-1]


def trade_points(dates: list[date], closes: list[float], pos: list[int]) -> list[dict]:
    """提取关键买卖点：仓位 0→1 记 buy，1→0 记 sell（用于净值图标注）。"""
    pts = []
    for i in range(1, len(pos)):
        if pos[i] > pos[i - 1]:
            pts.append({"date": dates[i], "side": "buy", "price": closes[i]})
        elif pos[i] < pos[i - 1]:
            pts.append({"date": dates[i], "side": "sell", "price": closes[i]})
    return pts

