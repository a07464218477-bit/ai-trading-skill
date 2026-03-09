"""
市场分析引擎
AI 判断当前是震荡行情还是趋势行情
"""
import numpy as np
from typing import List, Dict, Tuple


class MarketAnalyzer:

    def __init__(self, config: dict):
        self.adx_trend_threshold = config["strategy"]["analysis"]["adx_trend_threshold"]
        self.adx_range_threshold = config["strategy"]["analysis"]["adx_range_threshold"]

    # ─── 技术指标计算 ───────────────────────────────────────────

    def calc_rsi(self, closes: List[float], period: int = 14) -> float:
        """计算 RSI"""
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def calc_atr(self, candles: List[dict], period: int = 14) -> float:
        """计算 ATR（平均真实波幅）"""
        if len(candles) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return round(np.mean(trs[-period:]), 6)

    def calc_adx(self, candles: List[dict], period: int = 14) -> float:
        """计算 ADX（趋势强度）"""
        if len(candles) < period * 2:
            return 0.0
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]

        plus_dm, minus_dm, tr_list = [], [], []
        for i in range(1, len(candles)):
            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            plus_dm.append(up if up > down and up > 0 else 0)
            minus_dm.append(down if down > up and down > 0 else 0)
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
            tr_list.append(tr)

        def smooth(data, n):
            result = [sum(data[:n])]
            for v in data[n:]:
                result.append(result[-1] - result[-1] / n + v)
            return result

        sm_tr = smooth(tr_list, period)
        sm_plus = smooth(plus_dm, period)
        sm_minus = smooth(minus_dm, period)

        dx_list = []
        for i in range(len(sm_tr)):
            if sm_tr[i] == 0:
                continue
            di_plus = 100 * sm_plus[i] / sm_tr[i]
            di_minus = 100 * sm_minus[i] / sm_tr[i]
            diff = abs(di_plus - di_minus)
            total = di_plus + di_minus
            dx_list.append(100 * diff / total if total != 0 else 0)

        if len(dx_list) < period:
            return 0.0
        return round(np.mean(dx_list[-period:]), 2)

    def calc_bollinger(self, closes: List[float], period: int = 20,
                       std_mult: float = 2.0) -> Tuple[float, float, float]:
        """计算布林带，返回 (上轨, 中轨, 下轨)"""
        if len(closes) < period:
            mid = closes[-1]
            return mid * 1.02, mid, mid * 0.98
        recent = closes[-period:]
        mid = np.mean(recent)
        std = np.std(recent)
        return mid + std_mult * std, mid, mid - std_mult * std

    def calc_macd(self, closes: List[float], fast: int = 12, slow: int = 26,
                  signal: int = 9) -> Tuple[float, float, float]:
        """计算 MACD，返回 (macd线, 信号线, 柱状图)"""
        def ema(data, n):
            k = 2 / (n + 1)
            result = [data[0]]
            for v in data[1:]:
                result.append(v * k + result[-1] * (1 - k))
            return result

        if len(closes) < slow + signal:
            return 0.0, 0.0, 0.0
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = ema(macd_line, signal)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        return (round(macd_line[-1], 6),
                round(signal_line[-1], 6),
                round(histogram[-1], 6))

    def calc_ma(self, closes: List[float], period: int) -> float:
        """计算移动均线"""
        if len(closes) < period:
            return closes[-1]
        return round(np.mean(closes[-period:]), 6)

    # ─── 市场状态判断 ────────────────────────────────────────────

    def analyze(self, candles: List[dict]) -> Dict:
        """
        分析市场状态，返回综合分析结果

        返回:
            market_type: "oscillation" | "trend_up" | "trend_down"
            confidence: 0~100
            signals: 各指标数值
            recommendation: 策略建议
        """
        closes = [c["close"] for c in candles]
        current_price = closes[-1]

        # 计算所有指标
        rsi = self.calc_rsi(closes)
        atr = self.calc_atr(candles)
        adx = self.calc_adx(candles)
        bb_upper, bb_mid, bb_lower = self.calc_bollinger(closes)
        macd, macd_sig, macd_hist = self.calc_macd(closes)
        ma20 = self.calc_ma(closes, 20)
        ma60 = self.calc_ma(closes, 60)

        # 成交量分析
        volumes = [c["volume"] for c in candles]
        vol_avg = np.mean(volumes[-20:])
        vol_current = volumes[-1]
        vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1.0

        # ── 判断逻辑 ──
        trend_score = 0
        oscillation_score = 0

        # ADX 判断（最重要指标）
        if adx > self.adx_trend_threshold:
            trend_score += 40
        elif adx < self.adx_range_threshold:
            oscillation_score += 40
        else:
            oscillation_score += 20

        # 布林带宽度
        bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0
        if bb_width > 0.04:        # 布林带扩张 → 趋势
            trend_score += 20
        elif bb_width < 0.02:      # 布林带收缩 → 震荡
            oscillation_score += 20

        # 均线排列
        if ma20 > ma60 * 1.005:    # 快线明显在慢线上方 → 上升趋势
            trend_score += 20
        elif ma20 < ma60 * 0.995:  # 快线明显在慢线下方 → 下降趋势
            trend_score += 20
        else:                       # 均线缠绕 → 震荡
            oscillation_score += 20

        # MACD
        if abs(macd_hist) > 0:
            trend_score += 10
        else:
            oscillation_score += 10

        # 成交量
        if vol_ratio > 1.5:
            trend_score += 10

        # ── 最终判断 ──
        if trend_score > oscillation_score:
            if ma20 > ma60:
                market_type = "trend_up"
                recommendation = "使用趋势策略，方向：做多"
            else:
                market_type = "trend_down"
                recommendation = "使用趋势策略，方向：做空"
            confidence = min(100, int(trend_score * 1.2))
        else:
            market_type = "oscillation"
            recommendation = "使用震荡策略，低买高卖"
            confidence = min(100, int(oscillation_score * 1.2))

        return {
            "market_type": market_type,
            "confidence": confidence,
            "recommendation": recommendation,
            "signals": {
                "price": current_price,
                "rsi": rsi,
                "adx": adx,
                "atr": atr,
                "macd": macd,
                "macd_signal": macd_sig,
                "macd_hist": macd_hist,
                "bb_upper": round(bb_upper, 4),
                "bb_mid": round(bb_mid, 4),
                "bb_lower": round(bb_lower, 4),
                "ma20": ma20,
                "ma60": ma60,
                "vol_ratio": round(vol_ratio, 2),
            },
            "scores": {
                "trend": trend_score,
                "oscillation": oscillation_score
            }
        }

    def format_report(self, symbol: str, analysis: dict) -> str:
        """格式化市场分析报告"""
        s = analysis["signals"]
        type_map = {
            "oscillation": "震荡行情",
            "trend_up": "上升趋势",
            "trend_down": "下降趋势"
        }
        market_cn = type_map.get(analysis["market_type"], "未知")
        return f"""
┌─────────────────────────────────────┐
│  市场分析: {symbol:<20}     │
├─────────────────────────────────────┤
│  市场状态: {market_cn}  (置信度 {analysis['confidence']}%)
│  建议策略: {analysis['recommendation']}
├─── 技术指标 ────────────────────────┤
│  当前价格: {s['price']}
│  RSI:      {s['rsi']}  ({'超卖' if s['rsi'] < 35 else '超买' if s['rsi'] > 65 else '中性'})
│  ADX:      {s['adx']}  ({'强趋势' if s['adx'] > 25 else '弱趋势/震荡'})
│  MACD:     {s['macd']}  柱: {s['macd_hist']}
│  布林上轨: {s['bb_upper']}
│  布林中轨: {s['bb_mid']}
│  布林下轨: {s['bb_lower']}
│  MA20/60:  {s['ma20']} / {s['ma60']}
│  成交量比: {s['vol_ratio']}x
└─────────────────────────────────────┘"""
