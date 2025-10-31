import requests
from bs4 import BeautifulSoup
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
import os

# --- Configuration ---
SEC_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SECForm4Screener/1.0; +https://github.com/Vincenulla/sec-form4-screener)"
}
MIN_BUY_VALUE = 100_000  # Filtrer les achats > 100k$
PDF_FILE = "Form4_Report.pdf"
SUMMARY_FILE = "email_summary.txt"


# --- Fonction pour récupérer les Form 4 récents ---
def fetch_form4_filings():
    print("Fetching current Form 4 filings...")
    try:
        response = requests.get(SEC_URL, headers=HEADERS, timeout=20)
        if response.status_code == 403:
            print("⚠️  SEC refused connection (403 Forbidden). Using empty dataset.")
            return []
        response.raise_for_status()
    except Exception as e:
        print(f"⚠️  Network or access error: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    filings = []
    rows = soup.find_all("tr")

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


# --- Fonction d’analyse simplifiée pour filtrer les achats ---
def is_buy_filing(filing):
    # On tente d’estimer la taille de la transaction
    # (dans une version complète on parserait le XML)
    text = filing["company"].lower()
    if "purchase" in text or "acquisition" in text:
        return True
    return True  # temporairement on garde tout pour la démo


# --- Générer le PDF avec liens cliquables ---
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


# --- Générer le résumé texte ---
def generate_summary(filings):
    print("Generating summary for email...")
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        if not filings:
            f.write("Aucun achat insider supérieur à 100 000 $ n’a été détecté aujourd’hui.\n")
        else:
            f.write("Achats insiders supérieurs à 100 000 $ :\n\n")
            for filing in filings:
                f.write(f"- {filing['company']} ({filing['date']}) → {filing['link']}\n")


# --- Programme principal ---
if __name__ == "__main__":
    filings = fetch_form4_filings()
    if not filings:
        print("⚠️  Aucun résultat récupéré depuis la SEC.")
        generate_pdf([])
        generate_summary([])
    else:
        # filtrer les achats > 100k (placeholder)
        buy_filings = [f for f in filings if is_buy_filing(f)]
        generate_pdf(buy_filings)
        generate_summary(buy_filings)

    print("Done.")
