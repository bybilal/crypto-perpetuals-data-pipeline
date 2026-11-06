"""Compatibility entry point; implementation lives in crypto_pipeline.normalization."""
# Import sys for use below.
import sys
# Import normalization from crypto_pipeline for use below.
from crypto_pipeline import normalization as _package
# Import import_module from importlib for use below.
from importlib import import_module
# Load the package implementation while preserving this legacy import or script name.
_impl = import_module("crypto_pipeline.normalization")
# Use _impl; store the result in sys.modules[__name__].
sys.modules[__name__] = _impl
