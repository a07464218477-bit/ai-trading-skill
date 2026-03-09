"""
震荡策略（Oscillation Strategy）
适用于横盘震荡行情，低买高卖
核心：布林带 + RSI 双重确认
"""
from typing import List, Dict, Optional
from core.market_analyzer import MarketAnalyzer


class OscillationStrategy:

    def __init__(self, config: dict):
        self.cfg = config["strategy"]["oscillation"]
        self.risk = config["risk"]
        self.analyzer = MarketAnalyzer(config)

    def generate_signals(self, symbol: str, candles: List[dict],
                         current_positions: List[dict]) -> Optional[Dict]:
        """
        生成震荡策略交易信号

        返回 signal 或 None（无信号）
        signal 格式:
        {
            "action": "buy" | "sell" | "close_long" | "close_short",
            "symbol": str,
            "reason": str,
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
            "size_pct": float,   # 使用总资金的百分比
        }
        """
        closes = [c["close"] for c in candles]
        current_price = closes[-1]

        # 计算指标
        rsi = self.analyzer.calc_rsi(closes)
        bb_upper, bb_mid, bb_lower = self.analyzer.calc_bollinger(
            closes,
            self.cfg["bollinger_period"],
            self.cfg["bollinger_std"]
        )
        atr = self.analyzer.calc_atr(candles)

        # 检查当前是否已有该交易对持仓
        has_long = any(p["symbol"] == symbol and p["side"] == "long"
                       for p in current_positions)
        has_short = any(p["symbol"] == symbol and p["side"] == "short"
                        for p in current_positions)

        # ─── 买入信号（超卖 + 触及下轨）───
        if (not has_long
                and rsi < self.cfg["rsi_oversold"]
                and current_price <= bb_lower * 1.005):  # 允许0.5%误差

            stop_loss = current_price * (1 - self.risk["stop_loss_pct"])
            take_profit = bb_mid  # 目标：回归中轨

            # 盈亏比检查
            reward = take_profit - current_price
            risk_amt = current_price - stop_loss
            rr_ratio = reward / risk_amt if risk_amt > 0 else 0

            if rr_ratio >= self.risk["risk_reward_ratio"]:
                return {
                    "action": "buy",
                    "symbol": symbol,
                    "strategy": "oscillation",
                    "reason": f"RSI超卖({rsi:.1f}) + 触及布林下轨({bb_lower:.4f})",
                    "entry_price": current_price,
                    "stop_loss": round(stop_loss, 6),
                    "take_profit": round(take_profit, 6),
                    "size_pct": self.risk["position_size_pct"],
                    "rr_ratio": round(rr_ratio, 2),
                    "atr": atr,
                }

        # ─── 卖出信号（超买 + 触及上轨）───
        if (not has_short
                and rsi > self.cfg["rsi_overbought"]
                and current_price >= bb_upper * 0.995):

            stop_loss = current_price * (1 + self.risk["stop_loss_pct"])
            take_profit = bb_mid  # 目标：回归中轨

            reward = current_price - take_profit
            risk_amt = stop_loss - current_price
            rr_ratio = reward / risk_amt if risk_amt > 0 else 0

            if rr_ratio >= self.risk["risk_reward_ratio"]:
                return {
                    "action": "sell",
                    "symbol": symbol,
                    "strategy": "oscillation",
                    "reason": f"RSI超买({rsi:.1f}) + 触及布林上轨({bb_upper:.4f})",
                    "entry_price": current_price,
                    "stop_loss": round(stop_loss, 6),
                    "take_profit": round(take_profit, 6),
                    "size_pct": self.risk["position_size_pct"],
                    "rr_ratio": round(rr_ratio, 2),
                    "atr": atr,
                }

        # ─── 平仓信号（已持仓时检查是否到达目标）───
        for pos in current_positions:
            if pos["symbol"] != symbol:
                continue

            if pos["side"] == "long":
                # 多仓：价格到达中轨或RSI进入超买区 → 平仓
                if current_price >= bb_mid or rsi > 60:
                    return {
                        "action": "close_long",
                        "symbol": symbol,
                        "strategy": "oscillation",
                        "reason": f"多仓止盈：价格({current_price:.4f}) 达到中轨({bb_mid:.4f})",
                        "entry_price": pos["entry_price"],
                        "current_price": current_price,
                        "pnl_pct": round(
                            (current_price - pos["entry_price"]) / pos["entry_price"] * 100, 2
                        )
                    }

            elif pos["side"] == "short":
                # 空仓：价格到达中轨或RSI进入超卖区 → 平仓
                if current_price <= bb_mid or rsi < 40:
                    return {
                        "action": "close_short",
                        "symbol": symbol,
                        "strategy": "oscillation",
                        "reason": f"空仓止盈：价格({current_price:.4f}) 达到中轨({bb_mid:.4f})",
                        "entry_price": pos["entry_price"],
                        "current_price": current_price,
                        "pnl_pct": round(
                            (pos["entry_price"] - current_price) / pos["entry_price"] * 100, 2
                        )
                    }

        return None  # 无信号

    def get_grid_levels(self, candles: List[dict]) -> List[dict]:
        """
        生成网格交易价格区间
        用于在震荡区间内布置多个买卖点
        """
        closes = [c["close"] for c in candles]
        atr = self.analyzer.calc_atr(candles)
        bb_upper, bb_mid, bb_lower = self.analyzer.calc_bollinger(closes)

        spacing = atr * self.cfg["grid_spacing_atr"]
        levels = []
        n = self.cfg["grid_levels"]

        for i in range(n):
            buy_price = bb_lower + i * spacing
            sell_price = buy_price + spacing
            if sell_price <= bb_upper:
                levels.append({
                    "level": i + 1,
                    "buy_price": round(buy_price, 6),
                    "sell_price": round(sell_price, 6),
                    "size_pct": self.risk["position_size_pct"] / n
                })

        return levels
