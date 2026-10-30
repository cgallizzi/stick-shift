"""Assembles dist/StickShift-portable/ and zips it for copying to test PCs."""
import os
import shutil

import vgamepad

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "dist", "StickShift-portable")
MSI = os.path.join(os.path.dirname(vgamepad.__file__), "win", "vigem", "install", "x64",
                   "ViGEmBusSetup_x64.msi")

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
shutil.copy2(os.path.join(ROOT, "dist", "StickShift.exe"), OUT)
shutil.copy2(MSI, OUT)
shutil.copy2(os.path.join(ROOT, "QUICKSTART.txt"), OUT)
for bat in ("Calibrate.bat", "Start DS4 mode.bat"):
    shutil.copy2(os.path.join(ROOT, "portable", bat), OUT)
zip_path = shutil.make_archive(OUT, "zip", OUT)
print("built", zip_path, f"({os.path.getsize(zip_path) / 1e6:.1f} MB)")
