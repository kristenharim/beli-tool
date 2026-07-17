# PyInstaller spec — builds "Beli Staging.app", a double-click launcher.
# osxphotos is heavy (pyobjc + data files), so collect it wholesale.
import re

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Parsed, not imported: beli_tool pulls in heavy deps that needn't load here.
VERSION = re.search(
    r'__version__ = "([^"]+)"', open("src/beli_tool/__init__.py").read()
).group(1)

datas, binaries, hiddenimports = collect_all("osxphotos")
hiddenimports += collect_submodules("uvicorn") + collect_submodules("photoscript")
datas += [("src/beli_tool/templates", "beli_tool/templates")]

a = Analysis(
    ["packaging/app_entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="Beli Staging", console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Beli Staging")
app = BUNDLE(
    coll,
    name="Beli Staging.app",
    bundle_identifier="com.kristenho.beli-tool",
    info_plist={"LSUIElement": False, "CFBundleShortVersionString": VERSION},
)
