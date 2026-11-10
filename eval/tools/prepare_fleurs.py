"""Constitue un corpus FLEURS fr_fr à partir du dépôt HuggingFace, sans tout télécharger.

Le tar.gz du split test pèse 349 Mo ; il est lu en flux et l'exécution s'arrête après
les N premiers fichiers audio. La transcription vient du TSV du même commit.

    python tools/prepare_fleurs.py --limit 100 --out corpora/fleurs-fr-test

Trois choses sont écrites, et aucune n'est optionnelle : les WAV, un manifest.tsv
prêt pour le harnais, et un PROVENANCE.json (commit, empreintes, licence, date,
attribution). Sans le dernier, le chiffre d'après n'est pas reproductible.

Les WAV de la source sont en float 32 bits ; le harnais ne mesure que du PCM 16 bits.
La conversion est faite ici, consignée par fichier dans PROVENANCE.json avec l'empreinte
du binaire d'origine : un auditeur peut retrouver ce qui a été transformé et ce qui ne
l'a pas été.

Dépendances : bibliothèque standard uniquement.
"""

from __future__ import annotations

import argparse
import array
import csv
import gzip
import hashlib
import io
import json
import tarfile
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path

DATASET = "google/fleurs"
# Le commit est relevé sur l'en-tête X-Repo-Commit du dépôt, et c'est lui qui sert
# d'adresse : « main » désignerait un contenu différent demain.
COMMIT = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"  # relevé le 2026-11-01
LICENCE = "CC-BY-4.0"
ATTRIBUTION = ("FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech. "
               "Google, 2021. https://huggingface.co/datasets/google/fleurs")
BASE = f"https://huggingface.co/datasets/{DATASET}/resolve/{COMMIT}/data/fr_fr"
CONFIG = "fr_fr"
SPLIT = "test"

# Colonnes du TSV FLEURS, vérifiées sur le fichier réel : 0 = identifiant, 1 = nom du
# wav, 2 = transcription casée, 3 = la même en minuscules, 4 = phonèmes, 5 = durée
# déclarée par la source, 6 = genre. Seules 1, 2 et 6 entrent dans le corpus ; le TSV
# n'a pas d'en-tête, donc l'index est figé et aucune lecture tolérante n'est possible.
COL_WAV, COL_CASSEE, COL_GENRE = 1, 2, 6
DOMAINE = "lecture-generaliste"
CAPTEUR = "non consigne par la source"
BRUIT = "non consigne par la source"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read()


def read_transcriptions(tsv_path: Path) -> dict[str, dict]:
    """id du fichier audio -> référence. Le TSV n'a pas d'en-tête : les index sont figés."""
    table: dict[str, dict] = {}
    with tsv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) != 7:
                raise ValueError(f"ligne TSV à {len(row)} champs, 7 attendus")
            table[row[COL_WAV]] = {"transcript": row[COL_CASSEE], "genre": row[COL_GENRE]}
    if not table:
        raise ValueError(f"TSV vide : {tsv_path}")
    return table


