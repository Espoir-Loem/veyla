"""Exécution d'une campagne de mesure STT et production du manifeste.

    python -m harness.runner --corpus eval/corpora/general --backend dummy

Sortie : un rapport JSON (manifeste de reproductibilité) et un tableau lisible.
Un rapport dont `mesure_valide` est false n'est pas un résultat.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import metrics, probes
from .backends import REGISTRY, build_backend

__all__ = ["Utterance", "load_corpus", "run"]

MANIFEST_NAME = "manifest.tsv"
COLUMNS = ("utt_id", "audio", "transcript", "domaine", "micro", "bruit_db")


@dataclass
class Utterance:
    utt_id: str
    audio: Path
    transcript: str
    domaine: str = "non-rens."
    micro: str = "non-rens."
    bruit_db: str = "non-rens."
    extras: dict = field(default_factory=dict)


def _from_manifest(corpus_dir: Path) -> list[Utterance]:
    rows: list[Utterance] = []
    # `newline` par défaut : un manifeste édité sous Windows finit en CRLF, et le \r
    # se collerait aux noms de colonne comme aux transcriptions.
    with (corpus_dir / MANIFEST_NAME).open(encoding="utf-8") as handle:
        header = [column.strip() for column in handle.readline().rstrip("\n").split("\t")]
        unknown = [c for c in header if c not in COLUMNS]
        if unknown:
            raise SystemExit(f"{MANIFEST_NAME} : colonnes inconnues {unknown}")
        for lineno, line in enumerate(handle, start=2):
            if not line.strip():
                continue
            fields = [column.strip() for column in line.rstrip("\n").split("\t")]
            if len(fields) < 3:
                raise SystemExit(f"{MANIFEST_NAME} ligne {lineno} : 3 colonnes minimum requises")
            record = dict(zip(header, fields))
            rows.append(
                Utterance(
                    utt_id=record["utt_id"],
                    audio=corpus_dir / record["audio"],
                    transcript=record["transcript"],
                    domaine=record.get("domaine", "non-rens."),
                    micro=record.get("micro", "non-rens."),
                    bruit_db=record.get("bruit_db", "non-rens."),
                )
            )
    return rows


def _from_pairs(corpus_dir: Path) -> list[Utterance]:
    """Mode sans manifeste : `x.wav` accompagné de `x.txt` contenant la référence."""
    rows: list[Utterance] = []
    for audio in sorted(corpus_dir.glob("*.wav")):
        text_file = audio.with_suffix(".txt")
        if not text_file.exists():
            raise SystemExit(f"référence manquante pour {audio.name} (attendu {text_file.name})")
        rows.append(
            Utterance(
                utt_id=audio.stem,
                audio=audio,
                transcript=text_file.read_text(encoding="utf-8").strip(),
            )
        )
    return rows


def load_corpus(corpus_dir: Path) -> list[Utterance]:
    if not corpus_dir.is_dir():
        raise SystemExit(f"corpus introuvable : {corpus_dir}")
    rows = _from_manifest(corpus_dir) if (corpus_dir / MANIFEST_NAME).exists() else _from_pairs(corpus_dir)
    if not rows:
        raise SystemExit(f"aucun énoncé dans {corpus_dir} : rien à mesurer")
    missing = [r.utt_id for r in rows if not r.audio.exists()]
    if missing:
        raise SystemExit(f"{len(missing)} fichier(s) audio manquant(s), ex. {missing[:5]}")
    return rows


def run(backend_name: str, corpus_dir: Path, model_dir: Path | None,
        warmups: int, limit: int | None) -> dict:
    backend = build_backend(backend_name, model_dir)

    utterances = load_corpus(corpus_dir)
    if limit:
        utterances = utterances[:limit]

    load_started = time.perf_counter()
    backend.load()
    load_seconds = time.perf_counter() - load_started

    rows: list[dict] = []
    for index, utt in enumerate(utterances, start=1):
        started = time.perf_counter()
        hypothesis = backend.transcribe(utt.audio)
        latency_ms = (time.perf_counter() - started) * 1000
        if index <= warmups:
            latency_ms = None
        duration = probes.audio_duration_s(utt.audio)
        row = {
            "utt_id": utt.utt_id,
            "domaine": utt.domaine,
            "micro": utt.micro,
            "bruit_db": utt.bruit_db,
            "audio_duration_s": duration,
            "latency_ms": round(latency_ms, 3) if latency_ms is not None else None,
            "warmup_excluded": index <= warmups,
            "reference": utt.transcript,
            "hypothesis": hypothesis,
            "wer": metrics.wer(utt.transcript, hypothesis),
            "cer": metrics.cer(utt.transcript, hypothesis),
        }
        rows.append(row)
        print(f"[{index}/{len(utterances)}] {utt.utt_id}", file=sys.stderr)

    # Les énoncés de chauffe sortent aussi du calcul du WER agrégé : ils fausseraient
    # taux et RTF sans rien apprendre sur le comportement en production.
    measured = [r for r in rows if not r["warmup_excluded"]]
    timings = [r for r in measured if r["latency_ms"] is not None and r["audio_duration_s"]]

    try:
        memory = probes.peak_rss_bytes() if getattr(backend, "inprocess", False) else None
        memory_reason = None
        if memory is None and not getattr(backend, "inprocess", False):
            memory_reason = "backend hors processus : le pic mémoire du harnais ne couvre pas le modèle"
    except probes.PeakRssError as exc:
        memory, memory_reason = None, str(exc)

    model_files = []
    for path in getattr(backend, "model_files", []) or []:
        if Path(path).exists():
            model_files.append({"path": str(path), "sha256": probes.sha256(Path(path)),
                                "bytes": Path(path).stat().st_size})

    validation_only = backend_name == "dummy"
    report = {
        "mesure_valide": not validation_only,
        "avertissement": (
            "backend dummy : pipeline validé, aucun chiffre de ce rapport n'est citable"
            if validation_only else None
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": getattr(backend, "name", backend_name),
        "inprocess": bool(getattr(backend, "inprocess", False)),
        "load_seconds": round(load_seconds, 3),
        "corpus": str(corpus_dir),
        "environment": probes.environment(),
        "model_files": model_files,
        "normalization": {"langue": "fr", "module": "harness.metrics.normalize_fr",
                          "cer_espace_compte": False, "wer_agrege": "total_errors/total_ref"},
        "agrégats": metrics.aggregate(measured),
        "par_domaine": {
            domain: metrics.aggregate([r for r in measured if r["domaine"] == domain])
            for domain in sorted({r["domaine"] for r in measured})
        },
        "mesures_brutes": rows,
    }
    if memory:
        report["agrégats"]["peak_rss_bytes"] = memory["peak_rss_bytes"]
        report["agrégats"]["peak_rss_source"] = memory["source"]
    if memory_reason:
        report["agrégats"]["peak_rss_bytes"] = None
        report["agrégats"]["peak_rss_absence"] = memory_reason
    return report


def render_markdown(report: dict) -> str:
    agg = report["agrégats"]
    lines = [
        f"# Rapport — backend `{report['backend']}`",
        "",
        f"mesure exploitable : **{report['mesure_valide']}**",
    ]
    if report.get("avertissement"):
        lines += ["", f"> {report['avertissement']}"]
    latency = agg.get("latency_ms") or {}
    rows = [
        ("énoncés mesurés", agg.get("utterances")),
        ("WER", _pct(agg.get("wer"))),
        ("CER", _pct(agg.get("cer"))),
        ("latence médiane", _ms(latency.get("median"))),
        ("latence p95", _ms(latency.get("p95"))),
        ("RTF", _num(agg.get("rtf"))),
        ("pic mémoire", _mb(agg.get("peak_rss_bytes"))),
        ("audio mesurée", _num(agg.get("audio_seconds"), 3) + " s" if agg.get("audio_seconds") is not None else None),
    ]
    lines += ["", "| indicateur | valeur |", "|---|---|"]
    lines += [f"| {name} | {value if value is not None else 'non mesuré'} |" for name, value in rows]

    if report["par_domaine"]:
        lines += ["", "## Par domaine", "", "| domaine | énoncés | WER | CER |", "|---|---|---|---|"]
        for domain, sub in report["par_domaine"].items():
            lines.append(
                f"| {domain} | {sub.get('utterances')} | {_pct(sub.get('wer'))} | {_pct(sub.get('cer'))} |"
            )
    lines += ["", f"Environnement : {report['environment']['platform']} / Python {report['environment']['python']}"]
    return "\n".join(lines) + "\n"


def _pct(value):
    return f"{value * 100:.2f} %" if isinstance(value, (int, float)) else None


def _ms(value):
    return f"{value:.1f} ms" if isinstance(value, (int, float)) else None


def _num(value, digits=4):
    return f"{value:.{digits}g}" if isinstance(value, (int, float)) else None


def _mb(value):
    return f"{value / 1024 / 1024:.1f} MiB" if isinstance(value, (int, float)) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Campagne de mesure STT reproductible.")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--backend", default="dummy", choices=sorted(REGISTRY))
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", type=Path, default=None, help="chemin du manifeste JSON")
    args = parser.parse_args(argv)

    report = run(args.backend, args.corpus, args.model_dir, args.warmups, args.limit)
    print(render_markdown(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"manifeste écrit : {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
