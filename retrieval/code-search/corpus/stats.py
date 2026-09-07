"""Rolling statistics built on the shared cache primitives."""

from miniproj.cache import Cache as Store
from miniproj.loggers import Logger


class StatsSink:
    """Accumulates numbers; draining pushes them into the store."""

    def __init__(self):
        self.store = Store(limit=2)
        self.logger = Logger(capacity=3)
        self.samples = []

    def add(self, value):
        self.samples.append(value)
        self.store.put("last", value)
        return len(self.samples)

    def drain(self):
        total = sum(self.samples)
        self.samples = []
        pushed = self.store.flush()
        self.logger.log("flush complete: %d keys" % pushed)
        self.logger.flush()
        return total
