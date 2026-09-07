"""Behavioral checks for miniproj (plain asserts, run as a script)."""

from miniproj import handler
from miniproj.cache import Cache
from miniproj.dispatch import ROUTES, ping_directly, route
from miniproj.loggers import Logger
from miniproj.textutil import normalize, shout


def test_handler_ping():
    assert handler({"kind": "ping"}) == "pong"


def test_route_batch():
    out = route({"kind": "batch", "items": [{"kind": "ping"}]})
    assert out == ["pong"]


def test_route_table_is_static():
    assert set(ROUTES) == {"ping", "batch"}


def test_ping_directly():
    assert ping_directly({"kind": "ping"}) == "ping-ok"


def test_normalize_and_shout():
    assert normalize("  Hello   World ") == "hello world"
    assert shout("hi there") == "HI THERE"


def test_cache_auto_flush():
    cache = Cache(limit=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.flush_count == 1
    cache.flush()
    assert cache.flush_count == 2


def test_logger_flush_returns_count():
    log = Logger(capacity=99)
    log.log("one")
    log.log("two")
    assert log.flush() == 2
    assert log.pending() == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all checks passed")
