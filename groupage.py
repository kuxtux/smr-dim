# -*- coding: utf-8 -*-
"""
PMSI SMR — groupage : de la morbidité au groupe nosologique.

Première moitié de la chaîne ``CM → GN → GR → GL → sévérité``, celle qui ne
dépend que des diagnostics :

* la **catégorie majeure** est donnée par la morbidité principale — la
  manifestation morbide principale d'abord, l'affection étiologique ensuite, et
  seulement dans les cas prévus ;
* le **groupe nosologique** est obtenu en parcourant, dans l'ordre, l'arbre de
  décision propre à cette catégorie majeure : le premier nœud entièrement
  satisfait l'emporte.

Chaque fonction renvoie, à côté du résultat, la **trace** de son raisonnement :
quel test a été évalué, sur quelle liste de diagnostics, et pourquoi il a été
retenu ou écarté. C'est ce dont un médecin DIM a besoin pour contrôler un
groupage, bien plus que du seul code final.

Références : manuel de groupage GME 2026, volume 1 § 2.2, et les classeurs
``CIM_infos_SMR.xlsx`` et ``GN_liste_tests.xlsx`` de ``sources/gme/CM et GN/``.
"""

import re

CM_NON_CLASSANTE = "90"

# Les deux listes que met en jeu la règle particulière des fractures multiples.
LISTE_LESIONS = "0896"
LISTE_LESIONS_ASSOCIEES = "0897"


# ---------------------------------------------------------------------------
# Accès aux référentiels
# ---------------------------------------------------------------------------

def normaliser_code(code):
    """Un code CIM-10 tel qu'il est saisi -> tel qu'il est stocké."""
    return str(code or "").replace(".", "").replace(" ", "").upper().strip()


def infos_code(d, code):
    """Ligne du référentiel CIM pour ce code, ou None s'il est inconnu."""
    code = normaliser_code(code)
    if not code:
        return None
    index = d.get("_cim_index")
    if index is None:
        return None
    return index.get(code)


def listes_du_code(d, code):
    """Listes de diagnostics auxquelles appartient ce code."""
    return d.get("_cim_listes", {}).get(normaliser_code(code), frozenset())


def libelle_liste(d, liste):
    ref = d.get("ref_listes_diag")
    if ref is None or ref.empty:
        return ""
    ligne = ref[ref["liste"] == liste]
    return "" if ligne.empty else ligne.iloc[0]["libelle"]


def libelle_cm(d, cm):
    return _libelle_groupe(d, "CM", cm)


def libelle_gn(d, gn):
    return _libelle_groupe(d, "GN", gn)


def _libelle_groupe(d, quoi, code):
    ref = d.get("ref_groupes")
    if ref is None or ref.empty:
        return ""
    ligne = ref[(ref["quoi"] == quoi) & (ref["code"] == code)]
    return "" if ligne.empty else ligne.iloc[0]["lib_long"]


# ---------------------------------------------------------------------------
# Catégorie majeure
# ---------------------------------------------------------------------------

