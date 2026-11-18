from types import SimpleNamespace

import pytest

from tests.conftest import pytest_collection_modifyitems


def partition(specification, nodeids):
    items = [SimpleNamespace(nodeid=nodeid) for nodeid in nodeids]
    removed = []
    config = SimpleNamespace(
        getoption=lambda option: specification,
        hook=SimpleNamespace(pytest_deselected=lambda items: removed.extend(items)),
    )
    pytest_collection_modifyitems(config, items)
    return [item.nodeid for item in items], [item.nodeid for item in removed]


@pytest.mark.parametrize("total", [4, 8])
def test_ci_shards_partition_every_parameterized_case_once_independently_of_order(total):
    cases = [f"tests/test_puzzle.py::test_solve[case-{index}]" for index in range(100)]
    seen = []
    for shard in range(1, total + 1):
        selected, removed = partition(f"{shard}/{total}", cases)
        backwards, _ = partition(f"{shard}/{total}", list(reversed(cases)))
        assert set(selected).isdisjoint(removed)
        assert set(selected) | set(removed) == set(cases)
        assert selected == list(reversed(backwards))
        assert selected
        seen.extend(selected)
    assert sorted(seen) == sorted(cases)


@pytest.mark.parametrize("specification", ["0/4", "5/4", "1/0", "1", "1/2/3", "x/y"])
def test_bad_ci_shard_fails_rather_than_silently_dropping_tests(specification):
    with pytest.raises(pytest.UsageError, match="--shard"):
        partition(specification, ["tests/test_puzzle.py::test_solve"])
