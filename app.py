"""
Flask Web 仪表盘 - 上海黄金交易所 AU9999 金价 & 国债收益率可视化
"""

from flask import Flask, render_template, jsonify
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "prices.db")

# 确保数据目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


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
    """最新数据摘要"""
    conn = get_db()
    
    # 最新金价
    gold = conn.execute(
        "SELECT fetch_date, fetch_time, price_cny_gram "
        "FROM gold_price ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    # 最新国债
    bond = conn.execute(
        "SELECT fetch_date, fetch_time, yield_10y "
        "FROM bond_yield ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    # 金价30日统计
    gold_stats = conn.execute("""
        SELECT 
            COALESCE(MAX(price_cny_gram), 0) as high,
            COALESCE(MIN(price_cny_gram), 0) as low,
            COALESCE(AVG(price_cny_gram), 0) as avg
        FROM gold_price 
        WHERE fetch_date >= date('now', '-30 days')
    """).fetchone()
    
    # 国债30日统计
    bond_stats = conn.execute("""
        SELECT 
            COALESCE(MAX(yield_10y), 0) as high,
            COALESCE(MIN(yield_10y), 0) as low,
            COALESCE(AVG(yield_10y), 0) as avg
        FROM bond_yield 
        WHERE fetch_date >= date('now', '-30 days')
    """).fetchone()
    
    # 最新油价 (深圳和泉州各取最新)
    oil_sz = conn.execute(
        "SELECT region, gasoline_92, data_date FROM oil_price WHERE region='深圳(广东)' ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    oil_qz = conn.execute(
        "SELECT region, gasoline_92, data_date FROM oil_price WHERE region='泉州(福建)' ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    # 最新M2 CAGR
    m2 = conn.execute(
        "SELECT cagr_20y, start_m2, current_m2, growth_multiple, data_period "
        "FROM m2_cagr ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    # 最新CPI CAGR
    cpi = conn.execute(
        "SELECT cagr_20y, cpi_max, cpi_min, cpi_median, data_period, data_count "
        "FROM cpi_cagr ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    # 金价变化 (与昨天对比)
    yesterday_gold = conn.execute(
        "SELECT price_cny_gram FROM gold_price WHERE fetch_date = date('now', '-1 day') ORDER BY fetch_time DESC LIMIT 1"
    ).fetchone()
    
    gold_change = None
    if gold and yesterday_gold and yesterday_gold["price_cny_gram"]:
        gold_change = round(gold["price_cny_gram"] - yesterday_gold["price_cny_gram"], 2)
    
    conn.close()
    
    return jsonify({
        "gold": {
            "price_cny_gram": gold["price_cny_gram"] if gold else None,
            "change_vs_yesterday": gold_change,
            "update_time": gold["fetch_time"] if gold else None,
            "stats_30d": {
                "high": round(gold_stats["high"], 2),
                "low": round(gold_stats["low"], 2),
                "avg": round(gold_stats["avg"], 2)
            }
        },
        "bond": {
            "yield_10y": bond["yield_10y"] if bond else None,
            "update_time": bond["fetch_time"] if bond else None,
            "stats_30d": {
                "high": round(bond_stats["high"], 4),
                "low": round(bond_stats["low"], 4),
                "avg": round(bond_stats["avg"], 4)
            }
        },
        "oil": {
            "shenzhen": {
                "price": oil_sz["gasoline_92"] if oil_sz else None,
                "data_date": oil_sz["data_date"] if oil_sz else None
            },
            "quanzhou": {
                "price": oil_qz["gasoline_92"] if oil_qz else None,
                "data_date": oil_qz["data_date"] if oil_qz else None
            }
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
            source TEXT DEFAULT 'chinamoney.com.cn'
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
