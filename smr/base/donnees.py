# -*- coding: utf-8 -*-
"""
PMSI SMR — accès aux données et référentiels partagés par l'application.

Regroupe le chargement de ``data/smr.sqlite``, les référentiels issus des
guides ATIH (règles de codage, listes fermées) et les fonctions de
recherche utilisées par les pages CSARR et CSAR.
"""

import os
import re
import sqlite3

import pandas as pd
import streamlit as st

from smr.base import construction
from smr.base.construction import CHAPITRES_CSAR, TYPES_CSAR, normaliser
from smr.chemins import BASE_SQLITE
from smr.synonymes import synonymes

# ---------------------------------------------------------------------------
# Constantes de navigation
# ---------------------------------------------------------------------------

P_CSARR = "🔎 Recherche d'actes CSARR"
P_CSAR = "🔎 Recherche d'actes CSAR"
P_FAV = "⭐ Favoris"
P_REF = "📚 Références"
P_VALO = "💶 Séjour & valorisation"
PAGES = [P_CSARR, P_CSAR, P_FAV, P_VALO, P_REF]

RE_CODE_CSAR = re.compile(r"^\d{1,2}[ESMP]?\d{0,2}$")
RE_CODE_CSARR = re.compile(r"^[A-Z]{1,3}\d{0,3}$")

# ---------------------------------------------------------------------------
# Référentiels issus des guides (listes fermées, non présentes dans les
# fichiers tabulaires) — voir la page Références pour les sources.
# ---------------------------------------------------------------------------

# Modulateurs de temps du CSAR (guide CSAR § 1.5). N'existent pas en CSARR.
MOD_TEMPS = {
    "T0": "Séance d'une demi-heure (< 45 minutes)",
    "T1": "Séance de 1 heure [45 ; 70 minutes[",
    "T2": "Séance de 1 heure et demie [70 ; 100 minutes[",
    "T3": "Séance de 2 heures [100 ; 130 minutes[",
    "T4": "Séance de plus de 2 heures (>= 130 minutes)",
}

# Modulateurs de lieu du CSAR (guide CSAR § 1.5).
MOD_LIEU_CSAR = {
    "L1": "Réalisation de l'acte hors établissement (milieu urbain ou naturel)",
    "L2": "Réalisation de l'acte sur le lieu d'activité du patient "
          "(domicile, travail…)",
    "L3": "Réalisation de l'acte dans un autre établissement",
}

# Modulateurs de technicité — plateaux techniques spécialisés (liste fermée,
# arrêté du 26 mai 2023 / note DGOS/R4/2023/172).
MOD_TECHNICITE = {
    "QM": "Plateau technique spécialisé de balnéothérapie",
    "QS": "Plateau technique spécialisé de rééducation assistée du membre "
          "supérieur",
    "QF": "Plateau technique spécialisé de rééducation intensive des membres "
          "inférieurs",
    "QI": "Plateau technique spécialisé d'isocinétisme",
    "QC": "Plateau technique spécialisé de rééducation du retour à la conduite",
    "QQ": "Plateau technique spécialisé d'analyse quantifiée de la marche et "
          "du mouvement",
}

# Seuls QS, QQ et QC disposent de deux modules / niveaux de complexité.
MOD_AVEC_NIVEAU = {
    "QS": ("Module 1 : dispositif d'assistance robotisée",
           "Module 2 : dispositif d'assistance non robotisée avec travail de "
           "l'intention du mouvement"),
    "QQ": ("Niveau 1 : laboratoire d'analyse quantifiée simple",
           "Niveau 2 : laboratoire d'analyse combinée et synchronisée"),
    "QC": ("Module 1 : simulateur de conduite",
           "Module 2 : véhicule adapté"),
}

# Modulateurs propres au CSARR (supprimés ou fusionnés dans le CSAR).
MOD_LIEU_CSARR = {
    "ZV": "Réalisation de l'acte au lit du patient",
    "ME": "Réalisation de l'acte en salle de soins",
    "TF": "Réalisation de l'acte en établissement, en extérieur sans équipement",
    "RW": "Réalisation de l'acte en établissement, en extérieur avec équipement",
    "HW": "Réalisation de l'acte hors établissement en milieu urbain",
    "LJ": "Réalisation de l'acte hors établissement en milieu naturel",
    "XH": "Réalisation de l'acte sur le lieu d'activité du patient",
    "L3": "Réalisation de l'acte dans un autre établissement",
}
MOD_PATIENT_CSARR = {"EZ": "Réalisation fractionnée de l'acte"}

