"""MAGI: a three-member council of local models that deliberates and decides."""

from importlib.metadata import PackageNotFoundError, version

# Read from installed metadata rather than a second hand-edited literal: this
# file said 0.12.0 while pyproject.toml said 0.13.1, and nothing caught it
# because nothing read it. The distribution is "magi-council" because plain
# "magi" was already taken on PyPI by a time-series package; the command is
# still `magi`.
try:
    __version__ = version("magi-council")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0+source"

__all__ = ["__version__"]
