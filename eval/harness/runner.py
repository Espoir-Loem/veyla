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
BASE_COLUMNS = ("utt_id", "audio", "transcript")
# Un axe est une colonne de métadonnée déclarée par son seul nom. `par_axe` n'est pas
# un cas particulier du domaine : le domaine est simplement l'axe déclaré par défaut,
# pour ne rien changer aux campagnes déjà lancées.
DEFAULT_AXES = ("domaine",)


@dataclass
class Utterance:
    utt_id: str
    audio: Path
    transcript: str
    axes: dict = field(default_factory=dict)


def _axes_or_fail(axes: tuple[str, ...]) -> tuple[str, ...]:
    if not axes:
        raise SystemExit("aucun axe déclaré : le harnais ne peut pas répartir les taux")
    doublons = set(BASE_COLUMNS) & set(axes)
    if doublons:
        raise SystemExit(f"axes portant le nom d'une colonne de base : {sorted(doublons)}")
    return axes


def _from_manifest(corpus_dir: Path, axes: tuple[str, ...]) -> list[Utterance]:
    axes = _axes_or_fail(axes)
    rows: list[Utterance] = []
    # `newline` par défaut : un manifeste édité sous Windows finit en CRLF, et le \r
    # se collerait aux noms de colonne comme aux transcriptions.
    with (corpus_dir / MANIFEST_NAME).open(encoding="utf-8") as handle:
        header = [column.strip() for column in handle.readline().rstrip("\n").split("\t")]
        known = set(BASE_COLUMNS) | set(axes)
        unknown = [c for c in header if c not in known]
        if unknown:
            raise SystemExit(
                f"{MANIFEST_NAME} : colonnes inconnues {unknown} - déclare-les comme axes avec "
                f"--axes {','.join(tuple(axes) + tuple(unknown))}, ou retire-les du manifeste"
            )
        absent = [c for c in BASE_COLUMNS + axes if c not in header]
        if absent:
            raise SystemExit(f"{MANIFEST_NAME} : colonnes requises absentes {absent}")
        for lineno, line in enumerate(handle, start=2):
            if not line.strip():
                continue
            fields = [column.strip() for column in line.rstrip("\n").split("\t")]
            # Le nombre de champs doit correspondre à l'en-tête : une tabulation perdue
            # dans une transcription décalerait les colonnes sans aucun message.
            if len(fields) != len(header):
                raise SystemExit(
                    f"{MANIFEST_NAME} ligne {lineno} : {len(fields)} champ(s) pour "
                    f"{len(header)} colonne(s)"
                )
            record = dict(zip(header, fields))
            rows.append(
                Utterance(
                    utt_id=record["utt_id"],
                    audio=corpus_dir / record["audio"],
                    transcript=record["transcript"],
                    axes={axis: record[axis] for axis in axes},
                )
            )
    return rows


def _from_pairs(corpus_dir: Path, axes: tuple[str, ...]) -> list[Utterance]:
    """Mode sans manifeste : `x.wav` accompagné de `x.txt` contenant la référence."""
    axes = _axes_or_fail(axes)
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
                # Pas de manifeste donc pas de métadonnée : l'axe existe mais reste
                # explicitement non renseigné plutôt que simulé.
                axes={axis: "non-rens." for axis in axes},
            )
        )
    return rows


def load_corpus(corpus_dir: Path, axes: tuple[str, ...] = DEFAULT_AXES) -> list[Utterance]:
    if not corpus_dir.is_dir():
        raise SystemExit(f"corpus introuvable : {corpus_dir}")
    if (corpus_dir / MANIFEST_NAME).exists():
        rows = _from_manifest(corpus_dir, axes)
    else:
        rows = _from_pairs(corpus_dir, axes)
    if not rows:
        raise SystemExit(f"aucun énoncé dans {corpus_dir} : rien à mesurer")
    missing = [r.utt_id for r in rows if not r.audio.exists()]
    if missing:
        raise SystemExit(f"{len(missing)} fichier(s) audio manquant(s), ex. {missing[:5]}")
    return rows


def run(backend_name: str, corpus_dir: Path, model_dir: Path | None,
        warmups: int, limit: int | None,
        axes: tuple[str, ...] = DEFAULT_AXES) -> dict:
    backend = build_backend(backend_name, model_dir)

    utterances = load_corpus(corpus_dir, axes)
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
            **utt.axes,
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
        "axes": list(axes),
        "environment": probes.environment(),
        "model_files": model_files,
        "normalization": {"langue": "fr", "module": "harness.metrics.normalize_fr",
                          "empreinte": metrics.empreinte_normalisation(),
                          "cer_espace_compte": False, "wer_agrege": "total_errors/total_ref"},
        "agrégats": metrics.aggregate(measured),
        # Un axe qui ne prend qu'une valeur (corpus sans manifeste, par exemple) n'a
        # pas de tableau : répéter le global sous un nom d'axe ne documente rien.
        "par_axe": {
            axis: {
                valeur: metrics.aggregate([r for r in measured if r[axis] == valeur])
                for valeur in sorted({r[axis] for r in measured})
            }
            for axis in axes
            if len({r[axis] for r in measured}) > 1
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
        f"# Rapport - backend `{report['backend']}`",
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

    for axis, groups in report["par_axe"].items():
        lines += ["", f"## Par {axis}", "", f"| {axis} | énoncés | WER | CER |", "|---|---|---|---|"]
        for valeur, sub in groups.items():
            lines.append(
                f"| {valeur} | {sub.get('utterances')} | {_pct(sub.get('wer'))} | {_pct(sub.get('cer'))} |"
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
    # Pas de choices= ici : un nom invalide doit passer par build_backend, qui nomme
    # les modules non chargeables et leur raison. argparse les cacherait.
    parser.add_argument("--backend", default="dummy")
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--axes", default=",".join(DEFAULT_AXES),
                        help="colonnes de métadonnée à répartir, séparées par des virgules")
    parser.add_argument("--json", type=Path, default=None, help="chemin du manifeste JSON")
    args = parser.parse_args(argv)

    axes = tuple(a.strip() for a in args.axes.split(",") if a.strip())
    report = run(args.backend, args.corpus, args.model_dir, args.warmups, args.limit, axes)
    print(render_markdown(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"manifeste écrit : {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
