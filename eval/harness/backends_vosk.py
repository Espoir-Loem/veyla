"""Backend Vosk : reconnaissance vocale locale, hors ligne, modèle français compact.

Le module s'importe sans Vosk installé — c'est l'instanciation qui échoue, avec
l'installation à demander. Le harnais reste ainsi en bibliothèque standard pour
tout ce qui n'est pas un backend.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

CHUNK = 8192


def _resample(frames: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Décimation linéaire 16 bits mono. Python pur : ni audioop (retiré en 3.13),
    ni scipy. Approximation assumée, documentée dans le manifeste."""
    if src_rate == dst_rate:
        return frames
    samples = [int.from_bytes(frames[i:i + 2], "little", signed=True)
               for i in range(0, len(frames) - 1, 2)]
    if not samples:
        return b""
    ratio = src_rate / dst_rate
    out = bytearray()
    for index in range(int(len(samples) / ratio)):
        position = index * ratio
        left = int(position)
        right = min(left + 1, len(samples) - 1)
        fraction = position - left
        value = samples[left] * (1 - fraction) + samples[right] * fraction
        out += int(value).to_bytes(2, "little", signed=True)
    return bytes(out)


class VoskBackend:
    name = "vosk-small-fr"
    inprocess = True

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = Path(model_dir) if model_dir else (
            Path(__file__).resolve().parents[2] / "models" / "vosk-model-small-fr-0.22")
        if not self.model_dir.is_dir():
            raise SystemExit(
                f"modèle introuvable : {self.model_dir}\n"
                "le télécharger depuis https://alphacephei.com/vosk/models "
                "(vosk-model-small-fr-0.22.zip) et le dépauder dans models/")
        # Empreinte des trois fichiers qui définissent le comportement du modèle.
        self.model_files = [self.model_dir / rel
                            for rel in ("am/final.mdl", "graph/Gr.fst", "conf/model.conf")]
        self.model = None
        self.resample = True

    def load(self) -> None:
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as exc:
            raise SystemExit(
                "Vosk n'est pas installé dans l'interpréteur courant.\n"
                "  python3 -m venv .venv && .venv/Scripts/python.exe -m pip install vosk\n"
                f"détail : {exc}")
        SetLogLevel(-1)
        self._recognizer_factory = KaldiRecognizer
        self.model = Model(str(self.model_dir))

    def transcribe(self, audio: Path) -> str:
        with wave.open(str(audio), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                raise ValueError(f"{audio.name} : canal unique et 16 bits requis")
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
        pcm = _resample(frames, rate, 16000) if rate != 16000 else frames

        recognizer = self._recognizer_factory(self.model, 16000)
        for offset in range(0, len(pcm), CHUNK):
            recognizer.AcceptWaveform(pcm[offset:offset + CHUNK])
        return json.loads(recognizer.FinalResult()).get("text", "")