def cm_du_rhs(d, mmp, ae=""):
    """Catégorie majeure d'un RHS. -> dict(cm, origine, trace, alertes).

    La manifestation morbide principale est testée en premier. Les codes dits
    « orientant en deuxième intention » — pour l'essentiel des symptômes — font
    exception : en position de MMP, ils laissent la main à l'affection
    étiologique et ne servent que de repli. Cette notion n'existe **que** pour
    la MMP, jamais pour l'AE.
    """
    resultat = {"cm": CM_NON_CLASSANTE, "origine": "", "trace": [],
                "alertes": []}
    info_mmp = infos_code(d, mmp)
    info_ae = infos_code(d, ae)

    if not normaliser_code(mmp):
        resultat["alertes"].append(
            ("erreur", "La manifestation morbide principale est obligatoire."))
        return resultat
    if info_mmp is None:
        resultat["alertes"].append(
            ("erreur", "Le code %s ne figure pas dans la CIM-10 à usage SMR."
                       % normaliser_code(mmp)))
        return resultat
    if normaliser_code(ae) and info_ae is None:
        resultat["alertes"].append(
            ("avert", "Le code %s, saisi en affection étiologique, ne figure "
                      "pas dans la CIM-10 à usage SMR : il est ignoré."
             % normaliser_code(ae)))

    _controler_position(resultat, info_mmp, "mmp",
                        "manifestation morbide principale")
    if info_ae is not None:
        _controler_position(resultat, info_ae, "ae", "affection étiologique")

    ae_classante = info_ae is not None and info_ae["cm"] != CM_NON_CLASSANTE

    if info_mmp["orientant_2e"] == "oui":
        resultat["trace"].append(
            "La MMP %s est un code **orientant en deuxième intention** : "
            "l'affection étiologique est testée d'abord."
            % info_mmp["code"])
        if ae_classante:
            resultat.update(cm=info_ae["cm"], origine="AE")
            resultat["trace"].append(
                "L'AE %s oriente vers la CM %s : elle l'emporte."
                % (info_ae["code"], info_ae["cm"]))
        else:
            resultat.update(cm=info_mmp["cm"], origine="MMP (repli)")
            resultat["trace"].append(
                "Aucune AE orientante : on retient la CM %s de la MMP, par "
                "repli." % info_mmp["cm"])
        return resultat

    if info_mmp["cm"] != CM_NON_CLASSANTE:
        resultat.update(cm=info_mmp["cm"], origine="MMP")
        resultat["trace"].append(
            "La MMP %s oriente vers la CM %s en première intention ; "
            "l'affection étiologique n'est pas testée."
            % (info_mmp["code"], info_mmp["cm"]))
        return resultat

    resultat["trace"].append(
        "La MMP %s n'oriente vers aucune CM : l'affection étiologique est "
        "testée." % info_mmp["code"])
    if ae_classante:
        resultat.update(cm=info_ae["cm"], origine="AE")
        resultat["trace"].append(
            "L'AE %s oriente vers la CM %s." % (info_ae["code"], info_ae["cm"]))
    else:
        resultat["alertes"].append(
            ("erreur", "Aucune catégorie majeure trouvée : ni la MMP ni "
                       "l'affection étiologique n'orientent. Le séjour part en "
                       "erreur de groupage (CM 90)."))
    return resultat


def _controler_position(resultat, info, position, libelle):
    """Le code est-il autorisé dans cette position du RHS ?"""
    if info[position] != "oui":
        resultat["alertes"].append(
            ("avert",
             "Le code %s n'est pas autorisé en %s (profil %s) : la fonction "
             "groupage le refuserait."
             % (info["code"], libelle, info["profil2"])))


# ---------------------------------------------------------------------------
# Groupe nosologique
# ---------------------------------------------------------------------------

def gn_du_rhs(d, cm, mmp, ae="", das=()):
    """Groupe nosologique dans une CM. -> dict(gn, noeud, trace, alertes).

    On parcourt les nœuds de la CM dans l'ordre croissant et l'on retient le
    premier dont tous les tests sont satisfaits. Un test porte sur une position
    — MMP, AE, « MMP ou AE », ou les DAS — et sur une liste de diagnostics.
    """
    resultat = {"gn": "", "noeud": None, "trace": [], "alertes": []}
    tests = d.get("gn_tests")
    if tests is None or tests.empty or not cm or cm == CM_NON_CLASSANTE:
        return resultat

    noeuds = tests[tests["cm"] == cm].sort_values("ordre")
    if noeuds.empty:
        resultat["alertes"].append(
            ("erreur", "Aucun arbre de décision pour la CM %s." % cm))
        return resultat

    l_mmp = listes_du_code(d, mmp)
    l_ae = listes_du_code(d, ae)
    das = [normaliser_code(x) for x in das if normaliser_code(x)]

    for _, n in noeuds.iterrows():
        ok1, detail1 = _evaluer(d, n["t1_pos"], n["t1_liste"], l_mmp, l_ae,
                                das, mmp, ae, n["regle_speciale"])
        if not ok1:
            continue
        if n["t2_pos"]:
            ok2, detail2 = _evaluer(d, n["t2_pos"], n["t2_liste"], l_mmp, l_ae,
                                    das, mmp, ae, n["regle_speciale"])
            if not ok2:
                resultat["trace"].append(
                    "Nœud %s : premier test franchi (%s), second test échoué "
                    "(%s) — on poursuit." % (n["ordre"], detail1, detail2))
                continue
            resultat["trace"].append(
                "Nœud %s retenu : %s **et** %s." % (n["ordre"], detail1,
                                                    detail2))
        else:
            resultat["trace"].append(
                "Nœud %s retenu : %s." % (n["ordre"], detail1))
        resultat["gn"] = n["gn"]
        resultat["noeud"] = n
        return resultat

    resultat["alertes"].append(
        ("erreur", "Aucun groupe nosologique trouvé dans la CM %s. L'arbre "
                   "étant exhaustif, cela signale une donnée incohérente." % cm))
    return resultat


