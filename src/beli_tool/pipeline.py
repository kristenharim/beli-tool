from __future__ import annotations

from dataclasses import dataclass, field

from beli_tool.ledger import Ledger
from beli_tool.matcher import match_maps_place, match_photo_cluster
from beli_tool.models import MatchedPlace, RawPlace


@dataclass
class Queue:
    want_to_try: list[MatchedPlace] = field(default_factory=list)
    been: list[MatchedPlace] = field(default_factory=list)
    review: list[MatchedPlace] = field(default_factory=list)


def build_queue(
    maps_places: list[RawPlace],
    photo_raws: list[RawPlace],
    client,
    ledger: Ledger,
) -> Queue:
    handled = ledger.handled_ids()
    q = Queue()

    for raw in maps_places:
        m = match_maps_place(raw, client)
        if m.status == "no_match":
            q.review.append(m)
        elif m.match and m.match.place_id in handled:
            continue
        else:
            q.want_to_try.append(m)

    for raw in photo_raws:
        m = match_photo_cluster(raw, client)
        if m.status == "no_match":
            q.review.append(m)
        elif m.status == "confident" and m.match and m.match.place_id in handled:
            continue
        else:
            q.been.append(m)

    return q
