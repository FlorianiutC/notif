"""Catalogue autonome : découverte, validation et archivage prudent, sans modèle payant."""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from monitor import normalize

AGENT = "PokemonLinkCatalogBot"
MAX_BYTES = 2_000_000


def canonical(url, base, host):
    """Uniquement HTTPS et le domaine configuré, sans identifiants ni fragments."""
    parsed = urlsplit(urljoin(base, url))
    if (parsed.scheme != "https" or parsed.netloc != host
            or parsed.username or parsed.password):
        return None
    return urlunsplit(("https", host, parsed.path, parsed.query, ""))


def relevant(title):
    text = normalize(title)
    anniversary = re.search(r"\b30a\b|\b30\s*(?:e|eme|th)?\s*(?:anniversaire|anniversary|celebration|ans)\b", text)
    category = re.search(r"coffret|bundle|duopack|duo pack|tripack|tri pack|\betb\b|\bupc\b|mini.?tin|pokebox|tin.?box|booster|dresseur|ultra.?premium", text)
    return "pokemon" in text and bool(anniversary and category)


def product_title(html):
    """Ne pas utiliser tout le texte : le menu '30 ans' figure sur d'autres produits."""
    soup = BeautifulSoup(html, "html.parser")
    headings = soup.select("h1")
    if len(headings) == 1:
        title = headings[0].get_text(" ", strip=True)
        if relevant(title):
            return title[:300]
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            todo = [json.loads(script.get_text())]
        except (ValueError, TypeError):
            continue
        while todo:
            item = todo.pop()
            if isinstance(item, list):
                todo.extend(item)
            elif isinstance(item, dict):
                kind = item.get("@type", [])
                if isinstance(kind, str):
                    kind = [kind]
                name = item.get("name", "")
                if "Product" in kind and isinstance(name, str) and relevant(name):
                    return name[:300]
                graph = item.get("@graph")
                if isinstance(graph, (list, dict)):
                    todo.append(graph)
    return None


class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urlsplit(req.full_url).netloc
        if not canonical(newurl, req.full_url, host):
            raise ValueError("Redirection externe refusée")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, maximum):
        self.remaining = maximum
        self.robots = {}
        self.opener = build_opener(SameHostRedirect())

    def raw(self, url):
        if self.remaining <= 0:
            return None, url, ""
        self.remaining -= 1
        time.sleep(1)
        try:
            with self.opener.open(Request(url, headers={"User-Agent": AGENT + "/1.0"}), timeout=15) as response:
                content = response.read(MAX_BYTES + 1)
                if len(content) > MAX_BYTES:
                    return None, url, ""
                return response.status, response.geturl(), content.decode("utf-8", "replace")
        except HTTPError as error:
            return error.code, url, ""
        except (URLError, ValueError, TimeoutError, OSError):
            return None, url, ""

    def get(self, url):
        host = urlsplit(url).netloc
        if host not in self.robots:
            code, _, text = self.raw("https://" + host + "/robots.txt")
            parser = RobotFileParser()
            if code == 200:
                parser.parse(text.splitlines())
                # Ne pas ignorer une cadence explicite plus lente que celle de ce bot.
                delay = parser.crawl_delay(AGENT) or parser.crawl_delay("*") or 0
                rate = parser.request_rate(AGENT) or parser.request_rate("*")
                self.robots[host] = parser if delay <= 1 and (not rate or rate.requests >= rate.seconds) else None
            elif code in (404, 410):
                parser.parse([])
                self.robots[host] = parser
            else:
                self.robots[host] = None
        parser = self.robots[host]
        if parser is None or not parser.can_fetch(AGENT, url):
            return None, url, ""
        return self.raw(url)


def update_record(record, code, title, now, final_url):
    record["checked_at"] = now
    record["http_status"] = code
    if code == 200 and title:
        record.update(status="valid", title=title, final_url=final_url, dead_checks=0, first_dead_at=None)
    elif code in (404, 410):
        if not record.get("first_dead_at"):
            record["first_dead_at"] = now
        record["dead_checks"] = record.get("dead_checks", 0) + 1
        elapsed = (datetime.fromisoformat(now) - datetime.fromisoformat(record["first_dead_at"])).total_seconds()
        record["status"] = "archived" if record["dead_checks"] >= 3 and elapsed >= 48 * 3600 else "suspect"
    else:
        # Un blocage, une redirection vers une catégorie ou une page JS ne prouve pas une suppression.
        record["status"] = "unknown" if record.get("status") != "archived" else "archived"
        record["dead_checks"] = 0
        record["first_dead_at"] = None


