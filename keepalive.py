"""
Render 保活脚本 - 每5分钟访问一次页面，防止免费实例休眠
运行方式: python3 keepalive.py
"""

import requests
import time
import os
from datetime import datetime

# 替换为你的 Render 实际地址
RENDER_URL = os.environ.get("RENDER_URL", "https://gold-bond-tracker.onrender.com")

INTERVAL = int(os.environ.get("KEEPALIVE_INTERVAL", "300"))  # 默认5分钟

print(f"🔁 保活脚本启动")
print(f"   目标: {RENDER_URL}")
print(f"   间隔: {INTERVAL}秒 ({INTERVAL//60}分钟)")
print(f"   按 Ctrl+C 停止\n")

while True:
    try:
        resp = requests.get(RENDER_URL, timeout=30)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] HTTP {resp.status_code} | {resp.elapsed.total_seconds():.2f}s")
    except Exception as e:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] ERROR: {e}")

    time.sleep(INTERVAL)
