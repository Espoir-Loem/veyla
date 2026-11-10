"""Préparation de l'audio de référence pour le clonage : URL, vidéo ou fichier local.

Une URL est téléchargée par yt-dlp ; tout ce qui n'est pas un WAV utilisable tel quel
est converti par ffmpeg en WAV mono 24 kHz, éventuellement découpé (`start`,
`duration`). Les deux outils sont des dépendances optionnelles (`veyla[url]`),
chargées seulement quand on en a besoin.

Ce que ce module ne fait pas : vérifier le consentement. La CLI l'exige avant
d'appeler `prepare_reference` : aucun téléchargement sans preuve.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .asr import MissingDependency, VeylaError
from .tts import MissingReference

__all__ = [
    "Reference",
    "convert_audio",
    "download_audio",
    "is_url",
    "isolate_voice",
    "prepare_reference",
]

REFERENCE_RATE = 24_000
"""Fréquence attendue par Qwen3-TTS ; convertir une fois évite un rééchantillonnage."""

REFERENCE_FILTERS = (
    "highpass=f=80,adeclick,afftdn=nr=12:nf=-40,loudnorm=I=-20:TP=-2:LRA=11"
)
"""Nettoyage de la référence : grondement < 80 Hz retiré, clics de bouche réparés
(`adeclick`), souffle réduit de 12 dB
au plus (léger, pour ne pas abîmer le timbre à cloner), niveau ramené à -20 LUFS.
Le clone reproduit ce qu'il entend : une référence propre donne un clone propre."""


@dataclass(frozen=True)
class Reference:
    """Un WAV de référence prêt pour le moteur, et d'où il vient."""

    path: Path
    source: str


def is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def download_audio(url: str, workdir: Path) -> Path:
    """Télécharge la meilleure piste audio de `url` dans `workdir`."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise MissingDependency(
            'yt-dlp n\'est pas installé. `uv pip install -e ".[url]"`.'
        ) from exc
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as exc:  # yt-dlp lève ses propres types, tous à présenter
        raise VeylaError(f"téléchargement impossible ({url}) : {exc}") from exc
    if not path.is_file():
        raise VeylaError(f"téléchargement sans fichier audio : {url}")
    return path


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise MissingDependency(
            'ffmpeg introuvable. Installer ffmpeg, ou `uv pip install -e ".[url]"`.'
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def convert_audio(src: Path, dst: Path, start: float, duration: float | None) -> None:
    """Convertit `src` (audio ou vidéo) en WAV PCM 16 bits mono 24 kHz."""
    command = [_ffmpeg(), "-nostdin", "-loglevel", "error", "-y"]
    if start:
        command += ["-ss", f"{start}"]
    command += ["-i", str(src)]
    if duration:
        command += ["-t", f"{duration}"]
    command += ["-vn", "-af", REFERENCE_FILTERS, "-ac", "1", "-ar", str(REFERENCE_RATE)]
    command += ["-c:a", "pcm_s16le", str(dst)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not dst.is_file():
        detail = result.stderr.strip().splitlines()[-1:] or ["sans message"]
        raise MissingReference(f"conversion impossible de {src} : {detail[0]}")


def isolate_voice(src: Path, workdir: Path) -> Path:
    """Sépare la voix du reste (musique, ambiance) avec Demucs `htdemucs`.

    Lancé dans un processus à part : le modèle (~80 Mo, téléchargé au premier
    usage) et ~1 Go de RAM sont rendus dès la fin de la séparation.
    Mesuré : un accord de fond baisse de 13 à 43 dB selon la note, et Vosk
    retrouve « ceci est » que la musique lui faisait entendre « c'est c'est ».
    """
    if importlib.util.find_spec("demucs") is None:
        raise MissingDependency(
            'demucs n\'est pas installé. `uv pip install -e ".[isolate]"`.'
        )
    out = workdir / "separation"
    command = [
        sys.executable, "-m", "demucs.separate", "--two-stems", "vocals",
        "-n", "htdemucs", "-d", "cpu", "-o", str(out), str(src),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    vocals = out / "htdemucs" / src.stem / "vocals.wav"
    if result.returncode != 0 or not vocals.is_file():
        detail = result.stderr.strip().splitlines()[-1:] or ["sans message"]
        raise VeylaError(f"séparation de la voix impossible ({src}) : {detail[0]}")
    return vocals


def prepare_reference(
    source: str,
    workdir: Path,
    *,
    start: float = 0.0,
    duration: float | None = None,
    isolate: bool = False,
    downloader: Callable[[str, Path], Path] = download_audio,
    converter: Callable[[Path, Path, float, float | None], None] = convert_audio,
    isolator: Callable[[Path, Path], Path] = isolate_voice,
) -> Reference:
    """Rend un WAV de référence à partir d'une URL, d'une vidéo ou d'un fichier audio.

    Avec `isolate`, la voix est séparée de la musique sur la source brute (pleine
    bande, stéréo : ce que Demucs sépare le mieux), avant découpe et nettoyage.
    """
    workdir = Path(workdir)
    if is_url(source):
        src = downloader(source, workdir)
    else:
        src = Path(source)
        if not src.is_file():
            raise MissingReference(f"audio de référence introuvable : {src}")
        if src.suffix.lower() == ".wav" and not start and not duration and not isolate:
            return Reference(path=src, source=source)
    if isolate:
        src = isolator(src, workdir)
    dst = workdir / "reference.wav"
    converter(src, dst, start, duration)
    return Reference(path=dst, source=source)
