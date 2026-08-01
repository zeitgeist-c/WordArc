#!/usr/bin/env python3
"""One-release compatibility entry point for legacy Verbatim commands."""

from wordarc import *  # noqa: F401,F403 - intentionally preserves the old API
from wordarc import main


if __name__ == "__main__":
    raise SystemExit(main())
