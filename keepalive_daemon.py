"""
Render 保活脚本 - 守护进程版
即使主进程挂了也会自动重启
"""

import requests
import time
import sys
import os
from datetime import datetime

RENDER_URL = "https://dashboard-4i3t.onrender.com/"
INTERVAL = 300  # 5分钟
LOG_FILE = "/tmp/keepalive-daemon.log"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg, flush=True)

def keepalive():
    while True:
        try:
            resp = requests.get(RENDER_URL, timeout=60)
            log(f"HTTP {resp.status_code} | {resp.elapsed.total_seconds():.2f}s")
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    log("🔁 保活守护进程启动")
    log(f"   目标: {RENDER_URL}")
    log(f"   间隔: {INTERVAL}秒")
    
    # 立即唤醒一次
    try:
        requests.get(RENDER_URL, timeout=60)
        log("✅ 首次唤醒成功")
    except:
        log("⚠️ 首次唤醒失败，继续运行")
    
    # 主循环，捕获所有异常防止退出
    while True:
        try:
            keepalive()
        except Exception as e:
            log(f"💥 守护进程崩溃: {e}，10秒后重启...")
            time.sleep(10)
