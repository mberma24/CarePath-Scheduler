from datetime import UTC, datetime
from itertools import combinations

import pytest
from sqlalchemy import select

from app.db.models import Block
from app.seed import seed


@pytest.mark.parametrize(
    "now",
    [
        pytest.param(datetime(2026, 11, 18, 14, 7, tzinfo=UTC), id="weekday-afternoon"),
        pytest.param(datetime(2026, 11, 1, 4, 0, tzinfo=UTC), id="dst-end-night"),
        pytest.param(datetime(2026, 3, 8, 23, 59, tzinfo=UTC), id="dst-start-late"),
    ],
)
def test_seed_never_overlaps_blocks_for_one_owner(db, now):
    seed(db, now)

    by_owner: dict[tuple[int | None, int | None], list[Block]] = {}
    for block in db.scalars(select(Block)):
        by_owner.setdefault((block.patient_id, block.resource_id), []).append(block)

    assert sum(len(blocks) for blocks in by_owner.values()) > 100  # the seed is busy
    for owner, blocks in by_owner.items():
        for a, b in combinations(blocks, 2):
            overlap = a.start_time < b.end_time and b.start_time < a.end_time
            assert not overlap, (
                f"owner {owner}: {a.start_time}-{a.end_time} overlaps {b.start_time}-{b.end_time}"
            )


def test_seed_blocks_are_valid(db):
    seed(db, datetime(2026, 11, 18, 14, 7, tzinfo=UTC))

    for block in db.scalars(select(Block)):
        assert block.end_time > block.start_time
        assert (block.patient_id is None) != (block.resource_id is None)  # exactly one owner
