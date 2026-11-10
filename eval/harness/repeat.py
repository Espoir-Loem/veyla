"""Agrégat de campagnes répétées sur un même corpus.

    python -m harness.repeat --corpus corpora/fleurs-fr-test --backend vosk-small-fr \\
        --model-dir ../models/vosk-model-small-fr-0.22 --campagnes 3 --json reports/x.json

Une campagne = un processus. Chaque campagne repart de son propre exécutable pour que
le pic mémoire reste celui d'un chargement unique : dans le même processus, la deuxième
campagne hériterait du modèle déjà résident et publierait un pic faux.

Deux dispersations sont séparées parce qu'elles ne répondent pas à la même question :
celle **entre campagnes** (la machine, l'ordonnanceur, l'état du système) et celle
due à la **taille de l'échantillon d'énoncés** (intervalle de confiance). Un WER
identique trois fois avec un RTF qui double ne rassure que sur le premier.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from . import metrics

__all__ = ["synthese", "lancer_campagne", "render_markdown"]

GRAINE_BOOTSTRAP = 20261101
REPRISES = 2000


def bootstrap_enonces(rows: list[dict], cle: str, reprises: int,
                      rng: random.Random) -> tuple[float, float] | None:
    """Bornes 2,5 % / 97,5 % par réechantillonnage des énoncés, avec remise.

    La pondération par la longueur doit survivre au tirage : on somme erreurs et
    longueurs de référence du jeu reconstitué, on ne moyenne pas des taux.
    """
    utiles = [(r[cle]["errors"], r[cle]["reference_length"]) for r in rows
              if isinstance(r.get(cle), dict) and r[cle].get("reference_length")]
    if len(utiles) < 2:
        return None
    nombre = len(utiles)
    taux = []
    for _ in range(reprises):
        erreurs = 0
        longueurs = 0
        for _ in range(nombre):
            e, l = utiles[rng.randrange(nombre)]
            erreurs += e
            longueurs += l
        if longueurs:
            taux.append(erreurs / longueurs)
    if len(taux) < 2:
        return None
    return metrics.percentile(taux, 2.5), metrics.percentile(taux, 97.5)


def _serie(valeurs: list) -> dict:
    ordonnees = sorted(v for v in valeurs if isinstance(v, (int, float)))
    if not ordonnees:
        return {"valeurs": valeurs, "identique": None,
                "motif": "aucune valeur numérique exploitable"}
    return {
        "min": ordonnees[0],
        "médiane": ordonnees[len(ordonnees) // 2],
        "max": ordonnees[-1],
        "étendue_relative": ((ordonnees[-1] - ordonnees[0]) / ordonnees[0]
                             if ordonnees[0] else None),
        "identique": len(set(ordonnees)) == 1,
    }


def synthese(campagnes: list[dict], reprises: int = REPRISES,
             graine: int = GRAINE_BOOTSTRAP) -> dict:
    """Combine des rapports de campagne en un rapport qui dit d'où il sort."""
    if not campagnes:
        raise ValueError("aucune campagne à agréger")

    wer = [c["agrégats"].get("wer") for c in campagnes]
    cer = [c["agrégats"].get("cer") for c in campagnes]
    rtf = [c["agrégats"].get("rtf") for c in campagnes]
    mediane = [(c["agrégats"].get("latency_ms") or {}).get("median") for c in campagnes]
    p95 = [(c["agrégats"].get("latency_ms") or {}).get("p95") for c in campagnes]
    rss = [c["agrégats"].get("peak_rss_bytes") for c in campagnes]

    # Une seule campagne porte l'intervalle : les énoncés sont les mêmes d'une campagne
    # à l'autre quand le modèle est déterministe. Quand ils ne le sont pas, le dire.
    accord_des_taux = {"wer": _serie(wer), "cer": _serie(cer)}
    rows = campagnes[0]["mesures_brutes"]
    rng = random.Random(graine)
    intervalles = {}
    for nom, estimation in (("wer", wer[0]), ("cer", cer[0])):
        intervalle = {"estimation": estimation, "ic95": None}
        if estimation is None:
            intervalle["motif"] = "aucun taux agrégé sur la première campagne"
        elif accord_des_taux[nom]["identique"] is False:
            # Réechantillonner une seule campagne ne couvre pas l'écart observé entre
            # campagnes : publier cet intervalle attribuerait tout au hasard du corpus.
            intervalle["motif"] = ("les campagnes rendent des taux divergents : "
                                   "l'intervalle d'une seule campagne ne couvre pas "
                                   "cette dispersion")
        else:
            bornes = bootstrap_enonces(rows, nom, reprises, rng)
            if bornes:
                intervalle["ic95"] = [round(bornes[0], 6), round(bornes[1], 6)]
            else:
                intervalle["motif"] = "moins de deux énoncés mesurés"
        intervalles[nom] = intervalle

    valides = [c for c in campagnes if c.get("mesure_valide")]
    return {
        "type": "agrégat_de_campagnes",
        "campagnes": len(campagnes),
        "mesure_valide": len(valides) == len(campagnes),
        "avertissement": (None if len(valides) == len(campagnes) else
                          f"seulement {len(valides)}/{len(campagnes)} campagne(s) exploitables : "
                          "cet agrégat n'est pas citable"),
        "backend": campagnes[0]["backend"],
        "corpus": campagnes[0]["corpus"],
        # Convergence des taux et stabilité des temps : deux questions distinctes.
        "accord_des_taux": accord_des_taux,
        "dispersion": {"rtf": _serie(rtf),
                       "latence_médiane_ms": _serie(mediane),
                       "latence_p95_ms": _serie(p95),
                       "pic_mémoire_octets": _serie(rss)},
        "intervalles": intervalles,
        "bootstrap": {"reprises": reprises, "graine": graine, "unité": "énoncé",
                      "campagne_utilisée": 1,
                      "méthode": "réechantillonnage avec remise des énoncés, "
                                 "bornes au rang le plus proche"},
        "campagnes_détail": [
            {"numéro": i + 1, "backend": c["backend"], "mesure_valide": c.get("mesure_valide"),
             "load_seconds": c.get("load_seconds"), "agrégats": c["agrégats"],
             "environment": c.get("environment")}
            for i, c in enumerate(campagnes)
        ],
    }


