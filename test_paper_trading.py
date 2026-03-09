"""
模拟交易测试脚本
使用 Binance 公开 API（无需 API Key）获取真实行情
在本地模拟执行买卖，不产生真实订单
"""
import sys
import os
import json
import time
import requests
import yaml
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from core.market_analyzer import MarketAnalyzer
from core.position_manager import PositionManager
from strategy.oscillation import OscillationStrategy
from strategy.trend import TrendStrategy

# ─── 颜色输出 ────────────────────────────────────────
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
BLUE  = "\033[94m"
BOLD  = "\033[1m"
RESET = "\033[0m"

def color(text, c): return f"{c}{text}{RESET}"

# ─── 模拟配置（无需填写真实 API）────────────────────
PAPER_CONFIG = {
    "system": {"enabled": True, "paper_trading": True, "log_level": "INFO"},
    "rebate": {"profit_share_pct": 0.05, "profit_share_wallet": ""},
    "exchanges": {
        "binance": {"enabled": True, "api_key": "", "api_secret": "", "testnet": False},
        "okx": {"enabled": False, "api_key": "", "api_secret": "", "passphrase": ""},
        "polymarket": {"enabled": False, "private_key": ""}
    },
    "markets": {
        "binance": {"symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"], "quote_currency": "USDT"}
    },
    "strategy": {
        "analysis": {
            "adx_trend_threshold": 25,
            "adx_range_threshold": 20,
            "timeframe": "1h",
            "lookback_candles": 100
        },
        "oscillation": {
            "enabled": True,
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "bollinger_period": 20,
            "bollinger_std": 2.0,
            "grid_levels": 5,
            "grid_spacing_atr": 0.5
        },
        "trend": {
            "enabled": True,
            "ma_fast": 20,
            "ma_slow": 60,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "volume_multiplier": 1.5,
            "trailing_stop_pct": 0.02
        }
    },
    "risk": {
        "total_capital": 10000,       # 模拟 10000 USDT
        "max_positions": 3,
        "position_size_pct": 0.10,
        "max_loss_per_trade": 0.02,
        "stop_loss_pct": 0.015,
        "take_profit_pct": 0.03,
        "max_daily_loss": 0.05,
        "risk_reward_ratio": 1.5      # 模拟测试略低门槛
    }
}

# ─── 公开行情获取（无需 API Key）────────────────────
def fetch_klines_public(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    """直接调用 Binance 公开端点，无需签名"""
    symbol_fmt = symbol.replace("/", "")
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol_fmt, "interval": interval, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return [{
            "timestamp": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5])
        } for c in r.json()]
    except Exception as e:
        print(color(f"  ✗ 获取行情失败: {e}", RED))
        return []

def fetch_price_public(symbol: str) -> float:
    """获取当前价格"""
    symbol_fmt = symbol.replace("/", "")
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price",
                         params={"symbol": symbol_fmt}, timeout=5)
        return float(r.json()["price"])
    except:
        return 0.0

# ─── 模拟账户 ────────────────────────────────────────
class PaperAccount:
    def __init__(self, capital: float = 10000):
        self.capital = capital
        self.initial_capital = capital
        self.positions = []
        self.trade_log = []

    def open(self, symbol, side, price, qty, stop_loss, take_profit, strategy):
        cost = qty * price
        self.capital -= cost
        pos = {
            "symbol": symbol, "side": side, "entry_price": price,
            "qty": qty, "cost": cost,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "strategy": strategy, "open_time": datetime.now().strftime("%H:%M:%S")
        }
        self.positions.append(pos)
        self.trade_log.append({**pos, "action": "OPEN"})
        return pos

    def close(self, symbol, price, reason=""):
        for p in self.positions[:]:
            if p["symbol"] == symbol:
                if p["side"] == "long":
                    pnl = (price - p["entry_price"]) * p["qty"]
                else:
                    pnl = (p["entry_price"] - price) * p["qty"]
                self.capital += p["cost"] + pnl
                self.positions.remove(p)
                self.trade_log.append({
                    **p, "action": "CLOSE", "close_price": price,
                    "pnl": pnl, "reason": reason
                })
                return pnl
        return 0

    def pnl(self):
        return self.capital - self.initial_capital

    def pnl_pct(self):
        return (self.capital - self.initial_capital) / self.initial_capital * 100


