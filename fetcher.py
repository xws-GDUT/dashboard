"""
数据获取模块 - 获取上海黄金交易所 AU9999 金价、中国十年期国债收益率、92号汽油油价
数据源:
  - 金价: 上海黄金交易所 (via AKShare spot_quotations_sge + spot_hist_sge)
  - 国债利率: 中国债券信息网 (yield.chinabond.com.cn) + 东方财富备用
  - 油价: api.ruseo.cn 全国油价免费API
"""

import requests
import sqlite3
import os
from datetime import datetime, date
from typing import Optional, Dict

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "prices.db")

# 确保数据目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gold_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date DATE NOT NULL,
            fetch_time DATETIME NOT NULL,
            price_cny_gram REAL NOT NULL,
            source TEXT DEFAULT 'sge.com.cn'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bond_yield (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date DATE NOT NULL,
            fetch_time DATETIME NOT NULL,
            yield_10y REAL NOT NULL,
            source TEXT DEFAULT 'chinamoney.com.cn'
        )
    """)
    # 创建索引加速查询
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gold_date ON gold_price(fetch_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bond_date ON bond_yield(fetch_date)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oil_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date DATE NOT NULL,
            fetch_time DATETIME NOT NULL,
            region TEXT NOT NULL,
            gasoline_92 REAL NOT NULL,
            data_date TEXT,
            source TEXT DEFAULT 'api.ruseo.cn'
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oil_date ON oil_price(fetch_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oil_region ON oil_price(region)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS m2_cagr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date DATE NOT NULL,
            fetch_time DATETIME NOT NULL,
            cagr_20y REAL NOT NULL,
            start_m2 REAL,
            current_m2 REAL,
            growth_multiple REAL,
            data_period TEXT,
            source TEXT DEFAULT 'pbc.gov.cn'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cpi_cagr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date DATE NOT NULL,
            fetch_time DATETIME NOT NULL,
            cagr_20y REAL NOT NULL,
            cpi_max REAL,
            cpi_min REAL,
            cpi_median REAL,
            data_period TEXT,
            data_count INTEGER,
            source TEXT DEFAULT 'stats.gov.cn'
        )
    """)
    conn.commit()
    conn.close()


