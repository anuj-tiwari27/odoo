"""Demo data seeding for a zero-config local run.

Populates the star schema with a small, self-contained dataset so the web
dashboard and CLI can be exercised without an Acumatica connection.  The
scenario is tuned to show every output state: an EXPEDITE shortage, a
PO-constrained kit ETA, and a same-day order.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.engine import Engine

from .schema import create_all

# Fixed reference date so the demo is deterministic regardless of wall-clock.
DEMO_TODAY = date(2026, 6, 1)


def seed_demo(engine: Engine) -> None:
    """(Re)create the schema and load the demo dataset."""
    create_all(engine)

    pd.DataFrame([
        {"item_id": "EXTR-RAIL-HD", "descr": "HD extruded rail", "family": "EXTR",
         "lead_time_wks": 5, "safety_stock": 50, "assembly_days": 0.5,
         "pack_ship_days": 0.5, "decoupling_flag": True},
        {"item_id": "EXTR-PANEL-WALL", "descr": "Wall panel extrusion", "family": "EXTR",
         "lead_time_wks": 5, "safety_stock": 50, "assembly_days": 0,
         "pack_ship_days": 0, "decoupling_flag": True},
        {"item_id": "SEAL-KIT-2", "descr": "2in seal kit", "family": "SEAL",
         "lead_time_wks": 2, "safety_stock": 100, "assembly_days": 0,
         "pack_ship_days": 0, "decoupling_flag": True},
        {"item_id": "KIT-HVS-08", "descr": "HVS 08 3-cyl kit", "family": "KIT",
         "lead_time_wks": 0, "safety_stock": 0, "assembly_days": 0.5,
         "pack_ship_days": 0.5, "decoupling_flag": False},
        {"item_id": "KIT-TB-04", "descr": "TB 04x08 AL kit", "family": "KIT",
         "lead_time_wks": 0, "safety_stock": 0, "assembly_days": 0,
         "pack_ship_days": 0, "decoupling_flag": False},
    ]).to_sql("dim_item", engine, if_exists="replace", index=False)

    pd.DataFrame([
        {"item_id": "EXTR-RAIL-HD", "warehouse": "MAIN", "qty_onhand": 240, "qty_allocated": 0},
        {"item_id": "EXTR-PANEL-WALL", "warehouse": "MAIN", "qty_onhand": 12, "qty_allocated": 0},
        {"item_id": "SEAL-KIT-2", "warehouse": "MAIN", "qty_onhand": 1250, "qty_allocated": 0},
    ]).to_sql("fact_onhand", engine, if_exists="replace", index=False)

    pd.DataFrame([
        {"po_id": "PO-5501", "item_id": "EXTR-RAIL-HD", "vendor_id": "MILL-A",
         "qty_ordered": 200, "promised_date": "2026-06-10", "warehouse": "MAIN"},
        {"po_id": "PO-5512", "item_id": "EXTR-PANEL-WALL", "vendor_id": "MILL-B",
         "qty_ordered": 200, "promised_date": "2026-06-03", "warehouse": "MAIN"},
    ]).to_sql("fact_open_po", engine, if_exists="replace", index=False)

    pd.DataFrame([
        {"parent_item_id": "KIT-HVS-08", "component_item_id": "EXTR-PANEL-WALL", "qty_per": 3},
        {"parent_item_id": "KIT-HVS-08", "component_item_id": "SEAL-KIT-2", "qty_per": 2},
        {"parent_item_id": "KIT-TB-04", "component_item_id": "SEAL-KIT-2", "qty_per": 4},
    ]).to_sql("fact_bom", engine, if_exists="replace", index=False)

    pd.DataFrame([
        {"so_id": "48817", "line_id": "1", "customer": "United Rentals #4471",
         "item_id": "KIT-HVS-08", "qty": 10, "request_date": "2026-06-05", "warehouse": "MAIN"},
        {"so_id": "48822", "line_id": "1", "customer": "Sunbelt #119",
         "item_id": "KIT-TB-04", "qty": 4, "request_date": "2026-06-02", "warehouse": "MAIN"},
    ]).to_sql("fact_sales_order_line", engine, if_exists="replace", index=False)

    pd.DataFrame([
        {"item_id": "EXTR-RAIL-HD", "year": 2026, "month": 6, "forecast_qty": 340},
        {"item_id": "EXTR-PANEL-WALL", "year": 2026, "month": 6, "forecast_qty": 255},
        {"item_id": "SEAL-KIT-2", "year": 2026, "month": 6, "forecast_qty": 600},
    ]).to_sql("fact_monthly_forecast", engine, if_exists="replace", index=False)
