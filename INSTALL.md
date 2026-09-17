# B-ICE DeTRESer — install, run, build

The user guide (what the program does and how to use it) is `detreser/README.md`, also shown by the **Read Me** button inside the program. This file is only about getting it running.

## Packaged app (nothing to install)

Download the build for your computer, unzip it and double-click:

* **macOS (Apple Silicon)** — `B-ICE DeTRESer.app`. The first time, macOS says the developer cannot be verified: right-click the app → *Open* → *Open*. Once per computer.
* **Windows 10/11** — the `B-ICE DeTRESer` folder with `B-ICE DeTRESer.exe` inside; keep the folder together. If SmartScreen appears: *More info* → *Run anyway*.

No Python, no admin rights; about 1 GB of disk.

## Running from source

Requirements: Python 3.10 or newer.

    git clone <this repository>
    cd "TRES Program"
    python -m pip install -r requirements-gui.txt
    python run_detreser.py

(`python3` instead of `python` on macOS.) Minimum files: `run_detreser.py`, `detreser/`, `tres_suite/tres_suite/`, `requirements-gui.txt`.

## Building the packaged app

One build per platform: build on a Mac for Macs, on Windows for Windows. You do not need a machine of each kind — pushing a version tag to GitHub builds both automatically (see below).

Building by hand, in a clean environment (avoids Anaconda's incompatible `pathlib` package):

    conda create -n detreser python=3.11 -y
    conda activate detreser
    python -m pip install -r requirements-gui.txt pyinstaller
    pyinstaller DeTRESer.spec

Output in `dist/`. Warnings about `user32`/`ole32` libraries on macOS are harmless. Zip and share the `.app` (macOS) or the whole `B-ICE DeTRESer` folder (Windows); delete `build/`.

## Automatic builds on GitHub

`.github/workflows/build.yml` builds the Windows folder and the macOS app on GitHub's own machines, runs the backend tests first, and attaches both zips to a Release:

    git tag v1.0
    git push origin v1.0

A few minutes later the zips are under *Releases* on the repository page. The *Actions* tab also has a "Run workflow" button for a build without a release (zips appear as workflow artifacts). Windows users download `B-ICE-DeTRESer-windows.zip`, unzip it and run `B-ICE DeTRESer.exe` from inside the folder.

## Tests

    cd tres_suite && python -m pytest tests -q          # backend
    QT_QPA_PLATFORM=offscreen python tests_gui/drive_gui.py <data folder> <screenshot folder>   # GUI end-to-end
