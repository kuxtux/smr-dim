# -*- coding: utf-8 -*-
"""
PMSI SMR — valorisation d'un séjour à partir de son GME.

Chaîne : GN → GME → GMT → tarif. Un GME est tarifé par un à quatre GMT :

* **principal** (codes 0xxx et 1xxx) — temps partiel, et hospitalisation
  complète jusqu'à 90 journées de présence ;
* **hebdomadaire** (7xxx) — journées au-delà de la 90ᵉ ;
* **court** (8xxx) — séjour de moins de 8 journées terminé par transfert,
  mutation ou décès ;
* les soins palliatifs (GN 2303) ont **trois** GMT principaux, un par lieu de
  prise en charge, dont un seul est facturable.

Les trois blocs partagent la même structure à trois zones. Pour les blocs
hebdomadaire et court, ``DZF = FZF = 7`` et ``SZB = SZH`` : la formule y
dégénère en un prix de journée, ce qui permet de n'écrire qu'une seule
fonction de zone. Attention, ``SZH`` y vaut *approximativement* ``TZF1 / 7``
— l'arrêté publie une valeur arrondie au centime, qui s'en écarte de moins
d'un centime par journée. C'est la valeur publiée qui est appliquée, et non
le quotient recalculé : d'où de légers écarts, de l'ordre de quelques euros
sur un séjour très long, avec un calcul qui recalculerait ``TZF1 / 7``.

Règles : arrêté du 4 décembre 2023 (classification et prise en charge des
prestations) et arrêté du 12 janvier 2026 (tarifs), dont les annexes sont à
déposer dans ``sources/``.
"""

import pandas as pd
import streamlit as st

from smr import etat
from smr.actes import panier
from smr.base import donnees as sd
from smr.sejour import groupage

# Catégorie de l'établissement pour lequel l'outil est paramétré : le a de
# l'article L.162-22 du code de la sécurité sociale (établissement public de
# santé), donc grille ex-DAF (annexe I) et coefficient de revalorisation
# salariale correspondant.
CATEGORIE_ETABLISSEMENT = "a de l'article L.162-22"
PREFIXE_CATEGORIE = "etablissements mentionnes au a "

# Département d'implantation : il ne figure dans aucune zone de l'annexe III,
# donc coefficient géographique nul. On le vérifie contre la table plutôt que
# d'écrire zéro en dur, pour que l'outil se corrige seul si l'annexe évolue.
DEPARTEMENT = "56"

MODES_SORTIE = {
    "autre": "Autre mode de sortie (domicile…)",
    "transfert": "Transfert",
    "mutation": "Mutation",
    "deces": "Décès",
}
MODES_COURTS = ("transfert", "mutation", "deces")

SEUIL_LONG = 90        # journées de présence au-delà desquelles le GMT 7xxx joue
SEUIL_COURT = 8        # séjour « court » = strictement moins de 8 journées


def _n(v):
    """Cellule -> nombre, ou None si vide / non numérique."""
    try:
        s = str(v).strip().replace(",", ".")
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Accès aux tarifs
# ---------------------------------------------------------------------------

def gmt_du_gme(d, gme, bloc=None):
    """Lignes tarifaires d'un GME, éventuellement filtrées sur un bloc."""
    t = d.get("tarifs_gmt")
    if t is None or t.empty:
        return pd.DataFrame()
    lignes = t[t["gme"] == gme]
    if bloc:
        lignes = lignes[lignes["bloc"] == bloc]
    return lignes


def est_temps_partiel(gme):
    """Le 5ᵉ caractère du GME donne le type de réadaptation, donc le régime."""
    return len(gme) >= 5 and gme[4] in "HIJKL"


def gme_connus(d):
    t = d.get("tarifs_gmt")
    return [] if t is None or t.empty else sorted(t["gme"].unique())


# ---------------------------------------------------------------------------
# Formule de zone
# ---------------------------------------------------------------------------

def montant_zone(p, journees):
    """Montant d'un GMT pour un nombre de journées. -> (montant, libellé).

    Zone basse ``J < DZF``     : TZB − (DZF − J) × SZB
    Zone forfaitaire           : TZF de la semaine atteinte
    Zone haute  ``J > FZF``    : dernier TZF + (J − FZF) × SZH

    La courbe est continue : en ``J = DZF`` la formule de la zone basse redonne
    exactement TZB. Une journée au moins est toujours décomptée.

    Toute donnée tarifaire manquante fait renvoyer ``(None, "tarif
    incomplet")`` : un montant plausible tiré d'un tarif incomplet serait plus
    dangereux qu'une absence de montant. En particulier, cette fonction ne sait
    pas valoriser une ligne de temps partiel, qui ne porte ni TZB, ni SZB, ni
    SZH — c'est ``valoriser`` qui l'intercepte en amont.
    """
    try:
        journees = int(journees)
    except (TypeError, ValueError):
        return None, "nombre de journées invalide"
    if journees < 0:
        return None, "nombre de journées négatif"
    journees = max(journees, 1)

    dzf, fzf = _n(p["dzf"]), _n(p["fzf"])
    if dzf is None or fzf is None or dzf < 1 or fzf < dzf:
        return None, "bornes de zone absentes ou incohérentes"
    dzf, fzf = int(dzf), int(fzf)

    tzb, szb, szh = _n(p["tzb"]), _n(p["szb"]), _n(p["szh"])
    forfaits = [_n(p["tzf1"]), _n(p["tzf2"]), _n(p["tzf3"])]
    connus = [t for t in forfaits if t is not None]
    if not connus:
        return None, "tarif incomplet"

    if journees < dzf:
        if tzb is None or szb is None:
            return None, "tarif incomplet"
        return tzb - (dzf - journees) * szb, "zone basse"

    if journees <= fzf:
        semaine = 1 + (journees - dzf) // 7
        if not 1 <= semaine <= 3 or forfaits[semaine - 1] is None:
            return None, "tarif incomplet"
        libelle = "zone forfaitaire"
        if len(connus) > 1:
            libelle += " — semaine %d" % semaine
        return forfaits[semaine - 1], libelle

    if szh is None:
        return None, "tarif incomplet"
    return connus[-1] + (journees - fzf) * szh, "zone haute"


# ---------------------------------------------------------------------------
# Valorisation d'un séjour
# ---------------------------------------------------------------------------

