"""
Polymarket 连接器
基于 CLOB API（预测市场）
"""
import json
import time
import requests
from typing import Optional
from eth_account import Account
from eth_account.messages import encode_defunct


class PolymarketConnector:
    CLOB_URL = "https://clob.polymarket.com"
    GAMMA_URL = "https://gamma-api.polymarket.com"

    def __init__(self, private_key: str, proxy_address: str = "",
                 chain_id: int = 137):
        self.private_key = private_key
        self.proxy_address = proxy_address
        self.chain_id = chain_id  # 137 = Polygon Mainnet
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._api_key = None
        self._api_secret = None
        self._passphrase = None

    def _sign_message(self, message: str) -> str:
        msg = encode_defunct(text=message)
        signed = self.account.sign_message(msg)
        return signed.signature.hex()

    def get_api_credentials(self) -> dict:
        """获取/创建 CLOB API Key"""
        timestamp = str(int(time.time()))
        message = f"{self.address}{timestamp}"
        signature = self._sign_message(message)
        r = self.session.post(f"{self.CLOB_URL}/auth/api-key", json={
            "address": self.address,
            "timestamp": timestamp,
            "signature": signature,
        })
        r.raise_for_status()
        data = r.json()
        self._api_key = data.get("apiKey")
        self._api_secret = data.get("secret")
        self._passphrase = data.get("passphrase")
        return data

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        if not self._api_key:
            self.get_api_credentials()
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method.upper() + path + body
        signed = self._sign_message(message)
        return {
            "POLY_ADDRESS": self.address,
            "POLY_SIGNATURE": signed,
            "POLY_TIMESTAMP": timestamp,
            "POLY_API_KEY": self._api_key,
        }

    def get_markets(self, limit: int = 20, min_liquidity: float = 10000) -> list:
        """获取活跃市场列表"""
        r = self.session.get(f"{self.GAMMA_URL}/markets", params={
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false"
        })
        r.raise_for_status()
        markets = r.json()
        # 过滤流动性
        filtered = [m for m in markets
                    if float(m.get("volume24hr", 0)) >= min_liquidity]
        return filtered

    def get_orderbook(self, token_id: str) -> dict:
        """获取订单簿"""
        r = self.session.get(f"{self.CLOB_URL}/book", params={"token_id": token_id})
        r.raise_for_status()
        return r.json()

    def get_balance(self) -> float:
        """获取 USDC 余额"""
        headers = self._auth_headers("GET", "/balance")
        r = self.session.get(f"{self.CLOB_URL}/balance", headers=headers)
        r.raise_for_status()
        data = r.json()
        return float(data.get("balance", 0))

    def place_order(self, token_id: str, side: str, price: float,
                    size: float, order_type: str = "GTC") -> dict:
        """
        下单
        token_id: 市场代币ID（YES/NO token）
        side: BUY / SELL
        price: 0~1 之间（概率）
        size: USDC 金额
        """
        body = json.dumps({
            "tokenID": token_id,
            "side": side.upper(),
            "price": str(price),
            "size": str(size),
            "orderType": order_type,
        })
        headers = self._auth_headers("POST", "/order", body)
        r = self.session.post(f"{self.CLOB_URL}/order",
                              headers=headers, data=body)
        r.raise_for_status()
        return r.json()

    def cancel_order(self, order_id: str) -> dict:
        """取消订单"""
        body = json.dumps({"orderID": order_id})
        headers = self._auth_headers("DELETE", "/order", body)
        r = self.session.delete(f"{self.CLOB_URL}/order",
                                headers=headers, data=body)
        r.raise_for_status()
        return r.json()

    def get_open_orders(self) -> list:
        """获取未成交订单"""
        headers = self._auth_headers("GET", "/orders")
        r = self.session.get(f"{self.CLOB_URL}/orders", headers=headers,
                             params={"maker_address": self.address})
        r.raise_for_status()
        return r.json()

    def get_positions(self) -> list:
        """获取当前持仓"""
        headers = self._auth_headers("GET", "/positions")
        r = self.session.get(f"{self.CLOB_URL}/positions", headers=headers,
                             params={"user": self.address})
        r.raise_for_status()
        return r.json()

    def analyze_market_sentiment(self, market: dict) -> dict:
        """
        分析预测市场情绪（用于 AI 判断策略）
        返回: YES概率、流动性、24h变化
        """
        outcomes = market.get("outcomes", [])
        yes_price = 0.5
        no_price = 0.5
        for o in outcomes:
            if o.get("outcome") == "Yes":
                yes_price = float(o.get("price", 0.5))
            elif o.get("outcome") == "No":
                no_price = float(o.get("price", 0.5))
        return {
            "market_id": market.get("conditionId"),
            "question": market.get("question"),
            "yes_price": yes_price,
            "no_price": no_price,
            "volume_24h": float(market.get("volume24hr", 0)),
            "total_liquidity": float(market.get("liquidity", 0)),
            "end_date": market.get("endDate"),
        }

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            r = self.session.get(f"{self.CLOB_URL}/time")
            return r.status_code == 200
        except Exception:
            return False
