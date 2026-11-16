#!/usr/bin/env python3
"""
Scarica la "Liturgia delle Ore" dal sito ufficiale della CEI (chiesacattolica.it)
e la salva in ore.json, che la webapp legge senza chiamare servizi esterni.

Uso tipico (lo lancia GitHub Actions ogni mercoledì, insieme alla Messa del Giorno):
    python3 scripts/fetch_ore.py

Opzioni utili:
    --days N              quanti giorni scaricare a partire da oggi (default 14)
    --out FILE            file di destinazione (default ore.json nella root)

Per ogni giorno scarica le ore che la CEI elenca nel menù di quel giorno (Invitatorio, Ufficio
delle letture, Lodi, Ora media [Terza/Sesta/Nona], Vespri, Compieta) e, se il giorno ha memorie
facoltative, anche le loro varianti. Le ore cambiano: il sabato non ci sono Vespri e Compieta
(la sera è già la domenica) e la domenica ci sono Primi e Secondi Vespri con le rispettive Compiete.
Solo libreria standard: non serve installare nulla.
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_liturgia import (  # noqa: E402  (stesso parser HTML e stesse regole di rete della Messa)
    MESI,
    Node,
    clean_text,
    download,
    parse_date_label,
    parse_html,
    walk,
)

BASE_URL = "https://www.chiesacattolica.it/la-liturgia-delle-ore/"
INLINE_CLASSES = {"lo_antifona", "lo_rosso", "lo_normal", "lo_rif"}
SUBTITLE_CLASSES = {"lo_sottotitolo", "lo_sottotitolonoi", "lo_sottotitolorosso"}
INDENT = "&nbsp;&nbsp;&nbsp;"  # rientro dei versi (la CEI lo scrive con una serie di &nbsp;)
ROMAN = re.compile(r"^[IVX]+$")
ANTIPHON_LABEL = re.compile(r"^(\d+\s*)?ant\.(\s*al\s+\w+\.?)?$", re.I)
MIN_HOURS = 3  # ore minime in un giorno (il sabato ce ne sono 4 voci di menù: Invitatorio, Ufficio, Lodi, Ora media)
SKIP_CLASSES = {"share-container", "cci_get_social_share", "cci_get_social_share_buttons"}


# --------------------------------------------------------------------------- #
# Struttura della pagina: una lista piatta di "blocchi"
#
# La CEI scrive ogni ora come una sequenza di <div class="lo_..."> a volte annidati
# (un lo_versetto che contiene un lo_titolo, un lo_sottotitolo che contiene un lo_versetto...).
# Qui la appiattiamo in blocchi (titolo, sottotitolo, nota, testo) nell'ordine del documento.
# --------------------------------------------------------------------------- #
class Block:
    __slots__ = ("kind", "red", "nodes", "loose")

    def __init__(self, kind, red, nodes, loose):
        self.kind, self.red, self.nodes, self.loose = kind, red, nodes, loose


def has_block_descendant(node):
    return any(isinstance(d, Node) and d.tag in ("div", "h2") and not is_inline_div(d) for d in walk(node))


def is_inline_div(node):
    return (node.tag == "div" and bool(INLINE_CLASSES & set(node.classes()))
            and not has_block_descendant(node))


def collect_blocks(node, kind="testo", red=False, root=True, out=None):
    out = [] if out is None else out
    buf = []

    def flush():
        if any((isinstance(c, str) and c.strip()) or isinstance(c, Node) for c in buf):
            out.append(Block(kind, red, list(buf), root))
        buf.clear()

    for child in node.children:
        if isinstance(child, Node) and child.tag in ("div", "h2") and not is_inline_div(child):
            flush()
            if child.tag == "h2":
                out.append(Block("h2", False, [child], False))
                continue
            classes = set(child.classes())
            if classes & SKIP_CLASSES:
                continue  # in alcune pagine la CEI lascia un <div> aperto e i pulsanti "Condividi" finiscono nel testo
            k, r = kind, red
            if kind == "titolo" and classes & {"lo_versetto", "lo_vr"}:
                k = "testo"  # protezione: un <div> di titolo non chiuso non deve trasformare il testo in titoli
            if "lo_titolo" in classes:
                k = "titolo"
            elif classes & SUBTITLE_CLASSES:
                k, r = "sottotitolo", red or "lo_sottotitolorosso" in classes
            elif "lo_nota" in classes:
                k = "nota"
            if "lo_rosso" in classes:
                r = True
            collect_blocks(child, k, r, False, out)
        else:
            buf.append(child)
    flush()
    return out


# --------------------------------------------------------------------------- #
# Da blocco a HTML "sicuro" (solo p, br, strong, em, span.rosso)
# --------------------------------------------------------------------------- #
def render_inline(node):
    if isinstance(node, str):
        text = re.sub(r"[ \t\r\n\f]+", " ", node.replace("​", ""))  # \xa0 resta: serve per i rientri
        return html.escape(text, quote=False)
    if node.tag == "br":
        return "<br>"
    inner = "".join(render_inline(c) for c in node.children)
    classes = set(node.classes())
    if node.tag == "div" and classes & {"lo_antifona", "lo_rosso"}:
        # l'a capo che la CEI mette dentro l'etichetta rossa ("<br> R.") va prima dell'etichetta
        lead = re.match(r"(?:[ \xa0]*<br>)*", inner).group(0)
        rest = inner[len(lead):]
        tail = re.search(r"(?:<br>[ \xa0]*)*$", rest).group(0)
        rest = rest[: len(rest) - len(tail)]
        lead_brs = "<br>" * lead.count("<br>")
        tail_brs = "<br>" * tail.count("<br>")
        core = rest.strip(" \xa0")
        if not core:
            return lead_brs + rest + tail_brs
        # gli spazi stanno fuori dall'etichetta rossa, non dentro
        before = " " if (rest[:1] in (" ", "\xa0") and not lead_brs) else ""
        after = " " if (rest[-1:] in (" ", "\xa0") and not tail_brs) else ""
        return f'{lead_brs}{before}<span class="rosso">{core}</span>{after}{tail_brs}'
    if node.tag == "div" and "lo_rif" in classes:
        return " " + inner
    if node.tag in ("strong", "b"):
        return f"<strong>{inner}</strong>" if inner.strip() else inner
    if node.tag in ("em", "i"):
        return f"<em>{inner}</em>" if inner.strip() else inner
    return inner  # qualsiasi altro tag: teniamo solo il testo


def tidy(markup):
    # rientri: "<br> &nbsp;&nbsp;&nbsp;verso" -> un rientro fisso; i \xa0 a metà riga sono spazi normali
    markup = re.sub(r"<br>([ \xa0]*)(?=\S)(?!<br>)", lambda m: "<br>" + (INDENT if "\xa0" in m.group(1) else ""), markup)
    markup = re.sub(r"^[ \xa0]+", "", markup)
    markup = markup.replace("\xa0", " ")
    markup = re.sub(r" {2,}", " ", markup)
    markup = re.sub(r"[ \t]*<br>[ \t]*", "<br>", markup)
    markup = re.sub(r"(<br>){3,}", "<br><br>", markup)
    markup = re.sub(r"^(<br>)+|(<br>)+$", "", markup.strip())
    return markup.strip()


def render_block(block):
    markup = tidy("".join(render_inline(c) for c in block.nodes))
    if not re.sub(r"<[^>]+>|&nbsp;|\s", "", markup):
        return ""
    if block.kind == "sottotitolo" and not block.red:
        markup = f"<em>{markup}</em>"
    elif block.kind == "nota" and not block.red:
        markup = f"<em>{markup}</em>"
    elif block.red:
        markup = f'<span class="rosso">{markup}</span>'
    return markup


def title_parts(block):
    """Il titolo di una sezione è spesso "SALMO 94 <spazi> Invito a lodare Dio": lo separiamo in parti."""
    pieces = []

    def rec(n):
        if isinstance(n, str):
            pieces.append(re.sub(r"[ \t\r\n\f]+", " ", n.replace("​", "")))
        elif n.tag == "br":
            pieces.append("\n")
        elif n.tag == "div" and "lo_rif" in n.classes():
            pieces.append("\n" + clean_text(n))
        else:
            for c in n.children:
                rec(c)

    for n in block.nodes:
        rec(n)
    text = "".join(pieces)
    text = re.sub(r"[ \xa0]{2,}", lambda m: "\n" if "\xa0" in m.group(0) else " ", text)
    text = text.replace("\xa0", " ")
    return [re.sub(r"\s+", " ", p).strip() for p in text.split("\n") if p.strip()]


# --------------------------------------------------------------------------- #
# Da blocchi a sezioni
# --------------------------------------------------------------------------- #
def antiphon_label(markup):
    m = re.match(r'<span class="rosso">([^<]*)</span>', markup)
    return m.group(1).strip() if m else None


def is_antiphon(markup):
    label = antiphon_label(markup)
    return bool(label and ANTIPHON_LABEL.match(label))


def finalize(sec):
    """Se l'antifona di apertura sta DOPO il titolo (primo blocco di testo della sezione), la porta prima."""
    if not sec["antifona"]:
        for k, (markup, kind, _) in enumerate(sec["items"][:3]):
            if kind in ("sottotitolo", "sub"):
                continue  # l'epigrafe del salmo può precedere l'antifona: si salta
            if is_antiphon(markup):
                sec["antifona"] = sec["items"].pop(k)[0]
            break
    return sec