# ─── 主测试流程 ──────────────────────────────────────
def run_paper_test():
    print(color("\n" + "═"*55, BOLD))
    print(color("   AI 全自动交易系统 — 模拟交易测试", BOLD))
    print(color("   Paper Trading Mode (真实行情 / 虚拟下单)", BLUE))
    print(color("═"*55, BOLD))
    print(f"   初始资金: {color('10,000 USDT', GREEN)}  |  模式: {color('模拟', YELLOW)}")
    print(color("═"*55, BOLD) + "\n")

    cfg = PAPER_CONFIG
    analyzer = MarketAnalyzer(cfg)
    osc_strategy = OscillationStrategy(cfg)
    trend_strategy = TrendStrategy(cfg)
    account = PaperAccount(cfg["risk"]["total_capital"])
    symbols = cfg["markets"]["binance"]["symbols"]

    results = []

    for symbol in symbols:
        print(color(f"\n▶ 分析: {symbol}", BOLD))
        print("  正在获取 Binance 公开行情数据...")

        candles = fetch_klines_public(symbol, "1h", 100)
        if not candles:
            print(color("  跳过（无法获取行情）", YELLOW))
            continue

        current_price = candles[-1]["close"]
        print(f"  当前价格: {color(f'{current_price:,.4f} USDT', BOLD)}")
        print(f"  K线数量:  {len(candles)} 根 (1h)")

        # 市场分析
        analysis = analyzer.analyze(candles)
        signals_data = analysis["signals"]
        market_type = analysis["market_type"]

        type_display = {
            "oscillation": color("⇄  震荡行情", YELLOW),
            "trend_up":    color("↑  上升趋势", GREEN),
            "trend_down":  color("↓  下降趋势", RED),
        }

        print(f"\n  {'─'*45}")
        print(f"  市场判断: {type_display[market_type]}  "
              f"(置信度 {color(str(analysis['confidence'])+'%', BOLD)})")
        print(f"  建议策略: {analysis['recommendation']}")
        print(f"  {'─'*45}")
        print(f"  RSI:   {signals_data['rsi']:>6.1f}  "
              f"{'↓超卖' if signals_data['rsi'] < 35 else '↑超买' if signals_data['rsi'] > 65 else '  中性'}")
        print(f"  ADX:   {signals_data['adx']:>6.1f}  "
              f"{'强趋势' if signals_data['adx'] > 25 else '震荡区'}")
        print(f"  MACD:  {signals_data['macd']:>10.4f}  柱:{signals_data['macd_hist']:>10.4f}")
        print(f"  BB上轨: {signals_data['bb_upper']:>12.4f}")
        print(f"  BB中轨: {signals_data['bb_mid']:>12.4f}")
        print(f"  BB下轨: {signals_data['bb_lower']:>12.4f}")
        print(f"  MA20:  {signals_data['ma20']:>12.4f}")
        print(f"  MA60:  {signals_data['ma60']:>12.4f}")
        print(f"  量比:  {signals_data['vol_ratio']:>6.2f}x")

        # 生成信号
        open_positions = [{"symbol": p["symbol"],
                           "side": p["side"],
                           "entry_price": p["entry_price"]}
                          for p in account.positions]

        signal = None
        if market_type == "oscillation":
            signal = osc_strategy.generate_signals(symbol, candles, open_positions)
        else:
            signal = trend_strategy.generate_signals(
                symbol, candles, market_type, open_positions)

        if signal:
            action = signal["action"]
            entry  = signal["entry_price"]
            sl     = signal.get("stop_loss", 0)
            tp     = signal.get("take_profit", 0)

            # 计算仓位
            max_loss = cfg["risk"]["total_capital"] * cfg["risk"]["max_loss_per_trade"]
            risk_per_unit = abs(entry - sl) if sl else entry * cfg["risk"]["stop_loss_pct"]
            qty = min(
                max_loss / risk_per_unit if risk_per_unit > 0 else 0,
                account.capital * cfg["risk"]["position_size_pct"] / entry
            )
            qty = round(qty, 6)

            action_display = {
                "buy":  color("▲ 做多 BUY", GREEN),
                "sell": color("▼ 做空 SELL", RED),
            }.get(action, color(action.upper(), YELLOW))

            print(f"\n  {'─'*45}")
            print(f"  {color('>>> 交易信号', BOLD)} {action_display}")
            print(f"  入场价: {color(f'{entry:,.4f}', BOLD)}")
            print(f"  止 损:  {color(f'{sl:,.4f}', RED)}  ({((sl-entry)/entry*100):+.2f}%)")
            print(f"  止 盈:  {color(f'{tp:,.4f}', GREEN)}  ({((tp-entry)/entry*100):+.2f}%)")
            print(f"  盈亏比: {color(str(signal.get('rr_ratio', '-')), BOLD)}")
            print(f"  下单量: {qty:.6f} {symbol.split('/')[0]}")
            print(f"  占用资金: {qty * entry:,.2f} USDT")
            print(f"  原因: {signal.get('reason', '')}")

            # 模拟下单
            if action == "buy" and qty > 0:
                pos = account.open(symbol, "long", entry, qty, sl, tp, signal.get("strategy"))
                print(color(f"\n  ✓ [模拟] 多仓已开启", GREEN))
            elif action == "sell" and qty > 0:
                pos = account.open(symbol, "short", entry, qty, sl, tp, signal.get("strategy"))
                print(color(f"\n  ✓ [模拟] 空仓已开启", GREEN))

            results.append({
                "symbol": symbol,
                "market": market_type,
                "signal": action,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "qty": qty,
                "reason": signal.get("reason", "")
            })
        else:
            print(color(f"\n  ○  暂无交易信号（等待更好的入场机会）", YELLOW))
            results.append({"symbol": symbol, "market": market_type, "signal": "none"})

        time.sleep(0.3)  # 避免请求过快

    # ─── 止损止盈模拟演示 ────────────────────────────
    simulate_stop_tp(account, cfg)

    # ─── 汇总报告 ───────────────────────────────────
    print(color("\n" + "═"*55, BOLD))
    print(color("   模拟交易汇总报告", BOLD))
    print(color("═"*55, BOLD))
    print(f"  {'交易对':<12} {'行情':<10} {'信号':<10} {'入场价':<14} {'盈亏比'}")
    print(f"  {'─'*50}")

    for r in results:
        signal_color = GREEN if r["signal"] == "buy" else RED if r["signal"] == "sell" else YELLOW
        market_map = {"oscillation":"震荡","trend_up":"上升","trend_down":"下降"}
        m = market_map.get(r["market"], r["market"])
        s = r["signal"] if r["signal"] != "none" else "观望"
        entry_str = f"{r['entry']:>12,.4f}" if r.get("entry") else "       -"
        print(f"  {r['symbol']:<12} {m:<8} {color(s, signal_color):<20} {entry_str}")

    print(f"\n  {'─'*50}")
    print(f"  剩余持仓数: {len(account.positions)}")
    print(f"  当前净值:  {color(f'{account.capital:,.2f} USDT', BOLD)}")
    total_pnl = account.capital - account.initial_capital
    pnl_color = GREEN if total_pnl >= 0 else RED
    print(f"  总盈亏:    {color(f'{total_pnl:+,.2f} USDT ({account.pnl_pct():+.2f}%)', pnl_color)}")
    print(color("═"*55, BOLD))
    print(color(f"\n  模拟交易完成！以上为虚拟订单，未产生任何真实交易。", BLUE))
    print(color("  将 config/user_config.yaml 中的 paper_trading 改为 false", YELLOW))
    print(color("  并填入真实 API Key 即可开启实盘交易。\n", YELLOW))


