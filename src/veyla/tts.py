"""Synthèse vocale locale : du texte vers un WAV audible.

Le module ne dépend que de la bibliothèque standard ; le moteur neuronal
(sherpa-onnx + modèle Piper) est une dépendance optionnelle, chargée seulement
quand on s'en sert.

Contrat : `Speaker.say` refuse de rendre un fichier muet. Une panne du moteur
lève `SilentSynthesis` au lieu d'écrire un WAV de zéros que personne ne remarque.
"""

from __future__ import annotations

import array
import hashlib
import json
import os
import random
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .asr import (
    MissingDependency,
    MissingModel,
    VeylaError,
    peak_amplitude,
    read_wav,
)
from .master import master as apply_master

__all__ = [
    "ConsentProof",
    "EmptyText",
    "MissingConsent",
    "MissingReference",
    "PiperEngine",
    "QwenCloneEngine",
    "SilentSynthesis",
    "Speaker",
    "Speech",
    "TtsEngine",
    "load_consent",
    "resolve_clone_model_dir",
    "resolve_model_dir",
    "wav_duration",
    "to_pcm16",
    "write_wav",
]

MODEL_VAR_ENV = "VEYLA_TTS_MODEL"
MODEL_DOWNLOAD_HINT = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "vits-piper-fr_FR-siwis-medium.tar.bz2"
)
DEFAULT_MODEL_DIR = Path("models") / "vits-piper-fr_FR-siwis-medium"
MODEL_VAR_ENV_CLONE = "VEYLA_CLONE_MODEL"
MODEL_DOWNLOAD_HINT_CLONE = "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base"
DEFAULT_MODEL_DIR_CLONE = Path("models") / "Qwen3-TTS-12Hz-0.6B-Base"
SILENCE_PEAK = 1
"""En dessous ou à ce niveau, un PCM 16 bits ne porte aucun son exploitable."""


class EmptyText(VeylaError):
    """Le texte à dire est vide : rien à synthétiser."""


class SilentSynthesis(VeylaError):
    """Le moteur a rendu un signal muet : le fichier serait sans son."""


class MissingConsent(VeylaError):
    """Aucune preuve de consentement pour le clonage : la capacité reste fermée."""


class MissingReference(VeylaError):
    """Audio de référence absent ou illisible pour le clonage."""


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
        raise VeylaError(f"ce fichier n'est pas un WAV lisible : {path} ({exc})") from exc
    if rate <= 0:
        raise VeylaError(f"WAV invalide, fréquence nulle : {path}")
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


