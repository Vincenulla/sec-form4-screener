import requests
import re
import os
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

# ---------- CONFIG ----------
OUTPUT_FILE = "Form4_Report.pdf"
MIN_PURCHASE_USD = 400_000
USER_AGENT = {"User-Agent": "Form4Screener/1.0 (contact: your_email@example.com)"}
SUMMARY_FILE = "email_summary.txt"
# ----------------------------

def download_daily_index():
    """Télécharge l'index journalier le plus récent disponible"""
    today = datetime.utcnow()
    for i in range(3):  # essaie les 3 derniers jours
        date = today - timedelta(days=i)
        year, qtr = date.year, (date.month - 1)//3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/company.{date.strftime('%Y%m%d')}.idx"
        print(f"Tentative : {url}")
        resp = requests.get(url, headers=USER_AGENT)
        if resp.status_code == 200:
            print("Index trouvé :", url)
            return resp.text
    raise RuntimeError("Impossible de récupérer l'index SEC des 3 derniers jours.")

def extract_form4_lines(index_text):
    """Extrait les lignes Form 4 depuis le texte brut"""
    lines = []
    capture = False
    for line in index_text.splitlines():
        if "-----" in line:
            capture = True
            continue
        if capture and re.search(r"\b4\b", line):
            lines.append(line)
    return lines

def parse_index_line(line):
    """Parse une ligne d'index"""
    try:
        parts = re.split(r"\s{2,}", line.strip())
        company = parts[0]
        form_type = parts[1]
        cik = parts[2]
        filename = parts[-1]
        filing_url = f"https://www.sec.gov/Archives/{filename}"
        return {"company": company, "cik": cik, "url": filing_url}
    except Exception:
        return None

def extract_buy_transactions(filing_text):
    """Analyse simple du contenu pour détecter des achats > seuil"""
    text = filing_text.lower()
    if "acquisition" not in text and "purchase" not in text:
        return False
    matches = re.findall(r"\$?([\d,]+)", text)
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if val >= MIN_PURCHASE_USD:
                return True
        except:
            pass
    return False

def generate_pdf(buy_filings):
    """Crée le rapport PDF"""
    doc = SimpleDocTemplate(OUTPUT_FILE, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph("📈 SEC Form 4 Insider Buys > 400k$", styles["Title"]), Spacer(1, 0.2*inch)]
    story.append(Paragraph(f"Date du rapport : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 0.3*inch))

    if not buy_filings:
        story.append(Paragraph("Aucun achat significatif trouvé aujourd'hui.", styles["Normal"]))
    else:
        for f in buy_filings:
            story.append(Paragraph(f"<b>{f['company']}</b> (CIK {f['cik']})", styles["Heading3"]))
            story.append(Paragraph(f"<a href='{f['url']}'>{f['url']}</a>", styles["Normal"]))
            story.append(Spacer(1, 0.2*inch))

    doc.build(story)
    print(f"✅ Rapport PDF généré : {OUTPUT_FILE}")

def write_summary(buy_filings):
    """Crée un résumé texte pour le corps de l'email"""
    lines = []
    lines.append("📊 Résumé du jour : Achats Form 4 > 100k$")
    lines.append(f"Date du rapport : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("----------------------------------------------------")
    if not buy_filings:
        lines.append("Aucun achat insider significatif trouvé aujourd'hui.")
    else:
        for f in buy_filings:
            lines.append(f"- {f['company']} (CIK {f['cik']}) → {f['url']}")
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("📝 Résumé email généré :", SUMMARY_FILE)

def main():
    print("Téléchargement de l'index journalier SEC...")
    index_text = download_daily_index()
    lines = extract_form4_lines(index_text)
    print(f"{len(lines)} Form 4 trouvés dans l'index.")

    filings = []
    for line in lines[:50]:
        info = parse_index_line(line)
        if not info:
            continue
        try:
            filing_resp = requests.get(info["url"], headers=USER_AGENT)
            if filing_resp.status_code == 200 and extract_buy_transactions(filing_resp.text):
                filings.append(info)
        except Exception as e:
            print(f"Erreur {info['company']}: {e}")

    print(f"{len(filings)} achats significatifs trouvés.")
    generate_pdf(filings)
    write_summary(filings)

if __name__ == "__main__":
    main()
