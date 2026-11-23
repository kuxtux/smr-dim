# -*- coding: utf-8 -*-
"""
PMSI SMR — fiches détaillées des actes et composeurs de zone d'acte.

Une fiche présente l'acte (libellé, définition, notes, exclusions) puis
l'ensemble des codes supplémentaires que le codage autorise. Le composeur
assemble une zone d'acte complète en contrôlant les associations permises.
"""

import pandas as pd
import streamlit as st

from smr import etat
from smr.actes import favoris, panier
from smr.base import donnees as sd
from smr.base.donnees import (ETAPES_APPAREILLAGE, MOD_AVEC_NIVEAU,
                              MOD_LIEU_CSAR, MOD_LIEU_CSARR, MOD_PATIENT_CSARR,
                              MOD_TECHNICITE, MOD_TEMPS, STATUTS_POND,
                              TYPES_CSARR_POND, badge, lien_acte, puces)

VIDE = "— aucun —"

# Espace de clés d'une fiche. Streamlit rend le corps de TOUS les onglets d'un
# même run : si le même acte est retenu dans « Recherche d'actes » et dans
# « Actes spécialisés par GN », sa fiche est construite deux fois. Sans espace
# distinct, les deux jeux de boutons et de champs porteraient les mêmes clés et
# Streamlit interrompait la page (StreamlitDuplicateElementKey).
ESPACE_DEFAUT = "comp"

# Modalités de réalisation d'un acte CSARR : libellé, puis bornes du nombre de
# patients — minimum, maximum, valeur par défaut (guide CSARR § 3.3.3). Les
# clés sont des codes et non les libellés : elles servent de chemin dans le
# magasin de session, et « Individuel dédié » et « Individuel non dédié » se
# termineraient sur le même mot.
MODALITES_CSARR = {
    "dedie": ("Individuel dédié", 1, 1, 1),
    "non_dedie": ("Individuel non dédié", 2, 8, 2),
    "collectif": ("Collectif", 2, 99, 2),
}


# ---------------------------------------------------------------------------
# Outils communs
# ---------------------------------------------------------------------------
# Tous les widgets des composeurs sont liés au magasin de session : la
# composition d'une zone d'acte survit à un passage par un autre onglet ou par
# les Références.

def _selection(chemin, libelle, options, libelles, aide=""):
    """Selectbox « aucun » + codes, affichant « code — libellé »."""
    return etat.choix(
        chemin, libelle, [""] + list(options), defaut="", help=aide or None,
        format_func=lambda c: VIDE if not c else "%s — %s" % (
            c, libelles.get(c, "")))


def _intervenants(d, chemin, code=None, aide="", csarr=False):
    """Choix de l'intervenant, ceux attendus pour l'acte étant listés en tête.

    Les catégories 80 et 81 n'existent que dans le CSAR : elles sont écartées
    lorsque l'on code en CSARR.
    """
    ref = d["ref_intervenants"]
    if csarr:
        ref = ref[ref["csarr"] == "oui"]
    attendus = []
    if code:
        ia = d["csar_intervenants"]
        ia = ia[(ia["code"] == code) & (ia["attendu"] == "1")]
        attendus = sorted(ia["code_inter"].tolist())
    autres = [c for c in ref["code"].tolist() if c not in attendus]
    options = attendus + autres
    libs = d["lib_intervenant"]

    def fmt(c):
        marque = " ⭐" if c in attendus else ""
        return "%s — %s%s" % (c, libs.get(c, ""), marque)

    valeur = etat.choix(chemin, "Intervenant", options,
                        defaut=options[0] if options else None,
                        format_func=fmt,
                        help=aide or sd.AIDE["Intervenant"])
    return valeur, attendus


def _ajouter_au_panier(ligne, cle, prefixe=None):
    """Bouton d'ajout de la zone d'acte composée au panier du dossier.

    On relance le run après l'ajout pour que le compteur de la colonne de
    gauche, rendue avant le corps de la page, soit à jour immédiatement.

    Le composeur est ensuite remis à zéro. Un même acte revient souvent
    plusieurs jours de suite avec des modulateurs différents : sans remise à
    zéro, la composition précédente reste affichée et le codeur ajoute sans
    s'en apercevoir un modulateur de la veille. La remise à zéro est différée
    au run suivant, Streamlit refusant qu'on touche aux clés de widgets déjà
    rendus.
    """
    if st.button("🧺 Ajouter au panier", key=cle, type="primary",
                 help="L'acte rejoint le panier, commun aux deux "
                      "nomenclatures et conservé quand vous naviguez. Le "
                      "composeur repart ensuite d'une zone d'acte vierge."):
        etat.ajouter_acte(ligne)
        if prefixe:
            st.session_state["reinit_composeur"] = prefixe
        st.session_state["message_panier"] = (
            "Acte %s ajouté au panier (%d au total)."
            % (ligne["code"], etat.nb_actes()))
        st.rerun()


def _reinitialiser(prefixe):
    """Consomme une remise à zéro demandée au run précédent.

    L'intervenant y échappe : il décrit **qui code**, non ce qui a été fait.
    Le ramener à la première catégorie de la liste après chaque ajout
    obligerait un kinésithérapeute enchaînant ses actes à resaisir la sienne à
    chaque fois — et à coder « médecin » le jour où il ne le remarque pas.
    """
    if st.session_state.get("reinit_composeur") != prefixe:
        return
    st.session_state.pop("reinit_composeur", None)
    intervenant = etat.lire(prefixe + "int")
    etat.vider_sous_arbre(prefixe.rstrip("."))
    if intervenant:
        etat.ecrire(prefixe + "int", intervenant)


