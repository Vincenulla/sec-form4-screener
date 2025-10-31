import requests
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
import os

# --- Configuration ---
API_URL = "https://efts.sec.gov/LATEST/search-index"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SECForm4Screener/2.0; +https://github.com/Vincenulla/sec-form4-screener)"
}
MIN_BUY_VALUE = 100_000
PDF_FILE = "Form4_Report.pdf"
SUMMARY_FILE = "email_summary.txt"


# --- Fonction : récupérer les filings via EDGAR Next ---
def fetch_form4_filings():
    print("Fetching current Form 4 filings via EDGAR Next API...")
    params = {
        "q": "formType:\"4\"",
        "from": "0",
        "size": "100",
        "sort": "filedAt:desc"
    }
    try:
        r = requests.get(API_URL, headers=HEADERS, params=params, timeout=20)
        if r.status_code == 403:
            print("⚠️ SEC 403 – access forbidden.")
            return []
        r.raise_for_status()
        data = r.json()
        filings = []
        for item in data.get("hits", {}).get("hits", []):
            src = item["_source"]
            accession = src.get("accessionNo", "")
            company = src.get("displayNames", [""])[0]
            filed_at = src.get("filedAt", "")[:10]
            link = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{src.get('ciks', [''])[0]}/{accession.replace('-', '')}/{accession}-index.html"
            filings.append({"company": company, "link": link, "date": filed_at})
        return filings
    except Exception as e:
        print(f"⚠️ Error fetching EDGAR Next: {e}")
        return []


# --- Fonction fallback : ancienne page (HTML) ---
def fetch_form4_legacy():
    from bs4 import BeautifulSoup
    print("Fallback: fetching via legacy HTML page...")
    try:
        r = requests.get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4", headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.find_all("tr")
        filings = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            filing_type = cols[0].text.strip()
            company = cols[1].text.strip()
            link_tag = cols[1].find("a")
            link = "https://www.sec.gov" + link_tag["href"] if link_tag else ""
            date_filed = cols[3].text.strip()
            if filing_type == "4":
                filings.append({"company": company, "link": link, "date": date_filed})
        return filings
    except Exception as e:
        print(f"⚠️ Legacy fetch failed: {e}")
        return []


# --- Génération du PDF ---
def generate_pdf(filings):
    print("Generating PDF report...")
    doc = SimpleDocTemplate(PDF_FILE, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        spaceAfter=20,
    )

    story.append(Paragraph("📈 Rapport quotidien – Form 4 (achats > 100k $)", title_style))
    story.append(Spacer(1, 0.5 * cm))

    if not filings:
        story.append(Paragraph("Aucun achat insider supérieur à 100 000 $ n’a été détecté aujourd’hui.", styles["Normal"]))
        doc.build(story)
        return

    data = [["Entreprise", "Date", "Lien SEC"]]

    for f in filings:
        link_html = f"<a href='{f['link']}' color='blue'>{f['link']}</a>"
        data.append([f["company"], f["date"], Paragraph(link_html, styles["Normal"])])

    table = Table(data, colWidths=[7 * cm, 3 * cm, 7 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    story.append(table)
    doc.build(story)
    print(f"✅ PDF generated: {PDF_FILE}")


# --- Génération du résumé texte ---
def generate_summary(filings):
    print("Generating summary for email...")
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        if not filings:
            f.write("Aucun achat insider supérieur à 100 000 $ n’a été détecté aujourd’hui.\n")
        else:
            f.write("Achats insiders récents (>100k$) :\n\n")
            for filing in filings:
                f.write(f"- {filing['company']} ({filing['date']}) → {filing['link']}\n")


# --- Programme principal ---
if __name__ == "__main__":
    filings = fetch_form4_filings()
    if not filings:
        filings = fetch_form4_legacy()

    if not filings:
        print("⚠️  Aucun résultat trouvé, création d’un rapport vide.")
        generate_pdf([])
        generate_summary([])
    else:
        generate_pdf(filings)
        generate_summary(filings)

    print("✅ Done.")