# Étapes de réalisation des actes d'appareillage du CSARR (guide § 3.3.2).
ETAPES_APPAREILLAGE = {
    "A": "Prise de mesure, moulage, empreinte ou acquisition numérique",
    "B": "Fabrication proprement dite",
    "C": "Mise à disposition ou fourniture",
}

TYPES_CSARR_POND = {
    "D": "Acte dédié (1 patient)",
    "D/ND": "Acte dédié ou non dédié (2 à 8 patients)",
    "C": "Acte collectif (2 à 25 patients)",
    "A": "Appareillage avec étapes A / B / C",
    "PP": "Acte pluriprofessionnel (nombre d'intervenants obligatoire)",
    "CCAM": "Acte CCAM comptant dans le score de réadaptation",
}

STATUTS_POND = {
    "pond_u": "Pondération unique pour tous les intervenants",
    "diff inter": "Pondération différenciée selon les intervenants",
    "pond 0": "Pondération nulle pour certains couples acte / intervenant",
    "pond 0 / diff inter": "Pondération nulle pour certains couples acte / "
                           "intervenant, différenciée pour les autres",
    "CCAM": "Acte CCAM",
}

AIDE = {
    "Code": "Code de l'acte. CSAR : 5 caractères (chapitre + objectif + "
            "compteur). CSARR : 7 caractères (topographie + action + voie).",
    "Libellé": "Libellé officiel de l'acte.",
    "Intervenant": "Catégorie professionnelle de l'intervenant qui code "
                   "l'acte, c'est-à-dire celui à qui incombe la "
                   "responsabilité de l'acte.",
    "Pondération": "Poids de l'acte servant au calcul des scores de "
                   "réadaptation (par séjour et par jour) utilisés pour "
                   "l'orientation en groupe de réadaptation.",
    "Attendu": "L'intervenant figure dans la liste indicative des "
               "intervenants attendus pour cet acte (guide CSAR § 2.4).",
}


# ---------------------------------------------------------------------------
# Chargement
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Construction de la base SMR…")
def charger():
    """Charge (et construit au besoin) la base locale. Renvoie un dict."""
    if not os.path.exists(BASE_SQLITE):
        construction.construire(verbose=False)
    con = sqlite3.connect(BASE_SQLITE)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    d = {t: pd.read_sql('SELECT * FROM "%s"' % t, con).fillna("")
         for t in tables}
    con.close()
    d["meta"] = dict(zip(d["meta"]["cle"], d["meta"]["valeur"]))
    d["ref_intervenants"] = d["ref_intervenants"].sort_values("code")
    d["lib_intervenant"] = dict(zip(d["ref_intervenants"]["code"],
                                    d["ref_intervenants"]["libelle"]))
    d["lib_csar"] = dict(zip(d["csar_actes"]["code"],
                             d["csar_actes"]["libelle"]))
    d["lib_csarr"] = dict(zip(d["csarr_actes"]["code"],
                              d["csarr_actes"]["libelle"]))
    _enrichir(d)
    return d


def _enrichir(d):
    """Colonnes de synthèse et index utilisés à l'exécution."""
    _indexer_cim(d)
    _indexer_ccam(d)
    # CSAR : résumé des codes supplémentaires autorisés.
    m = d["csar_modulateurs"].set_index("code")

    def _resume_csar(code):
        if code not in m.index:
            return ""
        r = m.loc[code]
        bouts = []
        if r["temps"] == "oui":
            bouts.append("T0-T4")
        lieux = [c.upper() for c in ("l1", "l2", "l3") if r[c] == "oui"]
        if lieux:
            bouts.append(" ".join(lieux))
        tech = [c.upper() for c in ("qm", "qi", "qf", "qs", "qq", "qc")
                if r[c] == "oui"]
        if tech:
            bouts.append(" ".join(tech))
        return " · ".join(bouts)

    a = d["csar_actes"]
    a["mods_txt"] = a["code"].map(_resume_csar)
    coll = dict(zip(d["csar_modulateurs"]["code"], d["csar_modulateurs"]["coll"]))
    a["collectif_txt"] = a["code"].map(
        lambda c: "Oui" if coll.get(c) == "oui" else "")
    pond = d["csar_ponderations"]
    if not pond.empty:
        num = pd.to_numeric(pond["ponderation"], errors="coerce")
        maxi = num.groupby(pond["code"]).max()
        a["pond_max"] = a["code"].map(maxi).map(
            lambda v: "" if pd.isna(v) else ("%g" % v))
    else:
        a["pond_max"] = ""
    spe = d["csar_spe"]
    if not spe.empty:
        n_spe = spe[spe["gn_liste"] != "sans_objet"].groupby(
            "code")["libelle_gn"].nunique()
        a["spe_txt"] = a["code"].map(n_spe).map(
            lambda v: "" if pd.isna(v) else "%d liste(s)" % int(v))
    else:
        a["spe_txt"] = ""

    # CSARR : modulateurs, cible de transcodage.
    b = d["csarr_actes"]
    b["mods_txt"] = b.apply(
        lambda r: " · ".join(
            x.replace(";", " ").strip()
            for x in (r["mod_lieu"], r["mod_patient"], r["mod_tech"]) if x),
        axis=1)
    cible = (d["transcodage"].drop_duplicates("code_csarr")
             .set_index("code_csarr")["code_csar"])
    b["csar_cible"] = b["code"].map(cible).fillna("")
    pc = d["csarr_ponderations"]
    if not pc.empty:
        valides = pc[pc["validite"] != ""]
        num = pd.to_numeric(valides["ponderation"], errors="coerce")
        maxi = num.groupby(valides["code"]).max()
        b["pond_max"] = b["code"].map(maxi).map(
            lambda v: "" if pd.isna(v) else ("%g" % v))
    else:
        b["pond_max"] = ""