def _amorcer(prefixe, valeurs):
    """Amorce les champs d'un composeur depuis une ligne de panier, une fois.

    L'amorçage n'a lieu qu'à l'ouverture : ensuite les widgets sont maîtres.
    Sans ce garde-fou, chaque run réécrirait les valeurs d'origine et la
    correction en cours serait effacée à la première modification.
    """
    if etat.lire(prefixe + "_amorce"):
        return
    for suffixe, valeur in valeurs.items():
        etat.ecrire(prefixe + suffixe, valeur)
        etat.resynchroniser(prefixe + suffixe)
    etat.ecrire(prefixe + "_amorce", True)


def _modalite_de(pat, mods):
    """Modalité de réalisation CSARR correspondant à un nombre de patients.

    Le panier ne mémorise que le nombre de patients : la modalité s'en déduit,
    puis se rabat sur celles que le libellé autorise réellement.
    """
    permises = [m for m, ok in (("dedie", mods["dedie"]),
                                ("non_dedie", mods["non_dedie"]),
                                ("collectif", mods["collectif"])) if ok]
    if not permises:
        return "dedie"
    try:
        n = int(pat)
    except (TypeError, ValueError):
        return permises[0]
    voulue = "dedie" if n <= 1 else ("non_dedie" if n <= 8 else "collectif")
    if voulue in permises:
        return voulue
    # À défaut, la modalité permise la plus proche dans l'ordre dédié → non
    # dédié → collectif : un nombre de patients hors bornes doit retomber sur
    # la valeur légale la plus voisine, non sur la première de la liste.
    # À distance égale on retient la modalité la plus haute : elle conserve le
    # nombre de patients mémorisé, là où l'individuel dédié le ramènerait à 1.
    ordre = ("dedie", "non_dedie", "collectif")
    rang = ordre.index(voulue)
    return min(permises,
               key=lambda m: (abs(ordre.index(m) - rang), -ordre.index(m)))


def _action_finale(ligne, cle, edition, prefixe=None):
    """Bouton de fin de composition : ajout au panier, ou mise à jour.

    En modification, les boutons sont rendus par le panier : c'est lui qui
    connaît la sélection du tableau à libérer une fois la correction close.
    """
    if edition is None:
        _ajouter_au_panier(ligne, cle, prefixe)
    else:
        panier.actions_edition(ligne, edition)


def _tableau_ponderations(d, lignes, colonnes):
    st.dataframe(
        lignes[list(colonnes)].rename(columns=colonnes),
        width="stretch", hide_index=True,
        column_config={
            "Pondération": st.column_config.TextColumn(
                width="small", help=sd.AIDE["Pondération"]),
        },
    )


def _zone_acte(variables, alertes):
    """Affiche la zone d'acte composée puis les contrôles."""
    # Toutes les valeurs sont converties en texte : la colonne mélange
    # codes et nombres, et Arrow refuse les types hétérogènes.
    remplies = [(k, str(v)) for k, v in variables if str(v) not in ("", "—")]
    st.markdown("**Zone d'acte à saisir**")
    st.dataframe(
        pd.DataFrame(remplies, columns=["Variable", "Valeur"]),
        width="stretch", hide_index=True,
    )
    resume = " · ".join("%s=%s" % (k, v) for k, v in remplies)
    st.code(resume, language=None)

    for niveau, message in alertes:
        {"erreur": st.error, "avert": st.warning, "info": st.info}[niveau](
            message)
    if not any(n == "erreur" for n, _ in alertes):
        st.success("Association conforme aux tables ATIH.")


# ---------------------------------------------------------------------------
# Fiche CCAM
# ---------------------------------------------------------------------------

def fiche_ccam(d, code, edition=None, espace=ESPACE_DEFAUT):
    """Acte CCAM comptant dans le score de réadaptation.

    Ces actes n'appartiennent ni au CSARR ni au CSAR, mais l'ATIH les pondère
    dans le fichier de pondérations du CSARR. Il n'y a donc ni modulateur, ni
    catégorie d'intervenant à choisir, ni zone d'acte à composer : la fiche se
    limite au nombre de réalisations. Ils se recueillent dans la zone d'actes
    CCAM du RHS, non dans une zone d'acte de réadaptation.
    """
    actes = d.get("ccam_actes")
    trouve = (actes[actes["code"] == code]
              if actes is not None and not actes.empty else None)
    if trouve is None or trouve.empty:
        st.error(
            "L'acte **%s** ne figure pas dans la table de pondérations du "
            "SMR : il ne compte dans aucun score de réadaptation." % code)
        return
    acte = trouve.iloc[0]
    ponderation = sd.ponderation_ccam(d, code)

    p = ("edit.%s." % edition["id"] if edition is not None
         else "%s.ccam.%s." % (espace, code))
    if edition is None:
        _reinitialiser(p)
    else:
        _amorcer(p, {"nb": int(edition.get("nb") or 1)})

    st.markdown("## %s — %s" % (code, acte["libelle"]))
    if edition is None:
        favoris.etoile("ccam", code, acte["libelle"], espace)
    st.info(
        "Acte **CCAM**, et non CSARR ou CSAR. Il compte dans le score de "
        "réadaptation — global, et spécialisé pour les groupes nosologiques "
        "dont la liste le mentionne — mais il se recueille dans la zone "
        "d'actes CCAM du RHS. Aucun modulateur ne s'y associe, et la "
        "pondération publiée vaut pour l'intervenant 10 (médecin).")

    listes = _listes_du_ccam(d, code)
    if listes:
        st.caption("Acte spécialisé pour la ou les listes : %s."
                   % ", ".join("**%s**" % l for l in listes))
    else:
        st.caption("Cet acte ne figure dans aucune liste d'actes "
                   "spécialisés : il ne compte que dans le score global.")

    colonnes = st.columns([1, 1, 2])
    with colonnes[0]:
        realisations = etat.nombre(
            p + "nb", "Nombre de réalisations", 1, 20, 1,
            help="1 sauf si l'acte est réalisé plusieurs fois le même jour.")
    with colonnes[1]:
        if ponderation is not None:
            st.metric("Pondération", ponderation,
                      help=sd.AIDE["Pondération"])
        else:
            st.caption("Pondération non publiée pour cet acte.")
    with colonnes[2]:
        _action_finale(panier.ligne_vide(
            code=code, nomenclature="ccam", libelle=acte["libelle"],
            inter="10", nb=int(realisations),
        ), "%s_panier_ccam_%s" % (espace, code), edition, p)


