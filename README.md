# Social Feed

Un petit fil de nouvelles personnel, sans algorithme : les publications de vos
sources sont réunies de la plus récente à la plus ancienne, sur GitHub Pages et
dans un flux RSS global.

- **Site** : https://otisdave.github.io/social-feed/
- **RSS** : https://otisdave.github.io/social-feed/feed.xml
- **YouTube** : Éco en bâtons, Investi QC, Hugo Lisoir et Alex Demers — Finance 360.
- **Facebook** : Guild Wars et The Lord of the Rings Online, via un scraper public expérimental.

## Fonctionnement

```text
YouTube (Atom officiel) -----> Adaptateur YouTube ----+
                                                    |
Facebook (page publique) ----> Adaptateur Facebook ---+--> Publications standardisées
                                                               |
                                                     Fusion + dédoublonnage
                                                               |
                                                   Archive JSON + flux RSS
                                                               |
                                                         GitHub Pages
```

Le site affiche les miniatures, les dates de publication, les descriptions et les
liens d'origine. Une recherche, un filtre par source et un filtre par plateforme
permettent de parcourir le fil. Les cartes ouvrent une page interne partageable
(`publication.html?source=…&id=…`), avec le texte archivé, la date et un bouton
permanent vers l'original. Les liens du RSS continuent de pointer vers l'original.

Le lecteur YouTube (domaine `youtube-nocookie.com`) ou la publication/vidéo
Facebook officielle est chargé seulement après un clic explicite. Aucun lecteur
tiers n'est chargé avant ce consentement; les miniatures sont toutefois chargées
depuis YouTube ou Facebook. Aucune vidéo n'est téléchargée ni réhébergée.
Une intégration peut être refusée par le fournisseur, demander des cookies ou
une connexion : un message et le bouton vers l'original restent disponibles.
Le navigateur ne permet pas de détecter de façon fiable les refus à l'intérieur
d'une iframe tierce. Facebook affiche un extrait archivé de 240 caractères, pas
une copie garantie du texte intégral; YouTube affiche la description archivée.

GitHub Actions interroge les sources environ chaque heure, à la minute 17, et à
chaque modification de `main`. GitHub peut retarder les tâches planifiées.
Une actualisation manuelle est possible dans **Actions > Refresh and publish >
Run workflow**.

L'archive `site/feed.json` est conservée dans Git. Le flux initial YouTube expose
seulement ses publications récentes (généralement une quinzaine), pas l'historique
complet de la chaîne. Les publications découvertes restent archivées lors des
actualisations suivantes. Une publication qui apparaît puis disparaît entre deux
actualisations peut ne jamais être captée. Une vidéo supprimée chez YouTube n'est
pas automatiquement retirée de l'archive.

## Développement local

Python 3.12 ou plus récent, Git et Chromium via Playwright sont nécessaires.
Aucune clé YouTube, aucun compte Facebook et aucun secret à configurer.

Depuis le dossier du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
python tests/browser_smoke.py
python -m social_feed
python -m http.server 8000 --directory site --bind 127.0.0.1
```

Ouvrir http://127.0.0.1:8000. Le site doit être servi par HTTP, et non ouvert
directement avec `file://`, car il charge `feed.json`.
Si l'exécution de `Activate.ps1` est restreinte, utiliser directement
`.\.venv\Scripts\python.exe` à la place de `python`, sans changer la politique
d'exécution Windows. Les tests unitaires n'ont pas besoin de navigateur.

## Gérer les abonnements

Tous les abonnements sont regroupés par plateforme dans **`sources.json`** :

```json
{
  "subscriptions": {
    "youtube": [
      {
        "id": "eco-en-batons",
        "name": "Éco en bâtons",
        "url": "https://www.youtube.com/@Eco_en_batons",
        "channel_id": "UCJrYJevv7eUOBg857Jx_qIA",
        "enabled": true
      }
    ],
    "facebook": [
      {
        "id": "guild-wars",
        "name": "Guild Wars",
        "url": "https://www.facebook.com/GuildWars/",
        "enabled": true
      },
      {
        "id": "lotro",
        "name": "The Lord of the Rings Online",
        "url": "https://www.facebook.com/LOTRO/",
        "enabled": true
      }
    ],
    "reddit": []
  }
}
```

- Ajouter une entrée dans la liste de la plateforme voulue.
- Choisir un `id` unique parmi **toutes** les plateformes, un nom et une URL HTTPS.
- `enabled: true` active la récupération; `false` conserve l'abonnement en attente
  et ne fait aucun appel au fournisseur. Les publications déjà archivées restent
  affichées si un abonnement actif est mis en pause.
- Retirer complètement l'entrée retire ses publications à la prochaine actualisation.
- La plateforme est déduite de la section : ne pas ajouter de champ `platform`
  dans chaque abonnement.

Pour YouTube, utiliser l'identifiant permanent `UC…` de la chaîne, pas son handle `@…`.
Il est exposé dans le lien du flux de la page YouTube ou dans les informations
avancées de sa propre chaîne. L'identifiant d'Éco en bâtons a été résolu depuis
sa page officielle. Après modification, exécuter `python -m social_feed`, puis
committer les fichiers de configuration et les deux fichiers générés.