def coefficients(d):
    """Coefficients applicables à l'établissement paramétré.

    Les trois coefficients s'appliquent conjointement, donc en se multipliant,
    et **tous s'écrivent (1 + coefficient)**. Le coefficient honoraires est
    défini par la notice technique comme un ratio diminué de 1, donc
    structurellement négatif : c'est lui qui porte son propre signe, il ne faut
    pas le soustraire une seconde fois.

    Renvoie aussi les alertes rencontrées : un coefficient qu'on ne retrouve
    plus dans les annexes doit se signaler, pas retomber silencieusement à zéro.
    """
    alertes = []

    segur = None
    ref = d.get("ref_coef_segur")
    if ref is not None and not ref.empty:
        cible = ref[ref["categorie"].map(sd.normaliser).str.startswith(
            sd.normaliser(PREFIXE_CATEGORIE))]
        if not cible.empty:
            segur = _n(cible.iloc[0]["coefficient"])
    if segur is None:
        alertes.append(
            ("avert",
             "Le coefficient de revalorisation salariale n'a pas été retrouvé "
             "dans l'annexe V pour la catégorie « %s » : il est ignoré, et le "
             "montant est donc sous-évalué. L'intitulé de la ligne a "
             "probablement changé dans l'arrêté."
             % CATEGORIE_ETABLISSEMENT))
        segur = 0.0

    # Coefficient géographique : vérifié contre l'annexe plutôt qu'écrit en dur.
    geo = 0.0
    zones = d.get("ref_coef_geo")
    if zones is not None and not zones.empty:
        cible = zones[zones["zone"].str.strip().str.startswith(DEPARTEMENT)]
        if not cible.empty:
            geo = _n(cible.iloc[0]["coefficient"]) or 0.0
            alertes.append(
                ("avert",
                 "Le département %s figure désormais dans l'annexe III avec un "
                 "coefficient géographique de %+.2f %% : vérifiez le "
                 "paramétrage de l'outil." % (DEPARTEMENT, geo * 100)))

    return {
        "geographique": geo,
        "segur": segur,
        "honoraires": 0.0,   # sans objet : établissement à personnel salarié
        "alertes": alertes,
    }


def valoriser(d, gme, journees, mode_sortie="autre", gmt_choisi=None,
              appliquer_coefficients=True):
    """Valorise un séjour. Renvoie un dict détaillant chaque étape."""
    coefs = coefficients(d) if appliquer_coefficients else {
        "geographique": 0.0, "segur": 0.0, "honoraires": 0.0, "alertes": []}
    resultat = {
        "gme": gme, "journees": 0, "regime": "", "etapes": [],
        "brut": 0.0, "net": 0.0, "facteur": 1.0,
        "alertes": list(coefs.pop("alertes", [])), "coefficients": coefs,
    }

    # --- validation des entrées ------------------------------------------
    try:
        resultat["journees"] = int(journees)
    except (TypeError, ValueError):
        resultat["alertes"].append(
            ("erreur", "Nombre de journées de présence invalide : « %s »."
                       % journees))
        return resultat
    if resultat["journees"] < 0:
        resultat["alertes"].append(
            ("erreur", "Le nombre de journées de présence ne peut pas être "
                       "négatif."))
        return resultat
    if resultat["journees"] == 0:
        resultat["alertes"].append(
            ("avert",
             "Aucune journée de présence décomptée. En hospitalisation "
             "complète, la règle applique l'écart entre le début de zone "
             "forfaitaire et une journée ; en temps partiel, il n'y a rien à "
             "facturer."))

    if mode_sortie not in MODES_SORTIE:
        resultat["alertes"].append(
            ("erreur", "Mode de sortie inconnu : « %s ». Valeurs admises : %s."
                       % (mode_sortie, ", ".join(MODES_SORTIE))))
        return resultat

    lignes = gmt_du_gme(d, gme)
    if lignes.empty:
        resultat["alertes"].append(
            ("erreur", "Le GME %s ne figure pas dans la grille tarifaire "
                       "chargée." % gme))
        return resultat

    principaux = lignes[lignes["bloc"] == "principal"]
    if gmt_choisi:
        retenu = principaux[principaux["gmt"] == gmt_choisi]
        if retenu.empty:
            resultat["alertes"].append(
                ("erreur", "Le GMT %s n'est pas un GMT principal du GME %s."
                           % (gmt_choisi, gme)))
            return resultat
        principaux = retenu
    elif len(principaux) > 1:
        resultat["alertes"].append(
            ("avert",
             "Ce GME dispose de %d GMT principaux, qui se distinguent par le "
             "lieu de prise en charge (article 3). Aucun n'a été désigné : "
             "c'est le premier, **%s**, qui est retenu. Les montants vont de "
             "%s à %s — désignez le bon."
             % (len(principaux), principaux.iloc[0]["gmt"],
                _euro(min(_n(t) for t in principaux["tzf1"])),
                _euro(max(_n(t) for t in principaux["tzf1"])))))

    # --- temps partiel : un seul GMT, prix de journée ----------------------
    if est_temps_partiel(gme):
        if principaux.empty:
            resultat["alertes"].append(
                ("erreur", "Aucun GMT principal pour ce GME de temps "
                           "partiel."))
            return resultat
        p = principaux.iloc[0]
        tarif = _n(p["tzf1"])
        if tarif is None:
            resultat["alertes"].append(
                ("erreur", "Le GMT %s ne porte pas de tarif : le séjour ne "
                           "peut pas être valorisé." % p["gmt"]))
            return resultat
        resultat["regime"] = "Temps partiel"
        resultat["brut"] = tarif * resultat["journees"]
        resultat["etapes"].append({
            "libelle": "%d journée(s) × TZF1" % resultat["journees"],
            "gmt": p["gmt"], "zone": "prix de journée",
            "detail": "%d × %s" % (resultat["journees"], _euro(tarif)),
            "montant": resultat["brut"],
        })
        return _finaliser(resultat)

    # --- hospitalisation complète -----------------------------------------
    journees = resultat["journees"]
    courts = lignes[lignes["bloc"] == "court"]

    if journees < SEUIL_COURT and mode_sortie in MODES_COURTS:
        if courts.empty:
            resultat["alertes"].append(
                ("info", "Ce groupe nosologique ne dispose pas de GMT « séjour "
                         "court » : le séjour est valorisé sur le GMT "
                         "principal."))
        else:
            p = courts.iloc[0]
            montant, zone = montant_zone(p, journees)
            resultat["regime"] = "Séjour court (< 8 journées, sortie par %s)" \
                % MODES_SORTIE[mode_sortie].lower()
            resultat["brut"] = montant or 0.0
            resultat["etapes"].append({
                "libelle": "Séjour court", "gmt": p["gmt"], "zone": zone,
                "detail": _detail(p, journees, zone),
                "montant": resultat["brut"]})
            return _finaliser(resultat)

    if principaux.empty:
        resultat["alertes"].append(
            ("erreur", "Aucun GMT principal pour ce GME."))
        return resultat
    p = principaux.iloc[0]

    if journees <= SEUIL_LONG:
        montant, zone = montant_zone(p, journees)
        if montant is None:
            resultat["alertes"].append(
                ("erreur", "GMT %s : %s." % (p["gmt"], zone)))
            return resultat
        resultat["regime"] = "Hospitalisation complète"
        resultat["brut"] = montant
        resultat["etapes"].append({
            "libelle": "%d journée(s)" % journees, "gmt": p["gmt"],
            "zone": zone, "detail": _detail(p, journees, zone),
            "montant": resultat["brut"]})
        return _finaliser(resultat)

    # --- séjour de plus de 90 journées : coupure --------------------------
    resultat["regime"] = "Séjour long (plus de 90 journées)"
    montant, zone = montant_zone(p, SEUIL_LONG)
    if montant is None:
        resultat["alertes"].append(
            ("erreur", "GMT %s : %s." % (p["gmt"], zone)))
        return resultat
    resultat["etapes"].append({
        "libelle": "90 premières journées", "gmt": p["gmt"], "zone": zone,
        "detail": _detail(p, SEUIL_LONG, zone), "montant": montant})

    hebdo = lignes[lignes["bloc"] == "hebdomadaire"]
    reste = journees - SEUIL_LONG
    if hebdo.empty:
        resultat["alertes"].append(
            ("erreur", "Aucun GMT hebdomadaire pour ce GME : les %d journées "
                       "au-delà de la 90ᵉ ne peuvent pas être valorisées."
             % reste))
        supplement = 0.0
    else:
        h = hebdo.iloc[0]
        par_jour = _n(h["szh"])
        if par_jour is None:
            resultat["alertes"].append(
                ("erreur", "Le GMT hebdomadaire %s ne porte pas de prix de "
                           "journée." % h["gmt"]))
            return resultat
        supplement = par_jour * reste
        resultat["etapes"].append({
            "libelle": "%d journée(s) au-delà de la 90ᵉ" % reste,
            "gmt": h["gmt"], "zone": "prix de journée",
            "detail": "%d × %s (SZH publié)" % (reste, _euro(par_jour)),
            "montant": supplement})

    resultat["brut"] = montant + supplement
    resultat["alertes"].append(
        ("info", "Pour un séjour de plus de 90 journées, le GME et le GMT de "
                 "financement sont calculés sur les seuls RHS allant jusqu'à "
                 "celui qui contient la 90ᵉ journée. À la clôture, un second "
                 "GME est déterminé sur l'ensemble des RHS (GME_d), à des fins "
                 "de description de l'activité et non de financement."))
    return _finaliser(resultat)


