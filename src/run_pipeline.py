"""Compatibility entry point for crypto_pipeline.cli."""
# Import sys for use below.
import sys
# Import import_module from importlib for use below.
from importlib import import_module
# Load the package implementation while preserving this legacy import or script name.
_impl = import_module("crypto_pipeline.cli")
# Run this entry point only when the file is executed directly.
if __name__ == "__main__":
    # Stop this operation with SystemExit(_impl.main()).
    raise SystemExit(_impl.main())
else:
    # Use _impl; store the result in sys.modules[__name__].
    sys.modules[__name__] = _impl
