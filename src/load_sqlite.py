"""Compatibility entry point for crypto_pipeline.storage.loader."""
import sys
from importlib import import_module
_impl = import_module("crypto_pipeline.storage.loader")
if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl
