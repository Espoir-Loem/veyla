"""Transcription d'un fichier audio, sur l'appareil.

Le module ne dépend que de la bibliothèque standard ; le modèle Vosk est une
dépendance optionnelle, chargée seulement quand on l'utilise.

Ce que ce module ne fait pas : découper un flux, synthétiser une voix, reconnaître un
locuteur. La v1 produit du texte à partir d'un audio déjà présent sur la machine.
"""

from __future__ import annotations

import array
import json
import os
import wave
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "SAMPLE_RATE",
    "MissingDependency",
    "MissingModel",
    "VeylaError",
    "Transcription",
    "Transcriber",
    "UnsupportedAudio",
    "VoskEngine",
    "read_wav",
    "resample_pcm16",
    "transcribe",
]

SAMPLE_RATE = 16_000
"""Fréquence attendue par les modèles Vosk. Toute autre fréquence est ramenée ici."""

MODEL_VAR_ENV = "VEYLA_VOSK_MODEL"
MODEL_DOWNLOAD_HINT = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"


class VeylaError(Exception):
    """Erreur destinée à l'utilisateur : message lisible, pas de traceback."""


class UnsupportedAudio(VeylaError):
    """Le fichier n'est pas un WAV PCM mono 16 bits."""


class MissingDependency(VeylaError):
    """Le backend demandé n'est pas installé."""


class MissingModel(VeylaError):
    """Le répertoire de modèle est absent ou incomplet."""


@dataclass(frozen=True)
class Transcription:
    """Résultat d'une transcription, avec ce qu'il faut pour l'interpréter.

    `peak` est l'amplitude maximale du signal, en valeur absolue sur 32768 : il permet
    de distinguer un fichier muet d'un fichier où le modèle n'a simplement rien reconnu.
    """

    text: str
    duration_s: float
    sample_rate: int
    engine: str
    peak: int = 0

    @property
    def silent(self) -> bool:
        return self.peak <= 1


def peak_amplitude(frames: bytes) -> int:
    """Amplitude maximale d'un flux PCM 16 bits, en valeur absolue (0 à 32768)."""
    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
    return max((abs(value) for value in samples), default=0)


def read_wav(path: str | os.PathLike[str]) -> tuple[bytes, int]:
    """Lit un WAV PCM 16 bits mono et rend (échantillons bruts, fréquence).

    Refuse explicitement ce qui n'est pas mesurable sans conversion silencieuse :
    un WAV stéréo ou 8/24/32 bits doit être converti par l'appelant, pas deviné ici.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise UnsupportedAudio(f"{path} : WAV illisible ({exc})") from exc
    except FileNotFoundError as exc:
        raise UnsupportedAudio(f"{path} : fichier absent") from exc

    if channels != 1:
        raise UnsupportedAudio(
            f"{path} : {channels} canaux, seul le mono est accepté. "
            "Convertir en mono PCM 16 bits avant de transcrire."
        )
    if width != 2:
        raise UnsupportedAudio(
            f"{path} : {width * 8} bits par échantillon, seul le PCM 16 bits est accepté."
        )
    if rate <= 0:
        raise UnsupportedAudio(f"{path} : fréquence d'échantillonnage invalide ({rate}).")
    return frames, rate


def resample_pcm16(frames: bytes, source_rate: int, target_rate: int) -> bytes:
    """Ramène des échantillons PCM 16 bits à `target_rate`.

    Réduction : moyenne glissante de largeur `source_rate // target_rate` avant
    décimation - un filtre passe-bas du premier ordre, pas une décimation nue, dont la
    réponse est médiocre près de la bande passante mais qui empêche le repliement des
    fréquences hautes dans la bande utile.

    Augmentation : interpolation linéaire. Ce n'est pas un reconstructeur sinc : les
    harmoniques au-delà de la moitié de la fréquence source ne sont pas recréées.
    """
    if source_rate == target_rate or not frames:
        return frames
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("fréquence d'échantillonnage invalide")

    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - (len(frames) % 2)])

    if source_rate > target_rate:
        width = max(1, source_rate // target_rate)
        filtered = array.array("h", bytes(2 * len(samples)))
        running = 0
        for index, value in enumerate(samples):
            running += value
            if index >= width:
                running -= samples[index - width]
            filtered[index] = int(running / min(index + 1, width))
        samples = filtered

    ratio = source_rate / target_rate
    count = int(len(samples) * target_rate / source_rate)
    out = array.array("h", bytes(2 * count))
    for index in range(count):
        position = index * ratio
        left = int(position)
        right = min(left + 1, len(samples) - 1)
        weight = position - left
        out[index] = int(samples[left] * (1.0 - weight) + samples[right] * weight)
    return out.tobytes()


class Transcriber:
    """Applique un backend à des fichiers, sans connaître son implémentation."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def transcribe_file(self, path: str | os.PathLike[str]) -> Transcription:
        frames, rate = read_wav(path)
        pcm = resample_pcm16(frames, rate, SAMPLE_RATE)
        self.engine.load()
        text = self.engine.transcribe(pcm, SAMPLE_RATE)
        duration = len(frames) / 2 / rate
        return Transcription(
            text=text.strip(),
            duration_s=duration,
            sample_rate=SAMPLE_RATE,
            engine=self.engine.name,
            peak=peak_amplitude(pcm),
        )


class VoskEngine:
    """Backend Vosk. Le modèle est chargé une fois, à la première transcription."""

    name = "vosk"

    def __init__(self, model_dir: str | os.PathLike[str] | None = None) -> None:
        self.model_dir = resolve_model_dir(model_dir)
        self._model = None
        self._vosk = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            import vosk  # noqa: F401  (import différé : dépendance optionnelle)
        except ImportError as exc:
            raise MissingDependency(
                'Vosk n\'est pas installé. `pip install "veyla[vosk]"`.'
            ) from exc
        if not Path(self.model_dir).is_dir():
            raise MissingModel(
                f"modèle absent : {self.model_dir}. Télécharger {MODEL_DOWNLOAD_HINT} "
                f"et l'extraire, ou indiquer --model / {MODEL_VAR_ENV}."
            )
        self._vosk = vosk
        # Vosk écrit son journal de chargement sur stderr : une CLI qui transcrit
        # silencieusement ne doit pas noyer son résultat. VEYLA_VOSK_LOG=0 le rétablit.
        vosk.SetLogLevel(int(os.environ.get("VEYLA_VOSK_LOG", "-1")))
        self._model = vosk.Model(str(self.model_dir))

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        self.load()
        recognizer = self._vosk.KaldiRecognizer(self._model, sample_rate)
        recognizer.AcceptWaveform(pcm)
        return json.loads(recognizer.FinalResult()).get("text", "")

    def close(self) -> None:
        self._model = None


def resolve_model_dir(model_dir: str | os.PathLike[str] | None = None) -> Path:
    """Ordre de résolution : argument, variable d'environnement, `models/` local."""
    if model_dir:
        return Path(model_dir)
    from_env = os.environ.get(MODEL_VAR_ENV)
    if from_env:
        return Path(from_env)
    return Path("models") / "vosk-model-small-fr-0.22"


def transcribe(
    path: str | os.PathLike[str], model_dir: str | os.PathLike[str] | None = None
) -> Transcription:
    """Raccourci : transcrit `path` avec Vosk et rend un `Transcription`."""
    return Transcriber(VoskEngine(model_dir)).transcribe_file(path)