def _listes_du_ccam(d, code):
    """Listes d'actes spécialisés qui mentionnent cet acte CCAM."""
    spe = d.get("csarr_spe")
    if spe is None or spe.empty:
        return []
    return sorted(set(spe[spe["code"] == code]["libelle_gn"]))


# ---------------------------------------------------------------------------
# Fiche CSAR
# ---------------------------------------------------------------------------

def fiche_csar(d, acte, espace=ESPACE_DEFAUT):
    code = acte["code"]
    mods = sd.modulateurs_csar(d, code)

    st.markdown(
        '<div class="fil">%s %s › %s</div>' % (
            acte["chapitre"], acte["chapitre_titre"], acte["type_libelle"]),
        unsafe_allow_html=True,
    )
    st.subheader("%s — %s" % (code, acte["libelle"]))

    pastilles = [badge(acte["type_libelle"].split("—")[0].strip(), "bleu")]
    if mods["collectif"]:
        pastilles.append(badge("Collectif possible", "vert",
                               "Modalité collective codable (annexe 3)"))
    pastilles.append(badge("Pluriprofessionnel possible", "vert",
                           "Codable pour tous les actes CSAR (guide § 1.4.2)"))
    if mods["temps"]:
        pastilles.append(badge("Modulateur de temps", "orange",
                               "Acte à durée hétérogène : T0 à T4"))
    if mods["technicite"]:
        pastilles.append(badge("Plateau technique : " +
                               " ".join(mods["technicite"]), "orange"))
    spe = sd.spe_csar(d, code)
    if not spe.empty:
        pastilles.append(badge(
            "Acte spécialisé — %d liste(s) de GN" % spe["gn_liste"].nunique(),
            "rouge", "Compte dans le score de réadaptation spécialisée"))
    st.markdown(" ".join(pastilles), unsafe_allow_html=True)
    favoris.etoile("csar", code, acte["libelle"], espace)

    gauche, droite = st.columns([1.15, 1])

    with gauche:
        if acte["definition"]:
            st.markdown("**Définition**")
            st.markdown(puces(acte["definition"]))
        if acte["description"]:
            st.markdown("**Description — contenu de l'acte**")
            st.markdown(puces(acte["description"]))
        if acte["fonction_cif"]:
            st.markdown("**Fonction CIF**")
            st.caption(acte["fonction_cif"])
        if acte["exclusions"]:
            st.markdown("**À l'exclusion de**")
            exclus = [c.strip() for c in acte["exclusions"].split(",")
                      if c.strip()]
            for c in exclus:
                lien_acte(c, "csar", d["lib_csar"].get(c, ""),
                          cle="%s_excl_%s_%s" % (espace, code, c),
                          largeur="stretch")

    with droite:
        st.markdown("**Codes supplémentaires autorisés**")
        blocs = []
        if mods["temps"]:
            blocs.append(("⏱️ Modulateur de temps",
                          ["%s — %s" % (k, v) for k, v in MOD_TEMPS.items()]))
        blocs.append((
            "📍 Modulateur de lieu",
            ["%s — %s" % (c, MOD_LIEU_CSAR[c]) for c in mods["lieux"]]
            or ["*aucun*"],
        ))
        blocs.append((
            "🏋️ Modulateur de technicité",
            ["%s — %s" % (c, MOD_TECHNICITE[c]) for c in mods["technicite"]]
            or ["*aucun*"],
        ))
        if mods["niveau"]:
            niv = [c for c in mods["technicite"] if c in MOD_AVEC_NIVEAU]
            detail = []
            for c in niv:
                for i, lib in enumerate(MOD_AVEC_NIVEAU[c], start=1):
                    detail.append("%s niveau/module %d — %s" % (c, i, lib))
            blocs.append(("🔢 Module et niveau de technicité",
                          detail or ["*aucun*"]))
        blocs.append((
            "👥 Modalités",
            (["1 — Réalisation en collectif"] if mods["collectif"] else [])
            + ["1 — Réalisation en pluriprofessionnel"],
        ))
        ext = d["ref_modulateurs_csar"]
        ext = ext[ext["type"].str.lower().str.startswith("extension")]
        blocs.append(("📎 Extensions documentaires",
                      ["%s — %s" % (r["modalite"], r["libelle"])
                       for _, r in ext.iterrows()]))
        for titre, items in blocs:
            st.markdown("*%s*" % titre)
            st.markdown("\n".join("- " + i for i in items))

        ia = d["csar_intervenants"]
        att = ia[(ia["code"] == code) & (ia["attendu"] == "1")]
        st.markdown("*🧑‍⚕️ Intervenants attendus*")
        if att.empty:
            st.caption("Aucun intervenant spécifiquement attendu.")
        else:
            st.markdown("\n".join(
                "- `%s` %s" % (r["code_inter"], r["lib_inter"])
                for _, r in att.sort_values("code_inter").iterrows()))
            st.caption("Liste indicative (guide CSAR § 2.4) : tout autre "
                       "intervenant reste codable si sa formation le justifie.")

    st.divider()
    with st.expander("🧩 Composer la zone d'acte", expanded=True):
        composeur_csar(d, acte, mods, espace=espace)

    with st.expander("⚖️ Pondérations de l'acte"):
        pond = sd.ponderations_csar(d, code)
        if pond.empty:
            st.info("Aucune pondération publiée pour cet acte.")
        else:
            pond = pond.copy()
            pond["_int"] = pond["intervenant"].map(
                lambda c: "Tous les intervenants" if c == "00"
                else "%s %s" % (c, d["lib_intervenant"].get(c, "")))
            pond["_mod"] = pond["acte_collectif"].map(
                {"0": "Individuel", "1": "Collectif",
                 "2": "Individuel ou collectif"})
            pond["_maj"] = pond.apply(
                lambda r: " ".join(
                    m for m, c in (("temps", "mod_tps"), ("L1", "mod_l1"),
                                   ("L2", "mod_l2"), ("L3", "mod_l3"))
                    if r[c]) or "—", axis=1)
            _tableau_ponderations(d, pond.sort_values(
                ["_mod", "intervenant"]), {
                "_int": "Intervenant", "_mod": "Réalisation",
                "ponderation": "Pondération",
                "_maj": "Modulateurs majorants"})
            st.caption(
                "Pondérations issues du transcodage des pondérations CSARR "
                "(les actes CSAR n'en disposent pas en propre). Elles servent "
                "au calcul des scores de réadaptation ; l'outil ne réalise "
                "pas le groupage.")

    if not spe.empty:
        with st.expander("🎯 Caractère spécialisé — listes de groupes "
                         "nosologiques"):
            spe = spe.copy()
            spe["_int"] = spe["intervenant"].map(
                lambda c: "Tous" if c == "00"
                else "%s %s" % (c, d["lib_intervenant"].get(c, "")))
            spe["_mod"] = spe["acte_coll"].map(
                {"0": "Individuel", "1": "Collectif",
                 "2": "Individuel ou collectif"})
            st.dataframe(
                spe[["libelle_gn", "gn_liste", "_mod", "_int"]].rename(
                    columns={"libelle_gn": "Regroupement de GN",
                             "gn_liste": "GN concernés",
                             "_mod": "Réalisation", "_int": "Intervenant"}),
                width="stretch", hide_index=True)
            st.caption(
                "L'acte est retenu comme *spécialisé* pour ces regroupements "
                "de groupes nosologiques : sa pondération alimente alors le "
                "score de réadaptation spécialisée qui oriente vers le groupe "
                "de réadaptation (voir onglet Références › Groupes de "
                "réadaptation).")

    with st.expander("🔁 Actes CSARR transcodés vers cet acte"):
        tr = sd.transcodage_vers_csarr(d, code)
        if tr.empty:
            st.info("Acte CSAR créé : aucun acte CSARR d'origine "
                    "(signalé ZZZ dans la table d'aide au codage).")
        else:
            st.caption("%d acte(s) CSARR regroupé(s) dans cet acte CSAR."
                       % len(tr))
            for _, r in tr.sort_values("code_csarr").iterrows():
                lien_acte(r["code_csarr"], "csarr", r["libelle_csarr"],
                          cle="%s_tr_%s_%s" % (espace, code, r["code_csarr"]),
                          largeur="stretch")


