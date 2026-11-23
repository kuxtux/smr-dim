# -*- coding: utf-8 -*-
"""
PMSI SMR — construction de la base locale des actes de réadaptation.

Lit les fichiers sources de l'ATIH déposés dans ``sources/`` et produit
``data/smr.sqlite``, entièrement régénérable.

Les fichiers sont repérés par leur NOM, cherché récursivement dans
``sources/`` : le rangement du dossier est libre et peut être réorganisé sans
toucher au code. Lors d'un changement de version, il suffit de déposer les
nouveaux fichiers ; si plusieurs versions coexistent, la plus récente est
retenue.

Usage :  python smr_build.py
"""

import glob
import os
import re
import sqlite3
import unicodedata

import pandas as pd

RACINE = os.path.dirname(os.path.abspath(__file__))
DOSSIER_SOURCES = os.path.join(RACINE, "sources")
DOSSIER_DATA = os.path.join(RACINE, "data")
BASE_SQLITE = os.path.join(DOSSIER_DATA, "smr.sqlite")

# Motifs de recherche des fichiers sources : de simples motifs de NOM, cherchés
# récursivement dans sources/. Le rangement du dossier est donc libre — on peut
# le réorganiser sans toucher au code, et un fichier retrouve sa place où qu'il
# soit déposé. Seul son nom compte.
MOTIFS = {
    # Nomenclatures d'actes
    "csar": "csar_version_*.xlsx",
    "csar_assoc": "fichier_associe_csar_*.xlsx",
    "csarr": "fichier_complementaire_csarr_*.xlsx",
    "transcodage": "Transcodage_CSARR_CSAR*.xlsx",
    # Groupe de réadaptation : pondérations, actes spécialisés, seuils
    "pond_csarr": "ACTES_ponderations_CSARR*.xlsx",
    "pond_csar": "ACTES_ponderations_CSAR_transcodage*.xlsx",
    "spe_csar": "ACTES_listes_SPE_CSAR*.xlsx",
    "spe_csarr": "ACTES_listes_SPE.xlsx",
    "csar_gme": "CSAR_infos*.xlsx",
    "gr": "GR_infos*.xlsx",
    # Catégorie majeure, groupe nosologique, lourdeur, sévérité
    "cim": "CIM_infos_SMR*.xlsx",
    "gn_tests": "GN_liste_tests*.xlsx",
    "gl": "GL_infos*.xlsx",
    "cma_exclusion": "CMA_exclusion*.xlsx",
    "cma_ccam": "CMA_CCAM*.xlsx",
    # Libellés de tous les groupes, et tarifs
    "groupes": "TOTAL_listes_groupes*.xlsx",
    "tarifs": "annexes_arrete_tarifaire_smr_*.xlsx",
}

# Renvoi d'une ligne d'exclusion vers la liste d'un autre code CMA.
RE_MEME_LISTE = re.compile(r"m[êe]me\s+liste\s+que\s+(.+)$", re.I)

# Règle de lourdeur combinée : le niveau dépend alors de l'âge, et la table
# l'écrit en clair dans la cellule (« age 18_70 -> B; age 71_plus --> A; »).
# La flèche est tantôt simple tantôt double dans le fichier de l'ATIH.
RE_REGLE_COMBINEE = re.compile(r"age\s+(\d+)_(\d+|plus)\s*-+>\s*([ABC])")

# Syntaxe des tests d'entrée en groupe nosologique : « <position> D-<liste> ».
# Les séparateurs sont irréguliers dans le fichier ATIH (« D- 0841 »,
# « D-0878-Ostéopathies », espaces insécables) ; cette expression couvre les
# 100 nœuds. L'alternative « MMP ou AE » doit précéder « MMP ».
RE_TEST_GN = re.compile(r"(MMP ou AE|MMP|AE|DAS)\s*D-?\s*(\d{4})")

# L'outil est paramétré pour un établissement public de santé (a de l'article
# L.162-22 du code de la sécurité sociale), donc grille ex-DAF (annexe I).
GRILLE_TARIFAIRE = "Tarifs GMT - DAF"

# Chapitres du CSAR (guide de codage CSAR, tableau 1 et § 1.2.2).
CHAPITRES_CSAR = {
    "01": "Fonctions cérébrales",
    "02": "Fonctions sensorielles et douleur",
    "03": "Fonctions de la voix et de la parole",
    "04": "Fonctions cardiaques, vasculaires et respiratoires",
    "05": "Fonctions digestives et nutrition",
    "06": "Fonctions génito-urinaires et reproductives",
    "07": "Fonctions de l'appareil locomoteur et liées au mouvement",
    "08": "Fonctions de la peau et des phanères",
    "09": "Appareillage",
    "10": "Éducation et information",
    "11": "Activités et participation",
}

# 3e caractère du code CSAR = objectif de l'acte (guide CSAR § 1.3.2).
TYPES_CSAR = {
    "E": "Acte d'évaluation à visée de diagnostic et de synthèse",
    "S": "Séance — acte de prise en charge à visée thérapeutique",
    "M": "Mise à disposition d'appareillage",
    "P": "Préparation et/ou suivi de l'avancement d'un dossier",
}

# Sous-chapitres du CSARR qui décrivent non pas des actes mais des codes
# supplémentaires (modulateurs, extensions documentaires).
HIERA_MODULATEURS = "12.02"
HIERA_EXTENSIONS = "12.03"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _norm_col(texte):
    """Normalise un nom de colonne / de feuille (accents, insécables, casse)."""
    txt = str(texte).replace("\xa0", " ")
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


# Ligatures : la décomposition Unicode ne les sépare pas. Sans cette table,
# « œdème » devenait « d me » et « manœuvre » « man uvre », introuvables.
LIGATURES = str.maketrans({"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE"})