def wav_chunks(data: bytes) -> dict:
    """En-tete RIFF : format, canaux, frequence et bloc `data`. Lecture stricte."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("fichier qui n'est pas un RIFF/WAVE")
    fmt = None
    payload = None
    position = 12
    while position + 8 <= len(data):
        tag = data[position:position + 4]
        size = int.from_bytes(data[position + 4:position + 8], "little")
        block = data[position + 8:position + 8 + size]
        if tag == b"fmt ":
            fmt = {"audio_format": int.from_bytes(block[0:2], "little"),
                   "num_channels": int.from_bytes(block[2:4], "little"),
                   "sample_rate": int.from_bytes(block[4:8], "little"),
                   "bits_per_sample": int.from_bytes(block[14:16], "little")}
        elif tag == b"data":
            payload = block
        position += 8 + size + (size % 2)
    if fmt is None or payload is None:
        raise ValueError("blocs fmt ou data absents")
    return {"fmt": fmt, "data": payload}


def to_pcm16(mono: dict, name: str) -> tuple[bytes, str]:
    """Ramène l'échantillon au format que le harnais sait mesurer : PCM 16 bits mono.

    FLEURS livre du float 32 bits (tag 3) : le module wave refuse de l'ouvrir, et un
    backend qui ne lit que du PCM n'aurait rien à transcrire. La conversion ne touche
    que le type d'échantillon - ni rééchantillonnage, ni rognage de durée.
    """
    fmt = mono["fmt"]
    if fmt["num_channels"] != 1:
        raise ValueError(f"{name} : {fmt['num_channels']} canaux, le mono est requis")
    if fmt["audio_format"] == 1 and fmt["bits_per_sample"] == 16:
        return mono["data"], "pcm_s16le (aucune conversion)"
    if fmt["audio_format"] != 3 or fmt["bits_per_sample"] != 32:
        raise ValueError(f"{name} : format {fmt['audio_format']}/{fmt['bits_per_sample']} bits non pris en charge")
    flotteurs = array.array("f", mono["data"])
    pcm = array.array("h", (max(-32768, min(32767, round(s * 32767.0))) for s in flotteurs))
    return pcm.tobytes(), "float32 -> int16 (arrondi, même nombre d'échantillons)"


def pcm_wav_header(sample_rate: int, nframes: int) -> bytes:
    """En-tete WAV canonical de 44 octets pour du PCM mono 16 bits."""
    octets = nframes * 2
    return (b"RIFF" + (36 + octets).to_bytes(4, "little") + b"WAVEfmt "
            + (16).to_bytes(4, "little")
            + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
            + sample_rate.to_bytes(4, "little")
            + (sample_rate * 2).to_bytes(4, "little")
            + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
            + b"data" + octets.to_bytes(4, "little"))


def stream_audio(url: str, out_dir: Path, references: dict[str, dict], limit: int) -> list[dict]:
    """Écrit les N premiers WAV du flux et renvoie leurs métadonnées mesurées."""
    rows: list[dict] = []
    downloaded = 0
    with urllib.request.urlopen(url, timeout=300) as response:
        stream = gzip.GzipFile(fileobj=io.BufferedReader(response, buffer_size=1 << 16))
        tar = tarfile.open(fileobj=stream, mode="r|")
        for member in tar:
            if not member.isfile() or not member.name.endswith(".wav"):
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            downloaded += len(data)
            name = Path(member.name).name
            reference = references.get(name)
            if reference is None:
                # Le nom n'est pas dans le TSV du même commit : ce n'est pas un
                # appariement approximatif qui dira le contraire.
                raise ValueError(f"audio sans référence : {name}")
            mono = wav_chunks(data)
            samples, conversion = to_pcm16(mono, name)
            out = pcm_wav_header(mono["fmt"]["sample_rate"], len(samples) // 2) + samples
            (out_dir / name).write_bytes(out)
            with wave.open(str(out_dir / name), "rb") as audio:
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                    raise ValueError(f"{name} : canal unique et 16 bits requis")
                duration = audio.getnframes() / float(audio.getframerate())
                rate = audio.getframerate()
            rows.append({"audio": name, "bytes": len(out), "sha256": sha256_bytes(out),
                         "sha256_source": sha256_bytes(data),
                         "format_source": mono["fmt"], "conversion": conversion,
                         "sample_rate": rate, "duration_s": round(duration, 3), **reference})
            print(f"[{len(rows)}/{limit}] {name} {duration:.1f} s "
                  f"({downloaded / 1e6:.0f} Mo lus)", flush=True)
            if len(rows) >= limit:
                break
    return rows


def write_corpus(out_dir: Path, rows: list[dict], tsv_sha: str, elapsed: float) -> dict:
    # L'utt_id est l'identifiant FLEURS lui-meme : un auditeur doit pouvoir retrouver
    # l'enregistrement a la source sans passer par une table de correspondance locale.
    manifest = ["\t".join(("utt_id", "audio", "transcript", "domaine", "micro", "bruit_db",
                           "genre", "locuteur"))]
    for row in rows:
        manifest.append("\t".join((Path(row["audio"]).stem, row["audio"], row["transcript"],
                                   DOMAINE, CAPTEUR, BRUIT, row["genre"], "non-identifie")))
    (out_dir / "manifest.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    provenance = {
        "dataset": DATASET, "config": CONFIG, "split": SPLIT,
        "commit": COMMIT, "licence": LICENCE, "attribution": ATTRIBUTION,
        "recupere_le": datetime.now(timezone.utc).isoformat(),
        "outil": "tools/prepare_fleurs.py", "duree_extraction_s": round(elapsed, 1),
        "transcriptions_sha256": tsv_sha,
        # La sélection n'est pas un tirage : ce sont les N premiers membres de
        # l'archive, dans son ordre. Rejouer la commande sur le même commit rend
        # les mêmes fichiers, mais ce n'est pas un échantillonnage de la population.
        "selection": f"{len(rows)} premiers membres de data/{CONFIG}/audio/{SPLIT}.tar.gz, ordre d'archive",
        "enregistrements": len(rows),
        "heures_audio": round(sum(r["duration_s"] for r in rows) / 3600, 4),
        "octets_ecrits": sum(r["bytes"] for r in rows),
        "formats": {"sample_rate": sorted({r["sample_rate"] for r in rows}),
                    "canaux": 1, "profondeur_bits": 16,
                    "source": sorted({json.dumps(r["format_source"], sort_keys=True) for r in rows}),
                    "conversion": sorted({r["conversion"] for r in rows})},
        "limites_source": [
            "Le capteur et le niveau de bruit d'origine ne sont pas consignés par FLEURS : "
            "les colonnes correspondantes portent la mention explicite, pas une valeur par défaut.",
            "Annotation de référence unique, non double-validée. La règle « double annotation "
            "dans les corpus de domaine » de eval/CORPUS.md ne peut pas être tenue ici.",
            "Le locuteur n'est pas identifié : le genre est la seule stratification disponible.",
            "Lecture de phrases isolées : rien sur les tours de parole, les hésitations ou le "
            "français spontané du client primaire.",
            "La sélection est la tête d'archive, pas un tirage aléatoire : les taux mesurés ne "
            "s'affranchissent de rien d'autre que de la taille de l'échantillon.",
        ],
        "fichiers": [{k: r[k] for k in ("audio", "sha256", "sha256_source", "bytes",
                                        "duration_s", "genre", "conversion")}
                     for r in rows],
    }
    (out_dir / "PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--out", type=Path, required=True)
    # Ancre absolue : une racine de cache calculee relativement au repertoire courant
    # se retrouvait hors du depot des qu'on lançait l'outil depuis ailleurs.
    parser.add_argument("--cache", type=Path,
                        default=Path(__file__).resolve().parents[2] / ".cache" / "fleurs")
    args = parser.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)

    tsv_local = args.cache / f"{SPLIT}.tsv"
    if not tsv_local.exists():
        tsv_local.write_bytes(fetch(f"{BASE}/{SPLIT}.tsv"))
    tsv_sha = sha256_bytes(tsv_local.read_bytes())
    references = read_transcriptions(tsv_local)
    print(f"références chargées : {len(references)} | TSV sha256 {tsv_sha[:12]}")

    started = datetime.now(timezone.utc)
    rows = stream_audio(f"{BASE}/audio/{SPLIT}.tar.gz", out_dir, references, args.limit)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    provenance = write_corpus(out_dir, rows, tsv_sha, elapsed)
    print(f"\n{provenance['enregistrements']} enregistrements, "
          f"{provenance['heures_audio']:.3f} h d'audio, "
          f"{provenance['octets_ecrits'] / 1e6:.0f} Mo écrits, "
          f"licence {provenance['licence']}")
    print(f"corpus : {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