def _finaliser(resultat):
    """Applique les coefficients et arrondit au centime.

    Les trois coefficients se multiplient, chacun sous la forme
    ``(1 + coefficient)`` : le coefficient honoraires porte déjà son signe
    négatif, le soustraire reviendrait à majorer le montant.
    """
    c = resultat["coefficients"]
    facteur = ((1 + c["geographique"]) * (1 + c["segur"])
               * (1 + c["honoraires"]))
    resultat["facteur"] = facteur
    resultat["brut"] = round(resultat["brut"], 2)
    resultat["net"] = round(resultat["brut"] * facteur, 2)
    for etape in resultat["etapes"]:
        etape["montant"] = round(etape["montant"], 2)
    return resultat


def _detail(p, journees, zone):
    """Formule appliquée, en clair."""
    dzf, fzf = int(_n(p["dzf"]) or 1), int(_n(p["fzf"]) or 1)
    if zone.startswith("zone basse"):
        return "%s − (%d − %d) × %s" % (_euro(_n(p["tzb"])), dzf, journees,
                                        _euro(_n(p["szb"])))
    if zone.startswith("zone haute"):
        forfaits = [_n(p[c]) for c in ("tzf1", "tzf2", "tzf3")]
        dernier = [t for t in forfaits if t is not None][-1]
        return "%s + (%d − %d) × %s" % (_euro(dernier), journees, fzf,
                                        _euro(_n(p["szh"])))
    return "forfait, bornes %d–%d journées" % (dzf, fzf)


def _euro(v):
    if v is None:
        return "—"
    return ("%.2f" % v).replace(".", ",") + " €"


def _euro_long(v):
    """Montant avec séparateur de milliers, à la française."""
    if v is None:
        return "—"
    return "{:,.2f}".format(v).replace(",", " ").replace(".", ",") + " €"


# ---------------------------------------------------------------------------
# Page « Séjour & valorisation »
# ---------------------------------------------------------------------------

def page(d):
    st.header("💶 Séjour & valorisation")
    st.caption(
        "Valorisation d'un séjour, pour un **établissement public de santé** "
        "(a de l'article L.162-22 du code de la sécurité sociale) situé dans "
        "le Morbihan : grille ex-DAF (annexe I), pas de coefficient "
        "géographique.")

    if d.get("tarifs_gmt") is None or d["tarifs_gmt"].empty:
        st.warning("La grille tarifaire n'est pas chargée : déposez les "
                   "annexes de l'arrêté tarifaire dans `sources/`.")
        return

    morbidite = _section_morbidite(d)
    st.divider()
    contexte = _section_sejour(d)
    st.divider()
    gr = _section_gr(d, morbidite["gn"], contexte)
    st.divider()
    gl = _section_gl(d, gr, contexte)
    st.divider()
    gme = _section_severite(d, gl, contexte, morbidite)
    st.divider()
    _formulaire(d, morbidite["gn"], gr, contexte, gl, gme)


# ---------------------------------------------------------------------------
# Morbidité : catégorie majeure et groupe nosologique
# ---------------------------------------------------------------------------

