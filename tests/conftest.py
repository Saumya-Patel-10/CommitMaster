"""Suite-wide hygiene.

Tkinter objects (Tk roots, StringVar, ...) must be finalised on the thread that owns the Tcl
interpreter. Tests create many windows; when one is left in a reference cycle, the cyclic garbage
collector may free it later on whichever thread happens to trigger a collection, for example a git
worker or HTTP-server thread from another test. That has produced `main thread is not in main loop`
errors and, intermittently, a hard process abort (exit code 0x80000003) halfway through the suite.
Collecting on the main thread after every test frees those objects where it is safe.
"""
import gc

import pytest


@pytest.fixture(autouse=True)
def _collect_tk_garbage_on_main_thread():
    yield
    gc.collect()
