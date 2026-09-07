"""miniproj: synthetic corpus for the code-search benchmark.

The package facade re-exports the public API so callers can write
``from miniproj import handler`` without knowing the module layout.
"""

from .handlers import handler as handler
from .cache import Cache as Cache
from .loggers import Logger as Logger