def _section_morbidite(d):
    """Saisie de la morbidité, groupage en CM puis GN.

    Renvoie un dict : gn, mmp, ae, das, et les codes orientants — ceux qui ont
    fait entrer le séjour dans son groupe nosologique et qui pourront, à ce
    titre, neutraliser une complication au niveau de la sévérité.
    """
    vide = {"gn": "", "mmp": "", "ae": "", "das": [], "orientants": set()}
    st.subheader("🩺 Morbidité du séjour")
    if d.get("cim_diag") is None or d["cim_diag"].empty:
        st.warning("Le référentiel CIM-10 à usage SMR n'est pas chargé.")
        return vide

    st.caption(
        "La catégorie majeure puis le groupe nosologique se déduisent des "
        "seuls diagnostics. Une seule morbidité est saisie pour l'ensemble du "
        "séjour : en hospitalisation complète le groupe nosologique du séjour "
        "est de toute façon celui qui domine, et en temps partiel c'est le "
        "choix retenu pour cet outil.")

    c1, c2 = st.columns(2)
    with c1:
        mmp = etat.texte("sejour.mmp", "Manifestation morbide principale (MMP)",
                         placeholder="Ex. : G811")
        _apercu_code(d, mmp, "mmp")
    with c2:
        ae = etat.texte("sejour.ae", "Affection étiologique (AE)",
                        placeholder="Ex. : I634")
        _apercu_code(d, ae, "ae")

    das_texte = etat.texte(
        "sejour.das", "Diagnostics associés significatifs (DAS)",
        placeholder="Ex. : S5200, E119 — séparés par une virgule",
        help="Un seul nœud de l'arbre de décision teste les DAS, celui des "
             "fractures multiples ; ils servent surtout au niveau de sévérité.")
    das = [x.strip() for x in str(das_texte).replace(";", ",").split(",")
           if x.strip()]

    _recherche_cim(d)

    if not str(mmp).strip():
        st.info("Saisissez au moins la manifestation morbide principale pour "
                "obtenir la catégorie majeure et le groupe nosologique.")
        return vide

    r = groupage.grouper(d, mmp, ae, das)
    for niveau, message in r["alertes"]:
        {"erreur": st.error, "avert": st.warning, "info": st.info}[niveau](
            message)

    c1, c2 = st.columns(2)
    c1.metric("Catégorie majeure",
              r["cm"] if r["cm"] != groupage.CM_NON_CLASSANTE else "—",
              help=r["cm_libelle"])
    c2.metric("Groupe nosologique", r["gn"] or "—", help=r["gn_libelle"])
    if r["cm_libelle"]:
        st.markdown("**CM %s** — %s" % (r["cm"], r["cm_libelle"]))
    if r["gn_libelle"]:
        st.markdown("**GN %s** — %s" % (r["gn"], r["gn_libelle"]))

    with st.expander("Pourquoi ce groupe nosologique ?"):
        for t in r["trace_cm"]:
            st.markdown("- " + t)
        for t in r["trace_gn"]:
            st.markdown("- " + t)
        if r["noeud"] is not None:
            st.caption(
                "Arbre de la CM %s, nœud n° %s sur %d." % (
                    r["cm"], r["noeud"]["ordre"],
                    len(d["gn_tests"][d["gn_tests"]["cm"] == r["cm"]])))
    return {"gn": r["gn"], "mmp": mmp, "ae": ae, "das": das,
            "orientants": groupage.codes_orientants(d, r["noeud"], mmp, ae)}


def _apercu_code(d, code, position):
    """Libellé et orientation du code saisi, ou message d'erreur."""
    if not str(code).strip():
        return
    info = groupage.infos_code(d, code)
    if info is None:
        st.caption("❌ Code inconnu de la CIM-10 à usage SMR.")
        return
    bouts = [info["libelle"].capitalize()]
    if info["cm"] != groupage.CM_NON_CLASSANTE:
        bouts.append("oriente vers la CM %s" % info["cm"])
    else:
        bouts.append("n'oriente vers aucune CM")
    if info["orientant_2e"] == "oui":
        bouts.append("**orientant en deuxième intention**")
    if info[position] != "oui":
        bouts.append("⚠️ non autorisé dans cette position")
    st.caption(" — ".join(bouts))


LIMITE_CIM = 200


def _recherche_cim(d):
    """Moteur de recherche du référentiel CIM, par code ou par libellé."""
    with st.expander("🔎 Chercher un code CIM-10"):
        st.caption(
            "Le référentiel chargé est la **CIM-10 complète de l'ATIH** — "
            "%s codes, et non une sélection. La recherche accepte un code "
            "(`I63`) ou des mots du libellé ; les libellés ATIH étant abrégés "
            "(« ACCID. VASC. CEREB. »), un mot cherché correspond aussi à son "
            "abréviation."
            % "{:,}".format(len(d["cim_diag"])).replace(",", " "))
        requete = etat.texte("sejour.recherche_cim", "Code ou mots du libellé",
                             placeholder="Ex. : I63 · hémiplégie · "
                                         "accident vasculaire cérébral")
        if not str(requete).strip():
            return
        trouves, total = sd.chercher_cim(d, requete, LIMITE_CIM)
        if not total:
            st.caption(
                "Aucun code trouvé. La CIM-10 de l'ATIH n'emploie pas de "
                "synonymes : une escarre s'y lit « ulcère de décubitus », une "
                "dénutrition « malnutrition ».")
            return
        st.caption("%d code(s) trouvé(s)%s." % (
            total, "" if total <= LIMITE_CIM
            else " — les %d premiers sont affichés" % LIMITE_CIM))
        st.dataframe(
            trouves[["code", "libelle", "cm", "profil2", "cma"]].rename(
                columns={
                    "code": "Code", "libelle": "Libellé", "cm": "CM",
                    "profil2": "Positions FPP/MMP/AE/DAS", "cma": "CMA"}),
            width="stretch", hide_index=True, height=260,
            column_config={"Libellé": st.column_config.TextColumn(
                width="large"),
                "CMA": st.column_config.TextColumn(
                    width="small",
                    help="X = ce diagnostic est une complication ou morbidité "
                         "associée : voir Références › CMA.")})


# ---------------------------------------------------------------------------
# Valorisation
# ---------------------------------------------------------------------------