def _evaluer(d, position, liste, l_mmp, l_ae, das, mmp, ae, regle):
    """Un test d'entrée. -> (satisfait, description en clair)."""
    nom = "D-%s %s" % (liste, libelle_liste(d, liste))
    nom = nom.strip()

    if position == "MMP":
        return liste in l_mmp, "la MMP appartient à %s" % nom
    if position == "AE":
        return liste in l_ae, "l'AE appartient à %s" % nom
    if position == "MMP ou AE":
        return (liste in l_mmp or liste in l_ae), \
            "la MMP ou l'AE appartient à %s" % nom
    if position == "DAS":
        return _evaluer_das(d, liste, das, l_mmp, l_ae, mmp, ae, regle, nom)
    return False, "test non interprété"


def _evaluer_das(d, liste, das, l_mmp, l_ae, mmp, ae, regle, nom):
    """Test portant sur les diagnostics associés.

    Le seul nœud concerné — les fractures multiples — exige en outre que le
    diagnostic associé porte sur une **topographie différente** de celle du
    code classant : les quatre premiers caractères doivent différer.
    """
    candidats = [x for x in das if liste in listes_du_code(d, x)]
    if not candidats:
        return False, "aucun DAS n'appartient à %s" % nom

    if regle != "fractures_multiples":
        return True, "le DAS %s appartient à %s" % (candidats[0], nom)

    classant = normaliser_code(mmp) if LISTE_LESIONS in l_mmp \
        else normaliser_code(ae)
    if not classant:
        return False, "aucun code classant pour comparer la topographie"
    distincts = [x for x in candidats if x[:4] != classant[:4]]
    if not distincts:
        return False, (
            "le ou les DAS de %s portent la même topographie que le code "
            "classant %s (%s)" % (nom, classant, classant[:4]))
    return True, (
        "le DAS %s appartient à %s et porte une topographie différente du code "
        "classant %s" % (distincts[0], nom, classant))


# ---------------------------------------------------------------------------
# Groupe de réadaptation
# ---------------------------------------------------------------------------

AGE_PEDIATRIQUE = 18

# 5ᵉ caractère du GR. En hospitalisation complète : pédiatrique, réadaptation
# spécialisée importante, globale importante, autre. En temps partiel :
# pédiatrique, très intense, intense, modérée, indifférenciée.
LETTRES_GR = {
    "P": "réadaptation pédiatrique", "S": "réadaptation spécialisée importante",
    "T": "réadaptation globale importante", "U": "autre réadaptation",
    "H": "réadaptation pédiatrique", "I": "réadaptation très intense",
    "J": "réadaptation intense", "K": "réadaptation modérée",
    "L": "réadaptation indifférenciée",
}


def _seuil(ligne, colonne):
    try:
        return float(str(ligne.get(colonne, "")).replace(",", ".") or "nan")
    except (TypeError, ValueError):
        return float("nan")


