from datetime import date, timedelta

import pandas as pd

from sca.eta import compute_order_etas, explode_bom


def test_explode_bom_multilevel():
    bom = pd.DataFrame([
        {"parent_item_id": "KIT", "component_item_id": "SUB", "qty_per": 2},
        {"parent_item_id": "KIT", "component_item_id": "SEAL", "qty_per": 4},
        {"parent_item_id": "SUB", "component_item_id": "ROD", "qty_per": 3},
    ])
    leaves = explode_bom("KIT", 10, bom)
    # SUB explodes to ROD: 10 * 2 * 3 = 60; SEAL: 10 * 4 = 40.
    assert leaves == {"ROD": 60, "SEAL": 40}


def _items():
    return pd.DataFrame([
        {"item_id": "KIT", "lead_time_wks": 0, "assembly_days": 0.5,
         "pack_ship_days": 0.5},
        {"item_id": "ROD", "lead_time_wks": 4, "assembly_days": 0,
         "pack_ship_days": 0},
        {"item_id": "SEAL", "lead_time_wks": 2, "assembly_days": 0,
         "pack_ship_days": 0},
    ])


def test_same_day_when_all_on_hand():
    today = date(2026, 6, 1)
    bom = pd.DataFrame([
        {"parent_item_id": "KIT", "component_item_id": "ROD", "qty_per": 1},
        {"parent_item_id": "KIT", "component_item_id": "SEAL", "qty_per": 1},
    ])
    onhand = pd.DataFrame([
        {"item_id": "ROD", "qty_onhand": 100, "qty_allocated": 0},
        {"item_id": "SEAL", "qty_onhand": 100, "qty_allocated": 0},
    ])
    so = pd.DataFrame([{"so_id": "SO1", "line_id": "1", "customer": "Acme",
                        "item_id": "KIT", "qty": 4}])
    lines, orders = compute_order_etas(so, bom, onhand, pd.DataFrame(
        columns=["item_id", "qty_ordered", "promised_date"]), _items(), today)
    # All on hand -> material today; assembly 0.5 + pack 0.5 = 1 day ceil.
    assert orders.iloc[0]["committed_ship"] == today + timedelta(days=1)


def test_constraint_uses_lead_time_when_short():
    today = date(2026, 6, 1)
    bom = pd.DataFrame([
        {"parent_item_id": "KIT", "component_item_id": "ROD", "qty_per": 1},
    ])
    onhand = pd.DataFrame(columns=["item_id", "qty_onhand", "qty_allocated"])
    so = pd.DataFrame([{"so_id": "SO1", "line_id": "1", "customer": "Acme",
                        "item_id": "KIT", "qty": 10}])
    lines, orders = compute_order_etas(so, bom, onhand, pd.DataFrame(
        columns=["item_id", "qty_ordered", "promised_date"]), _items(), today)
    line = lines.iloc[0]
    assert line["constraint_item"] == "ROD"
    # ROD has no stock/PO -> today + 4 wks, + 1 day build.
    assert line["material_available"] == today + timedelta(weeks=4)
    assert orders.iloc[0]["committed_ship"] == today + timedelta(weeks=4, days=1)


def test_open_po_covers_before_lead_time():
    today = date(2026, 6, 1)
    bom = pd.DataFrame([
        {"parent_item_id": "KIT", "component_item_id": "ROD", "qty_per": 1},
    ])
    onhand = pd.DataFrame(columns=["item_id", "qty_onhand", "qty_allocated"])
    open_po = pd.DataFrame([{"item_id": "ROD", "qty_ordered": 10,
                             "promised_date": today + timedelta(days=7)}])
    so = pd.DataFrame([{"so_id": "SO1", "line_id": "1", "customer": "Acme",
                        "item_id": "KIT", "qty": 10}])
    lines, _ = compute_order_etas(so, bom, onhand, open_po, _items(), today)
    # PO arrives in 7 days, earlier than the 4-week lead time.
    assert lines.iloc[0]["material_available"] == today + timedelta(days=7)
