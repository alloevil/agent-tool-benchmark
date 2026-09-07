"""Function decorators used across miniproj."""

import functools

CALLS = {}


def traced(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        CALLS[func.__name__] = CALLS.get(func.__name__, 0) + 1
        return func(*args, **kwargs)

    return wrapper
