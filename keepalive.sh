#!/bin/bash
# ============================================
#  Render 保活脚本 - 防止免费实例休眠
#  每5分钟访问一次页面，保持服务活跃
# ============================================

# 替换为你的 Render 实际地址
RENDER_URL="${RENDER_URL:-https://gold-bond-tracker.onrender.com}"

# 发送请求并记录结果
curl -s -o /dev/null -w "$(date '+%Y-%m-%d %H:%M:%S') | HTTP %{http_code} | Time %{time_total}s" "$RENDER_URL" >> /tmp/render-keepalive.log
echo "" >> /tmp/render-keepalive.log
