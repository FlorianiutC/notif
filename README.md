# Pokémon 30e Anniversaire — stocks locaux dans la métropole lilloise

## État réel

Programme publié sur GitHub ; notifications configurables par le secret `NTFY_TOPIC`. **La surveillance de stock local n'est pas opérationnelle** : aucune source locale n'est encore validée. Une page référencée par un moteur de recherche n'est pas une preuve de stock actuel. La fiche Cultura Poster examinée redirige vers la catégorie Pokémon ; elle n'est pas activée.

## Agent de maintenance des liens

`link_agent.py` entretient `data/links.json` à partir des pages de King Jouet, Cultura et Smyths configurées dans `link_sites.json`. C'est un agent autonome à règles, sans modèle de langage ni API d'IA payante. Il ne recherche pas sur l'ensemble du Web. Une fois publié, le workflow **Maintenance des liens Pokemon** fonctionne chaque jour à 06:17 UTC (08:17 à Paris en été, 07:17 en hiver), ou manuellement depuis Actions. Aucun crédit Codex n'est utilisé par ces exécutions Python.

- Découverte de liens produits pertinents sur les listes configurées ; confirmation par le titre de la fiche ou ses données structurées Product.
- Vérification des liens existants, mise à jour des titres et de l'URL finale sur le même domaine.
- Suppression logique : après au moins trois réponses HTTP 404/410 réparties sur 48 heures, le lien passe en `archived`. L'historique reste récupérable ; une fiche revenue peut être réactivée.
- Les erreurs réseau, 403/429/5xx, redirections vers une catégorie et pages non lisibles passent en `unknown`, sans suppression. Une indisponibilité de produit n'est pas un lien mort.
- Respect de robots.txt, cadence limitée, au plus 36 requêtes réseau et 24 contrôles produit par passage. La couverture n'est pas exhaustive ; JavaScript, protections anti-bot et pagination peuvent limiter la découverte. Le résumé Actions indique les sites accessibles.
- Une notification ntfy signale un changement du **catalogue**, sans affirmer de stock local. Le catalogue n'active jamais automatiquement une source de `sources.json` : le magasin lillois et son stock doivent être validés séparément.

Le workflow écrit uniquement le catalogue avec l'identité technique de GitHub Actions ; le secret ntfy n'est jamais enregistré dans les fichiers, caches ou messages de diagnostic. Les titres et URLs publics des boutiques sont enregistrés. GitHub peut désactiver la planification après 60 jours sans activité ; contrôler périodiquement l'onglet Actions. Les notifications de changement ne sont pas réessayées si leur envoi échoue après la mise à jour du catalogue.

Périmètre : produits français scellés de l'extension 30e Anniversaire, coffrets, bundles, duopacks, tripacks, ETB, UPC, mini-tins et Pokébox. Un stock d'entrepôt ou une livraison en magasin ne prouve pas un stock en rayon.

## GitHub gratuit, Mac éteint

Utiliser un dépôt **public**, avec les runners Linux standard GitHub Actions. Le code et les sources seront publics ; ne jamais y mettre de secrets. Le workflow vise un passage toutes les cinq minutes, sans garantie de ponctualité. Les workflows planifiés doivent être sur la branche par défaut. GitHub peut retarder ou supprimer des passages sous forte charge et désactive les tâches planifiées des dépôts publics après 60 jours sans activité : prévoir une vérification mensuelle manuelle. Aucun serveur personnel ni Mac allumé n'est nécessaire.

Documentation :
- https://docs.github.com/en/actions/concepts/billing-and-usage
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## Notifications gratuites

1. Installer l'application officielle ntfy sur iPhone et autoriser les notifications.
2. Générer un nom de topic aléatoire, par exemple avec `python3 -c 'import secrets; print(secrets.token_hex(24))'`.
3. S'abonner à ce topic sur le serveur `https://ntfy.sh` dans l'application.
4. Sur GitHub : Settings → Secrets and variables → Actions → New repository secret, nom `NTFY_TOPIC`, valeur identique au topic.
5. Sur Mac, s'abonner au même topic sur https://ntfy.sh et autoriser les notifications du navigateur. Le navigateur ou l'application web doit généralement rester ouvert.

Le topic ntfy gratuit n'est pas un canal authentifié : quiconque connaît son nom peut le lire ou y publier. Le garder secret et ne pas y envoyer de données personnelles. Le compte Apple n'intervient pas. Documentation : https://docs.ntfy.sh/ et https://docs.ntfy.sh/subscribe/pwa/.

## Ajouter une source réellement vérifiée

Le moteur actuel lit uniquement du HTML accessible sans connexion. Un site qui charge le stock par JavaScript ou demande de sélectionner un magasin nécessite un adaptateur dédié ; ne pas marquer sa source comme validée tant que ce travail n'est pas fait. Ne pas contourner les protections des sites.

Chaque entrée de `sources.json` doit désigner une **fiche produit unique** et un **bloc de stock explicitement rattaché au magasin**. Exemple de structure, volontairement fictif et à ne pas activer :

```json
{
  "id": "enseigne-magasin-produit",
  "url": "https://example.org/produit",
  "store": "Nom exact du magasin lillois",
  "product": "Nom exact du produit 30e Anniversaire",
  "local_stock_verified": false,
  "product_selector": "h1",
  "scope_selector": "#bloc-stock-magasin",
  "stock_selector": ".statut",
  "labels": {
    "available": ["Disponible en magasin"],
    "unavailable": ["Rupture en magasin"],
    "preorder": ["Précommande en magasin"]
  }
}
```

Vérifier la commune dans la Métropole européenne de Lille, la langue, l'extension et la référence produit avant activation. Copier uniquement les libellés exacts observés. Toute ambiguïté, redirection ou erreur donne `unknown`, jamais « disponible » ou « rupture ». Le nom du magasin et le produit doivent aussi correspondre.

## Vérification et lancement

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python monitor.py
```

Après publication et configuration des sources et du secret, lancer Actions → Stocks Pokemon Lille → Run workflow. Lire le résumé et `rapport-stock`. Vérifier une notification réelle sur iPhone avant de considérer la configuration terminée. Décommenter ensuite les deux lignes `schedule` et `cron` dans `.github/workflows/stocks.yml` pour activer la surveillance périodique. La planification reste désactivée tant qu'aucune source n'a été validée.

Les alertes partent lors de la première disponibilité observée ou du passage vers disponible/précommande. Une lecture inconnue conserve le dernier état connu. L'état anti-doublons est conservé dans le cache GitHub : une éviction peut provoquer une nouvelle alerte. Une panne après envoi mais avant sauvegarde peut également produire un doublon. Les rapports expirent après un jour. Le moniteur ne réserve et n'achète rien.
