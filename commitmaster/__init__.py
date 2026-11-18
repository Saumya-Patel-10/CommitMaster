import os
import sys

# Ensure Windows Tcl/Tk library paths are resolved for Tkinter
if sys.platform == "win32":
    py_dir = os.path.dirname(sys.executable)
    tcl_dir = os.path.join(py_dir, "tcl", "tcl8.6")
    tk_dir = os.path.join(py_dir, "tcl", "tk8.6")
    if os.path.exists(tcl_dir) and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.exists(tk_dir) and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = tk_dir
