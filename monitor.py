"""Contrôle prudent de pages produit affichant explicitement un stock local."""
import json
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
    if source.get("local_stock_verified") is not True:
        raise ValueError("Source de stock local non validée")


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


def notify(source, status):
    topic = os.environ.get("NTFY_TOPIC", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", topic):
        raise ValueError("Configurer NTFY_TOPIC avec un nom aléatoire d'au moins 24 caractères")
    message = f"{'Disponible' if status == 'available' else 'Précommande'} : {source['product']}\n{source['store']}\n{source['url']}"
    request = Request("https://ntfy.sh/" + topic, data=message.encode(), headers={
        "Title": "Pokemon - stock local", "Click": source["url"],
        "Content-Type": "text/plain; charset=utf-8",
    }, method="POST")
    with urlopen(request, timeout=20) as response:
        response.read()


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
            status, detail = classify(fetch(source), source)
            if status == "unknown":
                errors += 1
            else:
                previous = state.get(key, {})
                identity = [source["url"], source["store"], source["product"]]
                changed = previous.get("status") != status or previous.get("identity") != identity
                if changed and status in {"available", "preorder"}:
                    notify(source, status)
                # Ne sauvegarder une alerte qu'après confirmation de son envoi.
                state[key] = {"status": status, "identity": identity}
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
    raise SystemExit(main())
