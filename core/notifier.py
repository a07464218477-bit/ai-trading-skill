"""
统一通知模块
支持：Telegram / 微信(PushPlus/Server酱) / 飞书 / QQ(go-cqhttp)
所有通道并发发送，任一失败不影响其他通道
"""
import json
import logging
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List


class Notifier:

    def __init__(self, cfg: dict):
        self.notify_cfg = cfg.get("notifications", {})
        self.executor = ThreadPoolExecutor(max_workers=5)

    # ─────────────────────────────────────────────────────────
    #  公共入口（并发发所有已启用通道）
    # ─────────────────────────────────────────────────────────

    def send(self, title: str, body: str, level: str = "info"):
        """
        向所有启用的通道发送通知
        level: info / warning / success / danger
        """
        futures = []
        cfg = self.notify_cfg

        if cfg.get("telegram", {}).get("enabled"):
            futures.append(self.executor.submit(
                self._telegram, title, body, level))

        if cfg.get("wechat_pushplus", {}).get("enabled"):
            futures.append(self.executor.submit(
                self._wechat_pushplus, title, body))

        if cfg.get("wechat_ftqq", {}).get("enabled"):
            futures.append(self.executor.submit(
                self._wechat_ftqq, title, body))

        if cfg.get("feishu", {}).get("enabled"):
            futures.append(self.executor.submit(
                self._feishu, title, body, level))

        if cfg.get("qq", {}).get("enabled"):
            futures.append(self.executor.submit(
                self._qq, title, body))

        # 收集结果（不阻塞主流程）
        for f in futures:
            try:
                f.result(timeout=10)
            except Exception as e:
                logging.warning(f"通知发送异常: {e}")

    # ─────────────────────────────────────────────────────────
    #  预置消息模板（交易场景）
    # ─────────────────────────────────────────────────────────

    def notify_open(self, signal: dict):
        """开仓通知"""
        side_cn = "做多 ▲" if signal.get("action") == "buy" else "做空 ▼"
        strategy_cn = "震荡策略" if signal.get("strategy") == "oscillation" else "趋势策略"
        title = f"【开仓】{signal.get('symbol')} {side_cn}"
        body = (
            f"交易所：{signal.get('exchange', '').upper()}\n"
            f"策略：{strategy_cn}\n"
            f"入场价：{signal.get('entry_price', 0):,.4f}\n"
            f"止  损：{signal.get('stop_loss', 0):,.4f}\n"
            f"止  盈：{signal.get('take_profit', 0):,.4f}\n"
            f"盈亏比：{signal.get('rr_ratio', '-')}\n"
            f"原  因：{signal.get('reason', '')}\n"
            f"时  间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send(title, body, level="info")

    def notify_close(self, symbol: str, exchange: str, side: str,
                     entry: float, close_price: float, pnl_pct: float,
                     reason: str):
        """平仓通知"""
        is_profit = pnl_pct >= 0
        emoji = "✅" if is_profit else "❌"
        title = f"{emoji}【平仓】{symbol}  {pnl_pct:+.2f}%"
        body = (
            f"交易所：{exchange.upper()}\n"
            f"方  向：{'多仓' if side == 'long' else '空仓'}\n"
            f"入场价：{entry:,.4f}\n"
            f"平仓价：{close_price:,.4f}\n"
            f"盈  亏：{pnl_pct:+.2f}%\n"
            f"原  因：{reason}\n"
            f"时  间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        level = "success" if is_profit else "danger"
        self.send(title, body, level=level)

    def notify_signal(self, symbol: str, market_type: str, analysis: dict):
        """市场分析信号通知"""
        type_map = {"oscillation": "震荡行情", "trend_up": "上升趋势", "trend_down": "下降趋势"}
        title = f"【分析】{symbol}  {type_map.get(market_type, market_type)}"
        s = analysis.get("signals", {})
        body = (
            f"市场状态：{type_map.get(market_type)}\n"
            f"置信度：{analysis.get('confidence')}%\n"
            f"RSI：{s.get('rsi', 0):.1f}\n"
            f"ADX：{s.get('adx', 0):.1f}\n"
            f"建议：{analysis.get('recommendation', '')}\n"
            f"时  间：{datetime.now().strftime('%H:%M:%S')}"
        )
        self.send(title, body, level="info")

    def notify_daily_report(self, summary: dict):
        """每日收益报告"""
        net = summary.get("today_net", 0)
        emoji = "📈" if net >= 0 else "📉"
        title = f"{emoji}【日报】今日净盈亏 {net:+.2f} USDT"
        body = (
            f"今日交易：{summary.get('today_trades', 0)} 次\n"
            f"今日盈利：+{summary.get('today_profit', 0):.2f} USDT\n"
            f"今日亏损：-{summary.get('today_loss', 0):.2f} USDT\n"
            f"净盈亏：{net:+.2f} USDT\n"
            f"当前持仓：{summary.get('open_count', 0)} 个\n"
            f"统计时间：{datetime.now().strftime('%Y-%m-%d')}"
        )
        self.send(title, body, level="info")

    def notify_error(self, msg: str):
        """系统异常通知"""
        self.send("⚠️【系统告警】", msg, level="warning")

    # ─────────────────────────────────────────────────────────
    #  Telegram
    # ─────────────────────────────────────────────────────────

    def _telegram(self, title: str, body: str, level: str = "info"):
        """
        配置方式：
        1. 向 @BotFather 创建 Bot，获取 bot_token
        2. 向 @userinfobot 获取你的 chat_id
        """
        cfg = self.notify_cfg.get("telegram", {})
        token = cfg.get("bot_token", "")
        chat_id = cfg.get("chat_id", "")
        if not token or not chat_id:
            return

        text = f"*{self._escape_md(title)}*\n\n{self._escape_md(body)}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2"
        }, timeout=10)
        r.raise_for_status()
        logging.debug("Telegram 通知发送成功")

    @staticmethod
    def _escape_md(text: str) -> str:
        """转义 Telegram MarkdownV2 特殊字符"""
        for ch in r"_*[]()~`>#+-=|{}.!":
            text = text.replace(ch, f"\\{ch}")
        return text

    # ─────────────────────────────────────────────────────────
    #  微信 - PushPlus（推荐，直接推到个人微信）
    # ─────────────────────────────────────────────────────────

    def _wechat_pushplus(self, title: str, body: str):
        """
        PushPlus 微信推送
        配置方式：
        1. 访问 https://www.pushplus.plus 注册
        2. 获取 token（在个人中心）
        3. 扫码关注公众号后即可接收消息
        """
        cfg = self.notify_cfg.get("wechat_pushplus", {})
        token = cfg.get("token", "")
        if not token:
            return

        # 构造 HTML 格式消息（PushPlus 支持）
        html_body = body.replace("\n", "<br>")

        r = requests.post("https://www.pushplus.plus/send", json={
            "token": token,
            "title": title,
            "content": f"<p>{html_body}</p>",
            "template": "html",
            "channel": cfg.get("channel", "wechat"),  # wechat / webhook / cp / sms
            "topic": cfg.get("topic", "")              # 群组推送用（空=只推自己）
        }, timeout=10)
        data = r.json()
        if data.get("code") != 200:
            logging.warning(f"PushPlus 发送失败: {data.get('msg')}")
        else:
            logging.debug("PushPlus 微信通知发送成功")

    # ─────────────────────────────────────────────────────────
    #  微信 - Server酱(方糖)（备用方案）
    # ─────────────────────────────────────────────────────────

    def _wechat_ftqq(self, title: str, body: str):
        """
        Server酱(方糖) 微信推送
        配置方式：
        1. 访问 https://sct.ftqq.com 注册
        2. 微信扫码绑定，获取 SendKey
        """
        cfg = self.notify_cfg.get("wechat_ftqq", {})
        send_key = cfg.get("send_key", "")
        if not send_key:
            return

        r = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={"title": title, "desp": body.replace("\n", "\n\n")},
            timeout=10
        )
        data = r.json()
        if data.get("code") != 0:
            logging.warning(f"Server酱 发送失败: {data.get('message')}")
        else:
            logging.debug("Server酱 微信通知发送成功")

    # ─────────────────────────────────────────────────────────
    #  飞书 Webhook（群机器人）
    # ─────────────────────────────────────────────────────────

    def _feishu(self, title: str, body: str, level: str = "info"):
        """
        飞书群机器人 Webhook
        配置方式：
        1. 飞书群 → 设置 → 机器人 → 添加机器人 → 自定义机器人
        2. 复制 Webhook URL
        3. 如启用签名验证，复制 secret
        """
        cfg = self.notify_cfg.get("feishu", {})
        webhook = cfg.get("webhook_url", "")
        if not webhook:
            return

        color_map = {
            "info":    "blue",
            "success": "green",
            "warning": "yellow",
            "danger":  "red"
        }

        # 飞书富文本卡片消息
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color_map.get(level, "blue")
                },
                "elements": [{
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": body.replace("\n", "\n")
                    }
                }, {
                    "tag": "note",
                    "elements": [{
                        "tag": "plain_text",
                        "content": f"AI 交易系统  {datetime.now().strftime('%H:%M:%S')}"
                    }]
                }]
            }
        }

        # 如果启用了签名验证
        secret = cfg.get("secret", "")
        if secret:
            import hmac, hashlib, base64, time as _time
            ts = str(int(_time.time()))
            sign_str = f"{ts}\n{secret}"
            sig = base64.b64encode(
                hmac.new(sign_str.encode(), digestmod=hashlib.sha256).digest()
            ).decode()
            payload["timestamp"] = ts
            payload["sign"] = sig

        r = requests.post(webhook, json=payload, timeout=10)
        data = r.json()
        if data.get("code") != 0:
            logging.warning(f"飞书通知失败: {data.get('msg')}")
        else:
            logging.debug("飞书通知发送成功")

    # ─────────────────────────────────────────────────────────
    #  QQ - go-cqhttp / OneBot 协议
    # ─────────────────────────────────────────────────────────

    def _qq(self, title: str, body: str):
        """
        QQ 推送（基于 go-cqhttp 或 NapCat）
        配置方式：
        1. 下载 go-cqhttp: https://github.com/Mrs4s/go-cqhttp
           或 NapCat: https://github.com/NapNeko/NapCatQQ
        2. 配置 http 服务，默认端口 5700
        3. 填入 QQ 号（个人）或群号（群聊）
        """
        cfg = self.notify_cfg.get("qq", {})
        host = cfg.get("host", "http://127.0.0.1:5700")
        access_token = cfg.get("access_token", "")
        msg = f"{title}\n\n{body}"

        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        # 发私聊消息
        user_id = cfg.get("user_id", "")
        if user_id:
            r = requests.post(f"{host}/send_private_msg", headers=headers,
                              json={"user_id": int(user_id), "message": msg},
                              timeout=10)
            if r.json().get("status") == "ok":
                logging.debug("QQ 私聊通知发送成功")
            else:
                logging.warning(f"QQ 私聊发送失败: {r.json().get('msg')}")

        # 发群消息
        group_id = cfg.get("group_id", "")
        if group_id:
            r = requests.post(f"{host}/send_group_msg", headers=headers,
                              json={"group_id": int(group_id), "message": msg},
                              timeout=10)
            if r.json().get("status") == "ok":
                logging.debug("QQ 群通知发送成功")
            else:
                logging.warning(f"QQ 群发送失败: {r.json().get('msg')}")
