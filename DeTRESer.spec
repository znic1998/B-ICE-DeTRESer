# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build file:  pyinstaller DeTRESer.spec
# Run it from the "TRES Program" folder (where run_detreser.py, detreser/ and tres_suite/ live).
import os

here = os.path.abspath(".")
backend = os.path.join(here, "tres_suite")  # folder that contains the tres_suite package

a = Analysis(
    ["run_detreser.py"],
    pathex=[here, backend],
    binaries=[],
    datas=[
        (os.path.join(here, "detreser", "fonts"), os.path.join("detreser", "fonts")),
        (os.path.join(here, "detreser", "assets"), os.path.join("detreser", "assets")),
        (os.path.join(here, "detreser", "README.md"), "detreser"),
    ],
    hiddenimports=["matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg", "openpyxl", "yaml", "scipy.optimize", "scipy.signal",
                   "PySide6.QtSvg", "PySide6.QtSvgWidgets", "tres_suite", "tres_suite.advanced.deconvolution", "tres_suite.advanced.time_gated"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "IPython", "jupyter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="B-ICE DeTRESer",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(here, "detreser", "icon.icns") if os.path.exists(os.path.join(here, "detreser", "icon.icns")) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="B-ICE DeTRESer")
app = BUNDLE(coll, name="B-ICE DeTRESer.app", icon=None, bundle_identifier="jp.osaka-u.bice.detreser",
             info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "0.1.0"})