def export_wav(
    path: str | os.PathLike[str],
    pcm: bytes,
    sample_rate: int,
    out_rate: int | None = None,
    bits: int = 16,
) -> Path:
    """Écrit le PCM 16 bits en WAV mono, à la fréquence et la profondeur demandées.

    48 kHz / 24 bits est le format d'échange des logiciels de montage (MAO,
    vidéo). Le rééchantillonnage est fait en flottant ; en 16 bits, un dither
    TPDF masque l'erreur de quantification au lieu de la laisser en distorsion.
    Ce que ça ne fait pas : ajouter de la précision. Le moteur rend du 16 bits ;
    le 24 bits évite seulement une perte de plus dans la chaîne de montage.
    """
    if bits not in (16, 24):
        raise VeylaError(f"profondeur non prise en charge : {bits} bits (16 ou 24)")
    rate = out_rate or sample_rate
    if rate == sample_rate and bits == 16:
        return write_wav(path, pcm, sample_rate)
    from .master import resample, samples_of

    values = resample(samples_of(pcm), sample_rate, rate)
    if bits == 16:
        rng = random.Random(0)  # reproductible : même entrée, même fichier
        values = [x + rng.random() - rng.random() for x in values]
        data = array.array("h", (max(-32768, min(32767, round(x))) for x in values)).tobytes()
    else:
        out = bytearray()
        for x in values:
            v = max(-8388608, min(8388607, round(x * 256)))
            out += (v & 0xFFFFFF).to_bytes(3, "little")
        data = bytes(out)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(bits // 8)
        handle.setframerate(rate)
        handle.writeframes(data)
    with wave.open(str(target)) as check:
        if check.getframerate() != rate or check.getnframes() != len(values):
            raise VeylaError(f"{target} : en-tête incohérent après écriture")
    return target


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
        raise VeylaError(f"{target} : en-tête incohérent après écriture")
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
    lufs: float = -70.0
    true_peak_dbfs: float = -90.3
    provenance: dict[str, Any] | None = None

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / 2 / self.sample_rate

    @property
    def peak(self) -> int:
        return peak_amplitude(self.pcm)

    @property
    def silent(self) -> bool:
        return self.peak <= SILENCE_PEAK

    def save(
        self, path: str | os.PathLike[str], rate: int | None = None, bits: int = 16
    ) -> Path:
        return export_wav(path, self.pcm, self.sample_rate, rate, bits)


class Speaker:
    """Orchestre texte → audio, sans connaître l'implémentation du moteur."""

    def __init__(self, engine: TtsEngine) -> None:
        self.engine = engine

    def say(self, text: str, style: str = "studio", loudness: str = "podcast") -> Speech:
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
            mastered = apply_master(pcm, rate, style, loudness)
        except ValueError as exc:
            raise VeylaError(str(exc)) from exc
        return Speech(
            text=clean,
            pcm=mastered.pcm,
            sample_rate=rate,
            engine=self.engine.name,
            style=mastered.style,
            gain_db=mastered.gain_db,
            lufs=mastered.lufs,
            true_peak_dbfs=mastered.true_peak_dbfs,
        )


def resolve_model_dir(model_dir: str | os.PathLike[str] | None = None) -> Path:
    """Ordre de résolution : argument, variable d'environnement, `models/` local."""
    if model_dir:
        return Path(model_dir)
    from_env = os.environ.get(MODEL_VAR_ENV)
    if from_env:
        return Path(from_env)
    return DEFAULT_MODEL_DIR


@dataclass(frozen=True)
class ConsentProof:
    """Preuve locale de consentement pour le clonage (§8)."""

    path: Path
    sha256: str
    subject: str
    granted_by: str
    statement: str


def load_consent(path: str | os.PathLike[str] | None) -> ConsentProof:
    """Lit et valide une preuve de consentement JSON. Lève `MissingConsent` sinon."""
    if not path:
        raise MissingConsent(
            "consentement requis pour le clonage : fournir --consent <fichier.json>."
        )
    proof_path = Path(path)
    if not proof_path.is_file():
        raise MissingConsent(f"preuve de consentement introuvable : {proof_path}")
    try:
        raw = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MissingConsent(
            f"preuve de consentement illisible ({proof_path}) : {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise MissingConsent("preuve de consentement : objet JSON attendu.")
    required = ("subject", "granted_by", "statement")
    values: dict[str, str] = {}
    for key in required:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MissingConsent(
                f"preuve de consentement incomplète : champ '{key}' manquant ou vide."
            )
        values[key] = value.strip()
    digest = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    return ConsentProof(
        path=proof_path,
        sha256=digest,
        subject=values["subject"],
        granted_by=values["granted_by"],
        statement=values["statement"],
    )


def resolve_clone_model_dir(model_dir: str | os.PathLike[str] | None = None) -> Path:
    """Ordre de résolution : argument, variable d'environnement, `models/` local."""
    if model_dir:
        return Path(model_dir)
    from_env = os.environ.get(MODEL_VAR_ENV_CLONE)
    if from_env:
        return Path(from_env)
    return DEFAULT_MODEL_DIR_CLONE


class QwenCloneEngine:
    """Clonage zero-shot français via Qwen3-TTS, sur le processeur.

    La preuve de consentement est exigée pour charger le modèle : sans elle, la
    capacité reste fermée (§8). L'audio de référence doit exister sur le disque.
    """

    name = "qwen-clone"

    def __init__(
        self,
        model_dir: str | os.PathLike[str] | None = None,
        ref_audio: str | os.PathLike[str] | None = None,
        ref_text: str | None = None,
        consent: ConsentProof | None = None,
        device: str = "cpu",
        dtype: str = "bfloat16",
    ) -> None:
        self.model_dir = resolve_clone_model_dir(model_dir)
        self.ref_audio = Path(ref_audio) if ref_audio else None
        self.ref_text = " ".join(ref_text.split()) if ref_text else None
        self.consent = consent
        self.device = device
        self.dtype = dtype
        self.sample_rate = 24_000
        self._model = None

    def _check_inputs(self) -> None:
        if self.consent is None:
            raise MissingConsent(
                "consentement requis pour le clonage : fournir --consent <fichier.json>."
            )
        if self.ref_audio is None or not self.ref_audio.is_file():
            raise MissingReference(
                "audio de référence introuvable : "
                + (str(self.ref_audio) if self.ref_audio else "(aucun)")
                + ". Fournir --ref-audio <fichier.wav>."
            )

    def load(self) -> None:
        if self._model is not None:
            return
        self._check_inputs()
        try:
            import qwen_tts  # noqa: F401
        except ImportError as exc:
            raise MissingDependency(
                'qwen-tts n\'est pas installé. `uv pip install "veyla[clone]"`.'
            ) from exc

        model_file = self.model_dir / "model.safetensors"
        config_file = self.model_dir / "config.json"
        missing = [p for p in (model_file, config_file) if not p.exists()]
        if missing:
            raise MissingModel(
                "modèle de clonage absent : "
                + ", ".join(str(p) for p in missing)
                + f". Télécharger {MODEL_DOWNLOAD_HINT_CLONE} dans "
                f"{self.model_dir}, ou indiquer --model / {MODEL_VAR_ENV_CLONE}."
            )

        import torch

        self._model = qwen_tts.Qwen3TTSModel.from_pretrained(
            str(self.model_dir),
            device_map=self.device,
            dtype=getattr(torch, self.dtype),
        )
        try:
            sr = getattr(self._model, "sample_rate", None)
            if sr:
                self.sample_rate = int(sr)
        except (TypeError, ValueError):
            pass

    def synthesize(self, text: str) -> bytes:
        self.load()
        # Sans transcription de la référence, Qwen refuse le mode ICL : on se
        # rabat sur l'empreinte vocale seule (moins fidèle, mais pas d'échec).
        try:
            wavs, sr = self._model.generate_voice_clone(
                text=text,
                language="French",
                ref_audio=str(self.ref_audio),
                ref_text=self.ref_text,
                x_vector_only_mode=self.ref_text is None,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            raise VeylaError(f"échec du moteur de clonage : {exc}") from exc
        if not wavs:
            raise SilentSynthesis("le moteur de clonage n'a rendu aucun audio.")
        self.sample_rate = int(sr) or self.sample_rate
        return to_pcm16(wavs[0])

    def close(self) -> None:
        self._model = None


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
        except ModuleNotFoundError as exc:
            raise MissingDependency(
                'sherpa-onnx n\'est pas installé. `uv pip install "veyla[tts]"`.'
            ) from exc
        except ImportError as exc:
            # Paquet présent mais bibliothèque native manquante (libonnxruntime,
            # fournie par sherpa-onnx-core) : le dire, au lieu de « pas installé ».
            raise MissingDependency(
                f"sherpa-onnx est installé mais ne se charge pas : {exc}. "
                'Réinstaller : `uv pip install -e ".[tts]"`.'
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
