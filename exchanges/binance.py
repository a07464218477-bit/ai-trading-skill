"""
币安交易所连接器
支持现货和合约交易
"""
import hmac
import hashlib
import time
import requests
from typing import Optional


class BinanceConnector:
    BASE_URL = "https://api.binance.com"
    BASE_URL_TESTNET = "https://testnet.binance.vision"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False,
                 ref_id: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.ref_id = ref_id  # 返佣ID
        self.base_url = self.BASE_URL_TESTNET if testnet else self.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json"
        })

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        sig = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params

    def get_account(self) -> dict:
        """获取账户信息"""
        params = self._sign({})
        r = self.session.get(f"{self.base_url}/api/v3/account", params=params)
        r.raise_for_status()
        return r.json()

    def get_balance(self, asset: str = "USDT") -> float:
        """获取指定资产余额"""
        account = self.get_account()
        for b in account.get("balances", []):
            if b["asset"] == asset:
                return float(b["free"])
        return 0.0

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> list:
        """获取K线数据"""
        symbol_fmt = symbol.replace("/", "")
        params = {"symbol": symbol_fmt, "interval": interval, "limit": limit}
        r = self.session.get(f"{self.base_url}/api/v3/klines", params=params)
        r.raise_for_status()
        raw = r.json()
        return [{
            "timestamp": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5])
        } for c in raw]

    def get_ticker(self, symbol: str) -> dict:
        """获取当前价格"""
        symbol_fmt = symbol.replace("/", "")
        r = self.session.get(f"{self.base_url}/api/v3/ticker/price",
                             params={"symbol": symbol_fmt})
        r.raise_for_status()
        return r.json()

    def place_order(self, symbol: str, side: str, order_type: str,
                    quantity: float, price: Optional[float] = None) -> dict:
        """下单"""
        symbol_fmt = symbol.replace("/", "")
        params = {
            "symbol": symbol_fmt,
            "side": side.upper(),       # BUY / SELL
            "type": order_type.upper(), # MARKET / LIMIT
            "quantity": round(quantity, 6),
        }
        if order_type.upper() == "LIMIT" and price:
            params["price"] = price
            params["timeInForce"] = "GTC"

        params = self._sign(params)
        r = self.session.post(f"{self.base_url}/api/v3/order", params=params)
        r.raise_for_status()
        return r.json()

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """取消订单"""
        symbol_fmt = symbol.replace("/", "")
        params = self._sign({"symbol": symbol_fmt, "orderId": order_id})
        r = self.session.delete(f"{self.base_url}/api/v3/order", params=params)
        r.raise_for_status()
        return r.json()

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """获取未成交订单"""
        params = {}
        if symbol:
            params["symbol"] = symbol.replace("/", "")
        params = self._sign(params)
        r = self.session.get(f"{self.base_url}/api/v3/openOrders", params=params)
        r.raise_for_status()
        return r.json()

    def get_positions(self) -> list:
        """获取持仓（基于账户余额推算）"""
        account = self.get_account()
        positions = []
        for b in account.get("balances", []):
            free = float(b["free"])
            locked = float(b["locked"])
            if free + locked > 0 and b["asset"] != "USDT":
                positions.append({
                    "asset": b["asset"],
                    "free": free,
                    "locked": locked,
                    "total": free + locked
                })
        return positions

    def test_connection(self) -> bool:
        """测试API连接"""
        try:
            r = self.session.get(f"{self.base_url}/api/v3/ping")
            return r.status_code == 200
        except Exception:
            return False