def _existe(ligne, colonne):
    return str(ligne.get(colonne, "")).strip().lower() == "oui"


def gr_du_sejour(d, gn, age, scores, temps_partiel=False):
    """Groupe de réadaptation. -> dict(gr, lettre, trace, alertes).

    En hospitalisation complète, quatre tests successifs : pédiatrique, puis
    réadaptation spécialisée importante, puis globale importante, puis autre.
    Un test de score n'est positif que si le score **par séjour et** le score
    par jour dépassent tous deux leur seuil.

    En temps partiel, un seul indicateur — le score global par jour de la
    semaine — départage très intense, intense et modérée ; le groupe est
    déterminé **par semaine**, non pour l'ensemble du séjour.
    """
    resultat = {"gr": "", "lettre": "", "trace": [], "alertes": []}
    ref = d.get("ref_gr")
    if not gn or ref is None or ref.empty:
        return resultat
    ligne = ref[ref["gn"] == gn]
    if ligne.empty:
        resultat["alertes"].append(
            ("erreur", "Aucun groupe de réadaptation publié pour le GN %s."
                       % gn))
        return resultat
    ligne = ligne.iloc[0]

    _, info_gn = liste_du_gn_local(d, gn)
    spe_unique = info_gn is not None and info_gn.get("gr_spe_unique") == "oui"

    lettre = (_gr_temps_partiel(ligne, age, scores, resultat)
              if temps_partiel
              else _gr_hospitalisation_complete(ligne, age, scores, resultat,
                                                spe_unique))
    resultat["lettre"] = lettre
    resultat["gr"] = gn + lettre if lettre else ""
    return resultat


def liste_du_gn_local(d, gn):
    """Ligne du référentiel des groupes nosologiques (liste et GR spé unique)."""
    ref = d.get("ref_gn")
    if ref is None or ref.empty:
        return "", None
    trouve = ref[ref["gn"] == gn]
    if trouve.empty:
        return "", None
    return trouve.iloc[0]["libelle_gn_liste"], trouve.iloc[0]


def _gr_hospitalisation_complete(ligne, age, scores, resultat, spe_unique):
    pediatrique = _existe(ligne, "hc_pediatrique")
    specialisee = _existe(ligne, "hc_specialisee")
    globale = _existe(ligne, "hc_globale")

    if age is not None and age < AGE_PEDIATRIQUE:
        if pediatrique:
            resultat["trace"].append(
                "Patient de %d ans et ce groupe nosologique dispose d'une "
                "subdivision pédiatrique : orientation immédiate, sans calcul "
                "de score." % age)
            return "P"
        cible = "S" if specialisee else ("T" if globale else "U")
        resultat["trace"].append(
            "Patient de %d ans mais ce groupe nosologique n'a pas de "
            "subdivision pédiatrique : orientation **sans aucun test de "
            "score** vers la %s." % (age, LETTRES_GR[cible]))
        return cible

    if specialisee:
        if spe_unique:
            resultat["trace"].append(
                "Ce groupe nosologique n'a pas de liste d'actes spécialisés "
                "mais dispose d'un groupe de réadaptation spécialisée "
                "**unique** : classement direct, sans test de score.")
            return "S"
        s_jour = _seuil(ligne, "hc_seuil_jour_spe")
        s_sejour = _seuil(ligne, "hc_seuil_sejour_spe")
        ok, detail = _tester(scores["spe_jour"], s_jour,
                             scores["spe_sejour"], s_sejour, "spécialisé")
        resultat["trace"].append(detail)
        if ok:
            return "S"

    if globale:
        g_jour = _seuil(ligne, "hc_seuil_jour_glob")
        g_sejour = _seuil(ligne, "hc_seuil_sejour_glob")
        ok, detail = _tester(scores["glob_jour"], g_jour,
                             scores["glob_sejour"], g_sejour, "global")
        resultat["trace"].append(detail)
        if ok:
            return "T"

    resultat["trace"].append(
        "Aucun seuil atteint : classement en autre réadaptation.")
    return "U"


