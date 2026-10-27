"""
ErEkon – automatické zverejňovanie Tipu dňa na Instagram.

Použitie (spúšťa GitHub Actions, ručne netreba):
  python publikuj.py priprav      -> nájde dnešný tip a vyrobí obrázok obrazky/tip-RRRR-MM-DD.jpg
  python publikuj.py zverejni     -> uverejní pripravený obrázok na Instagram
  python publikuj.py obnov-token  -> predĺži platnosť Instagram tokenu (vypíše nový token)

Premenné prostredia:
  IG_TOKEN     Instagram prístupový token (GitHub secret)
  IG_USER_ID   číslo Instagram účtu (GitHub secret)
  DATUM        voliteľne iný dátum vo formáte RRRR-MM-DD (na skúšku)
  VYNUTIT      "1" = zverejniť aj keď už tento deň bol zverejnený
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TIPY_URL = os.environ.get("TIPY_URL", "https://www.erekon.eu/tipy.js")
LOGO_URL = os.environ.get("LOGO_URL", "https://www.erekon.eu/logo-erekon.png")
API = "https://graph.instagram.com/v25.0"

ROOT = Path(__file__).resolve().parent
OBRAZKY = ROOT / "obrazky"
DENNIK = ROOT / "zverejnene.txt"
DNES_JSON = ROOT / "obrazky" / "dnes.json"

HASHTAGY = "#ucto #uctovnictvo #dane #podnikanie #zivnostnik #sro #dph #mzdy #erekon"


# ---------------------------------------------------------------- pomocné
def dnes() -> date:
    if os.environ.get("DATUM"):
        return date.fromisoformat(os.environ["DATUM"])
    return datetime.now(ZoneInfo("Europe/Bratislava")).date()


def stiahni(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "erekon-instagram-tipy"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def nacitaj_tipy() -> list:
    """Načíta tipy.js z webu (alebo z lokálneho súboru TIPY_SUBOR) a vráti zoznam tipov."""
    if os.environ.get("TIPY_SUBOR"):
        js = Path(os.environ["TIPY_SUBOR"]).read_text(encoding="utf-8")
    else:
        js = stiahni(TIPY_URL).decode("utf-8")
    # tipy.js je JavaScript (const TIPY = [...]) – vyhodnotí ho Node.js
    kod = js + "\n;process.stdout.write(JSON.stringify(TIPY));"
    out = subprocess.run(["node", "-e", kod], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def popis(tip: dict) -> str:
    kat = re.sub(r"[^a-z0-9]", "", bez_diakritiky(tip["kategoria"]).lower())
    tagy = HASHTAGY if not kat or f"#{kat} " in HASHTAGY + " " else f"#{kat} " + HASHTAGY
    return (
        f"💡 {tip['titulok']}\n\n"
        f"{tip['text']}\n\n"
        "Každý deň nový tip na www.erekon.eu/tipy 👉 odkaz v profile\n"
        "Potrebujete pomôcť s účtovníctvom? Napíšte nám.\n\n"
        f"{tagy}"
    )


def uz_zverejnene(d: date) -> bool:
    return DENNIK.exists() and d.isoformat() in DENNIK.read_text(encoding="utf-8").split()


# ---------------------------------------------------------------- obrázok
SABLONA = """<!doctype html><html lang="sk"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=block" rel="stylesheet">
<style>
* { margin:0; box-sizing:border-box; }
body { width:1080px; height:1350px; font-family:'Inter',sans-serif; background:#1a6b54; color:#fff; overflow:hidden; }
.wrap { position:relative; height:100%; padding:80px 90px 76px; display:flex; flex-direction:column; }
.top { display:flex; justify-content:space-between; align-items:center; }
.logo { background:#fff; border-radius:24px; padding:18px 30px; display:flex; align-items:center; }
.logo img { height:96px; width:auto; display:block; }
.logo span { font-size:40px; font-weight:800; color:#1a6b54; }
.date { font-size:30px; font-weight:600; opacity:.8; letter-spacing:.03em; }
.label { margin-top:56px; display:flex; align-items:center; gap:18px; }
.label .tip { font-size:30px; font-weight:700; color:#f2c14e; letter-spacing:.12em; text-transform:uppercase; }
.badge { background:#f2c14e; color:#123f33; padding:10px 22px; border-radius:40px; font-size:24px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; }
h1 { margin-top:24px; font-size:72px; line-height:1.08; font-weight:800; letter-spacing:-.015em; }
.card { margin-top:50px; background:#fff; color:#1d2b27; border-radius:28px; padding:50px 56px; font-size:36px; line-height:1.45; }
.foot { margin-top:auto; padding-top:36px; display:flex; justify-content:space-between; align-items:center; font-size:30px; }
.foot b { font-weight:700; }
.foot span { opacity:.85; }
</style></head><body><div class="wrap" id="wrap">
<div class="top"><div class="logo">__LOGO__</div><div class="date">__DATUM__</div></div>
<div class="label"><span class="tip">Tip dňa</span><span class="badge">__KATEGORIA__</span></div>
<h1 id="h">__TITULOK__</h1>
<div class="card" id="c">__TEXT__</div>
<div class="foot" id="f"><b>@erekon_academy</b><span>www.erekon.eu/tipy</span></div>
</div>
<script>
// dlhý tip: zmenšuj písmo, kým sa všetko nezmestí
window.prisposob = () => {
  const h = document.getElementById('h'), c = document.getElementById('c'), f = document.getElementById('f');
  let hs = 72, cs = 36;
  const prilis = () => f.getBoundingClientRect().bottom > 1350 - 76 + 1 || document.getElementById('wrap').scrollHeight > 1350;
  while (prilis() && cs > 24) { hs -= 3; cs -= 1.5; h.style.fontSize = hs + 'px'; c.style.fontSize = cs + 'px'; }
  return {hs, cs};
};
</script></body></html>"""


def nbsp(t: str) -> str:
    """Nezalomiteľné medzery: 1. 11., 1 500 €, 100 %, § 122, č. 261 – nerozdelia sa na dva riadky."""
    t = html.escape(t)
    t = re.sub(r"(\d\.?) (?=[\d€%])", "\\1&nbsp;", t)
    t = re.sub(r"(\d\.?) (?=[\d€%])", "\\1&nbsp;", t)
    t = re.sub(r"(§|č\.|ods\.|písm\.) ", "\\1&nbsp;", t)
    t = re.sub(r"(\d\.) (?=(janu|febru|mar|apr|máj|jún|júl|aug|sept|okt|nov|dec))", "\\1&nbsp;", t)
    return t


def vyrob_obrazok(tip: dict, d: date, cesta: Path) -> None:
    from playwright.sync_api import sync_playwright

    OBRAZKY.mkdir(exist_ok=True)
    logo_html = '<span>ErEkon</span>'
    logo = OBRAZKY / "_logo.png"
    try:
        if (ROOT / "logo.png").exists():  # logo uložené v repozitári
            logo.write_bytes((ROOT / "logo.png").read_bytes())
        else:
            logo.write_bytes(stiahni(LOGO_URL))
        logo_html = f'<img src="{logo.name}" alt="ErEkon">'
    except Exception as e:  # bez loga sa použije textové ErEkon
        print(f"Logo sa nepodarilo načítať ({e}), použijem text.")

    stranka = (SABLONA
               .replace("__LOGO__", logo_html)
               .replace("__DATUM__", f"{d.day}. {d.month}. {d.year}")
               .replace("__KATEGORIA__", html.escape(tip["kategoria"]))
               .replace("__TITULOK__", nbsp(tip["titulok"]))
               .replace("__TEXT__", nbsp(tip["text"])))
    html_subor = OBRAZKY / "_tip.html"
    html_subor.write_text(stranka, encoding="utf-8")

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        pg.goto(html_subor.as_uri(), wait_until="networkidle", timeout=30000)
        pg.evaluate("document.fonts.ready")
        velkosti = pg.evaluate("window.prisposob()")
        pg.screenshot(path=str(cesta), type="jpeg", quality=92)
        b.close()
    print(f"Obrázok: {cesta.name} (písmo nadpis {velkosti['hs']}px, text {velkosti['cs']}px)")


# ---------------------------------------------------------------- Instagram API
def api(metoda: str, cesta: str, **params):
    params["access_token"] = os.environ["IG_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{cesta}"
    if metoda == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Chyba Instagram API ({e.code}): {e.read().decode(errors='replace')}")


def zverejni() -> None:
    d = dnes()
    if not DNES_JSON.exists():
        print("Na dnes nie je pripravený tip – nič nezverejňujem.")
        return
    info = json.loads(DNES_JSON.read_text(encoding="utf-8"))
    if info["datum"] != d.isoformat():
        sys.exit(f"Pripravený tip je na {info['datum']}, nie na {d}.")

    repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["COMMIT_SHA"]
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/obrazky/{info['obrazok']}"
    for _ in range(12):  # počkaj, kým je obrázok verejne dostupný
        try:
            stiahni(url)
            break
        except Exception:
            time.sleep(5)

    ig = os.environ["IG_USER_ID"]
    kontajner = api("POST", f"{ig}/media", image_url=url, caption=info["popis"])["id"]
    for _ in range(30):
        stav = api("GET", kontajner, fields="status_code").get("status_code")
        if stav == "FINISHED":
            break
        if stav in ("ERROR", "EXPIRED"):
            sys.exit(f"Instagram obrázok neprijal (stav {stav}).")
        time.sleep(10)
    media = api("POST", f"{ig}/media_publish", creation_id=kontajner)["id"]

    with DENNIK.open("a", encoding="utf-8") as f:
        f.write(f"{d.isoformat()} {media}\n")
    print(f"Zverejnené na Instagrame: {d} (media {media})")


def obnov_token() -> None:
    q = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": os.environ["IG_TOKEN"]})
    with urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?{q}", timeout=30) as r:
        sys.stdout.write(json.loads(r.read())["access_token"])


def priprav() -> None:
    d = dnes()
    DNES_JSON.unlink(missing_ok=True)
    if uz_zverejnene(d) and os.environ.get("VYNUTIT") != "1":
        print(f"Tip na {d} už bol zverejnený.")
        return
    tip = next((t for t in nacitaj_tipy() if t.get("datum") == d.isoformat()), None)
    if not tip:
        print(f"V tipy.js nie je tip na {d}.")
        return
    nazov = f"tip-{d.isoformat()}.jpg"
    vyrob_obrazok(tip, d, OBRAZKY / nazov)
    DNES_JSON.write_text(json.dumps({"datum": d.isoformat(), "obrazok": nazov, "popis": popis(tip)},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print("---- popis príspevku ----\n" + popis(tip))


if __name__ == "__main__":
    {"priprav": priprav, "zverejni": zverejni, "obnov-token": obnov_token}[sys.argv[1]]()
