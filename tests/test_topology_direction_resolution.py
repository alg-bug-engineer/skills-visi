from app.trace.topology import resolve_dir8_turn


def test_resolve_dir8_turn_accepts_entry_labels() -> None:
    assert resolve_dir8_turn("北进口", "直行") == (0, 2)
    assert resolve_dir8_turn("东进口", "左转") == (2, 1)
    assert resolve_dir8_turn("西进口", "直行") == (6, 2)

