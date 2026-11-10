"""Point d'entrée `veyla` : transcrire un fichier, et dire du texte."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .asr import Transcriber, VeylaError, VoskEngine
from .fetch import prepare_reference
from .master import LOUDNESS_TARGETS, STYLES
from .players import play_file
from .setup import check as setup_check
from .setup import install as setup_install
from .tts import (
    EmptyText,
    PiperEngine,
    QwenCloneEngine,
    Speaker,
    load_consent,
    wav_duration,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veyla", description="Voix locale, sans serveur.")
    parser.add_argument("--version", action="version", version=f"veyla {__version__}")
    sub = parser.add_subparsers(dest="commande", required=True)

    trans = sub.add_parser("transcribe", help="transcrire un fichier WAV en texte")
    trans.add_argument("audio", help="fichier WAV mono PCM 16 bits")
    trans.add_argument(
        "--model",
        default=None,
        help="répertoire du modèle Vosk (défaut : models/ ou VEYLA_VOSK_MODEL)",
    )
    trans.add_argument("--json", action="store_true", help="sortie JSON")

    say = sub.add_parser("say", help="synthétiser du texte en WAV audible")
    say.add_argument("texte", nargs="+", help="phrase à dire")
    say.add_argument("--out", default="voix.wav", help="fichier WAV de sortie (défaut : voix.wav)")
    say.add_argument(
        "--model",
        default=None,
        help="répertoire du modèle Piper (défaut : models/ ou VEYLA_TTS_MODEL)",
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
        default="studio",
        help="traitement audio (défaut : studio ; radio : dense et présent ; chaud : doux)",
    )
    say.add_argument(
        "--rate",
        type=int,
        choices=(44100, 48000),
        default=None,
        help="fréquence du fichier écrit (défaut : celle du moteur ; 48000 pour la vidéo)",
    )
    say.add_argument(
        "--bits",
        type=int,
        choices=(16, 24),
        default=16,
        help="profondeur du fichier écrit (défaut : 16 ; 24 pour un logiciel de montage)",
    )
    say.add_argument(
        "--loudness",
        choices=tuple(LOUDNESS_TARGETS),
        default="podcast",
        help="cible de diffusion : podcast/apple -16, youtube/spotify -14, "
        "amazon -14 (-2 dBTP), broadcast -23 LUFS (défaut : podcast)",
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
        help="répertoire du modèle Qwen3-TTS (défaut : models/ ou VEYLA_CLONE_MODEL)",
    )
    clone.add_argument(
        "--ref-audio",
        required=True,
        help="référence à cloner : WAV, fichier audio ou vidéo, ou URL (veyla[url])",
    )
    clone.add_argument(
        "--ref-start",
        type=float,
        default=0.0,
        help="début du passage à garder dans la référence, en secondes (défaut : 0)",
    )
    clone.add_argument(
        "--isolate-voice",
        action="store_true",
        help="séparer la voix de la musique de fond avant le clonage (veyla[isolate])",
    )
    clone.add_argument(
        "--ref-duration",
        type=float,
        default=None,
        help="durée du passage à garder, en secondes (conseillé : 10 à 15)",
    )
    clone.add_argument(
        "--ref-text",
        default=None,
        help="transcription de l'audio de référence (recommandé pour la fidélité)",
    )
    clone.add_argument(
        "--consent",
        required=True,
        help='nom de la personne dont la voix est clonée ("Alice Martin"), '
        "ou fichier JSON de preuve (§8)",
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
        default="studio",
        help="traitement audio (défaut : studio ; radio : dense et présent ; chaud : doux)",
    )
    clone.add_argument(
        "--rate",
        type=int,
        choices=(44100, 48000),
        default=None,
        help="fréquence du fichier écrit (défaut : celle du moteur ; 48000 pour la vidéo)",
    )
    clone.add_argument(
        "--bits",
        type=int,
        choices=(16, 24),
        default=16,
        help="profondeur du fichier écrit (défaut : 16 ; 24 pour un logiciel de montage)",
    )
    clone.add_argument(
        "--loudness",
        choices=tuple(LOUDNESS_TARGETS),
        default="podcast",
        help="cible de diffusion : podcast/apple -16, youtube/spotify -14, "
        "amazon -14 (-2 dBTP), broadcast -23 LUFS (défaut : podcast)",
    )
    clone.add_argument("--json", action="store_true", help="sortie JSON")

    setup = sub.add_parser("setup", help="télécharger et installer les modèles")
    setup.add_argument(
        "--dir", default="models", help="dossier des modèles (défaut : models)"
    )
    setup.add_argument(
        "--clone",
        action="store_true",
        help="installer aussi Qwen3-TTS pour le clonage (2,4 Go, veyla[clone])",
    )
    setup.add_argument(
        "--no-check",
        action="store_true",
        help="ne pas faire l'essai final (synthèse puis transcription)",
    )

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
    except VeylaError as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 1

    if not result.text:
        print(f"veyla: {empty_message(result)}", file=sys.stderr)

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
        speaker = Speaker(tts_factory(args.model))
        speech = speaker.say(texte, style=args.style, loudness=args.loudness)
        path = speech.save(args.out, rate=args.rate, bits=args.bits)
        if args.play:
            joue = player(path)
    except EmptyText as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 2
    except VeylaError as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "text": speech.text,
                    "path": str(path),
                    "duration_s": speech.duration_s,
                    "sample_rate": args.rate or speech.sample_rate,
                    "bits": args.bits,
                    "peak": speech.peak,
                    "engine": speech.engine,
                    "style": speech.style,
                    "gain_db": round(speech.gain_db, 1),
                    "loudness": args.loudness,
                    "lufs": round(speech.lufs, 1),
                    "true_peak_dbtp": round(speech.true_peak_dbfs, 1),
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
            f"{path} - {speech.duration_s:.2f} s, "
            f"{args.rate or speech.sample_rate} Hz/{args.bits} bits, "
            f"{speech.lufs:.1f} LUFS, pic réel {speech.true_peak_dbfs:.1f} dBTP{style}{lecture}"
        )
    return 0


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clone(args, clone_factory, player, reference_factory) -> int:
    # Le consentement d'abord : sans preuve, rien n'est téléchargé ni converti.
    try:
        consent = load_consent(args.consent)
    except VeylaError as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="veyla-ref-") as workdir:
        try:
            reference = reference_factory(
                args.ref_audio,
                Path(workdir),
                start=args.ref_start,
                duration=args.ref_duration,
                isolate=args.isolate_voice,
            )
        except VeylaError as exc:
            print(f"veyla: {exc}", file=sys.stderr)
            return 1
        return _clone_from(args, clone_factory, player, consent, reference)


def _clone_from(args, clone_factory, player, consent, reference) -> int:
    ref_path = reference.path
    engine = clone_factory(
        args.model,
        ref_audio=ref_path,
        ref_text=args.ref_text,
        consent=consent,
    )
    texte = " ".join(args.texte)
    joue = None
    try:
        speech = Speaker(engine).say(texte, style=args.style, loudness=args.loudness)
        provenance = {
            "synthetic": True,
            "engine": speech.engine,
            "ref_source": reference.source,
            "ref_start_s": args.ref_start,
            "ref_duration_s": args.ref_duration,
            "ref_voice_isolated": args.isolate_voice,
            "ref_audio_sha256": _sha256_file(ref_path),
            "consent_mode": consent.mode,
            "consent_file": str(consent.path.resolve()) if consent.path else None,
            "consent_statement": consent.statement,
            "consent_sha256": consent.sha256,
            "consent_subject": consent.subject,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        speech = dataclasses.replace(speech, provenance=provenance)
        path = speech.save(args.out, rate=args.rate, bits=args.bits)
        sidecar = path.with_name(path.stem + ".provenance.json")
        sidecar.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if args.play:
            joue = player(path)
    except EmptyText as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 2
    except VeylaError as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "text": speech.text,
                    "path": str(path),
                    "provenance": str(sidecar),
                    "duration_s": speech.duration_s,
                    "sample_rate": args.rate or speech.sample_rate,
                    "bits": args.bits,
                    "peak": speech.peak,
                    "engine": speech.engine,
                    "style": speech.style,
                    "gain_db": round(speech.gain_db, 1),
                    "loudness": args.loudness,
                    "lufs": round(speech.lufs, 1),
                    "true_peak_dbtp": round(speech.true_peak_dbfs, 1),
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
            f"{path} - {speech.duration_s:.2f} s, "
            f"{args.rate or speech.sample_rate} Hz/{args.bits} bits, "
            f"{speech.lufs:.1f} LUFS, pic réel {speech.true_peak_dbfs:.1f} dBTP"
            f"{style}{lecture} (provenance : {sidecar})"
        )
    return 0


def _setup(args, installer, checker) -> int:
    names = ["vosk", "piper"] + (["qwen"] if args.clone else [])
    root = Path(args.dir)
    try:
        results = installer(names, root, log=lambda m: print(m, file=sys.stderr))
    except VeylaError as exc:
        print(f"veyla: {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(f"{result.name:6} {result.status:13} {result.path}")
    if args.no_check:
        return 0
    try:
        texte = checker(root)
    except VeylaError as exc:
        print(f"veyla: modèles installés, mais l'essai a échoué : {exc}", file=sys.stderr)
        return 1
    print(f"essai : synthèse puis transcription -> « {texte} »")
    return 0


def _play(args, player) -> int:
    path = Path(args.audio)
    if not path.is_file():
        print(f"veyla: fichier introuvable : {path}", file=sys.stderr)
        return 1
    try:
        duration, rate = wav_duration(path)
        joue = player(path)
    except VeylaError as exc:
        print(f"veyla: {exc}", file=sys.stderr)
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
        print(f"{path} - {duration:.2f} s, {rate} Hz, lu avec {joue}")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    engine_factory=VoskEngine,
    tts_factory=PiperEngine,
    clone_factory=QwenCloneEngine,
    reference_factory=prepare_reference,
    setup_installer=setup_install,
    setup_checker=setup_check,
    player=None,
) -> int:
    args = _build_parser().parse_args(argv)
    if args.commande == "transcribe":
        return _transcribe(args, engine_factory)
    if args.commande == "clone":
        return _clone(args, clone_factory, player or play_file, reference_factory)
    if args.commande == "setup":
        return _setup(args, setup_installer, setup_checker)
    if args.commande == "play":
        return _play(args, player or play_file)
    return _say(args, tts_factory, player or play_file)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