def _tester(par_jour, seuil_jour, par_sejour, seuil_sejour, nom):
    """Test de score : les deux conditions doivent être remplies."""
    import math
    if math.isnan(seuil_jour) or math.isnan(seuil_sejour):
        return False, ("Test %s impossible : les seuils ne sont pas publiés "
                       "pour ce groupe nosologique." % nom)
    ok_jour = par_jour >= seuil_jour
    ok_sejour = par_sejour >= seuil_sejour
    verdict = "franchi" if (ok_jour and ok_sejour) else "non franchi"
    return ok_jour and ok_sejour, (
        "Test %s **%s** : %.1f par jour pour un seuil de %g (%s) et %g par "
        "séjour pour un seuil de %g (%s). Les deux conditions sont exigées."
        % (nom, verdict, par_jour, seuil_jour, "atteint" if ok_jour else "non "
           "atteint", par_sejour, seuil_sejour,
           "atteint" if ok_sejour else "non atteint"))


def _gr_temps_partiel(ligne, age, scores, resultat):
    pediatrique = _existe(ligne, "htp_pediatrique")
    gradue = all(_existe(ligne, c) for c in ("htp_tres_intense", "htp_intense",
                                             "htp_moderee"))

    if age is not None and age < AGE_PEDIATRIQUE:
        if pediatrique:
            resultat["trace"].append(
                "Patient de %d ans et subdivision pédiatrique existante : "
                "orientation immédiate." % age)
            return "H"
        cible = "I" if _existe(ligne, "htp_tres_intense") else "L"
        resultat["trace"].append(
            "Patient de %d ans sans subdivision pédiatrique : orientation "
            "**sans test** vers la %s." % (age, LETTRES_GR[cible]))
        return cible

    if not gradue:
        resultat["trace"].append(
            "Ce groupe nosologique n'est pas gradué en temps partiel : "
            "classement en réadaptation indifférenciée, sans seuil.")
        return "L"

    haut = _seuil(ligne, "htp_seuil_haut")
    bas = _seuil(ligne, "htp_seuil_bas")
    score = scores["glob_jour"]
    if score >= haut:
        resultat["trace"].append(
            "Score global par jour de %.1f, supérieur au seuil très intense "
            "de %g." % (score, haut))
        return "I"
    if score >= bas:
        resultat["trace"].append(
            "Score global par jour de %.1f : inférieur au seuil très intense "
            "de %g, supérieur au seuil intense de %g." % (score, haut, bas))
        return "J"
    resultat["trace"].append(
        "Score global par jour de %.1f, inférieur au seuil intense de %g."
        % (score, bas))
    return "K"


# ---------------------------------------------------------------------------
# Groupe de lourdeur
# ---------------------------------------------------------------------------

# Cotation de la dépendance selon la grille des activités de la vie
# quotidienne (guide méthodologique SMR, chapitre VII). Quatre items composent
# la dépendance physique, deux la dépendance cognitive.
ITEMS_PHYSIQUES = [
    ("habillage", "Habillage ou toilette"),
    ("deplacement", "Déplacement et locomotion"),
    ("alimentation", "Alimentation"),
    ("continence", "Continence — hygiène de l'élimination"),
]
ITEMS_COGNITIFS = [
    ("comportement", "Comportement"),
    ("communication", "Communication"),
]

COTATION = {
    1: "Indépendance — sans aide humaine",
    2: "Supervision ou arrangement — présence d'un tiers, sans contact physique",
    3: "Assistance partielle — aide par un tiers",
    4: "Assistance totale — réalisation par un tiers",
}

ORDRE_NIVEAU = {"A": 0, "B": 1, "C": 2}

# Une règle combinée fait dépendre le niveau de l'âge : « age 18_70 -> B ».
RE_REGLE_COMBINEE = re.compile(r"age\s+(\d+)_(\d+|plus)\s*-+>\s*([ABC])")

