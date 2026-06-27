from beli_tool.config import Config
from beli_tool.cli import build_app_from_config, local_ip


class FakeSource:
    def points(self):
        return []


class FakeClient:
    def text_search(self, query):
        return [{"place_id": "w1", "name": query, "formatted_address": "x", "types": ["restaurant"]}]

    def nearby_food(self, lat, lon, radius_m=60):
        return []


def test_local_ip_returns_string():
    assert isinstance(local_ip(), str)


def test_build_app_from_config_wires_sources(tmp_path):
    (tmp_path / "Want to go.csv").write_text("Title,Note,URL\nDhamaka,,u\n")
    cfg = Config(api_key="k", saved_dir=tmp_path, db_path=tmp_path / "l.sqlite")
    app, ledger = build_app_from_config(cfg, photo_source=FakeSource(), client=FakeClient())
    from fastapi.testclient import TestClient
    data = TestClient(app).get("/api/queue").json()
    assert [i["name"] for i in data["want_to_try"]] == ["Dhamaka"]
