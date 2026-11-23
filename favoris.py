# -*- coding: utf-8 -*-
"""
PMSI SMR — favoris : les actes que l'on code le plus souvent, nommés et commentés.

Les favoris sont rangés **hors du dossier du projet**, dans le dossier commun
aux outils du DIM (``~/.dim/smr_favoris.json``) : ils survivent ainsi au
remplacement du dossier de l'application — téléchargement d'une nouvelle
version, reconstruction de la base. Pour passer d'un poste à l'autre, la page
Favoris les exporte et les importe en JSON.

Chaque favori est un dictionnaire :

    nomenclature  « csarr », « csar » ou « ccam »
    code          code de l'acte : GLR+226, 07S06, DKRP002
    nom           intitulé libre ; vide, le libellé officiel en tient lieu
    commentaire   annotation libre
    ajoute_le     date d'ajout, AAAA-MM-JJ

Le module réunit le stockage, l'étoile des fiches d'acte et la page Favoris.
Les opérations d'écriture relisent le fichier juste avant de l'écrire : deux
onglets du navigateur ouverts sur l'application ne s'écrasent pas l'un l'autre.
"""

import datetime
import json
import math
import os
import zlib

import pandas as pd
import streamlit as st

import panier
import smr_data as sd
import smr_etat as etat

# Les outils du DIM (SMR, CCAM…) partagent un seul dossier dans le répertoire
# personnel, ~/.dim, où chacun range ses fichiers sous un nom préfixé.
DOSSIER_FAVORIS = os.path.join(os.path.expanduser("~"), ".dim")
FICHIER_FAVORIS = os.path.join(DOSSIER_FAVORIS, "smr_favoris.json")

NOMENCLATURES = {"csarr": "CSARR", "csar": "CSAR", "ccam": "CCAM"}

# Espace de clés des fiches ouvertes depuis la page Favoris (voir
# fiches.ESPACE_DEFAUT) : la même fiche peut l'être aussi dans une recherche.
ESPACE_FICHE = "fav"


# ---------------------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------------------

def _texte(v):
    """Valeur libre -> chaîne propre ; absente ou cellule vidée -> ''."""
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip()


def cle(nomenclature, code):
    """Identifiant d'un favori, unique dans les trois nomenclatures."""
    return "%s|%s" % (nomenclature, code)


def nettoyer(donnees):
    """Favoris valides d'une liste lue sur disque ou importée.

    Le code fait foi : la nomenclature en est déduite comme dans le panier, et
    il est remis en forme — « glr226 » devient « GLR+226 ». Les entrées sans
    code reconnaissable et les doublons sont écartés.
    Renvoie (favoris, nombre d'entrées écartées).
    """
    propres, vus, ecartes = [], set(), 0
    for brut in donnees if isinstance(donnees, list) else []:
        nomen, code = (panier.reconnaitre(brut.get("code", ""))
                       if isinstance(brut, dict) else ("", ""))
        if not nomen or cle(nomen, code) in vus:
            ecartes += 1
            continue
        vus.add(cle(nomen, code))
        propres.append({
            "nomenclature": nomen,
            "code": code,
            "nom": _texte(brut.get("nom")),
            "commentaire": _texte(brut.get("commentaire")),
            "ajoute_le": _texte(brut.get("ajoute_le")),
        })
    return propres, ecartes


def lire(chemin=None):
    """(favoris, alerte) ; l'alerte signale un fichier présent mais illisible."""
    chemin = chemin or FICHIER_FAVORIS
    if not os.path.exists(chemin):
        return [], ""
    try:
        with open(chemin, encoding="utf-8") as f:
            donnees = json.load(f)
    except (OSError, ValueError) as err:
        return [], "Le fichier des favoris est illisible (%s)." % err
    if not isinstance(donnees, list):
        return [], ("Le fichier des favoris est illisible : une liste JSON "
                    "est attendue.")
    return nettoyer(donnees)[0], ""


def charger(chemin=None):
    """Liste des favoris ; vide si le fichier n'existe pas encore."""
    return lire(chemin)[0]


