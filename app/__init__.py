"""Follei backend application package."""
import sys
import os

# Ensure app/services is in sys.path so that 'import mcp' works correctly
services_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'services'))
if services_dir not in sys.path:
    sys.path.insert(0, services_dir)
