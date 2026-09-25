# Pokémon 30e Anniversaire — stocks locaux dans la métropole lilloise

## État réel

Base de programme prête à tester, **surveillance non opérationnelle** : aucune source locale n'est encore validée, aucun dépôt distant n'est connecté et aucun destinataire de notification n'est configuré. Une page référencée par un moteur de recherche n'est pas une preuve de stock actuel. La fiche Cultura Poster examinée redirige vers la catégorie Pokémon ; elle n'est pas activée.

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
