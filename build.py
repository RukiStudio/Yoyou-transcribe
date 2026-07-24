"""Create a distributable Windows executable with PyInstaller.

Run `python build.py` after installing requirements. The resulting application is
placed in dist/RukiMusicTranscriber/RukiMusicTranscriber.exe.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Invoke PyInstaller with the packages used through runtime imports."""
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "RukiMusicTranscriber",
        "--collect-all",
        "librosa",
        "--collect-all",
        "soundfile",
        "--collect-all",
        "scipy",
        "main.py",
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
