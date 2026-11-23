# -*- coding: utf-8 -*-
"""
PMSI SMR — magasin de session : la saisie de l'utilisateur survit à la navigation.

Streamlit purge l'état d'un widget dès qu'un run se termine sans que ce widget
ait été instancié : changer de page suffit à perdre une saisie. La parade
consiste à ne jamais traiter la clé du widget comme la source de vérité.

Les données vivent ici, dans ``st.session_state[DOSSIER]``, sous des clés qui
n'appartiennent à aucun widget et que Streamlit ne purge donc jamais. Chaque
widget n'est qu'une vue : il est réamorcé à chaque run depuis le magasin, et il
y réécrit par un rappel ``on_change``. On peut naviguer librement, la saisie
reste.

Le magasin porte le « dossier de travail » courant :

    {
      "actes":   [ {...}, ... ],   panier d'actes collectés (CSARR et/ou CSAR)
      "gme":     { ... },          variables du futur générateur de GME
      "_compteur": n,              pour attribuer un identifiant stable
    }
"""

import streamlit as st

DOSSIER = "dossier_smr"
PREFIXE = "w_"


# ---------------------------------------------------------------------------
# Accès au magasin
# ---------------------------------------------------------------------------

def dossier():
    """Le dossier de travail courant, créé au besoin."""
    if DOSSIER not in st.session_state:
        st.session_state[DOSSIER] = {"actes": [], "gme": {}, "_compteur": 0}
    return st.session_state[DOSSIER]


def _naviguer(chemin, creer=False):
    """Résout un chemin pointé ('gme.age') en (conteneur, dernière clé)."""
    noeud = dossier()
    morceaux = chemin.split(".")
    for m in morceaux[:-1]:
        if m not in noeud or not isinstance(noeud[m], dict):
            if not creer:
                return None, morceaux[-1]
            noeud[m] = {}
        noeud = noeud[m]
    return noeud, morceaux[-1]


def lire(chemin, defaut=None):
    conteneur, cle = _naviguer(chemin)
    if conteneur is None:
        return defaut
    valeur = conteneur.get(cle, defaut)
    return defaut if valeur is None else valeur


def ecrire(chemin, valeur):
    conteneur, cle = _naviguer(chemin, creer=True)
    conteneur[cle] = valeur


def _cle_base(chemin):
    return PREFIXE + chemin.replace(".", "_")


def cle_widget(chemin):
    """Clé du widget, renouvelée à chaque resynchronisation.

    Vider la clé ne suffit pas pour un champ de saisie : le navigateur garde
    la valeur qu'il affiche et la renvoie à la première interaction suivante,
    écrasant alors celle que le programme venait d'imposer. On voyait la fiche
    d'un acte pendant que le champ de recherche affichait encore le précédent,
    puis le moindre clic ramenait à ce précédent. Changer de clé crée un
    widget neuf, que le navigateur ne peut pas contredire.
    """
    generation = dossier().get("_generations", {}).get(chemin, 0)
    base = _cle_base(chemin)
    return base if not generation else "%s__g%d" % (base, generation)


def resynchroniser(chemin):
    """Force le widget à se réamorcer depuis le magasin au prochain run.

    À n'appeler que dans un rappel de bouton ou avant l'instanciation du
    widget : Streamlit refuse qu'on touche à la clé d'un widget déjà rendu.
    """
    st.session_state.pop(cle_widget(chemin), None)
    generations = dossier().setdefault("_generations", {})
    generations[chemin] = generations.get(chemin, 0) + 1


def vider(chemin):
    conteneur, cle = _naviguer(chemin)
    if conteneur is not None:
        conteneur.pop(cle, None)
    resynchroniser(chemin)


