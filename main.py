"""
AI 全自动交易系统 - 主入口
使用方式: python main.py [status|close|pause|resume|report]

运行模式（双线程）：
  线程1 - 策略分析：每小时运行一次，扫描市场信号，开仓
  线程2 - 价格监控：每30秒检查一次，实时触发止损/止盈/移动止损
"""
import sys
import yaml
import time
import logging
import threading
from datetime import datetime

from exchanges.binance import BinanceConnector
from exchanges.okx import OKXConnector
from exchanges.polymarket import PolymarketConnector
from core.market_analyzer import MarketAnalyzer
from core.position_manager import PositionManager
from core.monitor import PriceMonitor
from core.notifier import Notifier
from strategy.oscillation import OscillationStrategy
from strategy.trend import TrendStrategy
from core.rebate_tracker import RebateTracker


def load_config(path: str = "config/user_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("logs/system.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def init_exchanges(cfg: dict) -> dict:
    """初始化所有启用的交易所"""
    exchanges = {}
    ex_cfg = cfg["exchanges"]
    rebate = cfg.get("rebate", {})

    if ex_cfg["binance"]["enabled"]:
        exchanges["binance"] = BinanceConnector(
            api_key=ex_cfg["binance"]["api_key"],
            api_secret=ex_cfg["binance"]["api_secret"],
            testnet=ex_cfg["binance"].get("testnet", False),
            ref_id=rebate.get("binance_ref_id", "")
        )
        logging.info("✓ 币安连接器初始化完成")

    if ex_cfg["okx"]["enabled"]:
        exchanges["okx"] = OKXConnector(
            api_key=ex_cfg["okx"]["api_key"],
            api_secret=ex_cfg["okx"]["api_secret"],
            passphrase=ex_cfg["okx"]["passphrase"],
            testnet=ex_cfg["okx"].get("testnet", False),
            broker_id=rebate.get("okx_broker_id", "")
        )
        logging.info("✓ OKX连接器初始化完成")

    if ex_cfg["polymarket"]["enabled"]:
        exchanges["polymarket"] = PolymarketConnector(
            private_key=ex_cfg["polymarket"]["private_key"],
            proxy_address=ex_cfg["polymarket"].get("proxy_address", "")
        )
        logging.info("✓ Polymarket连接器初始化完成")

    return exchanges


def run_trading_cycle(cfg: dict, exchanges: dict,
                      position_mgr: PositionManager,
                      analyzer: MarketAnalyzer,
                      osc_strategy: OscillationStrategy,
                      trend_strategy: TrendStrategy,
                      notifier=None):
    """执行一轮完整的分析和交易"""

    print("\n" + "═" * 50)
    print(f"  AI 交易周期开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 50)

    # ── 检查今天是否还能交易 ──
    total_capital = cfg["risk"]["total_capital"]
    can_trade, reason = position_mgr.can_trade_today(total_capital)
    if not can_trade:
        print(f"⚠  今日交易暂停: {reason}")
        return

    open_positions = position_mgr.get_open_positions()
    current_prices = {}
    signals = []

    # ── 遍历每个交易所和交易对 ──
    for ex_name, connector in exchanges.items():
        if ex_name == "polymarket":
            _process_polymarket(connector, cfg, analyzer, osc_strategy,
                                trend_strategy, open_positions, signals)
            continue

        symbols = cfg["markets"][ex_name]["symbols"]
        for symbol in symbols:
            try:
                # 获取K线
                timeframe = cfg["strategy"]["analysis"]["timeframe"]
                bar = timeframe.upper().replace("H", "H")
                candles = connector.get_klines(symbol, bar,
                                               cfg["strategy"]["analysis"]["lookback_candles"])
                if not candles:
                    continue

                current_prices[symbol] = candles[-1]["close"]

                # 市场分析
                analysis = analyzer.analyze(candles)
                print(analyzer.format_report(symbol, analysis))

                market_type = analysis["market_type"]
                pos_for_symbol = [p for p in open_positions
                                   if p["symbol"] == symbol]

                # 选择策略
                signal = None
                if market_type == "oscillation":
                    signal = osc_strategy.generate_signals(
                        symbol, candles, pos_for_symbol)
                else:
                    signal = trend_strategy.generate_signals(
                        symbol, candles, market_type, pos_for_symbol)

                if signal:
                    signal["exchange"] = ex_name
                    signals.append(signal)
                    logging.info(f"信号: {symbol} {signal['action']} - {signal.get('reason', '')}")

            except Exception as e:
                logging.error(f"处理 {ex_name}/{symbol} 时出错: {e}")

    # ── 检查止损止盈触发 ──
    triggers = position_mgr.check_stop_triggers(current_prices)
    for t in triggers:
        print(f"  触发{t['close_reason']}: {t['symbol']} @ {t['close_price']}")
        signals.append({
            "action": "close_long" if t["side"] == "long" else "close_short",
            "symbol": t["symbol"],
            "exchange": t["exchange"],
            "close_reason": t["close_reason"],
            "close_price": t["close_price"]
        })

    # ── 执行交易信号 ──
    _execute_signals(signals, exchanges, position_mgr, cfg, notifier)

    # ── 输出汇总 ──
    summary = position_mgr.get_summary()
    print(f"""
─────────────────────────────────────
  今日交易次数: {summary['today_trades']}
  今日盈利:    +{summary['today_profit']:.2f} USDT
  今日亏损:    -{summary['today_loss']:.2f} USDT
  今日净盈亏:   {summary['today_net']:+.2f} USDT
  当前持仓数:  {summary['open_count']}
─────────────────────────────────────""")


def _process_polymarket(connector, cfg, analyzer, osc_strategy,
                        trend_strategy, open_positions, signals):
    """处理 Polymarket 预测市场"""
    try:
        min_liq = cfg["markets"]["polymarket"]["min_liquidity"]
        max_markets = cfg["markets"]["polymarket"]["max_markets"]
        markets = connector.get_markets(limit=max_markets * 2,
                                        min_liquidity=min_liq)
        for market in markets[:max_markets]:
            sentiment = connector.analyze_market_sentiment(market)
            # 极端概率 → 震荡策略（买入低估方）
            yes_price = sentiment["yes_price"]
            token_id = market.get("tokens", [{}])[0].get("tokenID", "")
            if not token_id:
                continue
            if yes_price < 0.2:      # YES 严重低估
                signals.append({
                    "action": "buy_yes",
                    "exchange": "polymarket",
                    "token_id": token_id,
                    "price": yes_price,
                    "reason": f"YES 低估 ({yes_price:.2f})",
                    "size": 50  # USDC
                })
            elif yes_price > 0.8:    # YES 严重高估 → 买 NO
                signals.append({
                    "action": "buy_no",
                    "exchange": "polymarket",
                    "token_id": market.get("tokens", [{}, {}])[1].get("tokenID", ""),
                    "price": 1 - yes_price,
                    "reason": f"NO 低估 ({1-yes_price:.2f})",
                    "size": 50
                })
    except Exception as e:
        logging.error(f"Polymarket 处理出错: {e}")


def _execute_signals(signals, exchanges, position_mgr, cfg, notifier=None):
    """执行所有交易信号"""
    for sig in signals:
        ex_name = sig.get("exchange")
        connector = exchanges.get(ex_name)
        if not connector:
            continue

        try:
            if sig["action"] in ("buy", "sell"):
                total_capital = cfg["risk"]["total_capital"]
                stop_loss = sig.get("stop_loss", 0)
                entry = sig["entry_price"]

                size_info = position_mgr.calc_position_size(
                    total_capital, entry, stop_loss)
                qty = size_info["quantity"]

                if ex_name == "polymarket":
                    result = connector.place_order(
                        sig["token_id"], sig["action"],
                        sig["price"], sig.get("size", 50))
                else:
                    result = connector.place_order(
                        sig["symbol"],
                        "BUY" if sig["action"] == "buy" else "SELL",
                        "MARKET",
                        qty
                    )

                position_mgr.open_position(sig, result, ex_name)
                print(f"  ✓ 下单成功: {sig.get('symbol', '')} {sig['action'].upper()}"
                      f" 数量:{qty:.4f} @ {entry}")
                logging.info(f"下单成功: {sig}")
                if notifier:
                    notifier.notify_open(sig)

            elif sig["action"] in ("close_long", "close_short"):
                symbol = sig["symbol"]
                price = sig.get("close_price", sig.get("current_price", 0))
                if ex_name != "polymarket":
                    connector.place_order(symbol,
                                          "SELL" if sig["action"] == "close_long" else "BUY",
                                          "MARKET", 0)  # 全平
                closed = position_mgr.close_position(symbol, ex_name, price)
                if closed:
                    print(f"  ✓ 平仓成功: {symbol} 盈亏:{closed['pnl_pct']:+.2f}%")
                    if notifier:
                        notifier.notify_close(
                            symbol=symbol, exchange=ex_name,
                            side=closed.get("side", ""),
                            entry=closed.get("entry_price", 0),
                            close_price=price,
                            pnl_pct=closed.get("pnl_pct", 0),
                            reason=sig.get("reason", "策略平仓")
                        )

            elif sig["action"] == "update_trailing_stop":
                position_mgr.update_trailing_stop(
                    sig["symbol"], ex_name, sig["new_trailing_stop"])

        except Exception as e:
            logging.error(f"执行信号失败 {sig}: {e}")


def cmd_status(position_mgr):
    summary = position_mgr.get_summary()
    print(f"\n当前持仓 ({summary['open_count']} 个):")
    for p in summary["open_positions"]:
        print(f"  {p['exchange']:8} {p['symbol']:12} {p['side']:5} "
              f"入场:{p['entry_price']}  止损:{p['stop_loss']}")
    print(f"\n今日净盈亏: {summary['today_net']:+.2f} USDT")


def main():
    args = sys.argv[1:]
    cfg = load_config()

    if not cfg["system"]["enabled"]:
        print("系统已暂停（system.enabled = false）")
        return

    setup_logging(cfg["system"].get("log_level", "INFO"))
    exchanges = init_exchanges(cfg)
    position_mgr = PositionManager(cfg)
    analyzer = MarketAnalyzer(cfg)
    osc_strategy = OscillationStrategy(cfg)
    trend_strategy = TrendStrategy(cfg)
    rebate_tracker = RebateTracker(cfg)
    notifier = Notifier(cfg)

    if not exchanges:
        print("未启用任何交易所，请在 config/user_config.yaml 中配置 enabled: true")
        return

    # 命令处理
    if args and args[0] == "status":
        cmd_status(position_mgr)
        return
    elif args and args[0] == "close" and len(args) > 1:
        print(f"平仓: {args[1]}")
        return
    elif args and args[0] == "report":
        rebate_tracker.print_report()
        return
    elif args and args[0] in ("pause", "resume"):
        print(f"请手动修改 config/user_config.yaml 中的 system.enabled")
        return

    # 正常运行模式
    print("\n" + "=" * 50)
    print("  AI 全自动交易系统 启动")
    print(f"  交易所: {', '.join(exchanges.keys())}")
    print(f"  模拟交易: {'是' if cfg['system']['paper_trading'] else '否'}")
    print("  策略分析: 每 1 小时")
    interval = max(5, int(cfg.get("system", {}).get("monitor_interval", 30)))
    print(f"  止损监控: 每 {interval} 秒")
    print("=" * 50)

    # ── 启动通知：系统上线推送 ────────────────────────────────
    notifier.send(
        "🚀 AI 交易系统已启动",
        f"交易所：{', '.join(exchanges.keys())}\n"
        f"模拟模式：{'是' if cfg['system']['paper_trading'] else '否'}\n"
        f"监控频率：每 {max(5, int(cfg.get('system',{}).get('monitor_interval',30)))} 秒\n"
        f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        level="info"
    )

    # ── 线程2：价格监控（止损/止盈/移动止损）────────────────────
    def on_stop_trigger(triggers):
        for t in triggers:
            emoji = "🔴" if t.get("close_reason") == "触发止损" else "🟢"
            print(f"\n  {emoji} [{t['close_reason']}] {t['symbol']} "
                  f"@ {t['close_price']:.4f}")
            # 推送平仓通知
            notifier.notify_close(
                symbol=t["symbol"],
                exchange=t.get("exchange", ""),
                side=t.get("side", ""),
                entry=t.get("entry_price", 0),
                close_price=t.get("close_price", 0),
                pnl_pct=t.get("pnl_pct", 0),
                reason=t.get("close_reason", "")
            )

    monitor = PriceMonitor(position_mgr, exchanges, cfg, on_stop_trigger)
    monitor_thread = threading.Thread(target=monitor.run, daemon=True)
    monitor_thread.start()
    logging.info("价格监控线程已启动")

    # ── 线程1：策略分析循环（主线程）────────────────────────────
    strategy_interval = 3600  # 每小时
    cycle_count = 0
    try:
        while True:
            run_trading_cycle(cfg, exchanges, position_mgr, analyzer,
                              osc_strategy, trend_strategy, notifier)
            cycle_count += 1
            # 每 24 轮（约每天）发一次日报
            if cycle_count % 24 == 0:
                summary = position_mgr.get_summary()
                notifier.notify_daily_report(summary)
            next_run = datetime.now().strftime("%H:%M:%S")
            print(f"\n  下次策略分析将在 {strategy_interval//60} 分钟后运行...")
            time.sleep(strategy_interval)
    except KeyboardInterrupt:
        print("\n  系统已停止 (Ctrl+C)")
        monitor.stop()


if __name__ == "__main__":
    main()
