# -*- coding: utf-8 -*-
"""
PMSI SMR — panier d'actes : collecte, contrôle des associations et scores.

Le panier remplace l'ancienne page « contrôle par lot ». Il rassemble les actes
d'un même dossier, qu'ils viennent d'une fiche (bouton « Ajouter au panier ») ou
d'un collage de lignes déjà codées, les contrôle au regard des tables ATIH et en
calcule les scores de réadaptation.

Son contenu vit dans le magasin de session (voir smr/etat.py) : il survit à la
navigation entre les pages, et servira d'entrée au futur générateur de GME.
"""

import re

import pandas as pd
import streamlit as st

from smr import etat
from smr.base import donnees as sd
from smr.base.donnees import (MOD_AVEC_NIVEAU, MOD_LIEU_CSAR, MOD_LIEU_CSARR,
                              MOD_PATIENT_CSARR, MOD_TECHNICITE, MOD_TEMPS)

# Journées de présence proposées tant que la page « Séjour & valorisation »
# n'a rien saisi : elles bornent aussi le dénominateur des scores par jour.
JOURNEES_DEFAUT = 25
# En temps partiel, la saisie porte sur une semaine, groupée à part (manuel
# des GME 2026, vol. 1, § 3.1) : 7 journées de présence au plus.
JOURNEES_MAX_SEMAINE = 7

# Préfixe de la clé du tableau du panier. La sélection d'un tableau est un
# état de widget : pour la libérer après une correction, il faut pouvoir la
# nommer. Voir aussi _cle_tableau, qui y ajoute la composition du panier.
CLE_TABLEAU = "panier_tableau"

RE_CSAR = re.compile(r"^\d{2}[ESMP]\d{2}$")
RE_CSARR = re.compile(r"^[A-Z]{3}\+?\d{3}$")
# Un code CCAM porte quatre lettres et trois chiffres, éventuellement suivis
# du code d'activité que le SMR n'utilise pas.
RE_CCAM = re.compile(r"^[A-Z]{4}\d{3}\d?$")
RE_KV = re.compile(r"^(pat|int|nb|niv)\s*=\s*(\d+)$", re.I)
RE_EXT = re.compile(r"^[PA]\d$")
TOK_TEMPS = set(MOD_TEMPS)
TOK_TECH = set(MOD_TECHNICITE)
TOK_LIEU = set(MOD_LIEU_CSAR) | set(MOD_LIEU_CSARR)
TOK_PATIENT = set(MOD_PATIENT_CSARR)

FORMAT_LOT = """\
Une ligne par acte — code CSAR (`07S06`), CSARR (`GLR+226`) ou CCAM
(`DKRP002`). Les champs suivants, dans n'importe quel ordre, séparés par `;`,
une tabulation ou une virgule (un acte CCAM n'en admet aucun, hormis `nb`) :

| Champ | Exemples |
|---|---|
| intervenant | `22`, `27`, `30` |
| modulateur de temps (CSAR) | `T0` … `T4` |
| modulateur de lieu | `L1`, `L2`, `L3`, `ZV`, `HW`, `XH` … |
| modulateur de patient (CSARR) | `EZ` |
| modulateur de technicité | `QM`, `QS`, `QF`, `QI`, `QC`, `QQ` |
| extension documentaire | `P3`, `P7`, `A1` … |
| étape d'appareillage (CSARR) | `A`, `B`, `C` ou `ABC` |
| modalités (CSAR) | `coll`, `pp` |
| valeurs numériques | `pat=4` patients · `int=2` intervenants · `nb=2` réalisations · `niv=1` module/niveau |
"""

EXEMPLE_LOT = """\
07S06;22;T2;QM
01E01;30;T4
01S09;30
11S06;30
GLR+226;22;pat=1
ZZC+221;10;int=3
"""

# Gabarit d'une ligne de panier. Les fiches et l'import texte produisent la
# même structure, si bien qu'un seul jeu de contrôles couvre les deux.
GABARIT = {
    "code": "", "nomenclature": "", "libelle": "", "inter": "",
    "temps": "", "lieu": "", "patient": "", "tech": "", "niv": "", "ext": "",
    "etapes": "", "geste": "", "coll": False, "pp": False,
    "pat": None, "nb_inter": None, "nb": 1,
    "ponderation": None, "majoration": None, "origine": "fiche",
}


def ligne_vide(**valeurs):
    ligne = dict(GABARIT)
    ligne.update(valeurs)
    return ligne


# ---------------------------------------------------------------------------
# Lecture d'une saisie textuelle
# ---------------------------------------------------------------------------

def _decouper(ligne):
    if any(s in ligne for s in (";", "\t", ",")):
        champs = re.split(r"[;\t,]", ligne)
    else:
        champs = ligne.split()
    return [c.strip() for c in champs if c.strip()]


