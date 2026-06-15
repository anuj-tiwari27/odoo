"""Tiny stdlib web dashboard for the coverage / ETA / exception outputs.

No web framework dependency: a single ``http.server`` handler renders the
analytics result tables as HTML at ``/`` and serves the same data as JSON at
``/api/data``.  Intended for local use.

Run it::

    python -m sca.web --demo                 # seeded demo data, no Acumatica
    python -m sca.web -c config.yaml         # your configured warehouse

then open the printed http://127.0.0.1:8000 link.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape

import pandas as pd

from .config import Config, AcumaticaConfig, PlanningConfig, SeasonalityConfig
from .demo import DEMO_TODAY, seed_demo
from .pipeline import run_analytics
from .schema import make_engine

_FLAG_COLORS = {"EXPEDITE": "#e5484d", "WATCH": "#f5a623", "OK": "#30a46c"}


def _df_to_html(df: pd.DataFrame, flag_col: str | None = None) -> str:
    if df is None or df.empty:
        return '<p class="empty">— none —</p>'
    cols = list(df.columns)
    head = "".join(f"<th>{escape(str(c))}</th>" for c in cols)
    rows = []
    for rec in df.to_dict("records"):
        cells = []
        for c in cols:
            val = rec[c]
            text = "" if val is None or (isinstance(val, float) and pd.isna(val)) else str(val)
            if c == flag_col and text in _FLAG_COLORS:
                cells.append(
                    f'<td><span class="badge" style="background:{_FLAG_COLORS[text]}">'
                    f"{escape(text)}</span></td>"
                )
            else:
                cells.append(f"<td>{escape(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_page(results: dict[str, pd.DataFrame], as_of: date) -> str:
    coverage = results.get("coverage", pd.DataFrame())
    orders = results.get("order_etas", pd.DataFrame())
    lines = results.get("line_etas", pd.DataFrame())
    shortages = results.get("exc_shortages", pd.DataFrame())
    late_pos = results.get("exc_late_pos", pd.DataFrame())
    at_risk = results.get("exc_at_risk_orders", pd.DataFrame())

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supply-Chain Coverage & CTP-ETA</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
          background: #f6f7f9; color: #1c2024; }}
  header {{ background: #11181c; color: #fff; padding: 18px 28px; }}
  header h1 {{ margin: 0; font-size: 18px; }}
  header .sub {{ color: #9ba1a6; font-size: 13px; margin-top: 4px; }}
  main {{ padding: 24px 28px; max-width: 1100px; }}
  section {{ background: #fff; border: 1px solid #e6e8eb; border-radius: 10px;
            padding: 16px 20px; margin-bottom: 22px; }}
  h2 {{ font-size: 15px; margin: 0 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid #eceef0; }}
  th {{ color: #687076; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
  tbody tr:hover {{ background: #f8f9fa; }}
  .badge {{ color: #fff; padding: 2px 8px; border-radius: 999px; font-size: 11px;
            font-weight: 600; }}
  .empty {{ color: #889096; font-style: italic; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style></head>
<body>
<header>
  <h1>Supply-Chain Coverage &amp; CTP-ETA</h1>
  <div class="sub">As of {as_of:%a %Y-%m-%d} &middot; <a style="color:#7cc4fa" href="/api/data">JSON</a></div>
</header>
<main>
  <section><h2>Component coverage — decoupling-point items</h2>
    {_df_to_html(coverage, flag_col="flag")}</section>
  <section><h2>Order ETAs (committed ship)</h2>
    {_df_to_html(orders)}</section>
  <section><h2>Order line ETAs</h2>
    {_df_to_html(lines)}</section>
  <div class="grid">
    <section><h2>Shortages / at-risk coverage</h2>{_df_to_html(shortages, flag_col="flag")}</section>
    <section><h2>Late purchase orders</h2>{_df_to_html(late_pos)}</section>
  </div>
  <section><h2>Same-day / at-risk orders</h2>{_df_to_html(at_risk)}</section>
</main>
</body></html>"""


def _json_safe(results: dict[str, pd.DataFrame]) -> dict:
    out = {}
    for key, df in results.items():
        if isinstance(df, pd.DataFrame):
            out[key] = json.loads(df.to_json(orient="records", date_format="iso"))
    return out


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, config: Config, today: date, **kwargs):
        self._config = config
        self._today = today
        super().__init__(*args, **kwargs)

    def log_message(self, *_args):  # quiet console
        pass

    def _compute(self):
        engine = make_engine(self._config.database_url)
        return run_analytics(engine, self._config, today=self._today)

    def do_GET(self):
        try:
            results = self._compute()
        except Exception as exc:  # surface errors in the browser
            self._send(500, "text/plain", f"Error computing analytics: {exc}")
            return

        if self.path.startswith("/api/data"):
            body = json.dumps(_json_safe(results), indent=2)
            self._send(200, "application/json", body)
        elif self.path in ("/", "/index.html"):
            self._send(200, "text/html", render_page(results, self._today))
        else:
            self._send(404, "text/plain", "Not found")

    def _send(self, code: int, content_type: str, body: str):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _demo_config(db_url: str) -> Config:
    return Config(
        database_url=db_url,
        acumatica=AcumaticaConfig(base_url="", company="", username="", password=""),
        seasonality=SeasonalityConfig(week_of_month_weights=[1, 1, 1, 1, 1]),
        planning=PlanningConfig(coverage_horizon_weeks=5),
    )


def serve(config: Config, host: str, port: int, today: date) -> None:
    handler = partial(_Handler, config=config, today=today)
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"Supply-chain dashboard running at {url}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.server_close()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Local supply-chain analytics dashboard")
    p.add_argument("-c", "--config", help="path to config YAML")
    p.add_argument("--demo", action="store_true",
                   help="seed a self-contained demo dataset (no Acumatica)")
    p.add_argument("--db", default="sqlite_demo.db",
                   help="sqlite file for --demo (default: ./sqlite_demo.db)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--today", help="override 'as of' date (ISO)")
    args = p.parse_args(argv)

    if args.demo:
        db_url = f"sqlite:///{args.db}"
        config = _demo_config(db_url)
        seed_demo(make_engine(db_url))
        today = date.fromisoformat(args.today) if args.today else DEMO_TODAY
    elif args.config:
        config = Config.load(args.config)
        today = date.fromisoformat(args.today) if args.today else date.today()
    else:
        p.error("provide --demo or -c/--config")
        return

    serve(config, args.host, args.port, today)


if __name__ == "__main__":
    main()
