"""
价格监控器（高频）
独立于策略分析，专门负责持仓的止损/止盈/移动止损实时触发
策略分析：每 1 小时跑一次
价格监控：每 30 秒检查一次
"""
import time
import logging
import requests
from typing import Dict, List, Callable


def fetch_price_binance(symbol: str) -> float:
    """从 Binance 公开 API 获取最新价（无需 Key）"""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol.replace("/", "")},
            timeout=5
        )
        return float(r.json()["price"])
    except Exception as e:
        logging.warning(f"获取 {symbol} 价格失败: {e}")
        return 0.0


def fetch_price_okx(symbol: str) -> float:
    """从 OKX 公开 API 获取最新价（无需 Key）"""
    try:
        r = requests.get(
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": symbol.replace("/", "-")},
            timeout=5
        )
        data = r.json().get("data", [{}])
        return float(data[0].get("last", 0)) if data else 0.0
    except Exception as e:
        logging.warning(f"获取 OKX {symbol} 价格失败: {e}")
        return 0.0


class PriceMonitor:
    """
    持续监控持仓价格，触发止损/止盈/移动止损
    应在独立线程中运行
    """

    def __init__(self, position_mgr, exchanges: dict, cfg: dict,
                 on_trigger: Callable):
        """
        position_mgr: PositionManager 实例
        exchanges:    已初始化的交易所连接器字典
        cfg:          完整配置
        on_trigger:   触发止损/止盈时的回调函数 (接收 trigger_list)
        """
        self.position_mgr = position_mgr
        self.exchanges = exchanges
        self.cfg = cfg
        self.on_trigger = on_trigger
        self.running = False
        # 从配置读取监控频率，最低 5 秒，默认 30 秒
        raw = cfg.get("system", {}).get("monitor_interval", 30)
        self.check_interval = max(5, int(raw))

    def _get_current_prices(self) -> Dict[str, float]:
        """获取所有持仓交易对的最新价格"""
        positions = self.position_mgr.get_open_positions()
        prices = {}
        for p in positions:
            symbol = p["symbol"]
            if symbol in prices:
                continue
            exchange = p.get("exchange", "binance")
            if exchange == "binance":
                prices[symbol] = fetch_price_binance(symbol)
            elif exchange == "okx":
                prices[symbol] = fetch_price_okx(symbol)
        return prices

    def _update_trailing_stops(self, prices: Dict[str, float]):
        """更新所有多仓/空仓的移动止损"""
        positions = self.position_mgr.get_open_positions()
        trailing_pct = self.cfg["strategy"]["trend"]["trailing_stop_pct"]

        for p in positions:
            if p.get("strategy") != "trend":
                continue
            symbol = p["symbol"]
            price = prices.get(symbol, 0)
            if not price:
                continue

            if p["side"] == "long":
                new_trail = price * (1 - trailing_pct)
                if new_trail > p.get("trailing_stop", 0):
                    self.position_mgr.update_trailing_stop(
                        symbol, p["exchange"], new_trail)
                    logging.info(
                        f"[移动止损] {symbol} 多仓止损上移至 {new_trail:.4f} "
                        f"(当前价 {price:.4f})"
                    )

            elif p["side"] == "short":
                new_trail = price * (1 + trailing_pct)
                if new_trail < p.get("trailing_stop", float("inf")):
                    self.position_mgr.update_trailing_stop(
                        symbol, p["exchange"], new_trail)
                    logging.info(
                        f"[移动止损] {symbol} 空仓止损下移至 {new_trail:.4f} "
                        f"(当前价 {price:.4f})"
                    )

    def check_once(self) -> List[dict]:
        """
        执行一次价格检查
        返回触发止损/止盈的仓位列表
        """
        positions = self.position_mgr.get_open_positions()
        if not positions:
            return []

        prices = self._get_current_prices()
        if not prices:
            return []

        # 先更新移动止损
        self._update_trailing_stops(prices)

        # 再检查是否触发
        triggers = self.position_mgr.check_stop_triggers(prices)

        for t in triggers:
            reason = t.get("close_reason", "触发止损/止盈")
            symbol = t["symbol"]
            exchange = t.get("exchange", "binance")
            close_price = t["close_price"]
            connector = self.exchanges.get(exchange)

            try:
                if connector and exchange != "polymarket":
                    side = "SELL" if t["side"] == "long" else "BUY"
                    connector.place_order(symbol, side, "MARKET", 0)

                closed = self.position_mgr.close_position(
                    symbol, exchange, close_price)

                if closed:
                    pnl_pct = closed.get("pnl_pct", 0)
                    pnl_color = "盈利" if pnl_pct >= 0 else "亏损"
                    logging.info(
                        f"[{reason}] {symbol} {t['side']} "
                        f"入场:{t['entry_price']:.4f} "
                        f"平仓:{close_price:.4f} "
                        f"{pnl_color}:{pnl_pct:+.2f}%"
                    )
            except Exception as e:
                logging.error(f"执行平仓失败 {symbol}: {e}")

        return triggers

    def run(self):
        """持续运行监控循环（阻塞）"""
        self.running = True
        logging.info(f"价格监控器启动，每 {self.check_interval} 秒检查一次")

        while self.running:
            try:
                triggers = self.check_once()
                if triggers:
                    self.on_trigger(triggers)
            except Exception as e:
                logging.error(f"监控循环异常: {e}")
            time.sleep(self.check_interval)

    def stop(self):
        self.running = False
        logging.info("价格监控器已停止")
