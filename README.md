# 🩺 PMSI SMR — Recherche d'actes de réadaptation CSARR & CSAR

Outil local (Streamlit) pour le Département d'Information Médicale d'un
établissement de soins médicaux et de réadaptation : retrouver rapidement un
acte de réadaptation et **tous les codes supplémentaires** nécessaires pour
remplir la zone d'acte du RHS, sans ouvrir les Excel et les PDF de l'ATIH.

Deux nomenclatures sont couvertes en parallèle, le temps de la transition :

| | CSARR | CSAR |
|---|---|---|
| Actes | 512 | 146 |
| Code | 7 caractères (`GLR+226`) | 5 caractères (`07S06`) |
| Statut | codage possible jusqu'au 31/12/2026 | codage possible depuis mars 2025, **obligatoire au 01/01/2027** |

Le **transcodage** est navigable dans les deux sens : depuis un acte CSARR vers
l'acte CSAR suggéré, et depuis un acte CSAR vers la liste des actes CSARR qu'il
regroupe.

## Ce que l'outil affiche

**Recherche** par code (complet ou partiel : `07S06`, `01E`, `04`, `glr226`,
`ALQ`) ou par mots du libellé, accents et majuscules ignorés, tous les mots
saisis devant être présents. Filtres par chapitre, par objectif d'acte (CSAR)
et extension de la recherche aux notes, définitions et descriptions. Le filtre
par chapitre est un bouton qui ouvre la liste des intitulés **complets**, un
par ligne, dans un panneau plus large que la colonne de gauche ; il se referme
dès qu'un chapitre est choisi, et le bouton affiche alors l'intitulé entier.

