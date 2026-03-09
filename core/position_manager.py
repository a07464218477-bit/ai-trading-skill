"""
仓位管理器
负责止损、止盈、仓位大小计算、当日风险控制
"""
import json
import os
from datetime import date
from typing import List, Dict, Optional


class PositionManager:

    def __init__(self, config: dict):
        self.risk = config["risk"]
        self.positions_file = "logs/positions.json"
        self.daily_pnl_file = "logs/daily_pnl.json"
        self._ensure_files()

    def _ensure_files(self):
        os.makedirs("logs", exist_ok=True)
        if not os.path.exists(self.positions_file):
            self._save_positions([])
        if not os.path.exists(self.daily_pnl_file):
            self._save_daily_pnl({})

    # ─── 仓位文件操作 ─────────────────────────────────────────

    def _load_positions(self) -> List[dict]:
        with open(self.positions_file, "r") as f:
            return json.load(f)

    def _save_positions(self, positions: list):
        with open(self.positions_file, "w") as f:
            json.dump(positions, f, indent=2, ensure_ascii=False)

    def _load_daily_pnl(self) -> dict:
        with open(self.daily_pnl_file, "r") as f:
            return json.load(f)

    def _save_daily_pnl(self, data: dict):
        with open(self.daily_pnl_file, "w") as f:
            json.dump(data, f, indent=2)

    # ─── 仓位大小计算 ─────────────────────────────────────────

    def calc_position_size(self, total_capital: float, entry_price: float,
                           stop_loss: float) -> Dict:
        """
        根据风险计算合适的仓位大小
        使用固定风险法：每笔最多亏损总资金的 max_loss_per_trade
        """
        max_loss_amount = total_capital * self.risk["max_loss_per_trade"]
        risk_per_unit = abs(entry_price - stop_loss)

        if risk_per_unit <= 0:
            return {"quantity": 0, "cost": 0}

        quantity = max_loss_amount / risk_per_unit
        cost = quantity * entry_price

        # 不超过总资金的 position_size_pct
        max_cost = total_capital * self.risk["position_size_pct"]
        if cost > max_cost:
            cost = max_cost
            quantity = cost / entry_price

        return {
            "quantity": round(quantity, 6),
            "cost": round(cost, 2),
            "risk_amount": round(min(max_loss_amount, quantity * risk_per_unit), 2),
            "risk_pct": round(min(max_loss_amount, quantity * risk_per_unit) / total_capital * 100, 2)
        }

    # ─── 当日风险检查 ─────────────────────────────────────────

    def can_trade_today(self, total_capital: float) -> tuple:
        """
        检查今天是否还能交易
        返回: (是否可交易, 原因)
        """
        today = str(date.today())
        daily_pnl = self._load_daily_pnl()
        today_loss = daily_pnl.get(today, {}).get("loss", 0)

        max_loss = total_capital * self.risk["max_daily_loss"]
        if today_loss >= max_loss:
            return False, f"已达当日最大亏损限制 ({today_loss:.2f} / {max_loss:.2f} USDT)"

        positions = self._load_positions()
        if len(positions) >= self.risk["max_positions"]:
            return False, f"已达最大持仓数 ({len(positions)}/{self.risk['max_positions']})"

        return True, "可以交易"

    def record_daily_pnl(self, pnl: float):
        """记录当日盈亏"""
        today = str(date.today())
        data = self._load_daily_pnl()
        if today not in data:
            data[today] = {"profit": 0, "loss": 0, "trades": 0}
        if pnl >= 0:
            data[today]["profit"] += pnl
        else:
            data[today]["loss"] += abs(pnl)
        data[today]["trades"] += 1
        self._save_daily_pnl(data)

    # ─── 仓位操作 ─────────────────────────────────────────────

    def open_position(self, signal: dict, order_result: dict,
                      exchange: str) -> dict:
        """记录开仓"""
        positions = self._load_positions()

        position = {
            "id": f"{exchange}_{signal['symbol']}_{len(positions)+1}",
            "exchange": exchange,
            "symbol": signal["symbol"],
            "side": "long" if signal["action"] == "buy" else "short",
            "strategy": signal.get("strategy", "unknown"),
            "entry_price": signal["entry_price"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "trailing_stop": signal.get("trailing_stop", signal["stop_loss"]),
            "size_pct": signal.get("size_pct", 0.1),
            "order_id": order_result.get("orderId") or order_result.get("data", [{}])[0].get("ordId"),
            "open_time": str(date.today()),
            "status": "open"
        }
        positions.append(position)
        self._save_positions(positions)
        return position

    def close_position(self, symbol: str, exchange: str,
                       close_price: float) -> Optional[dict]:
        """记录平仓并计算盈亏"""
        positions = self._load_positions()
        closed = None

        for p in positions:
            if p["symbol"] == symbol and p["exchange"] == exchange \
               and p["status"] == "open":
                if p["side"] == "long":
                    pnl = (close_price - p["entry_price"]) / p["entry_price"]
                else:
                    pnl = (p["entry_price"] - close_price) / p["entry_price"]

                p["status"] = "closed"
                p["close_price"] = close_price
                p["pnl_pct"] = round(pnl * 100, 2)
                closed = p

                # 记录当日盈亏（估算）
                estimated_pnl = pnl * self.risk["total_capital"] * p["size_pct"]
                self.record_daily_pnl(estimated_pnl)
                break

        self._save_positions(positions)
        return closed

    def get_open_positions(self, exchange: Optional[str] = None) -> List[dict]:
        """获取所有未平仓位"""
        positions = self._load_positions()
        open_pos = [p for p in positions if p["status"] == "open"]
        if exchange:
            open_pos = [p for p in open_pos if p["exchange"] == exchange]
        return open_pos

    def update_trailing_stop(self, symbol: str, exchange: str,
                              new_stop: float):
        """更新移动止损"""
        positions = self._load_positions()
        for p in positions:
            if p["symbol"] == symbol and p["exchange"] == exchange \
               and p["status"] == "open":
                p["trailing_stop"] = new_stop
        self._save_positions(positions)

    def check_stop_triggers(self, current_prices: Dict[str, float]) -> List[dict]:
        """
        检查是否触发止损/止盈
        返回需要平仓的仓位列表
        """
        positions = self._load_positions()
        to_close = []

        for p in positions:
            if p["status"] != "open":
                continue
            symbol = p["symbol"]
            price = current_prices.get(symbol)
            if not price:
                continue

            if p["side"] == "long":
                # 止损：价格跌破止损线
                if price <= p["trailing_stop"] or price <= p["stop_loss"]:
                    to_close.append({
                        **p,
                        "close_reason": "触发止损",
                        "close_price": price
                    })
                # 止盈：价格达到目标
                elif price >= p["take_profit"]:
                    to_close.append({
                        **p,
                        "close_reason": "触发止盈",
                        "close_price": price
                    })

            elif p["side"] == "short":
                if price >= p["trailing_stop"] or price >= p["stop_loss"]:
                    to_close.append({
                        **p,
                        "close_reason": "触发止损",
                        "close_price": price
                    })
                elif price <= p["take_profit"]:
                    to_close.append({
                        **p,
                        "close_reason": "触发止盈",
                        "close_price": price
                    })

        return to_close

    def get_summary(self) -> dict:
        """获取仓位汇总"""
        positions = self._load_positions()
        today = str(date.today())
        daily_pnl = self._load_daily_pnl().get(today, {})

        open_pos = [p for p in positions if p["status"] == "open"]
        closed_pos = [p for p in positions if p["status"] == "closed"]

        return {
            "open_count": len(open_pos),
            "total_count": len(positions),
            "today_trades": daily_pnl.get("trades", 0),
            "today_profit": daily_pnl.get("profit", 0),
            "today_loss": daily_pnl.get("loss", 0),
            "today_net": daily_pnl.get("profit", 0) - daily_pnl.get("loss", 0),
            "open_positions": open_pos,
        }
