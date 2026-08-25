from estimate_maestro.projection import open_interval, slice_count


def test_added_slices_are_counted():
    records = [
        {"event": "added", "slice": "sl-01"},
        {"event": "added", "slice": "sl-02"},
    ]

    assert slice_count(records) == 2


def test_dropped_slices_are_not_counted():
    records = [
        {"event": "added", "slice": "sl-01"},
        {"event": "added", "slice": "sl-02"},
        {"event": "dropped", "slice": "sl-02"},
    ]

    assert slice_count(records) == 1


def test_closing_a_slice_leaves_it_counted():
    records = [
        {"event": "added", "slice": "sl-01"},
        {"event": "closed", "slice": "sl-01"},
    ]

    assert slice_count(records) == 1


def test_renaming_a_slice_leaves_it_counted_once():
    records = [
        {"event": "added", "slice": "sl-01"},
        {"event": "renamed", "slice": "sl-01", "title": "Tier enum expansion"},
    ]

    assert slice_count(records) == 1


def test_a_rename_of_a_dropped_slice_does_not_resurrect_it():
    records = [
        {"event": "added", "slice": "sl-01"},
        {"event": "added", "slice": "sl-02"},
        {"event": "dropped", "slice": "sl-02"},
        {"event": "renamed", "slice": "sl-02", "title": "Back from the dead"},
    ]

    assert slice_count(records) == 1


def test_an_empty_log_counts_zero():
    assert slice_count([]) == 0


def test_an_interval_without_a_clock_out_is_open():
    records = [{"event": "clock_in", "interval": "iv-01", "at": "2026-08-24T09:00:00+02:00"}]

    found = open_interval(records)

    assert found is not None
    assert found["interval"] == "iv-01"


def test_a_closed_interval_is_not_open():
    records = [
        {"event": "clock_in", "interval": "iv-01", "at": "2026-08-24T09:00:00+02:00"},
        {"event": "clock_out", "interval": "iv-01", "at": "2026-08-24T11:00:00+02:00"},
    ]

    assert open_interval(records) is None


def test_an_annotation_does_not_close_an_interval():
    records = [
        {"event": "clock_in", "interval": "iv-01", "at": "2026-08-24T09:00:00+02:00"},
        {"event": "annotate", "interval": "iv-01", "note": "pairing"},
    ]

    assert open_interval(records) is not None
