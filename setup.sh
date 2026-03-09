#!/bin/bash
# ================================================================
#   AI 全自动交易系统 — 一键安装脚本
#   适用系统: macOS / Linux
#   使用方式: bash setup.sh
# ================================================================

set -e  # 任何命令失败立即退出

# ── 颜色 ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()    { echo -e "\n${BOLD}>>> $1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${BOLD}   AI 全自动交易系统 安装程序${NC}"
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo ""

# ── 步骤 1：检测操作系统 ──────────────────────────────────────
step "步骤 1/6  检测系统环境"
OS="$(uname -s)"
case "$OS" in
  Darwin) info "检测到 macOS" ;;
  Linux)  info "检测到 Linux" ;;
  *)      error "不支持的操作系统: $OS" ;;
esac

# ── 步骤 2：检查 Python ───────────────────────────────────────
step "步骤 2/6  检查 Python 环境"
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version 2>&1)
  success "Python 已安装: $PY_VER"
  PYTHON=python3
else
  error "未找到 Python3，请先安装 Python 3.9+\n  macOS: brew install python3\n  Ubuntu: sudo apt install python3"
fi

# Python 版本检查（需要 3.9+）
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
  error "需要 Python 3.9 或更高版本，当前版本过低"
fi

# ── 步骤 3：检查 Claude Code ──────────────────────────────────
step "步骤 3/6  检查 Claude Code"
if command -v claude &>/dev/null; then
  success "Claude Code 已安装"
else
  warn "未检测到 Claude Code，正在尝试安装..."
  if command -v npm &>/dev/null; then
    npm install -g @anthropic-ai/claude-code
    success "Claude Code 安装完成"
  else
    warn "请手动安装 Claude Code: npm install -g @anthropic-ai/claude-code"
    warn "或访问 https://claude.ai/code 获取安装指引"
  fi
fi

# ── 步骤 4：安装 Python 依赖 ──────────────────────────────────
step "步骤 4/6  安装 Python 依赖库"
cd "$SCRIPT_DIR"

# 优先使用虚拟环境
if [ ! -d ".venv" ]; then
  info "创建虚拟环境 .venv ..."
  $PYTHON -m venv .venv
fi
source .venv/bin/activate
info "虚拟环境已激活"

info "安装依赖..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "所有依赖安装完成"

# ── 步骤 5：安装 Claude Skill ─────────────────────────────────
step "步骤 5/6  安装 Claude Skill"

# 用户级 commands 目录
USER_COMMANDS="$HOME/.claude/commands"
mkdir -p "$USER_COMMANDS"

# 复制 skill 文件
cp "$SCRIPT_DIR/.claude/commands/trading.md" "$USER_COMMANDS/trading.md"
success "Skill 已安装到 $USER_COMMANDS/trading.md"
info "客户现在可以在任意目录使用 /trading 命令"

# ── 步骤 6：配置向导 ──────────────────────────────────────────
step "步骤 6/6  配置向导"

CONFIG="$SCRIPT_DIR/config/user_config.yaml"

echo ""
echo -e "  ${BOLD}请选择要启用的交易所：${NC}"
echo "  1) 币安 (Binance)"
echo "  2) OKX"
echo "  3) Polymarket"
echo "  4) 全部跳过（稍后手动配置）"
echo ""
read -p "  请输入选项 [1/2/3/4]: " EXCHANGE_CHOICE

configure_binance() {
  echo ""
  echo -e "  ${BOLD}── 配置币安 API ──${NC}"
  read -p "  Binance API Key: " BN_KEY
  read -p "  Binance Secret:  " BN_SEC
  # 替换配置文件中的值
  if [[ "$OS" == "Darwin" ]]; then
    sed -i '' "s/binance:/binance:\n    enabled: true/" "$CONFIG" 2>/dev/null || true
    sed -i '' "/api_key: \"\"/{s/api_key: \"\"/api_key: \"$BN_KEY\"/}" "$CONFIG"
    sed -i '' "/api_secret: \"\"/{0,/api_secret: \"\"/s/api_secret: \"\"/api_secret: \"$BN_SEC\"/}" "$CONFIG"
  else
    sed -i "/api_key: \"\"/{s/api_key: \"\"/api_key: \"$BN_KEY\"/}" "$CONFIG"
    sed -i "/api_secret: \"\"/{0,/api_secret: \"\"/s/api_secret: \"\"/api_secret: \"$BN_SEC\"/}" "$CONFIG"
  fi
  # 将 binance enabled 设为 true
  python3 -c "
import yaml
with open('$CONFIG') as f: cfg = yaml.safe_load(f)
cfg['exchanges']['binance']['enabled'] = True
cfg['exchanges']['binance']['api_key'] = '$BN_KEY'
cfg['exchanges']['binance']['api_secret'] = '$BN_SEC'
with open('$CONFIG','w') as f: yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
"
  success "币安 API 配置完成"
}

