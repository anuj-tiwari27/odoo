"""Daily exception list: shortages, late POs, at-risk same-day orders.

Consumes the coverage table, the open-PO fact, and the line/order ETAs and
emits a compact, human-readable digest plus a structured dict for downstream
alerting.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


def build_exceptions(coverage: pd.DataFrame, open_po: pd.DataFrame,
                     order_etas: pd.DataFrame, today: date) -> dict[str, pd.DataFrame]:
    """Return the three exception buckets as DataFrames."""
    shortages = coverage[coverage["flag"].isin(["EXPEDITE", "WATCH"])].copy() \
        if not coverage.empty else coverage

    if not open_po.empty:
        po = open_po.copy()
        po["promised_date"] = pd.to_datetime(po["promised_date"]).dt.date
        late_pos = po[po["promised_date"] < today].copy()
    else:
        late_pos = open_po

    at_risk = order_etas[order_etas.get("same_day", False)].copy() \
        if not order_etas.empty else order_etas

    return {"shortages": shortages, "late_pos": late_pos, "at_risk_orders": at_risk}


def render_text(exceptions: dict[str, pd.DataFrame], today: date) -> str:
    """Render the exception buckets as a plain-text daily digest."""
    lines = [f"DAILY EXCEPTION LIST — As of {today:%a %Y-%m-%d}", "=" * 48]

    shortages = exceptions["shortages"]
    lines.append(f"\nSHORTAGES / AT-RISK COVERAGE ({len(shortages)})")
    if shortages.empty:
        lines.append("  (none)")
    else:
        for r in shortages.itertuples(index=False):
            lines.append(
                f"  {r.item_id:<18} gap={r.coverage_gap:>8.0f}  "
                f"WoS={r.weeks_of_supply}  [{r.flag}]"
            )

    late = exceptions["late_pos"]
    lines.append(f"\nLATE PURCHASE ORDERS ({len(late)})")
    if late.empty:
        lines.append("  (none)")
    else:
        for r in late.itertuples(index=False):
            lines.append(
                f"  PO {r.po_id:<12} {r.item_id:<18} promised {r.promised_date}"
            )

    at_risk = exceptions["at_risk_orders"]
    lines.append(f"\nSAME-DAY / AT-RISK ORDERS ({len(at_risk)})")
    if at_risk.empty:
        lines.append("  (none)")
    else:
        for r in at_risk.itertuples(index=False):
            lines.append(f"  SO {r.so_id:<10} {r.customer}  ship {r.committed_ship}")

    return "\n".join(lines)
