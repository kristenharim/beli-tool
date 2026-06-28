from datetime import date
from fastapi.testclient import TestClient

from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace
from beli_tool.pipeline import Queue
from beli_tool.ledger import Ledger
from beli_tool.webapp import create_app


def _queue():
    been = MatchedPlace(
        bucket="been", status="confident",
        raw=RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12),
                     photo_count=4, photo_ref="uuid-b1"),
        match=PlaceCandidate(place_id="b1", name="Lilia", address="567 Union Ave", category="restaurant"),
    )
    want = MatchedPlace(
        bucket="want_to_try", status="confident",
        raw=RawPlace(source="maps", name="Dhamaka"),
        match=PlaceCandidate(place_id="w1", name="Dhamaka", address="119 Delancey", category="restaurant"),
    )
    return Queue(want_to_try=[want], been=[been])


def test_queue_endpoint_lists_items():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    data = client.get("/api/queue").json()
    assert [i["name"] for i in data["been"]] == ["Lilia"]
    assert data["been"][0]["photo_count"] == 4
    assert data["been"][0]["photo_ref"] == "uuid-b1"
    assert [i["name"] for i in data["want_to_try"]] == ["Dhamaka"]


_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da6360000002000001e5274de40000000049454e44ae426082"
)


def test_photo_endpoint_serves_image(tmp_path):
    img = tmp_path / "uuid-b1.png"
    img.write_bytes(_PNG_1x1)
    client = TestClient(create_app(_queue(), Ledger(":memory:"),
                                   photo_resolver=lambda u: str(img) if u == "uuid-b1" else None))
    r = client.get("/api/photo/uuid-b1")
    assert r.status_code == 200
    assert "image/png" in r.headers["content-type"]
    assert r.content == _PNG_1x1


def test_photo_endpoint_404_when_unknown():
    client = TestClient(create_app(_queue(), Ledger(":memory:"), photo_resolver=lambda u: None))
    assert client.get("/api/photo/nope").status_code == 404


def test_photo_endpoint_404_without_resolver():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    assert client.get("/api/photo/anything").status_code == 404


def test_added_marks_handled_and_filters_next_queue():
    led = Ledger(":memory:")
    client = TestClient(create_app(_queue(), led))
    r = client.post("/api/added", json={"place_id": "b1", "name": "Lilia", "bucket": "been", "rating": "loved"})
    assert r.json() == {"ok": True}
    assert led.is_handled("b1")
    data = client.get("/api/queue").json()
    assert data["been"] == []  # filtered out after being handled


def test_index_serves_html():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_ambiguous_item_filtered_when_candidate_handled():
    amb = MatchedPlace(
        bucket="been", status="ambiguous",
        raw=RawPlace(source="photos", lat=40.72, lon=-73.98),
        candidates=[
            PlaceCandidate(place_id="c1", name="Los Tacos No. 1", address="75 9th Ave", category="restaurant"),
            PlaceCandidate(place_id="c2", name="Time Out Market", address="55 Water St", category="restaurant"),
        ],
    )
    led = Ledger(":memory:")
    client = TestClient(create_app(Queue(been=[amb]), led))
    data = client.get("/api/queue").json()
    assert len(data["been"]) == 1
    assert data["been"][0]["place_id"] is None
    assert {c["name"] for c in data["been"][0]["candidates"]} == {"Los Tacos No. 1", "Time Out Market"}
    client.post("/api/added", json={"place_id": "c1", "name": "Los Tacos No. 1", "bucket": "been", "rating": "loved"})
    assert client.get("/api/queue").json()["been"] == []
