"""
API Key 验证工具
搭建时用于确认客户的 API Key 是否正确可用
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import yaml

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
BOLD  = "\033[1m";  NC  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{NC}  {msg}")
def fail(msg): print(f"  {RED}✗{NC}  {msg}")
def warn(msg): print(f"  {YELLOW}!{NC}  {msg}")

def load_cfg():
    with open("config/user_config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

def verify_binance(cfg):
    print(f"\n  {BOLD}── 验证币安 API ──{NC}")
    ex = cfg["exchanges"]["binance"]
    if not ex.get("enabled"):
        warn("币安未启用，跳过")
        return True
    if not ex.get("api_key") or not ex.get("api_secret"):
        fail("API Key 或 Secret 为空，请填写后重试")
        return False
    try:
        from exchanges.binance import BinanceConnector
        conn = BinanceConnector(
            ex["api_key"], ex["api_secret"],
            testnet=ex.get("testnet", False)
        )
        if not conn.test_connection():
            fail("网络连接失败，请检查网络或代理")
            return False
        balance = conn.get_balance("USDT")
        ok(f"连接成功！USDT 余额: {balance:.2f}")
        return True
    except Exception as e:
        fail(f"验证失败: {e}")
        return False

def verify_okx(cfg):
    print(f"\n  {BOLD}── 验证 OKX API ──{NC}")
    ex = cfg["exchanges"]["okx"]
    if not ex.get("enabled"):
        warn("OKX 未启用，跳过")
        return True
    if not ex.get("api_key"):
        fail("API Key 为空，请填写后重试")
        return False
    try:
        from exchanges.okx import OKXConnector
        conn = OKXConnector(
            ex["api_key"], ex["api_secret"], ex["passphrase"],
            testnet=ex.get("testnet", False)
        )
        if not conn.test_connection():
            fail("网络连接失败")
            return False
        balance = conn.get_balance("USDT")
        ok(f"连接成功！USDT 余额: {balance:.2f}")
        return True
    except Exception as e:
        fail(f"验证失败: {e}")
        return False

def verify_polymarket(cfg):
    print(f"\n  {BOLD}── 验证 Polymarket ──{NC}")
    ex = cfg["exchanges"]["polymarket"]
    if not ex.get("enabled"):
        warn("Polymarket 未启用，跳过")
        return True
    if not ex.get("private_key"):
        fail("钱包私钥为空")
        return False
    try:
        from exchanges.polymarket import PolymarketConnector
        conn = PolymarketConnector(ex["private_key"])
        if not conn.test_connection():
            fail("Polymarket 网络连接失败")
            return False
        ok(f"连接成功！钱包地址: {conn.address}")
        balance = conn.get_balance()
        ok(f"USDC 余额: {balance:.2f}")
        return True
    except Exception as e:
        fail(f"验证失败: {e}")
        return False

def verify_config(cfg):
    print(f"\n  {BOLD}── 检查配置参数 ──{NC}")
    risk = cfg.get("risk", {})
    issues = []

    capital = risk.get("total_capital", 0)
    if capital <= 0:
        issues.append("total_capital 必须 > 0")
    else:
        ok(f"交易资金: {capital} USDT")

    sl = risk.get("stop_loss_pct", 0)
    tp = risk.get("take_profit_pct", 0)
    if sl <= 0 or sl >= 0.5:
        issues.append("stop_loss_pct 应在 0.005~0.5 之间")
    if tp <= 0 or tp >= 1:
        issues.append("take_profit_pct 应在 0.005~1 之间")
    if tp <= sl:
        issues.append("take_profit_pct 必须大于 stop_loss_pct")
    else:
        rr = tp / sl
        ok(f"止损: {sl*100:.1f}%  止盈: {tp*100:.1f}%  盈亏比: {rr:.1f}:1")

    interval = cfg.get("system", {}).get("monitor_interval", 30)
    if interval < 5:
        issues.append("monitor_interval 最低 5 秒")
    else:
        ok(f"监控频率: 每 {interval} 秒")

    for issue in issues:
        fail(issue)

    return len(issues) == 0


def main():
    print(f"\n{BOLD}════════════════════════════════════{NC}")
    print(f"{BOLD}   API 连接验证工具{NC}")
    print(f"{BOLD}════════════════════════════════════{NC}")

    try:
        cfg = load_cfg()
    except FileNotFoundError:
        fail("找不到 config/user_config.yaml，请在项目根目录运行此脚本")
        sys.exit(1)

    results = [
        verify_config(cfg),
        verify_binance(cfg),
        verify_okx(cfg),
        verify_polymarket(cfg),
    ]

    print(f"\n{BOLD}════════════════════════════════════{NC}")
    if all(results):
        print(f"{GREEN}{BOLD}   所有验证通过！系统可以启动。{NC}")
    else:
        print(f"{RED}{BOLD}   存在验证失败项，请修正后重试。{NC}")
    print(f"{BOLD}════════════════════════════════════{NC}\n")

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
