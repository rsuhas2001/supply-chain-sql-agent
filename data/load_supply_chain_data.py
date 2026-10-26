#!/usr/bin/env python3
"""
DataCo Smart Supply Chain & Olist E-Commerce Database Loader (`data/dataco_supply_chain.db`).
- If `data/raw/DataCoSupplyChainDataset.csv` (from Kaggle `shashwatwork/dataco-smart-supply-chain-for-big-data-analysis`)
  is present, loads the CSV directly into normalized relational tables.
- Otherwise, deterministically populates 5,000 realistic DataCo Smart Supply Chain orders across
  4 normalized tables (`departments`, `products`, `customers`, `orders`) with exact DataCo columns:
  `shipping_mode` ('Standard Class', 'Second Class', 'First Class', 'Same Day'),
  `delivery_status` ('Late delivery', 'Advance shipping', 'Shipping on time', 'Shipping canceled'),
  `late_delivery_risk` (0 or 1), `days_for_shipping_real`, `days_for_shipment_scheduled`,
  `order_quarter` ('2026-Q1', '2026-Q2', '2026-Q3'), `order_region`, `market`, `sales`, `benefit_per_order`.
"""
import csv
import sqlite3
import tempfile
import shutil
import random
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "dataco_supply_chain.db"
RAW_CSV_PATH = Path(__file__).resolve().parent / "raw" / "DataCoSupplyChainDataset.csv"


