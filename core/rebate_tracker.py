"""
返佣追踪器
追踪平台返佣收益和利润分成
"""
import json
import os
from datetime import date, datetime


class RebateTracker:

    def __init__(self, config: dict):
        self.cfg = config.get("rebate", {})
        self.profit_share_pct = self.cfg.get("profit_share_pct", 0.05)
        self.profit_share_wallet = self.cfg.get("profit_share_wallet", "")
        self.report_file = "logs/rebate_report.json"
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs("logs", exist_ok=True)
        if not os.path.exists(self.report_file):
            self._save({})

    def _load(self) -> dict:
        with open(self.report_file, "r") as f:
            return json.load(f)

    def _save(self, data: dict):
        with open(self.report_file, "w") as f:
            json.dump(data, f, indent=2)

    def record_trade_profit(self, exchange: str, symbol: str,
                             profit_usdt: float):
        """记录每笔盈利，计算应提取的利润分成"""
        if profit_usdt <= 0:
            return

        data = self._load()
        month = datetime.now().strftime("%Y-%m")
        if month not in data:
            data[month] = {
                "total_profit": 0,
                "profit_share_owed": 0,
                "trades": []
            }

        share = round(profit_usdt * self.profit_share_pct, 4)
        data[month]["total_profit"] += profit_usdt
        data[month]["profit_share_owed"] += share
        data[month]["trades"].append({
            "date": str(date.today()),
            "exchange": exchange,
            "symbol": symbol,
            "profit": profit_usdt,
            "share": share
        })
        self._save(data)

    def get_monthly_summary(self, month: str = None) -> dict:
        """获取月度汇总"""
        if not month:
            month = datetime.now().strftime("%Y-%m")
        data = self._load()
        return data.get(month, {
            "total_profit": 0,
            "profit_share_owed": 0,
            "trades": []
        })

    def print_report(self):
        """打印收益报告"""
        data = self._load()
        print("\n" + "═" * 45)
        print("  收益与返佣报告")
        print("═" * 45)
        total_profit = 0
        total_share = 0
        for month, info in sorted(data.items()):
            p = info.get("total_profit", 0)
            s = info.get("profit_share_owed", 0)
            t = len(info.get("trades", []))
            total_profit += p
            total_share += s
            print(f"  {month}  盈利:{p:>10.2f} USDT  "
                  f"应分成:{s:>8.2f} USDT  交易:{t}次")
        print("─" * 45)
        print(f"  累计盈利: {total_profit:.2f} USDT")
        print(f"  累计应付分成: {total_share:.2f} USDT ({self.profit_share_pct*100:.0f}%)")
        if self.profit_share_wallet:
            print(f"  分成收款地址: {self.profit_share_wallet}")
        print("═" * 45)
