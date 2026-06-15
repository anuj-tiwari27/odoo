"""Component coverage / exposure for decoupling-point items.

For every item flagged as a decoupling point we compare available supply
against near-term demand:

    total_supply = on_hand + open POs promised within the coverage horizon
    demand       = sum over the next N weeks of max(forecast, firm orders)
    coverage_gap = total_supply - demand
    weeks_of_supply = total_supply / (demand / N)

Items are sorted most-exposed first and flagged when the gap drops below the
item's safety stock.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def _iso_week_range(today: date, horizon_weeks: int) -> list[tuple[int, int]]:
    """Return ``(year, iso_week)`` for the current week and the next N-1."""
    weeks = []
    cursor = today
    for _ in range(horizon_weeks):
        iy, iw, _ = cursor.isocalendar()
        weeks.append((iy, iw))
        cursor += timedelta(weeks=1)
    return weeks


def compute_coverage(items: pd.DataFrame, onhand: pd.DataFrame,
                     open_po: pd.DataFrame, demand_weekly: pd.DataFrame,
                     today: date, horizon_weeks: int = 5,
                     default_lead_time_wks: float = 4.0,
                     default_safety_stock: float = 0.0) -> pd.DataFrame:
    """Build the coverage/exposure table for decoupling-point items.

    Parameters mirror the star-schema facts.  ``open_po`` is filtered to POs
    promised within ``min(horizon, lead_time)`` weeks of ``today`` per item.
    """
    dp = items[items["decoupling_flag"].fillna(False).astype(bool)].copy()
    if dp.empty:
        return pd.DataFrame(
            columns=["item_id", "on_hand", "open_po", "demand", "coverage_gap",
                     "weeks_of_supply", "safety_stock", "flag"]
        )

    dp["lead_time_wks"] = dp["lead_time_wks"].fillna(default_lead_time_wks)
    dp["safety_stock"] = dp["safety_stock"].fillna(default_safety_stock)

    # On-hand (net of allocation) per item.
    oh = onhand.copy()
    oh["net_onhand"] = oh["qty_onhand"].fillna(0) - oh.get("qty_allocated", 0)
    oh_by_item = oh.groupby("item_id")["net_onhand"].sum()

    # Demand: next N ISO weeks, max(forecast, firm) per week then summed.
    wk = _iso_week_range(today, horizon_weeks)
    wanted = pd.DataFrame(wk, columns=["year", "iso_week"])
    dw = demand_weekly.merge(wanted, on=["year", "iso_week"], how="inner").copy()
    dw["req"] = dw[["forecast_qty", "firm_order_qty"]].fillna(0).max(axis=1)
    demand_by_item = dw.groupby("item_id")["req"].sum()

    rows = []
    for it in dp.itertuples(index=False):
        horizon_days = min(horizon_weeks, float(it.lead_time_wks)) * 7
        cutoff = today + timedelta(days=horizon_days)
        po = open_po[(open_po["item_id"] == it.item_id)
                     & (pd.to_datetime(open_po["promised_date"]).dt.date <= cutoff)]
        po_qty = float(pd.to_numeric(po["qty_ordered"], errors="coerce").fillna(0).sum())

        on_hand = float(oh_by_item.get(it.item_id, 0.0))
        demand = float(demand_by_item.get(it.item_id, 0.0))
        total_supply = on_hand + po_qty
        gap = total_supply - demand
        wos = (total_supply / (demand / horizon_weeks)) if demand > 0 else float("inf")

        if gap < 0:
            flag = "EXPEDITE"
        elif gap < float(it.safety_stock):
            flag = "WATCH"
        else:
            flag = "OK"

        rows.append({
            "item_id": it.item_id,
            "on_hand": on_hand,
            "open_po": po_qty,
            "demand": demand,
            "coverage_gap": gap,
            "weeks_of_supply": round(wos, 1) if wos != float("inf") else None,
            "safety_stock": float(it.safety_stock),
            "flag": flag,
        })

    out = pd.DataFrame(rows)
    return out.sort_values("coverage_gap").reset_index(drop=True)