def run(config, database, client, now):
    products = database["products"]
    candidates = {}
    site_health = {}
    for site in config["sites"]:
        for url in site.get("product_seeds", []):
            if canonical(url, url, site["host"]) and re.search(site["product_path"], urlsplit(url).path):
                candidates[url] = site
        queue = list(site["seeds"])
        visited = set()
        site_health[site["id"]] = {"pages_read": 0, "unreadable": 0}
        while queue and len(visited) < 3:
            url = queue.pop(0)
            if url in visited or not canonical(url, url, site["host"]):
                continue
            visited.add(url)
            code, final, html = client.get(url)
            if code != 200:
                site_health[site["id"]]["unreadable"] += 1
                continue
            site_health[site["id"]]["pages_read"] += 1
            for link in BeautifulSoup(html, "html.parser").select("a[href]"):
                target = canonical(link["href"], final, site["host"])
                if not target:
                    continue
                path = urlsplit(target).path
                label = link.get_text(" ", strip=True) + " " + path.replace("-", " ")
                if re.search(site["product_path"], path) and relevant(label):
                    candidates[target] = site
                elif re.search(site["listing_path"], path) and target not in visited:
                    queue.append(target)
    # Les moins récemment vérifiés passent d'abord ; les archives sont aussi revérifiées.
    by_id = {site["id"]: site for site in config["sites"]}
    known = sorted(products, key=lambda url: products[url].get("checked_at", ""))
    # Réserver de la place aux nouveautés même quand le catalogue devient volumineux.
    new = [url for url in sorted(candidates) if url not in products]
    new_slots = max(1, config["max_product_checks"] // 2)
    tasks = list(dict.fromkeys(new[:new_slots] + known + new[new_slots:]))
    events = []
    for url in tasks[:config["max_product_checks"]]:
        if client.remaining <= 0:
            break
        existing = products.get(url)
        site = candidates.get(url) or by_id.get((existing or {}).get("site"))
        if not site or not canonical(url, url, site["host"]):
            continue
        code, final, html = client.get(url)
        title = product_title(html) if code == 200 and re.search(site["product_path"], urlsplit(final).path) else None
        # Une suggestion issue d'une liste n'est enregistrée qu'après validation de sa fiche.
        if existing is None and not title:
            continue
        record = existing or {"site": site["id"], "discovered_at": now, "stock_local_verified": False}
        old_status = record.get("status")
        old_title = record.get("title")
        update_record(record, code, title, now, final)
        products[url] = record
        if (record["status"] == "valid" and (old_status != "valid" or old_title != title)) or (record["status"] == "archived" and old_status != "archived"):
            events.append({"url": url, "status": record["status"]})
    database.update(last_run=now, sites=site_health)
    return events


def main():
    config = json.loads(Path("link_sites.json").read_text())
    path = Path("data/links.json")
    database = json.loads(path.read_text())
    now = datetime.now(timezone.utc).isoformat()
    events = run(config, database, Client(config["max_requests"]), now)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(database, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)
    counts = {status: sum(p["status"] == status for p in database["products"].values())
              for status in ("valid", "suspect", "unknown", "archived")}
    summary = f"Catalogue de liens (pas un relevé de stock) : {counts}. Changements : {len(events)}."
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            output.write(summary + "\n\n")
            for site, health in database["sites"].items():
                output.write(f"- {site}: {health['pages_read']} pages lues, {health['unreadable']} inaccessibles.\n")
    # Les notifications de catalogue sont délibérément distinctes des alertes de stock.
    if events and os.environ.get("NTFY_TOPIC"):
        from urllib.request import urlopen
        topic = os.environ["NTFY_TOPIC"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", topic):
            raise ValueError("Secret NTFY_TOPIC invalide")
        message = f"Catalogue Pokémon : {len(events)} changement(s).\nCeci ne confirme aucun stock local.\nhttps://github.com/FlorianiutC/notif/blob/main/data/links.json"
        try:
            with urlopen(Request("https://ntfy.sh/" + topic, data=message.encode(), headers={"Title": "Pokemon - mise a jour des liens"}), timeout=20) as response:
                response.read()
        except Exception:
            print("Notification non envoyée ; consulter le catalogue.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
