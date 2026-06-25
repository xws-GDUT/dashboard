"""
Flask Web 仪表盘 - 上海黄金交易所 AU9999 金价 & 国债收益率可视化
"""

from flask import Flask, render_template, jsonify
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "prices.db")

# 确保数据目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@app.route("/healthz")
def healthz():
    """健康检查端点 - 供 Cloudflare Worker 保活使用"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    """主页"""
    return render_template("dashboard.html")


@app.route("/api/summary")
def api_summary():
    """最新数据摘要 - 并行获取，8秒超时"""
    conn = get_db()
    
    # === 并行获取实时数据 (金价、国债、LPR) ===
    gold_data = None
    bond_data = None
    lpr_data = None
    m1m2_data = None
    
    def fetch_gold_wrapper():
        from fetcher import fetch_gold_price
        return fetch_gold_price()
    
    def fetch_bond_wrapper():
        from fetcher import fetch_bond_yield
        return fetch_bond_yield()
    
    def fetch_lpr_wrapper():
        from fetcher import fetch_lpr
        return fetch_lpr()
    
    def fetch_m1m2_wrapper():
        from fetcher import fetch_m1m2_gap
        return fetch_m1m2_gap()
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_gold_wrapper): "gold",
            executor.submit(fetch_bond_wrapper): "bond",
            executor.submit(fetch_lpr_wrapper): "lpr",
            executor.submit(fetch_m1m2_wrapper): "m1m2",
        }
        for future in futures:
            name = futures[future]
            try:
                result = future.result(timeout=8)
                if name == "gold":
                    gold_data = result
                elif name == "bond":
                    bond_data = result
                elif name == "lpr":
                    lpr_data = result
                elif name == "m1m2":
                    m1m2_data = result
            except Exception:
                pass  # 失败则使用数据库缓存
    
    # === 处理金价 ===
    if gold_data:
        gold_price = gold_data["price_cny_gram"]
        gold_time = gold_data.get("updated_at", "")
    else:
        gold_db = conn.execute(
            "SELECT price_cny_gram, fetch_time FROM gold_price ORDER BY fetch_time DESC LIMIT 1"
        ).fetchone()
        gold_price = gold_db["price_cny_gram"] if gold_db else None
        gold_time = gold_db["fetch_time"] if gold_db else None
    
    shuibei_price = None
    if gold_price:
        from fetcher import calc_shuibei_buy_price
        shuibei_price = calc_shuibei_buy_price(gold_price)
    
    # === 处理国债 ===
    if bond_data:
        bond_yield_val = bond_data["yield_10y"]
        bond_time = datetime.now().isoformat()
    else:
        bond_db = conn.execute(
            "SELECT yield_10y, fetch_time FROM bond_yield ORDER BY fetch_time DESC LIMIT 1"
        ).fetchone()
        bond_yield_val = bond_db["yield_10y"] if bond_db else None
        bond_time = bond_db["fetch_time"] if bond_db else None
    
    # === 处理LPR ===
    if not lpr_data:
        lpr_db = conn.execute(
            "SELECT lpr_1y, lpr_5y, data_date FROM lpr_data ORDER BY fetch_time DESC LIMIT 1"
        ).fetchone() if False else None  # LPR用实时数据
    if not lpr_data:
        # LPR变化慢，用默认值
        lpr_data = {"lpr_1y": 3.0, "lpr_5y": 3.5, "data_date": "2026-06-22"}
    
    # === 公积金贷款利率 (固定值，央行发布) ===
    # 2026年1月1日起: 首套5年以上2.6%, 二套5年以上3.075%
    fund_rate = {
        "first_5y_plus": 2.6,
        "first_5y_below": 2.1,
        "second_5y_plus": 3.075,
        "second_5y_below": 2.525,
        "data_date": "2026-01-01",
        "source": "中国人民银行"
    }
    
    # === 快速数据库查询 (统计+缓存数据) ===
    gold_stats = conn.execute("""
        SELECT COALESCE(MAX(price_cny_gram), 0) as high,
               COALESCE(MIN(price_cny_gram), 0) as low,
               COALESCE(AVG(price_cny_gram), 0) as avg
        FROM gold_price WHERE fetch_date >= date('now', '-30 days')
    """).fetchone()
    
    bond_stats = conn.execute("""
        SELECT COALESCE(MAX(yield_10y), 0) as high,
               COALESCE(MIN(yield_10y), 0) as low,
               COALESCE(AVG(yield_10y), 0) as avg
        FROM bond_yield WHERE fetch_date >= date('now', '-30 days')
    """).fetchone()
    
    oil_sz = conn.execute(
        "SELECT gasoline_92, data_date FROM oil_price WHERE region='深圳(广东)' ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    oil_qz = conn.execute(
        "SELECT gasoline_92, data_date FROM oil_price WHERE region='泉州(福建)' ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    m2 = conn.execute(
        "SELECT cagr_20y, start_m2, current_m2, growth_multiple, data_period FROM m2_cagr ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    cpi = conn.execute(
        "SELECT cagr_20y, cpi_max, cpi_min, cpi_median, data_period FROM cpi_cagr ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    yesterday_gold = conn.execute(
        "SELECT price_cny_gram FROM gold_price WHERE fetch_date = date('now', '-1 day') ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    gold_change = None
    if gold_price and yesterday_gold and yesterday_gold["price_cny_gram"]:
        gold_change = round(gold_price - yesterday_gold["price_cny_gram"], 2)
    
    conn.close()
    
    return jsonify({
        "gold": {
            "price_cny_gram": gold_price,
            "shuibei_buy": shuibei_price,
            "change_vs_yesterday": gold_change,
            "update_time": gold_time,
            "stats_30d": {
                "high": round(gold_stats["high"], 2),
                "low": round(gold_stats["low"], 2),
                "avg": round(gold_stats["avg"], 2)
            }
        },
        "bond": {
            "yield_10y": bond_yield_val,
            "update_time": bond_time,
            "stats_30d": {
                "high": round(bond_stats["high"], 4),
                "low": round(bond_stats["low"], 4),
                "avg": round(bond_stats["avg"], 4)
            }
        },
        "oil": {
            "shenzhen": {"price": oil_sz["gasoline_92"] if oil_sz else None, "data_date": oil_sz["data_date"] if oil_sz else None},
            "quanzhou": {"price": oil_qz["gasoline_92"] if oil_qz else None, "data_date": oil_qz["data_date"] if oil_qz else None}
        },
        "m2": {
            "cagr_20y": m2["cagr_20y"] if m2 else None,
            "start_m2": m2["start_m2"] if m2 else None,
            "current_m2": m2["current_m2"] if m2 else None,
            "growth_multiple": m2["growth_multiple"] if m2 else None,
            "data_period": m2["data_period"] if m2 else None
        },
        "cpi": {
            "cagr_20y": cpi["cagr_20y"] if cpi else None,
            "cpi_max": cpi["cpi_max"] if cpi else None,
            "cpi_min": cpi["cpi_min"] if cpi else None,
            "cpi_median": cpi["cpi_median"] if cpi else None,
            "data_period": cpi["data_period"] if cpi else None
        },
        "lpr": {
            "lpr_1y": lpr_data["lpr_1y"] if lpr_data else None,
            "lpr_5y": lpr_data["lpr_5y"] if lpr_data else None,
            "data_date": lpr_data["data_date"] if lpr_data else None
        },
        "fund_rate": fund_rate,
        "m1m2_gap": {
            "gap": m1m2_data["gap"] if m1m2_data else None,
            "m2_yoy": m1m2_data["m2_yoy"] if m1m2_data else None,
            "m1_yoy": m1m2_data["m1_yoy"] if m1m2_data else None,
            "data_date": m1m2_data["data_date"] if m1m2_data else None
        }
    })


@app.route("/api/gold_history")
def api_gold_history():
    """金价历史数据 (最近90天)"""
    days = 90
    conn = get_db()
    rows = conn.execute(f"""
        SELECT fetch_date, MAX(price_cny_gram) as price_cny_gram
        FROM gold_price 
        WHERE fetch_date >= date('now', '-{days} days')
        GROUP BY fetch_date
        ORDER BY fetch_date ASC
    """).fetchall()
    conn.close()
    
    return jsonify([{
        "date": r["fetch_date"],
        "price_cny_gram": r["price_cny_gram"]
    } for r in rows])


@app.route("/api/m1m2_monthly")
def api_m1m2_monthly():
    """M2/M1 环比增长率历史 (最近24个月)"""
    try:
        from fetcher import fetch_m1m2_monthly
        data = fetch_m1m2_monthly()
        if data:
            return jsonify(data)
    except Exception:
        pass
    return jsonify([])


@app.route("/api/bond_history")
def api_bond_history():
    """国债收益率历史数据 (最近90天)"""
    days = 90
    conn = get_db()
    rows = conn.execute(f"""
        SELECT fetch_date, MAX(yield_10y) as yield_10y
        FROM bond_yield 
        WHERE fetch_date >= date('now', '-{days} days')
        GROUP BY fetch_date
        ORDER BY fetch_date ASC
    """).fetchall()
    conn.close()
    
    return jsonify([{
        "date": r["fetch_date"],
        "yield_10y": r["yield_10y"]
    } for r in rows])


@app.route("/api/combined")
def api_combined():
    """组合数据: 金价与国债收益率 (最近90天)"""
    days = 90
    conn = get_db()
    
    gold_rows = conn.execute(f"""
        SELECT fetch_date, MAX(price_cny_gram) as price_cny_gram
        FROM gold_price 
        WHERE fetch_date >= date('now', '-{days} days')
        GROUP BY fetch_date
        ORDER BY fetch_date ASC
    """).fetchall()
    
    bond_rows = conn.execute(f"""
        SELECT fetch_date, MAX(yield_10y) as yield_10y
        FROM bond_yield 
        WHERE fetch_date >= date('now', '-{days} days')
        GROUP BY fetch_date
        ORDER BY fetch_date ASC
    """).fetchall()
    
    conn.close()
    
    gold_dict = {r["fetch_date"]: r["price_cny_gram"] for r in gold_rows}
    bond_dict = {r["fetch_date"]: r["yield_10y"] for r in bond_rows}
    
    all_dates = sorted(set(list(gold_dict.keys()) + list(bond_dict.keys())))
    
    return jsonify([{
        "date": d,
        "gold_cny_gram": gold_dict.get(d),
        "bond_yield_10y": bond_dict.get(d)
    } for d in all_dates])


def init_web_db():
    """确保数据库在Web启动时存在"""
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
            source TEXT DEFAULT 'chinabond.com.cn'
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gold_date ON gold_price(fetch_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bond_date ON bond_yield(fetch_date)")
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oil_date ON oil_price(fetch_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oil_region ON oil_price(region)")
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


# === 分片API: 逐个返回数据，前端逐卡片渲染 ===

@app.route("/api/gold_live")
def api_gold_live():
    """实时金价 + 水贝买价"""
    try:
        from fetcher import fetch_gold_price, calc_shuibei_buy_price
        gold_data = fetch_gold_price()
        if gold_data:
            return jsonify({
                "price_cny_gram": gold_data["price_cny_gram"],
                "shuibei_buy": calc_shuibei_buy_price(gold_data["price_cny_gram"]),
                "update_time": gold_data.get("updated_at", "")
            })
    except:
        pass
    # fallback
    conn = get_db()
    g = conn.execute("SELECT price_cny_gram FROM gold_price ORDER BY fetch_time DESC LIMIT 1").fetchone()
    conn.close()
    if g:
        from fetcher import calc_shuibei_buy_price
        return jsonify({"price_cny_gram": g["price_cny_gram"], "shuibei_buy": calc_shuibei_buy_price(g["price_cny_gram"])})
    return jsonify({})


@app.route("/api/bond_live")
def api_bond_live():
    """实时国债收益率"""
    try:
        from fetcher import fetch_bond_yield
        data = fetch_bond_yield()
        if data:
            return jsonify(data)
    except:
        pass
    conn = get_db()
    b = conn.execute("SELECT yield_10y FROM bond_yield ORDER BY fetch_time DESC LIMIT 1").fetchone()
    conn.close()
    if b:
        return jsonify({"yield_10y": b["yield_10y"]})
    return jsonify({})


@app.route("/api/lpr_live")
def api_lpr_live():
    """LPR利率"""
    try:
        from fetcher import fetch_lpr
        data = fetch_lpr()
        if data:
            return jsonify(data)
    except:
        pass
    return jsonify({"lpr_1y": 3.0, "lpr_5y": 3.5, "data_date": "2026-06-22"})


@app.route("/api/m1m2_live")
def api_m1m2_live():
    """M2-M1剪刀差"""
    try:
        from fetcher import fetch_m1m2_gap
        data = fetch_m1m2_gap()
        if data:
            return jsonify(data)
    except:
        pass
    return jsonify({})


@app.route("/api/static_data")
def api_static_data():
    """缓存数据: M2年化、CPI、油价、公积金"""
    conn = get_db()
    m2 = conn.execute("SELECT cagr_20y, growth_multiple, data_period FROM m2_cagr ORDER BY fetch_time DESC LIMIT 1").fetchone()
    cpi = conn.execute("SELECT cagr_20y, cpi_max, cpi_min, data_period FROM cpi_cagr ORDER BY fetch_time DESC LIMIT 1").fetchone()
    oil_sz = conn.execute("SELECT gasoline_92, data_date FROM oil_price WHERE region='深圳(广东)' ORDER BY fetch_time DESC LIMIT 1").fetchone()
    oil_qz = conn.execute("SELECT gasoline_92, data_date FROM oil_price WHERE region='泉州(福建)' ORDER BY fetch_time DESC LIMIT 1").fetchone()
    conn.close()
    return jsonify({
        "m2": {"cagr_20y": m2["cagr_20y"], "growth_multiple": m2["growth_multiple"], "data_period": m2["data_period"]} if m2 else None,
        "cpi": {"cagr_20y": cpi["cagr_20y"], "cpi_max": cpi["cpi_max"], "cpi_min": cpi["cpi_min"], "data_period": cpi["data_period"]} if cpi else None,
        "oil_sz": {"price": oil_sz["gasoline_92"], "data_date": oil_sz["data_date"]} if oil_sz else None,
        "oil_qz": {"price": oil_qz["gasoline_92"], "data_date": oil_qz["data_date"]} if oil_qz else None,
        "fund_rate": {"first_5y_plus": 2.6, "first_5y_below": 2.1, "second_5y_plus": 3.075, "second_5y_below": 2.525, "data_date": "2026-01-01", "source": "中国人民银行"}
    })


if __name__ == "__main__":
    init_web_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n🚀 上海金 AU9999 & 国债收益率追踪器已启动!")
    print(f"📊 访问 http://0.0.0.0:{port} 查看仪表盘")
    print("📡 API 端点:")
    print("   /api/summary      - 最新数据摘要")
    print("   /api/gold_history  - 金价历史")
    print("   /api/bond_history  - 国债收益率历史")
    print("   /api/combined      - 组合数据\n")
    app.run(host="0.0.0.0", port=port, debug=False)
