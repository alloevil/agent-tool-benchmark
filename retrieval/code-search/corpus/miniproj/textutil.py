"""Text helpers; normalize is wrapped by the traced decorator."""

from .decorators import traced


@traced
def normalize(text):
    return " ".join(text.strip().lower().split())


def shout(text):
    # normalize the text first, then upper-case it.
    return normalize(text).upper()
