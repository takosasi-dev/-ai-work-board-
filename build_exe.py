#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a single-file executable with PyInstaller (Windows: AIWorkBoard.exe).

Usage (Windows):
    pip install pyinstaller
    python build_exe.py
Output: dist/AIWorkBoard.exe
"""
import subprocess
import sys


def main():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--windowed",
        "--name", "AIWorkBoard",
        "ai_work_board.py",
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
