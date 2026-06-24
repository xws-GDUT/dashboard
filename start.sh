#!/bin/bash
# ============================================
#  金价 & 国债收益率追踪器 - 启动脚本
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  🥇 金价 & 国债收益率追踪器"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3.11 &> /dev/null; then
    echo "❌ 需要 Python 3.11"
    exit 1
fi

# 检查依赖
echo "📦 检查依赖..."
python3.11 -c "import flask, requests, akshare, schedule" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  缺少依赖，正在安装..."
    python3.11 -m pip install flask requests akshare schedule -q
fi
echo "✅ 依赖就绪"

# 确保数据目录存在
mkdir -p data

echo ""
echo "🚀 启动服务..."
echo "   📊 Web 仪表盘: http://localhost:5000"
echo "   ⏰ 定时同步: 每日 09:00, 12:00, 16:00, 20:00"
echo "   📡 按 Ctrl+C 停止"
echo ""

# 启动
python3.11 scheduler.py