# ---------------------------------------------------------------------------
# Navigation et présentation
# ---------------------------------------------------------------------------

def badge(texte, style="gris", info=""):
    """Pastille colorée, avec infobulle facultative."""
    attr = ' title="%s"' % info.replace('"', "'") if info else ""
    return '<span class="badge badge-%s"%s>%s</span>' % (style, attr, texte)


def aller_a(code, nomenclature):
    """Navigation interne : ouvre la fiche d'un acte dans la bonne page.

    On ne peut pas modifier l'état d'un widget déjà instancié pendant le run
    en cours ; la cible est mémorisée et consommée au début du run suivant.
    """
    st.session_state["nav_cible"] = (nomenclature, code)
    st.rerun()


def lien_acte(code, nomenclature, libelle="", cle="", largeur="content"):
    """Bouton ouvrant la fiche d'un acte. Renvoie True si cliqué."""
    texte = code if not libelle else "%s — %s" % (code, libelle)
    if st.button(texte, key=cle or ("go_%s_%s" % (nomenclature, code)),
                 width=largeur):
        aller_a(code, nomenclature)
        return True
    return False


def puces(texte, prefixe="- "):
    """Transforme un texte multiligne ATIH en liste markdown."""
    lignes = [l.strip(" -•\t") for l in str(texte).split("\n") if l.strip()]
    return "\n".join(prefixe + l for l in lignes)


def historiser(code, nomenclature):
    """Mémorise un acte consulté, sans déplacer ceux déjà listés.

    Les entrées ne sont pas reclassées par récence. Un classement du plus
    récent au plus ancien fait bouger les boutons de la colonne de gauche à
    chaque consultation : on vise un acte, la liste se réordonne, et le clic
    suivant tombe sur son voisin. Une liste stable se clique du premier coup.
    """
    hist = st.session_state.setdefault("historique", [])
    cle = (nomenclature, code)
    if cle in hist:
        return
    hist.append(cle)
    del hist[:-10]


# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------

def _plein_texte(df, requete, dans_notes):
    """Tous les mots de la requête doivent être présents ; tri par pertinence."""
    mots = normaliser(requete).split()
    if not mots:
        return df.head(0)
    champ = df["recherche"]
    if dans_notes:
        champ = champ + " " + df["recherche_notes"]
    masque = pd.Series(True, index=df.index)
    for m in mots:
        masque &= champ.str.contains(re.escape(m), na=False)
    res = df[masque].copy()
    if res.empty:
        return res
    res["_pos"] = res["recherche"].str.find(mots[0]).replace(-1, 9999)
    res["_lg"] = res["libelle"].str.len()
    return res.sort_values(["_pos", "_lg", "code"]).drop(
        columns=["_pos", "_lg"])


def _presence(champ, mot, entier=False):
    """Lignes dont le texte contient le mot saisi.

    Un pluriel introuvable est cherché au singulier, en début de mot :
    « orthèses » retrouve « orthèse », sans que « repas » ne ramène
    « préparation ». Un mot à trait d'union l'est aussi sans le trait.
    """
    if entier:
        return champ.str.contains(synonymes.motif_entier(mot), na=False)
    masque = champ.str.contains(mot, regex=False, na=False)
    if "-" in mot:
        masque |= champ.str.contains(mot.replace("-", ""), regex=False,
                                     na=False)
    if not masque.any() and len(mot) >= 5 and mot[-1] in "sx":
        masque = champ.str.contains(
            r"(?<![a-z0-9])" + re.escape(mot[:-1]), na=False)
    return masque