def analyser(champs):
    """Champs d'une ligne saisie -> ligne de panier (+ jetons non reconnus)."""
    v = ligne_vide(origine="import")
    v["inconnus"] = []
    for i, champ in enumerate(champs):
        c = champ.strip()
        haut = c.upper().replace(" ", "")
        if i == 0:
            v["code"] = haut
            continue
        kv = RE_KV.match(c)
        if kv:
            cle, val = kv.group(1).lower(), int(kv.group(2))
            if cle == "pat":
                v["pat"] = val
            elif cle == "int":
                v["nb_inter"] = val
            elif cle == "nb":
                v["nb"] = val
            else:
                v["niv"] = str(val)
            continue
        if c.lower() in ("coll", "collectif", "c1"):
            v["coll"] = True
        elif c.lower() in ("pp", "pluri", "pluripro"):
            v["pp"] = True
        elif re.match(r"^\d{2}$", haut):
            v["inter"] = haut
        elif haut in TOK_TEMPS:
            v["temps"] = haut
        elif haut in TOK_TECH:
            v["tech"] = haut
        elif haut in TOK_LIEU:
            v["lieu"] = haut
        elif haut in TOK_PATIENT:
            v["patient"] = haut
        elif RE_EXT.match(haut):
            v["ext"] = haut
        elif re.match(r"^[ABC]{1,3}$", haut):
            v["etapes"] = "".join(sorted(set(haut)))
        else:
            v["inconnus"].append(c)
    return v


def reconnaitre(code):
    """(nomenclature, code normalisé) ; nomenclature vide si non reconnu."""
    code = str(code).upper().replace(" ", "")
    if RE_CSAR.match(code):
        return "csar", code
    if RE_CSARR.match(code):
        return "csarr", (code if "+" in code else code[:3] + "+" + code[3:])
    if RE_CCAM.match(code):
        # Le code d'activité éventuel est écarté : le SMR ne le recueille pas.
        return "ccam", code[:7]
    return "", code


# ---------------------------------------------------------------------------
# Contrôles
# ---------------------------------------------------------------------------

def controler(d, v):
    """Contrôle une ligne de panier -> (libellé, erreurs, avertissements)."""
    nomen, code = reconnaitre(v.get("code", ""))
    err, avert = [], []

    if not nomen:
        return "", ["Code non reconnu (ni CSAR à 5 caractères, ni CSARR à "
                    "7 caractères, ni CCAM à 4 lettres et 3 chiffres)."], []

    if v.get("inconnus"):
        avert.append("Champs non reconnus : %s." % ", ".join(v["inconnus"]))

    if nomen == "ccam":
        return _controler_ccam(d, v, code, err, avert)

    inter = v.get("inter") or ""
    if inter:
        ref = d["ref_intervenants"]
        if inter not in d["lib_intervenant"]:
            err.append("Catégorie d'intervenant %s inexistante." % inter)
        elif nomen == "csarr" and ref[(ref["code"] == inter)
                                      & (ref["csarr"] == "oui")].empty:
            err.append("La catégorie d'intervenant %s n'existe que dans le "
                       "CSAR." % inter)

    # Le composeur borne le nombre de réalisations à 20 ; un collage peut
    # porter davantage. On le signale plutôt que de le rabattre en silence à
    # la première correction de la ligne.
    nb = v.get("nb")
    if nb not in (None, ""):
        try:
            entier = int(nb)
        except (TypeError, ValueError):
            entier = None
        if entier is None or not 1 <= entier <= 20:
            avert.append(
                "Nombre de réalisations « %s » hors des bornes 1 à 20 : "
                "corriger cet acte le ramènera dans ces bornes." % nb)

    if nomen == "csar":
        return _controler_csar(d, v, code, err, avert)
    return _controler_csarr(d, v, code, err, avert)


def _controler_ccam(d, v, code, err, avert):
    """Contrôle d'un acte CCAM comptant dans le score de réadaptation."""
    libelle = d.get("lib_ccam", {}).get(code, "")
    if not libelle:
        return "", ["Acte CCAM absent de la table de pondérations du SMR : il "
                    "ne compte dans aucun score de réadaptation."], []
    for champ, nom in (("temps", "modulateur de temps"),
                       ("lieu", "modulateur de lieu"),
                       ("patient", "modulateur de patient"),
                       ("tech", "modulateur de technicité"),
                       ("ext", "extension documentaire"),
                       ("etapes", "étape d'appareillage"),
                       ("geste", "geste complémentaire")):
        if v.get(champ):
            err.append("Aucun %s ne s'associe à un acte CCAM." % nom)
    if v.get("coll") or v.get("pp"):
        err.append("Les modalités collective et pluriprofessionnelle "
                   "n'existent qu'en CSAR.")
    if v.get("pat"):
        err.append("Le nombre de patients ne se recueille pas pour un acte "
                   "CCAM.")
    if v.get("inter") and v["inter"] != "10":
        avert.append("La pondération publiée d'un acte CCAM vaut pour "
                     "l'intervenant 10 (médecin).")
    return libelle, err, avert


