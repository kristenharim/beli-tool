__all__ = ["__version__"]
# Single source of truth: pyproject reads this via [tool.setuptools.dynamic],
# beli-tool.spec parses it for CFBundleShortVersionString, and the web UI shows
# it in the footer. Bump here only.
__version__ = "0.6.0"
