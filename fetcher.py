"""
数据获取模块 - 获取上海黄金交易所 AU9999 金价、中国十年期国债收益率、92号汽油油价
数据源:
  - 金价: 上海黄金交易所 (via AKShare spot_quotations_sge + spot_hist_sge)
  - 国债利率: 中国货币网 (chinamoney.com.cn) 政府债券利率历史数据
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


def calc_shuibei_buy_price(au9999_price: float) -> float:
    """根据研究报告计算水贝黄金实时买价
    
    公式: 水贝买价 ≈ 上金所Au99.99实时价 - 4元/克
    来源: 《融通金APP水贝黄金买价形成机制研究报告》
    
    Args:
        au9999_price: 上金所 Au99.99 实时价 (元/克)
    
    Returns:
        水贝黄金买价 (元/克)
    """
    # 回购价差: 市场平稳时约 3~4元/克，取中间值4元
    BUY_SPREAD = 4.0
    return round(au9999_price - BUY_SPREAD, 2)


def fetch_bond_yield() -> Optional[Dict]:
    """获取中国十年期国债收益率
    
    数据来源: 中国货币网 (chinamoney.com.cn)
    API: /ags/ms/cm-u-bk-currency/SddsIntrRateGovYldHis
    返回最新一日的十年期国债收益率 (tenRate 字段)
    
    Returns:
        dict: {"yield_10y": float, "data_date": str} 或 None
    """
    try:
        url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/SddsIntrRateGovYldHis"
        params = {
            "lang": "CN",
            "pageNum": 1,
            "pageSize": 3  # 取最近3条确保有数据
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.chinamoney.com.cn/chinese/sddsintigy/",
            "Origin": "https://www.chinamoney.com.cn",
        }

        resp = requests.post(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # 检查响应状态
        head = data.get("head", {})
        if head.get("rep_code") != "200":
            print(f"[WARN] 中国货币网API返回异常: {head.get('rep_message')}")
            return None

        records = data.get("records", [])
        if not records:
            print("[WARN] 中国货币网未返回国债数据")
            return None

        # 取最新一条记录
        latest = records[0]
        ten_rate = latest.get("tenRate")
        data_date = latest.get("dateString")

        if ten_rate and float(ten_rate) > 0:
            return {
                "yield_10y": round(float(ten_rate), 4),
                "data_date": data_date
            }

        print("[WARN] 中国货币网十年期国债数据为空")
        return None

    except Exception as e:
        print(f"[ERROR] 获取国债收益率失败: {e}")
        return _fetch_bond_yield_fallback()


def _fetch_bond_yield_fallback() -> Optional[Dict]:
    """备用方案: 通过 AKShare 获取中国10年期国债收益率"""
    try:
        import akshare as ak
        df = ak.bond_zh_us_rate()
        if df is not None and not df.empty:
            if "中国10年" in df.columns:
                latest = df.iloc[-1]
                val = latest["中国10年"]
                if val and float(val) > 0:
                    return {"yield_10y": round(float(val), 4)}
    except Exception as e:
        print(f"[ERROR] 备用国债数据源也失败: {e}")
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
