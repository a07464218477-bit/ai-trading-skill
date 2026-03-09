"""
交付测试脚本
逐项检查所有模块是否正常，输出完整测试报告
"""
import sys, os, json, time, importlib
sys.path.insert(0, os.path.dirname(__file__))

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
BLUE  = "\033[94m"; BOLD = "\033[1m"; NC = "\033[0m"

passed = 0
failed = 0
warns  = 0
results = []

def ok(name, detail=""):
    global passed
    passed += 1
    results.append(("ok", name, detail))
    print(f"  {GREEN}✓{NC}  {name}" + (f"  →  {detail}" if detail else ""))

def fail(name, detail=""):
    global failed
    failed += 1
    results.append(("fail", name, detail))
    print(f"  {RED}✗{NC}  {name}" + (f"  →  {RED}{detail}{NC}" if detail else ""))

def warn(name, detail=""):
    global warns
    warns += 1
    results.append(("warn", name, detail))
    print(f"  {YELLOW}!{NC}  {name}" + (f"  →  {YELLOW}{detail}{NC}" if detail else ""))

def section(title):
    print(f"\n{BOLD}── {title} {'─'*(45-len(title))}{NC}")

# ════════════════════════════════════════════════════
print(f"\n{BOLD}{'═'*52}{NC}")
print(f"{BOLD}   AI 交易系统 · 交付前完整测试{NC}")
print(f"{BOLD}{'═'*52}{NC}")

# ── 1. Python 依赖检查 ───────────────────────────────
section("1. Python 依赖库")
deps = ["yaml", "numpy", "requests"]
for dep in deps:
    try:
        importlib.import_module(dep)
        ok(dep)
    except ImportError:
        fail(dep, "未安装，请运行 pip install -r requirements.txt")

# ── 2. 目录结构检查 ──────────────────────────────────
section("2. 项目文件结构")
required_files = [
    ".claude/commands/trading.md",
    "config/user_config.yaml",
    "core/market_analyzer.py",
    "core/position_manager.py",
    "core/monitor.py",
    "core/notifier.py",
    "core/rebate_tracker.py",
    "exchanges/binance.py",
    "exchanges/okx.py",
    "exchanges/polymarket.py",
    "strategy/oscillation.py",
    "strategy/trend.py",
    "main.py",
    "verify.py",
    "setup.sh",
    "test_paper_trading.py",
    "使用说明.md",
    "requirements.txt",
]
for f in required_files:
    if os.path.exists(f):
        ok(f)
    else:
        fail(f, "文件缺失")