def composeur_csar(d, acte, mods, edition=None, espace=ESPACE_DEFAUT):
    """Composeur d'une zone d'acte CSAR.

    ``edition`` est la ligne de panier à corriger ; les champs vivent alors
    sous un chemin propre à cette ligne, amorcé par sa composition actuelle.
    ``espace`` isole les champs d'un onglet à l'autre.
    """
    code = acte["code"]
    p = "%s.csar.%s." % (espace, code)
    if edition is None:
        _reinitialiser(p)
    if edition is not None:
        p = "edit.%s." % edition["id"]
        _amorcer(p, {
            "int": edition.get("inter") or "",
            "nb": int(edition.get("nb") or 1),
            # La case de modalité collective est grisée quand l'acte ne
            # l'admet pas : réamorcer un « oui » venu d'un collage y serait
            # indélébile, et la ligne resterait en erreur sans recours.
            "coll": bool(edition.get("coll")) and bool(mods["collectif"]),
            "pp": bool(edition.get("pp")),
            "tps": edition.get("temps") or "",
            "lieu": edition.get("lieu") or "",
            "tech": edition.get("tech") or "",
            "niv": edition.get("niv") or "",
            "ext": edition.get("ext") or "",
        })
    alertes = []

    c1, c2, c3 = st.columns(3)
    with c1:
        inter, attendus = _intervenants(d, p + "int", code)
        realisations = etat.nombre(
            p + "nb", "Nombre de réalisations", 1, 20, 1,
            help="1 sauf si le même acte est réalisé plusieurs fois le même "
                 "jour par le même intervenant.")
    with c2:
        collectif = etat.case(
            p + "coll", "Modalité collective (1)",
            disabled=not mods["collectif"],
            help="Acte réalisé pour un groupe de patients pris en charge "
                 "simultanément ; à coder pour chaque patient."
                 if mods["collectif"] else
                 "Modalité collective non autorisée pour cet acte "
                 "(annexe 3 du guide CSAR).")
        pluripro = etat.case(
            p + "pp", "Modalité pluriprofessionnelle (1)",
            help="Plusieurs professionnels intervenant simultanément ; "
                 "l'acte n'est codé que par le responsable de l'acte.")
    with c3:
        temps = _selection(
            p + "tps", "Modulateur de temps",
            MOD_TEMPS if mods["temps"] else [], MOD_TEMPS,
            aide="Temps effectif de réalisation ; en collectif, coder la "
                 "durée de l'ensemble de l'acte."
                 if mods["temps"] else "Non autorisé pour cet acte.")
        lieu = _selection(p + "lieu", "Modulateur de lieu", mods["lieux"],
                          MOD_LIEU_CSAR)

    c4, c5, c6 = st.columns(3)
    with c4:
        tech = _selection(p + "tech", "Modulateur de technicité",
                          mods["technicite"], MOD_TECHNICITE)
    with c5:
        # L'option « aucun » doit être PRÉFIXÉE et non remplacée : sans elle le
        # widget renvoie « 0 » sans que le codeur ait rien choisi, ce qui fait
        # apparaître un module de technicité dans la zone d'acte et neutralise
        # l'invitation à préciser la gradation.
        options_niv = [""]
        if tech in MOD_AVEC_NIVEAU and mods["niveau"]:
            options_niv = ["", "0", "1", "2"]
        niveau = etat.choix(
            p + "niv", "Module / niveau de technicité", options_niv,
            defaut="",
            format_func=lambda v: VIDE if not v else (
                "0 — non gradué" if v == "0" else
                "%s — %s" % (v, MOD_AVEC_NIVEAU[tech][int(v) - 1])),
            help="Réservé aux plateaux QS, QQ et QC disposant de deux "
                 "modules ou niveaux de complexité.")
    with c6:
        ext = d["ref_modulateurs_csar"]
        ext = ext[ext["type"].str.lower().str.startswith("extension")]
        libs_ext = dict(zip(ext["modalite"], ext["libelle"]))
        extension = _selection(
            p + "ext", "Extension documentaire", ext["modalite"].tolist(),
            libs_ext,
            aide="Aucune table d'association ATIH : la pertinence de "
                 "l'association acte / extension relève du codeur "
                 "(guide CSAR § 1.6).")

    # --- contrôles ---------------------------------------------------------
    if attendus and inter not in attendus:
        alertes.append((
            "avert",
            "L'intervenant **%s %s** ne figure pas dans la liste indicative "
            "des intervenants attendus pour cet acte. Le codage reste "
            "possible si la formation du professionnel le justifie "
            "(guide CSAR § 2.4)." % (inter, d["lib_intervenant"].get(inter, ""))))
    if collectif and not mods["collectif"]:
        alertes.append(("erreur",
                        "La modalité collective n'est pas autorisée pour "
                        "l'acte %s (annexe 3 du guide CSAR)." % code))
    if temps and not mods["temps"]:
        alertes.append(("erreur",
                        "Le modulateur de temps n'est pas autorisé pour "
                        "l'acte %s." % code))
    if tech and tech in MOD_AVEC_NIVEAU and niveau in ("", None):
        alertes.append((
            "info",
            "Le plateau %s dispose de deux modules/niveaux : renseigner le "
            "module et niveau de technicité permet de préciser la gradation "
            "d'usage." % tech))
    if niveau in ("1", "2") and not tech:
        alertes.append(("erreur",
                        "Un module/niveau de technicité ne peut être codé "
                        "sans modulateur de technicité."))
    if tech and not lieu:
        alertes.append((
            "info",
            "Si le plateau technique est mobilisé dans le cadre d'une "
            "prestation externalisée, associer le modulateur de lieu **L3** "
            "(guide CSAR § 1.5)."))
    if extension:
        alertes.append((
            "info",
            "Extension documentaire **%s** : vérifier la cohérence de "
            "l'association avec l'acte, aucune table ATIH ne la contrôle."
            % extension))
    if collectif and temps:
        alertes.append(("info",
                        "Acte collectif : le modulateur de temps doit "
                        "décrire la durée de l'ensemble de l'acte."))

    detail = sd.ponderation_csar_detaillee(d, code, inter, collectif, temps,
                                           lieu)
    for note in detail["notes"]:
        alertes.append(("info", note))

    st.divider()
    _zone_acte([
        ("Code CSAR", code),
        ("Intervenant", inter),
        ("Modalité collective", "1" if collectif else "0"),
        ("Modalité pluriprofessionnelle", "1" if pluripro else "0"),
        ("Modulateur de temps", temps),
        ("Modulateur de lieu", lieu),
        ("Modulateur de technicité", tech),
        ("Module et niveau de technicité", niveau),
        ("Extension documentaire", extension),
        ("Nombre de réalisations", realisations),
    ], alertes)

    colonnes = st.columns([1, 1, 2])
    with colonnes[0]:
        if detail["retenue"] is not None:
            delta = None
            if detail["temps"] is not None and detail["acte"] is not None:
                delta = ("temps %g vs acte %g"
                         % (detail["temps"], detail["acte"]))
            st.metric("Pondération retenue", "%g" % detail["retenue"],
                      delta=delta, delta_color="off",
                      help="Pondération de l'acte pour %s, ou celle du "
                           "modulateur de temps si elle est plus élevée. %s"
                           % (detail["source"], sd.AIDE["Pondération"]))
        else:
            st.caption("Pondération : %s." % detail["source"])
    with colonnes[1]:
        if detail["majoration"]:
            st.metric("Total avec majoration %s" % lieu,
                      "%g" % detail["total"],
                      delta="+%g" % detail["majoration"],
                      help="Majoration du modulateur de lieu, appliquée au "
                           "moment du groupage.")
    with colonnes[2]:
        _action_finale(panier.ligne_vide(
            code=code, nomenclature="csar", libelle=acte["libelle"],
            inter=inter, coll=collectif, pp=pluripro, temps=temps, lieu=lieu,
            tech=tech, niv=niveau, ext=extension, nb=int(realisations),
        ), "%s_panier_csar_%s" % (espace, code), edition, p)


