from estimate_maestro.projection import slice_count


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


def test_an_empty_log_counts_zero():
    assert slice_count([]) == 0
