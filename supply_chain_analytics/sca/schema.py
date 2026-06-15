"""SQL star schema (SQLAlchemy Core) shared by SQLite (dev) and Postgres.

The schema mirrors the simplified star schema in the spec: conformed
dimensions (item, vendor, calendar) plus the facts needed for coverage and
CTP-ETA (on-hand, open POs, weekly demand, sales-order lines, BOM, PO
receipts, actual shipments).

Using SQLAlchemy Core (a :class:`~sqlalchemy.MetaData` registry) rather than
the ORM keeps the load path a plain ``DataFrame.to_sql`` and the read path a
plain ``pd.read_sql`` while still letting us create the tables portably.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

dim_item = Table(
    "dim_item", metadata,
    Column("item_id", String, primary_key=True),
    Column("descr", String),
    Column("family", String),
    Column("abc", String(1)),
    Column("xyz", String(1)),
    Column("planning_method", String),
    Column("lead_time_wks", Numeric),
    Column("safety_stock", Numeric),
    Column("lot_size", Numeric),
    Column("assembly_days", Numeric),
    Column("pack_ship_days", Numeric),
    Column("decoupling_flag", Boolean),
)

dim_vendor = Table(
    "dim_vendor", metadata,
    Column("vendor_id", String, primary_key=True),
    Column("name", String),
)

dim_calendar = Table(
    "dim_calendar", metadata,
    Column("date_id", Date, primary_key=True),
    Column("iso_week", Integer),
    Column("month", Integer),
    Column("year", Integer),
)

fact_onhand = Table(
    "fact_onhand", metadata,
    Column("item_id", String, index=True),
    Column("warehouse", String),
    Column("qty_onhand", Numeric),
    Column("qty_allocated", Numeric),
    Column("snapshot_date", Date),
)

fact_open_po = Table(
    "fact_open_po", metadata,
    Column("po_id", String),
    Column("item_id", String, index=True),
    Column("vendor_id", String),
    Column("qty_ordered", Numeric),
    Column("promised_date", Date),
    Column("warehouse", String),
)

fact_demand_weekly = Table(
    "fact_demand_weekly", metadata,
    Column("item_id", String, index=True),
    Column("iso_week", Integer),
    Column("year", Integer),
    Column("forecast_qty", Numeric),
    Column("firm_order_qty", Numeric),
    Column("warehouse", String),
)

fact_sales_order_line = Table(
    "fact_sales_order_line", metadata,
    Column("so_id", String, index=True),
    Column("line_id", String),
    Column("customer", String),
    Column("item_id", String),
    Column("qty", Numeric),
    Column("request_date", Date),
    Column("warehouse", String),
)

fact_bom = Table(
    "fact_bom", metadata,
    Column("parent_item_id", String, index=True),
    Column("component_item_id", String),
    Column("qty_per", Numeric),
)

fact_po_receipts = Table(
    "fact_po_receipts", metadata,
    Column("po_id", String),
    Column("item_id", String),
    Column("vendor_id", String, index=True),
    Column("order_date", Date),
    Column("promised_date", Date),
    Column("receipt_date", Date),
    Column("qty", Numeric),
)

fact_actual_ship = Table(
    "fact_actual_ship", metadata,
    Column("item_id", String, index=True),
    Column("iso_week", Integer),
    Column("year", Integer),
    Column("actual_qty", Numeric),
)


def make_engine(database_url: str) -> Engine:
    """Create an engine; ``future``-style, works for sqlite and postgres URLs."""
    return create_engine(database_url, future=True)


def create_all(engine: Engine) -> None:
    metadata.create_all(engine)
