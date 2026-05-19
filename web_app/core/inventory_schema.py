from __future__ import annotations


ITEM_SERVICE_COLUMNS = [
    ("track_inventory", "INTEGER NOT NULL DEFAULT 1"),
    ("unit", "TEXT"),
    ("minimum_stock_level", "NUMERIC NOT NULL DEFAULT 0"),
    ("opening_stock", "NUMERIC NOT NULL DEFAULT 0"),
    ("opening_cost", "NUMERIC NOT NULL DEFAULT 0"),
]

SALES_RETURN_COLUMNS = [
    ("return_stock_action", "TEXT DEFAULT 'Return to Stock'"),
]


STOCK_TABLE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        item_service_id INTEGER NOT NULL,
        movement_date TEXT NOT NULL,
        movement_type TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id INTEGER,
        source_no TEXT,
        quantity_in NUMERIC NOT NULL DEFAULT 0,
        quantity_out NUMERIC NOT NULL DEFAULT 0,
        unit_cost NUMERIC NOT NULL DEFAULT 0,
        remarks TEXT,
        created_by_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        adjustment_no TEXT NOT NULL,
        adjustment_date TEXT NOT NULL,
        adjustment_type TEXT NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'Posted',
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE(company_id, branch_id, adjustment_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_adjustment_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adjustment_id INTEGER NOT NULL,
        item_service_id INTEGER NOT NULL,
        quantity NUMERIC NOT NULL,
        unit_cost NUMERIC NOT NULL DEFAULT 0,
        remarks TEXT,
        FOREIGN KEY (adjustment_id) REFERENCES stock_adjustments(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id)
    )
    """,
]


STOCK_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_company_branch ON stock_movements(company_id, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_item ON stock_movements(item_service_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_date ON stock_movements(movement_date)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_type ON stock_movements(movement_type)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_source ON stock_movements(source_type, source_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_adjustments_company_branch ON stock_adjustments(company_id, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_adjustments_no ON stock_adjustments(adjustment_no)",
    "CREATE INDEX IF NOT EXISTS idx_stock_adjustments_date ON stock_adjustments(adjustment_date)",
    "CREATE INDEX IF NOT EXISTS idx_stock_adjustments_status ON stock_adjustments(status)",
]
