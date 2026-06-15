"""Monthly -> ISO-weekly forecast disaggregation.

The monthly forecast (one row per item/month) is spread across the ISO weeks
that overlap the month, weighted by a configurable week-of-month profile, then
reconciled so the weekly quantities sum back to the monthly total exactly
(largest-remainder rounding, no leakage).

A week is attributed to a month by the share of its days that fall inside the
month; the week-of-month weight is taken from the position of the week's
*first in-month day* within the month.  Quantities are kept as floats unless
``round_to_int`` is set, in which case largest-remainder rounding guarantees
the integer weekly buckets still sum to the (rounded) monthly total.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd


def _weeks_overlapping_month(year: int, month: int) -> list[tuple[int, int, int]]:
    """Return ``(iso_year, iso_week, in_month_days)`` for weeks touching a month."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    counts: dict[tuple[int, int], int] = {}
    day = first
    while day <= last:
        iso_year, iso_week, _ = day.isocalendar()
        counts[(iso_year, iso_week)] = counts.get((iso_year, iso_week), 0) + 1
        day += timedelta(days=1)
    return [(iy, iw, n) for (iy, iw), n in sorted(counts.items())]


def _largest_remainder_round(values: list[float], target: int) -> list[int]:
    """Round ``values`` to ints summing to ``target`` (largest-remainder)."""
    floors = [int(v // 1) for v in values]
    remainder = target - sum(floors)
    if remainder <= 0:
        return floors
    # Hand out the leftover units to the largest fractional parts.
    fracs = sorted(range(len(values)), key=lambda i: values[i] - floors[i], reverse=True)
    for i in fracs[:remainder]:
        floors[i] += 1
    return floors


def disaggregate_month(item_id: str, year: int, month: int, monthly_qty: float,
                       week_of_month_weights: list[float],
                       round_to_int: bool = False) -> pd.DataFrame:
    """Spread one item-month total across its ISO weeks.

    Returns a DataFrame with ``item_id, year, iso_week, forecast_qty`` whose
    ``forecast_qty`` sums to ``monthly_qty`` (or its rounded value).
    """
    weeks = _weeks_overlapping_month(year, month)
    if not weeks:
        return pd.DataFrame(columns=["item_id", "year", "iso_week", "forecast_qty"])

    # Weight = week-of-month profile weight * fraction of the week inside month.
    raw_weights: list[float] = []
    for pos, (_iy, _iw, in_month_days) in enumerate(weeks):
        wom = week_of_month_weights[min(pos, len(week_of_month_weights) - 1)]
        raw_weights.append(wom * in_month_days)

    total_w = sum(raw_weights) or 1.0
    qtys = [monthly_qty * w / total_w for w in raw_weights]

    if round_to_int:
        qtys = [float(x) for x in _largest_remainder_round(qtys, round(monthly_qty))]

    return pd.DataFrame(
        {
            "item_id": item_id,
            "year": [iy for iy, _iw, _n in weeks],
            "iso_week": [iw for _iy, iw, _n in weeks],
            "forecast_qty": qtys,
        }
    )


def disaggregate_monthly_forecast(monthly: pd.DataFrame,
                                  week_of_month_weights: list[float],
                                  round_to_int: bool = False) -> pd.DataFrame:
    """Disaggregate a monthly forecast table to ISO-weekly buckets.

    ``monthly`` must have columns ``item_id, year, month, forecast_qty``.
    Weeks shared by two months accumulate contributions from both, so the
    output is grouped/summed by ``item_id, year, iso_week``.
    """
    required = {"item_id", "year", "month", "forecast_qty"}
    missing = required - set(monthly.columns)
    if missing:
        raise ValueError(f"monthly forecast missing columns: {sorted(missing)}")

    parts = [
        disaggregate_month(
            row.item_id, int(row.year), int(row.month), float(row.forecast_qty),
            week_of_month_weights, round_to_int=round_to_int,
        )
        for row in monthly.itertuples(index=False)
    ]
    if not parts:
        return pd.DataFrame(columns=["item_id", "year", "iso_week", "forecast_qty"])

    out = pd.concat(parts, ignore_index=True)
    return (
        out.groupby(["item_id", "year", "iso_week"], as_index=False)["forecast_qty"]
        .sum()
        .sort_values(["item_id", "year", "iso_week"])
        .reset_index(drop=True)
    )
