#!/bin/bash
# Render 定时任务 - 每天执行数据同步
# Render Cron Job: 0 1,5,9,13,17,21 * * * (北京时间 9:00/12:00/16:00/20:00)
cd /opt/render/project/src
python3 fetcher.py