def _plein_texte_csar(df, requete, dans_notes):
    """Recherche par mots dans le CSAR, synonymes du dictionnaire compris.

    Chaque mot saisi est cherché tel quel OU par l'un de ses synonymes (voir
    ``smr/synonymes/synonymes.py``) ; tous les mots doivent être satisfaits. Les actes
    trouvés sans l'aide du dictionnaire sont classés les premiers, puis ceux
    qui répondent aux possibilités écrites en tête dans le dictionnaire : leur
    ordre y vaut priorité. La colonne
    ``synonymes`` dit, acte par acte, quel synonyme l'a fait ressortir : une
    correspondance que l'on ne peut pas expliquer ne se laisse pas vérifier.
    """
    unites = synonymes.developper(requete)
    if not unites:
        return df.head(0)
    champ = df["recherche"]
    if dans_notes:
        champ = champ + " " + df["recherche_notes"]
    # « psychocorporelle » et « ostéoarticulaire » doivent retrouver les
    # libellés qui écrivent ces mots avec un trait d'union.
    champ = champ + " " + champ.str.replace("-", "", regex=False)

    retenu = pd.Series(True, index=df.index)
    nb_synonymes = pd.Series(0, index=df.index)
    explication = pd.Series("", index=df.index)
    priorite = pd.Series(0, index=df.index)
    # Terme dont la position dans le libellé sert au classement : le premier
    # mot saisi ou, à défaut, le synonyme qui le remplace.
    premier = pd.Series(unites[0]["mots"][0], index=df.index)

    for rang, unite in enumerate(unites):
        litteral = pd.Series(True, index=df.index)
        for mot in unite["mots"]:
            litteral &= _presence(champ, mot, unite["entier"])
        par_synonyme = pd.Series(False, index=df.index)
        for ordre, (mots, ecrit) in enumerate(unite["cibles"]):
            present = pd.Series(True, index=df.index)
            for mot in mots:
                present &= champ.str.contains(mot, regex=False, na=False)
            nouveau = present & ~litteral & ~par_synonyme
            explication[nouveau] += "%s → %s ; " % (unite["saisi"], ecrit)
            priorite[nouveau] += ordre
            if rang == 0 and mots:
                premier[nouveau] = mots[0]
            par_synonyme |= present
        nb_synonymes += (par_synonyme & ~litteral).astype(int)
        retenu &= litteral | par_synonyme

    res = df[retenu].copy()
    if res.empty:
        return res
    res["synonymes"] = explication[retenu].str.rstrip(" ;")
    res["_syn"] = nb_synonymes[retenu]
    res["_ordre"] = priorite[retenu]
    res["_pos"] = [
        texte.find(terme) if terme in texte else 9999
        for texte, terme in zip(res["recherche"], premier[retenu])]
    res["_lg"] = res["libelle"].str.len()
    return res.sort_values(["_syn", "_ordre", "_pos", "_lg", "code"]).drop(
        columns=["_syn", "_ordre", "_pos", "_lg"])


def rechercher_csar(actes, requete, chapitre=None, type_acte=None,
                    dans_notes=False):
    df = actes
    if chapitre:
        df = df[df["chapitre"] == chapitre]
    if type_acte:
        df = df[df["type_acte"] == type_acte]
    requete = requete.strip()
    if not requete:
        return df.head(0)
    code_q = requete.upper().replace(" ", "")
    if RE_CODE_CSAR.match(code_q):
        res = df[df["code"].str.startswith(code_q)]
        if not res.empty:
            return res.sort_values("code")
    return _plein_texte_csar(df, requete, dans_notes)


def rechercher_csarr(actes, requete, chapitre=None, dans_notes=False,
                     masquer_gestes=False):
    df = actes
    if chapitre:
        df = df[df["chap1_num"] == chapitre]
    if masquer_gestes:
        df = df[df["geste_comp"] != "oui"]
    requete = requete.strip()
    if not requete:
        return df.head(0)
    code_q = requete.upper().replace(" ", "").replace("+", "")
    if RE_CODE_CSARR.match(code_q):
        res = df[df["code_plat"].str.startswith(code_q)]
        if not res.empty:
            return res.sort_values("code")
    return _plein_texte(df, requete, dans_notes)


# Longueur minimale d'un préfixe accepté comme abréviation d'un mot cherché.
# En dessous, « cer » ramènerait tout le vocabulaire cervical et cérébral.
ABREV_MIN = 4

RE_CODE_CIM = re.compile(r"^[A-Z]\d")


