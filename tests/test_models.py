from datetime import date
from beli_tool.models import RawPlace, PlaceCandidate, MatchedPlace


def test_rawplace_defaults():
    rp = RawPlace(source="maps", name="Lilia", source_list="Want to go")
    assert rp.lat is None and rp.photo_count == 0


def test_matchedplace_holds_candidate():
    cand = PlaceCandidate(place_id="abc", name="Lilia", address="567 Union Ave", category="restaurant")
    mp = MatchedPlace(
        bucket="been",
        status="confident",
        raw=RawPlace(source="photos", lat=40.7, lon=-73.9, visit_date=date(2026, 4, 12)),
        match=cand,
    )
    assert mp.match.place_id == "abc"
    assert mp.candidates == []
