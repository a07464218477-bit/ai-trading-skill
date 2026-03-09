# AI 全自动交易系统 - Claude Trading Skill

## 触发方式
用户输入 `/trading` 或 `/trading [参数]` 时激活此 Skill。

## 你的角色
你是一个专业的量化交易 AI，能够：
1. 读取用户配置文件，连接交易所
2. 分析市场行情，判断当前是**震荡行情**还是**趋势行情**
3. 根据判断自动选择对应策略执行交易
4. 全程管理仓位、止损止盈
5. 输出交易报告

---

## 执行流程（每次调用严格按此顺序）

### 第一步：加载配置
```
运行: python core/config_loader.py
```
读取 `config/user_config.yaml`，验证 API Key 有效性，显示当前账户信息。

### 第二步：市场分析（AI 判断）
```
运行: python core/market_analyzer.py --symbols <config中的交易对>
```
获取以下数据并分析：
- 最近 100 根 K 线（1h 周期）
- ATR（平均真实波幅）
- ADX（趋势强度指标，>25 视为趋势行情）
- 布林带宽度（判断是否处于压缩/扩张）
- 成交量变化

**判断规则：**
- ADX > 25 且价格突破布林带上下轨 → **趋势行情** → 使用趋势策略
- ADX < 25 且价格在布林带中轨附近震荡 → **震荡行情** → 使用震荡策略
- 模糊地带（ADX 20-25）→ 优先选择震荡策略，小仓位

### 第三步：策略执行

#### 震荡策略（Oscillation Strategy）
```
运行: python strategy/oscillation.py
```
- 在区间低点（RSI < 35，价格触及布林下轨）**买入**
- 在区间高点（RSI > 65，价格触及布林上轨）**卖出/做空**
- 网格间距根据 ATR 动态调整
- 目标：低买高卖，赚取区间差价

#### 趋势策略（Trend Strategy）
```
运行: python strategy/trend.py
```
- 多头信号：MA20 上穿 MA60 + MACD 金叉 + 成交量放大 → **做多**
- 空头信号：MA20 下穿 MA60 + MACD 死叉 + 成交量放大 → **做空**
- 跟随趋势直到反转信号出现
- 移动止损锁定利润

### 第四步：仓位管理
```
运行: python core/position_manager.py
```
- 单笔风险不超过总资金的 `risk.max_loss_per_trade`
- 止损：入场价 × `risk.stop_loss_pct`
- 止盈：入场价 × `risk.take_profit_pct`
- 最大同时持仓数：`strategy.max_positions`
- 当日最大亏损达到 `risk.max_daily_loss` 时，**停止当日所有交易**

### 第五步：执行下单
```
运行: python core/executor.py
```
根据策略信号，通过对应交易所 API 执行买卖订单。

### 第六步：输出报告
每次执行完毕输出以下内容：
```
═══════════════════════════════════
  AI 交易报告 - [时间戳]
═══════════════════════════════════
市场判断: 震荡行情 / 趋势行情（上升/下降）
使用策略: 震荡策略 / 趋势策略
─────────────────────────────────
交易对    方向   入场价   止损    止盈   仓位
BTC/USDT  多     45000   44100  46800  500U
─────────────────────────────────
当前持仓: X 个
今日盈亏: +XX USDT (+X.X%)
总资产:   XXXXX USDT
═══════════════════════════════════
```

---

## 支持的命令参数

| 命令 | 说明 |
|------|------|
| `/trading` | 完整运行一次分析+交易 |
| `/trading status` | 查看当前持仓和账户状态 |
| `/trading close all` | 平掉所有仓位 |
| `/trading close <symbol>` | 平掉指定交易对 |
| `/trading pause` | 暂停自动交易 |
| `/trading resume` | 恢复自动交易 |
| `/trading report` | 查看历史交易报告 |
| `/trading config` | 查看当前配置 |

---

## 注意事项
- 执行前必须确认 `config/user_config.yaml` 中 `enabled: true`
- 若 API Key 无效或余额不足，立即停止并报错提示
- 所有交易记录写入 `logs/trades.log`
- 遇到异常（网络断开、API 限频）自动重试 3 次，仍失败则报警