configure_okx() {
  echo ""
  echo -e "  ${BOLD}── 配置 OKX API ──${NC}"
  read -p "  OKX API Key:    " OKX_KEY
  read -p "  OKX Secret:     " OKX_SEC
  read -p "  OKX Passphrase: " OKX_PASS
  python3 -c "
import yaml
with open('$CONFIG') as f: cfg = yaml.safe_load(f)
cfg['exchanges']['okx']['enabled'] = True
cfg['exchanges']['okx']['api_key'] = '$OKX_KEY'
cfg['exchanges']['okx']['api_secret'] = '$OKX_SEC'
cfg['exchanges']['okx']['passphrase'] = '$OKX_PASS'
with open('$CONFIG','w') as f: yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
"
  success "OKX API 配置完成"
}

configure_polymarket() {
  echo ""
  echo -e "  ${BOLD}── 配置 Polymarket ──${NC}"
  read -p "  钱包私钥 (0x...): " PM_KEY
  python3 -c "
import yaml
with open('$CONFIG') as f: cfg = yaml.safe_load(f)
cfg['exchanges']['polymarket']['enabled'] = True
cfg['exchanges']['polymarket']['private_key'] = '$PM_KEY'
with open('$CONFIG','w') as f: yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
"
  success "Polymarket 配置完成"
}

case "$EXCHANGE_CHOICE" in
  1) configure_binance ;;
  2) configure_okx ;;
  3) configure_polymarket ;;
  4) warn "跳过配置，请稍后手动编辑 config/user_config.yaml" ;;
  *) warn "无效输入，跳过配置" ;;
esac

# 设置资金和监控频率
echo ""
read -p "  请输入初始交易资金（USDT，默认 1000）: " CAPITAL
CAPITAL=${CAPITAL:-1000}
read -p "  价格监控频率（秒，建议 30，默认 30）: " INTERVAL
INTERVAL=${INTERVAL:-30}

python3 -c "
import yaml
with open('$CONFIG') as f: cfg = yaml.safe_load(f)
cfg['risk']['total_capital'] = float('$CAPITAL')
cfg['system']['monitor_interval'] = int('$INTERVAL')
with open('$CONFIG','w') as f: yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
"
success "资金和监控频率配置完成"

# ── 验证 API 连接 ─────────────────────────────────────────────
echo ""
read -p "  是否立即验证 API 连接？[Y/n]: " DO_VERIFY
if [[ "$DO_VERIFY" != "n" && "$DO_VERIFY" != "N" ]]; then
  info "正在验证 API 连接..."
  $PYTHON "$SCRIPT_DIR/verify.py" || warn "API 验证失败，请检查 config/user_config.yaml 中的 Key 是否正确"
fi

# ── 设置开机自启（可选）──────────────────────────────────────
echo ""
read -p "  是否设置开机自动启动交易系统？[y/N]: " DO_AUTOSTART
if [[ "$DO_AUTOSTART" == "y" || "$DO_AUTOSTART" == "Y" ]]; then
  if [[ "$OS" == "Darwin" ]]; then
    # macOS launchd
    PLIST="$HOME/Library/LaunchAgents/com.trading.plist"
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.trading</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>$SCRIPT_DIR/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/stderr.log</string>
</dict>
</plist>
PLIST
    launchctl load "$PLIST" 2>/dev/null || true
    success "macOS 开机自启已配置 (launchd)"
  else
    # Linux systemd
    SERVICE="/etc/systemd/system/trading.service"
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
    sudo tee "$SERVICE" > /dev/null <<SERVICE
[Unit]
Description=AI Trading System
After=network.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_PYTHON $SCRIPT_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE
    sudo systemctl daemon-reload
    sudo systemctl enable trading
    success "Linux systemd 开机自启已配置"
  fi
fi

# ── 完成 ──────────────────────────────────────────────────────
mkdir -p "$SCRIPT_DIR/logs"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}   安装完成！${NC}"
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}使用方式：${NC}"
echo ""
echo -e "  ${GREEN}▶ 启动实盘交易${NC}"
echo "    cd $SCRIPT_DIR"
echo "    source .venv/bin/activate"
echo "    python main.py"
echo ""
echo -e "  ${GREEN}▶ 运行模拟测试${NC}"
echo "    python test_paper_trading.py"
echo ""
echo -e "  ${GREEN}▶ 在 Claude Code 中使用${NC}"
echo "    打开 Claude Code，输入 /trading"
echo ""
echo -e "  ${GREEN}▶ 查看状态${NC}"
echo "    python main.py status"
echo ""
echo -e "  ${YELLOW}配置文件位置：${NC}"
echo "    $CONFIG"
echo ""
