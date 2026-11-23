# -*- coding: utf-8 -*-
"""
PMSI SMR — page « Références » : référentiels, arborescences et règles de codage.
"""

import re

import pandas as pd
import streamlit as st

import groupage
import smr_data as sd
import smr_etat as etat
from smr_data import CHAPITRES_CSAR, MOD_AVEC_NIVEAU, TYPES_CSAR

REGLES = [
    ("Principes de codage — communs au CSARR et au CSAR", [
        "**Acte global** : chaque libellé décrit l'acte dans l'intégralité de "
        "sa réalisation. On ne décompose jamais un acte en codant ses actions "
        "élémentaires. La réalisation comprend la préparation de la salle, "
        "l'installation du matériel, la lecture du dossier, le staff "
        "hebdomadaire, la restitution au patient, le compte rendu, la "
        "traçabilité et le codage.",
        "**Codage exact** : le code retenu est celui du libellé correspondant "
        "le plus exactement à l'acte effectué. Le codage « par assimilation » "
        "d'un acte non inscrit au catalogue est interdit ; en l'absence de "
        "libellé adéquat, il faut s'abstenir de coder.",
        "**Acte finalement réalisé** : on code l'acte réellement pratiqué, "
        "apprécié à la fin de sa réalisation complète, et non l'acte "
        "initialement prévu.",
        "**Un seul codeur** : si plusieurs professionnels ont contribué, un "
        "seul acte est codé, par celui à qui incombe la responsabilité de "
        "l'acte. Pour un stagiaire, c'est le type d'intervenant du maître de "
        "stage qui est renseigné.",
        "**Professionnel externe** : tous les actes de réadaptation réalisés "
        "par un professionnel externe à l'établissement doivent être codés, "
        "quel que soit son mode de rémunération.",
    ]),
    ("Règles propres au CSAR", [
        "**Évaluations (E)** : la temporalité (initiale, intermédiaire, "
        "finale) a disparu des libellés. Une évaluation n'est pas une "
        "observation isolée : c'est un acte structuré, tracé dans le dossier.",
        "**Séances (S)** : codables deux fois par jour calendaire par un même "
        "type d'intervenant et pour un même plateau technique (une fois le "
        "matin, une fois l'après-midi), lorsque la séance est réalisée en "
        "totalité. Plus de 2 séances par jour sont admises pour l'éducation "
        "thérapeutique et pour les séances de posture, d'étirement et/ou de "
        "compression cutanée.",
        "**Organes pairs ou multiples** : évaluations et séances peuvent être "
        "codées autant de fois qu'il y a d'organes concernés par le besoin de "
        "réadaptation (pas le côté sain).",
        "**Mises à disposition d'appareillage (M)** : un seul acte par séjour, "
        "sauf organes pairs ou changement d'appareillage. Adaptations "
        "secondaires : coder l'acte de séance. Réparations et fabrications : "
        "non codables en CSAR.",
        "**Préparation / suivi de dossier (P)** : à coder une fois par "
        "démarche distincte.",
        "**Actes implicitement inclus** : 07S14 (massage), 07S04 (mobilisation "
        "articulaire passive) et 07S05 (posture articulaire) ne se codent pas "
        "en association avec 07S01, 07S02, 07S03 ou 07S06. 10S04 (information "
        "à visée préventive) ne se code pas avec 10S01 ni 10S02.",
        "**Actes identiques** : même code et mêmes modalités/modulateurs sur "
        "une journée par le même professionnel → le nombre de réalisations "
        "peut être recueilli au lieu de coder chaque acte.",
    ]),
    ("Règles propres au CSARR", [
        "**Individuel dédié** : un professionnel, un patient. Nombre de "
        "patients = 1.",
        "**Individuel non dédié** : le professionnel prend en charge plusieurs "
        "patients en leur consacrant des laps de temps spécifiques en face à "
        "face. Nombre de patients de 2 à 8 — on renseigne le nombre maximal de "
        "patients présents en même temps. Seuls certains actes ont le statut "
        "« non dédié possible ».",
        "**Collectif** : plusieurs patients en même temps, réalisant le même "
        "acte. Nombre de patients de 2 à 25 (sauf ZZR+026), 99 au-delà de 99.",
        "**Pluriprofessionnel** : actes exigeant la collaboration simultanée "
        "de plusieurs professionnels de disciplines différentes. Le nombre "
        "d'intervenants est alors **obligatoire**. Hors de ces actes, sa "
        "saisie reste facultative.",
        "**Appareillage** : les actes de fabrication d'orthèse ou de prothèse "
        "sont subdivisés en 3 étapes (A prise de mesure/moulage, B "
        "fabrication, C mise à disposition). Au moins une étape doit être "
        "codée ; la seule mention du code à 7 caractères n'est pas autorisée. "
        "L'appareillage facturé par un prestataire externe n'est pas codable.",
        "**Modulateurs** : jusqu'à trois modulateurs — un modulateur patient, "
        "un modulateur de lieu, un modulateur de technicité — dans la limite "
        "des associations autorisées pour le code.",
        "**Gestes complémentaires** : codables seulement si l'association est "
        "prévue et si le geste est réalisé dans le laps de temps consacré à "
        "l'acte principal.",
    ]),
    ("Ce qui change du CSARR au CSAR", [
        "512 actes → **146 actes** : regroupement selon deux axes, la "
        "**fonction** (CIF) et l'**objectif** (évaluation, séance, mise à "
        "disposition, préparation de dossier).",
        "Le code passe de 7 à **5 caractères** ; les notions de topographie et "
        "d'action réalisée disparaissent de la codification.",
        "**Nombre réel de patients** supprimé → remplacé par la **modalité "
        "collective** (0/1).",
        "**Nombre d'intervenants** supprimé, ainsi que la notion d'actes "
        "pluriprofessionnels par nature → remplacé par la **modalité "
        "pluriprofessionnelle** (0/1), codable pour tous les actes.",
        "La distinction **individuel dédié / non dédié** disparaît et ne fait "
        "plus l'objet d'un recueil : elle est laissée à l'appréciation du "
        "professionnel.",
        "Le **modulateur de patient** (EZ, réalisation fractionnée) est "
        "supprimé.",
        "Les **étapes A et B** d'appareillage sont supprimées : seule la mise "
        "à disposition (ex-étape C) est transcodée, un seul acte de mise à "
        "disposition par appareillage étant attendu.",
        "Apparition des **modulateurs de temps** T0 à T4, pour 32 actes à "
        "durée hétérogène — ils n'existaient pas en CSARR.",
        "Les modulateurs de lieu ZV, ME, TF et RW sont supprimés ; HW et LJ "
        "fusionnent en **L1**, XH devient **L2**, L3 est inchangé.",
        "La **temporalité des évaluations** (initiale / intermédiaire / "
        "finale) disparaît des libellés.",
    ]),
]