def _section_sejour(d):
    """Entrées communes au groupage et à la valorisation."""
    st.subheader("🏥 Caractéristiques du séjour")

    c1, c2, c3 = st.columns(3)
    with c1:
        partiel = etat.choix(
            "sejour.hospitalisation", "Type d'hospitalisation",
            ["complete", "partielle"], defaut="complete",
            format_func=lambda t: "Hospitalisation complète" if t == "complete"
            else "Hospitalisation à temps partiel",
            help="C'est cette variable qui commande tout l'algorithme : en "
                 "hospitalisation complète le groupage porte sur le séjour "
                 "entier, en temps partiel sur chaque semaine.") == "partielle"
    with c2:
        age = etat.nombre(
            "sejour.age", "Âge du patient", 0, 120, 60,
            help="Âge au premier RHS du séjour. En deçà de 18 ans, "
                 "l'orientation vers le groupe pédiatrique est immédiate "
                 "lorsqu'il existe pour ce groupe nosologique.")
    with c3:
        journees = etat.nombre(
            "sejour.journees", "Journées de présence", 0,
            panier.JOURNEES_MAX_SEMAINE if partiel else 900,
            panier.JOURNEES_DEFAUT,
            help="Présence à minuit. Le jour de sortie n'est pas compté, sauf "
                 "décès. Une permission de moins de 48 h ou un transfert de "
                 "moins de 2 jours ne rompent pas le séjour (article 4). En "
                 "temps partiel, chaque jour de venue de la semaine, 7 au "
                 "plus.")

    c4, c5 = st.columns(2)
    with c4:
        if partiel:
            st.text_input("Mode de sortie",
                          value="sans objet en temps partiel", disabled=True,
                          key="sortie_tp")
            mode = "autre"
        else:
            mode = etat.choix(
                "sejour.sortie", "Mode de sortie", list(MODES_SORTIE),
                defaut="autre", format_func=lambda m: MODES_SORTIE[m],
                help="Un séjour de moins de 8 journées terminé par transfert, "
                     "mutation ou décès bascule sur le GMT « séjour court ».")
    with c5:
        # Dénominateur des scores par jour (manuel des GME 2026, vol. 1,
        # § 3.3.2). En temps partiel, le manuel divise par tous les jours de
        # présence de la semaine, week-end compris : ce sont les journées
        # saisies à côté, et le champ du lundi au vendredi ne sert pas.
        if partiel:
            st.text_input(
                "dont jours de présence du lundi au vendredi",
                value="sans objet en temps partiel", disabled=True,
                key="jours_semaine_tp",
                help="En temps partiel, le score par jour divise la somme de "
                     "la semaine par tous ses jours de présence, week-end "
                     "compris : les journées de présence saisies à côté "
                     "(manuel des GME 2026, vol. 1, § 3.3.2.2).")
            denominateur = max(int(journees), 1)
        else:
            # Borne lue sur les journées, déjà rendues : les réduire ramène
            # aussitôt ce nombre.
            denominateur = etat.nombre(
                "sejour.jours_semaine",
                "dont jours de présence du lundi au vendredi", 1,
                panier.maxi_jours_semaine(), 5,
                help="Dénominateur des scores par jour en hospitalisation "
                     "complète (manuel des GME 2026, vol. 1, § 3.3.2.1) : "
                     "les jours de présence du lundi au vendredi du séjour, "
                     "au plus le nombre de journées de présence. Au-delà de "
                     "90 journées, le GME de financement ne retient que les "
                     "RHS jusqu'à celui de la 90ᵉ journée (notice technique "
                     "ATIH-485-07-2023) : compter actes et jours sur cette "
                     "période. Un séjour sans aucun jour de semaine compte "
                     "ses jours de week-end. Le numérateur couvre toute la "
                     "période, week-end compris : un score par jour peut donc "
                     "dépasser la pondération réellement produite en une "
                     "journée.")

    if partiel:
        st.info(
            "En temps partiel, le groupage porte sur **chaque semaine** : le "
            "groupe nosologique et le niveau de lourdeur ne varient pas, mais "
            "le groupe de réadaptation dépend du score de la semaine "
            "considérée. Saisissez ici une semaine à la fois.")

    return {"temps_partiel": partiel, "age": int(age),
            "journees": int(journees), "mode": mode,
            "denominateur": int(denominateur)}


# ---------------------------------------------------------------------------
# Groupe de réadaptation
# ---------------------------------------------------------------------------

def _section_gr(d, gn, contexte):
    """Groupe de réadaptation, calculé à partir des actes du panier."""
    st.subheader("🎯 Groupe de réadaptation")
    if not gn:
        st.caption("Le groupe nosologique doit être déterminé au préalable.")
        return ""

    scores = panier.scores(d, gn, contexte["denominateur"])
    # Un seul conteneur, panier vide ou non : la saisie CCAM qui suit garde sa
    # place dans la page, et le navigateur ne la referme pas au premier ajout.
    with st.container():
        if not scores["n_actes"]:
            st.warning(
                "Le panier est vide : le score de réadaptation est nul et le "
                "séjour serait classé en réadaptation « autre ». Ajoutez les "
                "actes du séjour depuis les pages de recherche, et les actes "
                "CCAM pondérés ci-dessous.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Spécialisé / séjour", "%g" % scores["spe_sejour"])
            c2.metric("Spécialisé / jour", "%.1f" % scores["spe_jour"])
            c3.metric("Global / séjour", "%g" % scores["glob_sejour"])
            c4.metric("Global / jour", "%.1f" % scores["glob_jour"])
            st.caption(
                "%d acte(s) au panier, dont %d dans la liste d'actes "
                "spécialisés %s du groupe nosologique."
                % (scores["n_actes"], scores["n_spe"],
                   scores["liste"] or "—"))
            _actes_du_panier(d, scores["lignes"])

    _ajout_ccam(d, scores["liste"])

    r = groupage.gr_du_sejour(d, gn, contexte["age"], scores,
                              contexte["temps_partiel"])
    for niveau, message in r["alertes"]:
        {"erreur": st.error, "avert": st.warning, "info": st.info}[niveau](
            message)
    if not r["gr"]:
        return ""

    st.markdown("**GR %s** — %s"
                % (r["gr"], groupage.LETTRES_GR.get(r["lettre"], "")))
    with st.expander("Pourquoi ce groupe de réadaptation ?"):
        for t in r["trace"]:
            st.markdown("- " + t)
        if contexte["temps_partiel"]:
            st.caption(
                "Le manuel de groupage et le lisez-moi de GR_infos.xlsx se "
                "contredisent sur le dénominateur en temps partiel : « jours "
                "de présence dans la semaine » pour l'un, « jours du lundi au "
                "vendredi » pour l'autre. L'outil suit le manuel (vol. 1, "
                "§ 3.3.2.2), qui ne précise « lundi au vendredi » que pour "
                "l'hospitalisation complète : il divise par les journées de "
                "présence de la semaine, saisies plus haut. Les deux lectures "
                "ne diffèrent que pour une venue le samedi ou le dimanche.")
    return r["gr"]


def _actes_du_panier(d, lignes):
    """Actes du panier, corrigeables sans quitter la page.

    Cliquer une ligne rouvre le composeur de sa nomenclature, comme dans
    l'onglet Panier des pages de recherche : intervenant, modulateurs et
    nombre de réalisations se corrigent — un modulateur de temps oublié
    change la pondération —, et un acte ajouté par erreur se retire. Le
    tableau est plus étroit que celui de l'onglet : le composeur montre le
    reste.
    """
    tableau = pd.DataFrame([{
        "État": v["statut"].split()[0],
        "Code": v["code"],
        "Libellé": v["libelle"],
        "Codes suppl.": panier._resume_codes(v),
        "Nb": v.get("nb") or 1,
        "Total": "%g" % panier._total_ligne(v),
    } for v in lignes])
    # Largeurs serrées : sur un petit écran, les six colonnes tiennent sans
    # défilement, le libellé complet se lisant dans le composeur.
    panier.corriger(d, lignes, tableau, hauteur_max=250, column_config={
        "État": st.column_config.TextColumn(
            width=50,
            help="✅ conforme · ⚠️ à vérifier · ❌ erreur. Le détail "
                 "s'affiche en cliquant la ligne."),
        "Code": st.column_config.TextColumn(width=75),
        "Libellé": st.column_config.TextColumn(width="medium"),
        "Codes suppl.": st.column_config.TextColumn(width=90),
        "Nb": st.column_config.NumberColumn(width=50),
        "Total": st.column_config.TextColumn(width=60),
    })


