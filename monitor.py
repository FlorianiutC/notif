"""Contrôle prudent de pages produit affichant explicitement un stock local."""
import json
import argparse
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


def normalize(value):
    value = unicodedata.normalize("NFKD", value).casefold()
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split())


def validate(source):
    for key in ("id", "url", "store", "product", "scope_selector", "product_selector", "stock_selector"):
        if not source.get(key):
            raise ValueError(f"Champ requis : {key}")
    if urlparse(source["url"]).scheme != "https":
        raise ValueError("URL HTTPS requise")
    channel = source.get("channel", "store")
    if channel not in {"store", "online"}:
        raise ValueError("Canal inconnu")
    if channel == "online" and source.get("online_stock_verified") is not True:
        raise ValueError("Offre en ligne non validée")
    if channel == "store" and source.get("local_stock_verified") is not True:
        raise ValueError("Source de stock local non validée")
    if channel == "store" and normalize(source.get("city", "")).replace("’", "'") not in {
        "villeneuve-d'ascq", "croix", "lille", "wasquehal"
    }:
        raise ValueError("Commune hors du périmètre demandé ou absente")


def classify(html, source):
    soup = BeautifulSoup(html, "html.parser")
    products = soup.select(source["product_selector"])
    scopes = soup.select(source["scope_selector"])
    if len(products) != 1 or normalize(source["product"]) not in normalize(products[0].get_text(" ", strip=True)):
        return "unknown", "Produit absent ou ambigu"
    if len(scopes) != 1:
        return "unknown", "Bloc magasin absent ou ambigu"
    scope = scopes[0]
    if normalize(source["store"]) not in normalize(scope.get_text(" ", strip=True)):
        return "unknown", "Magasin attendu absent"
    stocks = scope.select(source["stock_selector"])
    if len(stocks) != 1:
        return "unknown", "Stock local absent ou ambigu"
    label = normalize(stocks[0].get_text(" ", strip=True))
    # Correspondance exacte : « indisponible » ne doit jamais correspondre à « disponible ».
    matches = [status for status, labels in source.get("labels", {}).items()
               if label in [normalize(item) for item in labels]]
    if len(matches) != 1 or matches[0] not in {"available", "unavailable", "preorder"}:
        return "unknown", "Libellé de stock inconnu"
    return matches[0], stocks[0].get_text(" ", strip=True)


def fetch(source):
    request = Request(source["url"], headers={"User-Agent": "PokemonLocalStockMonitor/1.0"})
    with urlopen(request, timeout=25) as response:
        if response.geturl().rstrip("/") != source["url"].rstrip("/"):
            raise ValueError("Redirection : fiche produit non confirmée")
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError("Réponse non HTML")
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Page trop volumineuse")
        return body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def alert_label(source, status):
    if status == "preorder":
        return "🟠 Précommande"
    if status == "available":
        return "🔵 Achat en ligne" if source.get("channel", "store") == "online" else "🟢 Achat en magasin"
    return "⚪ Disponibilité non confirmée"


def notify(source, status="available", price=None, test=False):
    topic = os.environ.get("NTFY_TOPIC", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", topic):
        raise ValueError("Configurer NTFY_TOPIC avec un nom aléatoire d'au moins 24 caractères")
    label = alert_label(source, status)
    availability = "Réservation avant sortie — pas un stock disponible" if status == "preorder" else "En stock"
    channel = "En ligne" if source.get("channel", "store") == "online" else "En magasin"
    message = f"{label}\n📦 {source['product']}\n📍 {source['store']} — {channel}\n{availability}"
    if price:
        message += f"\n💶 {price}"
    if test:
        message = "🧪 TEST — STOCK FICTIF\n" + message + "\nSimulation uniquement : aucune disponibilité réelle confirmée."
    else:
        message += "\nDisponibilité constatée sur le site ; elle peut changer."
    payload = {"topic": topic, "title": ("TEST — " if test else "") + "Pokémon — " + label,
               "message": message, "click": source["url"], "tags": ["test_tube" if test else "shopping_cart"]}
    request = Request("https://ntfy.sh", data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json",
    }, method="POST")
    with urlopen(request, timeout=20) as response:
        response.read()


def observe(source, html, previous):
    status, detail = classify(html, source)
    if status == "unknown":
        return previous, status, detail
    price = None
    if source.get("price_selector"):
        scope = BeautifulSoup(html, "html.parser").select_one(source["scope_selector"])
        prices = scope.select(source["price_selector"])
        if len(prices) != 1 or not prices[0].get_text(strip=True):
            return previous, "unknown", "Prix suivi absent ou ambigu"
        price = prices[0].get_text(" ", strip=True)
    current = {"status": status, "identity": [source["url"], source["store"], source["product"], source.get("channel", "store")], "price": price}
    # Une précommande reste distincte d'un produit immédiatement disponible.
    if status in {"available", "preorder"} and current != previous:
        notify(source, status=status, price=price)
    return current, status, detail


def test_notification():
    notify({"product": "Coffret Nymphali-ex — Pokémon 30 ans",
            "store": "Métropole lilloise — magasin fictif",
            "url": "https://www.king-jouet.com/pokemon-30-ans-tcg.htm"}, test=True)
    print("Notification TEST acceptée par ntfy. Réception sur le téléphone à confirmer.")


def main():
    sources = json.loads(Path("sources.json").read_text())["sources"]
    state_path = Path("state.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "results": []}
    errors = 0
    seen = set()
    for source in sources:
        validate(source)
        if source["id"] in seen:
            raise ValueError("Identifiant de source dupliqué")
        seen.add(source["id"])
    for source in sources:
        key = source["id"]
        try:
            current, status, detail = observe(source, fetch(source), state.get(key, {}))
            if status == "unknown":
                errors += 1
            else:
                # Ne sauvegarder une alerte qu'après confirmation de son envoi.
                state[key] = current
            report["results"].append({"id": key, "status": status, "detail": detail})
        except Exception as error:
            errors += 1
            # Ne pas afficher les URL d'erreur : elles peuvent contenir le topic secret.
            report["results"].append({"id": key, "status": "unknown", "detail": type(error).__name__})
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    Path("report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    summary = f"{len(sources)} source(s) configurée(s), {errors} contrôle(s) non concluants."
    if not sources:
        summary += " Surveillance inactive : ajouter des sources locales validées."
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            output.write(summary + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-notification", action="store_true")
    arguments = parser.parse_args()
    if arguments.test_notification:
        try:
            test_notification()
        except Exception as error:
            print("Échec du test ntfy : " + type(error).__name__)
            raise SystemExit(1)
    else:
        raise SystemExit(main())