def _motif_mot(mot):
    """Expression rationnelle d'un mot cherché, abréviations ATIH comprises.

    Les libellés de la CIM-10 publiés par l'ATIH sont abrégés : « INFARCTUS
    CEREB. », « INFECT. INTEST. BACT. ». La normalisation ôtant les points,
    l'abréviation devient un mot entier — « cereb ». Un mot cherché
    correspond donc soit littéralement, soit par l'un de ses préfixes présent
    comme mot entier du libellé.
    """
    if len(mot) <= ABREV_MIN:
        return re.escape(mot)
    prefixes = [re.escape(mot[:k]) for k in range(ABREV_MIN, len(mot))]
    return r"(?:%s|\b(?:%s)\b)" % (re.escape(mot), "|".join(prefixes))


def _libelles_cim(d):
    """Libellés CIM normalisés, construits une fois pour toutes au chargement.

    La série est bâtie par ``_indexer_cim`` et voyage donc avec les données
    mises en cache. L'écrire ici serait sans effet : ``charger`` est décoré par
    ``st.cache_data``, qui rend une copie du dictionnaire à chaque run — les
    42 897 normalisations seraient refaites à chaque recherche.
    """
    champ = d.get("_cim_recherche")
    if champ is None:
        diag = d.get("cim_diag")
        champ = (diag["libelle"].map(normaliser)
                 if diag is not None and not diag.empty
                 else pd.Series(dtype=str))
    return champ


def chercher_cim(d, requete, limite=200, base=None):
    """Cherche un diagnostic par son code ou par les mots de son libellé.

    -> (résultats, nombre total trouvé). Le total permet d'annoncer une
    troncature au lieu de la subir : un affichage borné qui ne se signale pas
    se lit comme une absence du code cherché.

    ``base`` restreint la recherche à un sous-ensemble du référentiel — les
    seules CMA, par exemple. Il doit provenir de ``cim_diag`` : les libellés
    normalisés sont mémorisés selon son index.
    """
    diag = d.get("cim_diag") if base is None else base
    if diag is None or diag.empty:
        return diag, 0
    brut = str(requete or "").strip()
    if not brut:
        return diag.head(0), 0

    code = brut.upper().replace(" ", "").replace(".", "").replace(",", "")
    if RE_CODE_CIM.match(code):
        res = diag[diag["code"].str.startswith(code)]
        if not res.empty:
            return res.sort_values("code").head(limite), len(res)

    mots = normaliser(brut).split()
    if not mots:
        return diag.head(0), 0
    champ = _libelles_cim(d).reindex(diag.index)
    masque = pd.Series(True, index=diag.index)
    for mot in mots:
        masque &= champ.str.contains(_motif_mot(mot), na=False, regex=True)
    res = diag[masque]
    if res.empty:
        return res, 0
    # Tri par pertinence, comme pour les actes : d'abord les libellés où le
    # premier mot cherché apparaît le plus tôt, puis les plus courts. Un tri
    # par code ferait tomber sous la troncature les libellés les plus proches
    # de la demande, au profit du début de l'alphabet.
    premier = re.compile(_motif_mot(mots[0]))

    def _position(texte):
        trouve = premier.search(texte)
        return trouve.start() if trouve else 9999

    res = res.assign(_pos=champ[res.index].map(_position),
                     _lg=res["libelle"].str.len())
    res = res.sort_values(["_pos", "_lg", "code"]).drop(
        columns=["_pos", "_lg"])
    return res.head(limite), len(res)


# ---------------------------------------------------------------------------
# Résolution des codes supplémentaires d'un acte
# ---------------------------------------------------------------------------

def modulateurs_csar(d, code):
    """Codes supplémentaires autorisés pour un acte CSAR.

    Renvoie un dict : temps, lieux, technicite, niveau, collectif, pluripro.
    """
    lignes = d["csar_modulateurs"]
    lignes = lignes[lignes["code"] == code]
    if lignes.empty:
        return {"temps": False, "lieux": [], "technicite": [],
                "niveau": False, "collectif": False, "pluripro": True}
    r = lignes.iloc[0]
    return {
        "temps": r["temps"] == "oui",
        "lieux": [c.upper() for c in ("l1", "l2", "l3") if r[c] == "oui"],
        "technicite": [c.upper() for c in ("qm", "qi", "qf", "qs", "qq", "qc")
                       if r[c] == "oui"],
        "niveau": r["niv_mod_tech"] == "oui",
        "collectif": r["coll"] == "oui",
        # Le guide CSAR § 1.4.2 autorise la modalité pluriprofessionnelle
        # pour tous les actes : pas de liste d'actes éligibles.
        "pluripro": True,
    }


def _liste(champ):
    """'L3;ZV' ou 'QI;QM;QS;' -> ['L3', 'ZV']."""
    return [p.strip().upper() for p in re.split(r"[;,]", str(champ))
            if p.strip()]


