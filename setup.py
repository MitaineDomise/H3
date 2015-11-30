__author__ = 'Emmanuel'
import sys

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {"packages": ["os"], "excludes": ["tkinter", "Pyside.QtXml"]}

# GUI applications require a different base on Windows (the default is for a
# console application).
base = None
if sys.platform == "win32":
    base = "Win32GUI"
#
# setup(name="H3",
#       version="0.1",
#       description="H3 first build",
#       options={"build_exe": build_exe_options},
#       requires=['pytz', 'Pyside', 'babel', 'iso3166', 'sqlalchemy', 'pg8000', 'xlsxwriter', 'openpyxl'],
#       executables=[Executable("H3.pyw", base=base)])
