"""
定时调度器 - 每天自动同步金价和国债收益率
使用 schedule 库实现定时任务 + 同时运行 Flask Web 服务
"""

import threading
import time
import schedule
import sys
import os

# 添加项目目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from fetcher import sync_all, init_db
from app import app


def run_scheduler():
    """运行定时调度器 (后台线程)"""
    # 每天 09:00, 12:00, 16:00, 20:00 各同步一次
    schedule.every().day.at("09:00").do(sync_all)
    schedule.every().day.at("12:00").do(sync_all)
    schedule.every().day.at("16:00").do(sync_all)
    schedule.every().day.at("20:00").do(sync_all)
    
    print("⏰ 定时任务已设置:")
    print("   - 每天 09:00 · 12:00 · 16:00 · 20:00 自动同步")
    print("   - 启动时立即执行一次同步\n")
    
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    # 初始化数据库
    init_db()
    
    # 启动时立即同步一次
    print("\n🔧 启动时立即同步一次...")
    sync_all()
    
    # 启动定时调度器 (后台线程)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # 启动 Flask Web 服务
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 启动 Web 仪表盘 (端口: {port})...\n")
    app.run(host="0.0.0.0", port=port, debug=False)