def page(d):
    st.header("📚 Références & aides au codage")
    # La page se rouvre sur le dernier onglet consulté.
    onglets = etat.onglets("ref.onglet", [
        "🎛️ Modulateurs & modalités", "📎 Extensions documentaires",
        "🧑‍⚕️ Intervenants", "🔁 Transcodage",
        "🌳 Arborescence CSAR", "🌳 Arborescence CSARR",
        "📖 Règles de codage", "🏥 Groupes nosologiques & réadaptation",
        "🩺 CMA & sévérité", "📄 Sources",
    ])

    with onglets[0]:
        _modulateurs(d)
    with onglets[1]:
        _extensions(d)
    with onglets[2]:
        _intervenants(d)
    with onglets[3]:
        _transcodage(d)
    with onglets[4]:
        arborescence_csar(d)
    with onglets[5]:
        arborescence_csarr(d)
    with onglets[6]:
        for titre, items in REGLES:
            st.subheader(titre)
            st.markdown("\n".join("- " + i for i in items))
    with onglets[7]:
        _groupes(d)
    with onglets[8]:
        _cma(d)
    with onglets[9]:
        _sources(d)


# ---------------------------------------------------------------------------
# Arborescences
# ---------------------------------------------------------------------------

def arborescence_csar(d):
    st.subheader("Arborescence du CSAR")
    st.markdown(
        "Le CSAR est organisé par **chapitre**, qui désigne la fonction "
        "concernée, puis par **objectif** de l'acte. Le code à 5 caractères "
        "reflète directement cette organisation : les 2 premiers caractères "
        "donnent le chapitre, le 3ᵉ l'objectif, les 2 derniers un compteur "
        "sans signification, réinitialisé à chaque chapitre et à chaque "
        "objectif.")

    actes = d["csar_actes"]
    nb = actes["chapitre"].value_counts()
    choix = etat.choix(
        "arbo.chap_csar", "Chapitre à explorer", [""] + list(CHAPITRES_CSAR),
        defaut="",
        format_func=lambda c: "Tous les chapitres (%d actes)" % len(actes)
        if not c else "%s — %s (%d actes)" % (c, CHAPITRES_CSAR[c],
                                              nb.get(c, 0)))

    chapitres = [choix] if choix else list(CHAPITRES_CSAR)
    for chap in chapitres:
        dans_chap = actes[actes["chapitre"] == chap]
        if dans_chap.empty:
            continue
        st.markdown(
            '<div class="arbo-n1">%s — %s · %d actes</div>'
            % (chap, CHAPITRES_CSAR[chap], len(dans_chap)),
            unsafe_allow_html=True)
        for objectif in ("E", "S", "M", "P"):
            lignes = dans_chap[dans_chap["type_acte"] == objectif]
            if lignes.empty:
                continue
            st.markdown(
                '<div class="arbo-n2">%s — %s · %d actes</div>'
                % (objectif, TYPES_CSAR[objectif].split("—")[0].strip(),
                   len(lignes)),
                unsafe_allow_html=True)
            for _, a in lignes.sort_values("code").iterrows():
                st.markdown(
                    '<div class="arbo-n4"><code>%s</code> %s</div>'
                    % (a["code"], a["libelle"]), unsafe_allow_html=True)


