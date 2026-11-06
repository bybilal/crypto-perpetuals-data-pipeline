"""Compatibility entry point; implementation lives in crypto_pipeline.normalization."""
import sys
from crypto_pipeline import normalization as _package
from importlib import import_module
_impl = import_module("crypto_pipeline.normalization")
sys.modules[__name__] = _impl