def build_sections(blocks):
    """Sezioni {titolo, sottotitolo, antifona, html}. L'antifona di apertura va SEMPRE prima del titolo
    (nella webapp è un campo a parte); nel testo restano solo l'epigrafe, i versetti e l'antifona di chiusura."""
    sections = []
    cur = {"titolo": "", "sottotitolo": "", "antifona": "", "items": []}  # items: (markup, kind, loose)
    for b in blocks:
        if b.kind == "titolo":
            parts = title_parts(b)
            if not parts:
                continue
            if ROMAN.match(parts[0]) and len(" ".join(parts)) < 24:
                # "I (1-11)", "II (12-21)": parti di uno stesso salmo, restano nella sezione
                cur["items"].append((f"<strong>{html.escape(' '.join(parts), quote=False)}</strong>", "sub", False))
                continue
            finalize(cur)
            carry = ""
            items = cur["items"]
            if items and is_antiphon(items[-1][0]) and items[-1][0] != cur["antifona"]:
                carry = items.pop()[0]  # antifona scritta subito prima del titolo: apre la sezione che segue
                # (se è uguale a quella con cui si apre il salmo è l'antifona di chiusura, ripetuta: resta dov'è)
            sections.append(cur)
            cur = {"titolo": parts[0], "sottotitolo": " – ".join(parts[1:]), "antifona": carry, "items": []}
            continue
        markup = render_block(b)
        if markup:
            cur["items"].append((markup, b.kind, b.loose))
    finalize(cur)
    sections.append(cur)

    result = []
    for s in sections:
        if not s["items"] and not s["antifona"]:
            continue
        out = ""
        for k, (markup, kind, loose) in enumerate(s["items"]):
            if k:
                prev_kind = s["items"][k - 1][1]
                tight = loose or prev_kind == "sub" or (prev_kind == "sottotitolo" and kind == "sottotitolo")
                out += "<br>" if tight else "<br><br>"
            out += markup
        result.append({"titolo": s["titolo"], "sottotitolo": s["sottotitolo"],
                       "antifona": f"<p>{s['antifona']}</p>" if s["antifona"] else "",
                       "html": f"<p>{out}</p>" if out else ""})
    return result