CCAM_GR = "sejour.ccam_gr"


def _ajout_ccam(d, liste):
    """Saisie des actes CCAM pondérés, versés au panier qui fait le score.

    Le groupe de réadaptation n'a pas de saisie propre : il lit le panier.
    Or les pages de recherche ne couvrent que le CSARR et le CSAR, et seuls
    les seize actes CCAM des listes d'actes spécialisés y figurent, dans
    l'onglet « Actes spécialisés par GN » ; les quarante autres ne
    rejoignaient le panier que par collage de leur code. Le champ « Actes
    CCAM du séjour » de la sévérité ne compte pas : il ne cherche que les
    actes CCAM valant complication.
    """
    actes = d.get("ccam_actes")
    if actes is None or actes.empty:
        return
    libelles = dict(zip(actes["code"], actes["libelle"]))
    ponderations = dict(zip(actes["code"], actes["ponderation"]))
    with st.expander("🧺 Ajouter un acte CCAM pondéré au panier"):
        st.caption(
            "Les %d actes CCAM pondérés par l'ATIH comptent dans le score de "
            "réadaptation. Ils se saisissent au code seul : ni modulateur, ni "
            "intervenant, la pondération publiée valant pour l'intervenant 10 "
            "(médecin). On les corrige ou les retire en cliquant leur ligne "
            "dans le tableau des actes du panier." % len(actes))
        # Toute la largeur pour la liste, qui coupe les libellés à la sienne ;
        # celui de l'acte retenu s'affiche en entier dessous.
        code = etat.choix(
            CCAM_GR + ".code", "Acte CCAM", [""] + list(libelles),
            format_func=lambda c: "— choisir un acte —" if not c
            else "%s — %s" % (c, libelles[c]),
            help="Tapez un code ou des mots du libellé pour filtrer.")
        if code:
            st.caption(
                "**%s** — %s · pondération %s · %s"
                % (code, libelles[code], ponderations[code] or "non publiée",
                   "spécialisé pour ce groupe nosologique"
                   if code in sd.codes_specialises(d, liste)
                   else "score global seulement"))
        c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
        with c1:
            etat.nombre(CCAM_GR + ".nb", "Réalisations", 1, 20, 1,
                        help="1 sauf si l'acte est réalisé plusieurs fois le "
                             "même jour.")
        with c2:
            st.button("🧺 Ajouter au panier", key="valo_ajout_ccam",
                      type="primary", disabled=not code,
                      on_click=_ajouter_ccam, args=(libelles,))


def _ajouter_ccam(libelles):
    """Rappel du bouton : la ligne est celle que produit la fiche CCAM.

    Les valeurs sont relues sur les widgets, comme pour le collage du panier :
    un nombre modifié juste avant le clic n'a pas encore rejoint le magasin.
    La saisie est ensuite remise à zéro, comme le composeur d'une fiche, pour
    qu'un second clic n'ajoute pas l'acte une deuxième fois.
    """
    code = st.session_state.get(etat.cle_widget(CCAM_GR + ".code"), "")
    nb = st.session_state.get(etat.cle_widget(CCAM_GR + ".nb"), 1)
    if not code:
        return
    etat.ajouter_acte(panier.ligne_vide(
        code=code, nomenclature="ccam", libelle=libelles.get(code, ""),
        inter="10", nb=int(nb)))
    etat.vider_sous_arbre(CCAM_GR)
    st.session_state["message_panier"] = (
        "Acte %s ajouté au panier (%d au total)." % (code, etat.nb_actes()))


# ---------------------------------------------------------------------------
# Dépendance et niveau de lourdeur
# ---------------------------------------------------------------------------

def _section_gl(d, gr, contexte):
    """Cotation de la dépendance puis niveau de lourdeur."""
    st.subheader("🧭 Dépendance et niveau de lourdeur")
    if not gr:
        st.caption("Le groupe de réadaptation doit être déterminé au "
                   "préalable.")
        return ""

    st.caption(
        "Cotation selon la grille des activités de la vie quotidienne, à "
        "l'issue de la semaine et d'après le dossier de soins. Si une variable "
        "recouvre plusieurs actions, retenir la cotation de l'action la plus "
        "dépendante ; si la dépendance a varié dans la semaine, retenir la "
        "cotation la plus élevée. En hospitalisation complète, on retient le "
        "**maximum** observé sur toutes les semaines du séjour.")

    cotations = {}
    st.markdown("**Dépendance physique** — quatre items, score de 4 à 16")
    colonnes = st.columns(4)
    for (cle, libelle), colonne in zip(groupage.ITEMS_PHYSIQUES, colonnes):
        with colonne:
            cotations[cle] = _item_dependance(cle, libelle)

    st.markdown("**Dépendance cognitive** — deux items, score de 2 à 8")
    colonnes = st.columns([1, 1, 2])
    for (cle, libelle), colonne in zip(groupage.ITEMS_COGNITIFS, colonnes):
        with colonne:
            cotations[cle] = _item_dependance(cle, libelle)
    with colonnes[2]:
        chirurgie = etat.case(
            "sejour.post_chirurgical",
            "Intervention chirurgicale de moins de 90 jours",
            help="Statut post-chirurgical lu sur le premier RHS du séjour. Le "
                 "manuel ne précise pas la date de référence exacte du délai : "
                 "la saisie directe évite d'avoir à la deviner.")

    phy = groupage.score_physique(cotations)
    cog = groupage.score_cognitif(cotations)
    c1, c2 = st.columns(2)
    c1.metric("Dépendance physique", "%d / 16" % phy,
              help="Habillage ou toilette, déplacement et locomotion, "
                   "alimentation, continence.")
    c2.metric("Dépendance cognitive", "%d / 8" % cog,
              help="Comportement et communication.")

    r = groupage.gl_du_sejour(d, gr, contexte["age"], cotations, chirurgie,
                              contexte["temps_partiel"])
    for niveau, message in r["alertes"]:
        {"erreur": st.error, "avert": st.warning, "info": st.info}[niveau](
            message)
    if not r["gl"]:
        return ""

    st.markdown("**GL %s** — niveau de lourdeur **%s**" % (r["gl"],
                                                           r["niveau"]))
    with st.expander("Pourquoi ce niveau de lourdeur ?"):
        for t in r["trace"]:
            st.markdown("- " + t)
        if r["contributions"]:
            st.dataframe(
                pd.DataFrame([
                    {"Variable": n.capitalize(),
                     "Niveau entraîné": v or "sans objet pour ce groupe"}
                    for n, v in r["contributions"].items()]),
                width="stretch", hide_index=True)
            st.caption(
                "Le niveau retenu est le maximum des quatre, A étant le plus "
                "léger et C le plus lourd. Une variable « sans objet » ne "
                "contribue pas : la classe d'âge n'est pas applicable à ce "
                "groupe de réadaptation.")
    return r["gl"]