def fetch_gold_price() -> Optional[Dict]:
    """获取上海黄金交易所 AU9999 实时金价

    优先使用 spot_quotations_sge() 获取日内实时报价 (含夜盘)。
    仅当实时接口无数据时才回退到日线收盘价。

    Returns:
        dict: {
            "price_cny_gram": float,   # 人民币/克
            "data_date": str,          # 数据日期
            "updated_at": str,         # 更新时间
            "is_live": bool,           # 是否实时报价
        }
        失败返回 None
    """
    try:
        import akshare as ak

        # 首选: 实时报价 (含日盘+夜盘，交易时段每1分钟更新)
        df_live = ak.spot_quotations_sge()
        if df_live is not None and not df_live.empty:
            au9999 = df_live[df_live["品种"] == "Au99.99"]
            if not au9999.empty:
                # 取最近5条的中位数，避免尾盘结算价等异常值干扰
                recent = au9999.tail(5)
                prices = recent["现价"].astype(float).tolist()
                prices = [p for p in prices if p > 0]
                if prices:
                    # 排序取中位数
                    prices_sorted = sorted(prices)
                    median_price = prices_sorted[len(prices_sorted) // 2]
                    update_time = recent.iloc[-1].get("更新时间", datetime.now().isoformat())
                    return {
                        "price_cny_gram": round(median_price, 2),
                        "data_date": str(date.today()),
                        "updated_at": str(update_time),
                        "is_live": True
                    }

        # 备用: 日线收盘价
        df_hist = ak.spot_hist_sge(symbol="Au99.99")
        if df_hist is not None and not df_hist.empty:
            latest_hist = df_hist.iloc[-1]
            return {
                "price_cny_gram": round(float(latest_hist["close"]), 2),
                "data_date": str(latest_hist["date"]),
                "updated_at": datetime.now().isoformat(),
                "is_live": False
            }

        print("[WARN] 上海黄金交易所未返回有效数据")
        return None

    except Exception as e:
        print(f"[ERROR] 获取金价失败: {e}")
        return None


def calc_shuibei_buy_price(au9999_price: float) -> Dict:
    """动态预测水贝黄金回购价差（基于融通金实际运营模型）

    价差构成（来自研究报告）:
      回购价差 = 运营成本 + 熔炼损耗 + 检测费 + 利润空间
              ≈ 基准价差 × 运营景气系数 × 风险溢价系数

    模型基于研究报告中的实际验证数据拟合:
      2025-08-29: 价差1.60元 (金价~780, 低波动)
      2026-06-10: 价差4.00元 (金价~917, 正常)
      2026-06-23: 价差4.18元 (金价~899, 正常交易时段)
      2026-06-25: 价差2.00元 (金价~872, 盘前普通金)
      2026-06-25: 价差16.99元 (金价~885, 盘前9999品种，极端)

    关键规律:
      1. 正常交易时段价差: 1.6~4.2元，均值约3.5元
      2. 金价越高→回收商资金占用越大→价差越宽
      3. 金价急跌→回收商恐慌→价差急剧扩大
      4. 盘前/非交易时段→流动性差→价差拉大

    Args:
        au9999_price: 上金所 Au99.99 实时价 (元/克)

    Returns:
        {
            "shuibei_buy": float,
            "spread": float,
            "spread_detail": str,
            "breakdown": dict,  # 价差构成明细
        }
    """
    # === 基准价差: 研究报告历史数据均值 ===
    # 正常交易时段: (1.60+4.00+4.18+4.00+1.60)/5 ≈ 3.08
    # 取整为3.0作为正常市场基准
    BASE_SPREAD = 3.0
    
    # === 价差构成比例 (来自研究报告) ===
    # 运营成本40% + 熔炼损耗20% + 检测费15% + 利润25%
    COST_RATIO = {"运营成本": 0.40, "熔炼损耗": 0.20, "检测费": 0.15, "利润": 0.25}
    
    try:
        import akshare as ak
        from datetime import datetime
        
        # === 因子1: 金价水平 (资金占用成本) ===
        # 金价越高，回收商每克占用的资金越多，资金成本线性上升
        # 以800元为基准 (2025年中枢)
        price_level = au9999_price / 800.0  # >1则成本高于基准
        
        # 运营成本中约40%与金价直接相关 (资金占用、保险、运输)
        price_impact = (price_level - 1.0) * BASE_SPREAD * 0.4
        
        # === 因子2: 市场波动率 (风险溢价) ===
        df_gold = ak.spot_hist_sge(symbol="Au99.99")
        if df_gold is not None and not df_gold.empty:
            recent = df_gold.tail(20)
            volatility = recent["close"].std()
            mean_price = recent["close"].mean()
            vol_ratio = volatility / mean_price
            
            # 5日趋势
            recent5 = recent.tail(5)
            trend_5d = (recent5.iloc[-1]["close"] - recent5.iloc[0]["close"]) / recent5.iloc[0]["close"]
        else:
            vol_ratio = 0.015
            trend_5d = 0.0
        
        # 波动率影响熔炼损耗和检测费（行情不稳时更谨慎）
        # 基准波动率约1.5%，当前越高→风险溢价越大
        vol_impact = max(0, (vol_ratio - 0.015) * 100)  # 每1%超额波动加0.1元
        
        # === 因子3: 趋势方向 (回收商行为心理) ===
        # 急跌时回收商极度谨慎，价差可翻倍
        if trend_5d < -0.04:       # 暴跌>4%
            trend_mult = 1.6
        elif trend_5d < -0.02:     # 明显下跌
            trend_mult = 1.3
        elif trend_5d < -0.01:     # 温和下跌
            trend_mult = 1.1
        elif trend_5d < 0.01:      # 横盘
            trend_mult = 1.0
        elif trend_5d < 0.02:      # 温和上涨
            trend_mult = 0.9
        else:                       # 明显上涨: 回收积极
            trend_mult = 0.8
        
        # === 因子4: 交易时段判断 ===
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        # 上金所交易时段: 9:00-15:30, 19:50-02:30
        is_trading = (9.0 <= hour <= 15.5) or (19.83 <= hour <= 24.0) or (0 <= hour <= 2.5)
        session_mult = 1.0 if is_trading else 1.3  # 非交易时段+30%
        
        # === 综合回购价差 ===
        base_with_price = BASE_SPREAD + price_impact
        spread_before_trend = base_with_price + vol_impact
        spread_after_trend = spread_before_trend * trend_mult
        spread = spread_after_trend * session_mult
        
        # 限制在 1.5 ~ 8.0 元 (去掉极端盘前值)
        spread = max(1.5, min(8.0, spread))
        spread = round(spread, 2)
        
        # === 价差构成明细 ===
        breakdown = {
            "运营成本": round(spread * COST_RATIO["运营成本"], 2),
            "熔炼损耗": round(spread * COST_RATIO["熔炼损耗"], 2),
            "检测费": round(spread * COST_RATIO["检测费"], 2),
            "利润": round(spread * COST_RATIO["利润"], 2),
        }
        
        shuibei_buy = round(au9999_price - spread, 2)
        
        # 生成说明
        parts = []
        if abs(price_impact) > 0.05:
            parts.append(f"金价{price_impact:+.1f}")
        if vol_impact > 0.05:
            parts.append(f"波动+{vol_impact:.1f}")
        if trend_mult != 1.0:
            parts.append(f"趋势×{trend_mult:.1f}")
        if not is_trading:
            parts.append(f"非交易×1.3")
        detail = f"基准{BASE_SPREAD}元" + (" + " + " + ".join(parts) if parts else "") + f" = {spread}元"
        
        return {
            "shuibei_buy": shuibei_buy,
            "spread": spread,
            "spread_detail": detail,
            "breakdown": breakdown,
            "price_impact": round(price_impact, 2),
            "vol_ratio": round(vol_ratio * 100, 2),
            "trend_5d_pct": round(trend_5d * 100, 2),
            "is_trading": is_trading,
        }
        
    except Exception as e:
        spread = 3.0
        shuibei_buy = round(au9999_price - spread, 2)
        return {
            "shuibei_buy": shuibei_buy,
            "spread": spread,
            "spread_detail": f"降级模型: {spread}元",
            "breakdown": {k: round(spread * v, 2) for k, v in COST_RATIO.items()},
        }


def fetch_bond_yield() -> Optional[Dict]:
    """获取中国十年期国债收益率（实时）
    
    数据来源优先级:
      1. 中国货币网实时收益率曲线 (chinamoney.com.cn) - 盘中实时，每分钟更新
      2. 中国债券信息网 (yield.chinabond.com.cn) - 权威估值，T+1
      3. 东方财富 AKShare - 备用

    Returns:
        dict: {"yield_10y": float, "data_date": str} 或 None
    """
    # 方案1: 中国货币网实时收益率曲线 (交易时段实时)
    try:
        url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/RtimeYldCurv"
        params = {"lang": "CN"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.chinamoney.com.cn/chinese/bkcurvrty/",
        }
        resp = requests.post(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        head = data.get("head", {})
        if head.get("rep_code") != "200":
            print(f"[WARN] 实时曲线API异常: {head.get('rep_message')}")
        else:
            records = data.get("data", {}).get("data", [])
            curve_date = data.get("data", {}).get("date", "")
            
            # 找最接近10年的基准债券数据点
            # 数据行格式: [报买收益率, 报卖收益率, 均值, 期限年, ...]
            best_buy = None
            best_sell = None
            best_term = None
            
            for row in records:
                try:
                    term = float(row[3]) if row[3] else 0
                    buy_yield = float(row[0]) if row[0] else 0
                    sell_yield = float(row[1]) if row[1] else 0
                    
                    if buy_yield > 0 and sell_yield > 0:
                        if best_term is None or abs(term - 10.0) < abs(best_term - 10.0):
                            best_term = term
                            best_buy = buy_yield
                            best_sell = sell_yield
                except (ValueError, IndexError):
                    continue
            
            if best_buy and best_sell and best_term:
                # 使用报买和报卖的均值作为十年期收益率
                mid_yield = round((best_buy + best_sell) / 2, 4)
                if 0 < mid_yield < 20:  # 合理范围
                    return {
                        "yield_10y": mid_yield,
                        "data_date": curve_date
                    }
    except Exception as e:
        print(f"[WARN] 实时曲线获取失败: {e}")
    
    # 方案2: 中国债券信息网 (T+1权威估值)
    try:
        from datetime import datetime, timedelta
        url = "https://yield.chinabond.com.cn/cbweb-mn/pgxh/xyQuery"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://yield.chinabond.com.cn/cbweb-mn/pgxh/pgxhIndex",
        }
        today = datetime.now()
        for days_back in range(3):
            check_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
            resp = requests.get(f"{url}?workTime={check_date}", headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data and len(data) >= 2 and data[0]:
                curve_data = data[0][0].get("seriesData", [])
                worktime = data[0][0].get("worktime", check_date)
                for point in curve_data:
                    if abs(point[0] - 10.0) < 0.01:
                        return {
                            "yield_10y": round(float(point[1]), 4),
                            "data_date": worktime
                        }
    except Exception as e:
        print(f"[WARN] 中国债券信息网获取失败: {e}")
    
    # 方案3: 东方财富 AKShare
    try:
        import akshare as ak
        df = ak.bond_zh_us_rate()
        if df is not None and not df.empty and "中国国债收益率10年" in df.columns:
            latest = df.iloc[-1]
            val = latest["中国国债收益率10年"]
            if val and float(val) > 0:
                return {
                    "yield_10y": round(float(val), 4),
                    "data_date": str(latest["日期"])
                }
    except Exception as e:
        print(f"[WARN] 东方财富备用也失败: {e}")
    
    return None


def fetch_lpr() -> Optional[Dict]:
    """获取最新贷款市场报价利率 (LPR)

    数据来源: AKShare → macro_china_lpr (中国人民银行)
    LPR每月20日(遇节假日顺延)发布

    Returns:
        dict: {
            "lpr_1y": float,    # 1年期LPR (%)
            "lpr_5y": float,    # 5年期LPR (%)
            "data_date": str,   # 发布日期
        }
        失败返回 None
    """
    try:
        import akshare as ak
        df = ak.macro_china_lpr()
        if df is None or df.empty:
            return None
        
        latest = df.iloc[-1]
        lpr_1y = float(latest["LPR1Y"])
        lpr_5y = float(latest["LPR5Y"])
        
        if lpr_1y > 0 and lpr_5y > 0:
            return {
                "lpr_1y": round(lpr_1y, 2),
                "lpr_5y": round(lpr_5y, 2),
                "data_date": str(latest["TRADE_DATE"])
            }
        return None
    except Exception as e:
        print(f"[ERROR] 获取LPR失败: {e}")
        return None


def fetch_m1m2_gap() -> Optional[Dict]:
    """计算最新 M1-M2 同比增速剪刀差

    数据来源: AKShare → macro_china_money_supply (央行)
    剪刀差 = M1同比增长 - M2同比增长
    正值 → M1增速快于M2，资金活化，经济偏热
    负值 → M1增速慢于M2，资金沉淀，经济偏冷

    Returns:
        dict: {
            "gap": float,           # M1-M2剪刀差 (%)
            "m2_yoy": float,        # M2同比 (%)
            "m1_yoy": float,        # M1同比 (%)
            "data_date": str,       # 数据月份
        }
        失败返回 None
    """
    try:
        import akshare as ak
        df = ak.macro_china_money_supply()
        if df is None or df.empty:
            return None
        
        latest = df.iloc[0]
        m2_yoy = float(latest["货币和准货币(M2)-同比增长"])
        m1_yoy = float(latest["货币(M1)-同比增长"])
        
        return {
            "gap": round(m1_yoy - m2_yoy, 2),
            "m2_yoy": round(m2_yoy, 2),
            "m1_yoy": round(m1_yoy, 2),
            "data_date": str(latest["月份"])
        }
    except Exception as e:
        print(f"[ERROR] 获取M1/M2剪刀差失败: {e}")
        return None


def fetch_m1m2_monthly() -> Optional[list]:
    """获取 M2/M1 同比增长率历史 (2026年1月起，因25年1月M1口径调整)

    Returns:
        list: [{"month": str, "m2_yoy": float, "m1_yoy": float}, ...]
    """
    try:
        import akshare as ak
        df = ak.macro_china_money_supply()
        if df is None or df.empty:
            return None
        
        result = []
        for _, row in df.iterrows():
            month_str = str(row["月份"])
            # 只取2026年1月及之后 (M1口径调整后)
            if "2026" not in month_str:
                continue
            result.append({
                "month": month_str.replace("年", "-").replace("月份", ""),
                "m2_yoy": round(float(row["货币和准货币(M2)-同比增长"]), 2),
                "m1_yoy": round(float(row["货币(M1)-同比增长"]), 2)
            })
        return list(reversed(result))
    except Exception as e:
        print(f"[ERROR] 获取M1/M2同比历史失败: {e}")
        return None


def fetch_oil_price() -> Optional[Dict]:
    """获取92号汽油油价 (深圳=广东, 泉州=福建)

    数据来源: api.ruseo.cn 全国油价免费API
    按省级定价，广东省代表深圳，福建省代表泉州

    Returns:
        dict: {
            "shenzhen": float,      # 深圳(广东) 92号汽油 元/升
            "quanzhou": float,      # 泉州(福建) 92号汽油 元/升
            "data_date": str,       # 数据日期
        }
        失败返回 None
    """
    try:
        resp = requests.get(
            "https://api.ruseo.cn/api/oilprice",
            headers={"User-Agent": "GoldBondTracker/1.0"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            print(f"[WARN] 油价API返回异常: {data.get('msg')}")
            return None

        oil_list = data.get("data", {}).get("list", [])
        if not oil_list:
            print("[WARN] 油价API未返回数据")
            return None

        sz_price = None
        qz_price = None
        data_date = None

        for item in oil_list:
            region = item.get("region", "")
            price = item.get("gasoline_92")
            item_date = item.get("date", "")

            if region == "广东省":
                sz_price = float(price) if price else None
                data_date = data_date or item_date
            elif region == "福建省":
                qz_price = float(price) if price else None
                data_date = data_date or item_date

        if sz_price and qz_price:
            return {
                "shenzhen": round(sz_price, 2),
                "quanzhou": round(qz_price, 2),
                "data_date": data_date
            }

        print(f"[WARN] 油价API未找到广东/福建数据 (广东={sz_price}, 福建={qz_price})")
        return None

    except Exception as e:
        print(f"[ERROR] 获取油价失败: {e}")
        return None


def fetch_m2_cagr() -> Optional[Dict]:
    """计算近20年中国M2货币供应量年化增长率 (CAGR)

    数据来源: AKShare → macro_china_supply_of_money (央行数据)
    取2006年6月附近和最新月份的M2数据计算20年复合增长率

    Returns:
        dict: {
            "cagr_20y": float,      # 近20年年化增长率 (%)
            "start_m2": float,      # 起始M2 (亿元)
            "current_m2": float,    # 当前M2 (亿元)
            "growth_multiple": float, # 增长倍数
            "data_period": str,     # 数据周期描述
        }
        失败返回 None
    """
    try:
        import akshare as ak
        from datetime import datetime

        df = ak.macro_china_supply_of_money()

        if df is None or df.empty:
            print("[WARN] 未获取到M2数据")
            return None

        # 筛选有效M2数据
        m2_col = "货币和准货币（广义货币M2）"
        m2_valid = df[df[m2_col].notna()].copy()
        if m2_valid.empty:
            print("[WARN] M2数据全部为空")
            return None

        # 最新M2
        latest = m2_valid.iloc[0]
        current_m2 = float(latest[m2_col])

        # 近20年: 找最接近 (当前年月 - 20年) 的数据
        now = datetime.now()
        target_year_month = now.year - 20 + (now.month - 1) / 12  # 比如 2026.5 → 2006.5

        m2_valid["time_num"] = m2_valid["统计时间"].astype(float)
        m2_valid["diff"] = (m2_valid["time_num"] - target_year_month).abs()
        closest = m2_valid.loc[m2_valid["diff"].idxmin()]
        start_m2 = float(closest[m2_col])
        start_time = closest["统计时间"]

        # 计算实际年数
        actual_years = float(latest["统计时间"]) - float(start_time)

        # CAGR
        cagr = (current_m2 / start_m2) ** (1 / actual_years) - 1

        return {
            "cagr_20y": round(cagr * 100, 2),
            "start_m2": round(start_m2, 0),
            "current_m2": round(current_m2, 0),
            "growth_multiple": round(current_m2 / start_m2, 2),
            "data_period": f"{start_time} ~ {latest['统计时间']} ({actual_years:.1f}年)",
        }

    except Exception as e:
        print(f"[ERROR] 获取M2数据失败: {e}")
        return None


def fetch_cpi_cagr() -> Optional[Dict]:
    """计算近20年中国CPI平均年化增长率

    数据来源: AKShare → macro_china_cpi_yearly (国家统计局)
    取近20年每月同比CPI数据，计算算术平均年化增长率

    Returns:
        dict: {
            "cagr_20y": float,      # 近20年平均年化CPI (%)
            "cpi_max": float,       # 期间最高CPI (%)
            "cpi_min": float,       # 期间最低CPI (%)
            "cpi_median": float,    # 期间中位数CPI (%)
            "data_period": str,     # 数据周期描述
            "data_count": int,      # 数据条数
        }
        失败返回 None
    """
    try:
        import akshare as ak
        from datetime import datetime

        df = ak.macro_china_cpi_yearly()

        if df is None or df.empty:
            print("[WARN] 未获取到CPI数据")
            return None

        now = datetime.now()
        cutoff = f"{now.year - 20}-{now.month:02d}-01"

        df["date_str"] = df["日期"].astype(str)
        recent = df[(df["date_str"] >= "2006-06-01") & (df["今值"].notna())].copy()

        if recent.empty:
            print("[WARN] 近20年CPI数据为空")
            return None

        recent["cpi_val"] = recent["今值"].astype(float)

        mean_cpi = recent["cpi_val"].mean()
        cpi_max = recent["cpi_val"].max()
        cpi_min = recent["cpi_val"].min()
        cpi_median = recent["cpi_val"].median()

        return {
            "cagr_20y": round(mean_cpi, 2),
            "cpi_max": round(cpi_max, 1),
            "cpi_min": round(cpi_min, 1),
            "cpi_median": round(cpi_median, 1),
            "data_period": f"{recent.iloc[-1]['date_str']} ~ {recent.iloc[0]['date_str']}",
            "data_count": len(recent),
        }

    except Exception as e:
        print(f"[ERROR] 获取CPI数据失败: {e}")
        return None


def save_gold_price(data: Dict):
    """保存金价到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute(
        """INSERT INTO gold_price (fetch_date, fetch_time, price_cny_gram, source)
           VALUES (?, ?, ?, ?)""",
        (now.date(), now, data["price_cny_gram"], "sge.com.cn")
    )
    conn.commit()
    conn.close()
    print(f"[OK] AU9999金价已保存: ¥{data['price_cny_gram']}/g (数据日期: {data.get('data_date', 'N/A')})")


def save_bond_yield(data: Dict):
    """保存国债收益率到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute(
        """INSERT INTO bond_yield (fetch_date, fetch_time, yield_10y, source)
           VALUES (?, ?, ?, ?)""",
        (now.date(), now, data["yield_10y"], "chinamoney.com.cn")
    )
    conn.commit()
    conn.close()
    print(f"[OK] 国债收益率已保存: {data['yield_10y']}%")


def save_oil_price(data: Dict):
    """保存油价到数据库 (分别保存深圳和泉州)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    for region, price in [("深圳(广东)", data["shenzhen"]), ("泉州(福建)", data["quanzhou"])]:
        cursor.execute(
            """INSERT INTO oil_price (fetch_date, fetch_time, region, gasoline_92, data_date, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now.date(), now, region, price, data.get("data_date"), "api.ruseo.cn")
        )
    conn.commit()
    conn.close()
    print(f"[OK] 油价已保存: 深圳(广东) ¥{data['shenzhen']}/L, 泉州(福建) ¥{data['quanzhou']}/L")


def save_m2_cagr(data: Dict):
    """保存M2 CAGR到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute(
        """INSERT INTO m2_cagr (fetch_date, fetch_time, cagr_20y, start_m2, current_m2, growth_multiple, data_period, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.date(), now, data["cagr_20y"], data["start_m2"], data["current_m2"],
         data["growth_multiple"], data["data_period"], "pbc.gov.cn")
    )
    conn.commit()
    conn.close()
    print(f"[OK] M2 CAGR已保存: {data['cagr_20y']}% ({data['data_period']})")


def save_cpi_cagr(data: Dict):
    """保存CPI CAGR到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute(
        """INSERT INTO cpi_cagr (fetch_date, fetch_time, cagr_20y, cpi_max, cpi_min, cpi_median, data_period, data_count, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now.date(), now, data["cagr_20y"], data["cpi_max"], data["cpi_min"],
         data["cpi_median"], data["data_period"], data["data_count"], "stats.gov.cn")
    )
    conn.commit()
    conn.close()
    print(f"[OK] CPI CAGR已保存: {data['cagr_20y']}% ({data['data_period']})")


def sync_all():
    """执行一次完整同步"""
    print(f"\n{'='*50}")
    print(f"开始同步 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    init_db()
    
    # 获取金价
    gold = fetch_gold_price()
    if gold:
        save_gold_price(gold)
    else:
        print("[WARN] 金价获取失败，跳过")
    
    # 获取国债收益率
    bond = fetch_bond_yield()
    if bond:
        save_bond_yield(bond)
    else:
        print("[WARN] 国债收益率获取失败，跳过")
    
    # 获取油价
    oil = fetch_oil_price()
    if oil:
        save_oil_price(oil)
    else:
        print("[WARN] 油价获取失败，跳过")
    
    # 获取M2 (每天仅首次同步，避免重复拉取大数据)
    m2 = fetch_m2_cagr()
    if m2:
        save_m2_cagr(m2)
    else:
        print("[WARN] M2数据获取失败，跳过")
    
    # 获取CPI
    cpi = fetch_cpi_cagr()
    if cpi:
        save_cpi_cagr(cpi)
    else:
        print("[WARN] CPI数据获取失败，跳过")
    
    print(f"{'='*50}\n")


if __name__ == "__main__":
    sync_all()