# ---------------------------------------------------------------------------
# Fiche CSARR
# ---------------------------------------------------------------------------

def fiche_csarr(d, acte, espace=ESPACE_DEFAUT):
    code = acte["code"]
    mods = sd.modulateurs_csarr(d, acte)

    chemin = " › ".join(
        "%s %s" % (acte["chap%d_num" % i], acte["chap%d_titre" % i])
        for i in range(1, 5)
        if acte["chap%d_num" % i] and acte["chap%d_titre" % i])
    st.markdown('<div class="fil">%s</div>' % chemin, unsafe_allow_html=True)
    st.subheader("%s — %s" % (code, acte["libelle"]))

    pastilles = []
    if acte["geste_comp"] == "oui":
        pastilles.append(badge("Geste complémentaire", "bleu",
                               "Codable uniquement en complément d'un acte"))
    if mods["dedie"]:
        pastilles.append(badge("Individuel dédié", "gris",
                               "Nombre de patients = 1"))
    if mods["non_dedie"]:
        pastilles.append(badge("Non dédié possible", "orange",
                               "Nombre de patients de 2 à 8"))
    if mods["collectif"]:
        pastilles.append(badge("Collectif", "vert",
                               "Nombre de patients de 2 à 25"))
    if mods["pluripro"]:
        pastilles.append(badge("Pluriprofessionnel", "rouge",
                               "Nombre d'intervenants obligatoire"))
    if mods["appareillage"]:
        pastilles.append(badge("Étapes A / B / C obligatoires", "rouge"))
    if acte["fin"]:
        pastilles.append(badge("Fin de validité : " + acte["fin"], "rouge"))
    if pastilles:
        st.markdown(" ".join(pastilles), unsafe_allow_html=True)
    favoris.etoile("csarr", code, acte["libelle"], espace)

    gauche, droite = st.columns([1.15, 1])

    with gauche:
        notes = sd.notes_csarr(d, code)
        if not notes.empty:
            st.markdown("**Notes du catalogue**")
            st.markdown(sd.rendre_notes(notes))
        else:
            st.caption("Aucune note attachée à ce libellé.")
        if acte["consigne"]:
            st.markdown("**Consigne de codage pour le PMSI**")
            st.warning(acte["consigne"])
        if acte["debut"]:
            st.caption("Début de validité : %s" % acte["debut"])

    with droite:
        st.markdown("**Codes supplémentaires autorisés**")
        blocs = [
            ("📍 Modulateur de lieu",
             ["%s — %s" % (c, MOD_LIEU_CSARR.get(c, "")) for c in mods["lieux"]]
             or ["*aucun*"]),
            ("🧍 Modulateur de patient",
             ["%s — %s" % (c, MOD_PATIENT_CSARR.get(c, ""))
              for c in mods["patient"]] or ["*aucun*"]),
            ("🏋️ Modulateur de technicité",
             ["%s — %s" % (c, MOD_TECHNICITE.get(c, ""))
              for c in mods["technicite"]] or ["*aucun*"]),
        ]
        if mods["niveau"]:
            blocs.append(("🔢 Module et niveau de technicité",
                          ["valeurs autorisées : %s"
                           % ", ".join(mods["niveau"])]))
        if mods["appareillage"]:
            blocs.append(("🔧 Étapes de réalisation",
                          ["%s — %s" % (k, v)
                           for k, v in ETAPES_APPAREILLAGE.items()]))
        ext = d["ref_extensions_csarr"]
        blocs.append(("📎 Extensions documentaires",
                      ["%s — %s" % (r["code"], r["libelle"])
                       for _, r in ext.iterrows()]))
        for titre, items in blocs:
            st.markdown("*%s*" % titre)
            st.markdown("\n".join("- " + i for i in items))

        if mods["gestes"]:
            st.markdown("*➕ Gestes complémentaires autorisés*")
            for g in mods["gestes"]:
                lien_acte(g, "csarr", d["lib_csarr"].get(g, ""),
                          cle="%s_gc_%s_%s" % (espace, code, g),
                          largeur="stretch")

    st.divider()
    tr = sd.transcodage_vers_csar(d, code)
    if not tr.empty:
        cible = tr.iloc[0]
        if cible["code_csar"] == "ZZZ":
            st.error(
                "Aucun équivalent CSAR : cet acte n'a pas été retenu comme "
                "acte de réadaptation. Il ne sera plus codable à partir du "
                "1er janvier 2027.")
        else:
            st.markdown("**➡️ Transcodage vers le CSAR**")
            for _, r in tr.iterrows():
                if r["commentaire"]:
                    st.caption(r["commentaire"])
                lien_acte(r["code_csar"], "csar", r["libelle_csar"],
                          cle="%s_trc_%s_%s" % (espace, code, r["code_csar"]),
                          largeur="stretch")
            st.caption("Suggestion de la table d'aide au codage (annexe 4 du "
                       "guide CSAR) ; un autre choix peut être justifié.")

    with st.expander("🧩 Composer la zone d'acte", expanded=True):
        composeur_csarr(d, acte, mods, espace=espace)

    with st.expander("⚖️ Pondérations de l'acte"):
        pond = sd.ponderations_csarr(d, code)
        if pond.empty:
            st.info("Aucune pondération valide publiée pour cet acte.")
        else:
            pond = pond.copy()
            pond["_int"] = pond["intervenant"].map(
                lambda c: "Tous les intervenants" if c == "00"
                else "%s %s" % (c, d["lib_intervenant"].get(c, "")))
            pond["_maj"] = pond.apply(
                lambda r: " ".join(
                    m for m, c in (("HW", "mod_hw"), ("LJ", "mod_lj"),
                                   ("XH", "mod_xh"), ("L3", "mod_l3"))
                    if r[c]) or "—", axis=1)
            statut = pond.iloc[0]["statut"]
            type_a = pond.iloc[0]["type"]
            st.caption("%s · %s" % (TYPES_CSARR_POND.get(type_a, type_a),
                                    STATUTS_POND.get(statut, statut)))
            _tableau_ponderations(d, pond.sort_values("intervenant"), {
                "_int": "Intervenant", "ponderation": "Pondération",
                "_maj": "Modulateurs majorants"})
            maj = d["ref_modulateurs_csarr"].copy()
            maj["_n"] = pd.to_numeric(maj["majoration_indiv"], errors="coerce")
            maj = maj[maj["_n"] > 0]
            if not maj.empty:
                st.caption(
                    "Majorations appliquées au groupage : "
                    + " · ".join("%s +%s (individuel) / +%s (collectif)"
                                 % (r["code"], r["majoration_indiv"],
                                    r["majoration_coll"] or "0")
                                 for _, r in maj.iterrows()))


