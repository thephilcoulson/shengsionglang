import os
import sys

# Ensure the package under test is importable when running pytest from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