def split_groups(blocks):
    """L'"Ora media" contiene tre ore (Ora terza, sesta, nona) separate da un <h2>."""
    groups, name = [], None
    cur = []
    for b in blocks:
        if b.kind == "h2":
            if cur:
                groups.append((name, cur))
            name, cur = clean_text(b.nodes[0]), []
        else:
            cur.append(b)
    if cur:
        groups.append((name, cur))
    return groups


# --------------------------------------------------------------------------- #
# Estrazione dalla pagina
# --------------------------------------------------------------------------- #
def parse_hour_page(source):
    root = parse_html(source)

    title = ""
    box = None
    memorie = []
    menu = []  # [(valore del parametro "ora", nome)] nell'ordine del sito
    giorno = ""  # "LUNEDI' - XXXIII SETTIMANA DEL TEMPO ORDINARIO…", "NOSTRO SIGNORE GESU' CRISTO RE… - Solennità"
    for node in walk(root):
        if node.tag == "title" and not title:
            title = clean_text(node)
        elif node.tag == "div" and node.has_class("cci-opere-giorni-liturgia") and not giorno:
            giorno = clean_text(node)
        elif node.tag == "ul" and node.has_class("cci-liturgia-ore-menu") and not menu:
            for a in walk(node):
                m = re.search(r"[?&]ora=([a-z0-9-]+)", a.attrs.get("href") or "") if a.tag == "a" else None
                if m and clean_text(a):
                    menu.append((m.group(1), clean_text(a)))
        elif node.tag == "div" and box is None and node.has_class("cci-liturgia-ore"):
            box = node
        elif node.tag == "div" and node.has_class("memoria") and node.has_class("liturgia-delle-ore"):
            name_node = next((d for d in walk(node) if d.has_class("titolo_memoria")), None)
            if name_node is not None:
                m = re.search(r"memoria=(\d+)", name_node.attrs.get("href") or "")
                memorie.append({"titolo": clean_text(name_node),
                                "memoria": int(m.group(1)) if m else None,
                                "selected": node.has_class("selected")})

    # La data vera sta nel <title> ("Liturgia delle ore - Lodi mattutine - 16 Novembre 2026 - sito ufficiale…").
    # ATTENZIONE: h3.day è la data di OGGI nell'intestazione del sito, non quella richiesta.
    m = re.match(r"\s*Liturgia delle ore\s*-\s*(.+?)\s*-\s*(\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})\s*-", title, re.I)
    ora_name, day_label = (m.group(1), m.group(2)) if m else ("", "")

    groups = []
    if box is not None:
        for name, blocks in split_groups(collect_blocks(box)):
            sections = build_sections(blocks)
            if sections:
                groups.append((name, sections))
    return {"oraName": ora_name, "dataLabel": day_label, "groups": groups, "memorie": memorie, "menu": menu,
            "giorno": giorno}


