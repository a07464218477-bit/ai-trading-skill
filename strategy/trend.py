"""
趋势策略（Trend Strategy）
适用于单边行情，顺势而为
核心：均线交叉 + MACD + 成交量确认
"""
from typing import List, Dict, Optional
from core.market_analyzer import MarketAnalyzer


class TrendStrategy:

    def __init__(self, config: dict):
        self.cfg = config["strategy"]["trend"]
        self.risk = config["risk"]
        self.analyzer = MarketAnalyzer(config)

    def generate_signals(self, symbol: str, candles: List[dict],
                         market_type: str,
                         current_positions: List[dict]) -> Optional[Dict]:
        """
        生成趋势策略交易信号

        market_type: "trend_up" | "trend_down"
        """
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        current_price = closes[-1]

        # 计算指标
        ma_fast = self.analyzer.calc_ma(closes, self.cfg["ma_fast"])
        ma_slow = self.analyzer.calc_ma(closes, self.cfg["ma_slow"])
        ma_fast_prev = self.analyzer.calc_ma(closes[:-1], self.cfg["ma_fast"])
        ma_slow_prev = self.analyzer.calc_ma(closes[:-1], self.cfg["ma_slow"])

        macd, macd_sig, macd_hist = self.analyzer.calc_macd(
            closes,
            self.cfg["macd_fast"],
            self.cfg["macd_slow"],
            self.cfg["macd_signal"]
        )

        # 前一根K线的MACD
        _, _, macd_hist_prev = self.analyzer.calc_macd(
            closes[:-1],
            self.cfg["macd_fast"],
            self.cfg["macd_slow"],
            self.cfg["macd_signal"]
        )

        # 成交量确认
        vol_avg = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1]
        vol_current = volumes[-1]
        vol_confirm = vol_current >= vol_avg * self.cfg["volume_multiplier"]

        has_long = any(p["symbol"] == symbol and p["side"] == "long"
                       for p in current_positions)
        has_short = any(p["symbol"] == symbol and p["side"] == "short"
                        for p in current_positions)

        # ─── 做多信号 ───
        # 条件：金叉 + MACD翻正 + 成交量放大 + AI判断为上升趋势
        ma_golden_cross = ma_fast > ma_slow and ma_fast_prev <= ma_slow_prev
        macd_bullish = macd_hist > 0 and macd_hist_prev <= 0  # MACD柱翻正
        is_uptrend = market_type == "trend_up"

        if (not has_long
                and is_uptrend
                and (ma_golden_cross or (ma_fast > ma_slow and macd_bullish))
                and vol_confirm):

            stop_loss = current_price * (1 - self.risk["stop_loss_pct"])
            take_profit = current_price * (1 + self.risk["take_profit_pct"])
            trailing_stop = current_price * (1 - self.cfg["trailing_stop_pct"])

            reward = take_profit - current_price
            risk_amt = current_price - stop_loss
            rr_ratio = reward / risk_amt if risk_amt > 0 else 0

            if rr_ratio >= self.risk["risk_reward_ratio"]:
                reasons = []
                if ma_golden_cross:
                    reasons.append(f"均线金叉(MA{self.cfg['ma_fast']}/MA{self.cfg['ma_slow']})")
                if macd_bullish:
                    reasons.append("MACD金叉")
                if vol_confirm:
                    reasons.append(f"成交量放大({vol_current/vol_avg:.1f}x)")

                return {
                    "action": "buy",
                    "symbol": symbol,
                    "strategy": "trend",
                    "direction": "long",
                    "reason": " + ".join(reasons),
                    "entry_price": current_price,
                    "stop_loss": round(stop_loss, 6),
                    "take_profit": round(take_profit, 6),
                    "trailing_stop": round(trailing_stop, 6),
                    "size_pct": self.risk["position_size_pct"],
                    "rr_ratio": round(rr_ratio, 2),
                }

        # ─── 做空信号 ───
        # 条件：死叉 + MACD翻负 + 成交量放大 + AI判断为下降趋势
        ma_death_cross = ma_fast < ma_slow and ma_fast_prev >= ma_slow_prev
        macd_bearish = macd_hist < 0 and macd_hist_prev >= 0  # MACD柱翻负
        is_downtrend = market_type == "trend_down"

        if (not has_short
                and is_downtrend
                and (ma_death_cross or (ma_fast < ma_slow and macd_bearish))
                and vol_confirm):

            stop_loss = current_price * (1 + self.risk["stop_loss_pct"])
            take_profit = current_price * (1 - self.risk["take_profit_pct"])
            trailing_stop = current_price * (1 + self.cfg["trailing_stop_pct"])

            reward = current_price - take_profit
            risk_amt = stop_loss - current_price
            rr_ratio = reward / risk_amt if risk_amt > 0 else 0

            if rr_ratio >= self.risk["risk_reward_ratio"]:
                reasons = []
                if ma_death_cross:
                    reasons.append(f"均线死叉(MA{self.cfg['ma_fast']}/MA{self.cfg['ma_slow']})")
                if macd_bearish:
                    reasons.append("MACD死叉")
                if vol_confirm:
                    reasons.append(f"成交量放大({vol_current/vol_avg:.1f}x)")

                return {
                    "action": "sell",
                    "symbol": symbol,
                    "strategy": "trend",
                    "direction": "short",
                    "reason": " + ".join(reasons),
                    "entry_price": current_price,
                    "stop_loss": round(stop_loss, 6),
                    "take_profit": round(take_profit, 6),
                    "trailing_stop": round(trailing_stop, 6),
                    "size_pct": self.risk["position_size_pct"],
                    "rr_ratio": round(rr_ratio, 2),
                }

        # ─── 移动止损更新（保护利润）───
        for pos in current_positions:
            if pos["symbol"] != symbol:
                continue

            if pos["side"] == "long":
                # 更新移动止损：当价格上涨时，止损跟随上移
                new_trailing = current_price * (1 - self.cfg["trailing_stop_pct"])
                if new_trailing > pos.get("trailing_stop", 0):
                    return {
                        "action": "update_trailing_stop",
                        "symbol": symbol,
                        "strategy": "trend",
                        "new_trailing_stop": round(new_trailing, 6),
                        "reason": f"移动止损上移至 {new_trailing:.4f}"
                    }

                # 趋势反转 → 平仓
                if (ma_fast < ma_slow and macd_hist < 0) or \
                   current_price < pos.get("trailing_stop", 0):
                    return {
                        "action": "close_long",
                        "symbol": symbol,
                        "strategy": "trend",
                        "reason": "趋势反转信号，平多仓",
                        "entry_price": pos["entry_price"],
                        "current_price": current_price,
                        "pnl_pct": round(
                            (current_price - pos["entry_price"]) / pos["entry_price"] * 100, 2
                        )
                    }

            elif pos["side"] == "short":
                new_trailing = current_price * (1 + self.cfg["trailing_stop_pct"])
                if new_trailing < pos.get("trailing_stop", float("inf")):
                    return {
                        "action": "update_trailing_stop",
                        "symbol": symbol,
                        "strategy": "trend",
                        "new_trailing_stop": round(new_trailing, 6),
                        "reason": f"移动止损下移至 {new_trailing:.4f}"
                    }

                if (ma_fast > ma_slow and macd_hist > 0) or \
                   current_price > pos.get("trailing_stop", float("inf")):
                    return {
                        "action": "close_short",
                        "symbol": symbol,
                        "strategy": "trend",
                        "reason": "趋势反转信号，平空仓",
                        "entry_price": pos["entry_price"],
                        "current_price": current_price,
                        "pnl_pct": round(
                            (pos["entry_price"] - current_price) / pos["entry_price"] * 100, 2
                        )
                    }

        return None
