"""Test runner for the generated simple_login script."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Load the generated script
import importlib.util
spec = importlib.util.spec_from_file_location(
    "simple_login",
    os.path.join("benchmarks", "simple_login", "generated_v3.py"),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Run it
print("Starting test...")
try:
    result = mod.simple_login(username="teste", password="teste123")
    print("RESULTADO:", result)
    print("STATUS: F - End-to-end success")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
