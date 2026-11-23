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

Le dictionnaire est un fichier texte, `smr/synonymes/synonymes_csar.txt`, une
entrée par ligne :

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
widgets (`smr/etat.py`). On peut aller consulter les Références et revenir :
tout est là, et la page « Séjour & valorisation » reprend les actes du panier
pour calculer le groupe de réadaptation.

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

## Fichiers sources de l'ATIH, à déposer dans `sources/`

L'outil construit sa base à partir de **17 fichiers Excel publiés par
l'ATIH**. Ils **ne sont pas distribués avec le code** : chacun les télécharge
sur le site de l'ATIH et les dépose dans le dossier `sources/`. Seize sont
indispensables ; le dix-septième, `Transcodage_CSARR_CSAR*.xlsx`, est
facultatif.

| Publication de l'ATIH (campagne 2026) | Fichiers attendus |
|---|---|
| CSAR — catalogue et fichier associé | `csar_version_*.xlsx`, `fichier_associe_csar_*.xlsx` |
| CSARR — fichier complémentaire et transcodage | `fichier_complementaire_csarr_*.xlsx`, `Transcodage_CSARR_CSAR*.xlsx` (facultatif) |
| Manuel de groupage des GME — les 12 tables | `CIM_infos_SMR*.xlsx`, `GN_liste_tests*.xlsx`, `GR_infos*.xlsx`, `GL_infos*.xlsx`, `CMA_exclusion*.xlsx`, `CMA_CCAM*.xlsx`, `TOTAL_listes_groupes*.xlsx`, `ACTES_ponderations_CSARR*.xlsx`, `ACTES_listes_SPE.xlsx`, `ACTES_ponderations_CSAR_transcodage*.xlsx`, `ACTES_listes_SPE_CSAR*.xlsx`, `CSAR_infos*.xlsx` |
| Arrêté tarifaire SMR — annexes | `annexes_arrete_tarifaire_smr_*.xlsx` |

Dans ces motifs, `*` remplace n'importe quelle suite de caractères (date,
numéro de version) ; seul `ACTES_listes_SPE.xlsx` doit porter exactement ce
nom.

Le détail — nom exact de chaque fichier en 2026 et ce que l'outil y lit — est
dans **[`sources/LISEZMOI.md`](sources/LISEZMOI.md)**. Les guides et manuels au
format PDF ne sont pas nécessaires : l'outil ne les lit jamais.

Les fichiers sont détectés **par leur nom**, cherché récursivement dans
`sources/` : **le rangement du dossier est libre**, et une archive téléchargée
de l'ATIH s'y dézippe telle quelle. Lors d'un changement de version il suffit
de déposer les nouveaux fichiers ; si plusieurs versions coexistent, la plus
récemment modifiée est retenue. Tant qu'il manque un fichier indispensable,
l'outil affiche la liste de ceux qui manquent au lieu de démarrer.

Le site de l'ATIH étant en cours de restructuration, les liens de
téléchargement ne sont pas encore donnés : ils le seront dès qu'il sera
stabilisé.

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

1. **Télécharger l'outil** :
   [`smr-dim.zip`](https://github.com/kuxtux/smr-dim/releases/latest/download/smr-dim.zip),
   la dernière version publiée, puis le dézipper ; ou
   `git clone https://github.com/kuxtux/smr-dim.git`.
2. **Déposer les fichiers de l'ATIH** dans `sources/` (voir la section
   précédente et [`sources/LISEZMOI.md`](sources/LISEZMOI.md)).
3. **Lancer l'outil**, selon le système (ci-dessous). Au premier lancement,
   la base se construit en quelques secondes.

### Windows

