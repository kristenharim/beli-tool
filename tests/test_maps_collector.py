from pathlib import Path
from beli_tool.maps_collector import collect_maps

FIXTURES = Path(__file__).parent / "fixtures"


def test_collect_maps_reads_titles_and_skips_blank():
    places = collect_maps(FIXTURES)
    names = [p.name for p in places]
    assert "Tatiana by Kwame Onwuachi" in names
    assert "Dhamaka" in names
    assert len(places) == 2  # blank-title row skipped
    assert all(p.source == "maps" for p in places)
    assert places[0].source_list == "Want to go"