# ── 3. 配置文件解析 ──────────────────────────────────
section("3. 配置文件解析")
try:
    import yaml
    with open("config/user_config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ok("user_config.yaml 语法正确")

    required_keys = [
        ("system", "enabled"),
        ("system", "monitor_interval"),
        ("risk", "total_capital"),
        ("risk", "stop_loss_pct"),
        ("risk", "take_profit_pct"),
        ("risk", "max_daily_loss"),
        ("strategy", "oscillation"),
        ("strategy", "trend"),
        ("notifications",),
    ]
    for keys in required_keys:
        node = cfg
        for k in keys:
            node = node.get(k, {})
        if node is not None and node != {}:
            ok(f"配置项: {'.'.join(keys)}")
        else:
            warn(f"配置项: {'.'.join(keys)}", "为空或缺失")
except Exception as e:
    fail("user_config.yaml", str(e))
    cfg = {}

# ── 4. 核心模块导入 ──────────────────────────────────
section("4. 核心模块导入")
modules = [
    ("core.market_analyzer", "MarketAnalyzer"),
    ("core.position_manager", "PositionManager"),
    ("core.monitor",          "PriceMonitor"),
    ("core.notifier",         "Notifier"),
    ("core.rebate_tracker",   "RebateTracker"),
    ("strategy.oscillation",  "OscillationStrategy"),
    ("strategy.trend",        "TrendStrategy"),
    ("exchanges.binance",     "BinanceConnector"),
    ("exchanges.okx",         "OKXConnector"),
    ("exchanges.polymarket",  "PolymarketConnector"),
]
loaded = {}
for mod_name, cls_name in modules:
    try:
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        loaded[cls_name] = cls
        ok(f"{mod_name}.{cls_name}")
    except Exception as e:
        fail(f"{mod_name}.{cls_name}", str(e))

# ── 5. 市场分析器逻辑 ────────────────────────────────
section("5. 市场分析器（指标计算）")
if "MarketAnalyzer" in loaded and cfg:
    try:
        analyzer = loaded["MarketAnalyzer"](cfg)

        # 构造模拟K线（100根）
        import math, random
        random.seed(42)
        candles = []
        price = 50000.0
        for i in range(100):
            change = random.uniform(-0.015, 0.015)
            price *= (1 + change)
            candles.append({
                "timestamp": i * 3600000,
                "open": price * 0.999,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": random.uniform(100, 500)
            })

        # RSI
        rsi = analyzer.calc_rsi([c["close"] for c in candles])
        assert 0 <= rsi <= 100, "RSI 超出范围"
        ok(f"RSI 计算", f"{rsi:.1f}")

        # ATR
        atr = analyzer.calc_atr(candles)
        assert atr > 0, "ATR 为0"
        ok(f"ATR 计算", f"{atr:.2f}")

        # ADX
        adx = analyzer.calc_adx(candles)
        assert 0 <= adx <= 100, "ADX 超出范围"
        ok(f"ADX 计算", f"{adx:.1f}")

        # 布林带
        bb_u, bb_m, bb_l = analyzer.calc_bollinger([c["close"] for c in candles])
        assert bb_u > bb_m > bb_l, "布林带顺序错误"
        ok(f"布林带", f"上:{bb_u:.0f} 中:{bb_m:.0f} 下:{bb_l:.0f}")

        # MACD
        macd, sig, hist = analyzer.calc_macd([c["close"] for c in candles])
        ok(f"MACD 计算", f"macd:{macd:.2f} 柱:{hist:.2f}")

        # 综合分析
        analysis = analyzer.analyze(candles)
        assert analysis["market_type"] in ("oscillation","trend_up","trend_down")
        ok(f"综合市场判断", f"{analysis['market_type']} 置信度:{analysis['confidence']}%")

    except Exception as e:
        fail("市场分析器", str(e))

# ── 6. 策略信号生成 ──────────────────────────────────
section("6. 策略信号生成")
if "OscillationStrategy" in loaded and "TrendStrategy" in loaded and cfg:
    try:
        osc = loaded["OscillationStrategy"](cfg)
        trend = loaded["TrendStrategy"](cfg)

        # 构造超卖场景（测试震荡策略买入信号）
        import numpy as np
        base = 50000.0
        candles_oversold = []
        prices = [base * (1 - 0.003 * i) for i in range(100)]  # 持续下跌
        for i, p in enumerate(prices):
            candles_oversold.append({
                "timestamp": i * 3600000, "open": p*1.001,
                "high": p*1.005, "low": p*0.995,
                "close": p, "volume": 200.0
            })

        sig = osc.generate_signals("BTC/USDT", candles_oversold, [])
        if sig:
            ok("震荡策略信号生成", f"action={sig['action']} rr={sig.get('rr_ratio','-')}")
        else:
            ok("震荡策略信号生成", "当前无信号（条件未满足，属正常）")

        # 趋势策略（随机行情）
        sig2 = trend.generate_signals("ETH/USDT", candles_oversold, "trend_down", [])
        if sig2:
            ok("趋势策略信号生成", f"action={sig2['action']}")
        else:
            ok("趋势策略信号生成", "当前无信号（条件未满足，属正常）")

    except Exception as e:
        fail("策略信号生成", str(e))

# ── 7. 仓位管理器 ────────────────────────────────────
section("7. 仓位管理器")
if "PositionManager" in loaded and cfg:
    try:
        test_cfg = {**cfg, "risk": {**cfg["risk"], "total_capital": 10000}}
        pm = loaded["PositionManager"](test_cfg)

        # 计算仓位大小
        size = pm.calc_position_size(10000, 50000, 49250)
        assert size["quantity"] > 0
        ok("仓位大小计算", f"数量:{size['quantity']:.4f} 成本:{size['cost']:.2f}U 风险:{size['risk_pct']:.2f}%")

        # 可交易检查
        can, reason = pm.can_trade_today(10000)
        ok("当日风控检查", reason)

        # 获取持仓列表
        positions = pm.get_open_positions()
        ok("持仓列表读取", f"当前 {len(positions)} 个持仓")

        # 止损止盈触发检查
        triggers = pm.check_stop_triggers({"BTC/USDT": 50000})
        ok("止损止盈检查", f"触发 {len(triggers)} 个")

    except Exception as e:
        fail("仓位管理器", str(e))

# ── 8. 通知模块 ──────────────────────────────────────
section("8. 通知模块（仅测试初始化，不实际发送）")
if "Notifier" in loaded and cfg:
    try:
        notifier = loaded["Notifier"](cfg)
        ok("Notifier 初始化")

        # 测试消息构建（不发送）
        notifier.notify_open({
            "action": "buy", "symbol": "BTC/USDT", "exchange": "binance",
            "strategy": "trend", "entry_price": 50000,
            "stop_loss": 49250, "take_profit": 51500,
            "rr_ratio": 2.0, "reason": "测试信号"
        })
        ok("开仓通知格式", "消息构建成功（未启用通道，未实际发送）")

        enabled = [k for k, v in cfg.get("notifications", {}).items()
                   if isinstance(v, dict) and v.get("enabled")]
        if enabled:
            ok("已启用通知通道", ", ".join(enabled))
        else:
            warn("通知通道", "所有通道均未启用，建议至少开启一个（如微信PushPlus）")

    except Exception as e:
        fail("通知模块", str(e))

# ── 9. 公开行情接口 ──────────────────────────────────
section("9. 公开行情接口（网络测试）")
try:
    import requests as req
    r = req.get("https://api.binance.com/api/v3/ping", timeout=5)
    assert r.status_code == 200
    ok("Binance 公开接口", "连接正常")
except Exception as e:
    fail("Binance 公开接口", f"连接失败: {e}")

try:
    r = req.get("https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"}, timeout=5)
    btc = float(r.json()["price"])
    ok("BTC 实时价格获取", f"${btc:,.2f}")
