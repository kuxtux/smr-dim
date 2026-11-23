# -*- coding: utf-8 -*-
"""
PMSI SMR — dictionnaire des synonymes de la recherche d'actes CSAR.

Le CSAR a son vocabulaire : il dit « réadaptation » là où l'on cherche
« rééducation », « évaluation » pour « bilan », « squelette axial » pour
« rachis ». Une recherche par mots du libellé échoue donc sur le premier terme
d'usage courant. Le dictionnaire fait le pont : à chaque terme saisi, il
associe le ou les termes du catalogue à chercher À SA PLACE — ou plutôt EN
PLUS, le mot saisi restant toujours cherché tel quel.

Deux fichiers texte, lus à chaque recherche (une modification prend effet
sans relancer l'application ni reconstruire la base) :

- ``synonymes_csar.txt``, livré avec l'outil et remplacé à chaque mise à jour ;
- ``~/.dim/smr_synonymes_csar.txt``, personnel et facultatif, qui s'y ajoute.
  Rangé hors du dossier du projet, comme les favoris, il survit au
  remplacement complet de l'application.

Une ligne par entrée ::

    terme saisi, autre terme saisi = terme du catalogue | autre possibilité

À gauche du signe égal, les termes que l'on tape, séparés par des virgules ; à
droite, ce qu'il faut chercher dans le catalogue. La barre verticale sépare
plusieurs possibilités : une seule suffit. Dans une possibilité de plusieurs
mots, tous doivent être présents. Accents et majuscules sont ignorés ; ce qui
suit un # est un commentaire. Le terme de droite peut être un code d'acte.

Ce module ne dépend pas de Streamlit : il se teste seul.
"""

import os
import re

from smr_build import RACINE, normaliser

FICHIER = os.path.join(RACINE, "synonymes_csar.txt")
# Même dossier personnel que les favoris, commun aux outils du DIM.
FICHIER_PERSO = os.path.join(os.path.expanduser("~"), ".dim",
                             "smr_synonymes_csar.txt")

# Petits mots sans valeur de recherche. Les exiger fait échouer « rééducation
# du périnée » sur un libellé qui écrit « des fonctions périnéales ». « avec »
# et « sans » n'y figurent pas : ils départagent des actes (01E02 / 01E08).
MOTS_VIDES = frozenset(
    "a au aux d de des du en et l la le les ou un une".split())

# Longueur minimale d'un mot saisi pour valoir début d'un terme du
# dictionnaire : « reeduc » retrouve « rééducation ». En dessous, « mi » ou
# « art » ramèneraient la moitié du dictionnaire.
PREFIXE_MIN = 4

# Jusqu'à cette longueur, un mot saisi qui figure tel quel au dictionnaire est
# une abréviation (MS, MI, FRE) : on ne le cherche plus comme morceau de mot,
# « mi » se trouvant dans « mise à disposition » et « minimal ».
ABREVIATION_MAX = 3


def mots_utiles(texte):
    """Mots normalisés d'un texte, petits mots écartés.

    Un texte fait uniquement de petits mots les garde : on ne transforme pas
    une requête en requête vide.
    """
    mots = normaliser(texte).split()
    return [m for m in mots if m not in MOTS_VIDES] or mots


# ---------------------------------------------------------------------------
# Lecture des fichiers
# ---------------------------------------------------------------------------

def analyser(texte, origine=""):
    """Texte d'un fichier de synonymes -> (entrées, anomalies).

    Une entrée : ``{"saisis": [...], "cibles": [...], "origine", "ligne"}``,
    les termes étant gardés tels qu'écrits pour l'affichage. Une ligne mal
    formée n'arrête rien : elle est signalée, avec son numéro, et ignorée.
    """
    entrees, anomalies = [], []
    for numero, brut in enumerate(str(texte).splitlines(), 1):
        ligne = brut.split("#", 1)[0].strip()
        if not ligne:
            continue
        if ligne.count("=") != 1:
            anomalies.append((origine, numero, brut.strip(),
                              "un seul signe = est attendu"))
            continue
        gauche, droite = ligne.split("=")
        saisis = [t.strip() for t in gauche.split(",") if normaliser(t)]
        cibles = [t.strip() for t in droite.split("|") if normaliser(t)]
        if not saisis or not cibles:
            anomalies.append((origine, numero, brut.strip(),
                              "il manque un terme d'un côté du signe ="))
            continue
        entrees.append({"saisis": saisis, "cibles": cibles,
                        "origine": origine, "ligne": numero})
    return entrees, anomalies


