from datetime import date

import pandas as pd

from sca.coverage import compute_coverage


def _items():
    return pd.DataFrame([
        {"item_id": "EXTR-PANEL", "lead_time_wks": 5, "safety_stock": 50,
         "decoupling_flag": True},
        {"item_id": "EXTR-RAIL", "lead_time_wks": 5, "safety_stock": 50,
         "decoupling_flag": True},
        {"item_id": "NON-DP", "lead_time_wks": 2, "safety_stock": 0,
         "decoupling_flag": False},
    ])


def _demand(today):
    iy, iw, _ = today.isocalendar()
    rows = []
    for offset in range(5):
        wk = iw + offset
        for item, fc in [("EXTR-PANEL", 51), ("EXTR-RAIL", 40)]:
            rows.append({"item_id": item, "year": iy, "iso_week": wk,
                         "forecast_qty": fc, "firm_order_qty": 0})
    return pd.DataFrame(rows)


def test_coverage_flags_and_sorting():
    today = date(2026, 6, 1)
    onhand = pd.DataFrame([
        {"item_id": "EXTR-PANEL", "qty_onhand": 180, "qty_allocated": 0},
        {"item_id": "EXTR-RAIL", "qty_onhand": 240, "qty_allocated": 0},
    ])
    open_po = pd.DataFrame([
        {"item_id": "EXTR-RAIL", "qty_ordered": 200,
         "promised_date": date(2026, 6, 10)},
    ])
    cov = compute_coverage(_items(), onhand, open_po, _demand(today), today,
                           horizon_weeks=5)

    # Only decoupling-point items appear.
    assert set(cov["item_id"]) == {"EXTR-PANEL", "EXTR-RAIL"}
    # Sorted most-exposed (smallest gap) first.
    assert cov["coverage_gap"].is_monotonic_increasing

    panel = cov[cov.item_id == "EXTR-PANEL"].iloc[0]
    # demand = 51*5 = 255, supply 180 -> gap -75 -> EXPEDITE
    assert panel["coverage_gap"] == -75
    assert panel["flag"] == "EXPEDITE"

    rail = cov[cov.item_id == "EXTR-RAIL"].iloc[0]
    # demand 200, supply 240+200=440 -> gap 240 -> OK
    assert rail["flag"] == "OK"


def test_po_outside_horizon_excluded():
    today = date(2026, 6, 1)
    onhand = pd.DataFrame([{"item_id": "EXTR-PANEL", "qty_onhand": 180,
                            "qty_allocated": 0}])
    # Promised far beyond the 5-week horizon -> ignored.
    open_po = pd.DataFrame([{"item_id": "EXTR-PANEL", "qty_ordered": 500,
                             "promised_date": date(2026, 9, 1)}])
    items = _items()[_items().item_id == "EXTR-PANEL"]
    cov = compute_coverage(items, onhand, open_po, _demand(today), today,
                           horizon_weeks=5)
    assert cov.iloc[0]["open_po"] == 0
