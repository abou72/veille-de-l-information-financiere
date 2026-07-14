import requests
from bs4 import BeautifulSoup
import time
import logging
from urllib.parse import urljoin
from datetime import datetime
import xml.etree.ElementTree as ET

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

# Sites via scraping HTML normal
URLS_HTML = [
    {"url": "https://www.financialafrik.com/", "nom": "Financial Afrik"},
    {"url": "https://www.sikafinance.com/feed",     "nom": "Sika Finance RSS"},
]

# Sites via flux RSS (plus fiable, contourne les blocages)
URLS_RSS = [
    {"url": "https://www.financialafrik.com/feed/", "nom": "Financial Afrik RSS"},
    {"url": "https://www.sikafinance.com/feed",     "nom": "Sika Finance RSS"},
    {"url": "https://www.leconomiste.com/rss.xml",  "nom": "L'Economiste RSS"},
    {"url": "https://www.richbourse.com/",          "nom": "riche bourse RSS"},
]

KEYWORDS = ["nommé", "directeur", "dg", "pca", "président", "brvm","etat financier","resultat net","perte","Plam ci","sonatel","onatel","orange cote d ivoire","BOA","sucrivoire",
            "cie","sodeci","unilever","setao","sicor","safca","nestle","cfao","coris bank","servair abidjan","bici",
            "sicable","ecobank","nsia bank","oragroup togo","tractafric","agl","eviosys","societe generale","vivo energy",
            "erium","Solibra","smb","saph","sitab","uniwax","totalenergies marketing","nei-ceda"]

SEEN_FILE = "changement_important.txt"
CHECK_INTERVAL = 600  # 10 minutes

# ─── Telegram ───
TELEGRAM_TOKEN   = "8931546423:AAGORuxoU-wcqpANJpILTdPp2QbAzZnecNw"
TELEGRAM_CHAT_ID = "-5502663920"

# Headers qui imitent un vrai navigateur Chrome
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("actualites.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  GESTION DES ARTICLES DÉJÀ VUS
# ─────────────────────────────────────────────

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        for link in seen:
            f.write(link + "\n")

# ─────────────────────────────────────────────
#  ENVOI TELEGRAM
# ─────────────────────────────────────────────

def envoyer_telegram(articles_detectes):
    if not articles_detectes:
        return

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    texte = f"📰 *{len(articles_detectes)} nouvelle(s) alerte(s)* — {now}\n\n"

    for titre, lien, source in articles_detectes:
        texte += f"🌐 *{source}*\n• [{titre.strip()}]({lien})\n\n"

    texte += "—\n_Alerte automatique — Veille Financière Afrique_"

    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texte,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }

    try:
        resp = requests.post(url_api, json=payload, timeout=10)
        resp.raise_for_status()
        log.info(f"✅ Message Telegram envoyé avec {len(articles_detectes)} article(s).")
    except Exception as e:
        log.error(f"❌ Erreur Telegram : {e}")

# ─────────────────────────────────────────────
#  SCRAPING HTML
# ─────────────────────────────────────────────

def scraper_html(site, seen, new_seen, nouveaux_articles):
    url = site["url"]
    nom = site["nom"]
    try:
        response = requests.get(url, timeout=15, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for a in soup.find_all("a"):
            titre = a.get_text(strip=True)
            lien  = a.get("href")
            if not lien or not titre:
                continue
            lien_complet = urljoin(url, lien)
            if any(kw in titre.lower() for kw in KEYWORDS):
                if lien_complet not in seen:
                    log.info(f"🆕 [{nom}] {titre}")
                    nouveaux_articles.append((titre, lien_complet, nom))
                    new_seen.add(lien_complet)

    except requests.exceptions.HTTPError as e:
        log.warning(f"⚠️  Erreur HTTP {e} sur {url}.")
    except requests.exceptions.ConnectionError:
        log.warning(f"⚠️  Impossible de joindre {url}.")
    except requests.exceptions.Timeout:
        log.warning(f"⚠️  Timeout sur {url}.")
    except Exception as e:
        log.error(f"❌ Erreur sur {url} : {e}")

# ─────────────────────────────────────────────
#  SCRAPING RSS
# ─────────────────────────────────────────────

def scraper_rss(site, seen, new_seen, nouveaux_articles):
    url = site["url"]
    nom = site["nom"]
    try:
        response = requests.get(url, timeout=15, headers=HEADERS)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        # Parcourir les items RSS
        for item in root.iter("item"):
            titre_el = item.find("title")
            lien_el  = item.find("link")

            if titre_el is None or lien_el is None:
                continue

            titre = titre_el.text or ""
            lien  = lien_el.text or ""

            if not titre or not lien:
                continue

            if any(kw in titre.lower() for kw in KEYWORDS):
                if lien not in seen:
                    log.info(f"🆕 [{nom}] {titre}")
                    nouveaux_articles.append((titre, lien, nom))
                    new_seen.add(lien)

    except requests.exceptions.HTTPError as e:
        log.warning(f"⚠️  Erreur HTTP {e} sur {url}.")
    except requests.exceptions.ConnectionError:
        log.warning(f"⚠️  Impossible de joindre {url}.")
    except requests.exceptions.Timeout:
        log.warning(f"⚠️  Timeout sur {url}.")
    except ET.ParseError:
        log.warning(f"⚠️  Flux RSS invalide sur {url}.")
    except Exception as e:
        log.error(f"❌ Erreur RSS sur {url} : {e}")

# ─────────────────────────────────────────────
#  BOUCLE PRINCIPALE
# ─────────────────────────────────────────────

def check_news():
    seen = load_seen()
    new_seen = set(seen)
    nouveaux_articles = []

    for site in URLS_HTML:
        scraper_html(site, seen, new_seen, nouveaux_articles)

    for site in URLS_RSS:
        scraper_rss(site, seen, new_seen, nouveaux_articles)

    save_seen(new_seen)

    if nouveaux_articles:
        envoyer_telegram(nouveaux_articles)
    else:
        log.info("Aucune nouvelle info détectée.")

if __name__ == "__main__":
    log.info("🚀 Démarrage du script de veille actualités...")
    envoyer_telegram([("🚀 Script démarré — veille active sur 4 sites !", "https://www.financialafrik.com/", "Système")])
    while True:
        log.info("🔍 Vérification des actualités...")
        try:
            check_news()
        except Exception as e:
            log.error(f"❌ Erreur critique : {e}")
        log.info(f"⏳ Prochaine vérification dans {CHECK_INTERVAL // 60} minutes.")
        time.sleep(CHECK_INTERVAL)
