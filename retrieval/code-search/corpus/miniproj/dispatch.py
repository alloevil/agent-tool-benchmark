"""Dynamic dispatch traps: dict routing and getattr lookup."""

import sys

from .handlers import handler
from .handlers.impl import audit


def handle_ping(event):
    audit(event)
    return "ping-ok"


def handle_batch(event):
    return [handler(item) for item in event.get("items", ())]


ROUTES = {
    "ping": handle_ping,
    "batch": handle_batch,
}


def route(event):
    kind = event.get("kind", "unknown")
    if kind in ROUTES:
        return ROUTES[kind](event)
    return handler(event)


def route_by_name(event):
    target = getattr(sys.modules[__name__], "handle_" + event["kind"])
    return target(event)


def ping_directly(event):
    fn = getattr(sys.modules[__name__], "handle_ping")
    return fn(event)
