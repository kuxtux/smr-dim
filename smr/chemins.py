# -*- coding: utf-8 -*-
"""
PMSI SMR — emplacements des fichiers, définis en un seul endroit.

Trois familles de chemins :

- le dossier du projet : ``sources/``, où l'utilisateur dépose les fichiers de
  l'ATIH, et ``data/``, où la base est construite ;
- le code : le dictionnaire des synonymes livré avec l'outil ;
- le dossier personnel ``~/.dim``, commun aux outils du DIM, qui survit au
  remplacement du dossier de l'application : favoris et synonymes personnels.
"""

import os

# Le paquet smr/ est un sous-dossier de la racine du projet.
DOSSIER_CODE = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(DOSSIER_CODE)

DOSSIER_SOURCES = os.path.join(RACINE, "sources")
DOSSIER_DATA = os.path.join(RACINE, "data")
BASE_SQLITE = os.path.join(DOSSIER_DATA, "smr.sqlite")

FICHIER_SYNONYMES = os.path.join(DOSSIER_CODE, "synonymes",
                                 "synonymes_csar.txt")

# Dossier personnel commun aux outils du DIM : chacun y range ses fichiers sous
# un nom préfixé par l'outil, plutôt que de créer son propre dossier.
DOSSIER_PERSO = os.path.join(os.path.expanduser("~"), ".dim")
FICHIER_FAVORIS = os.path.join(DOSSIER_PERSO, "smr_favoris.json")
FICHIER_SYNONYMES_PERSO = os.path.join(DOSSIER_PERSO,
                                       "smr_synonymes_csar.txt")


def relatif(chemin):
    """Chemin à afficher, relatif à la racine du projet : smr/synonymes/…"""
    return os.path.relpath(chemin, RACINE).replace(os.sep, "/")
