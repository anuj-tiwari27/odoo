import json
from pathlib import Path

from sca.config import AcumaticaConfig
from sca.etl import map_rows
from sca.odata_client import AcumaticaODataClient

FIX = Path(__file__).parent / "fixtures"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    """Serves the two paginated fixture pages by URL."""

    def __init__(self):
        self.auth = None
        self.headers = {}
        self.calls = []
        self._page1 = json.loads((FIX / "odata_open_pos.json").read_text())
        self._page2 = json.loads((FIX / "odata_open_pos_page2.json").read_text())

    def get(self, url, params=None, timeout=None, verify=None):
        self.calls.append(url)
        if "skiptoken" in url:
            return _FakeResponse(self._page2)
        return _FakeResponse(self._page1)


def _config():
    return AcumaticaConfig(base_url="https://site", company="Co",
                           username="u", password="p")


def test_fetch_follows_pagination():
    session = _FakeSession()
    client = AcumaticaODataClient(_config(), session=session)
    rows = client.fetch("GI-OpenPOs")
    assert len(rows) == 3  # 2 from page1 + 1 from page2
    assert session.auth == ("u", "p")
    # nextLink was followed exactly once.
    assert any("skiptoken" in c for c in session.calls)


def test_map_rows_applies_field_map():
    session = _FakeSession()
    client = AcumaticaODataClient(_config(), session=session)
    rows = client.fetch("GI-OpenPOs")
    field_map = {
        "po_id": "OrderNbr", "item_id": "InventoryID", "vendor_id": "VendorID",
        "qty_ordered": "OrderQty", "promised_date": "PromisedOn",
        "warehouse": "Warehouse",
    }
    df = map_rows(rows, field_map)
    assert list(df.columns) == list(field_map.keys())
    assert df.iloc[0]["po_id"] == "PO1001"