def _controler_csar(d, v, code, err, avert):
    acte = d["csar_actes"][d["csar_actes"]["code"] == code]
    if acte.empty:
        return "", ["Code CSAR inexistant dans la version chargée."], []
    libelle = acte.iloc[0]["libelle"]
    mods = sd.modulateurs_csar(d, code)

    if v["temps"] and not mods["temps"]:
        err.append("Modulateur de temps %s non autorisé pour cet acte."
                   % v["temps"])
    if v["lieu"]:
        if v["lieu"] not in MOD_LIEU_CSAR:
            err.append("%s n'est pas un modulateur de lieu du CSAR "
                       "(modulateur CSARR ?)." % v["lieu"])
        elif v["lieu"] not in mods["lieux"]:
            err.append("Modulateur de lieu %s non autorisé pour cet acte."
                       % v["lieu"])
    if v["tech"] and v["tech"] not in mods["technicite"]:
        err.append("Modulateur de technicité %s non autorisé pour cet acte."
                   % v["tech"])
    if v["coll"] and not mods["collectif"]:
        err.append("Modalité collective non autorisée pour cet acte.")
    if v["patient"]:
        err.append("Le modulateur de patient EZ n'existe pas en CSAR.")
    if v["etapes"]:
        err.append("Les étapes d'appareillage A/B/C n'existent pas en CSAR.")
    if v["niv"] in ("1", "2"):
        if not v["tech"]:
            err.append("Module/niveau de technicité sans modulateur de "
                       "technicité.")
        elif v["tech"] not in MOD_AVEC_NIVEAU:
            err.append("Le plateau %s ne dispose pas de module ou niveau de "
                       "complexité." % v["tech"])
        elif not mods["niveau"]:
            err.append("Module/niveau de technicité non autorisé pour cet "
                       "acte.")
    if v["ext"]:
        ref = d["ref_modulateurs_csar"]
        valides = set(ref[ref["type"].str.lower()
                          .str.startswith("extension")]["modalite"])
        if v["ext"] not in valides:
            err.append("Extension documentaire %s non reprise dans le CSAR."
                       % v["ext"])
    if v["inter"]:
        ia = d["csar_intervenants"]
        att = ia[(ia["code"] == code) & (ia["attendu"] == "1")]
        if not att.empty and v["inter"] not in set(att["code_inter"]):
            avert.append("Intervenant %s hors liste indicative des "
                         "intervenants attendus." % v["inter"])
    return libelle, err, avert


def _controler_csarr(d, v, code, err, avert):
    supp = d["csarr_supprimes"]
    if code in set(supp["code"]):
        r = supp[supp["code"] == code].iloc[0]
        return "", ["Code CSARR supprimé le %s. Remplacement : %s."
                    % (r["date_suppression"],
                       r["remplacement"] or "non remplacé")], []
    acte = d["csarr_actes"][d["csarr_actes"]["code"] == code]
    if acte.empty:
        return "", ["Code CSARR inexistant dans la version chargée."], []
    acte = acte.iloc[0]
    libelle = acte["libelle"]
    mods = sd.modulateurs_csarr(d, acte)

    if v["temps"]:
        err.append("Les modulateurs de temps T0 à T4 n'existent pas en CSARR.")
    if v["coll"] or v["pp"]:
        err.append("Les modalités collective et pluriprofessionnelle "
                   "n'existent qu'en CSAR ; en CSARR, renseigner le nombre de "
                   "patients et le nombre d'intervenants.")
    if v["lieu"] and v["lieu"] not in mods["lieux"]:
        err.append("Modulateur de lieu %s non autorisé pour cet acte."
                   % v["lieu"])
    if v["patient"] and v["patient"] not in mods["patient"]:
        err.append("Modulateur de patient %s non autorisé pour cet acte."
                   % v["patient"])
    if v["tech"] and v["tech"] not in mods["technicite"]:
        err.append("Modulateur de technicité %s non autorisé pour cet acte."
                   % v["tech"])
    if v["niv"] in ("1", "2"):
        if not v["tech"]:
            err.append("Module/niveau de technicité sans modulateur de "
                       "technicité.")
        elif not mods["niveau"]:
            err.append("Module/niveau de technicité non autorisé pour cet "
                       "acte.")
    if mods["appareillage"] and not v["etapes"]:
        err.append("Acte d'appareillage à étapes : au moins une étape A, B ou "
                   "C est obligatoire.")
    if v["etapes"] and not mods["appareillage"]:
        err.append("Cet acte n'admet pas d'étape de réalisation A/B/C.")
    if mods["pluripro"] and not (v["nb_inter"] and v["nb_inter"] >= 2):
        err.append("Acte pluriprofessionnel : le nombre d'intervenants est "
                   "obligatoire et doit être au moins égal à 2.")
    pat = v.get("pat")
    if pat is not None:
        if pat == 1 and not mods["dedie"]:
            avert.append("Nombre de patients = 1 alors que l'acte n'est pas "
                         "prévu en individuel dédié.")
        elif 2 <= pat <= 8 and not (mods["non_dedie"] or mods["collectif"]):
            err.append("Nombre de patients = %d alors que l'acte n'admet ni le "
                       "non dédié ni le collectif." % pat)
        elif pat is not None and pat > 8:
            if not mods["collectif"]:
                err.append("Nombre de patients = %d alors que l'acte n'est pas "
                           "collectif." % pat)
            elif pat > 25 and code != "ZZR+026":
                avert.append("Nombre de patients > 25 : limite dépassée sauf "
                             "pour ZZR+026.")
    if v["ext"] and v["ext"] not in set(d["ref_extensions_csarr"]["code"]):
        err.append("Extension documentaire %s inexistante en CSARR." % v["ext"])
    if acte["csar_cible"] == "ZZZ":
        avert.append("Aucun équivalent CSAR : acte non codable après le "
                     "31 décembre 2026.")
    return libelle, err, avert