def modulateurs_csarr(d, acte):
    """Codes supplémentaires autorisés pour un acte CSARR (ligne de la table)."""
    return {
        "lieux": _liste(acte["mod_lieu"]),
        "patient": _liste(acte["mod_patient"]),
        "technicite": _liste(acte["mod_tech"]),
        "niveau": _liste(acte["module_niveau"]),
        "gestes": _liste(acte["gestes"]),
        "dedie": str(acte["dedie"]).lower().startswith("oui"),
        "non_dedie": str(acte["non_dedie"]).lower().startswith("possible"),
        "collectif": str(acte["collectif"]).lower().startswith("oui"),
        "pluripro": str(acte["pluripro"]).lower().startswith("oui"),
        "appareillage": str(acte["appareillage"]).lower().startswith("oui"),
    }


def ponderations_csar(d, code):
    p = d["csar_ponderations"]
    return p[p["code"] == code].copy()


def ponderations_csarr(d, code):
    p = d["csarr_ponderations"]
    p = p[(p["code"] == code) & (p["validite"] != "")]
    return p.copy()


def notes_csarr(d, code):
    n = d["csarr_notes"]
    return n[n["code"] == code].sort_values("ordre")


def rendre_notes(notes):
    """Notes ATIH d'un acte CSARR -> markdown (titres de note + puces)."""
    lignes = []
    for r in notes.to_dict("records"):
        txt = str(r["texte"]).strip()
        if not txt:
            continue
        if txt.endswith(":") and int(r["niveau"]) == 1:
            lignes.append("\n*%s*" % txt)
        elif int(r["niveau"]) == 2:
            lignes.append("    - %s" % txt)
        else:
            lignes.append("- %s" % txt)
    return "\n".join(lignes)


def transcodage_vers_csar(d, code_csarr):
    t = d["transcodage"]
    return t[(t["code_csarr"] == code_csarr) & (t["code_csar"] != "")]


def transcodage_vers_csarr(d, code_csar):
    t = d["transcodage"]
    return t[(t["code_csar"] == code_csar) & (t["code_csarr"] != "ZZZ")]


def spe_csar(d, code):
    s = d["csar_spe"]
    return s[(s["code"] == code) & (s["gn_liste"] != "sans_objet")].copy()


def spe_csarr(d, code):
    s = d.get("csarr_spe")
    if s is None or s.empty:
        return pd.DataFrame()
    return s[s["code"] == code].copy()


# ---------------------------------------------------------------------------
# Groupes nosologiques et actes spécialisés
# ---------------------------------------------------------------------------

def _indexer_ccam(d):
    """Actes CCAM qui comptent dans le score de réadaptation.

    Ils n'appartiennent ni au CSARR ni au CSAR, mais l'ATIH les pondère dans
    le fichier de pondérations du CSARR, sous la nomenclature « CCAM » : une
    seule pondération par acte, l'intervenant valant toujours 10 (médecin) et
    aucun modulateur n'étant prévu. Seize d'entre eux figurent en outre dans
    les listes d'actes spécialisés de la pneumologie et de la cardiologie.
    """
    p = d.get("csarr_ponderations")
    if p is None or p.empty or "nomenclature" not in p.columns:
        d["ccam_actes"] = pd.DataFrame(
            columns=["code", "libelle", "ponderation"])
        d["lib_ccam"] = {}
        return
    cc = p[p["nomenclature"] == "CCAM"]
    d["ccam_actes"] = (
        cc[["code", "liblong", "ponderation"]]
        .rename(columns={"liblong": "libelle"})
        .drop_duplicates("code").sort_values("code").reset_index(drop=True))
    d["lib_ccam"] = dict(zip(d["ccam_actes"]["code"],
                             d["ccam_actes"]["libelle"]))


def ponderation_ccam(d, code):
    """Pondération publiée d'un acte CCAM, ou None s'il n'en a pas."""
    actes = d.get("ccam_actes")
    if actes is None or actes.empty:
        return None
    trouve = actes[actes["code"] == code]
    if trouve.empty:
        return None
    valeur = str(trouve.iloc[0]["ponderation"]).strip()
    return valeur or None


