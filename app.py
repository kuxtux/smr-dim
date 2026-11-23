# -*- coding: utf-8 -*-
"""
PMSI SMR — recherche des actes de réadaptation CSARR et CSAR.

Lancement :  streamlit run app.py
"""

import pandas as pd
import streamlit as st

from smr import chemins, etat, references
from smr.actes import favoris, fiches, panier
from smr.base import construction
from smr.base import donnees as sd
from smr.base.donnees import (CHAPITRES_CSAR, P_CSAR, P_CSARR, P_FAV, P_REF,
                              P_VALO, PAGES, TYPES_CSAR)
from smr.sejour import valorisation
from smr.synonymes import synonymes

st.set_page_config(
    page_title="PMSI SMR",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
.badge {display:inline-block; padding:2px 10px; margin:2px 4px 2px 0;
        border-radius:12px; font-size:0.8rem; font-weight:600;}
.badge-vert   {background:#d4edda; color:#155724;}
.badge-rouge  {background:#f8d7da; color:#721c24;}
.badge-orange {background:#fff3cd; color:#856404;}
.badge-bleu   {background:#cce5ff; color:#004085;}
.badge-gris   {background:#e2e3e5; color:#383d41;}
.fil {color:#6c757d; font-size:0.85rem; margin-bottom:-6px;}
div[data-testid="stMetricValue"] {font-size:1.5rem;}
.arbo-n1 {font-weight:700; margin:12px 0 2px 0;}
.arbo-n2 {font-weight:600; margin:6px 0 2px 20px;}
.arbo-n3 {margin:2px 0 2px 40px; opacity:0.92;}
.arbo-n4 {margin:2px 0 2px 60px; opacity:0.85; font-size:0.92em;}
</style>
"""

MAX_RESULTATS = 300

# Libellés d'onglets : ils identifient l'onglet côté navigateur, donc ils
# doivent rester stables d'un run à l'autre sous peine de réinitialiser la
# sélection. Le compteur du panier est affiché dans la colonne de gauche.
ONGLETS = ["🔎 Recherche d'actes", "🎯 Actes spécialisés par GN", "🧺 Panier"]

CONFIG = {
    "csarr": {
        "titre": "🔎 Recherche d'actes CSARR",
        "sous_titre": "Catalogue spécifique des actes de rééducation et "
                      "réadaptation — %s actes. Remplacé par le CSAR pour le "
                      "codage à partir du 1er janvier 2027.",
        "cle_nb": "nb_actes_csarr",
        "libelle_champ": "Code CSARR (complet ou partiel, avec ou sans le +) "
                         "ou mots du libellé",
        "exemple": "Ex. : GLR+226  ·  glr226  ·  ALQ  ·  réentrainement "
                   "effort  ·  fauteuil roulant électrique",
    },
    "csar": {
        "titre": "🔎 Recherche d'actes CSAR",
        "sous_titre": "Catalogue spécifique des actes de réadaptation — %s "
                      "actes. Codage possible depuis mars 2025, obligatoire à "
                      "partir du 1er janvier 2027.",
        "cle_nb": "nb_actes_csar",
        "libelle_champ": "Code CSAR (complet ou partiel) ou mots du libellé",
        "exemple": "Ex. : 07S06  ·  01E  ·  04  ·  réentrainement effort  ·  "
                   "rééduc membre sup  ·  bilan équilibre  ·  ETP",
    },
}


# ---------------------------------------------------------------------------
# Onglet « Recherche »
# ---------------------------------------------------------------------------

def _selection_tableau(tableau, resultats, cle, actif):
    """Tableau cliquable ; renvoie la ligne sélectionnée ou None."""
    evenement = st.dataframe(
        tableau, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-cell",
        height=min(38 + 35 * len(tableau), 430), key=cle,
        column_config={
            "Code": st.column_config.TextColumn(width="small",
                                                help=sd.AIDE["Code"]),
            "Libellé": st.column_config.TextColumn(width="large"),
        })
    cellules = evenement.selection.get("cells") if evenement else None
    if cellules:
        return resultats.iloc[cellules[0][0]]
    if actif and (resultats["code"] == actif).any():
        return resultats[resultats["code"] == actif].iloc[0]
    return None


def _onglet_recherche(d, nomen, filtres):
    conf = CONFIG[nomen]
    # La requête vit dans le magasin : elle survit à un passage par les
    # Références ou par un autre onglet.
    requete = etat.texte("recherche.%s" % nomen, conf["libelle_champ"],
                         placeholder=conf["exemple"])

    if nomen == "csar":
        _anomalies_synonymes()

    if not str(requete).strip():
        _accueil(d, nomen)
        return

    if nomen == "csarr":
        resultats = sd.rechercher_csarr(
            d["csarr_actes"], requete, chapitre=filtres["chapitre"] or None,
            dans_notes=filtres["notes"],
            masquer_gestes=filtres["masquer_gestes"])
        # Pas de colonne des modalités : le libellé dit déjà « collectif »,
        # et la fiche comme le composeur portent le reste (dédié, non dédié,
        # pluriprofessionnel, étapes d'appareillage). La place va au libellé.
        colonnes = {"code": "Code", "libelle": "Libellé",
                    "mods_txt": "Modulateurs", "pond_max": "Pond. max",
                    "csar_cible": "→ CSAR"}
    else:
        resultats = sd.rechercher_csar(
            d["csar_actes"], requete, chapitre=filtres["chapitre"] or None,
            type_acte=filtres["type_acte"] or None, dans_notes=filtres["notes"])
        colonnes = {"code": "Code", "libelle": "Libellé",
                    "mods_txt": "Modulateurs", "collectif_txt": "Collectif",
                    "pond_max": "Pond. max", "spe_txt": "Spécialisé"}
        synonymes_appliques = _synonymes_appliques(resultats)
        if synonymes_appliques:
            colonnes["synonymes"] = "Trouvé par"

    if resultats.empty:
        st.warning("Aucun résultat. Essayez avec moins de mots, une autre "
                   "orthographe, ou cochez la case d'extension de la recherche "
                   "dans la colonne de gauche.")
        if nomen == "csarr":
            _bloc_supprimes(d, requete)
        else:
            st.caption(
                "Le terme cherché relève peut-être d'un autre vocabulaire que "
                "celui du catalogue : vous pouvez l'ajouter au dictionnaire "
                "des synonymes, le fichier `%s` (ou votre fichier personnel "
                "`%s`). L'ajout est pris en compte dès la recherche suivante."
                % (chemins.relatif(synonymes.FICHIER),
                   synonymes.FICHIER_PERSO))
        return

    n = len(resultats)
    st.caption("**%d** résultat(s)%s"
               % (n, " — %d premiers affichés" % MAX_RESULTATS
                  if n > MAX_RESULTATS else ""))
    resultats = resultats.head(MAX_RESULTATS)
    if nomen == "csar" and synonymes_appliques:
        # Toujours dire ce que le dictionnaire a fait de la saisie : un acte
        # qui ressort sans contenir le mot cherché doit pouvoir s'expliquer.
        st.caption("🔤 Synonymes appliqués : %s"
                   % " · ".join("**%s**" % s for s in synonymes_appliques))

    if n == 1:
        selection = resultats.iloc[0]
    else:
        tableau = resultats[list(colonnes)].rename(columns=colonnes)
        selection = _selection_tableau(
            tableau, resultats, "res_%s_%s" % (nomen, sd.normaliser(requete)),
            etat.lire("actif.%s" % nomen))
        if selection is None:
            st.info("👆 Cliquez sur une ligne pour afficher la fiche détaillée "
                    "de l'acte.")

    if selection is not None:
        etat.ecrire("actif.%s" % nomen, selection["code"])
        sd.historiser(selection["code"], nomen)
        st.divider()
        if nomen == "csarr":
            fiches.fiche_csarr(d, selection)
        else:
            fiches.fiche_csar(d, selection)


def _anomalies_synonymes():
    """Signale les lignes du dictionnaire que l'on n'a pas su lire.

    Une ligne mal formée est ignorée sans arrêter la recherche ; encore
    faut-il le dire, faute de quoi le synonyme ajouté semble sans effet.
    """
    anomalies = synonymes.charger().anomalies
    if not anomalies:
        return
    st.warning(
        "Dictionnaire des synonymes — %d ligne(s) ignorée(s) :\n%s"
        % (len(anomalies), "\n".join(
            "- fichier %s, ligne %d, `%s` : %s" % a for a in anomalies)))


def _synonymes_appliques(resultats):
    """Correspondances du dictionnaire ayant fait ressortir des résultats."""
    if "synonymes" not in resultats.columns:
        return []
    vus = []
    for texte in resultats["synonymes"]:
        for morceau in str(texte).split(" ; "):
            if morceau and morceau not in vus:
                vus.append(morceau)
    return vus


def _accueil(d, nomen):
    meta = d["meta"]
    if nomen == "csarr":
        c1, c2, c3 = st.columns(3)
        c1.metric("Actes CSARR", meta.get("nb_actes_csarr", ""))
        c2.metric("Transcodages vers le CSAR", meta.get("nb_transcodages", ""))
        c3.metric("Codes supprimés référencés", len(d["csarr_supprimes"]))
        st.info(
            "Saisissez un **code CSARR** (ex. `GLR+226`, `ALQ+001`) ou des "
            "**mots du libellé** (ex. `drainage lymphatique`). La recherche "
            "ignore accents et majuscules ; tous les mots saisis doivent être "
            "présents.")
        _bloc_supprimes(d)
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Actes CSAR", meta.get("nb_actes_csar", ""))
        c2.metric("Modulateurs, modalités et extensions",
                  len(d["ref_modulateurs_csar"]))
        c3.metric("Catégories d'intervenant", len(d["ref_intervenants"]))
        st.info(
            "Saisissez un **code CSAR** (ex. `07S06`), un **début de code** "
            "(`01E` pour les évaluations des fonctions cérébrales, `04` pour "
            "tout le chapitre) ou des **mots du libellé** "
            "(ex. `drainage lymphatique`). Les mots d'usage courant sont "
            "traduits dans le vocabulaire du catalogue par un **dictionnaire "
            "de synonymes** : `rééduc membre sup`, `bilan équilibre`, "
            "`kiné respi`, `ETP`… Il se consulte et se complète dans le "
            "fichier `%s` du dossier de l'outil."
            % chemins.relatif(synonymes.FICHIER))
        st.markdown("**Structure d'un code CSAR à 5 caractères**")
        st.markdown(
            "- `01` à `11` : chapitre — la fonction concernée\n"
            "- `E` évaluation · `S` séance · `M` mise à disposition "
            "d'appareillage · `P` préparation/suivi de dossier\n"
            "- `01` à `nn` : compteur, réinitialisé à chaque chapitre et "
            "chaque objectif")


def _bloc_supprimes(d, requete=""):
    supp = d["csarr_supprimes"]
    if requete:
        code = str(requete).upper().replace(" ", "")
        if "+" not in code and len(code) == 6:
            code = code[:3] + "+" + code[3:]
        trouve = supp[supp["code"] == code]
        if not trouve.empty:
            r = trouve.iloc[0]
            st.error("**%s** est un code CSARR **supprimé** le %s. "
                     "Remplacement : %s"
                     % (r["code"], r["date_suppression"],
                        r["remplacement"] or "non remplacé"))
            return
    with st.expander("🗑️ Codes CSARR supprimés (%d)" % len(supp)):
        st.dataframe(
            supp.rename(columns={
                "code": "Code supprimé", "remplacement": "Remplacé par",
                "date_suppression": "Supprimé le",
                "date_remplacement": "Remplacement au"}),
            width="stretch", hide_index=True, height=300)


# ---------------------------------------------------------------------------
# Onglet « Actes spécialisés par groupe nosologique »
# ---------------------------------------------------------------------------

def _onglet_specialises(d, nomen):
    ref_gn = d.get("ref_gn")
    if ref_gn is None or ref_gn.empty:
        st.warning("Les listes d'actes spécialisés ne sont pas chargées : "
                   "vérifiez la présence de `ACTES_listes_SPE.xlsx` dans "
                   "`sources/`.")
        return

    st.markdown(
        "Un acte est dit **spécialisé** pour un groupe nosologique lorsqu'il "
        "figure dans la liste d'actes attribuée à ce GN. Seuls ces actes "
        "alimentent le **score de réadaptation spécialisée**, qui oriente le "
        "séjour vers un groupe de réadaptation.")

    cms = sorted(set(ref_gn["cm"]))
    c1, c2 = st.columns([1, 2])
    with c1:
        cm = etat.choix(
            "spe.cm", "Catégorie majeure", [""] + cms,
            format_func=lambda c: "Toutes les CM" if not c else
            "%s — %s" % (c, _libelle_cm(d, c)))
    dispo = ref_gn if not cm else ref_gn[ref_gn["cm"] == cm]
    with c2:
        gn = etat.choix(
            "spe.gn", "Groupe nosologique", dispo["gn"].tolist(),
            format_func=lambda g: "%s — %s" % (g, sd.libelle_gn(d, g)))

    if not gn:
        return

    libelle_liste, ligne = sd.liste_du_gn(d, gn)
    st.subheader("%s — %s" % (gn, sd.libelle_gn(d, gn)))

    if not libelle_liste:
        if ligne is not None and ligne["gr_spe_unique"] == "oui":
            st.info(
                "Ce groupe nosologique n'a **pas de liste d'actes "
                "spécialisés**, mais il dispose d'un groupe de réadaptation "
                "spécialisée importante **unique** : l'orientation ne dépend "
                "pas d'un score spécialisé.")
        else:
            st.info("Aucune liste d'actes spécialisés n'est attribuée à ce "
                    "groupe nosologique.")
        return

    partage = ref_gn[ref_gn["libelle_gn_liste"] == libelle_liste]
    st.caption(
        "Liste **%s**, partagée par %d groupe(s) nosologique(s) : %s"
        % (libelle_liste, len(partage),
           ", ".join("%s %s" % (r["gn"], r["libelle"])
                     for _, r in partage.iterrows())))

    actes = sd.actes_specialises(d, libelle_liste, nomen)
    if actes.empty:
        st.warning("Aucun acte %s dans cette liste." % nomen.upper())
        return

    st.markdown("**%d acte(s) %s spécialisé(s)**" % (len(actes), nomen.upper()))
    if nomen == "csar":
        colonnes = {"code": "Code", "libelle": "Libellé",
                    "intervenants": "Intervenants concernés"}
    else:
        colonnes = {"code": "Code", "nomenclature": "Nomenclature",
                    "libelle": "Libellé", "hiera": "Hiérarchie"}

    # L'acte retenu est mémorisé PAR LISTE. Une clé unique pour toute la
    # nomenclature ramenait l'acte choisi dans le groupe nosologique précédent
    # dès qu'il appartenait aussi à la nouvelle liste — ce qui est presque
    # toujours le cas : 77 % des actes figurent dans plusieurs listes.
    chemin_actif = "actif_spe.%s.%s" % (nomen, libelle_liste)
    selection = _selection_tableau(
        actes[list(colonnes)].rename(columns=colonnes), actes,
        "spe_%s_%s" % (nomen, libelle_liste),
        etat.lire(chemin_actif))

    if nomen == "csarr":
        n_ccam = (actes["nomenclature"] == "CCAM").sum()
        if n_ccam:
            st.caption("Dont %d acte(s) CCAM, qui comptent également dans le "
                       "score de réadaptation." % n_ccam)

    with st.expander("🧺 Ajout groupé au panier"):
        codes = st.multiselect(
            "Actes à ajouter", actes["code"].tolist(),
            key="spe_ajout_%s" % nomen,
            format_func=lambda c: "%s — %s" % (
                c, dict(zip(actes["code"], actes["libelle"])).get(c, "")[:60]))
        if codes and st.button("Ajouter la sélection au panier",
                               key="spe_btn_%s" % nomen, type="primary"):
            for code in codes:
                etat.ajouter_acte(panier.ligne_vide(code=code,
                                                    origine="spécialisés"))
            st.session_state["message_panier"] = (
                "%d acte(s) ajouté(s) au panier." % len(codes))
            st.session_state.pop("spe_ajout_%s" % nomen, None)
            st.rerun()

    if selection is None:
        st.info("👆 Cliquez sur une ligne pour afficher la fiche de l'acte et "
                "composer sa zone d'acte.")
        return

    code = selection["code"]
    etat.ecrire(chemin_actif, code)
    st.divider()

    if nomen == "csarr" and selection.get("nomenclature") == "CCAM":
        fiches.fiche_ccam(d, code, espace="spe")
        return

    table = d["csarr_actes"] if nomen == "csarr" else d["csar_actes"]
    ligne = table[table["code"] == code]
    if ligne.empty:
        st.warning("L'acte %s ne figure pas dans la version %s chargée : il a "
                   "probablement été supprimé depuis la publication de la "
                   "liste d'actes spécialisés." % (code, nomen.upper()))
        return

    sd.historiser(code, nomen)
    if nomen == "csarr":
        # Espace de clés distinct : la fiche du même acte peut être
        # ouverte simultanément dans l'onglet de recherche.
        fiches.fiche_csarr(d, ligne.iloc[0], espace="spe")
    else:
        fiches.fiche_csar(d, ligne.iloc[0], espace="spe")


def _libelle_cm(d, cm):
    groupes = d.get("ref_groupes")
    if groupes is None or groupes.empty:
        return ""
    ligne = groupes[(groupes["quoi"] == "CM") & (groupes["code"] == cm)]
    return "" if ligne.empty else ligne.iloc[0]["lib_long"]


# ---------------------------------------------------------------------------
# Page de recherche (commune aux deux nomenclatures)
# ---------------------------------------------------------------------------

def page_recherche(d, nomen, filtres):
    conf = CONFIG[nomen]
    st.header(conf["titre"])
    st.caption(conf["sous_titre"] % d["meta"].get(conf["cle_nb"], ""))

    onglets = st.tabs(ONGLETS)
    with onglets[0]:
        _onglet_recherche(d, nomen, filtres)
    with onglets[1]:
        _onglet_specialises(d, nomen)
    with onglets[2]:
        panier.onglet_panier(d, nomen)


# ---------------------------------------------------------------------------
# Colonne de gauche
# ---------------------------------------------------------------------------

def _barre_laterale(d):
    st.title("🩺 PMSI SMR")
    page = st.radio("Navigation", PAGES, label_visibility="collapsed",
                    key="page_nav")
    st.divider()

    filtres = {"chapitre": "", "type_acte": "", "notes": False,
               "masquer_gestes": False}

    if page == P_CSARR:
        st.markdown("**Filtres CSARR**")
        chapitres = (d["csarr_structure"][d["csarr_structure"]["niveau"] == 1]
                     .sort_values("hiera"))
        # Le catalogue écrit ses chapitres en capitales : en minuscules, comme
        # ceux du CSAR, ils se lisent mieux et prennent moins de place.
        titres = dict(zip(chapitres["hiera"],
                          chapitres["titre"].str.capitalize()))
        filtres["chapitre"] = _filtre_chapitre(
            "filtres.chap_csarr", [""] + chapitres["hiera"].tolist(),
            lambda h: "Tous les chapitres" if not h else
            "%s — %s" % (h, titres.get(h, "")))
        filtres["notes"] = etat.case(
            "filtres.notes_csarr", "Chercher aussi dans les notes",
            help="Inclut les notes d'exclusion, le contenu de l'acte et les "
                 "consignes PMSI dans la recherche par mots.")
        filtres["masquer_gestes"] = etat.case(
            "filtres.masquer_gestes", "Masquer les gestes complémentaires",
            help="Les gestes complémentaires (sous-chapitre 12.01) ne se "
                 "codent qu'en complément d'un acte principal.")
    elif page == P_CSAR:
        st.markdown("**Filtres CSAR**")
        filtres["chapitre"] = _filtre_chapitre(
            "filtres.chap_csar", [""] + list(CHAPITRES_CSAR),
            lambda c: "Tous les chapitres" if not c else
            "%s — %s" % (c, CHAPITRES_CSAR.get(c, "")))
        filtres["type_acte"] = etat.choix(
            "filtres.type_csar", "Objectif de l'acte", [""] + list(TYPES_CSAR),
            format_func=lambda t: "Tous les objectifs" if not t else
            "%s — %s" % (t, TYPES_CSAR[t].split("—")[0].strip()))
        filtres["notes"] = etat.case(
            "filtres.notes_csar",
            "Chercher aussi dans les définitions et descriptions",
            help="Inclut la définition, la fonction CIF et la description du "
                 "contenu de l'acte dans la recherche par mots.")

    # Le panier est visible depuis toutes les pages : c'est le fil conducteur
    # du dossier en cours.
    st.divider()
    n = etat.nb_actes()
    if n:
        st.markdown("**🧺 Panier : %d acte(s)**" % n)
        st.caption("Score de réadaptation : %g"
                   % panier_total(d))
    else:
        st.caption("🧺 Panier vide")

    # Emplacement réservé pour l'historique : il est rempli APRÈS le corps de
    # la page, seul endroit où l'on sait quel acte est réellement affiché.
    # Rendu ici, il aurait toujours un run de retard et l'acte que l'on vient
    # d'ouvrir manquerait à la liste.
    emplacement_historique = st.container()

    st.divider()
    st.caption("CSAR version n°1 2026 · %s actes"
               % d["meta"].get("nb_actes_csar", ""))
    st.caption("CSARR 2026 · %s actes" % d["meta"].get("nb_actes_csarr", ""))
    st.caption("Sources ATIH — voir Références › Sources")
    return page, filtres, emplacement_historique


def _filtre_chapitre(chemin, options, format_func):
    """Filtre par chapitre : un bouton qui déplie les intitulés complets.

    Une liste déroulante coupe ses options à sa propre largeur, celle de la
    colonne, et les intitulés dépassent souvent cinquante caractères. Le
    panneau d'un popover s'élargit au-delà de la colonne : chaque intitulé y
    tient sur sa ligne, sans élargir la colonne de gauche, précieuse sur un
    petit écran. Le bouton affiche en entier le chapitre retenu.

    La clé du panneau dépend du chapitre retenu : choisir un chapitre crée un
    panneau neuf, donc fermé, qui cesse de masquer les résultats.
    """
    courant = etat.lire(chemin, "")
    if courant not in options:
        courant = options[0]
    with st.popover("Chapitre : %s" % format_func(courant), width="stretch",
                    key="panneau_%s_%s" % (chemin.replace(".", "_"),
                                           courant or "tous"),
                    on_change="rerun"):
        return etat.choix(chemin, "Chapitre", options, widget=st.radio,
                          format_func=format_func,
                          label_visibility="collapsed")


def _bloc_historique(emplacement):
    """Derniers actes consultés, dans l'emplacement réservé de la colonne."""
    hist = st.session_state.get("historique")
    if not hist:
        return
    with emplacement:
        st.divider()
        st.markdown("**Derniers actes consultés**")
        for nomenclature, code in hist:
            if st.button("%s · %s" % (code, nomenclature.upper()),
                         key="hist_%s_%s" % (nomenclature, code),
                         width="stretch"):
                sd.aller_a(code, nomenclature)


def panier_total(d):
    return sum(panier._total_ligne(panier.enrichir(d, v))
               for v in etat.panier())


# ---------------------------------------------------------------------------
# Premier lancement : fichiers sources de l'ATIH à déposer
# ---------------------------------------------------------------------------

def _sources_manquantes(cles):
    """Nomme les fichiers de l'ATIH à déposer, au lieu d'échouer.

    Les fichiers sources ne sont pas distribués avec le code : au premier
    lancement, chacun dépose les siens dans sources/. Tant qu'il en manque,
    la base ne peut pas être construite ; on les nomme tous d'un coup.
    """
    st.title("🩺 PMSI SMR — fichiers sources à déposer")
    n = len(cles)
    st.error(
        "La base de l'outil se construit à partir de fichiers publiés par "
        "l'ATIH, qui ne sont pas distribués avec le code. **%s** pour la "
        "construire." % ("1 fichier manque" if n == 1
                         else "%d fichiers manquent" % n))
    st.markdown(
        "Déposez-les dans le dossier `%s`, où vous voulez — sous-dossiers "
        "compris — en gardant leur nom d'origine : une archive téléchargée "
        "sur le site de l'ATIH se dézippe telle quelle. Cliquez ensuite sur "
        "**Vérifier à nouveau** : la base se construit en quelques secondes. "
        "La liste complète des fichiers attendus figure dans "
        "`sources/LISEZMOI.md`." % chemins.DOSSIER_SOURCES)
    st.dataframe(
        pd.DataFrame([{
            "Publication ATIH": construction.DESCRIPTIONS[c][0],
            "Fichier attendu": construction.MOTIFS[c],
            "Nom en 2026": construction.DESCRIPTIONS[c][1],
            "Contenu": construction.DESCRIPTIONS[c][2],
        } for c in cles]),
        width="stretch", hide_index=True)
    # Le clic relance la page, qui retente la construction.
    st.button("🔄 Vérifier à nouveau", type="primary")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def main():
    st.markdown(CSS, unsafe_allow_html=True)

    # Navigation interne demandée au run précédent (clic sur un code).
    if "nav_cible" in st.session_state:
        nomen, code = st.session_state.pop("nav_cible")
        etat.ecrire("recherche.%s" % nomen, code)
        etat.resynchroniser("recherche.%s" % nomen)
        etat.ecrire("actif.%s" % nomen, code)
        st.session_state["page_nav"] = P_CSAR if nomen == "csar" else P_CSARR

    try:
        d = sd.charger()
    except construction.SourcesManquantes as manque:
        # Une exception n'est pas mise en cache : dès que les fichiers sont
        # déposés, le run suivant construit la base.
        _sources_manquantes(manque.cles)
        st.stop()

    # Confirmation d'ajout au panier : en toast, donc visible quel que soit
    # l'onglet affiché.
    message = st.session_state.pop("message_panier", None)
    if message:
        st.toast(message, icon="🧺")
    message = st.session_state.pop("message_favoris", None)
    if message:
        st.toast(message, icon="⭐")

    with st.sidebar:
        page, filtres, emplacement_historique = _barre_laterale(d)

    if page == P_CSARR:
        page_recherche(d, "csarr", filtres)
    elif page == P_CSAR:
        page_recherche(d, "csar", filtres)
    elif page == P_FAV:
        favoris.page(d)
    elif page == P_VALO:
        valorisation.page(d)
    else:
        references.page(d)

    # Le corps de la page a renseigné l'historique : on peut enfin le rendre.
    _bloc_historique(emplacement_historique)


main()