DELAI_POST_CHIRURGICAL = 90   # jours


def classe_age(age):
    for borne, colonne in ((3, "a0_3"), (12, "a4_12"), (17, "a13_17"),
                           (60, "a18_60"), (70, "a61_70"), (75, "a71_75"),
                           (80, "a76_80"), (85, "a81_85")):
        if age <= borne:
            return colonne
    return "a86_plus"


def score_physique(cotations):
    """Somme des quatre items physiques, de 4 à 16."""
    return sum(int(cotations.get(c, 1) or 1) for c, _ in ITEMS_PHYSIQUES)


def score_cognitif(cotations):
    """Somme des deux items cognitifs, de 2 à 8."""
    return sum(int(cotations.get(c, 1) or 1) for c, _ in ITEMS_COGNITIFS)


def _resoudre(cellule, age):
    """Contenu d'une cellule de la table -> niveau, ou None si sans objet."""
    cellule = str(cellule or "").strip()
    if not cellule or cellule == "-":
        return None
    if cellule in ORDRE_NIVEAU:
        return cellule
    for bas, haut, niveau in RE_REGLE_COMBINEE.findall(cellule):
        borne = 999 if haut == "plus" else int(haut)
        if int(bas) <= age <= borne:
            return niveau
    return None


def gl_du_sejour(d, gr, age, cotations, post_chirurgical=False,
                 temps_partiel=False):
    """Niveau de lourdeur. -> dict(gl, niveau, contributions, trace, alertes).

    Quatre variables seulement entrent en jeu : l'âge, la dépendance physique,
    la dépendance cognitive et le statut post-chirurgical. Chacune désigne une
    colonne de la table, la cellule donne le niveau qu'elle entraîne, et c'est
    le **maximum** des quatre qui est retenu — A < B < C.

    En temps partiel, le niveau vaut toujours A, par convention : le groupe de
    lourdeur existe bien, mais il n'est pas gradué.

    L'âge et le statut post-chirurgical se lisent sur le premier RHS du
    séjour ; les deux scores de dépendance sont les **maximums** observés sur
    l'ensemble des RHS.
    """
    resultat = {"gl": "", "niveau": "", "contributions": {}, "trace": [],
                "alertes": [], "phy": score_physique(cotations),
                "cog": score_cognitif(cotations)}
    if not gr:
        return resultat

    if temps_partiel or (len(gr) >= 5 and gr[4] in "HIJKL"):
        resultat.update(gl=gr + "A", niveau="A")
        resultat["trace"].append(
            "Hospitalisation à temps partiel : le niveau de lourdeur vaut "
            "toujours **A**, sans aucun test. Le groupe de lourdeur existe "
            "bien en temps partiel, il n'y est simplement pas gradué.")
        return resultat

    table = d.get("gl_regles")
    if table is None or table.empty:
        return resultat
    ligne = table[table["gr"] == gr]
    if ligne.empty:
        resultat["alertes"].append(
            ("erreur", "Aucune règle de lourdeur publiée pour le GR %s." % gr))
        return resultat
    ligne = ligne.iloc[0]

    phy, cog = resultat["phy"], resultat["cog"]
    colonnes = {
        "âge": classe_age(age),
        "dépendance cognitive": "g02_06" if cog <= 6 else "g07_08",
        "dépendance physique": ("y04_08" if phy <= 8
                                else ("y09_12" if phy <= 12 else "y13_16")),
        "statut post-chirurgical": "c_avec" if post_chirurgical else "c_sans",
    }
    for nom, colonne in colonnes.items():
        niveau = _resoudre(ligne[colonne], age)
        resultat["contributions"][nom] = niveau

    niveaux = [n for n in resultat["contributions"].values() if n]
    if not niveaux:
        resultat["alertes"].append(
            ("erreur", "Aucune des quatre variables n'est applicable au GR %s "
                       "pour un patient de %d ans." % (gr, age)))
        return resultat

    niveau = max(niveaux, key=ORDRE_NIVEAU.get)
    resultat.update(gl=gr + niveau, niveau=niveau)
    determinantes = [n for n, v in resultat["contributions"].items()
                     if v == niveau]
    resultat["trace"].append(
        "Dépendance physique %d sur 16, dépendance cognitive %d sur 8, "
        "patient de %d ans, %s intervention chirurgicale de moins de %d jours."
        % (phy, cog, age, "avec" if post_chirurgical else "sans",
           DELAI_POST_CHIRURGICAL))
    resultat["trace"].append(
        "Niveaux entraînés — " + " · ".join(
            "%s : %s" % (n, v or "sans objet")
            for n, v in resultat["contributions"].items()))
    resultat["trace"].append(
        "Le maximum l'emporte : niveau **%s**, déterminé par %s."
        % (niveau, " et ".join(determinantes)))
    return resultat