**Synonymes (CSAR)** : le catalogue a son vocabulaire — « réadaptation » et
non « rééducation », « évaluation » et non « bilan », « squelette axial » et
non « rachis ». Un dictionnaire traduit les mots d'usage courant : `reeduc
super` retrouve la séance de réadaptation du membre supérieur, `bilan
équilibre` l'évaluation de l'équilibre, `kiné respi` le désencombrement, `ETP`
l'éducation thérapeutique, `FRE` le fauteuil roulant électrique. Le mot saisi
reste cherché tel quel, en plus de ses synonymes ; les actes trouvés sans le
dictionnaire sont classés les premiers, et chaque correspondance appliquée est
affichée (« reeduc → réadaptation »). Un mot d'au moins quatre lettres vaut
début de terme, les pluriels et les traits d'union sont tolérés
(`psychocorporelle`, `orthèses`), les petits mots (de, du, la, à…) ignorés.

Le dictionnaire est un fichier texte, `synonymes_csar.txt`, une entrée par
ligne :

```
rééducation, réhabilitation = réadaptation | entrainement
kiné respi, toux = désencombrement | ventilatoire
standing = 07S12
```

À gauche du signe égal, ce que l'on tape ; à droite, ce qu'il faut chercher
dans les libellés (ou un code d'acte), la barre verticale séparant plusieurs
possibilités. Une modification prend effet dès la recherche suivante, sans
relancer l'outil ni reconstruire la base ; une ligne mal formée est signalée
sur la page de recherche. Ce fichier étant remplacé à chaque mise à jour, les
ajouts personnels vont dans `~/.dim/smr_synonymes_csar.txt` (même syntaxe,
fichier à créer), qui s'y ajoute. Le dictionnaire traduit du vocabulaire, non
des indications : il ne contient ni diagnostics ni métiers. Il ne concerne pas
le CSARR, appelé à disparaître.

**Fiche d'un acte CSAR** : chapitre et objectif, définition, fonction CIF,
description du contenu de l'acte, exclusions cliquables, puis les codes
supplémentaires autorisés — modulateurs de temps (T0–T4), de lieu (L1–L3), de
technicité (QM, QS, QF, QI, QC, QQ) et leurs modules/niveaux, modalités
collective et pluriprofessionnelle, extensions documentaires, liste indicative
des **intervenants attendus** — ainsi que les pondérations par intervenant et
le caractère spécialisé par regroupement de groupes nosologiques.

**Fiche d'un acte CSARR** : arborescence complète (chapitre, sous-chapitre,
paragraphe, sous-paragraphe), notes du catalogue (« à l'exclusion de », « cet
acte comprend »), consigne de codage PMSI, statut dédié / non dédié /
collectif / pluriprofessionnel, étapes d'appareillage A, B, C, modulateurs
autorisés, gestes complémentaires cliquables, pondérations et majorations.

**Composeur de zone d'acte** : assemble le code principal et tous les codes
supplémentaires en contrôlant les associations autorisées (modulateur non
permis, module de technicité sans plateau, nombre de patients incohérent avec
le statut de l'acte, étape d'appareillage manquante, intervenant hors liste
indicative…), et affiche la **pondération résultante** pour l'intervenant et
la modalité retenus.

**Panier d'actes** (onglet de chaque page de recherche) : rassemble les actes
d'un même dossier, qu'ils viennent d'une fiche (bouton **🧺 Ajouter au
panier**), de la liste des actes spécialisés, ou d'un collage de lignes déjà
codées. Chaque ligne est contrôlée (code inexistant ou supprimé, association
interdite, exclusions codées ensemble) et pondérée. Le panier calcule le
**score de réadaptation** — global et spécialisé, par séjour et par jour — et
le positionne face aux seuils publiés du groupe nosologique choisi. Export CSV.

**Actes CCAM** : cinquante-six actes CCAM sont pondérés par l'ATIH dans le
fichier de pondérations du CSARR et comptent donc dans le score de
réadaptation — seize d'entre eux figurent en outre dans les listes d'actes
spécialisés de la pneumologie et de la cardiologie, pour neuf groupes
nosologiques. Le panier les accepte au même titre que les actes CSARR et CSAR,
au code seul : ni modulateur, ni catégorie d'intervenant, la pondération
publiée valant pour l'intervenant 10. On les ajoute depuis la partie **groupe
de réadaptation** de la page « Séjour & valorisation », qui les propose tous
avec leur nombre de réalisations, depuis l'onglet **Actes spécialisés par
GN**, ou en collant leur code. Ils se recueillent dans la zone d'actes CCAM du
RHS, non dans une zone d'acte de réadaptation.

**Correction d'un acte du panier** : cliquer une ligne du panier rouvre le
composeur de sa nomenclature, réamorcé sur la composition mémorisée —
intervenant, modulateurs, nombre de patients et de réalisations. On enregistre
et l'acte garde sa place dans la liste ; on peut aussi l'ajouter en plus,
le retirer, ou **corriger son code**, ce qui ouvre le composeur de l'acte
désigné, dans l'une ou l'autre nomenclature. Une erreur repérée au dixième
acte n'oblige donc pas à ressaisir les neuf précédents. La correction se fait
depuis l'onglet Panier ou depuis la partie groupe de réadaptation de la page
« Séjour & valorisation », qui liste les actes du panier.

**Actes spécialisés par groupe nosologique** (onglet de chaque page de
recherche) : choisir une catégorie majeure puis un GN, et obtenir la liste des
actes qui alimentent le score de réadaptation spécialisée de ce GN — côté
CSARR (et CCAM), côté CSAR avec la restriction d'intervenants applicable. Les
actes affichés peuvent être ajoutés au panier en une fois.

**Favoris** (page « ⭐ Favoris ») : le bouton **☆ Ajouter aux favoris** de
chaque fiche d'acte — CSARR, CSAR ou CCAM pondéré — range l'acte parmi les
favoris, avec un **nom** et un **commentaire** libres. La page Favoris les
**filtre** par nomenclature et par mots, cherchés dans le code, le nom, le
libellé officiel et le commentaire, accents et majuscules ignorés. Un clic sur
une ligne ouvre la fiche de l'acte, composeur compris : un favori se code et
rejoint le panier sans repasser par la recherche. Les favoris CSARR affichent
l'acte CSAR suggéré par la table d'aide au codage, en vue du 1er janvier 2027.
Modification en série (nom, commentaire, retrait), export et import JSON. Un
favori retiré par erreur se rétablit, nom et commentaire compris, d'un nouveau
clic sur l'étoile pendant la session.

**Aucune saisie perdue** : la recherche en cours, les filtres, les composeurs
de zone d'acte et le panier vivent dans un magasin de session découplé des
widgets (`smr_etat.py`). On peut aller consulter les Références et revenir :
tout est là. C'est la fondation du futur générateur de GME.

**Recherche d'un code CIM-10** (page « Séjour & valorisation ») : le
référentiel chargé est la CIM-10 **complète** de l'ATIH — 42 897 codes, et non
une sélection. La recherche accepte un code (`I63`) ou des mots du libellé ;
les libellés ATIH étant abrégés, un mot cherché correspond aussi à son
abréviation — « accident vasculaire cérébral » retrouve « ACCID. VASC.
CEREB. ». Le nombre total de résultats est annoncé, l'affichage étant borné à
200 lignes.

**Séjour & valorisation** : la saisie de la manifestation morbide principale,
de l'affection étiologique et des diagnostics associés détermine la
**catégorie majeure** puis le **groupe nosologique**, en expliquant le
raisonnement — quel test a été franchi, sur quelle liste de diagnostics, et
pourquoi les nœuds précédents ont été écartés. Le choix du GME est alors
restreint à ceux du groupe nosologique trouvé. Le **groupe de réadaptation**
est ensuite calculé à partir des actes du panier : les quatre scores, la règle
pédiatrique et les seuils du groupe nosologique conduisent à P, S, T ou U en
hospitalisation complète, à H, I, J, K ou L en temps partiel. Les actes du
panier y sont listés : cliquer une ligne rouvre le composeur, pour corriger
l'acte — un modulateur de temps oublié change sa pondération — ou le retirer.
Les actes CCAM pondérés s'y ajoutent au panier sans quitter la page. Le dénominateur des
scores par jour suit le manuel des GME 2026 (vol. 1, § 3.3.2). En
hospitalisation complète, ce sont les jours de présence du lundi au vendredi
du séjour, sans dépasser les journées de présence ; au-delà de 90 journées, on
les compte, comme les actes, sur les RHS jusqu'à celui de la 90ᵉ journée, qui
fixent le GME de financement. En temps partiel, ce sont tous les jours de
présence de la semaine, week-end compris : ses journées de présence, 7 au
plus. La **dépendance**
se cote enfin dans l'outil, item par item selon la grille des activités de la
vie quotidienne, ce qui donne le **niveau de lourdeur** A, B ou C. Le
**niveau de sévérité** clôt la chaîne : les complications sont retenues ou
neutralisées selon qu'elles sont ou non exclues par les diagnostics ayant
orienté le séjour. Les 21 actes CCAM qui valent complication à eux seuls se
choisissent dans leur liste, libellé complet affiché, comme les actes CCAM
pondérés du groupe de réadaptation ; ils ne rejoignent pas le panier, aucun
n'étant pondéré. Les actes retenus restent affichés, chacun avec un bouton
pour le retirer. Le **GME complet** est alors calculé, puis valorisé. À partir du GME et des journées de
présence, l'outil retrouve le ou les GMT applicables et calcule le montant,
en détaillant chaque étape — zone basse, forfaitaire ou haute, coupure au 90ᵉ
jour, séjour court terminé par transfert ou décès, temps partiel — puis
applique les coefficients. L'outil est paramétré pour un **établissement
public de santé** (a de l'article L.162-22 du code de la sécurité sociale)
situé dans le Morbihan : grille ex-DAF (annexe I), coefficient géographique
nul, coefficient de revalorisation salariale +1,41 %.

**Références** : modulateurs, modalités et extensions documentaires des deux
catalogues, catégories d'intervenant, transcodage des modulateurs,
**arborescence du CSAR** (chapitre → objectif → actes) et **du CSARR**
(chapitre → sous-chapitre → paragraphe → actes), synthèse des règles de codage,
les 92 groupes nosologiques et les seuils des groupes de réadaptation, versions
des fichiers sources. La page se rouvre sur le dernier onglet consulté.

**CMA & sévérité** (onglet des Références) : les 794 diagnostics et 21 actes
CCAM qui portent le niveau de sévérité de 1 à 2, filtrables par code ou par
libellé, avec les positions où le diagnostic peut être porté. Cliquer une CMA
affiche la **liste des diagnostics qui la neutralisent** lorsqu'ils orientent
déjà le séjour — de 38 à 4 055 codes selon la CMA, eux-mêmes filtrables. 39
CMA n'ont aucune exclusion et valent donc sévérité 2 sans condition ; les
actes CCAM ne sont jamais neutralisés.

## Fichiers sources requis (dossier `sources/`)

| Fichier | Rôle |
|---|---|
| `csar_version_*.xlsx` | actes CSAR, éligibilité des modulateurs et modalités, table d'aide au codage, intervenants attendus |
| `fichier_associe_csar_*.xlsx` | définitions, fonctions CIF et descriptions détaillées des actes CSAR |
| `fichier_complementaire_csarr_*.xlsx` | actes CSARR hiérarchisés, notes, gestes complémentaires, modulateurs, codes supprimés |
| `Transcodage_CSARR_CSAR*.xlsx` | commentaires de transcodage (facultatif) |
| `ACTES_ponderations_CSARR*.xlsx` | pondérations CSARR et majorations des modulateurs |
| `ACTES_ponderations_CSAR_transcodage*.xlsx` | pondérations CSAR |
| `ACTES_listes_SPE_CSAR*.xlsx` | caractère spécialisé des actes CSAR par regroupement de GN |
| `GR_infos*.xlsx` | groupes de réadaptation et seuils de score par GN |
| `ACTES_listes_SPE.xlsx` | actes spécialisés CSARR et CCAM, et dictionnaire des 92 GN |
| `CSAR_infos*.xlsx` | barème des modulateurs CSAR (pondération du temps, majorations de lieu) |
| `TOTAL_listes_groupes*.xlsx` | libellés des CM, GN, GR, GL et GME |
| `annexes_arrete_tarifaire_smr_*.xlsx` | tarifs des GMT (bornes de zone et forfaits), correspondance GME → GMT, coefficients |
| `CIM_infos_SMR.xlsx` | CIM-10 à usage SMR : orientation en catégorie majeure, positions autorisées, listes de diagnostics |
| `GN_liste_tests.xlsx` | arbres de décision menant au groupe nosologique |
| `GL_infos*.xlsx` | table des niveaux de lourdeur par groupe de réadaptation |
| `CMA_exclusion*.xlsx` | exclusions des complications et morbidités associées |
| `CMA_CCAM*.xlsx` | actes CCAM valant complication à eux seuls |

Les fichiers sont détectés **par leur nom**, cherché récursivement dans
`sources/` : **le rangement du dossier est libre**. On peut le réorganiser
comme on veut, la construction suit. Lors d'un changement de version il suffit
de déposer les nouveaux fichiers ; si plusieurs versions coexistent, la plus
récente est retenue. Le tableau ci-dessus ne donne donc que les noms attendus,
pas des emplacements imposés.

Seuls ces fichiers sont lus. Tout le reste de `sources/` — guides et manuels au
format PDF — est de la documentation, utile au lecteur mais jamais chargée.

> **Table de transcodage** — c'est la table d'aide au codage (annexe 4) publiée
> dans `csar_version_*.xlsx` qui fait foi, et non le fichier autonome
> `Transcodage_CSARR_CSAR.xlsx`, antérieur : ce dernier renvoie encore vers des
> codes CSAR supprimés depuis (11S14 à 11S16) et diverge sur 32
> correspondances. Seuls ses commentaires sont réutilisés. Le détail est
> rappelé dans l'onglet *Références › Sources*.

Au premier lancement, l'outil construit une base locale `data/smr.sqlite`
(quelques secondes). Pour **mettre à jour** : déposer les nouvelles versions
dans `sources/`, supprimer `data/smr.sqlite` et relancer.

## Installation & lancement

### Windows

1. Installer Python 3.9+ ([python.org](https://www.python.org/downloads/)) en
   cochant **« Add python.exe to PATH »**.
2. Copier le dossier complet du projet.
3. Double-cliquer sur **`lancer_smr.bat`** — l'environnement virtuel est créé
   et les dépendances installées automatiquement au premier lancement, puis
   l'application s'ouvre dans le navigateur
   ([http://localhost:8501](http://localhost:8501)).

> Si le poste passe par un proxy pour l'installation des paquets :
> `set HTTPS_PROXY=http://proxy:port` avant de lancer le script, ou installer
> les dépendances depuis un poste connecté et copier le dossier `.venv`.

