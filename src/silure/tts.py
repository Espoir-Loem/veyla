"""Synthèse vocale locale : du texte vers un WAV audible.

Le module ne dépend que de la bibliothèque standard ; le moteur neuronal
(sherpa-onnx + modèle Piper) est une dépendance optionnelle, chargée seulement
quand on s'en sert.

Contrat : `Speaker.say` refuse de rendre un fichier muet. Une panne du moteur
lève `SilentSynthesis` au lieu d'écrire un WAV de zéros que personne ne remarque.
"""

from __future__ import annotations

import array
import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .asr import (
    MissingDependency,
    MissingModel,
    SilureError,
    peak_amplitude,
    read_wav,
)
from .master import master as apply_master

__all__ = [
    "EmptyText",
    "PiperEngine",
    "SilentSynthesis",
    "Speaker",
    "Speech",
    "TtsEngine",
    "resolve_model_dir",
    "wav_duration",
    "to_pcm16",
    "write_wav",
]

MODEL_VAR_ENV = "SILURE_TTS_MODEL"
MODEL_DOWNLOAD_HINT = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "vits-piper-fr_FR-siwis-medium.tar.bz2"
)
DEFAULT_MODEL_DIR = Path("models") / "vits-piper-fr_FR-siwis-medium"
SILENCE_PEAK = 1
"""En dessous ou à ce niveau, un PCM 16 bits ne porte aucun son exploitable."""


class EmptyText(SilureError):
    """Le texte à dire est vide : rien à synthétiser."""


class SilentSynthesis(SilureError):
    """Le moteur a rendu un signal muet : le fichier serait sans son."""


@runtime_checkable
class TtsEngine(Protocol):
    """Ce qu'un moteur de synthèse doit offrir. `Speaker` ne connaît que ceci."""

    name: str
    sample_rate: int

    def load(self) -> None: ...

    def synthesize(self, text: str) -> bytes: ...


def wav_duration(path: str | os.PathLike[str]) -> tuple[float, int]:
    """Durée en secondes et fréquence d'un WAV lisible."""
    try:
        with wave.open(str(path)) as w:
            rate = w.getframerate()
            frames = w.getnframes()
    except (OSError, wave.Error) as exc:
        raise SilureError(f"ce fichier n'est pas un WAV lisible : {path} ({exc})") from exc
    if rate <= 0:
        raise SilureError(f"WAV invalide, fréquence nulle : {path}")
    return frames / rate, rate


def to_pcm16(samples) -> bytes:
    """Convertit des flottants [-1, 1] en PCM 16 bits, avec écrêtage explicite.

    Les valeurs hors bornes sont ramenées à -32768 / 32767 plutôt que de
    déborder en silence (le dépassement d'un `int` borné donne un bruit sec).
    """
    out = array.array("h")
    for value in samples:
        scaled = round(float(value) * 32767.0)
        out.append(max(-32768, min(32767, scaled)))
    if sys.byteorder == "big":  # pragma: no cover - plateformes exotiques
        out.byteswap()
    return out.tobytes()


def write_wav(path: str | os.PathLike[str], pcm: bytes, sample_rate: int) -> Path:
    """Écrit un WAV mono PCM 16 bits, puis relit l'en-tête pour le vérifier."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    frames, rate = read_wav(target)
    if rate != sample_rate or len(frames) != len(pcm):
        raise SilureError(f"{target} : en-tête incohérent après écriture")
    return target


@dataclass(frozen=True)
class Speech:
    """Audio synthétisé et ce qu'il faut pour en juger sans l'écouter."""

    text: str
    pcm: bytes
    sample_rate: int
    engine: str
    style: str = "neutre"
    gain_db: float = 0.0

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / 2 / self.sample_rate

    @property
    def peak(self) -> int:
        return peak_amplitude(self.pcm)

    @property
    def silent(self) -> bool:
        return self.peak <= SILENCE_PEAK

    def save(self, path: str | os.PathLike[str]) -> Path:
        return write_wav(path, self.pcm, self.sample_rate)


class Speaker:
    """Orchestre texte → audio, sans connaître l'implémentation du moteur."""

    def __init__(self, engine: TtsEngine) -> None:
        self.engine = engine

    def say(self, text: str, style: str = "podcast") -> Speech:
        clean = " ".join(text.split())
        if not clean:
            raise EmptyText("texte vide : donner une phrase à dire.")
        self.engine.load()
        pcm = self.engine.synthesize(clean)
        rate = self.engine.sample_rate
        speech = Speech(text=clean, pcm=pcm, sample_rate=rate, engine=self.engine.name)
        # Le contrôle du silence porte sur la sortie brute du moteur : un moteur
        # muet ne doit pas être sauvé par la normalisation.
        if speech.silent:
            raise SilentSynthesis(
                f"{self.engine.name} a rendu un signal silencieux "
                f"(pic {speech.peak}/32768, {speech.duration_s:.2f} s) : "
                "aucun fichier écrit. Vérifier le modèle de synthèse."
            )
        try:
            mastered = apply_master(pcm, rate, style)
        except ValueError as exc:
            raise SilureError(str(exc)) from exc
        return Speech(
            text=clean,
            pcm=mastered.pcm,
            sample_rate=rate,
            engine=self.engine.name,
            style=mastered.style,
            gain_db=mastered.gain_db,
        )


def resolve_model_dir(model_dir: str | os.PathLike[str] | None = None) -> Path:
    """Ordre de résolution : argument, variable d'environnement, `models/` local."""
    if model_dir:
        return Path(model_dir)
    from_env = os.environ.get(MODEL_VAR_ENV)
    if from_env:
        return Path(from_env)
    return DEFAULT_MODEL_DIR


class PiperEngine:
    """Voix Piper (VITS) exécutée par sherpa-onnx, sur le processeur."""

    name = "piper"

    def __init__(self, model_dir: str | os.PathLike[str] | None = None, threads: int = 2) -> None:
        self.model_dir = resolve_model_dir(model_dir)
        self.threads = max(1, threads)
        self.sample_rate = 22_050
        self._tts = None

    def _paths(self) -> tuple[Path, Path, Path]:
        model = self.model_dir / "fr_FR-siwis-medium.onnx"
        tokens = self.model_dir / "tokens.txt"
        data = self.model_dir / "espeak-ng-data"
        return model, tokens, data

    def load(self) -> None:
        if self._tts is not None:
            return
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise MissingDependency(
                'sherpa-onnx n\'est pas installé. `uv pip install "silure[tts]"`.'
            ) from exc

        model, tokens, data = self._paths()
        missing = [p for p in (model, tokens, data) if not p.exists()]
        if missing:
            raise MissingModel(
                "modèle de synthèse absent : "
                + ", ".join(str(p) for p in missing)
                + f". Télécharger {MODEL_DOWNLOAD_HINT} et l'extraire dans "
                f"{self.model_dir}, ou indiquer --model / {MODEL_VAR_ENV}."
            )

        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(model),
                    tokens=str(tokens),
                    data_dir=str(data),
                ),
                num_threads=self.threads,
            ),
            max_num_sentences=1,
        )
        # sherpa-onnx >= 2 ne compile plus le frontend espeak-ng : d'où la borne.
        self._tts = sherpa_onnx.OfflineTts(config)
        self.sample_rate = int(self._tts.sample_rate) or self.sample_rate

    def synthesize(self, text: str) -> bytes:
        self.load()
        audio = self._tts.generate(text, sid=0, speed=1.0)
        return to_pcm16(audio.samples)

    def close(self) -> None:
        self._tts = None
