# Supply-Chain Coverage & CTP-ETA Pipeline

A standalone Python pipeline that pulls **Acumatica Generic Inquiries** over
OData, loads them into a **SQL star schema** (SQLite for dev, Postgres for
prod), and computes:

1. **Component coverage / exposure** for decoupling-point items — on-hand +
   near-term open POs vs the next N weeks of demand (max of forecast and firm
   orders), sorted most-exposed first and flagged against safety stock.
2. **Capable-to-promise (CTP) ETAs** for open sales-order lines — explode the
   BOM, date each component's availability (on-hand → today, else earliest
   covering PO, else today + lead time), add assembly + pack/ship time, and
   roll the lines up to an order-level committed ship date.
3. A daily **exception list**: shortages, late POs, and at-risk same-day orders.

> **Scope.** This is the *core-first* slice of the original spec: ingest →
> load → coverage → ETA → exceptions. Acumatica write-back of the committed
> date and the Power BI refreshable dataset are intentionally **out of scope**
> here and left for a later iteration. The result tables are persisted to SQL,
> so a BI tool can already point at `fact_demand_weekly`, the coverage output,
> etc.

## Architecture

```
Acumatica GIs (OData)  ->  ETL (pandas)  ->  SQL star schema  ->  analytics
  OpenPOs, SalesOrders,                       dim_item/vendor/      coverage
  InventoryOnHand, BOM,                       calendar; facts:      + CTP-ETA
  POReceipts, Shipments,                      onhand, open_po,      + exceptions
  MonthlyForecast                             demand_weekly, ...
```

Compute modules (`forecast`, `coverage`, `eta`) are **pure pandas** and unit
tested; SQL I/O is isolated in `pipeline.py` and `etl.py`.

## Install

```bash
cd supply_chain_analytics
pip install -r requirements.txt
cp config.example.yaml config.yaml      # then edit
export ACUMATICA_USER=...                # secrets via env vars, never in YAML
export ACUMATICA_PASSWORD=...
```

## Usage

```bash
python -m sca.cli -c config.yaml init-db    # create the schema
python -m sca.cli -c config.yaml etl        # pull GIs -> warehouse
python -m sca.cli -c config.yaml analyze    # coverage + ETAs + exceptions
python -m sca.cli -c config.yaml run        # etl + analyze (daily job)
```

`analyze` accepts `--today YYYY-MM-DD` for what-if / backtest runs.

Schedule the daily job with `scripts/run_daily.sh` (cron / Task Scheduler).

## Configuration

- **`database_url`** — `sqlite:///sca.db` (dev) or
  `postgresql+psycopg2://...` (prod).
- **`acumatica.inquiries`** — map each logical feed to its GI (OData entity)
  name. Tick *Expose via OData* on each GI.
- **`field_maps`** — map GI field names to schema columns (deployment-specific).
- **`seasonality.week_of_month_weights`** — profile used to disaggregate the
  monthly forecast into ISO-weekly buckets (reconciled to the monthly total).
- **`planning`** — coverage horizon and per-item fallbacks (`lead_time_wks`,
  `safety_stock`, `assembly_days`, `pack_ship_days`). Per-item values in
  `dim_item` always win; these are only used when a field is null.

## Per-item parameters

`safety_stock`, `lead_time_wks`, `assembly_days`, and `pack_ship_days` are
columns on `dim_item`, so planners tune them per SKU. Set the
`decoupling_flag` on items that should appear in the coverage/exposure table.

## Tests

```bash
pytest -q                # from the supply_chain_analytics/ directory
```

Covers forecast reconciliation, coverage flags/sorting, multi-level BOM
explosion and ETA logic, OData pagination + field mapping (mocked JSON), and an
end-to-end SQLite run.

## Module map

| Module | Responsibility |
| --- | --- |
| `config.py` | YAML + env-var config, credential resolution |
| `odata_client.py` | Acumatica OData client (pagination, retry, incremental) |
| `schema.py` | SQLAlchemy star schema, engine factory |
| `etl.py` | field mapping + load feeds into SQL |
| `forecast.py` | monthly → ISO-weekly disaggregation |
| `coverage.py` | component coverage / exposure table |
| `eta.py` | BOM explosion + CTP order ETA |
| `exceptions_report.py` | daily exception digest |
| `pipeline.py` | SQL read/orchestration |
| `cli.py` | command-line entry point |

## Not yet implemented (next iteration)

- Write the committed ship date back to Acumatica via the contract-based REST
  API (`PUT SalesOrder`).
- A dedicated Power BI refreshable dataset / incremental-refresh wiring.
- Supplier OTD / lead-time variability and forecast MAPE/bias as first-class
  outputs (the SQL for these is in the spec and the facts are already loaded).
```
