"""ETL: pull Generic Inquiries, map fields, load the SQL star schema.

Acumatica GI field names vary per deployment, so the raw->target column
mapping is data-driven (``field_maps`` in config).  Each logical feed maps to
one fact/dimension table; rows are renamed/selected per the map and written
with ``DataFrame.to_sql`` (``if_exists="replace"`` for a clean daily refresh).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.engine import Engine

from .config import Config
from .odata_client import AcumaticaODataClient
from .schema import create_all

# Logical feed -> destination table.  Keys match config inquiry/field-map keys.
FEED_TABLES = {
    "inventory_onhand": "fact_onhand",
    "open_pos": "fact_open_po",
    "sales_orders": "fact_sales_order_line",
    "bom": "fact_bom",
    "production_orders": "fact_production_order",  # reserved for later
    "shipments": "fact_actual_ship",
    "po_receipts": "fact_po_receipts",
    "items": "dim_item",
    "vendors": "dim_vendor",
}


def map_rows(rows: list[dict], field_map: dict[str, str] | None) -> pd.DataFrame:
    """Rename/select raw OData rows to target columns.

    With no ``field_map`` the rows are returned as-is (useful when GI field
    names already match the schema, e.g. in tests).
    """
    df = pd.DataFrame(rows)
    if not field_map:
        return df
    # field_map is {target_column: source_field}; keep only mapped columns.
    present = {tgt: src for tgt, src in field_map.items() if src in df.columns}
    out = df[list(present.values())].rename(columns={v: k for k, v in present.items()})
    return out


def load_feed(engine: Engine, table: str, df: pd.DataFrame) -> int:
    """Replace ``table`` with ``df``; return the row count written."""
    df.to_sql(table, engine, if_exists="replace", index=False)
    return len(df)


def run_etl(config: Config, client: AcumaticaODataClient,
            engine: Engine) -> dict[str, int]:
    """Pull every configured feed and load it; return rows-per-table."""
    create_all(engine)
    loaded: dict[str, int] = {}
    for feed, inquiry in config.acumatica.inquiries.items():
        table = FEED_TABLES.get(feed)
        if not table:
            continue
        rows = client.fetch(inquiry)
        df = map_rows(rows, config.field_maps.get(feed))
        loaded[table] = load_feed(engine, table, df)
    return loaded
