# 🤖 AI Auto Trading Skill for Claude Code

> **AI 全自动交易技能** — 支持币安 / OKX / Polymarket
> Supports Binance · OKX · Polymarket · WeChat · Telegram · Feishu · QQ alerts

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-purple.svg)](https://claude.ai/code)

---

## ✨ Features / 功能亮点

| Feature | Description |
|---------|-------------|
| 🧠 **AI Market Analysis** | Automatically classifies market as **oscillation** or **trend** using RSI, ADX, Bollinger Bands, MACD |
| 📈 **Dual Strategy Engine** | **Oscillation**: mean reversion (buy low / sell high) · **Trend**: directional follow with trailing stop |
| 🛡️ **Triple Stop Protection** | Fixed stop-loss + fixed take-profit + trailing stop-loss |
| ⚡ **Real-time Monitoring** | Dedicated daemon thread checks positions every 5–300s (configurable) |
| 📣 **Multi-channel Alerts** | WeChat (PushPlus / Server酱) · Feishu · QQ · Telegram |
| 🏦 **3 Exchanges** | Binance · OKX · Polymarket (prediction markets) |
| 📊 **Risk Management** | Position sizing · daily loss limit · max positions cap |

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/trading-skill.git
cd trading-skill

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy the example config
cp config/user_config.yaml.example config/user_config.yaml

# Edit with your API keys and settings
nano config/user_config.yaml
```

### 3. Verify Connection

```bash
python verify.py
```

### 4. Paper Trading Test (Recommended First)

```bash
python test_paper_trading.py
```

### 5. Start Live Trading

```bash
python main.py
```

---

## 📁 Project Structure

```
trading-skill/
├── .claude/commands/trading.md   # Claude Code /trading skill
├── config/
│   └── user_config.yaml.example  # Configuration template
├── core/
│   ├── market_analyzer.py        # AI market classification (RSI/ADX/BB/MACD)
│   ├── position_manager.py       # Position tracking & risk control
│   ├── monitor.py                # Real-time price monitor (daemon thread)
│   └── notifier.py               # Multi-channel notifications
├── exchanges/
│   ├── binance.py                # Binance connector
│   ├── okx.py                    # OKX connector
│   └── polymarket.py             # Polymarket CLOB connector
├── strategy/
│   ├── oscillation.py            # Mean reversion strategy
│   └── trend.py                  # Trend following strategy
├── main.py                       # Entry point (dual-thread architecture)
├── verify.py                     # API key verification tool
├── test_paper_trading.py         # Paper trading simulation
└── 使用说明.md                   # Full Chinese user guide
```

---

## 🧠 Strategy Logic

### Market Classification
Every hour, the AI analyzes the last 100 candles and scores:

| Indicator | Weight | Signal |
|-----------|--------|--------|
| ADX | 40% | > 25 = trending, < 20 = ranging |
| Bollinger Width | 20% | Narrow = ranging, Wide = trending |
| MA20 / MA60 | 20% | Alignment = trend direction |
| MACD | 10% | Crossover confirmation |
| Volume | 10% | Volume spike = trend validation |

### Oscillation Strategy (Ranging Market)
- **Buy**: Price touches lower Bollinger Band **AND** RSI < 35
- **Sell**: Price touches upper Bollinger Band **AND** RSI > 65
- **Exit**: Price returns to middle band

### Trend Strategy (Trending Market)
- **Long**: MA20 crosses above MA60 (golden cross) + MACD histogram turns positive + volume spike
- **Short**: MA20 crosses below MA60 (death cross) + MACD histogram turns negative + volume spike
- **Exit**: Trailing stop follows price, triggers on reversal

---

## ⚙️ Configuration Highlights

```yaml
system:
  monitor_interval: 30     # Check positions every 30 seconds

risk:
  total_capital: 1000      # Total capital in USDT
  stop_loss_pct: 0.015     # 1.5% stop loss
  take_profit_pct: 0.03    # 3.0% take profit
  max_daily_loss: 0.05     # Stop trading if down 5% today

strategy:
  analysis:
    timeframe: "1h"        # Analyze 1-hour candles
```

---

## 🔔 Notification Setup

Enable at least one channel in `config/user_config.yaml`:

- **WeChat** (PushPlus): Register at [pushplus.plus](https://www.pushplus.plus), paste your token
- **Telegram**: Create a bot via @BotFather, get your chat_id from @userinfobot
- **Feishu**: Create a webhook bot in your Feishu group
- **QQ**: Deploy [go-cqhttp](https://github.com/Mrs4s/go-cqhttp) locally

---

## ⚠️ Risk Disclaimer

> This software is for **educational and research purposes only**.
> Cryptocurrency trading involves significant risk of loss.
> Past performance does not guarantee future results.
> **Never invest more than you can afford to lose.**
> Start with `paper_trading: true` to test before going live.

---

## 🤝 Professional Setup Service / 专业搭建服务

This open-source version is a **self-install community edition**.

For a **fully managed setup** including:
- ✅ One-on-one installation assistance
- ✅ Exchange referral account setup (for better rebate rates)
- ✅ Custom strategy parameter tuning
- ✅ Notification channel configuration
- ✅ Ongoing technical support

**Contact us for professional installation service.**

> 📩 专业搭建服务请联系：[JeeLinsun]绿泡泡
> 提供一对一安装、策略调优、通知配置和技术支持

---

## 📜 License

MIT License — free to use, modify, and distribute.

---

## 🌟 Star History

If this project helps you, please give it a ⭐ on GitHub!