def _est_collectif(d, code, v):
    """Un acte CSARR est-il collectif ? La question se tranche sur le libellé.

    Aucun acte du CSARR n'admet à la fois l'individuel non dédié et le
    collectif : le caractère collectif est donc une propriété de l'acte, pas du
    nombre de patients. Le déduire d'un compte supérieur à 8 majorait une
    séance collective de 4 patients au tarif de l'individuel — 30 points de
    majoration de lieu au lieu de 5, sur 19 actes concernés.

    On ne retombe sur le nombre de patients que si le code est inconnu.
    """
    actes = d["csarr_actes"]
    acte = actes[actes["code"] == code]
    if acte.empty:
        return bool(v.get("pat") and v["pat"] > 8)
    return bool(sd.modulateurs_csarr(d, acte.iloc[0])["collectif"])


def ponderer(d, v):
    """(pondération retenue, majoration) d'une ligne de panier.

    Côté CSAR, la pondération retenue est la plus élevée entre celle de l'acte
    et celle du modulateur de temps ; la majoration vient du modulateur de lieu.
    """
    nomen, code = reconnaitre(v.get("code", ""))
    inter = v.get("inter") or "00"
    if nomen == "csar":
        detail = sd.ponderation_csar_detaillee(
            d, code, inter, bool(v.get("coll")),
            v.get("temps") or "", v.get("lieu") or "")
        return detail["retenue"], detail["majoration"]
    if nomen == "ccam":
        # Pondération unique, sans modulateur ni majoration de lieu.
        return sd.ponderation_ccam(d, code), None
    if nomen == "csarr":
        valeur, _ = sd.ponderation_effective_csarr(d, code, inter)
        majo = None
        if v.get("lieu"):
            majo = sd.majoration_modulateur_csarr(
                d, v["lieu"], _est_collectif(d, code, v))
        if majo in ("0", "nan", ""):
            majo = None
        return valeur, majo
    return None, None


def enrichir(d, v):
    """Complète une ligne : nomenclature, libellé, pondération, statut."""
    nomen, code = reconnaitre(v.get("code", ""))
    libelle, err, avert = controler(d, v)
    pond, majo = ponderer(d, v) if nomen else (None, None)
    v = dict(v)
    v.update({
        "nomenclature": nomen, "code": code or v.get("code", ""),
        "libelle": libelle, "ponderation": pond, "majoration": majo,
        "erreurs": err, "avertissements": avert,
    })
    v["statut"] = "❌ Erreur" if err else ("⚠️ À vérifier" if avert
                                          else "✅ Conforme")
    return v


# ---------------------------------------------------------------------------
# Onglet « Panier »
# ---------------------------------------------------------------------------

def _rappel_import():
    """Rappel du bouton d'import : lit la zone de texte et remplit le panier."""
    texte = st.session_state.get(etat.cle_widget("import_texte"), "")
    ajoutes = 0
    for ligne in texte.splitlines():
        if not ligne.strip():
            continue
        v = analyser(_decouper(ligne))
        v["saisie"] = ligne.strip()
        etat.ajouter_acte(v)
        ajoutes += 1
    if ajoutes:
        etat.ecrire("import_texte", "")
        etat.resynchroniser("import_texte")
        st.session_state["message_panier"] = (
            "%d ligne(s) ajoutée(s) au panier." % ajoutes)
    else:
        st.session_state["message_panier"] = "Aucune ligne à ajouter."