def _item_dependance(cle, libelle):
    """Un item de la grille, coté de 1 à 4."""
    return etat.choix(
        "dependance.%s" % cle, libelle, [1, 2, 3, 4], defaut=1,
        format_func=lambda v: "%d — %s" % (v, groupage.COTATION[v].split(" —")[0]),
        help=groupage.COTATION.get(1, ""))


# ---------------------------------------------------------------------------
# Niveau de sévérité
# ---------------------------------------------------------------------------

def _section_severite(d, gl, contexte, morbidite):
    """Marqueurs de sévérité et niveau. -> GME complet ou ''."""
    st.subheader("⚕️ Niveau de sévérité")
    if not gl:
        st.caption("Le niveau de lourdeur doit être déterminé au préalable.")
        return ""

    if not contexte["temps_partiel"]:
        st.caption(
            "Un diagnostic ne vaut complication que s'il porte le drapeau CMA "
            "**et** qu'il n'est pas neutralisé par l'un des codes ayant "
            "orienté le séjour vers son groupe nosologique : une comorbidité "
            "déjà impliquée par la pathologie traitée n'ajoute pas de "
            "sévérité. Un seul marqueur suffit à porter le niveau à 2.")

        ccam = _ccam_severite(d)

        inclure_ae = etat.case(
            "sejour.severite_ae",
            "Compter aussi l'affection étiologique comme marqueur",
            help="Le manuel se contredit : son paragraphe 5.2.1 réserve les "
                 "marqueurs à la MMP et aux DAS, tandis que son tableau 2 "
                 "coche aussi l'affection étiologique. L'outil suit le "
                 "paragraphe, plus précis, et vous laisse le choix.")
    else:
        ccam, inclure_ae = [], False

    r = groupage.severite_du_sejour(
        d, gl, morbidite["mmp"], morbidite["ae"], morbidite["das"], ccam,
        morbidite["orientants"], contexte["temps_partiel"], inclure_ae)

    for niveau, message in r["alertes"]:
        {"erreur": st.error, "avert": st.warning, "info": st.info}[niveau](
            message)
    if not r["niveau"]:
        return ""

    st.markdown("**Niveau de sévérité %s** — GME **%s**"
                % (r["niveau"], r["gme"]))
    if r["marqueurs"] or r["exclus"]:
        st.dataframe(
            pd.DataFrame([
                {"Code": m["code"], "Position": m["position"],
                 "Libellé": m["libelle"],
                 "Retenu": "✅ marqueur de sévérité"}
                for m in r["marqueurs"]] + [
                {"Code": e["code"], "Position": e["position"],
                 "Libellé": e["libelle"],
                 "Retenu": "⬜ exclu par " + ", ".join(e["par"])}
                for e in r["exclus"]]),
            width="stretch", hide_index=True,
            column_config={"Libellé": st.column_config.TextColumn(
                width="large")})
    with st.expander("Pourquoi ce niveau de sévérité ?"):
        for t in r["trace"]:
            st.markdown("- " + t)
        if morbidite["orientants"]:
            st.caption(
                "Codes ayant orienté le séjour vers son groupe nosologique, "
                "donc susceptibles de neutraliser une complication : %s."
                % ", ".join(sorted(morbidite["orientants"])))
    return r["gme"]


CCAM_SEV = "sejour.ccam_sev"


def _ccam_severite(d):
    """Actes CCAM valant complication, saisis comme ceux du GR. -> codes.

    Même présentation que les actes CCAM pondérés de la partie groupe de
    réadaptation : la liste des actes, le libellé complet de l'acte choisi,
    un bouton d'ajout. Ils ne vont pas au panier, réservé aux actes pondérés,
    et aucun de ces 21 actes ne l'est : la liste retenue vit dans le magasin
    et ne sert qu'au niveau de sévérité.
    """
    ref = d.get("ref_cma_ccam")
    if ref is None or ref.empty:
        return []
    libelles = dict(zip(ref["code7"], ref["libelle"]))
    retenus = [c for c in etat.lire(CCAM_SEV + ".liste", []) if c in libelles]
    with st.expander("⚕️ Ajouter un acte CCAM valant complication"):
        st.caption(
            "Les %d actes CCAM de la liste de l'ATIH valent complication à eux "
            "seuls : rien ne peut les neutraliser, et un seul porte le niveau "
            "à 2. Aucun n'est pondéré pour le score de réadaptation."
            % len(libelles))
        code = etat.choix(
            CCAM_SEV + ".code", "Acte CCAM",
            [""] + [c for c in libelles if c not in retenus],
            format_func=lambda c: "— choisir un acte —" if not c
            else "%s — %s" % (c, libelles[c]),
            help="Tapez un code ou des mots du libellé pour filtrer.")
        if code:
            st.caption("**%s** — %s" % (code, libelles[code]))
        st.button("⚕️ Ajouter aux actes du séjour", key="valo_ajout_ccam_sev",
                  type="primary", disabled=not code,
                  on_click=_ajouter_ccam_sev)
    # Les actes retenus restent visibles hors du dépliant : un acte ajouté
    # par erreur se retire sans avoir à rouvrir la saisie.
    for c in retenus:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        c1.markdown("`%s` %s" % (c, libelles[c]))
        c2.button("Retirer", key="valo_retirer_ccam_sev_%s" % c,
                  width="stretch", on_click=_retirer_ccam_sev, args=(c,))
    return retenus


def _ajouter_ccam_sev():
    """Rappel du bouton : l'acte choisi rejoint la liste, la saisie s'efface.

    Le code est relu sur le widget, comme pour les actes du GR.
    """
    code = st.session_state.get(etat.cle_widget(CCAM_SEV + ".code"), "")
    if not code:
        return
    retenus = list(etat.lire(CCAM_SEV + ".liste", []))
    if code not in retenus:
        retenus.append(code)
    etat.ecrire(CCAM_SEV + ".liste", retenus)
    etat.vider(CCAM_SEV + ".code")


def _retirer_ccam_sev(code):
    etat.ecrire(CCAM_SEV + ".liste",
                [c for c in etat.lire(CCAM_SEV + ".liste", []) if c != code])


# ---------------------------------------------------------------------------
# Groupe médico-économique et montant
# ---------------------------------------------------------------------------

