#!/usr/bin/env python3
"""
Scarica la "Messa del Giorno" dal sito ufficiale della CEI (chiesacattolica.it)
e la salva in liturgia.json, che la webapp legge senza chiamare servizi esterni.

Uso tipico (lo lancia GitHub Actions ogni mercoledì):
    python3 scripts/fetch_liturgia.py

Opzioni utili:
    --days N              quanti giorni scaricare a partire da oggi (default 14)
    --out FILE            file di destinazione (default liturgia.json nella root)
    --html-file F --date YYYYMMDD
                          analizza una pagina salvata in locale (per i test)

Solo libreria standard: non serve installare nulla.
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = "https://www.chiesacattolica.it/liturgia-del-giorno/"
USER_AGENT = "pg-pitigliano-app/1.0 (+https://github.com/tvicxx/pg-pitigliano-app)"
MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "area", "base",
             "col", "embed", "param", "track", "wbr"}


# --------------------------------------------------------------------------- #
# Piccolo parser HTML -> albero (la libreria standard non ne ha uno pronto)
# --------------------------------------------------------------------------- #
class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = attrs
        self.children = []
        self.parent = parent

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def has_class(self, name):
        return name in self.classes()


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(node)
        if tag not in VOID_TAGS:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(source):
    builder = TreeBuilder()
    builder.feed(source)
    builder.close()
    return builder.root


def walk(node):
    for child in node.children:
        if isinstance(child, Node):
            yield child
            yield from walk(child)


def element_children(node):
    return [c for c in node.children if isinstance(c, Node)]


def text_of(node):
    if isinstance(node, str):
        return node
    return "".join(text_of(c) for c in node.children)


def clean_text(node):
    return re.sub(r"\s+", " ", text_of(node)).strip()


# --------------------------------------------------------------------------- #
# Conversione del corpo di una sezione in HTML "sicuro" (solo tag nostri)
# --------------------------------------------------------------------------- #
def render_inline(node):
    if isinstance(node, str):
        return html.escape(re.sub(r"\s+", " ", node), quote=False)
    if node.tag == "br":
        return "<br>"
    inner = "".join(render_inline(c) for c in node.children)
    if not inner.strip():
        return inner
    if node.tag in ("strong", "b"):
        return f"<strong>{inner}</strong>"
    if node.tag in ("em", "i"):
        return f"<em>{inner}</em>"
    if node.tag == "span" and node.has_class("cci-liturgia-giorno-testo-rosso"):
        return f'<span class="rosso">{inner}</span>'
    return inner  # qualsiasi altro tag (a, span, ...): teniamo solo il testo


def tidy(markup):
    markup = re.sub(r"[ \t]*<br>[ \t]*", "<br>", markup)
    markup = re.sub(r"(<br>){3,}", "<br><br>", markup)
    markup = re.sub(r"^(<br>)+|(<br>)+$", "", markup.strip())
    return markup.strip()


def render_body(content_div):
    paragraphs = []
    for child in element_children(content_div):
        if not clean_text(child):
            continue
        markup = tidy("".join(render_inline(c) for c in child.children))
        if markup:
            paragraphs.append(f"<p>{markup}</p>")
    return "".join(paragraphs)


# --------------------------------------------------------------------------- #
# Estrazione dalla pagina
# --------------------------------------------------------------------------- #
def parse_date_label(label):
    m = re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})", label or "")
    if not m or m.group(2).lower() not in MESI:
        return None
    return date(int(m.group(3)), MESI[m.group(2).lower()], int(m.group(1)))


def parse_page(source):
    root = parse_html(source)

    # Ogni messa inizia con un titolo (h3) e i suoi riquadri lo seguono nel documento.
    # Quasi sempre c'è una sola messa; il 2 novembre ce ne sono tre.
    # ATTENZIONE: h3.day è la data di OGGI nell'intestazione del sito, non quella
    # della liturgia richiesta: non va usata.
    messe = []
    for node in walk(root):
        if node.tag == "h3" and node.has_class("cci_content_single_title"):
            messe.append({"titolo": clean_text(node), "sezioni": []})
            continue
        if node.tag != "div" or not node.has_class("cci-liturgia-giorno-dettagli-content"):
            continue
        box = node
        if not messe:
            messe.append({"titolo": "", "sezioni": []})
        titolo = sottotitolo = versetto = ""
        body = ""
        for child in element_children(box):
            if child.tag == "h2" and child.has_class("cci-liturgia-giorno-section-title"):
                titolo = clean_text(child)
            elif child.tag == "h3" and child.has_class("cci-liturgia-giorno-section-subtitle"):
                sottotitolo = clean_text(child)
            elif child.has_class("cci-liturgia-giorno-section-versetto"):
                versetto = clean_text(child)
            elif child.tag == "div" and child.has_class("cci-liturgia-giorno-section-content"):
                body = render_body(child)
        if body:  # una sezione senza testo non serve alla webapp
            messe[-1]["sezioni"].append({
                "titolo": titolo,
                "sottotitolo": sottotitolo,
                "versetto": versetto,
                "html": body,
            })
    messe = [m for m in messe if m["sezioni"]]

    # La data vera sta in og:url (…?data-liturgia=YYYYMMDD) e nel <title>
    # ("Liturgia del giorno 09 Novembre 2026 - NOME DEL GIORNO - sito ufficiale…").
    title = ""
    og_date = None
    for node in walk(root):
        if node.tag == "title" and not title:
            title = clean_text(node)
        elif node.tag == "meta" and node.attrs.get("property") == "og:url" and og_date is None:
            m = re.search(r"data-liturgia=(\d{8})", node.attrs.get("content") or "")
            if m:
                try:
                    og_date = datetime.strptime(m.group(1), "%Y%m%d").date()
                except ValueError:
                    pass

    day_label, nome = "", ""
    m = re.match(r"\s*Liturgia del giorno\s+(\d{1,2}\s+\S+\s+\d{4})\s*-?\s*(.*)", title)
    if m:
        day_label = m.group(1)
        nome = re.sub(r"\s*-\s*sito ufficiale.*$", "", m.group(2)).strip()

    titles = [x["titolo"] for x in messe if x["titolo"]]
    if len(messe) > 1 and titles:
        # più messe: il nome del giorno è il titolo senza "(MESSA n)"
        giorno = re.sub(r"\s*\(MESSA\s*\d+\)\s*$", "", titles[0], flags=re.I)
    elif titles:
        giorno = titles[0]
        messe[0]["titolo"] = ""  # una sola messa: il titolo è già il nome del giorno
    else:
        giorno = nome

    return {"dataLabel": day_label, "giorno": giorno, "messe": messe, "ogDate": og_date}


def validate(parsed, expected):
    dates = {"og:url": parsed["ogDate"], "title": parse_date_label(parsed["dataLabel"])}
    known = {k: v for k, v in dates.items() if v}
    if not known:
        raise ValueError("la pagina non indica la data della liturgia: è cambiata?")
    for where, found in known.items():
        if found != expected:
            raise ValueError(f"data nella pagina ({where}: {found}) diversa da quella richiesta ({expected})")
    if not parsed["messe"]:
        raise ValueError("nessuna sezione con testo trovata: la pagina è cambiata?")
    for m in parsed["messe"]:
        if len(m["sezioni"]) < 3:
            raise ValueError(f"messa {m['titolo']!r}: solo {len(m['sezioni'])} sezioni con testo, la pagina è cambiata?")


# --------------------------------------------------------------------------- #
# Rete e file
# --------------------------------------------------------------------------- #
def page_url(day):
    return f"{BASE_URL}?data-liturgia={day:%Y%m%d}"


def download(url, attempts=3):
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "it"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"download fallito per {url}: {last}")


def build_entry(day, source):
    parsed = parse_page(source)
    validate(parsed, day)
    nomi_mesi = {v: k.capitalize() for k, v in MESI.items()}
    return {
        "data": day.isoformat(),
        "dataLabel": parsed["dataLabel"] or f"{day.day:02d} {nomi_mesi[day.month]} {day.year}",
        "giorno": parsed["giorno"],
        "url": page_url(day),
        "messe": parsed["messe"],
    }


def load_existing(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("giorni", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "liturgia.json"))
    ap.add_argument("--html-file")
    ap.add_argument("--date", help="YYYYMMDD, solo con --html-file")
    args = ap.parse_args()

    out = Path(args.out)
    giorni = load_existing(out)
    today = datetime.now(ZoneInfo("Europe/Rome")).date()

    if args.html_file:
        if not args.date:
            ap.error("--html-file richiede --date")
        day = datetime.strptime(args.date, "%Y%m%d").date()
        source = Path(args.html_file).read_text(encoding="utf-8")
        giorni[f"{day:%Y%m%d}"] = build_entry(day, source)
        today = day
    else:
        for i in range(args.days):
            day = today + timedelta(days=i)
            try:
                giorni[f"{day:%Y%m%d}"] = build_entry(day, download(page_url(day)))
                print(f"OK   {day}")
            except Exception as exc:  # un giorno che fallisce non blocca gli altri
                print(f"ERR  {day}: {exc}", file=sys.stderr)
            if i < args.days - 1:
                time.sleep(1)  # una richiesta al secondo, senza stressare il sito

    # teniamo da ieri in poi (utile a chi ha il telefono con un altro fuso orario)
    oldest = f"{today - timedelta(days=1):%Y%m%d}"
    giorni = {k: v for k, v in sorted(giorni.items()) if k >= oldest}

    payload = {"fonte": BASE_URL, "giorni": giorni}
    new_text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    old_text = out.read_text(encoding="utf-8") if out.exists() else ""
    if not giorni and not out.exists():
        print("Nessun dato scaricato: non creo un file vuoto")
    elif new_text != old_text:
        out.write_text(new_text, encoding="utf-8")
        print(f"Scritto {out} ({len(giorni)} giorni)")
    else:
        print("Nessun cambiamento")

    if f"{today:%Y%m%d}" not in giorni:
        print("ERRORE: la liturgia di oggi non è disponibile", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
