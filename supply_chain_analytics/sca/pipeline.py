"""Orchestration: read the warehouse, run analytics, return result tables.

Keeps SQL I/O in one place so the compute modules (``forecast``, ``coverage``,
``eta``) stay pure and unit-testable on plain DataFrames.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.engine import Engine

from .config import Config
from . import coverage as coverage_mod
from . import eta as eta_mod
from . import exceptions_report
from .forecast import disaggregate_monthly_forecast


def _read(engine: Engine, table: str) -> pd.DataFrame:
    try:
        return pd.read_sql_table(table, engine)
    except ValueError:
        # Table not present yet.
        return pd.DataFrame()


def build_weekly_demand(engine: Engine, config: Config) -> pd.DataFrame:
    """Disaggregate the monthly forecast and merge firm sales-order demand.

    Reads ``fact_monthly_forecast`` (item_id, year, month, forecast_qty) and
    the open sales-order lines, returning the ``fact_demand_weekly`` shape.
    """
    monthly = _read(engine, "fact_monthly_forecast")
    if monthly.empty:
        weekly = pd.DataFrame(columns=["item_id", "year", "iso_week", "forecast_qty"])
    else:
        weekly = disaggregate_monthly_forecast(
            monthly, config.seasonality.week_of_month_weights
        )

    # Firm demand from open SO lines, bucketed to the request-date ISO week.
    so = _read(engine, "fact_sales_order_line")
    if not so.empty and "request_date" in so.columns:
        so = so.copy()
        rd = pd.to_datetime(so["request_date"])
        iso = rd.dt.isocalendar()
        so["year"] = iso["year"].astype(int)
        so["iso_week"] = iso["week"].astype(int)
        firm = so.groupby(["item_id", "year", "iso_week"], as_index=False)["qty"].sum()
        firm = firm.rename(columns={"qty": "firm_order_qty"})
    else:
        firm = pd.DataFrame(columns=["item_id", "year", "iso_week", "firm_order_qty"])

    weekly = weekly.merge(firm, on=["item_id", "year", "iso_week"], how="outer")
    weekly["forecast_qty"] = weekly["forecast_qty"].fillna(0)
    weekly["firm_order_qty"] = weekly["firm_order_qty"].fillna(0)
    weekly["warehouse"] = None
    return weekly


def run_analytics(engine: Engine, config: Config,
                  today: date | None = None) -> dict[str, pd.DataFrame]:
    """Run coverage + ETA + exceptions and return all result tables."""
    today = today or date.today()
    items = _read(engine, "dim_item")
    onhand = _read(engine, "fact_onhand")
    open_po = _read(engine, "fact_open_po")
    bom = _read(engine, "fact_bom")
    so_lines = _read(engine, "fact_sales_order_line")

    demand_weekly = build_weekly_demand(engine, config)
    # Persist the disaggregated demand so Power BI / queries can read it.
    if not demand_weekly.empty:
        demand_weekly.to_sql("fact_demand_weekly", engine, if_exists="replace", index=False)

    coverage = coverage_mod.compute_coverage(
        items, onhand, open_po, demand_weekly, today,
        horizon_weeks=config.planning.coverage_horizon_weeks,
        default_lead_time_wks=config.planning.default_lead_time_wks,
        default_safety_stock=config.planning.default_safety_stock,
    ) if not items.empty else pd.DataFrame()

    if not so_lines.empty:
        line_etas, order_etas = eta_mod.compute_order_etas(
            so_lines, bom, onhand, open_po, items, today,
            default_lead_time_wks=config.planning.default_lead_time_wks,
            default_assembly_days=config.planning.default_assembly_days,
            default_pack_ship_days=config.planning.default_pack_ship_days,
        )
    else:
        line_etas, order_etas = pd.DataFrame(), pd.DataFrame()

    exceptions = exceptions_report.build_exceptions(
        coverage if not coverage.empty else pd.DataFrame(
            columns=["item_id", "coverage_gap", "weeks_of_supply", "flag"]),
        open_po, order_etas, today,
    )

    return {
        "coverage": coverage,
        "demand_weekly": demand_weekly,
        "line_etas": line_etas,
        "order_etas": order_etas,
        **{f"exc_{k}": v for k, v in exceptions.items()},
    }