def normaliser(texte):
    """Minuscules + suppression des accents, pour la recherche plein texte."""
    if not texte:
        return ""
    txt = unicodedata.normalize("NFKD", str(texte).translate(LIGATURES))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    txt = re.sub(r"[’']", " ", txt)
    txt = re.sub(r"[^a-z0-9\-\s]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _s(v):
    """Valeur de cellule -> chaîne propre (NaN, 'nan', espaces insécables)."""
    if v is None:
        return ""
    txt = str(v).replace("\xa0", " ").strip()
    if txt.lower() in ("nan", "nat", "none"):
        return ""
    return re.sub(r"[ \t]+", " ", txt)


def _oui(v):
    """Cellule marqueur ('oui', 'x', 'x', '1', 'possible') -> booléen."""
    return _s(v).lower() in ("oui", "x", "×", "1", "possible")


def trouver_source(cle, obligatoire=True):
    """Chemin du fichier source correspondant au motif, cherché récursivement.

    La recherche parcourt toute l'arborescence de ``sources/`` : le rangement
    du dossier est donc libre. Si plusieurs versions coexistent, la plus
    récente est retenue, à date égale la première dans l'ordre alphabétique —
    de sorte que deux exécutions donnent toujours le même résultat.
    """
    motif = os.path.join(DOSSIER_SOURCES, "**", MOTIFS[cle])
    fichiers = [f for f in glob.glob(motif, recursive=True)
                if os.path.isfile(f)
                and not os.path.basename(f).startswith("~$")]
    if not fichiers:
        if obligatoire:
            raise SystemExit(
                "Fichier source manquant : aucun fichier nommé « %s » dans "
                "sources/ (ni dans ses sous-dossiers).\nDéposez le fichier "
                "ATIH correspondant, son emplacement importe peu."
                % MOTIFS[cle])
        return None
    return max(sorted(fichiers, reverse=True), key=os.path.getmtime)


def _lire(chemin, prefixe_feuille, header=0):
    """Lit la 1re feuille dont le nom commence par ``prefixe_feuille``."""
    with pd.ExcelFile(chemin) as xl:
        cible = None
        attendu = _norm_col(prefixe_feuille)
        for nom in xl.sheet_names:
            if _norm_col(nom).startswith(attendu):
                cible = nom
                break
        if cible is None:
            raise SystemExit(
                "Feuille « %s » introuvable dans %s (feuilles : %s)"
                % (prefixe_feuille, os.path.basename(chemin), xl.sheet_names)
            )
        df = xl.parse(cible, header=header, dtype=str)
    df.columns = [_norm_col(c) for c in df.columns]
    return df.astype(object).map(_s)


def _col(df, *prefixes):
    """Colonne repérée par son nom normalisé.

    La correspondance exacte est testée d'abord pour tous les préfixes :
    sans cela ``code_csar`` capturerait la colonne ``code_csarr``.
    """
    noms = [_norm_col(p) for p in prefixes]
    for p in noms:
        for c in df.columns:
            if str(c) == p:
                return df[c]
    for p in noms:
        for c in df.columns:
            if str(c).startswith(p):
                return df[c]
    return pd.Series([""] * len(df), index=df.index, dtype=object)


def _version(chemin):
    return os.path.basename(chemin) if chemin else ""


# ---------------------------------------------------------------------------
# CSAR
# ---------------------------------------------------------------------------

def lire_csar():
    """Actes CSAR, éligibilité des modulateurs, intervenants, référentiels."""
    f_csar = trouver_source("csar")
    f_assoc = trouver_source("csar_assoc")

    base = _lire(f_csar, "actes_csar")
    defs = _lire(f_assoc, "def_acte_csar")

    actes = pd.DataFrame({
        "code": _col(base, "code_csar", "code"),
        "libelle": _col(base, "libelle_csar", "libelle"),
        "exclusions": _col(base, "exclusion"),
    })
    actes = actes[actes["code"].str.len() == 5].copy()

    d = pd.DataFrame({
        "code": _col(defs, "code"),
        "definition": _col(defs, "definition"),
        "fonction_cif": _col(defs, "fonction cif"),
        "description": _col(defs, "description"),
    })
    d = d[d["code"].str.len() == 5]
    actes = actes.merge(d, on="code", how="left").fillna("")

    actes["chapitre"] = actes["code"].str[:2]
    actes["chapitre_titre"] = actes["chapitre"].map(CHAPITRES_CSAR).fillna("")
    actes["type_acte"] = actes["code"].str[2]
    actes["type_libelle"] = actes["type_acte"].map(TYPES_CSAR).fillna("")
    actes["recherche"] = (actes["code"] + " " + actes["libelle"]).map(normaliser)
    actes["recherche_notes"] = (
        actes["definition"] + " " + actes["fonction_cif"] + " "
        + actes["description"]
    ).map(normaliser)

    # Éligibilité modulateurs / modalités (annexe 3 du guide CSAR).
    el = _lire(f_csar, "eligibilite_modulateur")
    mods = pd.DataFrame({"code": _col(el, "code_csar", "code")})
    for c in ("temps", "l1", "l2", "l3", "coll", "pp",
              "qm", "qi", "qf", "qs", "qq", "qc"):
        mods[c] = _col(el, c).map(lambda v: "oui" if _oui(v) else "")
    mods["mod_technicite"] = _col(el, "modulateurs_de_technicite")
    mods["niv_mod_tech"] = _col(el, "niv_ou_mod_tech").map(
        lambda v: "oui" if _oui(v) else "")
    mods = mods[mods["code"].str.len() == 5]

    # Liste indicative des intervenants attendus par acte.
    ia = _lire(f_csar, "inter_actes")
    inter = pd.DataFrame({
        "code": _col(ia, "code_csar", "code"),
        "code_inter": _col(ia, "code_inter"),
        "lib_inter": _col(ia, "lib_inter"),
        "attendu": _col(ia, "attendu"),
    })
    inter = inter[inter["code"].str.len() == 5].copy()
    inter["code_inter"] = inter["code_inter"].str.zfill(2)

    # Référentiel modulateurs / modalités / extensions documentaires CSAR.
    rm = _lire(f_csar, "modulateur_modalite_extension")
    ref_mod = pd.DataFrame({
        "type": _col(rm, "type"),
        "variable": _col(rm, "variable"),
        "modalite": _col(rm, "modalite"),
        "niveau": _col(rm, "niveau_ou_module"),
        "libelle": _col(rm, "libelle"),
    })
    ref_mod = ref_mod[ref_mod["modalite"] != ""]

    # Transcodage des modulateurs CSARR -> CSAR (addendum 1 du guide CSAR).
    tm = _lire(f_csar, "transcodage_modulateurs")
    ref_tm = pd.DataFrame({
        "type": _col(tm, "type_modulateur"),
        "code_csarr": _col(tm, "code_csarr"),
        "libelle_csarr": _col(tm, "libelle_csarr"),
        "code_csar": _col(tm, "code_csar"),
        "libelle_csar": _col(tm, "libelle_csar"),
    })

    t = _lire(f_csar, "tac")
    tac = pd.DataFrame({
        "code_csarr": _col(t, "code_csarr"),
        "libelle_csarr": _col(t, "libelle_csarr"),
        "code_csar": _col(t, "code_csar"),
        "libelle_csar": _col(t, "libelle_csar"),
    })
    tac = tac[tac["code_csarr"] != ""]

    return actes, mods, inter, ref_mod, ref_tm, tac, _version(f_csar)


def lire_ponderations_csar():
    """Pondérations CSAR (issues du transcodage des pondérations CSARR)."""
    f = trouver_source("pond_csar", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""
    p = _lire(f, "pond_csar")
    out = pd.DataFrame({
        "code": _col(p, "code_csar"),
        "acte_collectif": _col(p, "acte_collectif", "acte_coll"),
        "intervenant": _col(p, "intervenant").str.zfill(2),
        "ponderation": _col(p, "ponderation"),
        "mod_tps": _col(p, "mod_tps").map(lambda v: "x" if _oui(v) else ""),
        "mod_l1": _col(p, "mod_l1").map(lambda v: "x" if _oui(v) else ""),
        "mod_l2": _col(p, "mod_l2").map(lambda v: "x" if _oui(v) else ""),
        "mod_l3": _col(p, "mod_l3").map(lambda v: "x" if _oui(v) else ""),
    })
    return out[out["code"].str.len() == 5], _version(f)


def lire_spe_csar():
    """Caractère spécialisé des actes CSAR par regroupement de GN."""
    f = trouver_source("spe_csar", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""
    s = _lire(f, "liste_gn_spe")
    out = pd.DataFrame({
        "code": _col(s, "code_csar"),
        "acte_coll": _col(s, "acte_coll"),
        "intervenant": _col(s, "intervenant").str.zfill(2),
        "gn_liste": _col(s, "gn_liste"),
        "libelle_gn": _col(s, "libelle_gn_liste"),
    })
    return out[out["code"].str.len() == 5], _version(f)


# ---------------------------------------------------------------------------
# CSARR
# ---------------------------------------------------------------------------

def lire_csarr():
    """Actes CSARR hiérarchisés, notes, structure, codes supprimés."""
    f = trouver_source("csarr")
    df = _lire(f, "csarr")

    plat = pd.DataFrame({
        "hiera": _col(df, "codehier"),
        "code": _col(df, "codeacte"),
        "libelle": _col(df, "libelle"),
        "type": _col(df, "typeligne"),
        "gestes": _col(df, "gestescomplementaires"),
        "mod_lieu": _col(df, "modulateur lieu"),
        "mod_patient": _col(df, "modulateur patient"),
        "mod_tech": _col(df, "modulateur technicite"),
        "module_niveau": _col(df, "module et niveau"),
        "consigne": _col(df, "consigne de codage"),
        "action": _col(df, "actions annee"),
        "seance": _col(df, "seance"),
        "dedie": _col(df, "dedie"),
        "non_dedie": _col(df, "non dedie"),
        "collectif": _col(df, "collectif"),
        "pluripro": _col(df, "pluriprofessionnel"),
        "appareillage": _col(df, "appareillage avec etapes"),
        "debut": _col(df, "debut de validite"),
        "fin": _col(df, "fin de validite"),
    })

    # --- structure hiérarchique (titres) et notes de titre ------------------
    structure, notes_titre = [], {}
    dernier_titre = None
    for r in plat.to_dict("records"):
        if r["type"] == "T" and r["hiera"]:
            dernier_titre = r["hiera"]
            structure.append({
                "hiera": r["hiera"],
                "niveau": r["hiera"].count(".") + 1,
                "titre": r["libelle"],
            })
        elif r["type"] in ("NT", "NT2") and dernier_titre and r["libelle"]:
            notes_titre.setdefault(dernier_titre, []).append(r["libelle"])
    df_struct = pd.DataFrame(structure).drop_duplicates("hiera")
    df_struct["notes"] = df_struct["hiera"].map(
        lambda h: "\n".join(notes_titre.get(h, [])))
    titres = dict(zip(df_struct["hiera"], df_struct["titre"]))

    # --- lignes d'acte (L) et notes d'acte (N / N2) -------------------------
    actes, notes = [], []
    courant = None
    for r in plat.to_dict("records"):
        if r["type"] == "L" and r["code"]:
            courant = r["code"]
            actes.append(r)
        elif r["type"] in ("N", "N2") and courant and r["code"] == courant:
            if r["libelle"]:
                notes.append({
                    "code": courant,
                    "ordre": len(notes),
                    "niveau": 2 if r["type"] == "N2" else 1,
                    "texte": r["libelle"],
                })

    df_actes = pd.DataFrame(actes)
    df_notes = pd.DataFrame(notes, columns=["code", "ordre", "niveau", "texte"])

    # Séparation actes / codes supplémentaires du chapitre 12.
    est_mod = df_actes["hiera"].str.startswith(HIERA_MODULATEURS)
    est_ext = df_actes["hiera"].str.startswith(HIERA_EXTENSIONS)

    ref_ext = df_actes[est_ext][["code", "libelle", "hiera"]].copy()
    ref_ext["sous_chapitre"] = ref_ext["hiera"].map(lambda h: titres.get(h, ""))
    ref_ext = ref_ext.drop(columns=["hiera"])
    ref_mod = df_actes[est_mod][["code", "libelle"]].copy()

    df_actes = df_actes[~(est_mod | est_ext)].copy()

    # Rattachement hiérarchique (chapitre / sous-chapitre / § / sous-§).
    for i in range(1, 5):
        num = df_actes["hiera"].map(
            lambda h, i=i: ".".join(h.split(".")[:i])
            if h.count(".") >= i - 1 else "")
        df_actes["chap%d_num" % i] = num
        df_actes["chap%d_titre" % i] = num.map(lambda n: titres.get(n, ""))

    df_actes["geste_comp"] = df_actes["hiera"].str.startswith("12.01").map(
        lambda b: "oui" if b else "")
    df_actes["code_plat"] = df_actes["code"].str.replace("+", "", regex=False)

    if df_notes.empty:
        txt_notes = pd.Series(dtype=object)
    else:
        txt_notes = df_notes.groupby("code")["texte"].apply("\n".join)
    df_actes["notes_txt"] = df_actes["code"].map(txt_notes).fillna("")
    df_actes["recherche"] = (
        df_actes["code"] + " " + df_actes["code_plat"] + " " + df_actes["libelle"]
    ).map(normaliser)
    df_actes["recherche_notes"] = (
        df_actes["notes_txt"] + " " + df_actes["consigne"]
    ).map(normaliser)
    df_actes = df_actes.drop(columns=["type"])

    # --- codes supprimés ----------------------------------------------------
    supprimes = []
    try:
        cs = _lire(f, "codes supprim", header=None)
    except SystemExit:
        cs = None
    if cs is not None:
        date_s = date_r = ""
        for r in cs.to_dict("records"):
            vals = [_s(v) for v in r.values()]
            a = vals[0] if vals else ""
            b = next((v for v in vals[1:] if v), "")
            if a.lower().startswith("supprim"):
                date_s = a.split(" ", 1)[-1].strip()
                date_r = b.split(":", 1)[-1].strip() if ":" in b else ""
            elif re.match(r"^[A-Z]{3}\+\d{3}$", a.replace(" ", "")):
                supprimes.append({
                    "code": a.replace(" ", ""),
                    "remplacement": b,
                    "date_suppression": date_s,
                    "date_remplacement": date_r,
                })
    df_suppr = pd.DataFrame(
        supprimes,
        columns=["code", "remplacement", "date_suppression", "date_remplacement"])

    return (df_actes, df_notes, df_struct, df_suppr, ref_mod, ref_ext,
            _version(f))


def lire_ponderations_csarr():
    """Pondérations CSARR (et CCAM comptant dans le score de réadaptation)."""
    f = trouver_source("pond_csarr", obligatoire=False)
    if not f:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ""
    p = _lire(f, "ponderations")
    pond = pd.DataFrame({
        "code": _col(p, "code"),
        "nomenclature": _col(p, "nomenclature"),
        "type": _col(p, "type"),
        "statut": _col(p, "statut"),
        "intervenant": _col(p, "intervenant").str.zfill(2),
        "lib_pmsi": _col(p, "lib_pmsi"),
        "hiera": _col(p, "hiera"),
        "liblong": _col(p, "liblong"),
        "ponderation": _col(p, "ponderation"),
        "validite": _col(p, "validite"),
        "debut": _col(p, "debut"),
        "fin": _col(p, "fin"),
        "mod_hw": _col(p, "mod_hw"),
        "mod_lj": _col(p, "mod_lj"),
        "mod_xh": _col(p, "mod_xh"),
        "mod_l3": _col(p, "mod_l3"),
    })
    pond = pond[pond["code"] != ""]

    m = _lire(f, "modulateurs")
    ref_mod = pd.DataFrame({
        "code": _col(m, "code"),
        "libelle": _col(m, "libelle"),
        "majoration_indiv": _col(m, "majoration pour les actes individuels"),
        "majoration_coll": _col(m, "majoration pour les actes collectifs"),
    })
    ref_mod = ref_mod[ref_mod["code"] != ""]

    i = _lire(f, "intervenants", header=None)
    inter = []
    for ligne in [_s(v) for v in i.iloc[:, 0].tolist()]:
        m2 = re.match(r"^(\d{2})\s+(.+)$", ligne)
        if m2:
            inter.append({"code": m2.group(1), "libelle": m2.group(2).strip()})
    return pond, ref_mod, pd.DataFrame(inter), _version(f)


def lire_transcodage():
    """Table de transcodage CSARR -> CSAR (avec type d'acte et commentaires)."""
    f = trouver_source("transcodage", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""
    t = _lire(f, "transcodage")
    out = pd.DataFrame({
        "code_csarr": _col(t, "code_old"),
        "libelle_csarr": _col(t, "libelle_old"),
        "code_csar": _col(t, "code_new"),
        "libelle_csar": _col(t, "libelle_new"),
        "commentaire": _col(t, "commentaire"),
        "type": _col(t, "type"),
    })
    return out[out["code_csarr"] != ""], _version(f)


def lire_gn_et_spe():
    """Groupes nosologiques, actes spécialisés CSARR/CCAM, libellés des groupes.

    Les listes d'actes spécialisés existent en deux versions dont les clés
    ``GN_liste`` ne sont pas écrites pareil (``0121_24`` côté CSARR,
    ``0121;0124`` côté CSAR) : c'est le **libellé** de la liste
    (``1_aff_cereb_et_autres``) qui sert de clé de jointure commune.
    """
    f = trouver_source("spe_csarr", obligatoire=False)
    ref_gn = pd.DataFrame()
    spe_csarr = pd.DataFrame()
    if f:
        g = _lire(f, "gn_liste")
        ref_gn = pd.DataFrame({
            "gn": _col(g, "gn"),
            "libelle": _col(g, "lib_gn"),
            "gn_liste": _col(g, "gn_liste"),
            "gr_spe_unique": _col(g, "gr spe unique").map(
                lambda v: "oui" if _oui(v) else ""),
        })
        ref_gn = ref_gn[ref_gn["gn"].str.match(r"^\d{4}$")].copy()
        ref_gn["gn_liste"] = ref_gn["gn_liste"].map(
            lambda v: "" if v.strip().upper().startswith("PAS DE LISTE") else v)
        ref_gn["cm"] = ref_gn["gn"].str[:2]

        t = _lire(f, "total_liste")
        spe_csarr = pd.DataFrame({
            "code": _col(t, "acte"),
            "hiera": _col(t, "hier"),
            "nomenclature": _col(t, "type_acte"),
            "libelle": _col(t, "libelle"),
            "cm": _col(t, "cm"),
            "gn_liste": _col(t, "gn_liste"),
            "libelle_gn": _col(t, "libelle_gn_liste"),
        })
        spe_csarr = spe_csarr[spe_csarr["code"] != ""]

        # Libellé de liste manquant côté GN : on le reprend de la table des
        # actes, seule à le porter.
        libs = dict(zip(spe_csarr["gn_liste"], spe_csarr["libelle_gn"]))
        ref_gn["libelle_gn_liste"] = ref_gn["gn_liste"].map(
            lambda v: libs.get(v, ""))

    f2 = trouver_source("groupes", obligatoire=False)
    groupes = pd.DataFrame()
    if f2:
        lg = _lire(f2, "libelles")
        groupes = pd.DataFrame({
            "quoi": _col(lg, "quoi"),
            "code": _col(lg, "code"),
            "lib_court": _col(lg, "lib_court"),
            "lib_long": _col(lg, "lib_long"),
        })
        groupes = groupes[groupes["code"] != ""]

    return ref_gn, spe_csarr, groupes, _version(f), _version(f2)


def lire_ponderation_modulateurs_csar():
    """Pondérations et majorations portées par les modulateurs CSAR.

    Ces valeurs ne figurent pas dans le classeur CSAR de codage : elles sont
    publiées avec le manuel de groupage. Le modulateur de temps porte une
    pondération propre (T0=25 … T4=140) qui entre en concurrence avec celle de
    l'acte — c'est la plus élevée des deux qui est retenue — tandis que le
    modulateur de lieu apporte une majoration, différente selon que l'acte est
    individuel ou collectif.
    """
    f = trouver_source("csar_gme", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""
    m = _lire(f, "modulateur_modalite_extension")
    out = pd.DataFrame({
        "type": _col(m, "type"),
        "variable": _col(m, "variable"),
        "modalite": _col(m, "modalite"),
        "niveau": _col(m, "niveau_ou_module"),
        "libelle": _col(m, "libelle"),
        "ponderation": _col(m, "ponderation"),
        "majoration_indiv": _col(
            m, "majoration de ponderation des actes csar individuels"),
        "majoration_coll": _col(
            m, "majoration de ponderation des actes csar collectifs"),
    })
    return out[out["modalite"] != ""], _version(f)


def _col_sigle(df, sigle):
    """Colonne dont le nom porte le sigle entre parenthèses, ex. « (TZF1) »."""
    marque = "(" + sigle.lower() + ")"
    for c in df.columns:
        if str(c).endswith(marque):
            return df[c]
    return pd.Series([""] * len(df), index=df.index, dtype=object)


def lire_tarifs():
    """Tarifs des GMT et coefficients de valorisation (arrêté tarifaire).

    Chaque GME est tarifé par un à quatre GMT : le GMT « principal » (codes
    0xxx et 1xxx), le GMT hebdomadaire des séjours de plus de 90 jours (7xxx)
    et le GMT des séjours de moins de 8 jours terminés par transfert, mutation
    ou décès (8xxx). Les soins palliatifs ont trois GMT principaux, un par lieu
    de prise en charge.

    Les trois blocs partagent la même structure de zones : pour 7xxx et 8xxx,
    ``DZF = FZF = 7`` et ``SZB = SZH = TZF1 / 7``, si bien que la formule de
    zone y dégénère en un simple prix de journée.
    """
    f = trouver_source("tarifs", obligatoire=False)
    if not f:
        return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                pd.DataFrame(), "")

    t = _lire(f, GRILLE_TARIFAIRE, header=3)
    tarifs = pd.DataFrame({
        "gmt": _col(t, "gmt"),
        "gme": _col(t, "gme"),
        "libelle": _col(t, "libelle"),
        "dzf": _col_sigle(t, "DZF"),
        "fzf": _col_sigle(t, "FZF"),
        "tzb": _col_sigle(t, "TZB"),
        "szb": _col_sigle(t, "SZB"),
        "tzf1": _col_sigle(t, "TZF1"),
        "tzf2": _col_sigle(t, "TZF2"),
        "tzf3": _col_sigle(t, "TZF3"),
        "szh": _col_sigle(t, "SZH"),
    })
    tarifs = tarifs[tarifs["gmt"].str.match(r"^\d{4}$")].copy()
    tarifs["bloc"] = tarifs["gmt"].str[0].map(
        lambda c: "hebdomadaire" if c == "7"
        else ("court" if c == "8" else "principal"))
    tarifs["gr"] = tarifs["gme"].str[4]
    tarifs["temps_partiel"] = tarifs["gr"].isin(list("HIJKL")).map(
        lambda b: "oui" if b else "")

    g = _lire(f, "coef geo", header=3)
    coef_geo = pd.DataFrame({
        "zone": _col(g, "zone geographique"),
        "coefficient": _col(g, "valeur du coefficient"),
    })
    coef_geo = coef_geo[coef_geo["zone"] != ""]

    s = _lire(f, "coef SEGUR", header=3)
    coef_segur = pd.DataFrame({
        "categorie": _col(s, "categorie d etablissement", "categorie"),
        "coefficient": _col(s, "valeur du coefficient"),
    })
    coef_segur = coef_segur[coef_segur["categorie"] != ""]

    pts = _lire(f, "PTS", header=3)
    pts = pts.rename(columns={c: str(c) for c in pts.columns})
    pts = pts[pts[pts.columns[0]] != ""]

    return tarifs, coef_geo, coef_segur, pts, _version(f)


def _code_cim(v):
    """Nettoie un code CIM-10 du fichier ATIH.

    Trois codes sortent du format : ``U11.9`` et ``U12.9`` portent un point, et
    ``Z5185`` traîne un espace insécable de largeur nulle.
    """
    return _s(v).replace("​", "").replace(".", "").replace(" ", "").upper()


def lire_cim():
    """Codes CIM-10 à usage SMR : catégorie majeure, positions, listes.

    La colonne ``cm`` porte la catégorie majeure vers laquelle le code oriente,
    la valeur ``90`` signifiant « n'oriente vers aucune CM ». La colonne
    ``orientant_deuxieme_intention`` marque les 357 codes — essentiellement des
    symptômes — qui, en position de MMP, laissent la main à l'affection
    étiologique.

    ``profil2`` donne sur 4 caractères les positions autorisées, dans l'ordre
    FPP / MMP / AE / DAS. Elle ne sert pas au groupage mais aux contrôles de
    validité du codage.

    Les colonnes ``liste_1`` à ``liste_4`` **partitionnent** les listes de
    diagnostics en quatre ensembles disjoints : ce n'est pas un ordre de
    priorité et elles comportent des trous. Il faut balayer les quatre et
    normaliser en une table (code, liste).
    """
    f = trouver_source("cim", obligatoire=False)
    if not f:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ""

    df = _lire(f, "DIAG10")
    diag = pd.DataFrame({
        "code": _col(df, "code").map(_code_cim),
        "libelle": _col(df, "lib"),
        "cm": _col(df, "cm").str.zfill(2),
        "profil2": _col(df, "profil2"),
        "orientant_2e": _col(df, "orientant_deuxieme_intention").map(
            lambda v: "oui" if _oui(v) else ""),
        "cma": _col(df, "cma"),
    })
    diag = diag[diag["code"] != ""].drop_duplicates("code")
    # profil2 = FPP / MMP / AE / DAS
    for i, position in enumerate(("fpp", "mmp", "ae", "das")):
        diag[position] = diag["profil2"].map(
            lambda p, i=i: "oui" if len(p) > i and p[i].upper() == "O" else "")

    couples, libelles = [], {}
    for n in range(1, 5):
        colonne = _col(df, "liste_%d" % n)
        for code, cellule in zip(diag["code"], colonne.reindex(diag.index)):
            texte = _s(cellule)
            if len(texte) >= 4 and texte[:4].isdigit():
                couples.append({"code": code, "liste": texte[:4]})
                libelles.setdefault(texte[:4], texte[4:].strip(" -"))
    listes = pd.DataFrame(couples,
                          columns=["code", "liste"]).drop_duplicates()
    lib_listes = pd.DataFrame(
        sorted(libelles.items()), columns=["liste", "libelle"])
    return diag, listes, lib_listes, _version(f)


def lire_gn_tests():
    """Arbres de décision menant au groupe nosologique, un par CM.

    Chaque nœud porte un test obligatoire et parfois un second ; le premier
    nœud entièrement satisfait, dans l'ordre croissant de ``Ordre_intra_CM``,
    donne le GN. Le parsing des libellés de test est figé ici plutôt que refait
    à chaque groupage.
    """
    f = trouver_source("gn_tests", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""

    t = _lire(f, "GN_listes_test")
    lignes = []
    for cm, ordre, t1, t2, gn_lib, gn in zip(
            _col(t, "cm"), _col(t, "ordre_intra_cm"), _col(t, "test_1"),
            _col(t, "test_2"), _col(t, "groupe nosologique"), _col(t, "gn")):
        if not _s(gn):
            continue
        m1 = RE_TEST_GN.search(_s(t1).replace("\xa0", " "))
        m2 = RE_TEST_GN.search(_s(t2).replace("\xa0", " "))
        lignes.append({
            "cm": _s(cm).zfill(2),
            "ordre": int(_s(ordre) or 0),
            "t1_pos": m1.group(1) if m1 else "",
            "t1_liste": m1.group(2) if m1 else "",
            "t2_pos": m2.group(1) if m2 else "",
            "t2_liste": m2.group(2) if m2 else "",
            "gn": _s(gn).zfill(4),
            "libelle_gn": _s(gn_lib),
            # Un seul nœud teste les DAS : les fractures multiples, qui
            # exigent en plus que le DAS classant porte sur une topographie
            # différente de celle du code classant en MMP ou AE.
            "regle_speciale": "fractures_multiples" if (m2 and
                                                        m2.group(1) == "DAS")
            else "",
        })
    return pd.DataFrame(lignes).sort_values(["cm", "ordre"]), _version(f)


def lire_gl():
    """Table des niveaux de lourdeur, un GR d'hospitalisation complète par ligne.

    Chaque colonne correspond à une valeur possible d'une des quatre variables
    — classe d'âge, dépendance cognitive, dépendance physique, statut
    post-chirurgical — et la cellule porte le niveau de lourdeur (A, B ou C)
    que cette valeur entraîne. Le niveau retenu est le **maximum** des quatre.

    Un tiret signale une classe d'âge inapplicable au groupe : elle est alors
    sans contribution. Quatre lignes portent une règle combinée, où le niveau
    de la dépendance physique dépend en outre de l'âge ; elle est laissée telle
    quelle et interprétée au moment du groupage.

    L'en-tête réel est en deuxième ligne : la première n'est qu'un bandeau de
    regroupement fusionné, qui ne couvre même pas toutes les colonnes.
    """
    f = trouver_source("gl", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""
    r = _lire(f, "regles", header=1)
    colonnes = ["gr", "a0_3", "a4_12", "a13_17", "a18_60", "a61_70", "a71_75",
                "a76_80", "a81_85", "a86_plus", "g02_06", "g07_08", "y04_08",
                "y09_12", "y13_16", "c_sans", "c_avec"]
    table = pd.DataFrame({c: _col(r, c) for c in colonnes})
    table = table[table["gr"].str.match(r"^\d{4}[A-Z]$")].copy()
    table["combinee"] = _col(r, "regles_combinees").map(
        lambda v: "oui" if _oui(v) else "")
    return table, _version(f)


def lire_cma():
    """Exclusions des complications et morbidités associées, et CCAM valant CMA.

    Un diagnostic associé ne vaut marqueur de sévérité que s'il n'est pas
    *exclu* par l'un des diagnostics qui ont orienté le séjour vers son groupe
    nosologique : une complication déjà impliquée par la pathologie traitée
    n'apporte pas de sévérité supplémentaire.

    Le fichier donne, pour chaque code CMA, la liste des codes qui l'annulent.
    Sur 755 lignes, 138 portent la liste en clair et 617 renvoient à celle d'un
    autre code. Après résolution, ces 755 listes ne recouvrent que 136 listes
    distinctes : on les stocke dédupliquées, faute de quoi la table
    dépasserait 1,6 million de couples.

    Les codes sont écrits ici avec un point (``A00.0``) alors que le
    référentiel CIM les stocke sans (``A000``) : il faut normaliser.
    """
    f = trouver_source("cma_exclusion", obligatoire=False)
    appartenance = pd.DataFrame()
    membres = pd.DataFrame()
    if f:
        e = _lire(f, "CMA_Exclusions")
        codes = _col(e, "diagnostic associe cma")
        listes = _col(e, "liste")

        brut, renvois = {}, {}
        for code, contenu in zip(codes, listes):
            code = _code_cim(code)
            if not code:
                continue
            m = RE_MEME_LISTE.match(str(contenu).strip())
            if m:
                renvois[code] = _code_cim(m.group(1))
            else:
                brut[code] = {_code_cim(x) for x in str(contenu).split()
                              if _code_cim(x)}

        # Chaque liste explicite reçoit un identifiant ; les renvois pointent
        # vers l'identifiant de leur référence.
        identifiants = {code: "L%03d" % (i + 1)
                        for i, code in enumerate(sorted(brut))}
        couples = []
        for code, liste in brut.items():
            couples.append({"cma": code, "liste": identifiants[code]})
        orphelins = 0
        for code, reference in renvois.items():
            if reference in identifiants:
                couples.append({"cma": code, "liste": identifiants[reference]})
            else:
                orphelins += 1
        appartenance = pd.DataFrame(couples, columns=["cma", "liste"])

        lignes = []
        for code, liste in brut.items():
            identifiant = identifiants[code]
            for membre in sorted(liste):
                lignes.append({"liste": identifiant, "code": membre})
        membres = pd.DataFrame(lignes, columns=["liste", "code"])
        if orphelins:
            print("  %d renvoi(s) d'exclusion sans cible" % orphelins)

    f2 = trouver_source("cma_ccam", obligatoire=False)
    ccam = pd.DataFrame()
    if f2:
        c = _lire(f2, "ccam")
        ccam = pd.DataFrame({
            "code": _col(c, "code"),
            "libelle": _col(c, "libelle_acte", "libelle"),
        })
        ccam = ccam[ccam["code"] != ""].copy()
        # Le fichier code sur 8 caractères, le 8e portant l'activité ; le RHS
        # et les autres référentiels ATIH utilisent 7 caractères.
        ccam["code7"] = ccam["code"].str[:7]

    return appartenance, membres, ccam, _version(f), _version(f2)


def lire_gr():
    """Groupes de réadaptation et seuils de score par groupe nosologique."""
    f = trouver_source("gr", obligatoire=False)
    if not f:
        return pd.DataFrame(), ""
    g = _lire(f, "seuils_et_groupe", header=1)
    g = g[_col(g, "gn").str.match(r"^\d{4}$")]
    return g, _version(f)


# ---------------------------------------------------------------------------
# Construction de la base
# ---------------------------------------------------------------------------

def construire(verbose=True):
    def log(msg):
        if verbose:
            print(msg)

    os.makedirs(DOSSIER_DATA, exist_ok=True)

    log("Lecture du CSAR (actes, modulateurs, intervenants)…")
    (csar_actes, csar_mods, csar_inter, ref_mod_csar,
     ref_tm, tac, v_csar) = lire_csar()

    log("Lecture du CSARR (actes, notes, hiérarchie)…")
    (csarr_actes, csarr_notes, csarr_struct, csarr_suppr,
     ref_mod_csarr_lib, ref_ext_csarr, v_csarr) = lire_csarr()

    log("Lecture des pondérations, du transcodage et des seuils…")
    pond_csar, v_pcsar = lire_ponderations_csar()
    pond_csarr, ref_mod_csarr, inter_csarr, v_pcsarr = lire_ponderations_csarr()
    spe_csar, v_spe = lire_spe_csar()
    transco, v_transco = lire_transcodage()
    gr, v_gr = lire_gr()
    ref_gn, spe_csarr, groupes, v_spe_csarr, v_groupes = lire_gn_et_spe()
    pond_mod_csar, v_csar_gme = lire_ponderation_modulateurs_csar()
    tarifs, coef_geo, coef_segur, pts, v_tarifs = lire_tarifs()

    log("Lecture des données de groupage (CIM, arbres GN, lourdeur, CMA)…")
    cim_diag, cim_listes, lib_listes, v_cim = lire_cim()
    gn_tests, v_gn_tests = lire_gn_tests()
    gl_regles, v_gl = lire_gl()
    cma_listes, cma_membres, cma_ccam, v_cma, v_cma_ccam = lire_cma()

    # Le libellé de liste est la clé commune aux deux nomenclatures : on le
    # complète côté CSAR quand il manque, à partir de sa propre colonne.
    if not spe_csar.empty and not ref_gn.empty:
        par_libelle = dict(zip(ref_gn["libelle_gn_liste"], ref_gn["gn_liste"]))
        spe_csar = spe_csar.copy()
        spe_csar["gn_liste_csarr"] = spe_csar["libelle_gn"].map(
            lambda v: par_libelle.get(v, ""))

    # Transcodage : la table d'aide au codage (annexe 4) fait foi car elle est
    # publiée dans le même classeur que les actes. Le fichier autonome
    # Transcodage_CSARR_CSAR.xlsx est une publication antérieure — il renvoie
    # encore vers des codes CSAR supprimés depuis (11S14 à 11S16) ; on n'en
    # reprend que les commentaires, pour les couples de codes inchangés.
    divergences = 0
    if tac.empty:
        transco = transco.assign(commentaire=transco.get("commentaire", ""))
    else:
        transco_ancien = transco
        transco = tac.copy()
        transco["type"] = transco["code_csar"].str[2].where(
            transco["code_csar"] != "ZZZ", "")
        transco["commentaire"] = ""
        if not transco_ancien.empty:
            comm = {
                (a, b): c
                for a, b, c in zip(transco_ancien["code_csarr"],
                                   transco_ancien["code_csar"],
                                   transco_ancien["commentaire"]) if c
            }
            transco["commentaire"] = [
                comm.get((a, b), "")
                for a, b in zip(transco["code_csarr"], transco["code_csar"])
            ]
            ancien = dict(zip(transco_ancien["code_csarr"],
                              transco_ancien["code_csar"]))
            divergences = sum(
                1 for a, b in zip(transco["code_csarr"], transco["code_csar"])
                if a in ancien and ancien[a] != b
            )

    # Référentiel des intervenants : CSAR (34 codes) + marquage CSARR.
    ref_inter = (
        csar_inter[["code_inter", "lib_inter"]]
        .drop_duplicates()
        .rename(columns={"code_inter": "code", "lib_inter": "libelle"})
        .sort_values("code")
    )
    codes_csarr = set(inter_csarr["code"]) if not inter_csarr.empty else set()
    ref_inter["csarr"] = ref_inter["code"].map(
        lambda c: "oui" if c in codes_csarr else "")

    # Libellés CSARR des modulateurs (issus du chapitre 12.02 du CSARR).
    if not ref_mod_csarr.empty and not ref_mod_csarr_lib.empty:
        libs = dict(zip(ref_mod_csarr_lib["code"], ref_mod_csarr_lib["libelle"]))
        ref_mod_csarr["libelle"] = [
            libs.get(c, l)
            for c, l in zip(ref_mod_csarr["code"], ref_mod_csarr["libelle"])
        ]
    elif ref_mod_csarr.empty:
        ref_mod_csarr = ref_mod_csarr_lib.assign(
            majoration_indiv="", majoration_coll="")

    meta = {
        "version_csar": v_csar,
        "version_csar_assoc": os.path.basename(trouver_source("csar_assoc")),
        "version_csarr": v_csarr,
        "source_transcodage": "TAC (annexe 4) de " + v_csar,
        "version_transcodage": v_transco,
        "transcodage_divergences": str(divergences),
        "version_pond_csar": v_pcsar,
        "version_pond_csarr": v_pcsarr,
        "version_spe_csar": v_spe,
        "version_spe_csarr": v_spe_csarr,
        "version_csar_gme": v_csar_gme,
        "version_tarifs": v_tarifs,
        "version_cim": v_cim,
        "version_gn_tests": v_gn_tests,
        "nb_codes_cim": str(len(cim_diag)),
        "nb_noeuds_gn": str(len(gn_tests)),
        "version_gl": v_gl,
        "version_cma": v_cma,
        "version_cma_ccam": v_cma_ccam,
        "grille_tarifaire": GRILLE_TARIFAIRE,
        "nb_gmt": str(tarifs["gmt"].nunique() if not tarifs.empty else 0),
        "version_groupes": v_groupes,
        "version_gr": v_gr,
        "nb_gn": str(len(ref_gn)),
        "nb_actes_csar": str(len(csar_actes)),
        "nb_actes_csarr": str(len(csarr_actes)),
        "nb_transcodages": str(len(transco)),
    }

    tables = {
        "csar_actes": csar_actes,
        "csar_modulateurs": csar_mods,
        "csar_intervenants": csar_inter,
        "csar_ponderations": pond_csar,
        "csar_spe": spe_csar,
        "csarr_actes": csarr_actes,
        "csarr_notes": csarr_notes,
        "csarr_structure": csarr_struct,
        "csarr_supprimes": csarr_suppr,
        "csarr_ponderations": pond_csarr,
        "transcodage": transco,
        "ref_modulateurs_csar": ref_mod_csar,
        "ref_modulateurs_csarr": ref_mod_csarr,
        "ref_extensions_csarr": ref_ext_csarr,
        "ref_transco_modulateurs": ref_tm,
        "ref_intervenants": ref_inter,
        "ref_gr": gr,
        "ref_gn": ref_gn,
        "ref_ponderation_modulateurs_csar": pond_mod_csar,
        "tarifs_gmt": tarifs,
        "cim_diag": cim_diag,
        "cim_listes": cim_listes,
        "ref_listes_diag": lib_listes,
        "gn_tests": gn_tests,
        "gl_regles": gl_regles,
        "cma_exclusion_listes": cma_listes,
        "cma_exclusion_membres": cma_membres,
        "ref_cma_ccam": cma_ccam,
        "ref_coef_geo": coef_geo,
        "ref_coef_segur": coef_segur,
        "ref_pts": pts,
        "ref_groupes": groupes,
        "csarr_spe": spe_csarr,
        "meta": pd.DataFrame(sorted(meta.items()), columns=["cle", "valeur"]),
    }

    log("Écriture de " + os.path.relpath(BASE_SQLITE, RACINE) + "…")
    if os.path.exists(BASE_SQLITE):
        os.remove(BASE_SQLITE)
    con = sqlite3.connect(BASE_SQLITE)
    for nom, df in tables.items():
        df.to_sql(nom, con, index=False, if_exists="replace")
    for req in (
        "CREATE INDEX i_csar_code ON csar_actes(code)",
        "CREATE INDEX i_csarr_code ON csarr_actes(code)",
        "CREATE INDEX i_csar_mod ON csar_modulateurs(code)",
        "CREATE INDEX i_csar_int ON csar_intervenants(code)",
        "CREATE INDEX i_csarr_notes ON csarr_notes(code)",
        "CREATE INDEX i_tr_csarr ON transcodage(code_csarr)",
        "CREATE INDEX i_tr_csar ON transcodage(code_csar)",
        "CREATE INDEX i_cim_code ON cim_diag(code)",
        "CREATE INDEX i_cim_liste_code ON cim_listes(code)",
        "CREATE INDEX i_cim_liste_liste ON cim_listes(liste)",
        "CREATE INDEX i_gn_cm ON gn_tests(cm, ordre)",
        "CREATE INDEX i_gl_gr ON gl_regles(gr)",
        "CREATE INDEX i_cma_liste ON cma_exclusion_listes(cma)",
        "CREATE INDEX i_cma_membre ON cma_exclusion_membres(liste, code)",
        "CREATE INDEX i_gmt_gme ON tarifs_gmt(gme)",
    ):
        con.execute(req)
    con.commit()
    con.close()

    log("  %d actes CSAR · %d actes CSARR · %d transcodages"
        % (len(csar_actes), len(csarr_actes), len(transco)))
    return meta


if __name__ == "__main__":
    construire()
