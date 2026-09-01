"""Allow ``python -m riskon`` invocation."""

from riskon.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