def lire_fichier(chemin, origine=""):
    """(entrées, anomalies) d'un fichier ; vides s'il n'existe pas."""
    try:
        with open(chemin, encoding="utf-8-sig") as f:
            texte = f.read()
    except FileNotFoundError:
        return [], []
    except (OSError, UnicodeDecodeError) as err:
        return [], [(origine, 0, os.path.basename(chemin),
                     "fichier illisible (%s)" % err)]
    return analyser(texte, origine)


class Dictionnaire:
    """Entrées indexées par terme saisi, pour développer une requête."""

    def __init__(self, entrees=(), anomalies=()):
        self.entrees = list(entrees)
        self.anomalies = list(anomalies)
        # (mots du terme saisi) -> [(mots cherchés, terme tel qu'écrit), ...]
        self.index = {}
        for e in self.entrees:
            cibles = [(tuple(mots_utiles(c)), c) for c in e["cibles"]]
            for saisi in e["saisis"]:
                connues = self.index.setdefault(tuple(mots_utiles(saisi)), [])
                connues.extend(c for c in cibles if c not in connues)
        self.longueur_max = max((len(k) for k in self.index), default=1)

    def __len__(self):
        return len(self.entrees)

    def chercher(self, mots):
        """Possibilités associées à une suite de mots saisis.

        -> (possibilités, exact). Le terme est cherché tel quel, puis au
        singulier, enfin comme début d'un terme du dictionnaire. ``exact``
        est faux dans ce dernier cas.
        """
        mots = tuple(mots)
        if mots in self.index:
            return self.index[mots], True
        singulier = tuple(m[:-1] if len(m) > PREFIXE_MIN and m[-1] in "sx"
                          else m for m in mots)
        if singulier in self.index:
            return self.index[singulier], True
        trouvees = []
        for cle, cibles in self.index.items():
            if len(cle) == len(mots) and all(
                    c == m or (len(m) >= PREFIXE_MIN and c.startswith(m))
                    for c, m in zip(cle, mots)):
                trouvees.extend(c for c in cibles if c not in trouvees)
        return trouvees, False


_CACHE = {}


def _empreinte(chemin):
    try:
        etat = os.stat(chemin)
    except OSError:
        return None
    return (etat.st_mtime_ns, etat.st_size)


def charger(fichier=None, perso=None):
    """Dictionnaire courant, relu seulement si l'un des fichiers a changé."""
    fichier = fichier or FICHIER
    perso = perso or FICHIER_PERSO
    cle = (fichier, _empreinte(fichier), perso, _empreinte(perso))
    if _CACHE.get("cle") != cle:
        e1, a1 = lire_fichier(fichier, "outil")
        e2, a2 = lire_fichier(perso, "personnel")
        _CACHE["cle"] = cle
        _CACHE["dictionnaire"] = Dictionnaire(e1 + e2, a1 + a2)
    return _CACHE["dictionnaire"]


# ---------------------------------------------------------------------------
# Développement d'une requête
# ---------------------------------------------------------------------------

def developper(requete, dictionnaire=None):
    """Découpe une requête en unités de recherche, synonymes compris.

    Chaque unité est un dict :

    - ``saisi`` : le ou les mots tapés ;
    - ``mots`` : ces mots, à trouver tels quels dans le texte ;
    - ``entier`` : vrai s'ils doivent l'être en mots entiers (abréviation) ;
    - ``cibles`` : [(mots, terme tel qu'écrit)], les synonymes du catalogue.

    Un acte répond à une unité s'il contient les mots saisis OU l'une des
    cibles ; il répond à la requête s'il répond à toutes ses unités. Les
    termes de plusieurs mots du dictionnaire (« kiné respi ») sont reconnus
    en priorité sur leurs mots pris un à un.
    """
    dico = charger() if dictionnaire is None else dictionnaire
    mots = mots_utiles(requete)
    unites, i = [], 0
    while i < len(mots):
        for n in range(min(dico.longueur_max, len(mots) - i), 0, -1):
            fenetre = mots[i:i + n]
            cibles, exact = dico.chercher(fenetre)
            if cibles or n == 1:
                unites.append({
                    "saisi": " ".join(fenetre),
                    "mots": list(fenetre),
                    "entier": bool(cibles) and exact and n == 1
                    and len(fenetre[0]) <= ABREVIATION_MAX,
                    "cibles": list(cibles),
                })
                i += n
                break
    return unites


def motif_entier(mot):
    """Expression rationnelle d'un mot à trouver en entier."""
    return r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(mot)
