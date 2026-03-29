"""
Shared test fixtures and configuration for pytest.
"""

import os
import sys

# Ensure backend modules are importable from tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