### Linux / macOS

```bash
./lancer_smr.sh
```

ou manuellement :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

## Organisation du projet

```
SMR/
├── app.py               coquille Streamlit : navigation et pages de recherche
├── fiches.py            fiches d'acte et composeurs de zone d'acte
├── panier.py            panier d'actes : contrôles, pondérations, scores
├── favoris.py           favoris : étoile des fiches, page Favoris, stockage
├── groupage.py          morbidité → catégorie majeure → groupe nosologique
├── valorisation.py      GMT et valorisation d'un séjour
├── references.py        référentiels, arborescences, règles de codage
├── smr_etat.py          magasin de session : la saisie survit à la navigation
├── smr_data.py          chargement, référentiels des guides, recherche
├── synonymes.py         dictionnaire des synonymes de la recherche CSAR
├── synonymes_csar.txt   les synonymes livrés, un par ligne (modifiable)
├── smr_build.py         parsing des sources Excel → base SQLite
├── lancer_smr.bat/.sh   scripts de lancement (Windows / Linux-macOS)
├── requirements.txt     dépendances (streamlit, pandas, openpyxl)
├── data/smr.sqlite      base construite automatiquement (régénérable)
└── sources/             fichiers sources ATIH, dont gme/ (manuel de groupage)
```

La base `data/smr.sqlite` est entièrement régénérable à partir de `sources/` :
c'est ce dossier qu'il faut sauvegarder et copier sur un autre poste.