def vider_sous_arbre(chemin):
    """Efface une branche du magasin et les clés de widgets qui s'y rattachent.

    À n'appeler qu'AVANT le rendu des widgets concernés : Streamlit refuse
    qu'on touche à la clé d'un widget déjà instancié dans le run en cours.
    """
    conteneur, cle = _naviguer(chemin)
    noeud = conteneur.get(cle) if conteneur is not None else None
    # Chaque champ est resynchronisé un par un : vider sa clé ne suffit pas,
    # il faut lui en donner une neuve pour que le navigateur cesse de renvoyer
    # la valeur qu'il affiche encore.
    if isinstance(noeud, dict):
        for enfant in list(noeud):
            resynchroniser("%s.%s" % (chemin, enfant))
    if conteneur is not None:
        conteneur.pop(cle, None)
    # Filet, pour les clés orphelines du sous-arbre.
    prefixe = _cle_base(chemin) + "_"
    for k in [k for k in st.session_state if str(k).startswith(prefixe)]:
        st.session_state.pop(k, None)
    resynchroniser(chemin)


# ---------------------------------------------------------------------------
# Widgets liés au magasin
# ---------------------------------------------------------------------------

def _lier(chemin, fabrique, libelle, defaut, nom_valeur, **kw):
    """Instancie un widget dont la valeur est portée par le magasin.

    Le magasin amorce le widget (``value=``) et le rappel ``on_change`` y
    réécrit. On resynchronise aussi après le rendu : le magasin reste juste
    même si le rappel n'a pas été déclenché (premier rendu, valeur imposée).
    """
    cle = cle_widget(chemin)

    def _sauver():
        ecrire(chemin, st.session_state[cle])

    kw[nom_valeur] = lire(chemin, defaut)
    valeur = fabrique(libelle, key=cle, on_change=_sauver, **kw)
    ecrire(chemin, valeur)
    return valeur


def texte(chemin, libelle, defaut="", **kw):
    return _lier(chemin, st.text_input, libelle, defaut, "value", **kw)


def zone_texte(chemin, libelle, defaut="", **kw):
    return _lier(chemin, st.text_area, libelle, defaut, "value", **kw)


def nombre(chemin, libelle, mini, maxi, defaut, **kw):
    """Number input lié au magasin, la valeur étant ramenée dans les bornes.

    Les bornes d'un même champ peuvent changer d'un run à l'autre — le nombre
    de patients d'un acte CSARR dépend de la modalité de réalisation, par
    exemple. Streamlit refuse alors une valeur mémorisée devenue hors bornes ;
    on la ramène plutôt que de laisser l'application s'arrêter. La valeur par
    défaut l'est aussi : une borne haute calculée peut tomber sous elle.
    """
    defaut = min(max(defaut, mini), maxi)
    courant = lire(chemin, None)
    if courant is not None:
        try:
            borne = min(max(type(defaut)(courant), mini), maxi)
        except (TypeError, ValueError):
            borne = defaut
        if borne != courant:
            ecrire(chemin, borne)
            resynchroniser(chemin)
    return _lier(chemin, st.number_input, libelle, defaut, "value",
                 min_value=mini, max_value=maxi, **kw)


def case(chemin, libelle, defaut=False, **kw):
    return _lier(chemin, st.checkbox, libelle, defaut, "value", **kw)


def choix(chemin, libelle, options, defaut=None, widget=st.selectbox, **kw):
    """Selectbox liée au magasin (l'index est recalculé depuis la valeur).

    Les listes d'options dépendent souvent d'un autre choix (les modulateurs
    d'un acte, les GN d'une catégorie majeure). Si la valeur mémorisée n'y
    figure plus, on retombe sur la première option — mais jamais lorsque la
    liste est vide : le magasin serait alors écrasé par un état transitoire.

    ``widget`` accepte aussi ``st.radio``, dont les libellés longs passent à
    la ligne là où une liste déroulante les coupe à sa largeur.
    """
    options = list(options)
    if not options:
        return None
    cle = cle_widget(chemin)
    courant = lire(chemin, defaut if defaut is not None else options[0])

    def _sauver():
        ecrire(chemin, st.session_state[cle])

    index = options.index(courant) if courant in options else 0
    valeur = widget(libelle, options, index=index, key=cle,
                    on_change=_sauver, **kw)
    if valeur != courant:
        ecrire(chemin, valeur)
    return valeur


