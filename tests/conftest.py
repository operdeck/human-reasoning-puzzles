"""Deterministic, dependency-free CI partitions of the complete collected suite."""

import hashlib

import pytest


def pytest_addoption(parser):
    parser.addoption("--shard", metavar="INDEX/COUNT", help="run one deterministic CI partition")


def pytest_collection_modifyitems(config, items):
    specification = config.getoption("--shard")
    if specification is None:
        return
    try:
        index, count = (int(value) for value in specification.split("/"))
    except ValueError as exc:
        raise pytest.UsageError("--shard must be INDEX/COUNT, for example 1/4") from exc
    if not 1 <= index <= count:
        raise pytest.UsageError("--shard requires 1 <= INDEX <= COUNT")
    selected, deselected = [], []
    for item in items:
        shard = int.from_bytes(hashlib.sha256(item.nodeid.encode()).digest()[:8]) % count + 1
        (selected if shard == index else deselected).append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