Les **favoris** sont volontairement rangés **hors du dossier du projet**, dans
`~/.dim/smr_favoris.json` (sous Windows :
`C:\Users\<vous>\.dim\smr_favoris.json`) : ils survivent au remplacement
complet du dossier de l'application lors d'une mise à jour, comme à la
reconstruction de la base. Le dossier `~/.dim` est **commun aux outils du
DIM** : chacun y range ses fichiers sous un nom préfixé par l'outil, plutôt
que de créer son propre dossier dans le répertoire personnel.

Le fichier personnel de **synonymes**, `~/.dim/smr_synonymes_csar.txt`, y est
rangé pour la même raison.

Pour transporter les favoris d'un poste à l'autre, utiliser l'export/import
JSON de la page **Favoris**. Un fichier rendu illisible par une retouche
manuelle n'est jamais écrasé : il est mis de côté sous un nom horodaté
(`smr_favoris.json.illisible-AAAAMMJJ-HHMMSS`).

Pour reconstruire la base sans lancer l'application :

```bash
.venv/Scripts/python.exe smr_build.py
```

## Périmètre et évolutions prévues

La chaîne de groupage est **complète**, telle que décrite par le manuel de
groupage 2026 :

```
CM (2 car.) → GN (4) → GR (+1 lettre) → GL (+1 lettre) → sévérité (+1 chiffre)
                                                         = GME sur 7 caractères
```