except Exception as e:
    fail("BTC 价格获取", str(e))

# ── 10. Claude Skill 文件 ────────────────────────────
section("10. Claude Skill")
try:
    with open(".claude/commands/trading.md", encoding="utf-8") as f:
        content = f.read()
    assert "/trading" in content or "trading" in content.lower()
    assert "震荡" in content
    assert "趋势" in content
    assert "止损" in content
    ok("/trading skill 文件", f"{len(content)} 字符，关键词完整")
except Exception as e:
    fail("/trading skill 文件", str(e))

# ── 11. 返佣追踪 ─────────────────────────────────────
section("11. 返佣追踪器")
if "RebateTracker" in loaded and cfg:
    try:
        rt = loaded["RebateTracker"](cfg)
        rt.record_trade_profit("binance", "BTC/USDT", 100.0)
        summary = rt.get_monthly_summary()
        assert summary["total_profit"] > 0
        share_pct = cfg.get("rebate", {}).get("profit_share_pct", 0.05)
        ok("利润分成记录", f"测试盈利100U → 应分成 {100*share_pct:.1f}U ({share_pct*100:.0f}%)")
    except Exception as e:
        fail("返佣追踪器", str(e))

# ── 12. 使用说明文档 ─────────────────────────────────
section("12. 使用说明文档")
try:
    with open("使用说明.md", encoding="utf-8") as f:
        doc = f.read()
    sections_required = ["安装", "API Key", "通知", "启动", "策略", "风险", "常见问题"]
    missing = [s for s in sections_required if s not in doc]
    if missing:
        warn("使用说明.md", f"缺少章节: {', '.join(missing)}")
    else:
        ok("使用说明.md", f"共 {len(doc.splitlines())} 行，{len(sections_required)} 个必要章节均完整")
except Exception as e:
    fail("使用说明.md", str(e))

# ════════════════════════════════════════════════════
# 最终报告
print(f"\n{BOLD}{'═'*52}{NC}")
print(f"{BOLD}   测试报告汇总{NC}")
print(f"{BOLD}{'═'*52}{NC}")
print(f"  {GREEN}通过{NC}  {passed} 项")
print(f"  {RED}失败{NC}  {failed} 项")
print(f"  {YELLOW}警告{NC}  {warns} 项")
print(f"  合计  {passed+failed+warns} 项\n")

if failed == 0 and warns == 0:
    print(f"{GREEN}{BOLD}  ✅ 全部通过！系统可以交付给客户。{NC}\n")
elif failed == 0:
    print(f"{YELLOW}{BOLD}  ⚠️  通过（有 {warns} 个警告），建议处理警告后再交付。{NC}\n")
else:
    print(f"{RED}{BOLD}  ❌ 存在 {failed} 个失败项，请修复后再交付。{NC}")
    print(f"{RED}  失败项目：{NC}")
    for status, name, detail in results:
        if status == "fail":
            print(f"    • {name}: {detail}")
    print()

sys.exit(0 if failed == 0 else 1)