ACCENTI = {"A": "À", "E": "È", "I": "Ì", "O": "Ò", "U": "Ù"}


def clean_title(text):
    """La CEI scrive gli accenti maiuscoli come apostrofo: "LUNEDI'" -> "LUNEDÌ", "GESU'" -> "GESÙ"."""
    text = re.sub(r"(?<=[A-Z])([AEIOU])'(?=\s|$)", lambda m: ACCENTI[m.group(1)], text)
    return re.sub(r"\s+", " ", text).strip()


def hour_entries(slug, nome, parsed):
    """Una pagina -> una o più ore (l'Ora media diventa Terza, Sesta, Nona)."""
    entries = []
    for name, sections in parsed["groups"]:
        if slug == "ora-media" and name:
            short = re.sub(r"^ora\s+", "", name, flags=re.I).strip().capitalize()
            entries.append({"id": short.lower(), "nome": short, "sezioni": sections})
        else:
            entries.append({"id": slug, "nome": nome[:1].upper() + nome[1:], "sezioni": sections})
    return entries


def validate_hour(parsed, nome, expected):
    found = parse_date_label(parsed["dataLabel"])
    if not found:
        raise ValueError(f"{nome}: la pagina non indica la data: è cambiata?")
    if found != expected:
        raise ValueError(f"{nome}: data nella pagina ({found}) diversa da quella richiesta ({expected})")
    if parsed["oraName"].casefold() != nome.casefold():
        raise ValueError(f"{nome}: la pagina è un'altra ora ({parsed['oraName']!r})")
    text = sum(len(re.sub(r"<[^>]+>", "", s["html"] + s["antifona"])) for _, secs in parsed["groups"] for s in secs)
    if not parsed["groups"] or text < 300:
        raise ValueError(f"{nome}: testo troppo corto ({text} caratteri), la pagina è cambiata?")


