"""Concrete event handler implementation."""


def handler(event):
    """Process one event dict and return a status string.

    This docstring mentions handler(event) by name; a text search that
    counts docstrings will report this line as a reference.
    """
    kind = event.get("kind", "unknown")
    if kind == "ping":
        return "pong"
    if kind == "batch":
        return "handled:%d" % len(event.get("items", ()))
    return "handled:" + kind


def audit(event):
    # The word handler appears in this comment but is never called here.
    trail = dict(event)
    trail["audited"] = True
    return trail
