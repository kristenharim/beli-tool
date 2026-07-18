from datetime import date
from fastapi.testclient import TestClient

from beli_tool import __version__
from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace
from beli_tool.pipeline import Queue
from beli_tool.ledger import Ledger
from beli_tool.places_client import PlacesError
from beli_tool.webapp import create_app


def _queue():
    been = MatchedPlace(
        bucket="been", status="confident",
        raw=RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12),
                     photo_count=4, photo_ref="uuid-b1", photo_refs=["uuid-b1", "uuid-b2"]),
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
    assert data["been"][0]["photo_refs"] == ["uuid-b1", "uuid-b2"]
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


class FakeLog:
    def __init__(self):
        self.rows = []

    def append(self, name, bucket, rating=None, address="", visit_date=None):
        self.rows.append((name, bucket, rating, address, visit_date))
        return True


def test_added_mirrors_to_the_obsidian_log_with_server_side_details():
    log = FakeLog()
    client = TestClient(create_app(_queue(), Ledger(":memory:"), obsidian_log=log))
    client.post("/api/added", json={"place_id": "b1", "name": "Lilia", "bucket": "been", "rating": "loved"})
    # Address and visit date come from the queue, not the client's request.
    assert log.rows == [("Lilia", "been", "loved", "567 Union Ave", date(2026, 4, 12))]


def test_added_mirrors_an_ambiguous_pick_via_its_candidate():
    amb = MatchedPlace(
        bucket="been", status="ambiguous", raw=RawPlace(source="photos", lat=40.7, lon=-73.9),
        candidates=[PlaceCandidate(place_id="c1", name="Los Tacos", address="75 9th Ave", category="restaurant")],
    )
    log = FakeLog()
    client = TestClient(create_app(Queue(been=[amb]), Ledger(":memory:"), obsidian_log=log))
    client.post("/api/added", json={"place_id": "c1", "name": "Los Tacos", "bucket": "been", "rating": "fine"})
    assert log.rows[0][3] == "75 9th Ave"  # resolved from the chosen candidate


def test_no_log_configured_is_fine():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    assert client.post(
        "/api/added", json={"place_id": "b1", "name": "Lilia", "bucket": "been", "rating": "loved"}
    ).json() == {"ok": True}


def test_queue_reports_version_and_rescan_availability():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    data = client.get("/api/queue").json()
    assert data["version"] == __version__
    assert data["can_rescan"] is False  # no rebuild wired -> UI hides the button


def test_rescan_swaps_in_the_new_queue():
    fresh = MatchedPlace(
        bucket="want_to_try", status="confident", raw=RawPlace(source="maps", name="Rezdora"),
        match=PlaceCandidate(place_id="w2", name="Rezdora", address="27 E 20th", category="restaurant"),
    )
    client = TestClient(
        create_app(_queue(), Ledger(":memory:"), rebuild=lambda: Queue(want_to_try=[fresh]))
    )
    assert [i["name"] for i in client.get("/api/queue").json()["want_to_try"]] == ["Dhamaka"]
    assert client.post("/api/rescan").json() == {"ok": True}
    assert [i["name"] for i in client.get("/api/queue").json()["want_to_try"]] == ["Rezdora"]


def test_rescan_preserves_the_ledger():
    led = Ledger(":memory:")
    client = TestClient(create_app(_queue(), led, rebuild=_queue))
    client.post("/api/added", json={"place_id": "b1", "name": "Lilia", "bucket": "been", "rating": "loved"})
    client.post("/api/rescan")
    # The rescan re-finds Lilia, but it stays handled: the point of rescanning
    # is picking up new places, not re-litigating old ones.
    assert led.is_handled("b1")
    assert client.get("/api/queue").json()["been"] == []


def test_rescan_501_without_a_rebuild():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    assert client.post("/api/rescan").status_code == 501


def test_rescan_surfaces_places_setup_errors():
    def boom():
        raise PlacesError("billing isn't enabled")

    client = TestClient(create_app(_queue(), Ledger(":memory:"), rebuild=boom))
    r = client.post("/api/rescan")
    assert r.status_code == 502
    assert "billing" in r.json()["detail"]


def test_rescan_lock_is_released_after_a_failure():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise PlacesError("transient")
        return Queue()

    client = TestClient(create_app(_queue(), Ledger(":memory:"), rebuild=flaky))
    assert client.post("/api/rescan").status_code == 502
    # A failed rescan must not wedge the lock and 409 forever after.
    assert client.post("/api/rescan").status_code == 200


def test_rescan_requires_the_token():
    client = TestClient(create_app(_queue(), Ledger(":memory:"), token="s3cret", rebuild=Queue))
    assert client.post("/api/rescan").status_code == 403
    assert client.post("/api/rescan?t=s3cret").status_code == 200


def test_index_serves_html():
    client = TestClient(create_app(_queue(), Ledger(":memory:")))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_review_items_exposed_with_raw_name():
    rev = MatchedPlace(
        bucket="want_to_try", status="no_match",
        raw=RawPlace(source="maps", name="Prospect Park"),
    )
    client = TestClient(create_app(Queue(review=[rev]), Ledger(":memory:")))
    data = client.get("/api/queue").json()
    assert data["review"][0]["raw_name"] == "Prospect Park"
    assert data["review"][0]["name"] is None  # no match, so no resolved name


def test_token_guards_every_route():
    app = create_app(_queue(), Ledger(":memory:"), token="s3cret")
    # A fresh client (no cookie) with no token is rejected everywhere.
    assert TestClient(app).get("/api/queue").status_code == 403
    assert TestClient(app).get("/").status_code == 403
    assert TestClient(app).get("/", params={"t": "wrong"}).status_code == 403
    # The right token in the query works, and opening index sets the cookie
    # so later same-client calls (incl. photo/img loads) pass without ?t=.
    c = TestClient(app)
    assert c.get("/", params={"t": "s3cret"}).status_code == 200
    assert c.get("/api/queue").status_code == 200
    assert c.post("/api/skip", json={"place_id": "b1"}).status_code == 200


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
