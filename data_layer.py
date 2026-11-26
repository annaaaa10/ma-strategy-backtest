from config import START, END, SLOW, STOCK_CODE
import random
from datetime import date, timedelta
# =============================================================================
# ① 数据接入模块
# =============================================================================
def _parse(d: str) -> date:
    d = str(d).replace("-", "")
    return date(int(d[:4]), int(d[4:6]), int(d[6:8]))


# ------------------------------------------------------------------ 输入解析（本版新增）
def to_symbol(code: str) -> str:
    """6 位股票代码 → 新浪接口符号：6 开头沪市 sh，0/3 开头深市 sz。"""
    code = code.strip()
    if code[:2].lower() in ("sh", "sz"):
        return code
    return ("sh" if code.startswith("6") else "sz") + code


def lookup_name(code: str) -> str:
    """查股票中文简称；失败则返回代码本身，不影响回测。"""
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        hit = df[df["item"] == "股票简称"]["value"]
        if len(hit):
            return str(hit.iloc[0])
    except Exception:                              # noqa: BLE001
        pass
    return code


def parse_codes(args: list[str]) -> list[str]:
    """把命令行参数解析成 6 位代码列表，支持逗号/空格分隔与 sh/sz 前缀。"""
    out: list[str] = []
    for token in args:
        for raw in token.replace("，", ",").replace(";", ",").split(","):
            raw = raw.strip()
            if not raw:
                continue
            raw = raw.lower()
            if raw.startswith(("sh", "sz")):
                raw = raw[2:]
            if len(raw) == 6 and raw.isdigit():
                if raw not in out:
                    out.append(raw)
            else:
                print(f"[输入] 跳过无效代码：{raw}（需为 6 位数字）")
    return out


def _align_calendar(stock: list, bench: list, ak, pd) -> tuple[list, list] | None:
    """按 A 股交易日历对齐个股与基准，停牌日价格 ffill、成交量填 0。

    这是答辩要点：停牌日显式保留，价格前向填充（不突然归零），成交量记 0；
    收益率在填充后的价格上重算，避免"删掉停牌日→隔日收益率虚高/虚低"。
    """
    try:
        cal = ak.calendar_trade_date_hist_sina()
        cal["trade_date"] = pd.to_datetime(cal["trade_date"])
        cal = cal[(cal["trade_date"] >= pd.to_datetime(START)) &
                  (cal["trade_date"] <= pd.to_datetime(END))]
        cal_days = [d.date() if hasattr(d, "date") else d for d in cal["trade_date"]]
    except Exception:                              # noqa: BLE001
        return None                                 # 日历接口不可用 → 降级取交集

    smap = {x["date"]: x for x in stock}
    bmap = {x["date"]: x for x in bench}
    out_s, out_b, last_s, last_b = [], [], None, None
    for d in cal_days:
        # 个股：停牌日无数据 → 沿用前一日 OHLC，成交量填 0
        if d in smap:
            last_s = smap[d]
        elif last_s is not None:
            filled = dict(last_s)
            filled["date"] = d
            filled["volume"] = 0.0
            smap[d] = filled
        # 基准：同理（指数一般不停牌，保险起见同样处理）
        if d in bmap:
            last_b = bmap[d]
        elif last_b is not None:
            filled = dict(last_b)
            filled["date"] = d
            filled["volume"] = 0.0
            bmap[d] = filled
        if d in smap and d in bmap:
            out_s.append(smap[d])
            out_b.append(bmap[d])
    return (out_s, out_b) if len(out_s) >= SLOW + 30 else None


def fetch_real_data(code: str = STOCK_CODE) -> tuple[list, list] | None:
    """用 akshare 拉指定股票的真实数据；任何失败都返回 None。"""
    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        return None
    try:
        s = ak.stock_zh_a_daily(symbol=to_symbol(code), start_date=START, end_date=END, adjust="qfq")
        b = ak.stock_zh_index_daily(symbol="sh000300")

        b["date"] = pd.to_datetime(b["date"])
        b = b[(b["date"] >= pd.to_datetime(START)) & (b["date"] <= pd.to_datetime(END))]

        def conv(df, cols):
            out = []
            for _, r in df.iterrows():
                dt = r["date"]
                d = date(dt.year, dt.month, dt.day) if hasattr(dt, "year") else _parse(str(dt))
                out.append({
                    "date": d,
                    "open": float(r[cols[0]]), "high": float(r[cols[1]]),
                    "low": float(r[cols[2]]), "close": float(r[cols[3]]),
                    "volume": float(r[cols[4]]),
                })
            return sorted(out, key=lambda x: x["date"])

        stock = conv(s, ["open", "high", "low", "close", "volume"])
        bench = conv(b, ["open", "high", "low", "close", "volume"])

        # 优先按交易日历对齐（保留停牌日 + ffill）；接口失败则降级为日期交集
        aligned = _align_calendar(stock, bench, ak, pd)
        if aligned:
            stock, bench = aligned
            print(f"[数据] 交易日历对齐完成：{len(stock)} 个交易日，"
                  f"停牌日价格 ffill、成交量填 0")
        else:
            bd = {x["date"]: x for x in bench}
            stock = [x for x in stock if x["date"] in bd]
            bench = [bd[x["date"]] for x in stock]
        if len(stock) < SLOW + 30:
            return None
        return stock, bench
    except Exception as exc:                       # noqa: BLE001
        print(f"[数据] 真实数据获取失败：{exc}")
        return None


def make_demo_data() -> tuple[list, list]:
    """确定性演示数据（固定随机种子，结果可复现）。走完全相同的回测逻辑。"""
    rng = random.Random(20261123)
    days, cur = [], _parse(START)
    end = _parse(END)
    while cur <= end:
        if cur.weekday() < 5:                       # 只生成工作日近似交易日
            days.append(cur)
        cur += timedelta(days=1)

    def series(drift, vol, start_px):
        bars, px = [], start_px
        for d in days:
            o = px
            ret = drift + rng.gauss(0, vol)
            # 偶发趋势段，让均线策略有可识别的行情
            px = max(1.0, px * (1 + ret))
            c = px
            hi = max(o, c) * (1 + abs(rng.gauss(0, 0.004)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
            bars.append({"date": d, "open": o, "high": hi, "low": lo,
                         "close": c, "volume": 1e6 + rng.random() * 4e6})
        return bars

    stock = series(0.0006, 0.018, 100.0)           # 标的：波动较大、略有趋势
    bench = series(0.0003, 0.011, 3000.0)          # 基准：波动较小
    return stock, bench