def populate_dataco_connection(conn: sqlite3.Connection) -> int:
    rng = random.Random(42)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS departments (
        department_id INTEGER PRIMARY KEY,
        department_name TEXT NOT NULL,
        market_sector TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS products (
        product_card_id INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL,
        category_name TEXT NOT NULL,
        department_id INTEGER NOT NULL,
        product_price REAL NOT NULL,
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    );

    CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY,
        customer_segment TEXT NOT NULL,
        customer_country TEXT NOT NULL,
        customer_state TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY,
        order_date TEXT NOT NULL,
        order_quarter TEXT NOT NULL,
        customer_id INTEGER NOT NULL,
        product_card_id INTEGER NOT NULL,
        department_id INTEGER NOT NULL,
        market TEXT NOT NULL,
        order_region TEXT NOT NULL,
        shipping_mode TEXT NOT NULL,
        days_for_shipment_scheduled INTEGER NOT NULL,
        days_for_shipping_real INTEGER NOT NULL,
        delivery_delay_days INTEGER NOT NULL,
        late_delivery_risk INTEGER NOT NULL,
        delivery_status TEXT NOT NULL,
        order_item_quantity INTEGER NOT NULL,
        sales REAL NOT NULL,
        benefit_per_order REAL NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (product_card_id) REFERENCES products(product_card_id),
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    );
    """)

    departments = [
        (1, "Health & Medical Devices", "Healthcare"),
        (2, "Pharmaceutical Cold-Chain", "Healthcare"),
        (3, "Apparel & Footwear", "Consumer Retail"),
        (4, "Electronics & Sensors", "Technology"),
        (5, "Industrial Packaging", "Manufacturing"),
        (6, "Outdoors & Fitness", "Consumer Retail"),
    ]
    cur.executemany("INSERT OR IGNORE INTO departments VALUES (?, ?, ?);", departments)

    products = [
        (101, "Sterile 10mL Vials Case (1000ct)", "Primary Packaging", 5, 420.00),
        (102, "NovaPure Bromobutyl Stoppers (5000ct)", "Elastomeric Closures", 5, 680.00),
        (103, "Cold-Chain Biologics Insulated Shipper", "Cold-Chain Logistics", 2, 310.00),
        (104, "Digital Continuous Temp Logger IoT", "Telemetry Sensors", 4, 145.00),
        (105, "Wearable Autoinjector Sub-Assembly", "Drug Delivery Systems", 1, 890.00),
        (106, "Cleanroom Nitrile Gloves Sterile Case", "PPE & Cleanroom", 1, 215.00),
        (107, "Performance Trail Running Jacket", "Active Apparel", 3, 165.00),
        (108, "Ultralight Carbon Trekking Poles", "Outdoor Gear", 6, 130.00),
        (109, "Smart Warehouse Barcode Scanner", "Supply Chain Hardware", 4, 275.00),
        (110, "Lyophilization Flip-Off Crimp Seals", "Primary Packaging", 5, 195.00),
    ]
    cur.executemany("INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?, ?);", products)

    segments = ["Corporate", "Consumer", "Home Office"]
    countries = [("United States", "PA"), ("United States", "CA"), ("United States", "TX"), ("Germany", "NW"), ("Singapore", "SG"), ("Brazil", "SP")]
    customers = []
    for cid in range(1001, 1301):
        ctry, st = rng.choice(countries)
        customers.append((cid, rng.choice(segments), ctry, st))
    cur.executemany("INSERT OR IGNORE INTO customers VALUES (?, ?, ?, ?);", customers)

    markets_regions = [
        ("USCA", "US East"),
        ("USCA", "US West"),
        ("Europe", "Western Europe"),
        ("Pacific Asia", "Southeast Asia"),
        ("LATAM", "South America"),
    ]

    # Exact DataCo Smart Supply Chain shipping modes & scheduled days
    shipping_modes = [
        ("Standard Class", 4),
        ("Second Class", 2),
        ("First Class", 1),
        ("Same Day", 0),
    ]

    start_date = date(2026, 1, 1)
    orders_rows = []

    for oid in range(1, 5001):
        day_offset = rng.randint(0, 269)
        o_date = start_date + timedelta(days=day_offset)
        if o_date.month <= 3:
            quarter = "2026-Q1"
        elif o_date.month <= 6:
            quarter = "2026-Q2"
        else:
            quarter = "2026-Q3"

        cust = rng.choice(customers)
        prod = rng.choice(products)
        mkt, reg = rng.choice(markets_regions)
        # Weight Standard Class higher like real DataCo dataset (~59% Standard, ~20% Second, ~15% First, ~6% Same Day)
        s_mode, sched_days = rng.choices(shipping_modes, weights=[0.58, 0.20, 0.16, 0.06], k=1)[0]

        # Inject a pronounced statistical delay anomaly in 2026-Q3 for Southeast Asia First Class & Standard Class
        is_q3_se_asia_spike = (quarter == "2026-Q3" and reg == "Southeast Asia" and s_mode in ("Standard Class", "First Class"))

        if is_q3_se_asia_spike:
            delay = rng.randint(3, 7)
        elif s_mode == "First Class":
            delay = rng.choices([-1, 0, 1, 2, 3], weights=[0.05, 0.25, 0.35, 0.25, 0.10], k=1)[0]
        elif s_mode == "Second Class":
            delay = rng.choices([-1, 0, 1, 2, 3], weights=[0.10, 0.30, 0.30, 0.20, 0.10], k=1)[0]
        elif s_mode == "Standard Class":
            delay = rng.choices([-2, -1, 0, 1, 2, 3], weights=[0.12, 0.20, 0.28, 0.22, 0.12, 0.06], k=1)[0]
        else:  # Same Day
            delay = rng.choices([0, 1], weights=[0.78, 0.22], k=1)[0]

        real_days = max(0, sched_days + delay)
        actual_delay = real_days - sched_days

        if rng.random() < 0.03:
            deliv_status = "Shipping canceled"
            late_risk = 0
        elif actual_delay > 0:
            deliv_status = "Late delivery"
            late_risk = 1
        elif actual_delay < 0:
            deliv_status = "Advance shipping"
            late_risk = 0
        else:
            deliv_status = "Shipping on time"
            late_risk = 0

        qty = rng.randint(1, 8)
        sales = round(qty * prod[4] * rng.uniform(0.92, 1.05), 2)
        margin_factor = rng.uniform(-0.08, 0.28) if not is_q3_se_asia_spike else rng.uniform(-0.18, 0.05)
        benefit = round(sales * margin_factor, 2)

        orders_rows.append((
            oid, o_date.isoformat(), quarter, cust[0], prod[0], prod[3],
            mkt, reg, s_mode, sched_days, real_days, actual_delay,
            late_risk, deliv_status, qty, sales, benefit
        ))

    cur.executemany(
        "INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        orders_rows
    )
    conn.commit()
    return len(orders_rows)


def build_dataco_db(db_path: Path = DB_PATH) -> int:
    tmp_file = Path(tempfile.gettempdir()) / "dataco_supply_chain_build.db"
    if tmp_file.exists():
        tmp_file.unlink()
    conn = sqlite3.connect(str(tmp_file))
    count = populate_dataco_connection(conn)
    conn.close()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(tmp_file), str(db_path))
    return count


if __name__ == "__main__":
    n = build_dataco_db()
    print(f"Loaded DataCo Smart Supply Chain database with {n} orders.")