# ---------------------------------------------------------------------------
# Niveau de sévérité
# ---------------------------------------------------------------------------

def codes_orientants(d, noeud, mmp, ae):
    """Codes qui ont effectivement fait entrer le séjour dans son GN.

    Ce sont eux, et eux seuls, qui peuvent neutraliser une complication : une
    comorbidité déjà impliquée par la pathologie traitée n'ajoute pas de
    sévérité. On relit donc les tests du nœud retenu pour savoir lesquels des
    deux codes de la morbidité principale les ont satisfaits.
    """
    if noeud is None:
        return set()
    orientants = set()
    l_mmp, l_ae = listes_du_code(d, mmp), listes_du_code(d, ae)
    for position, liste in ((noeud["t1_pos"], noeud["t1_liste"]),
                            (noeud["t2_pos"], noeud["t2_liste"])):
        if not position or not liste:
            continue
        if position in ("MMP", "MMP ou AE") and liste in l_mmp:
            orientants.add(normaliser_code(mmp))
        if position in ("AE", "MMP ou AE") and liste in l_ae:
            orientants.add(normaliser_code(ae))
    return {c for c in orientants if c}


def est_cma(d, code):
    info = infos_code(d, code)
    return info is not None and info["cma"] == "X"


def exclusions_de(d, code):
    """Codes qui neutralisent ce marqueur de sévérité."""
    liste = d.get("_cma_liste", {}).get(normaliser_code(code))
    if not liste:
        return frozenset()
    return d.get("_cma_membres", {}).get(liste, frozenset())