def onglet_panier(d, nomenclature):
    """Onglet panier, identique dans les deux pages de recherche."""
    lignes = [enrichir(d, v) for v in etat.panier()]

    if not lignes:
        st.info(
            "Le panier est vide. Ajoutez des actes depuis leur fiche avec le "
            "bouton **🧺 Ajouter au panier**, ou collez ci-dessous des lignes "
            "déjà codées. Le panier est commun aux deux nomenclatures et "
            "**survit à la navigation** dans l'application.")
        _bloc_import()
        return

    # --- scores -----------------------------------------------------------
    total = sum(_total_ligne(v) for v in lignes)
    n_err = sum(1 for v in lignes if v["erreurs"])
    n_av = sum(1 for v in lignes if v["avertissements"] and not v["erreurs"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Actes au panier", len(lignes))
    c2.metric("Score de réadaptation", "%g" % total,
              help="Somme des pondérations, majorations et répétitions "
                   "comprises. C'est le score global du séjour.")
    c3.metric("Erreurs", n_err)
    c4.metric("À vérifier", n_av)

    _bloc_scores(d, lignes, total)

    # --- tableau ----------------------------------------------------------
    st.markdown("**Contenu du panier** — cliquez une ligne pour la corriger")
    tableau = pd.DataFrame([{
        "Statut": v["statut"],
        "Nomenclature": v["nomenclature"].upper() or "?",
        "Code": v["code"],
        "Libellé": v["libelle"],
        "Interv.": v["inter"] or "—",
        "Codes suppl.": _resume_codes(v),
        "Nb": v.get("nb") or 1,
        "Pondération": "—" if v["ponderation"] is None else "%s" % v["ponderation"],
        "Total": "%g" % _total_ligne(v),
        "Messages": " ".join(v["erreurs"] + v["avertissements"]),
    } for v in lignes])
    corriger(d, lignes, tableau, column_config={
        "Libellé": st.column_config.TextColumn(width="medium"),
        "Messages": st.column_config.TextColumn(width="large"),
        "Pondération": st.column_config.TextColumn(
            width="small", help=sd.AIDE["Pondération"]),
    })

    # --- retrait ligne à ligne -------------------------------------------
    with st.expander("Retirer un acte du panier"):
        for v in lignes:
            colonnes = st.columns([6, 1])
            colonnes[0].markdown(
                "`%s` %s" % (v["code"], v["libelle"][:70] or "—"))
            if colonnes[1].button("Retirer", key="rm_%s" % v["id"],
                                  width="stretch"):
                etat.retirer_acte(v["id"])
                st.rerun()

    c1, c2 = st.columns([1, 3])
    if c1.button("🗑️ Vider le panier", key="vider_%s" % nomenclature):
        etat.vider_panier()
        st.rerun()
    c2.download_button(
        "⬇️ Exporter le panier (CSV)",
        tableau.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="panier_actes_smr.csv", mime="text/csv")

    _bloc_import()


# ---------------------------------------------------------------------------
# Correction d'un acte déjà au panier
# ---------------------------------------------------------------------------
# Corriger le 10e acte d'une semaine ne doit pas obliger à ressaisir les neuf
# précédents : le composeur de la nomenclature est réouvert sur la composition
# mémorisée, et l'acte garde sa place dans le panier.

def corriger(d, lignes, tableau, hauteur_max=420, column_config=None):
    """Tableau cliquable du panier, puis le composeur de l'acte choisi.

    Commun à l'onglet Panier et à la partie groupe de réadaptation de la page
    « Séjour & valorisation » : cliquer une ligne rouvre le composeur de sa
    nomenclature, d'où l'on enregistre la correction ou retire l'acte.
    ``tableau`` porte une ligne par acte, dans l'ordre de ``lignes``.
    """
    # Une correction close libère la sélection du tableau, mais seulement
    # avant son rendu : Streamlit refuse qu'on touche à la clé d'un widget
    # déjà instancié.
    if st.session_state.pop("panier_liberer", False):
        for cle in [k for k in st.session_state if str(k).startswith(
                CLE_TABLEAU)]:
            st.session_state.pop(cle, None)
    evenement = st.dataframe(
        tableau, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-cell",
        key=_cle_tableau(lignes),
        height=min(38 + 35 * len(tableau), hauteur_max),
        column_config=column_config)
    _panneau_edition(d, lignes, _ligne_choisie(lignes, evenement))


def _cle_tableau(lignes):
    """Clé du tableau, dépendante de la composition du panier.

    La sélection que Streamlit renvoie est un **rang**, pas un identifiant :
    tant que la clé ne change pas, le rang survit à un ajout ou à un retrait et
    désignerait alors un autre acte. Faire dépendre la clé des identifiants
    présents remet la sélection à zéro dès que le panier bouge — l'acte en
    cours de correction, lui, est retenu par le magasin.
    """
    return "%s_%s" % (CLE_TABLEAU,
                      "-".join(str(v.get("id")) for v in lignes))


def _ligne_choisie(lignes, evenement):
    """Identifiant de l'acte à corriger : la sélection, sinon la mémoire.

    La sélection d'un tableau est purgée dès qu'on navigue ailleurs. Le magasin
    retient donc l'acte en cours de correction, la sélection ne servant qu'à le
    désigner — on revient d'un autre onglet sans perdre la correction en cours.
    """
    # Sélection par cellule et non par ligne : cliquer n'importe où dans la
    # ligne suffit alors, comme dans l'onglet de recherche. En mode ligne, il
    # aurait fallu viser la case à cocher de la première colonne.
    cellules = (evenement.selection.get("cells") or []) if evenement else []
    if cellules and cellules[0][0] < len(lignes):
        etat.ecrire("panier.edition", lignes[cellules[0][0]]["id"])
    memorise = etat.lire("panier.edition")
    return memorise if any(v["id"] == memorise for v in lignes) else None


def _clore_edition(identifiant, message=None):
    """Referme la correction : brouillon oublié, sélection libérée."""
    etat.vider("edit.%s" % identifiant)
    etat.vider("panier.edition")
    st.session_state["panier_liberer"] = True
    if message:
        st.session_state["message_panier"] = message


def _acte_du_code(d, code_saisi):
    """(nomenclature, ligne d'acte, modulateurs) pour un code saisi."""
    nomen, code = reconnaitre(code_saisi)
    if nomen == "csar":
        trouve = d["csar_actes"][d["csar_actes"]["code"] == code]
        if not trouve.empty:
            return nomen, trouve.iloc[0], sd.modulateurs_csar(d, code)
    elif nomen == "csarr":
        trouve = d["csarr_actes"][d["csarr_actes"]["code"] == code]
        if not trouve.empty:
            acte = trouve.iloc[0]
            return nomen, acte, sd.modulateurs_csarr(d, acte)
    elif nomen == "ccam":
        if code in d.get("lib_ccam", {}):
            return nomen, code, None
    return nomen, None, None


def _panneau_edition(d, lignes, identifiant):
    """Réouvre le composeur sur un acte du panier."""
    if identifiant is None:
        st.caption(
            "👆 Cliquez une ligne du tableau pour rouvrir le composeur sur "
            "cet acte : intervenant, modulateurs, nombre de patients et de "
            "réalisations restent modifiables, et l'acte peut être retiré du "
            "panier, sans toucher au reste.")
        return
    ligne = next(v for v in lignes if v["id"] == identifiant)

    st.divider()
    st.markdown("#### ✏️ Correction de l'acte `%s`" % ligne["code"])
    st.caption(
        "Rien ne change dans le panier avant **Enregistrer**. L'acte conserve "
        "sa place dans la liste, et la correction survit à un passage par un "
        "autre onglet.")

    # Le code lui-même est corrigeable : c'est l'erreur la plus coûteuse à
    # rattraper, et la seule dont le composeur ne peut pas venir à bout.
    saisi = etat.texte(
        "edit.%s._code" % identifiant, "Code de l'acte", defaut=ligne["code"],
        help="En corrigeant le code, le composeur de l'acte correspondant "
             "s'ouvre — dans l'une ou l'autre nomenclature.")
    nomen, acte, mods = _acte_du_code(d, saisi)

    if acte is None:
        st.error(
            "Le code **%s** ne figure pas dans les nomenclatures chargées. "
            "Corrigez-le ci-dessus, ou retirez l'acte du panier."
            % (str(saisi).strip() or "—"))
        _boutons_hors_composeur(identifiant)
        return

    # fiches importe déjà panier : l'import est local pour ne pas boucler.
    from smr.actes import fiches

    edition = dict(ligne)
    edition["id"] = identifiant
    if nomen == "ccam":
        fiches.fiche_ccam(d, acte, edition)
    elif nomen == "csar":
        fiches.composeur_csar(d, acte, mods, edition)
    else:
        fiches.composeur_csarr(d, acte, mods, edition)


def actions_edition(ligne, edition):
    """Boutons de fin de correction, appelés par le composeur.

    Ils occupent deux à deux une colonne étroite du composeur : sans retour à
    la ligne, « Retirer du panier » s'y lisait « Retirer du … » sur un petit
    écran.
    """
    identifiant = edition["id"]
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer", key="maj_%s" % identifiant,
                 type="primary", width="stretch", wrap=True,
                 help="Remplace la composition de l'acte, à sa place dans le "
                      "panier."):
        etat.modifier_acte(identifiant, ligne)
        _clore_edition(identifiant, "Acte %s corrigé." % ligne["code"])
        st.rerun()
    if c2.button("Annuler", key="ann_%s" % identifiant, width="stretch",
                 wrap=True,
                 help="Referme la correction sans rien changer au panier."):
        _clore_edition(identifiant)
        st.rerun()

    c3, c4 = st.columns(2)
    if c3.button("➕ Ajouter en plus", key="dup_%s" % identifiant,
                 width="stretch", wrap=True,
                 help="Ajoute la composition affichée comme un acte "
                      "supplémentaire ; l'acte d'origine reste inchangé."):
        etat.ajouter_acte(ligne)
        _clore_edition(identifiant, "Acte %s ajouté au panier."
                       % ligne["code"])
        st.rerun()
    if c4.button("🗑️ Retirer du panier", key="sup_%s" % identifiant,
                 width="stretch", wrap=True):
        etat.retirer_acte(identifiant)
        _clore_edition(identifiant, "Acte retiré du panier.")
        st.rerun()


def _boutons_hors_composeur(identifiant):
    """Sorties possibles quand le code ne correspond à aucun acte connu."""
    c1, c2 = st.columns(2)
    if c1.button("Annuler", key="ann_%s" % identifiant, width="stretch"):
        _clore_edition(identifiant)
        st.rerun()
    if c2.button("🗑️ Retirer du panier", key="sup_%s" % identifiant,
                 width="stretch"):
        etat.retirer_acte(identifiant)
        _clore_edition(identifiant, "Acte retiré du panier.")
        st.rerun()


def _total_ligne(v):
    base = etat._num(v.get("ponderation"))
    if base is None:
        return 0.0
    majo = etat._num(v.get("majoration")) or 0.0
    return (base + majo) * int(v.get("nb") or 1)


def _resume_codes(v):
    bouts = [v.get(c) for c in ("temps", "lieu", "patient", "tech", "ext",
                                "etapes", "geste")]
    if v.get("niv") in ("1", "2"):
        bouts.append("niv%s" % v["niv"])
    if v.get("coll"):
        bouts.append("coll")
    if v.get("pp"):
        bouts.append("pp")
    if v.get("pat"):
        bouts.append("%d pat." % v["pat"])
    if v.get("nb_inter") and v["nb_inter"] > 1:
        bouts.append("%d interv." % v["nb_inter"])
    return " ".join(b for b in bouts if b) or "—"


def maxi_jours_semaine():
    """Borne haute des jours de présence du lundi au vendredi.

    C'est le dénominateur des scores par jour en hospitalisation complète
    (manuel des GME 2026, vol. 1, § 3.3.2.1). Il couvre le séjour : il
    dépasse 5 dès la deuxième semaine, mais jamais le nombre de journées de
    présence saisi sur la page « Séjour & valorisation », dont il est une
    partie (guide méthodologique 2026, § 2.1.2.2). En temps partiel, ce champ
    ne sert pas : le manuel y divise par tous les jours de présence de la
    semaine (§ 3.3.2.2), qui sont ses journées de présence.
    """
    return max(int(etat.lire("sejour.journees", JOURNEES_DEFAUT)), 1)


def scores(d, gn, jours):
    """Les quatre scores de réadaptation du panier, pour un groupe nosologique.

    Le numérateur couvre toute la période, week-end et jour de sortie compris.
    Le dénominateur ``jours`` ne compte, en hospitalisation complète, que les
    jours de présence du lundi au vendredi : un score par jour peut donc y
    dépasser la pondération réellement produite en une journée — c'est voulu
    par le manuel de groupage. En temps partiel, il compte tous les jours de
    présence de la semaine (manuel des GME 2026, vol. 1, § 3.3.2).
    """
    lignes = [enrichir(d, v) for v in etat.panier()]
    total = sum(_total_ligne(v) for v in lignes)
    libelle_liste, _ = sd.liste_du_gn(d, gn) if gn else ("", None)
    codes_spe = sd.codes_specialises(d, libelle_liste)
    retenus = [v for v in lignes if v["code"] in codes_spe]
    specialise = sum(_total_ligne(v) for v in retenus)
    jours = max(int(jours or 1), 1)
    return {
        "glob_sejour": total, "glob_jour": total / jours,
        "spe_sejour": specialise, "spe_jour": specialise / jours,
        "n_actes": len(lignes), "n_spe": len(retenus),
        "liste": libelle_liste, "jours": jours, "lignes": lignes,
    }


def _bloc_scores(d, lignes, total):
    """Score spécialisé et score par jour, au regard des seuils du GN."""
    ref_gn = d.get("ref_gn")
    if ref_gn is None or ref_gn.empty:
        return

    with st.expander("🎯 Scores de réadaptation par groupe nosologique",
                     expanded=False):
        st.caption(
            "Le score **spécialisé** ne retient que les actes figurant dans la "
            "liste d'actes spécialisés du groupe nosologique ; le score "
            "**global** les retient tous. Chacun est décliné par séjour et par "
            "jour. La comparaison aux seuils oriente vers le groupe de "
            "réadaptation — l'outil ne réalise pas le groupage.")

        options = [""] + ref_gn["gn"].tolist()
        gn = etat.choix(
            "panier.gn", "Groupe nosologique du séjour", options,
            format_func=lambda g: "— non renseigné —" if not g else
            "%s — %s" % (g, sd.libelle_gn(d, g)))
        # Mêmes champs et mêmes bornes que la page « Séjour & valorisation » :
        # c'est le même dénominateur, il ne doit pas exister deux valeurs
        # pour un séjour. Le manuel ne compte pas les mêmes jours selon le
        # type d'hospitalisation (vol. 1, § 3.3.2).
        if etat.lire("sejour.hospitalisation") == "partielle":
            jours = max(etat.nombre(
                "sejour.journees", "Jours de présence dans la semaine",
                0, JOURNEES_MAX_SEMAINE, JOURNEES_DEFAUT,
                help="Dénominateur du score par jour en temps partiel : "
                     "tous les jours de présence de la semaine, week-end "
                     "compris (manuel des GME 2026, vol. 1, § 3.3.2.2). Ce "
                     "sont les journées de présence de la page « Séjour & "
                     "valorisation », qui partage ce champ."), 1)
        else:
            maxi = maxi_jours_semaine()
            jours = etat.nombre(
                "sejour.jours_semaine",
                "Jours de présence du lundi au vendredi, sur le séjour",
                1, maxi, 5,
                help="Dénominateur du score par jour en hospitalisation "
                     "complète (manuel des GME 2026, vol. 1, § 3.3.2.1). Au "
                     "plus %d, les journées de présence saisies sur la page "
                     "« Séjour & valorisation », qui partage ce champ. "
                     "Au-delà de 90 journées, ne compter que les RHS "
                     "jusqu'à celui de la 90ᵉ journée, qui fixent le GME de "
                     "financement." % maxi)

        if not gn:
            return

        libelle_liste, ligne_gn = sd.liste_du_gn(d, gn)
        codes_spe = sd.codes_specialises(d, libelle_liste)
        specialise = sum(_total_ligne(v) for v in lignes
                         if v["code"] in codes_spe)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spécialisé / séjour", "%g" % specialise)
        c2.metric("Spécialisé / jour", "%.1f" % (specialise / jours))
        c3.metric("Global / séjour", "%g" % total)
        c4.metric("Global / jour", "%.1f" % (total / jours))

        if not libelle_liste:
            if ligne_gn is not None and ligne_gn["gr_spe_unique"] == "oui":
                st.info(
                    "Ce groupe nosologique n'a **pas de liste d'actes "
                    "spécialisés** mais dispose d'un groupe de réadaptation "
                    "spécialisée importante **unique** : le score spécialisé "
                    "ne s'applique pas.")
            else:
                st.info("Aucune liste d'actes spécialisés n'est attribuée à ce "
                        "groupe nosologique.")
        else:
            n_spe = sum(1 for v in lignes if v["code"] in codes_spe)
            st.caption(
                "Liste **%s** — %d acte(s) du panier sur %d y figurent."
                % (libelle_liste, n_spe, len(lignes)))

        _seuils(d, gn, specialise, total, jours)


def _seuils(d, gn, specialise, global_, jours):
    """Rappel des seuils publiés pour ce GN et positionnement des scores."""
    gr = d.get("ref_gr")
    if gr is None or gr.empty:
        return
    ligne = gr[gr["gn"] == gn]
    if ligne.empty:
        st.caption("Aucun seuil publié pour ce groupe nosologique.")
        return
    r = ligne.iloc[0]

    def _cmp(valeur, seuil):
        s = etat._num(seuil)
        if s is None:
            return "—"
        return "%s %g / %g" % ("✅" if valeur >= s else "⬜", valeur, s)

    st.markdown("**Positionnement au regard des seuils publiés**")
    st.dataframe(pd.DataFrame([
        {"Hospitalisation": "HC · réadaptation spécialisée",
         "Par séjour": _cmp(specialise, r.get("hc_seuil_sejour_spe")),
         "Par jour": _cmp(specialise / jours, r.get("hc_seuil_jour_spe"))},
        {"Hospitalisation": "HC · réadaptation globale",
         "Par séjour": _cmp(global_, r.get("hc_seuil_sejour_glob")),
         "Par jour": _cmp(global_ / jours, r.get("hc_seuil_jour_glob"))},
        {"Hospitalisation": "HTP · réadaptation globale",
         "Par séjour": "—",
         "Par jour": "seuil bas %s · seuil haut %s"
                     % (r.get("htp_seuil_bas") or "—",
                        r.get("htp_seuil_haut") or "—")},
    ]), width="stretch", hide_index=True)
    st.caption(
        "⬜ score inférieur au seuil · ✅ score atteignant le seuil. "
        "Le groupe de réadaptation dépend aussi des groupes existants pour ce "
        "GN et, en HTP, du positionnement entre seuil bas et seuil haut.")


def _bloc_import():
    with st.expander("📋 Coller des lignes déjà codées", expanded=False):
        st.markdown(FORMAT_LOT)
        if st.button("Charger un exemple", key="ex_lot"):
            etat.ecrire("import_texte", EXEMPLE_LOT)
            etat.resynchroniser("import_texte")
            st.rerun()
        etat.zone_texte("import_texte", "Lignes à ajouter au panier",
                        height=160,
                        placeholder="07S06;22;T2;QM\nGLR+226;22;pat=1")
        st.button("➕ Ajouter au panier", key="btn_import",
                  on_click=_rappel_import, type="primary")