def _formulaire(d, gn="", gr="", contexte=None, gl="", gme_calcule=""):
    contexte = contexte or {"journees": 25, "mode": "autre"}
    st.subheader("💶 Groupe médico-économique et montant")
    tous = gme_connus(d)
    prefixe = gme_calcule or gl or gr or gn
    if prefixe:
        cibles = [g for g in tous if g.startswith(prefixe)]
        if cibles:
            if gme_calcule:
                message = ("Le GME **%s** est entièrement déterminé : les "
                           "cinq niveaux du groupage ont été calculés (%d "
                           "correspondance).")
            elif gl:
                message = ("Le groupe de lourdeur **%s** étant déterminé, il "
                           "ne reste que %d GME : seule la **sévérité** est "
                           "encore à désigner, dernier maillon que l'outil ne "
                           "calcule pas.")
            elif gr:
                message = ("Le groupe de réadaptation **%s** étant déterminé, "
                           "seuls ses %d GME sont proposés.")
            else:
                message = ("Le groupe nosologique **%s** étant déterminé, "
                           "seuls ses %d GME sont proposés.")
            st.caption(message % (prefixe, len(cibles)))
            tous = cibles
    # Un GME porte plusieurs lignes tarifaires ; c'est le libellé du GMT
    # principal qui décrit le groupe, celui des blocs 7xxx et 8xxx décrivant
    # le régime de facturation.
    principaux = d["tarifs_gmt"][d["tarifs_gmt"]["bloc"] == "principal"]
    libelles = dict(zip(principaux["gme"], principaux["libelle"]))

    c1, c2 = st.columns([3, 1])
    with c1:
        gme = etat.choix(
            "sejour.gme", "GME du séjour", tous,
            defaut=tous[0] if tous else None,
            format_func=lambda g: "%s — %s"
            % (g, _resume_gme(libelles.get(g, ""))))
    with c2:
        etat.case("sejour.coefficients", "Appliquer les coefficients",
                  defaut=True,
                  help="Coefficient géographique et coefficient de "
                       "revalorisation salariale (SEGUR).")
    journees = contexte["journees"]
    mode = contexte["mode"]

    # Soins palliatifs : trois GMT principaux, un seul facturable.
    principaux = gmt_du_gme(d, gme, "principal")
    gmt_choisi = None
    if len(principaux) > 1:
        st.warning(
            "Ce GME dispose de **%d GMT principaux** — soins palliatifs : le "
            "GMT facturable dépend du lieu de prise en charge (article 3). "
            "L'arrêté les publie dans l'ordre croissant de prise en charge : "
            "autre service, puis lit identifié, puis unité de soins "
            "palliatifs. Leurs libellés étant rigoureusement identiques, "
            "c'est le montant qui les distingue." % len(principaux))
        rangs = {g: i for i, g in enumerate(principaux["gmt"].tolist())}
        lieux = ["autre service", "lit identifié", "unité de soins palliatifs"]
        gmt_choisi = etat.choix(
            "sejour.gmt_palliatif", "GMT principal à retenir",
            principaux["gmt"].tolist(),
            format_func=lambda g: "%s — %s — TZF1 %s" % (
                g,
                lieux[rangs[g]] if rangs[g] < len(lieux) else "lieu %d" % (rangs[g] + 1),
                _euro(_n(principaux[principaux["gmt"] == g].iloc[0]["tzf1"]))))

    r = valoriser(d, gme, journees, mode, gmt_choisi,
                  etat.lire("sejour.coefficients", True))

    st.divider()
    _resultat(d, r, gme)


def _resultat(d, r, gme):
    for niveau, message in r["alertes"]:
        {"erreur": st.error, "avert": st.warning, "info": st.info}[niveau](
            message)
    if not r["etapes"]:
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Régime", r["regime"])
    c2.metric("Montant brut", _euro_long(r["brut"]),
              help="Avant application des coefficients.")
    c3.metric("Montant valorisé", _euro_long(r["net"]),
              delta="×%.4f" % r["facteur"], delta_color="off",
              help="Après coefficients géographique et de revalorisation "
                   "salariale.")

    st.markdown("**Détail du calcul**")
    st.dataframe(
        pd.DataFrame([{
            "Composante": e["libelle"], "GMT": e["gmt"], "Zone": e["zone"],
            "Formule": e["detail"], "Montant": _euro_long(e["montant"]),
        } for e in r["etapes"]]),
        width="stretch", hide_index=True,
        column_config={"Formule": st.column_config.TextColumn(width="large")})

    c = r["coefficients"]
    st.caption(
        "Coefficients appliqués — géographique %s · revalorisation salariale "
        "%s · honoraires %s. Ils se multiplient."
        % (_pct(c["geographique"]), _pct(c["segur"]),
           "sans objet" if not c["honoraires"] else _pct(c["honoraires"])))
    st.caption(
        "⚠️ Ce montant est celui du **GMT seul**. Les suppléments facturables "
        "en sus — transport ST4, ST5 et ST6, dialyse péritonéale D15 et D16, "
        "et depuis 2026 le supplément cancérologie ONC de 17 €/jour — ne sont "
        "pas encore calculés par l'outil.")

    with st.expander("Les trois GMT de ce GME"):
        lignes = gmt_du_gme(d, gme)
        st.dataframe(
            lignes[["gmt", "bloc", "libelle", "dzf", "fzf", "tzb", "szb",
                    "tzf1", "tzf2", "tzf3", "szh"]].rename(columns={
                "gmt": "GMT", "bloc": "Bloc", "libelle": "Libellé",
                "dzf": "DZF", "fzf": "FZF", "tzb": "TZB", "szb": "SZB",
                "tzf1": "TZF1", "tzf2": "TZF2", "tzf3": "TZF3", "szh": "SZH"}),
            width="stretch", hide_index=True,
            column_config={"Libellé": st.column_config.TextColumn(
                width="large")})
        st.caption(
            "Bloc **principal** : temps partiel, et hospitalisation complète "
            "jusqu'à 90 journées. Bloc **hebdomadaire** (7xxx) : journées "
            "au-delà de la 90ᵉ. Bloc **court** (8xxx) : séjour de moins de "
            "8 journées terminé par transfert, mutation ou décès.")


def _pct(v):
    return ("%+.2f" % (v * 100)).replace(".", ",") + " %"


def _resume_gme(libelle):
    """Partie utile du libellé d'un GME : ce qui suit le groupe nosologique.

    Le libellé complet répète le GN (« Lésions cérébrales traumatiques / HC
    Réadaptation spécialisée Niveau A-1 : sans sévérité ») ; dans un sélecteur
    déjà filtré sur un GN, seule la seconde moitié apporte de l'information.
    """
    return libelle.split(" / ", 1)[-1].strip() if " / " in libelle         else libelle[:80]