Les pages **Guild Wars** et **The Lord of the Rings Online** sont déjà inscrites
dans la section `facebook`, avec le scraper public activé. La configuration réelle
contient aussi les trois chaînes YouTube supplémentaires. La section `reddit` est
prête à recevoir des abonnements lorsque son adaptateur sera implémenté. Mettre
`enabled: true` sur une plateforme sans adaptateur provoque une erreur explicite
plutôt qu'une fausse connexion réussie.

## Ajouter un autre adaptateur

Chaque adaptateur reçoit une source et retourne une liste de `Publication`
(`social_feed/models.py`) :

| Champ | Contrat |
|---|---|
| `id` | Identifiant stable de la publication chez le fournisseur |
| `title`, `description` | Texte brut, jamais du HTML à exécuter |
| `url`, `image_url` | URL HTTPS; miniature facultative |
| `published_at`, `updated_at` | Dates ISO 8601 avec fuseau horaire |
| `source_id`, `source_name`, `platform` | Identité de la source configurée |

Enregistrer l'adaptateur dans `ADAPTERS` et sa validation de configuration dans
`VALIDATORS`, dans `social_feed/adapters.py`, puis ajouter ses tests. Le reste du
pipeline ne dépend pas du fournisseur. Les identifiants sont dédoublonnés par
source, les modifications mettent à jour les éléments existants, et le tri se
fait selon la date de publication réelle, indépendamment du fuseau horaire.

**YouTube et le scraping public Facebook sont implémentés.** Reddit est affiché
comme « À venir ». Il pourra utiliser un flux de subreddit ou son API selon les
conditions d'accès en vigueur.

### Limites du scraper Facebook

Playwright charge la page publique dans un navigateur Chromium neuf, sans compte,
sans cookies persistants, sans proxy ni mécanisme de contournement. Il ne ferme
pas de barrière de connexion et ne résout pas de CAPTCHA. Il tente au maximum
trois défilements de la page publique et s'arrête si les données ne progressent
plus. Il n'appelle aucun endpoint privé de pagination. Les images, médias et polices sont bloqués dans
le navigateur de collecte pour limiter la consommation réseau.

Le scraper lit les données JSON présentes dans le document rendu et conserve
uniquement les publications attribuées à la page demandée, avec un identifiant
stable et une date absolue fournie par Facebook. Les commentaires, suggestions
d'autres pages et textes « il y a X heures » ne deviennent pas des publications.
Le texte est limité à un extrait de 240 caractères, avec un lien vers l'original.
Les miniatures Facebook peuvent expirer.

**La collecte est expérimentale et non garantie.** Facebook peut ne montrer qu'une
publication, imposer une connexion ou modifier ses données. Les restrictions
peuvent aussi différer entre un poste local et GitHub Actions. Aucun historique
complet ni détection fiable des modifications n'est promis.
Si aucun post daté n'est accessible, l'adaptateur signale une erreur explicite et
conserve l'archive; il ne transforme pas les informations du profil en faux posts.
L'API Graph avec les permissions appropriées reste une option plus encadrée.
Vérifier les conditions applicables de Meta avant un usage régulier du scraping.

## Déploiement GitHub Pages

1. Publier le dépôt sur GitHub avec la branche `main`.
2. Dans **Settings > Pages > Build and deployment**, sélectionner **GitHub Actions**.
3. Vérifier `site_url` dans `sources.json` si le propriétaire ou le nom du dépôt change.
4. Lancer **Refresh and publish** dans Actions.

Le workflow a besoin des permissions `contents: write` pour archiver le fil,
`pages: write` et `id-token: write` pour publier Pages. Il utilise uniquement le
`GITHUB_TOKEN` automatique. Le commit d'archive effectué par ce token ne
redéclenche pas le workflow. Une règle de protection de `main` interdisant les
écritures du bot doit être adaptée, sinon la conservation de l'archive échouera.
Le workflow de pull request exécute seulement les tests, sans publication.

Le site et l'archive sont publics : ne pas ajouter de contenus privés ni de
secrets dans `sources.json`. Sur un dépôt public, GitHub peut désactiver les
workflows planifiés après 60 jours sans activité; surveiller Actions et réactiver
le workflow au besoin.

## Erreurs et fraîcheur

Les appels réseau ont un délai maximal, une limite de taille et trois tentatives
pour les erreurs transitoires. Une source en erreur n'efface pas ses publications
archivées et n'empêche pas la récupération des autres sources. L'erreur apparaît
dans les logs, dans l'état JSON et dans un avertissement visible sur le site.
La date du dernier succès par source est conservée. Le workflow publie cet état
dégradé, puis se marque en échec pour ne pas masquer le problème.

Une archive corrompue ou une configuration invalide fait échouer la génération
sans la remplacer. Le site avertit aussi lorsque sa dernière actualisation date
de plus de quatre heures. Les dates affichées utilisent le fuseau horaire du
navigateur; le RSS utilise des dates UTC.
