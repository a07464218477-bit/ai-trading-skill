"""
OKX 交易所连接器
支持现货和合约，含经纪商返佣
"""
import hmac
import hashlib
import base64
import time
import json
import requests
from typing import Optional
from datetime import datetime, timezone


class OKXConnector:
    BASE_URL = "https://www.okx.com"
    BASE_URL_TESTNET = "https://www.okx.com"  # OKX 测试网同域名，需传 x-simulated-trading

    def __init__(self, api_key: str, api_secret: str, passphrase: str,
                 testnet: bool = False, broker_id: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.broker_id = broker_id  # 经纪商返佣ID
        self.testnet = testnet
        self.base_url = self.BASE_URL
        self.session = requests.Session()

    def _get_timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = timestamp + method.upper() + path + body
        mac = hmac.new(self.api_secret.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        ts = self._get_timestamp()
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": self._sign(ts, method, path, body),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if self.broker_id:
            headers["OK-ACCESS-BROKER"] = self.broker_id
        if self.testnet:
            headers["x-simulated-trading"] = "1"
        return headers

    def _get(self, path: str, params: dict = None) -> dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        headers = self._headers("GET", path + query)
        r = self.session.get(f"{self.base_url}{path}", headers=headers, params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        body = json.dumps(data)
        headers = self._headers("POST", path, body)
        r = self.session.post(f"{self.base_url}{path}", headers=headers, data=body)
        r.raise_for_status()
        return r.json()

    def get_balance(self, currency: str = "USDT") -> float:
        """获取账户余额"""
        result = self._get("/api/v5/account/balance", {"ccy": currency})
        try:
            details = result["data"][0]["details"]
            for d in details:
                if d["ccy"] == currency:
                    return float(d["availEq"] or d["cashBal"])
        except (KeyError, IndexError):
            pass
        return 0.0

    def get_klines(self, symbol: str, bar: str = "1H", limit: int = 100) -> list:
        """获取K线"""
        inst_id = symbol.replace("/", "-")
        result = self._get("/api/v5/market/candles", {
            "instId": inst_id,
            "bar": bar,
            "limit": str(limit)
        })
        candles = []
        for c in result.get("data", []):
            candles.append({
                "timestamp": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })
        return list(reversed(candles))

    def get_ticker(self, symbol: str) -> dict:
        """获取当前价格"""
        inst_id = symbol.replace("/", "-")
        result = self._get("/api/v5/market/ticker", {"instId": inst_id})
        return result.get("data", [{}])[0]

    def place_order(self, symbol: str, side: str, order_type: str,
                    size: float, price: Optional[float] = None,
                    td_mode: str = "cash") -> dict:
        """下单"""
        inst_id = symbol.replace("/", "-")
        data = {
            "instId": inst_id,
            "tdMode": td_mode,      # cash=现货, cross=全仓, isolated=逐仓
            "side": side.lower(),   # buy / sell
            "ordType": order_type.lower(),  # market / limit
            "sz": str(round(size, 6)),
        }
        if order_type.lower() == "limit" and price:
            data["px"] = str(price)

        return self._post("/api/v5/trade/order", data)

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        """取消订单"""
        inst_id = symbol.replace("/", "-")
        return self._post("/api/v5/trade/cancel-order", {
            "instId": inst_id,
            "ordId": order_id
        })

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """获取未成交订单"""
        params = {"ordType": "limit"}
        if symbol:
            params["instId"] = symbol.replace("/", "-")
        result = self._get("/api/v5/trade/orders-pending", params)
        return result.get("data", [])

    def get_positions(self) -> list:
        """获取持仓"""
        result = self._get("/api/v5/account/positions")
        return result.get("data", [])

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            result = self._get("/api/v5/public/time")
            return result.get("code") == "0"
        except Exception:
            return False