def _indexer_cim(d):
    """Index en mémoire du référentiel CIM, pour un groupage instantané.

    Le groupage interroge le référentiel des dizaines de fois par séjour : un
    dictionnaire évite autant de filtres pandas sur 42 897 lignes.
    """
    diag = d.get("cim_diag")
    if diag is None or diag.empty:
        d["_cim_index"], d["_cim_listes"] = {}, {}
        return
    d["_cim_index"] = {
        r["code"]: r for r in diag.to_dict("records")
    }
    # Libellés normalisés pour la recherche plein texte : construits ici pour
    # voyager avec les données mises en cache (voir _libelles_cim).
    d["_cim_recherche"] = diag["libelle"].map(normaliser)
    listes = {}
    couples = d.get("cim_listes")
    if couples is not None and not couples.empty:
        for code, liste in zip(couples["code"], couples["liste"]):
            listes.setdefault(code, set()).add(liste)
    d["_cim_listes"] = {k: frozenset(v) for k, v in listes.items()}

    # Exclusions des CMA : on garde les listes dédupliquées et un simple
    # renvoi par code, faute de quoi la table dépasserait 1,6 million de
    # couples pour 155 000 lignes réellement distinctes.
    d["_cma_liste"] = {}
    d["_cma_membres"] = {}
    app = d.get("cma_exclusion_listes")
    mem = d.get("cma_exclusion_membres")
    if app is not None and not app.empty:
        d["_cma_liste"] = dict(zip(app["cma"], app["liste"]))
    if mem is not None and not mem.empty:
        groupes = {}
        for liste, code in zip(mem["liste"], mem["code"]):
            groupes.setdefault(liste, set()).add(code)
        d["_cma_membres"] = {k: frozenset(v) for k, v in groupes.items()}

    ccam = d.get("ref_cma_ccam")
    d["_cma_ccam"] = (frozenset(ccam["code7"])
                      if ccam is not None and not ccam.empty else frozenset())

    # Les niveaux de sévérité réellement publiés, par groupe de lourdeur.
    d["_severites_publiees"] = {}
    ref = d.get("ref_groupes")
    if ref is not None and not ref.empty:
        for code in ref[ref["quoi"] == "GME"]["code"]:
            if len(code) == 7:
                d["_severites_publiees"].setdefault(code[:6], set()).add(code[6])


def libelle_gn(d, gn):
    ref = d.get("ref_gn")
    if ref is None or ref.empty:
        return ""
    ligne = ref[ref["gn"] == gn]
    return "" if ligne.empty else ligne.iloc[0]["libelle"]


def liste_du_gn(d, gn):
    """(libellé de la liste d'actes spécialisés, ligne du GN) pour un GN."""
    ref = d.get("ref_gn")
    if ref is None or ref.empty:
        return "", None
    ligne = ref[ref["gn"] == gn]
    if ligne.empty:
        return "", None
    return ligne.iloc[0]["libelle_gn_liste"], ligne.iloc[0]


def actes_specialises(d, libelle_liste, nomenclature):
    """Actes spécialisés d'une liste, pour une nomenclature donnée.

    Côté CSAR la spécialisation est déclinée par intervenant : les lignes
    ``sans_objet`` retirent l'acte de la liste pour cet intervenant-là. On
    renvoie donc, par acte, la restriction d'intervenants applicable.
    """
    if not libelle_liste:
        return pd.DataFrame()

    if nomenclature == "csar":
        s = d["csar_spe"]
        s = s[s["libelle_gn"] == libelle_liste]
        if s.empty:
            return pd.DataFrame()
        inclus = s[s["gn_liste"] != "sans_objet"]
        exclus = s[s["gn_liste"] == "sans_objet"]
        lignes = []
        for code in sorted(inclus["code"].unique()):
            hors = sorted(exclus[exclus["code"] == code]["intervenant"].unique())
            lignes.append({
                "code": code,
                "libelle": d["lib_csar"].get(code, ""),
                "intervenants": (
                    "Tous sauf " + ", ".join(
                        "%s %s" % (i, d["lib_intervenant"].get(i, "")) for i in hors)
                    if hors else "Tous les intervenants"),
            })
        return pd.DataFrame(lignes)

    s = d.get("csarr_spe")
    if s is None or s.empty:
        return pd.DataFrame()
    s = s[s["libelle_gn"] == libelle_liste]
    return (s[["code", "nomenclature", "libelle", "hiera"]]
            .drop_duplicates("code").sort_values("code").reset_index(drop=True))


def codes_specialises(d, libelle_liste):
    """Ensemble des codes (CSARR, CCAM et CSAR) spécialisés pour une liste."""
    codes = set()
    if not libelle_liste:
        return codes
    s = d.get("csarr_spe")
    if s is not None and not s.empty:
        codes |= set(s[s["libelle_gn"] == libelle_liste]["code"])
    c = d["csar_spe"]
    c = c[(c["libelle_gn"] == libelle_liste) & (c["gn_liste"] != "sans_objet")]
    codes |= set(c["code"])
    return codes


# ---------------------------------------------------------------------------
# Pondération effective d'un acte codé
# ---------------------------------------------------------------------------