1. Installer Python : ouvrir le **Microsoft Store**, chercher « Python » et
   installer la version la plus récente publiée par la *Python Software
   Foundation* (3.10 au minimum). Si le Store est bloqué sur le poste,
   installer Python depuis [python.org](https://www.python.org/downloads/) en
   cochant **« Add python.exe to PATH »**, ou s'adresser au service
   informatique.
2. Double-cliquer sur **`lancer_smr.bat`** — l'environnement virtuel est créé
   et les dépendances installées automatiquement au premier lancement, puis
   l'application s'ouvre dans le navigateur
   ([http://localhost:8501](http://localhost:8501)).

> Si le poste passe par un proxy pour l'installation des paquets :
> `set HTTPS_PROXY=http://proxy:port` avant de lancer le script. Sans accès à
> Internet : sur un poste connecté qui a la même version de Python,
> `python -m pip download -r requirements.txt -d paquets` ; copier le dossier
> `paquets` dans celui de l'outil ; puis, après un premier lancement qui crée
> `.venv`, `.venv\Scripts\python.exe -m pip install --no-index --find-links
> paquets -r requirements.txt`. Un dossier `.venv` ne se copie pas d'un poste
> à l'autre.
>
> En cas d'échec de l'installation (Python trop ancien, installation
> interrompue), supprimer le dossier `.venv` et relancer : il est recréé.

### Linux / macOS

Python 3.10 ou plus récent, puis :

```bash
./lancer_smr.sh
```

ou manuellement :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

La collecte de statistiques d'usage de Streamlit est désactivée, et
l'application n'est accessible que depuis le poste qui la lance : ces
réglages sont dans `.streamlit/config.toml`, à modifier pour partager l'outil
sur un réseau.

## Mettre à jour l'outil

Les versions sont publiées sur la page
[Releases](https://github.com/kuxtux/smr-dim/releases), avec ce qu'elles
apportent ; le numéro de la version installée s'affiche en bas de la colonne
de gauche de l'application. Il se lit ainsi : l'année de la campagne ATIH, puis
le numéro de version dans la campagne (`2026.2` apporte une fonctionnalité,
`2026.1.1` une correction).

Pour passer à une nouvelle version, télécharger le nouveau
[`smr-dim.zip`](https://github.com/kuxtux/smr-dim/releases/latest/download/smr-dim.zip)
et le dézipper, puis y recopier le dossier `sources/` de l'ancienne
installation ; on peut aussi le dézipper par-dessus l'ancienne. Avec
`git clone`, un `git pull` suffit. Au premier lancement, la base est
reconstruite automatiquement si elle date d'une autre version. Les favoris et
les synonymes personnels, rangés dans `~/.dim`, sont conservés.

## Organisation du projet

```
smr-dim/
├── app.py                    coquille Streamlit : navigation et pages de recherche
├── lancer_smr.bat / .sh      scripts de lancement (Windows / Linux-macOS)
├── requirements.txt          dépendances (streamlit, pandas, openpyxl)
├── .streamlit/config.toml    réglages Streamlit : accès local, sans télémétrie
├── smr/                      le code de l'application
│   ├── chemins.py            emplacements : sources/, data/, ~/.dim
│   ├── etat.py               magasin de session : la saisie survit à la navigation
│   ├── references.py         page Références : référentiels, arborescences, règles
│   ├── base/                 les données
│   │   ├── construction.py   lecture des sources Excel → base SQLite
│   │   └── donnees.py        chargement, référentiels des guides, recherche
│   ├── synonymes/            la recherche CSAR en langage courant
│   │   ├── synonymes.py      lecture du dictionnaire, développement des requêtes
│   │   └── synonymes_csar.txt  les synonymes livrés, un par ligne (modifiable)
│   ├── actes/                autour d'un acte
│   │   ├── fiches.py         fiches d'acte et composeurs de zone d'acte
│   │   ├── panier.py         panier d'actes : contrôles, pondérations, scores
│   │   └── favoris.py        favoris : étoile des fiches, page Favoris, stockage
│   └── sejour/               le séjour, du diagnostic au montant
│       ├── groupage.py       CM → GN → GR → GL → sévérité
│       └── valorisation.py   page Séjour & valorisation : GME → GMT → montant
├── sources/                  fichiers de l'ATIH, à déposer (voir LISEZMOI.md)
└── data/smr.sqlite           base construite automatiquement (régénérable)
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

Pour reconstruire la base sans lancer l'application, depuis le dossier du
projet, sous Windows :

```bat
.venv\Scripts\python.exe -m smr.base.construction
```

et sous Linux / macOS :

```bash
.venv/bin/python -m smr.base.construction
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
Les douze tables du manuel de groupage sont chargées, notamment
`CIM_infos_SMR.xlsx` (catégories majeures et CMA, 42 897 codes),
`GN_liste_tests.xlsx` (arbres de décision des GN), `GR_infos.xlsx` (groupes
de réadaptation et seuils de score), `GL_infos.xlsx` (lourdeur),
`CMA_exclusion.xlsx` et `CMA_CCAM.xlsx` (sévérité) ; les pondérations et les
listes d'actes spécialisés viennent des fichiers `ACTES_*`.

La **valorisation** est opérationnelle de bout en bout : les tarifs des 1 638
GMT et la correspondance GME → GMT sont chargés. Le moteur a été contrôlé sur
cinq cas calculés à la main pour le GME 0109SA1 : séjour court terminé par un
décès, zone basse, zone forfaitaire, zone haute, coupure au 90ᵉ jour. Il les
retrouve au centime près, avec une nuance : au-delà du 90ᵉ jour, il applique
le prix de journée publié par l'arrêté, arrondi au centime, et non le quotient
TZF1 / 7 recalculé, soit 4 centimes d'écart sur un séjour de 120 jours.

Ce qui reste à faire : les **suppléments** facturables en sus du GMT (ST4,
ST5, ST6 transport, D15/D16 dialyse péritonéale, et le supplément cancérologie
ONC de 17 €/jour créé en 2026), la saisie **semaine par semaine** en temps
partiel, où chaque semaine produit son propre groupe de réadaptation, et les
**liens de téléchargement** des fichiers de l'ATIH, que l'outil pourra aller
chercher lui-même une fois le site de l'ATIH stabilisé.

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

## Licence

Le code est distribué sous **licence MIT** : voir [`LICENSE`](LICENSE). Les
fichiers de l'ATIH que l'outil lit n'en font pas partie : ils ne sont pas
distribués avec le code, chacun les télécharge à leur source.
