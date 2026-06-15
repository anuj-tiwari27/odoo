"""Capable-to-promise (CTP) ETA for open sales-order lines.

For each open sales-order line we explode the BOM to its purchased leaf
components and date each component's availability:

    on-hand covers the requirement  -> available today
    else an open PO exists          -> earliest promised date that covers it
    else                            -> today + item lead time

The line's material-availability date is the latest component date; the line
ETA adds assembly and pack/ship time.  The order's committed ship date is the
latest line ETA (a complete-kit ships together).

This is CTP layered on ATP: it vets material availability per component rather
than trusting a single static lead time, so a kitted manufacturer stops
over-promising.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def explode_bom(item_id: str, qty: float, bom: pd.DataFrame,
                _seen: frozenset[str] | None = None) -> dict[str, float]:
    """Recursively explode an item to purchased leaf components.

    Returns ``{leaf_item_id: total_qty}``.  A leaf is any item that never
    appears as a ``parent_item_id``.  Cycles are broken defensively.
    """
    _seen = _seen or frozenset()
    children = bom[bom["parent_item_id"] == item_id]
    if children.empty or item_id in _seen:
        return {item_id: qty}

    leaves: dict[str, float] = {}
    for child in children.itertuples(index=False):
        sub = explode_bom(
            child.component_item_id,
            qty * float(child.qty_per),
            bom,
            _seen | {item_id},
        )
        for leaf, q in sub.items():
            leaves[leaf] = leaves.get(leaf, 0.0) + q
    return leaves


def _component_available_date(item_id: str, required_qty: float, today: date,
                              onhand_by_item: dict[str, float],
                              po_by_item: dict[str, list[tuple[date, float]]],
                              lead_time_by_item: dict[str, float],
                              default_lead_time_wks: float) -> date:
    """Earliest date the required quantity of one component can be covered."""
    if onhand_by_item.get(item_id, 0.0) >= required_qty:
        return today

    # Accumulate on-hand + open POs (earliest first) until the requirement is met.
    running = onhand_by_item.get(item_id, 0.0)
    for promised, qty in sorted(po_by_item.get(item_id, [])):
        running += qty
        if running >= required_qty:
            return max(promised, today)

    lead = lead_time_by_item.get(item_id, default_lead_time_wks)
    return today + timedelta(weeks=lead)


def compute_order_etas(so_lines: pd.DataFrame, bom: pd.DataFrame,
                       onhand: pd.DataFrame, open_po: pd.DataFrame,
                       items: pd.DataFrame, today: date,
                       default_lead_time_wks: float = 4.0,
                       default_assembly_days: float = 0.5,
                       default_pack_ship_days: float = 0.5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute per-line and per-order committed ship dates.

    Returns ``(line_etas, order_etas)``.  ``line_etas`` has one row per
    sales-order line with the constraining component and dates; ``order_etas``
    rolls lines up to the latest (complete-kit) ship date per order.
    """
    onhand_by_item = (
        onhand.assign(net=onhand["qty_onhand"].fillna(0) - onhand.get("qty_allocated", 0))
        .groupby("item_id")["net"].sum().to_dict()
    )

    po_by_item: dict[str, list[tuple[date, float]]] = {}
    for po in open_po.itertuples(index=False):
        promised = pd.to_datetime(po.promised_date).date()
        po_by_item.setdefault(po.item_id, []).append((promised, float(po.qty_ordered)))

    idx = items.set_index("item_id")
    lead_by_item = idx["lead_time_wks"].fillna(default_lead_time_wks).to_dict()
    assembly_by_item = idx.get("assembly_days", pd.Series(dtype=float)).to_dict()
    packship_by_item = idx.get("pack_ship_days", pd.Series(dtype=float)).to_dict()

    line_rows = []
    for line in so_lines.itertuples(index=False):
        leaves = explode_bom(line.item_id, float(line.qty), bom)

        constraint_item, constraint_date = None, today
        for leaf, req_qty in leaves.items():
            avail = _component_available_date(
                leaf, req_qty, today, onhand_by_item, po_by_item,
                lead_by_item, default_lead_time_wks,
            )
            if avail > constraint_date or constraint_item is None:
                constraint_date, constraint_item = avail, leaf

        assembly = float(assembly_by_item.get(line.item_id, default_assembly_days) or default_assembly_days)
        pack_ship = float(packship_by_item.get(line.item_id, default_pack_ship_days) or default_pack_ship_days)
        # Build/pack/ship time is in days and may be fractional; round up to days.
        added_days = int(-(-(assembly + pack_ship) // 1))  # ceil
        line_eta = constraint_date + timedelta(days=added_days)

        line_rows.append({
            "so_id": line.so_id,
            "line_id": line.line_id,
            "customer": getattr(line, "customer", None),
            "item_id": line.item_id,
            "qty": float(line.qty),
            "material_available": constraint_date,
            "constraint_item": constraint_item,
            "assembly_days": assembly,
            "pack_ship_days": pack_ship,
            "line_eta": line_eta,
            "same_day": line_eta == today,
        })

    line_etas = pd.DataFrame(line_rows)
    if line_etas.empty:
        return line_etas, pd.DataFrame(columns=["so_id", "customer", "committed_ship", "same_day"])

    order_etas = (
        line_etas.groupby("so_id")
        .agg(customer=("customer", "first"), committed_ship=("line_eta", "max"))
        .reset_index()
    )
    order_etas["same_day"] = order_etas["committed_ship"] == today
    return line_etas, order_etas
