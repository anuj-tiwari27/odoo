import pandas as pd

from sca.forecast import disaggregate_month, disaggregate_monthly_forecast


def test_weekly_sums_reconcile_to_monthly_total():
    df = disaggregate_month("ITEM-A", 2026, 6, 1000.0, [1, 1, 1, 1, 1])
    assert round(df["forecast_qty"].sum(), 6) == 1000.0


def test_seasonality_weights_shift_mass():
    flat = disaggregate_month("X", 2026, 6, 100.0, [1, 1, 1, 1, 1])
    front = disaggregate_month("X", 2026, 6, 100.0, [3, 1, 1, 1, 1])
    # Front-loaded profile puts more on the first overlapping week.
    assert front["forecast_qty"].iloc[0] > flat["forecast_qty"].iloc[0]
    assert round(front["forecast_qty"].sum(), 6) == 100.0


def test_integer_rounding_preserves_total():
    df = disaggregate_month("X", 2026, 6, 101.0, [1.0, 1.1, 1.0, 0.9, 0.5],
                            round_to_int=True)
    assert df["forecast_qty"].sum() == 101
    assert (df["forecast_qty"] == df["forecast_qty"].round()).all()


def test_full_table_groups_shared_weeks():
    monthly = pd.DataFrame({
        "item_id": ["A", "A"],
        "year": [2026, 2026],
        "month": [6, 7],
        "forecast_qty": [300.0, 300.0],
    })
    weekly = disaggregate_monthly_forecast(monthly, [1, 1, 1, 1, 1])
    # No duplicate (item, year, week) rows after grouping.
    assert not weekly.duplicated(["item_id", "year", "iso_week"]).any()
    assert round(weekly["forecast_qty"].sum(), 6) == 600.0