def severite_du_sejour(d, gl, mmp, ae="", das=(), ccam=(), orientants=(),
                       temps_partiel=False, inclure_ae=False):
    """Niveau de sévérité. -> dict(niveau, gme, marqueurs, trace, alertes).

    Le niveau est binaire en hospitalisation complète : 2 dès qu'un marqueur de
    sévérité subsiste, 1 sinon. Il n'y a ni comptage ni degré — une seule
    complication non exclue suffit. En temps partiel il vaut 0.

    Un marqueur est soit un diagnostic portant le drapeau CMA, soit l'un des
    21 actes CCAM qui valent complication à eux seuls et que rien ne peut
    neutraliser.

    ``inclure_ae`` reflète une contradiction du manuel sur la position de
    l'affection étiologique : voir la note affichée à l'écran.
    """
    resultat = {"niveau": "", "gme": "", "marqueurs": [], "exclus": [],
                "trace": [], "alertes": []}
    if not gl:
        return resultat

    if temps_partiel or (len(gl) >= 5 and gl[4] in "HIJKL"):
        resultat.update(niveau="0", gme=gl + "0")
        resultat["trace"].append(
            "Hospitalisation à temps partiel : le niveau de sévérité vaut "
            "**0** par convention. Les niveaux 1 et 2 sont propres à "
            "l'hospitalisation complète.")
        return resultat

    orientants = {normaliser_code(c) for c in orientants if normaliser_code(c)}

    # Diagnostics candidats, selon la position retenue.
    candidats = [("manifestation morbide principale", normaliser_code(mmp))]
    if inclure_ae:
        candidats.append(("affection étiologique", normaliser_code(ae)))
    candidats += [("diagnostic associé", normaliser_code(x)) for x in das]

    for position, code in candidats:
        if not code or not est_cma(d, code):
            continue
        bloquants = exclusions_de(d, code) & orientants
        info = infos_code(d, code)
        libelle = info["libelle"].capitalize() if info else ""
        if bloquants:
            resultat["exclus"].append({
                "code": code, "position": position, "libelle": libelle,
                "par": sorted(bloquants)})
        else:
            resultat["marqueurs"].append({
                "code": code, "position": position, "libelle": libelle})

    for acte in ccam:
        code7 = str(acte or "").upper().replace(" ", "")[:7]
        if code7 and code7 in d.get("_cma_ccam", frozenset()):
            resultat["marqueurs"].append({
                "code": code7, "position": "acte CCAM",
                "libelle": _libelle_ccam(d, code7)})

    niveau = "2" if resultat["marqueurs"] else "1"

    # Tous les groupes de lourdeur n'ont pas de niveau 2 : les soins palliatifs
    # n'en ont pas. On le teste sur la nomenclature plutôt que de coder le
    # groupe nosologique en dur.
    publiees = d.get("_severites_publiees", {}).get(gl, set())
    if niveau == "2" and publiees and "2" not in publiees:
        resultat["trace"].append(
            "Un marqueur de sévérité a été trouvé, mais le niveau 2 n'existe "
            "pas pour ce groupe de lourdeur : le niveau 1 est retenu.")
        niveau = "1"
    elif publiees and niveau not in publiees:
        resultat["alertes"].append(
            ("avert", "Le niveau %s n'est pas publié pour le groupe de "
                      "lourdeur %s." % (niveau, gl)))

    resultat.update(niveau=niveau, gme=gl + niveau)
    if resultat["marqueurs"]:
        resultat["trace"].append(
            "%d marqueur(s) de sévérité retenu(s) : %s. Un seul suffit à "
            "porter le niveau à 2."
            % (len(resultat["marqueurs"]),
               ", ".join("%s (%s)" % (m["code"], m["position"])
                         for m in resultat["marqueurs"])))
    else:
        resultat["trace"].append(
            "Aucun marqueur de sévérité : niveau 1.")
    for e in resultat["exclus"]:
        resultat["trace"].append(
            "Le code %s est bien une complication, mais il est **exclu** par "
            "%s, qui a orienté le séjour vers son groupe nosologique : il "
            "n'apporte pas de sévérité."
            % (e["code"], " et ".join(e["par"])))
    return resultat


def _libelle_ccam(d, code7):
    ref = d.get("ref_cma_ccam")
    if ref is None or ref.empty:
        return ""
    ligne = ref[ref["code7"] == code7]
    return "" if ligne.empty else ligne.iloc[0]["libelle"]


# ---------------------------------------------------------------------------
# Chaîne complète
# ---------------------------------------------------------------------------

def grouper(d, mmp, ae="", das=()):
    """Enchaîne CM puis GN. -> dict(cm, gn, traces, alertes)."""
    r_cm = cm_du_rhs(d, mmp, ae)
    resultat = {
        "cm": r_cm["cm"], "cm_origine": r_cm["origine"],
        "cm_libelle": libelle_cm(d, r_cm["cm"]),
        "trace_cm": r_cm["trace"], "alertes": list(r_cm["alertes"]),
        "gn": "", "gn_libelle": "", "trace_gn": [], "noeud": None,
    }
    if r_cm["cm"] == CM_NON_CLASSANTE:
        return resultat

    r_gn = gn_du_rhs(d, r_cm["cm"], mmp, ae, das)
    resultat.update(
        gn=r_gn["gn"], gn_libelle=libelle_gn(d, r_gn["gn"]),
        trace_gn=r_gn["trace"], noeud=r_gn["noeud"])
    resultat["alertes"].extend(r_gn["alertes"])
    return resultat