def lancer_campagne(runner_args: list[str], cwd: Path,
                    destination: Path | None = None) -> dict:
    """Une campagne dans son processus, et son rapport relu depuis le disque.

    La progression de l'enfant est laissée sur stderr : une campagne de quinze minutes
    sans une seule ligne d'avancement n'est pas vérifiable pendant qu'elle tourne.

    `destination`, quand elle est donnée, est conservée : trente minutes de mesures ne
    doivent pas dépendre de la dernière campagne pour exister.
    """
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        sortie, menage = destination, None
    else:
        dossier = tempfile.TemporaryDirectory()
        sortie, menage = Path(dossier.name) / "campagne.json", dossier
    try:
        command = [sys.executable, "-m", "harness.runner", *runner_args, "--json", str(sortie)]
        resultat = subprocess.run(command, cwd=str(cwd), stdout=subprocess.PIPE,
                                  encoding="utf-8", errors="replace")
        if resultat.returncode != 0:
            raise SystemExit(f"campagne interrompue (code {resultat.returncode}):\n{resultat.stdout}")
        rapport = json.loads(sortie.read_text(encoding="utf-8"))
        if destination:
            print(f"campagne conservée : {destination}", file=sys.stderr, flush=True)
        return rapport
    finally:
        if menage:
            menage.cleanup()


def _pct(v):
    return f"{v * 100:.2f} %" if isinstance(v, (int, float)) else "non mesuré"


def _ms(v):
    return f"{v:.1f} ms" if isinstance(v, (int, float)) else "non mesuré"