def arborescence_csarr(d):
    st.subheader("Arborescence du CSARR")
    st.markdown(
        "Le CSARR est organisé par **fonction** (chapitre), puis par "
        "**objectif** (sous-chapitre : évaluation, prise en charge "
        "thérapeutique), affiné en paragraphes et sous-paragraphes. Le code à "
        "7 caractères reflète la topographie (2 lettres), l'action (1 lettre) "
        "et la voie d'abord ou technique (1 lettre) ; les 3 chiffres sont un "
        "compteur sans signification.")

    struct = d["csarr_structure"]
    actes = d["csarr_actes"]
    chapitres = struct[struct["niveau"] == 1].sort_values("hiera")
    liste = chapitres["hiera"].tolist()
    nb_actes = actes["chap1_num"].value_counts()
    # Le chapitre 00 ne contient que l'introduction et les notes générales :
    # on ouvre sur le premier chapitre porteur d'actes.
    defaut = next((h for h in liste if nb_actes.get(h, 0)), liste[0])
    choix = etat.choix(
        "arbo.chap_csarr", "Chapitre à explorer", liste, defaut=defaut,
        format_func=lambda h: "%s — %s (%d actes)" % (
            h, chapitres.set_index("hiera")["titre"].get(h, ""),
            nb_actes.get(h, 0)))

    sous = struct[(struct["hiera"].str.startswith(choix + "."))
                  | (struct["hiera"] == choix)]
    dans_chap = actes[actes["chap1_num"] == choix]
    for _, s in sous.sort_values("hiera").iterrows():
        niv = int(s["niveau"])
        if niv == 1:
            continue
        # Nombre d'actes du sous-arbre pour le titre, mais on ne liste que les
        # actes rattachés directement à cette subdivision : un acte n'apparaît
        # ainsi qu'une seule fois dans l'arborescence.
        prefixe = s["hiera"] + "."
        sous_arbre = dans_chap[(dans_chap["hiera"] == s["hiera"])
                               | dans_chap["hiera"].str.startswith(prefixe)]
        directs = dans_chap[dans_chap["hiera"] == s["hiera"]]
        st.markdown(
            '<div class="arbo-n%d">%s — %s · %d actes</div>'
            % (min(niv - 1, 4), s["hiera"], s["titre"], len(sous_arbre)),
            unsafe_allow_html=True)
        if s["notes"]:
            st.caption(s["notes"])
        for _, a in directs.iterrows():
            st.markdown('<div class="arbo-n4"><code>%s</code> %s</div>'
                        % (a["code"], a["libelle"]), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Autres onglets
# ---------------------------------------------------------------------------

def _modulateurs(d):
    st.subheader("CSAR — modulateurs, modalités et extensions")
    st.caption("Annexe 2 du guide de codage CSAR. Les associations autorisées "
               "acte par acte figurent sur la fiche de l'acte.")
    st.dataframe(
        d["ref_modulateurs_csar"].rename(columns={
            "type": "Type", "variable": "Variable", "modalite": "Code",
            "niveau": "Module / niveau", "libelle": "Libellé"}),
        width="stretch", hide_index=True, height=420)

    st.subheader("CSARR — modulateurs et majorations de pondération")
    st.caption("Sous-chapitre 12.02 du CSARR. Les majorations sont appliquées "
               "au moment du groupage.")
    st.dataframe(
        d["ref_modulateurs_csarr"].rename(columns={
            "code": "Code", "libelle": "Libellé",
            "majoration_indiv": "Majoration actes individuels",
            "majoration_coll": "Majoration actes collectifs"}),
        width="stretch", hide_index=True)

    st.subheader("Plateaux techniques spécialisés à deux niveaux")
    st.caption("Seuls QS, QQ et QC disposent de deux modules ou niveaux de "
               "complexité ; le module/niveau ne peut être codé qu'avec l'un "
               "de ces trois modulateurs.")
    st.dataframe(
        pd.DataFrame([{"Modulateur": c, "Module / niveau 1": v[0],
                       "Module / niveau 2": v[1]}
                      for c, v in MOD_AVEC_NIVEAU.items()]),
        width="stretch", hide_index=True)


def _extensions(d):
    st.subheader("Extensions documentaires")
    st.markdown(
        "Les extensions documentaires signalent un plateau technique ou un "
        "équipement mobilisé **en dehors** de ceux répondant à un cahier des "
        "charges spécifique (ces derniers étant décrits par un modulateur de "
        "technicité). Elles ne sont **pas contrôlées par une table "
        "d'association** : la pertinence de l'association avec l'acte relève "
        "du codeur.")
    g, dr = st.columns(2)
    with g:
        st.markdown("**CSARR — 13 extensions**")
        st.dataframe(
            d["ref_extensions_csarr"].rename(columns={
                "code": "Code", "libelle": "Libellé",
                "sous_chapitre": "Sous-chapitre"}),
            width="stretch", hide_index=True, height=380)
    with dr:
        st.markdown("**CSAR — 7 extensions conservées**")
        ext = d["ref_modulateurs_csar"]
        ext = ext[ext["type"].str.lower().str.startswith("extension")]
        st.dataframe(
            ext[["modalite", "libelle"]].rename(columns={
                "modalite": "Code", "libelle": "Libellé"}),
            width="stretch", hide_index=True, height=380)
        perdus = sorted(set(d["ref_extensions_csarr"]["code"])
                        - set(ext["modalite"]))
        st.caption("Non repris dans le CSAR : %s." % ", ".join(perdus))


def _intervenants(d):
    st.subheader("Catégories d'intervenant")
    st.caption(
        "Le type d'intervenant renseigné est toujours celui du professionnel "
        "qui a la **responsabilité** de l'acte. Les codes 80 et 81, "
        "facultatifs, n'existent qu'en CSAR : 80 pour l'éducation "
        "thérapeutique et la prévention, 81 pour les prises en charge "
        "nécessitant une formation particulière (thérapie psychocorporelle, "
        "prise en charge non médicamenteuse de la douleur, thérapie "
        "familiale).")
    ref = d["ref_intervenants"].copy()
    ref["csarr"] = ref["csarr"].map(lambda v: "✔" if v else "")
    st.dataframe(
        ref.rename(columns={"code": "Code", "libelle": "Libellé",
                            "csarr": "Existe en CSARR"}),
        width="stretch", hide_index=True, height=520)

    st.subheader("Nombre d'actes CSAR attendus par intervenant")
    st.caption(
        "Combien d'actes du CSAR, **sur les 146**, citent cette catégorie "
        "parmi les intervenants attendus (annexe 1 du guide CSAR). C'est un "
        "**comptage d'actes**, non une somme de pondérations et non un "
        "objectif d'activité : l'ergothérapeute est cité pour 99 actes, le "
        "masseur-kinésithérapeute pour 90. Cette liste est **indicative** — "
        "coder un acte avec un autre intervenant reste possible si la "
        "formation du professionnel le justifie (guide CSAR § 2.4), et "
        "l'outil se contente alors d'un avertissement.")
    ia = d["csar_intervenants"]
    att = (ia[ia["attendu"] == "1"].groupby(["code_inter", "lib_inter"])
           .size().reset_index(name="Actes attendus")
           .sort_values("Actes attendus", ascending=False))
    st.dataframe(
        att.rename(columns={"code_inter": "Code", "lib_inter": "Intervenant"}),
        width="stretch", hide_index=True, height=400)


def _transcodage(d):
    st.subheader("Transcodage des modulateurs CSARR → CSAR")
    st.caption("Addendum 1 du guide de codage CSAR.")
    st.dataframe(
        d["ref_transco_modulateurs"].rename(columns={
            "type": "Type", "code_csarr": "Code CSARR",
            "libelle_csarr": "Libellé CSARR", "code_csar": "Code CSAR",
            "libelle_csar": "Libellé CSAR"}),
        width="stretch", hide_index=True, height=420)

    st.subheader("Table d'aide au codage CSARR → CSAR")
    t = d["transcodage"]
    st.caption(
        "%d correspondances. %d actes CSARR sans équivalent CSAR (ZZZ) et %d "
        "actes CSAR créés sans origine CSARR."
        % (len(t), (t["code_csar"] == "ZZZ").sum(),
           (t["code_csarr"] == "ZZZ").sum()))
    filtre = etat.texte("ref.filtre_transco",
                        "Filtrer la table (code ou mots du libellé)")
    vue = t
    if filtre.strip():
        m = sd.normaliser(filtre)
        champ = (t["code_csarr"] + " " + t["code_csar"] + " "
                 + t["libelle_csarr"] + " " + t["libelle_csar"]).map(
            sd.normaliser)
        vue = t[champ.str.contains(re.escape(m), na=False)]
    st.dataframe(
        vue.rename(columns={
            "code_csarr": "Code CSARR", "libelle_csarr": "Libellé CSARR",
            "code_csar": "Code CSAR", "libelle_csar": "Libellé CSAR",
            "type": "Objectif", "commentaire": "Commentaire"}),
        width="stretch", hide_index=True, height=440)


def _groupes(d):
    st.subheader("Groupes nosologiques")
    ref_gn = d.get("ref_gn")
    if ref_gn is not None and not ref_gn.empty:
        st.caption(
            "%d groupes nosologiques. La colonne « liste d'actes spécialisés » "
            "indique le regroupement de GN qui partage la même liste ; les GN "
            "sans liste mais marqués « GR spé unique » disposent malgré tout "
            "d'un groupe de réadaptation spécialisée importante."
            % len(ref_gn))
        vue = ref_gn.copy()
        vue["gr_spe_unique"] = vue["gr_spe_unique"].map(
            lambda v: "✔" if v else "")
        st.dataframe(
            vue[["gn", "libelle", "cm", "libelle_gn_liste", "gr_spe_unique"]]
            .rename(columns={
                "gn": "GN", "libelle": "Libellé", "cm": "CM",
                "libelle_gn_liste": "Liste d'actes spécialisés",
                "gr_spe_unique": "GR spé unique"}),
            width="stretch", hide_index=True, height=420,
            column_config={"Libellé": st.column_config.TextColumn(
                width="large")})

    st.subheader("Groupes de réadaptation et seuils de score")
    st.markdown(
        "Le **score de réadaptation** est la somme des pondérations des actes "
        "CSARR (ou CCAM) réalisés. Il est calculé de deux façons :\n"
        "- **score spécialisé** : seuls les actes appartenant à la liste "
        "d'actes spécialisés du groupe nosologique sont comptés ;\n"
        "- **score global** : tous les actes sont comptés.\n\n"
        "Chaque score est décliné *par séjour* et *par jour* (division par le "
        "nombre de jours du lundi au vendredi). La comparaison aux seuils du "
        "groupe nosologique oriente le séjour vers un groupe de réadaptation.")
    st.info(
        "Le panier calcule ces deux scores pour les actes que vous y placez "
        "(onglet **🧺 Panier**). L'outil ne réalise pas le groupage : la "
        "génération des GMT puis des GME avec valorisation est prévue dans les "
        "évolutions ultérieures.")

    gr = d["ref_gr"]
    if gr.empty:
        st.warning("Fichier GR_infos absent du dossier sources.")
        return
    noms = {
        "gn": "GN", "libelle": "Libellé du groupe nosologique",
        "hc_specialisee": "HC · spécialisée", "hc_globale": "HC · globale",
        "hc_autres": "HC · autre", "hc_pediatrique": "HC · pédiatrique",
        "hc_seuil_sejour_spe": "HC · seuil spé. séjour",
        "hc_seuil_jour_spe": "HC · seuil spé. jour",
        "hc_seuil_sejour_glob": "HC · seuil global séjour",
        "hc_seuil_jour_glob": "HC · seuil global jour",
        "htp_tres_intense": "HTP · très intense", "htp_intense": "HTP · intense",
        "htp_moderee": "HTP · modérée",
        "htp_indifferenciee": "HTP · indifférenciée",
        "htp_pediatrique": "HTP · pédiatrique",
        "htp_seuil_bas": "HTP · seuil bas", "htp_seuil_haut": "HTP · seuil haut",
    }
    ordre = [c for c in ["gn", "libelle"] if c in gr.columns]
    ordre += [c for c in gr.columns if c not in ordre]
    st.dataframe(
        gr[ordre].rename(columns=noms), width="stretch", hide_index=True,
        height=440,
        column_config={"Libellé du groupe nosologique":
                       st.column_config.TextColumn(width="large")})
    st.caption("HC : hospitalisation complète · HTP : hospitalisation à temps "
               "partiel. Une cellule « oui » signale l'existence du groupe de "
               "réadaptation pour ce GN.")


# ---------------------------------------------------------------------------
# CMA — complications et morbidités associées
# ---------------------------------------------------------------------------

LIMITE_CMA = 300


def _cma(d):
    """Les marqueurs de sévérité : diagnostics CMA et actes CCAM."""
    diag = d.get("cim_diag")
    if diag is None or diag.empty:
        st.info("Référentiel CIM non chargé.")
        return
    cma = diag[diag["cma"] == "X"]
    ccam = d.get("ref_cma_ccam")

    st.subheader("🩺 Complications et morbidités associées")
    st.markdown(
        "Une **CMA** est un diagnostic — ou l'un de quelques actes CCAM — dont "
        "la présence porte le **niveau de sévérité** du GME de 1 à 2. Il n'y "
        "a ni comptage ni degré : une seule CMA retenue suffit. Les niveaux 1 "
        "et 2 sont propres à l'hospitalisation complète ; en temps partiel le "
        "niveau vaut 0.")
    st.markdown(
        "**Position de codage.** Pour être retenu, le diagnostic doit être "
        "porté en **manifestation morbide principale ou en diagnostic "
        "associé** — les 794 codes ci-dessous sont tous codables en DAS. "
        "L'**affection étiologique** n'est comptée que si vous le demandez "
        "sur la page « Séjour & valorisation » : les sources de l'ATIH "
        "divergent sur ce point et l'outil ne tranche pas à votre place.")
    st.markdown(
        "**Exclusion.** Une CMA ne compte que si elle n'est pas exclue. À "
        "chaque CMA est attachée une liste de diagnostics qui la neutralisent, "
        "mais seulement lorsque l'un d'eux a **orienté le séjour** vers son "
        "groupe nosologique — c'est-à-dire lorsqu'il a satisfait l'un des "
        "tests du nœud retenu, et non simplement lorsqu'il figure dans le "
        "résumé. La complication ne décrit alors rien de plus que la "
        "pathologie traitée. Les actes CCAM valant CMA ne sont jamais "
        "neutralisés.")
    st.markdown(
        "**Réserve.** Le niveau 2 doit encore **exister pour le groupe de "
        "lourdeur** atteint. Les groupes de soins palliatifs n'en ont pas : "
        "une CMA y est retenue sans faire passer le GME au niveau 2.")

    exclusions = {c: len(groupage.exclusions_de(d, c)) for c in cma["code"]}
    sans = sum(1 for n in exclusions.values() if not n)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Diagnostics CMA", len(cma))
    c2.metric("Actes CCAM CMA", 0 if ccam is None else len(ccam))
    c3.metric("CMA avec liste d'exclusion", len(cma) - sans)
    c4.metric("CMA que rien n'exclut", sans,
              help="Aucun diagnostic ne peut neutraliser ces CMA. Le passage "
                   "au niveau 2 reste subordonné à son existence pour le "
                   "groupe de lourdeur.")

    sous = etat.onglets("ref.onglet_cma",
                        ["🧬 Diagnostics CMA", "🔧 Actes CCAM valant CMA"])
    with sous[0]:
        _cma_diagnostics(d, cma, exclusions)
    with sous[1]:
        _cma_ccam(d, ccam)


def _positions_cim(ligne):
    """Positions de codage d'un diagnostic, telles que publiées par l'ATIH."""
    positions = [nom for cle, nom in (("fpp", "FPP"), ("mmp", "MMP"),
                                      ("ae", "AE"), ("das", "DAS"))
                 if ligne.get(cle) == "oui"]
    return " · ".join(positions) or "—"


def _cma_diagnostics(d, cma, exclusions):
    """Liste filtrable des diagnostics CMA, et exclusions de l'un d'eux."""
    c1, c2 = st.columns([3, 2])
    with c1:
        requete = etat.texte(
            "ref.cma.q", "Filtrer par code ou mots du libellé",
            placeholder="Ex. : L89 · ulcère de décubitus · malnutrition")
    with c2:
        seulement = etat.case(
            "ref.cma.sans_exclusion", "Seulement les CMA que rien n'exclut",
            help="Aucune liste d'exclusion ne les neutralise.")

    base = cma
    if seulement:
        base = base[base["code"].map(lambda c: not exclusions.get(c))]

    if str(requete).strip():
        trouves, total = sd.chercher_cim(d, requete, LIMITE_CMA, base=base)
    else:
        trouves, total = base.head(LIMITE_CMA), len(base)

    if not total:
        st.caption(
            "Aucune CMA ne correspond. Les libellés sont ceux de l'ATIH, sans "
            "synonymes : une escarre s'y lit « ulcère de décubitus », une "
            "dénutrition « malnutrition ».")
        return
    st.caption("%d CMA%s." % (
        total, "" if total <= LIMITE_CMA
        else " — les %d premières sont affichées" % LIMITE_CMA))

    tableau = pd.DataFrame({
        "Code": trouves["code"],
        "Libellé": trouves["libelle"],
        "CM": trouves["cm"],
        "Positions": trouves.apply(_positions_cim, axis=1),
        # Colonne de texte et non de nombres : mélanger un entier et « rien »
        # dans la meme colonne fait échouer la sérialisation Arrow des tableaux.
        "Exclue par": trouves["code"].map(
            lambda c: str(exclusions[c]) if exclusions.get(c) else "rien"),
    })
    evenement = st.dataframe(
        tableau, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-cell",
        key="ref_cma_%s_%d" % (sd.normaliser(str(requete)), int(seulement)),
        height=min(38 + 35 * len(tableau), 400),
        column_config={
            "Libellé": st.column_config.TextColumn(width="large"),
            "Positions": st.column_config.TextColumn(
                width="small",
                help="Positions où ce diagnostic peut être codé. Comptent "
                     "pour la sévérité : la MMP et les DAS ; l'affection "
                     "étiologique seulement selon la lecture retenue."),
            "Exclue par": st.column_config.TextColumn(
                width="small",
                help="Nombre de diagnostics qui neutralisent cette CMA "
                     "lorsqu'ils orientent déjà le séjour."),
        })

    # Sélection par cellule : cliquer n'importe où dans la ligne suffit,
    # comme dans les tableaux de recherche d'actes.
    cellules = (evenement.selection.get("cells") or []) if evenement else []
    if not cellules or cellules[0][0] >= len(trouves):
        st.caption("👆 Cliquez une ligne pour lire la liste des diagnostics "
                   "qui neutralisent cette CMA.")
        return
    _exclusions_cma(d, trouves.iloc[cellules[0][0]])


def _exclusions_cma(d, ligne):
    """Diagnostics qui neutralisent la CMA sélectionnée."""
    code = ligne["code"]
    codes = sorted(groupage.exclusions_de(d, code))
    st.divider()
    st.markdown("#### Exclusions de `%s` — %s"
                % (code, str(ligne["libelle"]).capitalize()))
    if not codes:
        st.success(
            "Aucune exclusion : aucun diagnostic ne neutralise cette CMA, "
            "quelle que soit l'orientation du séjour. Le passage au niveau 2 "
            "reste subordonné à son existence pour le groupe de lourdeur.")
        return
    st.caption(
        "Ces %d diagnostics neutralisent la CMA `%s` lorsqu'ils ont orienté "
        "le séjour vers son groupe nosologique." % (len(codes), code))

    index = d.get("_cim_index", {})
    libs = [{"Code": c,
             "Libellé": (index.get(c) or {}).get("libelle", "")}
            for c in codes]
    filtre = etat.texte("ref.cma.q_excl", "Filtrer ces exclusions",
                        placeholder="Ex. : I63")
    mots = sd.normaliser(filtre).split()
    if mots:
        libs = [l for l in libs
                if all(m in sd.normaliser(l["Code"] + " " + l["Libellé"])
                       for m in mots)]
    if not libs:
        st.caption("Aucun des %d codes d'exclusion ne correspond au filtre."
                   % len(codes))
        return
    st.caption("%d code(s) affiché(s) sur %d." % (len(libs), len(codes)))
    st.dataframe(pd.DataFrame(libs), width="stretch", hide_index=True,
                 height=260,
                 column_config={"Libellé": st.column_config.TextColumn(
                     width="large")})


def _cma_ccam(d, ccam):
    """Les actes CCAM qui valent complication à eux seuls."""
    if ccam is None or ccam.empty:
        st.info("Table des actes CCAM valant CMA non chargée.")
        return
    st.markdown(
        "Ces actes sont retenus comme complication par leur seule présence "
        "dans le résumé, et aucune liste d'exclusion ne les neutralise — le "
        "niveau 2 devant néanmoins exister pour le groupe de lourdeur. La "
        "comparaison se fait sur les **7 premiers caractères** du code.")
    requete = etat.texte("ref.cma.q_ccam", "Filtrer par code ou libellé",
                         placeholder="Ex. : GLLD002 · transfusion")
    lignes = ccam
    mots = sd.normaliser(requete).split()
    if mots:
        champ = (ccam["code"] + " " + ccam["libelle"]).map(sd.normaliser)
        garde = champ.map(lambda t: all(m in t for m in mots))
        lignes = ccam[garde]
    st.caption("%d acte(s) sur %d." % (len(lignes), len(ccam)))
    st.dataframe(
        pd.DataFrame({
            "Code (7)": lignes["code7"],
            "Code du fichier ATIH": lignes["code"],
            "Libellé": lignes["libelle"],
        }), width="stretch", hide_index=True,
        height=min(38 + 35 * len(lignes), 420),
        column_config={"Libellé": st.column_config.TextColumn(width="large")})


def _sources(d):
    st.subheader("Fichiers sources et versions")
    meta = d["meta"]
    st.dataframe(
        pd.DataFrame(sorted(meta.items()), columns=["Clé", "Valeur"]),
        width="stretch", hide_index=True)
    div = meta.get("transcodage_divergences", "0")
    if div and div != "0":
        st.warning(
            "Le fichier `%s` est une publication antérieure : il renvoie "
            "encore vers des codes CSAR supprimés depuis (11S14 à 11S16) et "
            "diverge de la table d'aide au codage sur **%s** correspondances. "
            "C'est la table d'aide au codage (annexe 4) du fichier `%s` qui "
            "fait foi dans cet outil ; seuls les commentaires du fichier "
            "autonome sont réutilisés."
            % (meta.get("version_transcodage", ""), div,
               meta.get("version_csar", "")))
    st.markdown(
        "**Documents de référence** (dossier `sources/`)\n"
        "- Guide de codage du CSAR, version n°1 2026 — ATIH\n"
        "- CSARR 2026, guide de lecture et de codage + partie analytique — "
        "ATIH, publié au Bulletin officiel\n"
        "- Guide méthodologique SMR 2026 (chapitre IV § 3 : actes de "
        "réadaptation) — ATIH\n"
        "- Manuel de groupage GME 2026, volumes 1 à 3 — ATIH "
        "(dossier `sources/gme/`)\n"
        "- Fichiers de pondération des actes, listes d'actes spécialisés et "
        "seuils des groupes de réadaptation — ATIH\n\n"
        "**Avertissement** : outil d'aide au codage et à la lecture des "
        "catalogues. En cas de divergence, seuls font foi les documents "
        "officiels de l'ATIH et les textes publiés au Journal officiel ou au "
        "Bulletin officiel Santé Protection sociale Solidarité.")