# --------------------------------------------------------------------------- #
# Rete e file
# --------------------------------------------------------------------------- #
def page_url(day, slug=None, memoria=None):
    url = f"{BASE_URL}?data-liturgia={day:%Y%m%d}"
    if memoria:
        url += f"&memoria={memoria}"
    if slug:
        url += f"&ora={slug}"
    return url


def fetch_celebration(day, memoria, menu, pause):
    """Tutte le ore del menù di una celebrazione. Se una manca, solleva l'errore (giorno incompleto)."""
    ore, label = [], ""
    for slug, nome in menu:
        parsed = parse_hour_page(download(page_url(day, slug, memoria)))
        try:
            validate_hour(parsed, nome, day)
        except ValueError as exc:
            raise ValueError(f"{nome}: {exc}") from None
        ore.extend(hour_entries(slug, nome, parsed))
        label = label or parsed["dataLabel"]
        time.sleep(pause)
    return ore, label


def build_entry(day, pause=0.8):
    # la pagina senza "ora" dice quali ore ci sono quel giorno e quali celebrazioni (memorie facoltative)
    first = parse_hour_page(download(page_url(day)))
    time.sleep(pause)
    menu = first["menu"]
    if len(menu) < MIN_HOURS:
        raise ValueError(f"il menù delle ore ha solo {len(menu)} voci: la pagina è cambiata?")
    memorie = first["memorie"]
    titles = [clean_title(m["titolo"]) for m in memorie]

    ore, label = fetch_celebration(day, None, menu, pause)
    celebrazioni = [{"titolo": titles[0] if len(memorie) > 1 else "", "ore": ore}]
    for m, titolo in zip(memorie, titles):
        if m["memoria"] is None:
            continue
        try:
            extra, _ = fetch_celebration(day, m["memoria"], menu, pause)
        except Exception as exc:  # una memoria che non si scarica non fa saltare il giorno
            print(f"     manca la celebrazione {titolo!r}: {exc}", file=sys.stderr)
            continue
        celebrazioni.append({"titolo": titolo, "ore": extra})
    nomi_mesi = {v: k.capitalize() for k, v in MESI.items()}
    return {
        "data": day.isoformat(),
        "dataLabel": label or f"{day.day:02d} {nomi_mesi[day.month]} {day.year}",
        "giorno": clean_title(first["giorno"]) or (titles[0] if titles else ""),
        "url": page_url(day),
        "celebrazioni": celebrazioni,
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
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "ore.json"))
    args = ap.parse_args()

    out = Path(args.out)
    giorni = load_existing(out)
    today = datetime.now(ZoneInfo("Europe/Rome")).date()

    for i in range(args.days):
        day = today + timedelta(days=i)
        try:
            giorni[f"{day:%Y%m%d}"] = build_entry(day)
            print(f"OK   {day}")
        except Exception as exc:  # un giorno che fallisce non blocca gli altri
            print(f"ERR  {day}: {exc}", file=sys.stderr)

    # teniamo da ieri in poi (utile a chi ha il telefono con un altro fuso orario)
    oldest = f"{today - timedelta(days=1):%Y%m%d}"
    giorni = {k: v for k, v in sorted(giorni.items()) if k >= oldest}

    payload = {"fonte": BASE_URL, "giorni": giorni}
    new_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    old_text = out.read_text(encoding="utf-8") if out.exists() else ""
    if not giorni and not out.exists():
        print("Nessun dato scaricato: non creo un file vuoto")
    elif new_text != old_text:
        out.write_text(new_text, encoding="utf-8")
        print(f"Scritto {out} ({len(giorni)} giorni)")
    else:
        print("Nessun cambiamento")

    if f"{today:%Y%m%d}" not in giorni:
        print("ERRORE: la Liturgia delle Ore di oggi non è disponibile", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
