"""Minimal Acumatica OData v4 client for Generic Inquiries.

Acumatica exposes each Generic Inquiry that has "Expose via OData" ticked at
``https://<site>/odata/<Company>/<InquiryName>``.  Responses are standard
OData JSON: the rows live under the ``value`` key and large result sets are
paginated via ``@odata.nextLink``.

The client supports:
  * HTTP basic auth (credentials supplied by :class:`~sca.config.AcumaticaConfig`),
  * transparent ``@odata.nextLink`` pagination,
  * incremental refresh via a ``$filter`` (e.g. by year) to dodge the known
    OData payload bloat on big inquiries such as Shipments, and
  * retry with exponential backoff on transient network errors.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

import requests

from .config import AcumaticaConfig


class ODataError(RuntimeError):
    pass


class AcumaticaODataClient:
    def __init__(self, config: AcumaticaConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()
        self.session.auth = (config.username, config.password)
        self.session.headers.update({"Accept": "application/json"})

    def _request(self, url: str, params: dict[str, Any] | None = None,
                 max_retries: int = 4) -> dict[str, Any]:
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    timeout=self.config.timeout_seconds,
                    verify=self.config.verify_ssl,
                )
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt == max_retries - 1:
                    break
                time.sleep(delay)
                delay *= 2
            except requests.HTTPError as exc:
                raise ODataError(f"OData request to {url} failed: {exc}") from exc
        raise ODataError(f"OData request to {url} failed after retries: {last_exc}")

    def fetch(self, inquiry: str, *, select: Iterable[str] | None = None,
              filter: str | None = None, top: int | None = None,
              extra_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return all rows of a Generic Inquiry, following pagination links.

        ``inquiry`` is the OData entity name (the GI name).  Use ``filter`` for
        incremental pulls, e.g. ``filter="Year eq 2026"``.
        """
        params: dict[str, Any] = {}
        if select:
            params["$select"] = ",".join(select)
        if filter:
            params["$filter"] = filter
        if top is not None:
            params["$top"] = top
        if extra_params:
            params.update(extra_params)

        url = f"{self.config.odata_root}/{inquiry}"
        rows: list[dict[str, Any]] = []
        payload = self._request(url, params=params)
        rows.extend(payload.get("value", []))

        # Follow server-driven paging. nextLink already carries the query string.
        next_link = payload.get("@odata.nextLink")
        while next_link:
            payload = self._request(next_link)
            rows.extend(payload.get("value", []))
            next_link = payload.get("@odata.nextLink")
        return rows

    def fetch_by_year(self, inquiry: str, year_field: str,
                      years: Iterable[int]) -> list[dict[str, Any]]:
        """Incremental refresh helper: union a GI pulled one year at a time."""
        rows: list[dict[str, Any]] = []
        for year in years:
            rows.extend(self.fetch(inquiry, filter=f"{year_field} eq {year}"))
        return rows