# ─── 止损止盈模拟演示函数 ────────────────────────────────────────
def simulate_stop_tp(account: PaperAccount, cfg: dict):
    """
    用真实行情强制构造一个假仓位，然后模拟4种价格变动场景：
    ① 价格上涨 → 触发止盈
    ② 价格下跌 → 触发止损
    ③ 价格上涨途中 → 移动止损上移
    ④ 价格回撤触发移动止损
    """
    print(color("\n\n" + "═"*55, BOLD))
    print(color("   止损 / 止盈 逻辑演示", BOLD))
    print(color("   （用真实BTC价格构造假仓位，模拟价格变动）", BLUE))
    print(color("═"*55, BOLD))

    # 获取当前 BTC 真实价格作为基准
    btc_price = fetch_price_public("BTC/USDT")
    if not btc_price:
        btc_price = 65000.0
    print(f"\n  当前 BTC 真实价格: {color(f'{btc_price:,.2f} USDT', BOLD)}\n")

    risk = cfg["risk"]
    entry = btc_price
    sl    = round(entry * (1 - risk["stop_loss_pct"]), 2)      # 止损价
    tp    = round(entry * (1 + risk["take_profit_pct"]), 2)    # 止盈价
    trail_pct = cfg["strategy"]["trend"]["trailing_stop_pct"]   # 移动止损比例

    print(f"  假设开多仓:")
    print(f"  {'─'*45}")
    print(f"  入场价:  {color(f'{entry:>12,.2f}', BOLD)}")
    print(f"  止 损:   {color(f'{sl:>12,.2f}', RED)}   ({-risk['stop_loss_pct']*100:.1f}%)")
    print(f"  止 盈:   {color(f'{tp:>12,.2f}', GREEN)}  (+{risk['take_profit_pct']*100:.1f}%)")
    print(f"  移动止损: {trail_pct*100:.1f}% 跟随")

    # ─────────── 场景 ① 止盈触发 ───────────
    print(color(f"\n  场景① 价格上涨 → 触发止盈", BOLD))
    price_up = tp  # 价格到达止盈线
    pnl_pct  = (price_up - entry) / entry * 100
    pnl_usdt = (price_up - entry) * (cfg["risk"]["total_capital"]
                * risk["position_size_pct"] / entry)
    print(f"  价格变动: {entry:,.2f} → {color(f'{price_up:,.2f}', GREEN)}")
    print(f"  触发条件: 价格 {price_up:,.2f} ≥ 止盈线 {tp:,.2f}  ✓")
    print(color(f"  >> 系统执行：平仓！盈利 {pnl_pct:+.2f}% / +{pnl_usdt:,.2f} USDT", GREEN))

    # ─────────── 场景 ② 止损触发 ───────────
    print(color(f"\n  场景② 价格下跌 → 触发止损", BOLD))
    price_down = sl  # 价格跌至止损线
    loss_pct   = (price_down - entry) / entry * 100
    loss_usdt  = (price_down - entry) * (cfg["risk"]["total_capital"]
                 * risk["position_size_pct"] / entry)
    print(f"  价格变动: {entry:,.2f} → {color(f'{price_down:,.2f}', RED)}")
    print(f"  触发条件: 价格 {price_down:,.2f} ≤ 止损线 {sl:,.2f}  ✓")
    print(color(f"  >> 系统执行：平仓！亏损 {loss_pct:.2f}% / {loss_usdt:,.2f} USDT", RED))
    print(f"     单笔亏损控制在总资金的 {abs(loss_usdt)/cfg['risk']['total_capital']*100:.2f}%（设定上限 {risk['max_loss_per_trade']*100:.1f}%）")

    # ─────────── 场景 ③ 移动止损上移 ───────
    print(color(f"\n  场景③ 价格上涨途中 → 移动止损跟随上移", BOLD))
    trail_stop = round(entry * (1 - trail_pct), 2)
    steps = [
        entry * 1.01,
        entry * 1.015,
        entry * 1.02,
        entry * 1.025,
    ]
    print(f"  初始移动止损: {trail_stop:,.2f}")
    for p in steps:
        new_trail = round(p * (1 - trail_pct), 2)
        print(f"  价格涨至 {color(f'{p:,.2f}', GREEN)} → 移动止损上移至 {color(f'{new_trail:,.2f}', YELLOW)}"
              f"  (+{(new_trail-trail_stop)/entry*100:.2f}%)")
        trail_stop = new_trail

    # ─────────── 场景 ④ 回撤触发移动止损 ───
    print(color(f"\n  场景④ 价格回撤 → 移动止损被触发，保护利润", BOLD))
    peak_price  = entry * 1.025
    retrace     = trail_stop  # 价格跌回到移动止损
    locked_pnl  = (trail_stop - entry) / entry * 100
    locked_usdt = (trail_stop - entry) * (cfg["risk"]["total_capital"]
                  * risk["position_size_pct"] / entry)
    print(f"  最高涨至:    {color(f'{peak_price:,.2f}', GREEN)}")
    print(f"  价格回撤至:  {color(f'{retrace:,.2f}', YELLOW)}")
    print(f"  移动止损线:  {trail_stop:,.2f}  ✓ 触发")
    print(color(f"  >> 系统执行：平仓！锁定利润 {locked_pnl:+.2f}% / +{locked_usdt:,.2f} USDT", GREEN))
    print(f"     （未等跌回成本，已自动锁利出场）")

    print(color(f"\n  止损/止盈演示完毕。实盘中每 30 秒自动检查一次。\n", BLUE))


if __name__ == "__main__":
    run_paper_test()
