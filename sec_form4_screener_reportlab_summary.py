import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
import os

# ========================
# CONFIGURATION
# ========================
BASE_URL = "https://www.sec.gov/Archives/"
CURRENT_FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
OUTPUT_PDF = "Form4_Report.pdf"
EMAIL_SUMMARY_FILE = "email_summary.txt"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SECForm4Screener/1.0)"}


# ========================
# 1️⃣ EXTRACTION DES DONNÉES
# ========================
def fetch_form4_filings():
    print("Fetching current Form 4 filings...")
    response = requests.get(CURRENT_FEED, headers=HEADERS)
    response.raise_for_status()
    lines = response.text.splitlines()

    filings = []
    for line in lines:
        if "href=" in line and "Archives/edgar/data" in line and ".txt" in line:
            parts = line.split('"')
            url_part = [p for p in parts if "Archives/edgar/data" in p]
            if not url_part:
                continue
            filename = url_part[0].split("Archives/")[1]
            company = line.split(">")[1].split("<")[0].strip()
            filings.append({"company": company, "filename": filename})

    print(f"Total filings found: {len(filings)}")
    return filings


# ========================
# 2️⃣ FILTRAGE PAR ACHAT > 100k$
# ========================
def filter_large_purchases(filings):
    large_buys = []

    for f in filings:
        url = BASE_URL + f["filename"]
        try:
            txt = requests.get(url, headers=HEADERS, timeout=10).text.lower()
            if "non-derivative" in txt and "$" in txt:
                # recherche approximative d’achats supérieurs à 100k
                numbers = [int(n.replace(",", "")) for n in txt.split("$") if n.strip()[:6].isdigit()]
                if any(n > 100000 for n in numbers):
                    # Construire le lien HTML direct
                    html_url = url.replace(".txt", ".htm")
                    f["url"] = html_url
                    large_buys.append(f)
        except Exception as e:
            print(f"Error reading {url}: {e}")

    print(f"Filtered {len(large_buys)} large purchases (>100k$)")
    return large_buys


# ========================
# 3️⃣ GÉNÉRATION DU RAPPORT PDF
# ========================
def generate_pdf(filings):
    print("Generating PDF report...")
    doc = SimpleDocTemplate(OUTPUT_PDF, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Rapport quotidien – Form 4 (achats > 100 000 $)</b>", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Date de génération : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 24))

    if not filings:
        story.append(Paragraph("Aucun achat insider supérieur à 100 000 $ n’a été trouvé aujourd’hui.", styles["Normal"]))
    else:
        for f in filings:
            story.append(Paragraph(f"<b>{f['company']}</b>", styles["Heading3"]))
            story.append(
                Paragraph(f"<a href='{f['url']}' color='blue'>{f['url']}</a>", styles["Normal"])
            )
            story.append(Spacer(1, 12))

    doc.build(story)
    print("PDF generated successfully.")


# ========================
# 4️⃣ CRÉATION DU RÉSUMÉ EMAIL
# ========================
def generate_email_summary(filings):
    with open(EMAIL_SUMMARY_FILE, "w") as f:
        f.write("Résumé des achats insiders du jour (>100k$)\n")
        f.write("=" * 50 + "\n\n")
        if not filings:
            f.write("Aucun achat insider supérieur à 100 000 $ trouvé aujourd’hui.\n")
        else:
            for filing in filings:
                f.write(f"- {filing['company']}: {filing['url']}\n")
    print("Email summary file generated.")


# ========================
# 5️⃣ PIPELINE PRINCIPAL
# ========================
if __name__ == "__main__":
    filings = fetch_form4_filings()
    large_purchases = filter_large_purchases(filings)
    generate_pdf(large_purchases)
    generate_email_summary(large_purchases)
    print("✅ Report and summary ready.")
