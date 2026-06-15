"""Command-line entry point.

Subcommands:
  init-db    create the SQL star schema
  etl        pull Acumatica GIs and load the warehouse
  analyze    run coverage + ETA + exceptions, print the digest
  run        etl + analyze (the scheduled daily job)
"""

from __future__ import annotations

import argparse
from datetime import date

from .config import Config
from .exceptions_report import render_text
from .odata_client import AcumaticaODataClient
from .pipeline import run_analytics
from .schema import create_all, make_engine


def _engine(config: Config):
    return make_engine(config.database_url)


def cmd_init_db(config: Config, _args) -> None:
    engine = _engine(config)
    create_all(engine)
    print(f"Schema created at {config.database_url}")


def cmd_etl(config: Config, _args) -> None:
    from .etl import run_etl

    engine = _engine(config)
    client = AcumaticaODataClient(config.acumatica)
    loaded = run_etl(config, client, engine)
    for table, n in loaded.items():
        print(f"  loaded {n:>7} rows -> {table}")


def cmd_analyze(config: Config, args) -> None:
    engine = _engine(config)
    today = date.fromisoformat(args.today) if args.today else date.today()
    results = run_analytics(engine, config, today=today)

    cov = results["coverage"]
    if not cov.empty:
        print("\nCOMPONENT COVERAGE — DECOUPLING-POINT ITEMS")
        print(cov.to_string(index=False))

    orders = results["order_etas"]
    if not orders.empty:
        print("\nORDER ETAs")
        print(orders.to_string(index=False))

    exceptions = {
        "shortages": results["exc_shortages"],
        "late_pos": results["exc_late_pos"],
        "at_risk_orders": results["exc_at_risk_orders"],
    }
    print("\n" + render_text(exceptions, today))


def cmd_run(config: Config, args) -> None:
    cmd_etl(config, args)
    cmd_analyze(config, args)


def cmd_serve(config: Config, args) -> None:
    from datetime import date as _date

    from .web import serve

    today = _date.fromisoformat(args.today) if args.today else _date.today()
    serve(config, args.host, args.port, today)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sca", description=__doc__)
    p.add_argument("-c", "--config", default="config.yaml", help="path to config YAML")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    sub.add_parser("etl").set_defaults(func=cmd_etl)

    a = sub.add_parser("analyze")
    a.add_argument("--today", help="override 'today' (ISO date) for what-if runs")
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("run")
    r.add_argument("--today", help="override 'today' (ISO date)")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("serve", help="local web dashboard for the results")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--today", help="override 'as of' date (ISO)")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = Config.load(args.config)
    args.func(config, args)


if __name__ == "__main__":
    main()
