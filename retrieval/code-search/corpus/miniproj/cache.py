"""In-memory cache whose flush() is unrelated to Logger.flush()."""


class Cache:
    def __init__(self, limit=8):
        self._data = {}
        self._dirty = 0
        self._limit = limit
        self.flush_count = 0

    def put(self, key, value):
        self._data[key] = value
        self._dirty += 1
        if self._dirty >= self._limit:
            self.flush()
        return value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def flush(self):
        """Reset the dirty counter. Unrelated to Logger.flush."""
        self._dirty = 0
        self.flush_count += 1
        return len(self._data)

    def __len__(self):
        return len(self._data)
