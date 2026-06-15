from datetime import date

import pandas as pd

from sca.config import Config, AcumaticaConfig
from sca.pipeline import run_analytics
from sca.schema import create_all, make_engine


def _config(db_url):
    return Config(
        database_url=db_url,
        acumatica=AcumaticaConfig(base_url="x", company="c",
                                  username="u", password="p"),
    )


def _seed(engine):
    dim_item = pd.DataFrame([
        {"item_id": "KIT", "lead_time_wks": 0, "safety_stock": 0,
         "assembly_days": 0.5, "pack_ship_days": 0.5, "decoupling_flag": False},
        {"item_id": "ROD", "lead_time_wks": 4, "safety_stock": 50,
         "assembly_days": 0, "pack_ship_days": 0, "decoupling_flag": True},
    ])
    dim_item.to_sql("dim_item", engine, if_exists="replace", index=False)

    pd.DataFrame([{"item_id": "ROD", "warehouse": "MAIN", "qty_onhand": 30,
                   "qty_allocated": 0}]).to_sql(
        "fact_onhand", engine, if_exists="replace", index=False)

    pd.DataFrame(columns=["po_id", "item_id", "vendor_id", "qty_ordered",
                          "promised_date", "warehouse"]).to_sql(
        "fact_open_po", engine, if_exists="replace", index=False)

    pd.DataFrame([{"parent_item_id": "KIT", "component_item_id": "ROD",
                   "qty_per": 2}]).to_sql(
        "fact_bom", engine, if_exists="replace", index=False)

    pd.DataFrame([{"so_id": "SO1", "line_id": "1", "customer": "Acme",
                   "item_id": "KIT", "qty": 5, "request_date": "2026-06-15",
                   "warehouse": "MAIN"}]).to_sql(
        "fact_sales_order_line", engine, if_exists="replace", index=False)

    pd.DataFrame([{"item_id": "ROD", "year": 2026, "month": 6,
                   "forecast_qty": 200}]).to_sql(
        "fact_monthly_forecast", engine, if_exists="replace", index=False)


def test_end_to_end_pipeline(tmp_path):
    db = tmp_path / "sca.db"
    engine = make_engine(f"sqlite:///{db}")
    create_all(engine)
    _seed(engine)

    results = run_analytics(engine, _config(f"sqlite:///{db}"),
                            today=date(2026, 6, 1))

    # ROD is the only decoupling-point item; it should be in the coverage table.
    cov = results["coverage"]
    assert list(cov["item_id"]) == ["ROD"]

    # The KIT order ETA should be driven by ROD's lead time (only 30 on hand,
    # need 10) -> material in 4 weeks.
    orders = results["order_etas"]
    assert orders.iloc[0]["so_id"] == "SO1"
    assert orders.iloc[0]["committed_ship"] > date(2026, 6, 1)

    # Disaggregated weekly demand was persisted.
    weekly = pd.read_sql_table("fact_demand_weekly", engine)
    assert not weekly.empty