def onglets(chemin, libelles):
    """Onglets liés au magasin : la page se rouvre sur le dernier consulté.

    Streamlit oublie l'onglet actif dès que la page n'est plus affichée. Un
    rappel l'écrit donc dans le magasin à chaque changement d'onglet, et la
    clé du widget est réamorcée depuis le magasin au retour sur la page. On
    passe par la clé plutôt que par ``default`` : ce paramètre entre dans
    l'identité du widget, qui serait alors recréé à chaque changement
    d'onglet.
    """
    libelles = list(libelles)
    cle = cle_widget(chemin)
    if cle not in st.session_state and lire(chemin) in libelles:
        st.session_state[cle] = lire(chemin)

    def _sauver():
        ecrire(chemin, st.session_state[cle])

    return st.tabs(libelles, key=cle, on_change=_sauver)


def segments(chemin, libelle, options, defaut=None, **kw):
    """Contrôle segmenté lié au magasin, une option restant toujours retenue.

    Même logique que ``choix`` pour une poignée d'options affichées côte à
    côte. Une valeur mémorisée sortie des options retombe sur la première, et
    le widget est alors recréé : Streamlit refuse une valeur par défaut
    absente des options. ``required`` interdit de désélectionner l'option
    affichée, ce qui laisserait le contrôle sans valeur.
    """
    options = list(options)
    if not options:
        return None
    courant = lire(chemin, defaut if defaut is not None else options[0])
    if courant not in options:
        courant = options[0]
        ecrire(chemin, courant)
        resynchroniser(chemin)
    cle = cle_widget(chemin)

    def _sauver():
        ecrire(chemin, st.session_state[cle])

    valeur = st.segmented_control(libelle, options, default=courant,
                                  required=True, key=cle, on_change=_sauver,
                                  **kw)
    if valeur != courant:
        ecrire(chemin, valeur)
    return valeur


def choix_multiple(chemin, libelle, options, defaut=None, **kw):
    options = list(options)
    cle = cle_widget(chemin)
    memorise = lire(chemin, defaut or [])
    courant = [v for v in memorise if v in options]

    def _sauver():
        ecrire(chemin, st.session_state[cle])

    valeur = st.multiselect(libelle, options, default=courant, key=cle,
                            on_change=_sauver, **kw)
    if not options and memorise:
        return memorise
    if list(valeur) != list(memorise):
        ecrire(chemin, list(valeur))
    return valeur


# ---------------------------------------------------------------------------
# Panier d'actes
# ---------------------------------------------------------------------------

def panier():
    return dossier()["actes"]


def ajouter_acte(acte):
    """Ajoute un acte au panier et renvoie son identifiant."""
    d = dossier()
    d["_compteur"] += 1
    acte = dict(acte)
    acte["id"] = d["_compteur"]
    d["actes"].append(acte)
    return acte["id"]


def modifier_acte(identifiant, valeurs):
    """Remplace la composition d'un acte du panier, sans le déplacer.

    On écrit dans le dictionnaire existant plutôt que de le remplacer : l'acte
    garde son identifiant et sa place dans le panier, si bien que corriger le
    3e acte d'une semaine ne le renvoie pas en fin de liste.
    """
    for a in dossier()["actes"]:
        if a.get("id") == identifiant:
            a.clear()
            a.update(valeurs)
            a["id"] = identifiant
            return True
    return False


def retirer_acte(identifiant):
    """Retire un acte du panier, en place.

    On modifie la liste existante plutôt que d'en réaffecter une nouvelle :
    un appelant qui détient déjà la référence renvoyée par ``panier()``
    continuerait sinon de travailler sur une liste morte.
    """
    actes = dossier()["actes"]
    for i, a in enumerate(actes):
        if a.get("id") == identifiant:
            del actes[i]
            return


def vider_panier():
    dossier()["actes"].clear()


def nb_actes():
    return len(dossier()["actes"])


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
