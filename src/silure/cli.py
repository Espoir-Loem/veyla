"""Point d'entrée `silure` : transcrire un fichier, et dire du texte."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .asr import SilureError, Transcriber, VoskEngine
from .master import STYLES
from .players import play_file
from .tts import (
    EmptyText,
    PiperEngine,
    QwenCloneEngine,
    Speaker,
    load_consent,
    wav_duration,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="silure", description="Voix locale, sans serveur.")
    parser.add_argument("--version", action="version", version=f"silure {__version__}")
    sub = parser.add_subparsers(dest="commande", required=True)

    trans = sub.add_parser("transcribe", help="transcrire un fichier WAV en texte")
    trans.add_argument("audio", help="fichier WAV mono PCM 16 bits")
    trans.add_argument(
        "--model",
        default=None,
        help="répertoire du modèle Vosk (défaut : models/ ou SILURE_VOSK_MODEL)",
    )
    trans.add_argument("--json", action="store_true", help="sortie JSON")

    say = sub.add_parser("say", help="synthétiser du texte en WAV audible")
    say.add_argument("texte", nargs="+", help="phrase à dire")
    say.add_argument("--out", default="voix.wav", help="fichier WAV de sortie (défaut : voix.wav)")
    say.add_argument(
        "--model",
        default=None,
        help="répertoire du modèle Piper (défaut : models/ ou SILURE_TTS_MODEL)",
    )
    say.add_argument(
        "--play",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="lire l'audio après l'écriture (défaut : oui ; --no-play : écrire seulement)",
    )
    say.add_argument(
        "--style",
        choices=STYLES,
        default="podcast",
        help="traitement audio (défaut : podcast)",
    )
    say.add_argument("--json", action="store_true", help="sortie JSON")

    clone = sub.add_parser("clone", help="cloner une voix à partir d'un audio de référence")
    clone.add_argument("texte", nargs="+", help="phrase à dire avec la voix clonée")
    clone.add_argument(
        "--out", default="clone.wav", help="fichier WAV de sortie (défaut : clone.wav)"
    )
    clone.add_argument(
        "--model",
        default=None,
        help="répertoire du modèle Qwen3-TTS (défaut : models/ ou SILURE_CLONE_MODEL)",
    )
    clone.add_argument("--ref-audio", required=True, help="WAV de référence à cloner")
    clone.add_argument(
        "--ref-text",
        default=None,
        help="transcription de l'audio de référence (recommandé pour la fidélité)",
    )
    clone.add_argument(
        "--consent",
        required=True,
        help="fichier JSON de preuve de consentement (§8)",
    )
    clone.add_argument(
        "--play",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="lire l'audio après l'écriture (défaut : oui ; --no-play : écrire seulement)",
    )
    clone.add_argument(
        "--style",
        choices=STYLES,
        default="podcast",
        help="traitement audio (défaut : podcast)",
    )
    clone.add_argument("--json", action="store_true", help="sortie JSON")

    play = sub.add_parser("play", help="lire un fichier WAV existant")
    play.add_argument("audio", help="fichier WAV à lire")
    play.add_argument("--json", action="store_true", help="sortie JSON")
    return parser


def empty_message(result) -> str:
    """Pourquoi le texte est vide : fichier muet, ou signal sans parole reconnue."""
    niveau = f"pic {result.peak}/32768, {result.duration_s:.1f} s"
    if result.silent:
        return (
            f"aucune parole : l'audio est silencieux ({niveau}). "
            "Vérifier l'entrée micro et le niveau d'enregistrement."
        )
    return (
        f"aucun mot reconnu ({niveau}) : le fichier contient un signal, mais pas de "
        "parole que ce modèle comprenne. Vérifier la langue du modèle et la qualité "
        "de la capture."
    )


def _transcribe(args, engine_factory) -> int:
    try:
        result = Transcriber(engine_factory(args.model)).transcribe_file(args.audio)
    except SilureError as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 1

    if not result.text:
        print(f"silure: {empty_message(result)}", file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                {
                    "text": result.text,
                    "duration_s": result.duration_s,
                    "sample_rate": result.sample_rate,
                    "engine": result.engine,
                    "peak": result.peak,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(result.text)
    return 0


def _say(args, tts_factory, player) -> int:
    texte = " ".join(args.texte)
    joue = None
    try:
        speech = Speaker(tts_factory(args.model)).say(texte, style=args.style)
        path = speech.save(args.out)
        if args.play:
            joue = player(path)
    except EmptyText as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 2
    except SilureError as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "text": speech.text,
                    "path": str(path),
                    "duration_s": speech.duration_s,
                    "sample_rate": speech.sample_rate,
                    "peak": speech.peak,
                    "engine": speech.engine,
                    "style": speech.style,
                    "gain_db": round(speech.gain_db, 1),
                    "played": joue is not None,
                    "player": joue,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        lecture = f", lu avec {joue}" if joue else ""
        style = f", style {speech.style}" if speech.style != "neutre" else ""
        print(
            f"{path} — {speech.duration_s:.2f} s, {speech.sample_rate} Hz, "
            f"pic {speech.peak}/32768{style}{lecture}"
        )
    return 0


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clone(args, clone_factory, player) -> int:
    try:
        consent = load_consent(args.consent)
    except SilureError as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 1

    ref_path = Path(args.ref_audio)
    if not ref_path.is_file():
        print(f"silure: audio de référence introuvable : {ref_path}", file=sys.stderr)
        return 1

    engine = clone_factory(
        args.model,
        ref_audio=ref_path,
        ref_text=args.ref_text,
        consent=consent,
    )
    texte = " ".join(args.texte)
    joue = None
    try:
        speech = Speaker(engine).say(texte, style=args.style)
        provenance = {
            "synthetic": True,
            "engine": speech.engine,
            "ref_audio": str(ref_path.resolve()),
            "ref_audio_sha256": _sha256_file(ref_path),
            "consent_file": str(Path(args.consent).resolve()),
            "consent_sha256": consent.sha256,
            "consent_subject": consent.subject,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        speech = dataclasses.replace(speech, provenance=provenance)
        path = speech.save(args.out)
        sidecar = path.with_name(path.stem + ".provenance.json")
        sidecar.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if args.play:
            joue = player(path)
    except EmptyText as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 2
    except SilureError as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "text": speech.text,
                    "path": str(path),
                    "provenance": str(sidecar),
                    "duration_s": speech.duration_s,
                    "sample_rate": speech.sample_rate,
                    "peak": speech.peak,
                    "engine": speech.engine,
                    "style": speech.style,
                    "gain_db": round(speech.gain_db, 1),
                    "played": joue is not None,
                    "player": joue,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        lecture = f", lu avec {joue}" if joue else ""
        style = f", style {speech.style}" if speech.style != "neutre" else ""
        print(
            f"{path} — {speech.duration_s:.2f} s, {speech.sample_rate} Hz, "
            f"pic {speech.peak}/32768{style}{lecture} (provenance : {sidecar})"
        )
    return 0


def _play(args, player) -> int:
    path = Path(args.audio)
    if not path.is_file():
        print(f"silure: fichier introuvable : {path}", file=sys.stderr)
        return 1
    try:
        duration, rate = wav_duration(path)
        joue = player(path)
    except SilureError as exc:
        print(f"silure: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "path": str(path),
                    "duration_s": duration,
                    "sample_rate": rate,
                    "player": joue,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{path} — {duration:.2f} s, {rate} Hz, lu avec {joue}")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    engine_factory=VoskEngine,
    tts_factory=PiperEngine,
    clone_factory=QwenCloneEngine,
    player=None,
) -> int:
    args = _build_parser().parse_args(argv)
    if args.commande == "transcribe":
        return _transcribe(args, engine_factory)
    if args.commande == "clone":
        return _clone(args, clone_factory, player or play_file)
    if args.commande == "play":
        return _play(args, player or play_file)
    return _say(args, tts_factory, player or play_file)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
