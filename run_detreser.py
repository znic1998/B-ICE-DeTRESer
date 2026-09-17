"""Double-click / command-line launcher: python run_detreser.py

Adds the sibling ``tres_suite`` package folder to the import path so the GUI works straight
from the TRES Program folder without installing anything.
"""
import multiprocessing
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(HERE, "tres_suite"), HERE):
    if os.path.isdir(os.path.join(cand, "tres_suite")) and cand not in sys.path:
        sys.path.insert(0, cand)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if __name__ == "__main__":
    # Parallel workers start new Python processes that import this file; the guard above keeps
    # them from opening extra windows (macOS/Windows use the "spawn" start method).
    multiprocessing.freeze_support()
    from detreser.app import main

    sys.exit(main())