def _choisir_pond(lignes, intervenant):
    """Ligne la plus spécifique : intervenant exact, sinon « 00 = tous »."""
    exact = lignes[lignes["intervenant"] == intervenant]
    if not exact.empty:
        return exact.iloc[0]
    tous = lignes[lignes["intervenant"] == "00"]
    if not tous.empty:
        return tous.iloc[0]
    return None


def ponderation_effective_csar(d, code, intervenant, collectif):
    """Pondération d'un acte CSAR pour un intervenant et une modalité.

    Renvoie (valeur ou None, commentaire).
    """
    lignes = ponderations_csar(d, code)
    if lignes.empty:
        return None, "pondération non renseignée dans le fichier ATIH"
    attendus = ["2", "1" if collectif else "0"]
    filtre = lignes[lignes["acte_collectif"].isin(attendus)]
    if filtre.empty:
        filtre = lignes
    r = _choisir_pond(filtre, intervenant)
    if r is None:
        return None, ("aucune pondération pour cet intervenant "
                      "(pondération nulle attendue)")
    lib = "tous les intervenants" if r["intervenant"] == "00" else \
        d["lib_intervenant"].get(r["intervenant"], r["intervenant"])
    return r["ponderation"], lib


def ponderation_effective_csarr(d, code, intervenant):
    """Pondération d'un acte CSARR pour un intervenant."""
    lignes = ponderations_csarr(d, code)
    if lignes.empty:
        return None, "pondération non renseignée dans le fichier ATIH"
    r = _choisir_pond(lignes, intervenant)
    if r is None:
        return None, ("aucune pondération pour cet intervenant "
                      "(pondération nulle attendue)")
    lib = "tous les intervenants" if r["intervenant"] == "00" else \
        d["lib_intervenant"].get(r["intervenant"], r["intervenant"])
    return r["ponderation"], lib


def _val(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def ponderation_modulateur_csar(d, modalite, variable):
    """Ligne du barème des modulateurs CSAR publié avec le manuel de groupage."""
    ref = d.get("ref_ponderation_modulateurs_csar")
    if ref is None or ref.empty or not modalite:
        return None
    ligne = ref[(ref["modalite"] == modalite) & (ref["variable"] == variable)]
    return None if ligne.empty else ligne.iloc[0]


def ponderation_csar_detaillee(d, code, intervenant, collectif, temps="",
                               lieu=""):
    """Pondération complète d'un acte CSAR codé, étape par étape.

    Le manuel de groupage enchaîne : pondération de l'acte (selon
    l'intervenant), puis — si un modulateur de temps est codé — on retient la
    **plus élevée** des deux pondérations, celle de l'acte ou celle du temps,
    puis on ajoute la majoration du modulateur de lieu, différente selon que
    l'acte est individuel ou collectif.

    Renvoie un dict : acte, temps, retenue, majoration, total, source, notes.
    """
    base, source = ponderation_effective_csar(d, code, intervenant, collectif)
    detail = {"acte": _val(base), "temps": None, "retenue": _val(base),
              "majoration": None, "total": _val(base), "source": source,
              "notes": []}

    ligne_temps = ponderation_modulateur_csar(d, temps, "Temps")
    if ligne_temps is not None:
        detail["temps"] = _val(ligne_temps["ponderation"])
        if detail["temps"] is not None:
            if detail["acte"] is None:
                detail["retenue"] = detail["temps"]
            else:
                detail["retenue"] = max(detail["acte"], detail["temps"])
                if detail["temps"] > detail["acte"]:
                    detail["notes"].append(
                        "La pondération du modulateur de temps %s (%g) "
                        "l'emporte sur celle de l'acte (%g)."
                        % (temps, detail["temps"], detail["acte"]))

    ligne_lieu = ponderation_modulateur_csar(d, lieu, "Lieu")
    if ligne_lieu is not None:
        colonne = "majoration_coll" if collectif else "majoration_indiv"
        brut = str(ligne_lieu[colonne]).strip()
        if brut.lower().startswith("sans objet"):
            detail["notes"].append(
                "Le modulateur de lieu %s n'apporte pas de majoration pour un "
                "acte collectif." % lieu)
        else:
            detail["majoration"] = _val(brut)

    detail["total"] = (detail["retenue"] or 0) + (detail["majoration"] or 0) \
        if (detail["retenue"] is not None or detail["majoration"] is not None) \
        else None
    return detail


def majoration_modulateur_csarr(d, modulateur, collectif=False):
    """Majoration de pondération apportée par un modulateur CSARR."""
    ref = d["ref_modulateurs_csarr"]
    ligne = ref[ref["code"] == modulateur]
    if ligne.empty:
        return None
    col = "majoration_coll" if collectif else "majoration_indiv"
    val = str(ligne.iloc[0][col]).strip()
    return val or None
