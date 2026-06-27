from beli_tool.ledger import Ledger


def test_ledger_marks_and_dedupes():
    led = Ledger(":memory:")
    assert led.handled_ids() == set()
    led.mark_added("p1", "Lilia", "been", rating="loved")
    assert led.is_handled("p1")
    assert "p1" in led.handled_ids()


def test_ledger_dismiss_counts_as_handled():
    led = Ledger(":memory:")
    led.mark_dismissed("p2", "Somewhere", "want_to_try")
    assert led.is_handled("p2")


def test_ledger_reinsert_is_idempotent():
    led = Ledger(":memory:")
    led.mark_added("p1", "Lilia", "been", "loved")
    led.mark_added("p1", "Lilia", "been", "fine")
    assert len(led.handled_ids()) == 1


def test_ledger_upsert_updates_rating():
    led = Ledger(":memory:")
    led.mark_added("p1", "Lilia", "been", "loved")
    led.mark_added("p1", "Lilia", "been", "fine")
    row = led.conn.execute("SELECT rating FROM handled WHERE place_id = 'p1'").fetchone()
    assert row[0] == "fine"