def enregistrer(favoris, chemin=None):
    """Écrit la liste sur disque : None si tout va bien, sinon le message
    d'erreur à présenter.

    L'écriture passe par un fichier provisoire, renommé ensuite : une coupure
    en cours d'écriture ne laisse jamais un fichier tronqué. Un fichier que
    l'on n'a pas su relire n'est jamais écrasé — une retouche manuelle
    maladroite ne doit pas coûter tous les favoris : il est mis de côté sous
    un nom horodaté.
    """
    chemin = chemin or FICHIER_FAVORIS
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        if lire(chemin)[1]:
            os.replace(chemin, "%s.illisible-%s" % (
                chemin, datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
        provisoire = chemin + ".tmp"
        with open(provisoire, "w", encoding="utf-8") as f:
            json.dump(favoris, f, ensure_ascii=False, indent=2)
        os.replace(provisoire, chemin)
    except OSError as err:
        return "Enregistrement des favoris impossible (%s)." % err
    return None


def trouver(favoris, nomenclature, code):
    return next((f for f in favoris if f["nomenclature"] == nomenclature
                 and f["code"] == code), None)


def ajouter(nomenclature, code, nom="", commentaire="", ajoute_le="",
            chemin=None):
    """Ajoute l'acte s'il n'est pas déjà favori. None ou message d'erreur."""
    favoris = charger(chemin)
    if trouver(favoris, nomenclature, code):
        return None
    favoris.append({
        "nomenclature": nomenclature,
        "code": code,
        "nom": _texte(nom),
        "commentaire": _texte(commentaire),
        "ajoute_le": ajoute_le or datetime.date.today().isoformat(),
    })
    return enregistrer(favoris, chemin)


def retirer(nomenclature, code, chemin=None):
    """Retire un favori. Renvoie (favori retiré ou None, erreur ou None)."""
    favoris = charger(chemin)
    retire = trouver(favoris, nomenclature, code)
    if retire is None:
        return None, None
    restants = [f for f in favoris if f is not retire]
    return retire, enregistrer(restants, chemin)


def modifier(nomenclature, code, nom, commentaire, chemin=None):
    """Change le nom et le commentaire d'un favori. None ou message d'erreur."""
    favoris = charger(chemin)
    favori = trouver(favoris, nomenclature, code)
    if favori is None:
        return ("Ce favori n'existe plus : il a sans doute été retiré depuis "
                "un autre onglet du navigateur.")
    favori["nom"], favori["commentaire"] = _texte(nom), _texte(commentaire)
    return enregistrer(favoris, chemin)


def appliquer(modifications, retraits, chemin=None):
    """Modification en série depuis la page Favoris.

    ``modifications`` : clé -> (nom, commentaire) ; ``retraits`` : clés des
    favoris à retirer. Renvoie (favoris retirés, erreur ou None).
    """
    gardes, retires = [], []
    for f in charger(chemin):
        k = cle(f["nomenclature"], f["code"])
        if k in retraits:
            retires.append(f)
            continue
        if k in modifications:
            f["nom"], f["commentaire"] = (_texte(v) for v in modifications[k])
        gardes.append(f)
    return retires, enregistrer(gardes, chemin)


def fusionner(importes, chemin=None):
    """Ajoute les favoris importés qui manquent.

    Un favori déjà présent garde son nom et son commentaire : l'import
    n'écrase jamais une annotation existante. Renvoie (nombre d'ajouts,
    erreur ou None).
    """
    favoris = charger(chemin)
    connus = {cle(f["nomenclature"], f["code"]) for f in favoris}
    ajouts = [dict(f) for f in importes
              if cle(f["nomenclature"], f["code"]) not in connus]
    if not ajouts:
        return 0, None
    for f in ajouts:
        f["ajoute_le"] = f["ajoute_le"] or datetime.date.today().isoformat()
    return len(ajouts), enregistrer(favoris + ajouts, chemin)


def filtrer(favoris, requete="", nomenclature="", libelle=None):
    """Favoris de la nomenclature demandée qui contiennent tous les mots saisis.

    Les mots sont cherchés dans le code (avec ou sans le « + » du CSARR), le
    nom, le libellé officiel et le commentaire, accents et majuscules ignorés
    — comme dans la recherche d'actes.
    """
    mots = sd.normaliser(requete).split()
    retenus = []
    for f in favoris:
        if nomenclature and f["nomenclature"] != nomenclature:
            continue
        if mots:
            texte = " ".join((
                sd.normaliser(f["code"]), f["code"].lower().replace("+", ""),
                sd.normaliser(f["nom"]),
                sd.normaliser(libelle(f) if libelle else ""),
                sd.normaliser(f["commentaire"])))
            if not all(m in texte for m in mots):
                continue
        retenus.append(f)
    return retenus


def _date(iso):
    try:
        return datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def _date_fr(iso):
    jour = _date(iso)
    return jour.strftime("%d/%m/%Y") if jour else ""


# ---------------------------------------------------------------------------
# Étoile des fiches d'acte
# ---------------------------------------------------------------------------

AIDE_STOCKAGE = (
    "Les favoris sont enregistrés sur ce poste, dans `%s`, hors du dossier "
    "de l'application : ils survivent à son remplacement par une nouvelle "
    "version." % FICHIER_FAVORIS)


def _message(texte):
    """Confirmation affichée en toast au run suivant (voir app.main)."""
    st.session_state["message_favoris"] = texte


def _retires():
    """Favoris retirés pendant la session, par clé.

    Un retrait se fait d'un clic : le rattraper doit en coûter un seul aussi.
    Rajouter l'acte aux favoris lui rend son nom, son commentaire et sa date.
    """
    return st.session_state.setdefault("favoris_retires", {})


def _ajout(nomenclature, code):
    k = cle(nomenclature, code)
    ancien = _retires().pop(k, None) or {}
    erreur = ajouter(nomenclature, code, ancien.get("nom", ""),
                     ancien.get("commentaire", ""), ancien.get("ajoute_le", ""))
    if erreur:
        if ancien:
            _retires()[k] = ancien
        st.error(erreur)
        return
    rendus = [quoi for quoi, valeur in (("son nom", ancien.get("nom")),
                                        ("son commentaire",
                                         ancien.get("commentaire")))
              if valeur]
    _message("%s ajouté aux favoris%s." % (
        code, " avec " + " et ".join(rendus) if rendus else ""))
    st.rerun()


def _retrait(nomenclature, code):
    retire, erreur = retirer(nomenclature, code)
    if erreur:
        st.error(erreur)
        return
    if retire is not None:
        _retires()[cle(nomenclature, code)] = retire
    annote = retire is not None and (retire["nom"] or retire["commentaire"])
    _message("%s retiré des favoris.%s" % (
        code, " « ☆ Ajouter aux favoris » le rétablit avec son nom et son "
              "commentaire." if annote else ""))
    st.rerun()


def etoile(nomenclature, code, libelle, espace):
    """Ajout aux favoris depuis la fiche d'un acte, avec nom et commentaire.

    ``espace`` distingue les clés : la fiche d'un même acte peut être rendue
    dans plusieurs onglets au cours d'un même run.
    """
    base = "%s_fav_%s_%s" % (espace, nomenclature, code)
    favori = trouver(charger(), nomenclature, code)
    gauche, droite = st.columns([2, 5], vertical_alignment="center")

    if favori is None:
        if gauche.button("☆ Ajouter aux favoris", key=base, width="stretch",
                         help=AIDE_STOCKAGE):
            _ajout(nomenclature, code)
        return

    if gauche.button("★ Retirer des favoris", key=base, width="stretch",
                     help="Le nom et le commentaire sont retrouvés si vous "
                          "rajoutez l'acte aux favoris pendant la session."):
        _retrait(nomenclature, code)
    with droite:
        date = _date_fr(favori["ajoute_le"])
        st.caption("★ Favori%s%s" % (
            " « **%s** »" % favori["nom"] if favori["nom"] else "",
            " · ajouté le %s" % date if date else ""))
        if favori["commentaire"]:
            # Saut de ligne Markdown explicite : le commentaire garde sa mise
            # en forme, ligne à ligne.
            st.caption(favori["commentaire"].replace("\n", "  \n"))

    # Les champs sont recréés dès que le favori change, où que ce soit : sans
    # quoi un champ resté affiché dans un autre onglet garderait l'ancienne
    # valeur, et l'enregistrerait de nouveau au prochain clic.
    version = "%x" % zlib.crc32(("%s\x00%s" % (
        favori["nom"], favori["commentaire"])).encode("utf-8"))
    with st.expander("✏️ Nom et commentaire du favori",
                     expanded=not (favori["nom"] or favori["commentaire"])):
        with st.form("%s_form_%s" % (base, version), border=False):
            nom = st.text_input(
                "Nom", value=favori["nom"], key="%s_nom_%s" % (base, version),
                max_chars=120, placeholder=str(libelle)[:80],
                help="Intitulé libre, repris dans la page Favoris. Laissé "
                     "vide, le libellé officiel en tient lieu.")
            commentaire = st.text_area(
                "Commentaire", value=favori["commentaire"],
                key="%s_com_%s" % (base, version), height=100,
                placeholder="Ex. : toujours avec QM le mardi ; à coder par "
                            "l'enseignant en APA ; vu en réunion DIM du "
                            "12/11…")
            if st.form_submit_button("💾 Enregistrer", type="primary"):
                erreur = modifier(nomenclature, code, nom, commentaire)
                if erreur:
                    st.error(erreur)
                else:
                    _message("Favori %s enregistré." % code)
                    st.rerun()


# ---------------------------------------------------------------------------
# Page « Favoris »
# ---------------------------------------------------------------------------

def _libelles(d):
    """Fonction favori -> libellé officiel, vide si l'acte n'est plus chargé."""
    tables = {"csarr": d.get("lib_csarr", {}), "csar": d.get("lib_csar", {}),
              "ccam": d.get("lib_ccam", {})}
    return lambda f: tables.get(f["nomenclature"], {}).get(f["code"], "")


def _empreinte(texte):
    return "%x" % zlib.crc32(texte.encode("utf-8"))


def page(d):
    st.header("⭐ Favoris")
    st.caption(
        "Vos actes de prédilection — CSARR, CSAR et CCAM pondérés —, avec un "
        "nom et un commentaire libres. Cliquez sur une ligne pour ouvrir la "
        "fiche de l'acte : le composeur y est, l'acte rejoint le panier sans "
        "repasser par la recherche.")

    favoris, alerte = lire()
    if alerte:
        st.warning(alerte + " Il sera mis de côté, et non écrasé, au prochain "
                   "enregistrement d'un favori.")
    libelle = _libelles(d)

    visibles = []
    if not favoris:
        st.info(
            "Aucun favori pour l'instant. Sur la fiche d'un acte — pages de "
            "recherche CSARR et CSAR, onglet « Actes spécialisés par GN » — "
            "cliquez sur **☆ Ajouter aux favoris** : vous pourrez ensuite lui "
            "donner un nom et un commentaire.")
    else:
        visibles = _liste(d, favoris, libelle)

    actif = _fiche_choisie(favoris, visibles, libelle)
    _modification_en_serie(visibles)
    _echanges(favoris)
    if actif:
        st.divider()
        _fiche(d, *actif.split("|", 1))


def _liste(d, favoris, libelle):
    """Filtres et tableau cliquable ; renvoie les favoris affichés."""
    comptes = {n: sum(1 for f in favoris if f["nomenclature"] == n)
               for n in NOMENCLATURES}
    # Rangée souple plutôt que colonnes fixes : quand la place manque, le
    # choix de nomenclature passe sous le champ au lieu d'être tronqué.
    with st.container(horizontal=True, vertical_alignment="bottom"):
        requete = etat.texte(
            "favoris.filtre", "Filtrer les favoris", type="search", live=True,
            placeholder="Ex. : bilan, GLR, 07S, balnéo",
            help="Tous les mots saisis doivent figurer dans le code, le nom, "
                 "le libellé officiel ou le commentaire ; accents et "
                 "majuscules sont ignorés.")
        nomenclature = etat.segments(
            "favoris.nomenclature", "Nomenclature",
            [""] + [n for n in NOMENCLATURES if comptes[n]],
            format_func=lambda n: "Toutes (%d)" % len(favoris) if not n
            else "%s (%d)" % (NOMENCLATURES[n], comptes[n]))

    visibles = filtrer(favoris, requete, nomenclature, libelle)
    if not visibles:
        st.info("Aucun favori ne correspond à ce filtre.")
        return visibles
    st.caption("**%d** favori(s)%s" % (
        len(visibles), " sur %d" % len(favoris)
        if len(visibles) < len(favoris) else ""))

    cible = dict(zip(d["csarr_actes"]["code"], d["csarr_actes"]["csar_cible"]))
    tableau = pd.DataFrame([{
        "Nomenclature": NOMENCLATURES[f["nomenclature"]],
        "Code": f["code"],
        "Nom": f["nom"],
        "Libellé officiel": libelle(f) or "⚠️ absent de la version chargée",
        "Commentaire": f["commentaire"],
        "→ CSAR": cible.get(f["code"], "") if f["nomenclature"] == "csarr"
        else "",
        "Ajouté le": _date(f["ajoute_le"]),
    } for f in visibles])
    if not any(f["nomenclature"] == "csarr" for f in visibles):
        tableau = tableau.drop(columns="→ CSAR")

    # La sélection renvoyée est un rang : la clé suit la liste affichée, si
    # bien qu'un filtre ou un retrait remet la sélection à zéro au lieu de la
    # laisser désigner un autre favori. L'acte ouvert, lui, est retenu par le
    # magasin.
    evenement = st.dataframe(
        tableau, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-cell",
        height=min(38 + 35 * len(tableau), 430),
        key="fav_tableau_%s" % _empreinte("\n".join(
            cle(f["nomenclature"], f["code"]) for f in visibles)),
        alt="Favoris affichés, un acte par ligne",
        column_config={
            "Nomenclature": st.column_config.TextColumn(width="small"),
            "Code": st.column_config.TextColumn(width="small",
                                                help=sd.AIDE["Code"]),
            "Nom": st.column_config.TextColumn(width="medium"),
            "Libellé officiel": st.column_config.TextColumn(width="large"),
            "Commentaire": st.column_config.TextColumn(width="large"),
            "→ CSAR": st.column_config.TextColumn(
                width="small",
                help="Acte CSAR suggéré par la table d'aide au codage, pour "
                     "le codage à partir du 1er janvier 2027."),
            "Ajouté le": st.column_config.DateColumn(format="DD/MM/YYYY",
                                                     width="small"),
        })
    cellules = (evenement.selection.get("cells") or []) if evenement else []
    if cellules and cellules[0][0] < len(visibles):
        f = visibles[cellules[0][0]]
        etat.ecrire("favoris.actif", cle(f["nomenclature"], f["code"]))
    return visibles


def _fiche_choisie(favoris, visibles, libelle):
    """Clé du favori dont la fiche est ouverte, ou None.

    L'acte que l'on vient de retirer d'un clic reste affiché : sa fiche porte
    l'étoile qui le rétablit. Sauf s'il est absent de la version chargée —
    il n'a alors pas de fiche, donc pas d'étoile.
    """
    actif = etat.lire("favoris.actif", "")
    if actif in {cle(f["nomenclature"], f["code"]) for f in visibles}:
        return actif
    retire = _retires().get(actif)
    if retire is not None and libelle(retire) and not any(
            cle(f["nomenclature"], f["code"]) == actif for f in favoris):
        st.warning(
            "**%s** vient d'être retiré de vos favoris. **☆ Ajouter aux "
            "favoris**, sur sa fiche ci-dessous, le rétablit avec son nom et "
            "son commentaire." % actif.split("|", 1)[1])
        return actif
    if visibles:
        st.caption("👆 Cliquez sur une ligne pour afficher la fiche de l'acte, "
                   "composer sa zone d'acte, ou changer son nom et son "
                   "commentaire.")
    return None


def _fiche(d, nomenclature, code):
    # fiches importe favoris pour son étoile : l'import est local pour ne pas
    # boucler.
    import fiches

    if nomenclature == "ccam":
        if code in d.get("lib_ccam", {}):
            fiches.fiche_ccam(d, code, espace=ESPACE_FICHE)
            return
        ligne = None
    else:
        table = d["csarr_actes"] if nomenclature == "csarr" else d["csar_actes"]
        trouve = table[table["code"] == code]
        ligne = None if trouve.empty else trouve.iloc[0]

    if ligne is None:
        st.warning(
            "L'acte **%s** ne figure pas dans la version %s chargée : il a pu "
            "être supprimé depuis son ajout aux favoris."
            % (code, NOMENCLATURES.get(nomenclature, nomenclature.upper())))
        if trouver(charger(), nomenclature, code) and st.button(
                "★ Retirer des favoris",
                key="%s_absent_%s_%s" % (ESPACE_FICHE, nomenclature, code)):
            _retrait(nomenclature, code)
        return

    sd.historiser(code, nomenclature)
    if nomenclature == "csarr":
        fiches.fiche_csarr(d, ligne, espace=ESPACE_FICHE)
    else:
        fiches.fiche_csar(d, ligne, espace=ESPACE_FICHE)


def _modification_en_serie(visibles):
    if not visibles:
        return
    with st.expander("✏️ Modifier en série : nom, commentaire, retrait"):
        st.caption(
            "Modifiez directement les colonnes **Nom** et **Commentaire**, "
            "cochez **Retirer** pour supprimer un favori, puis enregistrez. "
            "Seuls les favoris affichés — filtre compris — sont concernés.")
        edition = pd.DataFrame([{
            "Nomenclature": NOMENCLATURES[f["nomenclature"]],
            "Code": f["code"], "Nom": f["nom"],
            "Commentaire": f["commentaire"], "Retirer": False,
        } for f in visibles])
        # Clé dépendante du contenu : après un enregistrement, l'éditeur
        # repart des valeurs enregistrées au lieu de rejouer ses modifications.
        edite = st.data_editor(
            edition, width="stretch", hide_index=True, num_rows="fixed",
            key="fav_editeur_%s" % _empreinte(json.dumps(
                visibles, ensure_ascii=False, sort_keys=True)),
            disabled=["Nomenclature", "Code"],
            alt="Nom, commentaire et retrait des favoris affichés",
            column_config={
                "Nomenclature": st.column_config.TextColumn(width="small"),
                "Code": st.column_config.TextColumn(width="small"),
                "Nom": st.column_config.TextColumn(width="medium",
                                                   max_chars=120),
                "Commentaire": st.column_config.TextColumn(width="large"),
                "Retirer": st.column_config.CheckboxColumn(width="small"),
            })
        if not st.button("💾 Enregistrer les modifications", key="fav_serie",
                         type="primary"):
            return
        modifications, retraits = {}, set()
        for i, f in enumerate(visibles):
            ligne = edite.loc[i]
            k = cle(f["nomenclature"], f["code"])
            if bool(ligne["Retirer"]):
                retraits.add(k)
                continue
            nom, commentaire = _texte(ligne["Nom"]), _texte(ligne["Commentaire"])
            if (nom, commentaire) != (f["nom"], f["commentaire"]):
                modifications[k] = (nom, commentaire)
        if not modifications and not retraits:
            st.info("Aucune modification à enregistrer.")
            return
        retires, erreur = appliquer(modifications, retraits)
        if erreur:
            st.error(erreur)
            return
        for f in retires:
            _retires()[cle(f["nomenclature"], f["code"])] = f
        bilan = []
        if modifications:
            bilan.append("%d favori(s) modifié(s)" % len(modifications))
        if retires:
            bilan.append("%d retiré(s)" % len(retires))
        _message(", ".join(bilan) + ".")
        st.rerun()


def _echanges(favoris):
    """Export et import JSON : sauvegarde, passage d'un poste à l'autre."""
    with st.expander("📤 Exporter / importer — autre poste, sauvegarde"):
        st.caption(
            "Vos favoris sont enregistrés dans `%s`, en dehors du dossier de "
            "l'application : ils survivent donc à son remplacement par une "
            "nouvelle version. Pour les retrouver sur un autre poste, "
            "exportez-les puis importez le fichier obtenu." % FICHIER_FAVORIS)
        if favoris:
            st.download_button(
                "⬇️ Exporter mes favoris (JSON)", key="fav_export",
                data=json.dumps(favoris, ensure_ascii=False, indent=2),
                file_name="favoris_smr.json", mime="application/json",
                on_click="ignore")

        # Le dépôt change de clé après une fusion : le fichier importé quitte
        # l'écran au lieu d'inviter à le fusionner une seconde fois.
        generation = st.session_state.get("fav_import_generation", 0)
        depot = st.file_uploader("⬆️ Importer un fichier de favoris",
                                 type=["json"],
                                 key="fav_import_%d" % generation)
        if depot is None:
            return
        try:
            importes, ecartes = nettoyer(
                json.loads(depot.getvalue().decode("utf-8")))
        except ValueError:
            st.error("Fichier illisible : un export JSON de la page Favoris "
                     "est attendu.")
            return
        if not importes:
            st.warning("Aucun favori reconnaissable dans ce fichier.")
            return
        nouveaux = [f for f in importes
                    if not trouver(favoris, f["nomenclature"], f["code"])]
        st.caption("%d favori(s) lisible(s) dans ce fichier, dont %d "
                   "nouveau(x)%s." % (
                       len(importes), len(nouveaux),
                       " ; %d entrée(s) écartée(s) : code non reconnu ou "
                       "doublon" % ecartes if ecartes else ""))
        if st.button("Fusionner avec mes favoris", key="fav_fusion",
                     disabled=not nouveaux,
                     help="Ajoute les favoris absents. Un favori déjà présent "
                          "garde son nom et son commentaire."):
            ajouts, erreur = fusionner(importes)
            if erreur:
                st.error(erreur)
                return
            st.session_state["fav_import_generation"] = generation + 1
            _message("%d favori(s) importé(s)." % ajouts)
            st.rerun()
