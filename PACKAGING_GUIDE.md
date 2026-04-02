# Matrix Traffic App — Standalone Executable Packaging Guide

Complete reference for building the Matrix Traffic Data Extraction app into a
standalone Windows `.exe` that can run on any PC without Python installed.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tool Comparison & Recommendation](#2-tool-comparison--recommendation)
3. [One-Folder vs One-File Mode](#3-one-folder-vs-one-file-mode)
4. [Prerequisites](#4-prerequisites)
5. [Code Changes Required Before Building](#5-code-changes-required-before-building)
6. [PyInstaller Spec File](#6-pyinstaller-spec-file)
7. [Build Helper Script](#7-build-helper-script)
8. [Step-by-Step Build Instructions](#8-step-by-step-build-instructions)
9. [Troubleshooting Common Issues](#9-troubleshooting-common-issues)
10. [Distribution — Wrapping in an Installer](#10-distribution--wrapping-in-an-installer)
11. [Project File Structure Reference](#11-project-file-structure-reference)
12. [Full Dependency List](#12-full-dependency-list)
13. [Technical Notes & Gotchas](#13-technical-notes--gotchas)

---

## 1. Project Overview

**App**: Matrix Traffic Data Extraction v1.1.0
**Entry point**: `main.py` (function `main()`)
**GUI framework**: PySide6 (Qt for Python)
**Python version**: 3.10 – 3.13 (3.12 recommended; PaddlePaddle does NOT support 3.14)
**Repo**: https://github.com/noahprowse/Matrix_ANPR_AND_MIDBLOCK_COUNTER.git

**Heavy dependencies**:
- `ultralytics` (YOLO object detection + ByteTrack tracking)
- `paddleocr` + `paddlepaddle` (overlay text & license plate OCR)
- `PySide6` (Qt 6 GUI)
- `opencv-python` (video frame reading)
- `torch` (optional — only needed for vision AI classification)

**Data files that must ship with the app**:
| File | Purpose | Location |
|------|---------|----------|
| `yolo11n.pt` | Vehicle detection model (Counter module) | Project root |
| `yolov8n.pt` | Plate detection model (ANPR module) | Project root |
| `bytetrack_traffic.yaml` | Tuned ByteTrack tracker config | Project root |
| PaddleOCR models | OCR inference models (~100MB) | Auto-downloaded to `~/.paddleocr/` |

---

## 2. Tool Comparison & Recommendation

### Evaluated Options

| Tool | Build Time | Startup Speed | ML Support | PySide6 Support | Verdict |
|------|-----------|---------------|------------|-----------------|---------|
| **PyInstaller** | 5-15 min | Instant (folder) | Excellent | Excellent | **RECOMMENDED** |
| Nuitka | 1-2 hours | Fastest (compiled C) | Good | Good | Too slow to iterate |
| cx_Freeze | 5-10 min | Good | Limited | Has active bugs | Not reliable |
| Briefcase | 10-20 min | Good | No ML support | Great | Can't handle our stack |

### Why PyInstaller Wins

1. **Best ML ecosystem support** — documented workarounds for every combination
   of ultralytics, PaddleOCR, PaddlePaddle, and torch
2. **5-15 minute build** — fast iteration when fixing missing imports/data
3. **Largest community** — Stack Overflow answers exist for every error you'll hit
4. **Spec file system** — full control over what gets bundled, what gets excluded
5. **collect_all()** — automatically handles complex packages like `ultralytics`
   that dynamically load submodules and data files

### Why Not the Others

- **Nuitka**: Compiles Python to C, so builds take 1-2 hours. Great for final
  production but terrible for iterating. Consider as a follow-up optimisation.
- **cx_Freeze**: Has active bugs with PySide6 plugin copying. Would need manual
  workarounds for Qt platform plugins.
- **Briefcase**: Built for simple GUI apps. No support for bundling ML models
  or handling the complex import chains of ultralytics/paddle.

---

## 3. One-Folder vs One-File Mode

### One-Folder (RECOMMENDED)

```
dist/
  MatrixTraffic/
    MatrixTraffic.exe      ← Main executable
    python312.dll
    PySide6/
    ultralytics/
    paddleocr/
    yolo11n.pt             ← Model files alongside .exe
    yolov8n.pt
    bytetrack_traffic.yaml
    ... (DLLs, data files)
```

- **Instant startup** — files already unpacked on disk
- **~1.0–1.5 GB** disk footprint
- YOLO models sit alongside the .exe — easy to swap without rebuilding
- Wrap in an installer (Inno Setup) for clean distribution → user gets single `setup.exe`

### One-File (NOT recommended for this app)

```
dist/
  MatrixTraffic.exe  ← Single 1.5 GB file
```

- **1-2 minute startup** every launch — extracts entire bundle to `%TEMP%`
- Doubles disk usage (file + extracted temp folder)
- Antivirus programs frequently flag large self-extracting executables
- No advantage over folder mode when wrapped in an installer

---

## 4. Prerequisites

### Python Environment Setup (on the build machine)

```powershell
# Use Python 3.12 (NOT 3.14 — PaddlePaddle doesn't support it)
python -m venv venv
.\venv\Scripts\activate

# Install core dependencies
pip install -r requirements.txt

# Install PyInstaller
pip install pyinstaller

# IMPORTANT: If you want a smaller bundle, use CPU-only PyTorch
# This saves ~2 GB by excluding CUDA libraries
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Pre-download PaddleOCR models (they auto-download on first use)
# Run this once so they're cached locally:
python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='en', show_log=True)"
```

### Required YOLO Model Files

Ensure these exist at the project root:
- `yolo11n.pt` — used by Counter module (vehicle detection)
- `yolov8n.pt` — used by ANPR module (plate detection)

If missing, ultralytics will auto-download them on first run, but they need to
be present for packaging.

---

## 5. Code Changes Required Before Building

### 5.1. Add `get_base_path()` to `src/common/utils.py`

The app uses `__file__`-based path resolution in several places. When frozen
into an .exe, `__file__` points inside the PyInstaller bundle directory, not
the user-facing folder. Add this function:

```python
import sys
import os

def get_base_path() -> str:
    """Return the application root directory.

    When running from source: returns the project root (parent of src/).
    When running as a frozen .exe: returns the directory containing the .exe.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller sets sys.executable to the .exe path
        return os.path.dirname(sys.executable)
    # Source mode: utils.py is at src/common/utils.py → go up 3 levels
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

Add `import sys` and `import os` to the existing imports at the top of `utils.py`.

**Why**: YOLO model files (`.pt`) and `bytetrack_traffic.yaml` sit next to the
`.exe` in the output folder. `get_base_path()` resolves to that folder in frozen
mode, so the app finds its data files.

---

### 5.2. Fix tracker config path in `src/counter/counter_worker.py`

**Current code (lines 54-60)**:
```python
_TRACKER_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "bytetrack_traffic.yaml",
)
TRACKER_CONFIG = _TRACKER_CONFIG if os.path.isfile(_TRACKER_CONFIG) else "bytetrack.yaml"
```

**Replace with**:
```python
from src.common.utils import get_base_path

_TRACKER_CONFIG = os.path.join(get_base_path(), "bytetrack_traffic.yaml")
TRACKER_CONFIG = _TRACKER_CONFIG if os.path.isfile(_TRACKER_CONFIG) else "bytetrack.yaml"
```

**Why**: `__file__` resolves to a temporary directory inside the PyInstaller
bundle. `get_base_path()` resolves to the directory containing the `.exe`,
where `bytetrack_traffic.yaml` actually lives.

---

### 5.3. Handle PaddleOCR model paths in `src/common/overlay_ocr.py`

PaddleOCR auto-downloads models to `~/.paddleocr/` on first run. In a frozen
app, there are two strategies:

**Strategy A — Bundle models inside the app (offline-ready)**:

Modify the `_get_ocr()` classmethod:

```python
@classmethod
def _get_ocr(cls):
    """Lazy-load PaddleOCR as a thread-safe singleton."""
    if cls._ocr_instance is None:
        with cls._ocr_lock:
            if cls._ocr_instance is None:
                logger.info("Loading PaddleOCR engine (first use)...")
                from paddleocr import PaddleOCR

                kwargs = {
                    "use_angle_cls": True,
                    "lang": "en",
                    "show_log": False,
                    "use_gpu": False,
                }

                # When frozen, point to bundled model directories
                if getattr(sys, 'frozen', False):
                    import sys as _sys
                    base = _sys._MEIPASS  # PyInstaller's temp extraction dir
                    model_base = os.path.join(base, 'paddleocr_models')
                    if os.path.isdir(model_base):
                        kwargs['det_model_dir'] = os.path.join(model_base, 'det')
                        kwargs['rec_model_dir'] = os.path.join(model_base, 'rec')
                        kwargs['cls_model_dir'] = os.path.join(model_base, 'cls')

                cls._ocr_instance = PaddleOCR(**kwargs)
                logger.info("PaddleOCR engine ready.")
    return cls._ocr_instance
```

Add `import sys` and `import os` to the imports.

**Strategy B — Let PaddleOCR download on first launch (simpler, smaller bundle)**:

No code changes needed. PaddleOCR will auto-download models to `~/.paddleocr/`
on first launch. Requires internet on first run. Saves ~100 MB in bundle size.

**Recommendation**: Start with Strategy B for simplicity. Switch to A if you
need fully offline operation.

---

### 5.4. Add frozen-mode guards to `main.py`

```python
"""Matrix Traffic Data Extraction — Desktop Application Entry Point."""

import os
import logging
import sys

# Prevent OpenMP duplicate library crash (torch + paddle both ship libiomp5)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from src.app import MainWindow
from src.common.styles import APP_STYLESHEET


def _setup_logging() -> None:
    """Configure application-wide logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("ppocr").setLevel(logging.WARNING)
    logging.getLogger("paddle").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Matrix Traffic Data Extraction v1.1.0")

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


# CRITICAL: This guard prevents infinite process spawning in frozen mode.
# PyInstaller re-executes main.py when creating the process — without this
# guard, it would recursively spawn new windows forever.
if __name__ == "__main__":
    main()
```

**Key additions**:
1. `os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"` — must be set BEFORE importing
   torch or paddle. Both ship their own copy of Intel OpenMP (`libiomp5md.dll`)
   and without this flag, loading both causes a fatal crash.
2. `if __name__ == "__main__":` guard — already exists in current code, but
   ensure it stays. PyInstaller's bootloader re-imports the entry point.

---

### 5.5. Update `.gitignore`

Add these lines if not already present:

```gitignore
# PyInstaller build outputs
dist/
build/
*.spec
```

---

## 6. PyInstaller Spec File

Create `build.spec` at the project root:

```python
# build.spec — PyInstaller spec for Matrix Traffic Data Extraction
# Usage: pyinstaller build.spec

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ---- Collect complex packages ----
# These packages dynamically load submodules and data files that
# PyInstaller's automatic analysis can't detect.

ultralytics_datas, ultralytics_binaries, ultralytics_hiddenimports = collect_all('ultralytics')
paddleocr_datas, paddleocr_binaries, paddleocr_hiddenimports = collect_all('paddleocr')
paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all('paddle')

# ---- Data files to bundle ----
# These are copied into the bundle so the app can find them at runtime
added_datas = [
    ('bytetrack_traffic.yaml', '.'),  # tracker config → root of bundle
]

# Optionally bundle PaddleOCR models for offline operation
# Uncomment if using Strategy A from section 5.3:
# paddleocr_model_dir = os.path.expanduser('~/.paddleocr/whl')
# if os.path.isdir(paddleocr_model_dir):
#     added_datas.append((paddleocr_model_dir, 'paddleocr_models'))

all_datas = added_datas + ultralytics_datas + paddleocr_datas + paddle_datas

# ---- Hidden imports ----
# Modules that are imported dynamically (importlib, lazy loading, etc.)
hidden_imports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'cv2',
    'numpy',
    'pandas',
    'openpyxl',
    'PIL',
    'PIL.Image',
    'shapely',          # ultralytics may use this
    'scipy',            # ultralytics tracking
    'scipy.special',
    'yaml',             # tracker config parsing
    'logging.handlers',
]
hidden_imports += ultralytics_hiddenimports
hidden_imports += paddleocr_hiddenimports
hidden_imports += paddle_hiddenimports

# ---- Exclude unnecessary packages to reduce size ----
excludes = [
    'tkinter',
    'matplotlib',
    'notebook',
    'jupyter',
    'IPython',
    'sphinx',
    'pytest',
    'setuptools',
    'pip',
    'tensorboard',
    'tensorflow',
    'jax',
    'flax',
    # Optional vision AI deps (gracefully degrade if missing)
    'anthropic',
    'openai',
    'google',
    'transformers',
]

all_binaries = ultralytics_binaries + paddleocr_binaries + paddle_binaries

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],                    # Empty = one-folder mode
    exclude_binaries=True, # True = one-folder mode
    name='MatrixTraffic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,              # Compress binaries with UPX if available
    console=False,         # False = windowed mode (no terminal)
    # icon='assets/icon.ico',  # Uncomment when you have an icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MatrixTraffic',
)
```

---

## 7. Build Helper Script

Create `build.py` at the project root:

```python
"""Build helper for Matrix Traffic Data Extraction.

Automates the PyInstaller build process:
  1. Verifies environment
  2. Pre-downloads PaddleOCR models if needed
  3. Runs PyInstaller with the spec file
  4. Copies YOLO model files to the output folder
  5. Reports results

Usage:
    python build.py
"""

import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "MatrixTraffic")
SPEC_FILE = os.path.join(PROJECT_ROOT, "build.spec")

# YOLO model files that need to be alongside the .exe
MODEL_FILES = ["yolo11n.pt", "yolov8n.pt"]

# Tracker config
CONFIG_FILES = ["bytetrack_traffic.yaml"]


def check_environment():
    """Verify we're in the right Python environment."""
    print("=" * 60)
    print("Matrix Traffic — Build Script")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print(f"Project root: {PROJECT_ROOT}")
    print()

    # Check PyInstaller is installed
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("ERROR: PyInstaller not installed. Run: pip install pyinstaller")
        sys.exit(1)

    # Check critical dependencies
    for pkg in ["PySide6", "ultralytics", "paddleocr", "cv2", "pandas"]:
        try:
            __import__(pkg)
            print(f"  {pkg}: OK")
        except ImportError:
            print(f"  {pkg}: MISSING — run: pip install -r requirements.txt")
            sys.exit(1)

    # Check model files exist
    print()
    for model in MODEL_FILES:
        path = os.path.join(PROJECT_ROOT, model)
        if os.path.isfile(path):
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"  Model {model}: {size_mb:.1f} MB")
        else:
            print(f"  WARNING: {model} not found at project root!")
            print(f"  The app will try to download it on first run.")

    print()


def predownload_paddleocr_models():
    """Ensure PaddleOCR models are cached locally."""
    print("Checking PaddleOCR models...")
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False, use_gpu=False)
        print("  PaddleOCR models: OK (cached)")
    except Exception as e:
        print(f"  WARNING: PaddleOCR model download failed: {e}")
        print("  The app will try to download on first launch.")
    print()


def run_pyinstaller():
    """Run PyInstaller with the spec file."""
    print("Running PyInstaller...")
    print(f"  Spec file: {SPEC_FILE}")
    print()

    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", SPEC_FILE]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        print(f"\nERROR: PyInstaller failed with exit code {result.returncode}")
        sys.exit(1)

    print("\nPyInstaller completed successfully.")


def copy_model_files():
    """Copy YOLO model files to the dist folder (alongside .exe)."""
    print("\nCopying model files to output folder...")

    for filename in MODEL_FILES + CONFIG_FILES:
        src = os.path.join(PROJECT_ROOT, filename)
        dst = os.path.join(DIST_DIR, filename)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  Copied: {filename}")
        else:
            print(f"  SKIPPED (not found): {filename}")


def report_results():
    """Print final build report."""
    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)

    if os.path.isdir(DIST_DIR):
        # Calculate total size
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(DIST_DIR):
            for f in files:
                fp = os.path.join(root, f)
                total_size += os.path.getsize(fp)
                file_count += 1

        size_gb = total_size / (1024 ** 3)
        print(f"\nOutput directory: {DIST_DIR}")
        print(f"Total size: {size_gb:.2f} GB")
        print(f"File count: {file_count}")

        exe_path = os.path.join(DIST_DIR, "MatrixTraffic.exe")
        if os.path.isfile(exe_path):
            print(f"\nExecutable: {exe_path}")
            print("\nTo test: double-click MatrixTraffic.exe in the output folder")
        else:
            print("\nWARNING: MatrixTraffic.exe not found in output!")
    else:
        print(f"\nERROR: Output directory not found: {DIST_DIR}")


def main():
    check_environment()
    predownload_paddleocr_models()
    run_pyinstaller()
    copy_model_files()
    report_results()


if __name__ == "__main__":
    main()
```

---

## 8. Step-by-Step Build Instructions

### Quick Start (Summary)

```powershell
# 1. Activate venv
cd C:\Users\noahp\Matrix_ANPR_AND_MIDBLOCK_COUNTER
.\venv\Scripts\activate

# 2. Install PyInstaller
pip install pyinstaller

# 3. Make the code changes from Section 5 (if not already done)

# 4. Run the build
python build.py

# 5. Test the result
.\dist\MatrixTraffic\MatrixTraffic.exe
```

### Detailed Steps

#### Step 1: Prepare the environment

```powershell
cd C:\Users\noahp\Matrix_ANPR_AND_MIDBLOCK_COUNTER
.\venv\Scripts\activate
pip install pyinstaller
```

Verify PyInstaller installed:
```powershell
pyinstaller --version
```

#### Step 2: (Optional) Switch to CPU-only torch to save ~2 GB

If torch is installed (for the optional vision AI classifier), replace it with
the CPU-only version:

```powershell
pip uninstall torch torchvision torchaudio -y
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

This removes CUDA libraries (~2 GB) that aren't needed since detection runs
on CPU via ultralytics/ONNX.

#### Step 3: Make code changes

Apply all changes from [Section 5](#5-code-changes-required-before-building):
1. Add `get_base_path()` to `src/common/utils.py`
2. Update tracker config path in `src/counter/counter_worker.py`
3. (Optional) Update PaddleOCR model paths in `src/common/overlay_ocr.py`
4. Add `KMP_DUPLICATE_LIB_OK` to `main.py`

#### Step 4: Pre-download PaddleOCR models

```powershell
python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='en', show_log=True)"
```

This downloads the OCR models to `~/.paddleocr/whl/`. They'll be needed if
you want to bundle them (Strategy A) or they'll auto-download on the target
machine (Strategy B).

#### Step 5: Create `build.spec` and `build.py`

Copy the files from Sections 6 and 7 into the project root.

#### Step 6: Run the build

```powershell
python build.py
```

This will take 5-15 minutes. PyInstaller will:
1. Analyse all imports starting from `main.py`
2. Collect all data files from ultralytics, paddleocr, paddle
3. Bundle everything into `dist/MatrixTraffic/`
4. Copy YOLO model files alongside the .exe

#### Step 7: Test the output

```powershell
# Run the exe
.\dist\MatrixTraffic\MatrixTraffic.exe
```

Test checklist:
- [ ] App launches without Python installed
- [ ] Landing page appears with module selection
- [ ] Load a test video in both ANPR and Counter modules
- [ ] Counter: draw a count line and process — vehicles are detected and counted
- [ ] ANPR: process a video — plates are detected and read
- [ ] Export results to Excel — file saves correctly
- [ ] PaddleOCR overlay detection works (camera number, timestamp)

#### Step 8: Fix missing imports (iterative)

PyInstaller often misses dynamically imported modules. If the app crashes:

1. Run with console enabled to see the error:
   ```powershell
   # Temporarily change console=False to console=True in build.spec
   # Then rebuild
   pyinstaller --clean --noconfirm build.spec
   ```

2. Check for `ModuleNotFoundError` in the console output

3. Add the missing module to `hidden_imports` in `build.spec`

4. Rebuild and test again

Common modules that get missed:
- `sklearn.utils._typedefs`
- `skimage.feature._orb_descriptor_positions`
- `scipy.special._cdflib`
- `paddle.dataset`
- `paddle.distributed`

---

## 9. Troubleshooting Common Issues

### "DLL load failed" or "ImportError: DLL load failed"

**Cause**: Missing Visual C++ redistributable or conflicting DLLs.

**Fix**: Install the latest Visual C++ Redistributable from Microsoft:
https://aka.ms/vs/17/release/vc_redist.x64.exe

### "OMP: Error #15: Initializing libiomp5md.dll..."

**Cause**: Both PyTorch and PaddlePaddle ship their own copy of Intel OpenMP.
When both load, they conflict.

**Fix**: Add this to `main.py` BEFORE any imports:
```python
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
```

Or, after building, delete the duplicate DLL from the dist folder:
```powershell
# Find duplicate libiomp5md.dll files
Get-ChildItem -Path .\dist\MatrixTraffic\ -Recurse -Filter "libiomp5md.dll"
# Keep one, delete the other
```

### "Qt platform plugin could not be initialized"

**Cause**: PySide6 platform plugin DLLs not found.

**Fix**: PyInstaller's `collect_all('PySide6')` should handle this, but if not:
```python
# Add to build.spec hidden_imports:
'PySide6.QtCore',
'PySide6.QtGui',
'PySide6.QtWidgets',

# And add PySide6 plugins as data:
from PySide6 import __path__ as pyside6_path
pyside6_dir = pyside6_path[0]
added_datas.append((os.path.join(pyside6_dir, 'plugins'), 'PySide6/plugins'))
```

### App window appears but video processing fails

**Cause**: YOLO model files not found.

**Fix**: Ensure `.pt` files are in the same directory as `MatrixTraffic.exe`.
The `build.py` script copies them automatically, but double-check:
```powershell
ls .\dist\MatrixTraffic\*.pt
```

### PaddleOCR fails with "No such file or directory"

**Cause**: OCR models not downloaded or not bundled.

**Fix** (Strategy B — auto-download): Ensure the target machine has internet
access on first launch. Models download to `~/.paddleocr/whl/`.

**Fix** (Strategy A — bundled): Uncomment the PaddleOCR model bundling lines
in `build.spec` and rebuild.

### Build is too large (> 2 GB)

**Cause**: Full torch with CUDA libraries included.

**Fix**:
```powershell
pip uninstall torch torchvision torchaudio -y
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then rebuild. This typically saves 1.5-2 GB.

### App launches then immediately closes

**Cause**: Missing `if __name__ == "__main__"` guard.

**Fix**: Ensure `main.py` has:
```python
if __name__ == "__main__":
    main()
```

Without this, PyInstaller's bootloader re-imports `main.py` and causes
infinite process spawning.

### Antivirus flags the .exe

**Cause**: Normal for PyInstaller bundles. The self-extracting bootloader
triggers heuristic detection in some AV products.

**Fix**:
1. Sign the executable with a code signing certificate (recommended for distribution)
2. Submit to your AV vendor for whitelisting
3. Use `--key` flag in PyInstaller to encrypt the Python bytecode (mild deterrent)

---

## 10. Distribution — Wrapping in an Installer

For clean end-user distribution, wrap the one-folder output in an installer.

### Inno Setup (Recommended — Free)

1. Download Inno Setup: https://jrsoftware.org/isinfo.php

2. Create `installer.iss`:

```iss
[Setup]
AppName=Matrix Traffic Data Extraction
AppVersion=1.1.0
AppPublisher=Matrix
DefaultDirName={autopf}\MatrixTraffic
DefaultGroupName=Matrix Traffic
OutputBaseFilename=MatrixTraffic_Setup_v1.1.0
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=assets\icon.ico
; Remove the above line if no icon exists

[Files]
Source: "dist\MatrixTraffic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\Matrix Traffic"; Filename: "{app}\MatrixTraffic.exe"
Name: "{commondesktop}\Matrix Traffic"; Filename: "{app}\MatrixTraffic.exe"

[Run]
Filename: "{app}\MatrixTraffic.exe"; Description: "Launch Matrix Traffic"; Flags: nowait postinstall
```

3. Compile with Inno Setup → produces single `MatrixTraffic_Setup_v1.1.0.exe`

### What the user gets

- Download single `MatrixTraffic_Setup_v1.1.0.exe` (~600 MB compressed)
- Run installer → installs to Program Files
- Desktop shortcut + Start Menu entry
- Works offline after PaddleOCR models download on first run

---

## 11. Project File Structure Reference

```
Matrix_ANPR_AND_MIDBLOCK_COUNTER/
|-- main.py                          # App entry point
|-- pyproject.toml                   # Project metadata & dependencies
|-- requirements.txt                 # pip dependencies
|-- bytetrack_traffic.yaml           # Tuned ByteTrack tracker config
|-- yolo11n.pt                       # YOLOv11 Nano (vehicle detection)
|-- yolov8n.pt                       # YOLOv8 Nano (plate detection)
|-- build.spec                       # [TO CREATE] PyInstaller spec
|-- build.py                         # [TO CREATE] Build helper script
|-- .gitignore
|
|-- src/
|   |-- __init__.py
|   |-- app.py                       # MainWindow (QStackedWidget navigation)
|   |-- landing_page.py              # Module selection landing page
|   |
|   |-- anpr/                        # License Plate Recognition module
|   |   |-- __init__.py
|   |   |-- anpr_page.py             # ANPR UI page
|   |   |-- anpr_worker.py           # Background ANPR processing (QThread)
|   |   |-- anpr_export.py           # Excel export for ANPR results
|   |   |-- plate_detector.py        # YOLO-based plate detection
|   |   |-- plate_ocr.py             # PaddleOCR plate reading + validation
|   |
|   |-- counter/                     # Midblock Vehicle Counter module
|   |   |-- __init__.py
|   |   |-- counter_page.py          # Counter UI page
|   |   |-- counter_worker.py        # Background counting (QThread + ByteTrack)
|   |   |-- counter_export.py        # Excel export for count data
|   |   |-- vehicle_classifier.py    # Austroads 14-class vehicle classification
|   |   |-- vision_cache.py          # CLIP embedding cache for vision AI
|   |   |-- vision_classifier.py     # Optional AI-powered classification
|   |
|   |-- common/                      # Shared utilities
|       |-- __init__.py
|       |-- utils.py                 # Time/video/image helpers + get_base_path()
|       |-- overlay_ocr.py           # PaddleOCR singleton for CCTV text
|       |-- styles.py                # Dark theme stylesheet constants
|       |-- survey_widget.py         # Survey info form widget
|       |-- time_filter_widget.py    # Time window filter widget
|       |-- video_list_widget.py     # Drag-and-drop video list
|       |-- video_preview.py         # Video playback preview widget
|       |-- speed_calibration.py     # Speed estimation calibration
|
|-- assets/
|   |-- models/                      # (empty — for downloaded models)
|
|-- dist/                            # [BUILD OUTPUT] PyInstaller output
|   |-- MatrixTraffic/
|       |-- MatrixTraffic.exe
|       |-- yolo11n.pt
|       |-- yolov8n.pt
|       |-- bytetrack_traffic.yaml
|       |-- ... (DLLs, packages)
```

---

## 12. Full Dependency List

### Core Dependencies (required)

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | >= 6.6 | Qt 6 GUI framework |
| opencv-python | >= 4.9 | Video frame reading, image processing |
| ultralytics | >= 8.3 | YOLO object detection + ByteTrack tracking |
| paddleocr | >= 2.7 | Text recognition (overlay + plates) |
| paddlepaddle | >= 2.6 | PaddleOCR's ML backend |
| pandas | >= 2.2 | Data manipulation for exports |
| openpyxl | >= 3.1 | Excel file writing |
| numpy | >= 1.26 | Array operations |
| Pillow | >= 10.0 | Image format handling |

### Build Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pyinstaller | latest | Builds the standalone executable |

### Optional Dependencies (not included in build by default)

| Package | Purpose |
|---------|---------|
| anthropic | Claude AI vision classification |
| openai | GPT-4 vision classification |
| google-genai | Gemini vision classification |
| torch | CLIP embeddings for vehicle cache |
| transformers | HuggingFace model loading |

These are conditionally imported in `vision_classifier.py` and `vision_cache.py`.
The app degrades gracefully without them — falls back to size-based Austroads
classification using `vehicle_classifier.py`.

---

## 13. Technical Notes & Gotchas

### Python Version Compatibility

- **Python 3.12** is recommended
- **Python 3.10-3.13** all work
- **Python 3.14** does NOT work — PaddlePaddle has no 3.14 wheels
- The venv on the current machine uses Python 3.12

### The `persist=True` Bug (Critical — Already Fixed)

The ultralytics `model.track()` API has a subtle trap with the `persist`
parameter. `register_tracker()` only runs on the FIRST call and bakes the
`persist` value via `functools.partial`. If you pass `persist=False` on the
first call, the tracker is recreated on EVERY subsequent call, destroying all
tracking state. The current code correctly uses `persist=True` always and calls
`tracker.reset()` between videos.

**DO NOT CHANGE** the `persist=True` in `counter_worker.py` line 267.

### ByteTrack Configuration

The custom `bytetrack_traffic.yaml` is tuned for traffic counting:
- `track_buffer: 45` — keeps lost tracks for ~1.8 seconds at 25fps (handles
  brief occlusions from passing vehicles)
- `match_thresh: 0.85` — looser matching for traffic scenarios where vehicles
  can change appearance angle quickly
- `new_track_thresh: 0.3` — slightly higher to reduce false tracks from noise

### Frame Skip Settings

- **Counter**: `frame_skip=1` (process every frame) — best accuracy for
  line-crossing detection. ByteTrack needs consecutive frames for reliable tracking.
- **ANPR**: `frame_skip=3` (process every 3rd frame) — plates don't need
  frame-by-frame tracking, and OCR is expensive.

### PaddleOCR Thread Safety

The `OverlayOCR` class uses a thread-safe singleton pattern with a
`threading.Lock()`. This is critical because both the Counter and ANPR modules
may initialise OCR, and PaddleOCR is not thread-safe. The singleton ensures
only one instance exists across the entire application.

### OpenMP DLL Conflict

Both PyTorch and PaddlePaddle ship their own `libiomp5md.dll` (Intel OpenMP).
Loading both causes a fatal error unless `KMP_DUPLICATE_LIB_OK=TRUE` is set.
This must be set BEFORE any ML library imports. That's why it's at the very
top of `main.py`.

### sys._MEIPASS vs sys.executable

- `sys._MEIPASS` — points to PyInstaller's TEMPORARY extraction directory
  (inside `%TEMP%`). This is where bundled data files are extracted to.
  Use for accessing files bundled via `--add-data` in the spec file.
- `sys.executable` — points to the actual `.exe` file. Use `os.path.dirname()`
  to get the folder containing the .exe. This is where YOLO models and the
  tracker config should live (alongside the .exe, not bundled inside).

The `get_base_path()` function returns `os.path.dirname(sys.executable)` in
frozen mode because YOLO models are placed alongside the .exe (not bundled),
making them easy to update without rebuilding.

### Build Size Optimization

| Optimization | Savings |
|-------------|---------|
| CPU-only torch (remove CUDA) | ~2 GB |
| Exclude optional vision deps | ~200 MB |
| UPX compression | ~100-200 MB |
| Exclude test/doc data from packages | ~50-100 MB |

Expected final size: **1.0-1.5 GB** (one-folder, uncompressed)
Installer size: **~600 MB** (with LZMA2 compression)