soit 16 CM, 92 GN, 392 GR, 745 GL et 1 314 GME. À partir des diagnostics, des
actes du panier, de l'âge et de la cotation de dépendance, l'outil produit le
GME à sept caractères puis le montant valorisé, en expliquant chaque étape.
Toutes les tables de `sources/gme/` sont chargées : `CIM_infos_SMR.xlsx`
(catégories majeures et CMA, 42 897 codes), `GN_liste_tests.xlsx` (arbres de
décision des GN), `GR_infos.xlsx` (pondérations, actes spécialisés, seuils),
`GL_infos.xlsx` (lourdeur), `CMA_exclusion.xlsx` et `CMA_CCAM.xlsx`
(sévérité).

La **valorisation** est opérationnelle de bout en bout : les tarifs des 1 638
GMT et la correspondance GME → GMT sont chargés, et le moteur reproduit
exactement les cinq cas de contrôle de l'aide-mémoire de valorisation (séjour
court, zone basse, zone forfaitaire, zone haute, coupure au 90ᵉ jour).

Ce qui reste à faire : les **suppléments** facturables en sus du GMT (ST4,
ST5, ST6 transport, D15/D16 dialyse péritonéale, et le supplément cancérologie
ONC de 17 €/jour créé en 2026), et la saisie **semaine par semaine** en temps
partiel, où chaque semaine produit son propre groupe de réadaptation.

Deux points de divergence entre sources sont signalés à l'écran plutôt que
tranchés en silence. Le dénominateur des scores en temps partiel : le lisez-moi
de `GR_infos.xlsx` le limite aux jours du lundi au vendredi, l'outil suit le
manuel, qui compte tous les jours de présence de la semaine. La position de
l'affection étiologique comme marqueur de sévérité, laissée au choix.

Le **temps partiel** est traité partout : groupage identique pour la CM et le
GN, orientation en H/I/J/K/L pour le GR, valorisation en journées × TZF1 sans
coupure au 90ᵉ jour ni bloc « séjour court ». Le groupage y porte sur **une
semaine à la fois**, conformément au manuel : le groupe nosologique et le
niveau de lourdeur ne varient pas d'une semaine à l'autre, mais le groupe de
réadaptation dépend du score de la semaine considérée.

## Avertissement

Outil d'**aide au codage et à la lecture** des catalogues d'actes de
réadaptation. En cas de divergence, seuls font foi les documents officiels de
l'ATIH et les textes publiés au Journal officiel ou au Bulletin officiel Santé
Protection sociale Solidarité.
