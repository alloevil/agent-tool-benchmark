"""Tiny logger whose flush() shares its name with Cache.flush()."""


class Logger:
    def __init__(self, capacity=100):
        self._lines = []
        self._capacity = capacity
        self.flushed_lines = 0

    def log(self, message):
        self._lines.append(str(message))
        if len(self._lines) >= self._capacity:
            self.flush()

    def flush(self):
        count = len(self._lines)
        self.flushed_lines += count
        self._lines.clear()
        return count

    def pending(self):
        return len(self._lines)
