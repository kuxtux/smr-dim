# Fichiers sources de l'ATIH

L'outil construit sa base à partir de fichiers Excel publiés par l'ATIH. Ils ne
sont **pas distribués avec le code** : chacun télécharge les siens sur le site
de l'ATIH et les dépose dans ce dossier, `sources/`.

- **Où les déposer ?** N'importe où dans ce dossier, sous-dossiers compris. Les
  fichiers sont repérés par leur **nom**, cherché dans toute l'arborescence :
  une archive ZIP de l'ATIH se dézippe ici telle quelle, sans rien renommer ni
  ranger. Seul impératif : **garder le nom d'origine** des fichiers.
- **Quand ?** Avant le premier lancement. Tant qu'il manque un fichier
  indispensable, l'outil affiche la liste de ceux qui manquent au lieu de
  démarrer.
- **Et pour une nouvelle version ?** Déposer les nouveaux fichiers, supprimer
  `data/smr.sqlite` et relancer l'outil. Si plusieurs versions d'un même fichier
  coexistent, la plus récemment modifiée est retenue.

Le contenu de ce dossier n'est jamais versionné : Git l'ignore en entier, à
l'exception de ce LISEZMOI.

## Les 17 fichiers lus

Seize fichiers sont **indispensables** ; le dix-septième,
`Transcodage_CSARR_CSAR*.xlsx`, est facultatif. Seul compte le **motif** de la
première colonne, où `*` remplace n'importe quelle suite de caractères (date,
numéro de version) ; la deuxième donne le nom du fichier de la campagne 2026,
pour laquelle l'outil est écrit.

### CSAR — catalogue spécifique des actes de réadaptation, version 2026

| Fichier attendu | Nom en 2026 | Ce que l'outil y lit |
|---|---|---|
| `csar_version_*.xlsx` | `csar_version_2026_20260119.xlsx` | actes CSAR, modulateurs et modalités, intervenants attendus, table d'aide au codage |
| `fichier_associe_csar_*.xlsx` | `fichier_associe_csar_v2026_surligne_270326_0.xlsx` | définitions, fonctions CIF et descriptions des actes |

### CSARR — catalogue spécifique des actes de rééducation et réadaptation, 2026

| Fichier attendu | Nom en 2026 | Ce que l'outil y lit |
|---|---|---|
| `fichier_complementaire_csarr_*.xlsx` | `fichier_complementaire_csarr_2026.xlsx` | actes CSARR, notes, gestes complémentaires, modulateurs, codes supprimés |
| `Transcodage_CSARR_CSAR*.xlsx` | `Transcodage_CSARR_CSAR.xlsx` | commentaires de transcodage — **facultatif** |

### Manuel de groupage des GME 2026 — les tables

Douze classeurs, publiés par l'ATIH avec le manuel des groupes
médico-économiques (GME).

| Fichier attendu | Nom en 2026 | Ce que l'outil y lit |
|---|---|---|
| `CIM_infos_SMR*.xlsx` | `CIM_infos_SMR.xlsx` | CIM-10 à usage SMR : catégories majeures, positions, listes |
| `GN_liste_tests*.xlsx` | `GN_liste_tests.xlsx` | arbres de décision des groupes nosologiques |
| `GR_infos*.xlsx` | `GR_infos.xlsx` | groupes de réadaptation et seuils de score par GN |
| `GL_infos*.xlsx` | `GL_infos.xlsx` | niveaux de lourdeur par groupe de réadaptation |
| `CMA_exclusion*.xlsx` | `CMA_exclusion.xlsx` | exclusions des complications et morbidités associées |
| `CMA_CCAM*.xlsx` | `CMA_CCAM.xlsx` | actes CCAM valant complication à eux seuls |
| `TOTAL_listes_groupes*.xlsx` | `TOTAL_listes_groupes.xlsx` | libellés des CM, GN, GR, GL et GME |
| `ACTES_ponderations_CSARR*.xlsx` | `ACTES_ponderations_CSARR.xlsx` | pondérations CSARR et CCAM, majorations des modulateurs |
| `ACTES_listes_SPE.xlsx` | `ACTES_listes_SPE.xlsx` | actes CSARR et CCAM spécialisés, dictionnaire des 92 GN |
| `ACTES_ponderations_CSAR_transcodage*.xlsx` | `ACTES_ponderations_CSAR_transcodage.xlsx` | pondérations CSAR |
| `ACTES_listes_SPE_CSAR*.xlsx` | `ACTES_listes_SPE_CSAR_transcodage_26012026.xlsx` | actes CSAR spécialisés par regroupement de GN |
| `CSAR_infos*.xlsx` | `CSAR_infos.xlsx` | barème des modulateurs CSAR (temps, lieu) |

`ACTES_listes_SPE.xlsx` est le seul motif sans `*` : le fichier doit porter
exactement ce nom.

### Arrêté tarifaire SMR 2026 — les annexes

| Fichier attendu | Nom en 2026 | Ce que l'outil y lit |
|---|---|---|
| `annexes_arrete_tarifaire_smr_*.xlsx` | `annexes_arrete_tarifaire_smr_2026_0.xlsx` | tarifs des GMT, correspondance GME → GMT, coefficients |

## Ce qui n'est pas nécessaire

Les guides et manuels au format PDF — guide de codage du CSAR, manuel de
groupage des GME, guide méthodologique, notices techniques — sont utiles à la
lecture, mais l'outil ne les lit jamais : inutile de les déposer ici.

## Liens de téléchargement

Le site de l'ATIH est en cours de restructuration : les liens directs seront
ajoutés ici dès qu'il sera stabilisé. À terme, l'outil pourra aller chercher
ces fichiers lui-même.