def render_markdown(agg: dict) -> str:
    lignes = [f"# Agrégat - {agg['campagnes']} campagne(s), backend `{agg['backend']}`", "",
              f"mesure exploitable : **{agg['mesure_valide']}**", f"corpus : `{agg['corpus']}`"]
    if agg.get("avertissement"):
        lignes += ["", f"> {agg['avertissement']}"]

    lignes += ["", "## Convergence des taux entre campagnes", ""]
    for nom, serie in agg["accord_des_taux"].items():
        if serie["identique"]:
            lignes.append(f"- {nom.upper()} : **identique** sur {agg['campagnes']} campagne(s) "
                          f"({_pct(serie['médiane'])})")
        else:
            lignes.append(f"- {nom.upper()} : de {_pct(serie['min'])} à {_pct(serie['max'])}")

    lignes += ["", "## Intervalle dû à la taille de l'échantillon", "",
               "Ce que la machine ne varie pas, le corpus le varie : les bornes ci-dessous "
               "viennent du nombre d'énoncés, pas de l'ordonnanceur."]
    for nom, intervalle in agg["intervalles"].items():
        bornes = intervalle.get("ic95")
        if bornes:
            lignes.append(f"- {nom.upper()} : {_pct(intervalle['estimation'])}, "
                          f"intervalle à 95 % [{_pct(bornes[0])} ; {_pct(bornes[1])}] "
                          f"({agg['bootstrap']['reprises']} réechantillonnages, "
                          f"graine {agg['bootstrap']['graine']})")
        else:
            lignes.append(f"- {nom.upper()} : intervalle non calculé - {intervalle['motif']}")

    lignes += ["", "## Dispersion des temps entre campagnes", "",
               "| indicateur | min | médiane | max | identique |", "|---|---|---|---|---|"]
    formats = {"rtf": lambda v: f"{v:.4g}" if isinstance(v, (int, float)) else "non mesuré",
               "latence_médiane_ms": _ms, "latence_p95_ms": _ms,
               "pic_mémoire_octets": lambda v: (f"{v / 1024 / 1024:.1f} MiB"
                                                if isinstance(v, (int, float)) else "non mesuré")}
    for nom, serie in agg["dispersion"].items():
        forme = formats[nom]
        lignes.append(f"| {nom} | {forme(serie.get('min'))} | {forme(serie.get('médiane'))} | "
                      f"{forme(serie.get('max'))} | {serie.get('identique')} |")
    return "\n".join(lignes) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Campagnes STT répétées sur un même corpus.")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--backend", default="dummy")
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--axes", default="domaine")
    parser.add_argument("--campagnes", type=int, default=3)
    parser.add_argument("--reprises", type=int, default=REPRISES,
                        help="réechantillonnages du bootstrap")
    parser.add_argument("--graine", type=int, default=GRAINE_BOOTSTRAP)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.campagnes < 1:
        raise SystemExit("--campagnes vaut au moins 1")

    runner_args = ["--corpus", str(args.corpus), "--backend", args.backend,
                   "--warmups", str(args.warmups), "--axes", args.axes]
    if args.model_dir:
        runner_args += ["--model-dir", str(args.model_dir)]
    if args.limit:
        runner_args += ["--limit", str(args.limit)]

    depot = Path(__file__).resolve().parents[1]
    campagnes = []
    for numero in range(1, args.campagnes + 1):
        print(f"campagne {numero}/{args.campagnes}", file=sys.stderr, flush=True)
        destination = None
        if args.json:
            # Chaque campagne survit sur le disque au moment où elle finit : si la
            # troisième échoue, les deux premières ne sont pas perdues avec elle.
            destination = args.json.with_name(f"{args.json.stem}-campagne-{numero}.json")
        campagnes.append(lancer_campagne(runner_args, depot, destination))

    agg = synthese(campagnes, reprises=args.reprises, graine=args.graine)
    print(render_markdown(agg))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(agg)
        payload["rapports_campagnes"] = campagnes
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"agrégat écrit : {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