def composeur_csarr(d, acte, mods, edition=None, espace=ESPACE_DEFAUT):
    """Composeur d'une zone d'acte CSARR.

    ``edition`` est la ligne de panier à corriger ; les champs vivent alors
    sous un chemin propre à cette ligne, amorcé par sa composition actuelle.
    ``espace`` isole les champs d'un onglet à l'autre.
    """
    code = acte["code"]
    p = "%s.csarr.%s." % (espace, code)
    if edition is None:
        _reinitialiser(p)
    if edition is not None:
        p = "edit.%s." % edition["id"]
        mod_amorce = _modalite_de(edition.get("pat"), mods)
        _amorcer(p, {
            "int": edition.get("inter") or "",
            "nb": int(edition.get("nb") or 1),
            "mod": mod_amorce,
            "pat_" + mod_amorce: int(edition.get("pat") or 1),
            "nbint": int(edition.get("nb_inter") or 1),
            "etapes": sorted(set(edition.get("etapes") or "")),
            "lieu": edition.get("lieu") or "",
            "patmod": edition.get("patient") or "",
            "tech": edition.get("tech") or "",
            "niv": edition.get("niv") or "",
            "ext": edition.get("ext") or "",
            "geste": edition.get("geste") or "",
        })
    alertes = []

    c1, c2, c3 = st.columns(3)
    with c1:
        inter, _ = _intervenants(d, p + "int", csarr=True)
        realisations = etat.nombre(
            p + "nb", "Nombre de réalisations", 1, 20, 1,
            help="1 sauf si le même acte est réalisé plusieurs fois le même "
                 "jour par le même intervenant.")
    with c2:
        # Le CSARR distingue les libellés individuels et collectifs : on ne
        # propose que les modalités effectivement prévues pour ce libellé.
        modalites = []
        if mods["dedie"]:
            modalites.append("dedie")
        if mods["non_dedie"]:
            modalites.append("non_dedie")
        if mods["collectif"]:
            modalites.append("collectif")
        if not modalites:
            modalites = ["dedie"]
        modalite = etat.choix(
            p + "mod", "Modalité de réalisation", modalites,
            defaut=modalites[0],
            format_func=lambda m: MODALITES_CSARR[m][0],
            help="Détermine le nombre de patients à saisir "
                 "(guide CSARR § 3.3.3).")
        # Le nombre de patients a ses propres bornes par modalité, donc son
        # propre chemin dans le magasin : sans quoi une valeur mémorisée pour
        # une modalité serait refusée par les bornes d'une autre.
        _, mini, maxi, defaut = MODALITES_CSARR[modalite]
        patients = etat.nombre(
            p + "pat_" + modalite, "Nombre de patients", mini, maxi, defaut,
            help="Non dédié : nombre maximal de patients présents en même "
                 "temps. Collectif : nombre de patients pris en charge "
                 "simultanément (99 si >= 99).")
    with c3:
        nb_inter = etat.nombre(
            p + "nbint", "Nombre d'intervenants", 1, 9,
            2 if mods["pluripro"] else 1,
            help="Obligatoire pour les actes pluriprofessionnels ; facultatif "
                 "sinon (guide CSARR § 3.3.3).")
        etapes = []
        if mods["appareillage"]:
            etapes = etat.choix_multiple(
                p + "etapes", "Étapes de réalisation",
                list(ETAPES_APPAREILLAGE), defaut=["C"],
                format_func=lambda c: "%s — %s" % (c, ETAPES_APPAREILLAGE[c]),
                help="Au moins une étape est obligatoire pour les actes de "
                     "fabrication d'orthèse ou de prothèse.")

    c4, c5, c6 = st.columns(3)
    with c4:
        lieu = _selection(p + "lieu", "Modulateur de lieu", mods["lieux"],
                          MOD_LIEU_CSARR)
        patient_mod = _selection(p + "patmod", "Modulateur de patient",
                                 mods["patient"], MOD_PATIENT_CSARR)
    with c5:
        tech = _selection(p + "tech", "Modulateur de technicité",
                          mods["technicite"], MOD_TECHNICITE)
        options_niv = [""]
        if tech in MOD_AVEC_NIVEAU and mods["niveau"]:
            options_niv = [v for v in mods["niveau"] if v in ("0", "1", "2")] \
                or ["0", "1", "2"]
            options_niv = [""] + options_niv
        niveau = etat.choix(
            p + "niv", "Module / niveau de technicité", options_niv,
            defaut="",
            format_func=lambda v: VIDE if not v else (
                "0 — non gradué" if v == "0" else
                "%s — %s" % (v, MOD_AVEC_NIVEAU[tech][int(v) - 1])))
    with c6:
        ext = d["ref_extensions_csarr"]
        libs_ext = dict(zip(ext["code"], ext["libelle"]))
        extension = _selection(p + "ext", "Extension documentaire",
                               ext["code"].tolist(), libs_ext)
        geste = _selection(p + "geste", "Geste complémentaire",
                           mods["gestes"], d["lib_csarr"])

    # --- contrôles ---------------------------------------------------------
    if mods["pluripro"] and nb_inter < 2:
        alertes.append((
            "erreur",
            "Acte pluriprofessionnel : le nombre d'intervenants est "
            "obligatoire et doit être au moins égal à 2 "
            "(guide CSARR § 3.3.3.4)."))
    if mods["appareillage"] and not etapes:
        alertes.append((
            "erreur",
            "Acte de fabrication d'appareillage : au moins une étape A, B "
            "ou C doit être codée ; la seule mention du code à 7 caractères "
            "n'est pas autorisée."))
    if modalite == "collectif" and patients < 2:
        alertes.append(("erreur",
                        "Acte collectif : le nombre de patients doit être "
                        "compris entre 2 et 25."))
    if modalite == "collectif" and patients > 25 and code != "ZZR+026":
        alertes.append((
            "avert",
            "Le nombre de patients d'un acte collectif est limité à 25, sauf "
            "ZZR+026 (séance collective d'information)."))
    if niveau in ("1", "2") and not tech:
        alertes.append(("erreur",
                        "Un module/niveau de technicité ne peut être codé "
                        "sans modulateur de technicité."))
    if extension:
        alertes.append((
            "info",
            "Extension documentaire **%s** : le codage n'est pas contrôlé par "
            "une table d'association, vérifier la cohérence avec l'acte "
            "(guide CSARR § 3.3.4.4)." % extension))
    if geste:
        alertes.append((
            "info",
            "Le geste complémentaire **%s** se code dans une zone d'acte "
            "distincte, et seulement s'il est réalisé dans le laps de temps "
            "consacré à l'acte principal." % geste))
    tr = sd.transcodage_vers_csar(d, code)
    if not tr.empty and tr.iloc[0]["code_csar"] not in ("", "ZZZ"):
        alertes.append((
            "info",
            "À partir du 1er janvier 2027, coder **%s** (%s) en CSAR."
            % (tr.iloc[0]["code_csar"], tr.iloc[0]["libelle_csar"])))

    valeur, source = sd.ponderation_effective_csarr(d, code, inter)

    st.divider()
    _zone_acte([
        ("Code CSARR", code),
        ("Intervenant", inter),
        ("Nombre de patients", patients),
        ("Nombre d'intervenants", nb_inter),
        ("Étapes appareillage", "".join(sorted(etapes))),
        ("Modulateur de lieu", lieu),
        ("Modulateur de patient", patient_mod),
        ("Modulateur de technicité", tech),
        ("Module et niveau de technicité", niveau),
        ("Extension documentaire", extension),
        ("Geste complémentaire", geste),
        ("Nombre de réalisations", realisations),
    ], alertes)

    collectif = modalite == "collectif"
    maj = sd.majoration_modulateur_csarr(d, lieu, collectif) if lieu else None
    if maj in ("0", "nan", ""):
        maj = None

    col1, col2, col3 = st.columns([1, 1, 2])
    if valeur is not None:
        col1.metric("Pondération de l'acte codé", valeur,
                    help="Pondération retenue pour %s." % source)
        if maj:
            try:
                total = float(str(valeur).replace(",", ".")) + float(maj)
                col2.metric("Avec majoration %s" % lieu, "%g" % total,
                            delta="+%s" % maj,
                            help="Majoration appliquée au moment du groupage.")
            except ValueError:
                pass
    else:
        col1.caption("Pondération : %s." % source)
    with col3:
        _action_finale(panier.ligne_vide(
            code=code, nomenclature="csarr", libelle=acte["libelle"],
            inter=inter, pat=int(patients), nb_inter=int(nb_inter),
            etapes="".join(sorted(etapes)), lieu=lieu, patient=patient_mod,
            tech=tech, niv=niveau, ext=extension, geste=geste,
            nb=int(realisations),
        ), "%s_panier_csarr_%s" % (espace, code), edition, p)
