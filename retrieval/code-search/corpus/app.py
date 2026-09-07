"""Application entry point wiring everything together."""

import miniproj.textutil as tu

from miniproj import Cache, Logger, handler
from miniproj.dispatch import route, route_by_name


def run(events):
    # The Cache instance below is flushed once at the end of the run.
    cache = Cache(limit=4)
    log = Logger(capacity=10)
    results = []
    for event in events:
        name = tu.normalize(event.get("name", ""))
        cached = cache.get(name)
        if cached is None:
            cached = cache.put(name, handler(event))
        log.log("event %s -> %s" % (name, cached))
        results.append(route(event))
    cache.flush()
    log.flush()
    return results


def main():
    events = [
        {"kind": "ping", "name": "First Ping"},
        {"kind": "batch", "name": "Batch  One", "items": [{"kind": "ping"}]},
        {"kind": "other", "name": "misc"},
    ]
    out = run(events)
    out.append(route_by_name({"kind": "ping"}))
    print(len(out))


if __name__ == "__main__":
    main()
