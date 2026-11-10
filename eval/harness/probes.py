"""Sondes système : durée audio, pic mémoire, empreintes, environnement.

Chaque sonde renvoie None avec une raison quand elle ne peut pas mesurer. Elle ne
remplace jamais une valeur absente par une estimation.
"""

from __future__ import annotations

import hashlib
import os
import platform
import sys
import wave
from pathlib import Path

__all__ = ["audio_duration_s", "peak_rss_bytes", "sha256", "environment", "PeakRssError"]


class PeakRssError(RuntimeError):
    pass


def audio_duration_s(path: Path) -> float | None:
    """Durée en secondes d'un WAV PCM. Autre conteneur -> None (pas de RTF deviné)."""
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if frames <= 0 or rate <= 0:
                return None
            return frames / float(rate)
    except (wave.Error, EOFError, OSError):
        return None


def peak_rss_bytes() -> dict:
    """Pic de mémoire résidente du processus courant.

    Ne couvre que le processus du harnais : un backend lancé en sous-processus
    échappe à cette mesure (il faudrait un Job Object Windows). Le harnais le
    refuse au lieu de publier un chiffre faux — voir backends.Backend.inprocess.
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        # Sans ces signatures, le HANDLE 64 bits est tronque a 32 et l'appel echoue.
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters),
                                               wintypes.DWORD]
        handle = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise PeakRssError("GetProcessMemoryInfo a echoue")
        return {"peak_rss_bytes": int(counters.PeakWorkingSetSize), "source": "PSAPI"}

    try:
        import resource

        # getrusage renvoie des kilo-octets sur Linux, des octets sur macOS.
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        factor = 1024 if sys.platform == "linux" else 1
        return {"peak_rss_bytes": int(raw) * factor, "source": "getrusage"}
    except Exception as exc:  # plateforme non couverte
        raise PeakRssError(f"sonde de pic mémoire indisponible : {exc}") from exc


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def environment() -> dict:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "harness_version": "0.1",
    }
