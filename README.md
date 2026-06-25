# 📺 行情早知道

> 宏观经济核心指标实时追踪 — 金价 · 利率 · 油价 · 通胀 · 货币 · 每天看一眼，心里有数

[![Render](https://img.shields.io/badge/Render-Deployed-46E3B7)](https://dashboard-4i3t.onrender.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 一、项目简介

**行情早知道** 是一个宏观经济核心指标实时监控仪表盘，覆盖 11 项关键数据。项目部署于 [Render](https://render.com) 免费实例，通过 [Cloudflare Workers Cron](https://workers.cloudflare.com) 实现 24/7 保活。

### 核心指标（11 张数据卡片）

| # | 卡片 | 数据内容 | 更新频率 |
|---|------|---------|---------|
| 🌍 | 国际金价 (XAU/USD) | 伦敦现货金价 + 折算人民币克价 | 实时 |
| 💧 | 水贝黄金实时买价 | 融通金 APP 回购价（动态模型） | 实时 |
| 📀 | 上海金 AU9999 | 上金所现货实盘价 | 实时 |
| 💰 | 近 20 年 M2 年化增长率 | M2 货币供应量复合增速 | 每日 |
| ✂️ | M1-M2 剪刀差 | M1 同比 - M2 同比 | 每月 |
| 🛒 | 近 20 年 CPI 年化通胀 | 居民消费价格指数均值 | 每日 |
| 📈 | 十年期国债收益率 | 银行间实时收益率曲线 | 实时（盘中） |
| 🏦 | LPR 利率 | 1 年期 / 5 年期贷款市场报价利率 | 每月 20 日 |
| 🏠 | 公积金贷款利率 | 首套 / 二套 5 年以上 | 政策发布时 |
| ⛽ | 深圳 92# 汽油 | 广东省统一定价 | 调价窗口 |
| ⛽ | 泉州 92# 汽油 | 福建省统一定价 | 调价窗口 |

### 图表

| 图表 | 内容 | 数据范围 |
|------|------|---------|
| ✂️ M1-M2 同比剪刀差 | 柱状图（绿色正/红色负） | 2026 年 1 月起（M1 新口径） |

---

## 二、数据源 & 业务规则

### 2.1 国际金价 (XAU/USD)

| 项目 | 说明 |
|------|------|
| 数据源 | [xaus.com](https://xaus.com/api) 免费 API |
| 汇率 | 离岸人民币 USDCNH（优先东方财富实时，降级 xaus.com） |
| 计算公式 | `人民币/克 = 伦敦金(USD/oz) × USDCNH ÷ 31.1035` |

### 2.2 上海金 AU9999

| 项目 | 说明 |
|------|------|
| 数据源 | 上海黄金交易所（via AKShare `spot_quotations_sge`） |
| 实时策略 | 交易时段取最近 5 条报价中位数，过滤尾盘结算价异常值 |
| 降级 | 非交易时段回退日线收盘价（`spot_hist_sge`） |

### 2.3 水贝黄金实时买价（融通金 APP 回购价）

这是项目最核心的业务模型，完整模拟融通金 APP 的回购定价逻辑。

#### 交易时段定价（上金所开市）

```
SGE基准价 = P_AU9999 × W1 + P_AU(T+D) × W2
           (日市: W1=35% W2=65%, 夜市: W1=20% W2=80%)

XAU人民币基准 = 伦敦金(USD/oz) × 离岸汇率(USDCNH) ÷ 31.1035

综合基准价 = SGE基准价 × 0.95 + XAU人民币基准 × 0.05

APP实时回购价 = 综合基准价 - S_固定(1.0元) - S_波动(0~2元)
```

**波动点差规则**：当 AU9999 近 1 小时涨跌 ≥ 5 元/克时触发，`S_波动 = min(2.0, |涨跌幅| × 0.2)`。

#### 非交易时段定价（休市/周末/节假日）

```
收盘SGE基准价 = 最近交易日收盘价

休市基准价 = 收盘SGE基准价 × (1 + 伦敦金涨跌幅)

APP休市回购价 = 休市基准价 - S_固定(1.0) - S_休市风险(1.5~3.0)
```

**休市风险点差**：工作日 1.5 元，周五下午后 2.0 元，周末 2.5 元。

### 2.4 十年期国债收益率

| 层级 | 数据源 | 更新频率 |
|------|--------|---------|
| 第一优先 | 中国货币网实时收益率曲线 `RtimeYldCurv` | 盘中每分钟 |
| 第二降级 | 中国债券信息网 `xyQuery` | T+1 |
| 第三降级 | 东方财富 AKShare `bond_zh_us_rate` | T+1 |

实时曲线取最接近 10 年期基准债券的报买/报卖收益率均值。

### 2.5 M2 年化增长率

| 项目 | 说明 |
|------|------|
| 数据源 | 中国人民银行（via AKShare `macro_china_supply_of_money`） |
| 计算 | 近 20 年 M2 复合年化增长率 (CAGR) |
| 公式 | `CAGR = (当前M2 / 20年前M2)^(1/20) - 1` |

### 2.6 M1-M2 剪刀差

| 项目 | 说明 |
|------|------|
| 数据源 | 中国人民银行（via AKShare `macro_china_money_supply`） |
| 卡片公式 | `剪刀差 = M1同比增长 - M2同比增长` |
| 图表公式 | `剪刀差 = M1同比 - M2同比`（24 个月，2026年1月起） |
| 含义 | 正值 → 资金活化/经济偏热；负值 → 资金沉淀/经济偏冷 |

> ⚠️ 2025 年 1 月央行调整 M1 统计口径（纳入个人活期存款等），故图表数据从 2026 年 1 月起算，确保口径一致。

### 2.7 CPI 年化通胀

| 项目 | 说明 |
|------|------|
| 数据源 | 国家统计局（via AKShare `macro_china_cpi_yearly`） |
| 计算 | 近 20 年（2006 年起）月度同比 CPI 的算术均值 |

### 2.8 LPR 贷款市场报价利率

| 项目 | 说明 |
|------|------|
| 数据源 | 中国人民银行（via AKShare `macro_china_lpr`） |
| 发布频率 | 每月 20 日（遇节假日顺延） |

### 2.9 公积金贷款利率

| 项目 | 说明 |
|------|------|
| 数据源 | 中国人民银行（硬编码，政策变动时更新） |
| 当前值 | 2026 年 1 月 1 日起：首套 5 年以上 2.60%，二套 3.075% |

### 2.10 92 号汽油油价

| 项目 | 说明 |
|------|------|
| 数据源 | [api.ruseo.cn](https://api.ruseo.cn/api/oilprice) 全国油价免费 API |
| 深圳 | 广东省统一定价 |
| 泉州 | 福建省统一定价 |
| 更新频率 | 每 10 个工作日（国家调价窗口） |

---

## 三、技术架构

```
┌─────────────────────────────────────────────┐
│            Cloudflare Workers Cron           │
│         (每 14 分钟 ping /healthz)           │
└─────────────────┬───────────────────────────┘
                  │ keepalive
┌─────────────────▼───────────────────────────┐
│               Render Web Service             │
│         (Flask + Gunicorn, 免费实例)          │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ app.py   │  │fetcher.py│  │ scheduler  │ │
│  │ 7 个 API │  │ 数据获取  │  │ 定时同步    │ │
│  └──────────┘  └──────────┘  └────────────┘ │
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │            SQLite (prices.db)            ││
│  │  gold_price / bond_yield / oil_price /   ││
│  │  m2_cagr / cpi_cagr / lpr_data           ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

### 前端

- **逐卡片渲染**：7 个独立 API 端点，先到先渲染，互不阻塞
- **Chart.js**：M1-M2 剪刀差走势图
- **明亮主题 UI**：浅灰背景 + 白色卡片 + 蓝色渐变顶栏

### 后端

| 文件 | 职责 |
|------|------|
| `app.py` | Flask Web 服务 + 7 个分片 API + 健康检查 |
| `fetcher.py` | 所有数据获取逻辑 + 水贝定价模型 |
| `scheduler.py` | 定时同步任务（每日 9/12/16/20 点） |
| `requirements.txt` | Python 依赖 |

### 保活方案

```
Cloudflare Workers Cron (每 14 分钟)
    │ GET /healthz
    ▼
Render 免费实例 ← 重置 15 分钟休眠倒计时
```

- **不依赖任何 sandbox**，24/7 运行
- **完全免费**：Cloudflare Workers 免费额度 10 万次/天，保活仅用 ~100 次/天

---

## 四、部署指南

### 4.1 Render 部署

1. Fork 本仓库到你的 GitHub
2. 打开 [dashboard.render.com](https://dashboard.render.com)
3. **New + → Web Service** → 连接 GitHub 仓库
4. 配置：
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python3 scheduler.py`
   - **Runtime**: Python 3
   - **Plan**: Free

### 4.2 Cloudflare Workers 保活（防止休眠）

```bash
# 1. 安装 Wrangler
npm install -g wrangler

# 2. 登录 Cloudflare
npx wrangler login

# 3. 设置 Render URL
npx wrangler secret put RENDER_URL
# 输入: https://你的应用.onrender.com

# 4. 部署
npx wrangler deploy
```

### 4.3 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python3 scheduler.py

# 访问 http://localhost:5000
```

---

## 五、API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 仪表盘主页 |
| `/healthz` | GET | 健康检查（供保活使用） |
| `/api/gold_live` | GET | 实时金价 + 水贝买价 |
| `/api/intl_gold` | GET | 国际金价 + 离岸汇率 |
| `/api/bond_live` | GET | 实时国债收益率 |
| `/api/lpr_live` | GET | LPR 利率 |
| `/api/m1m2_live` | GET | M1-M2 剪刀差 |
| `/api/static_data` | GET | 缓存数据（M2/CPI/油价/公积金） |
| `/api/m1m2_monthly` | GET | M1-M2 剪刀差历史（24 个月） |

---

## 六、项目结构

```
gold-bond-tracker/
├── app.py                  # Flask Web 服务 + API
├── fetcher.py              # 数据获取 + 水贝定价模型
├── scheduler.py            # 定时任务 + Web 启动
├── requirements.txt        # Python 依赖
├── render.yaml             # Render 部署配置
├── wrangler.toml           # Cloudflare Worker 配置
├── cloudflare-worker.js    # Worker 保活脚本
├── keepalive_daemon.py     # 本地保活守护进程
├── start.sh                # 一键启动脚本
├── crontab.txt             # Cron 配置参考
├── templates/
│   └── dashboard.html      # 前端仪表盘
├── static/                 # 静态资源
└── data/
    └── prices.db           # SQLite 数据库
```

---

## 七、免责声明

本项目所有数据仅供参考，**不构成任何投资建议**。数据来源包括上海黄金交易所、中国人民银行、国家统计局、中国货币网、中国债券信息网等公开渠道，但可能存在延迟或误差。投资者应自行判断并承担投资风险。

---

## 八、License

MIT © 2025
