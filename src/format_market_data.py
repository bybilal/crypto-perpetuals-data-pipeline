"""Compatibility entry point; implementation lives in crypto_pipeline.reporting."""
import sys
from crypto_pipeline import reporting as _package
from importlib import import_module
_impl = import_module("crypto_pipeline.reporting")
sys.modules[__name__] = _impl
