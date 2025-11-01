import requests
from bs4 import BeautifulSoup
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm

PDF_FILE = "Form4_Report.pdf"
SUMMARY_FILE = "email_summary.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SECForm4Screener/1.1; +mailto:vincent.form4bot@gmail.com)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sec.gov/"
}

def fetch_form4_filings():
    """Récupère la liste des Form 4 récents via le flux RSS EDGAR."""
    print("Fetching Form 4 filings from SEC RSS...")
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "xml")
        entries = soup.find_all("entry")
        filings = []
        for e in entries:
            title = e.find("title").text.strip()
            link = e.find("link")["href"]
            updated = e.find("updated").text[:10]
            if "Form 4" not in title:
                continue
            filings.append({"company": title, "link": link, "date": updated})
        print(f"✅ {len(filings)} filings trouvés via RSS.")
        return filings
    except Exception as e:
        print("❌ Error fetching RSS:", e)
        return []

def parse_form4_details(filing):
    """Ouvre le XML associé à un Form 4 et extrait le total des achats."""
    try:
        # Le lien RSS pointe sur la page HTML — on reconstruit le lien XML
        link_xml = filing["link"].replace("-index.htm", ".xml")
        r = requests.get(link_xml, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None
        xml = BeautifulSoup(r.text, "xml")

        total_value = 0
        for trans in xml.find_all("nonDerivativeTransaction"):
            code = trans.transactionCoding.transactionCode.text if trans.transactionCoding.transactionCode else ""
            if code != "P":  # 'P' = Purchase
                continue
            val_node = trans.transactionAmounts.transactionValue
            if val_node and val_node.text.replace('.', '', 1).isdigit():
                total_value += float(val_node.text)

        if total_value >= 100000:
            return {"company": filing["company"], "link": filing["link"], "date": filing["date"], "value": total_value}
        else:
            return None
    except Exception as e:
        print(f"⚠️ Erreur parsing {filing['company']}: {e}")
        return None

def generate_pdf(filings):
    print("Generating PDF report...")
    doc = SimpleDocTemplate(PDF_FILE, pagesize=A4)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", alignment=TA_CENTER, fontSize=16, spaceAfter=20))
    story = []
    story.append(Paragraph("📈 Rapport quotidien – Achats insiders > 100 000 $", styles["CenterTitle"]))
    story.append(Spacer(1, 0.5 * cm))

    if not filings:
        story.append(Paragraph("Aucun achat insider > 100 000 $ détecté aujourd’hui.", styles["Normal"]))
        doc.build(story)
        return

    data = [["Entreprise", "Date", "Montant ($)", "Lien SEC"]]
    for f in filings:
        link_html = f"<a href='{f['link']}' color='blue'>{f['link']}</a>"
        data.append([
            f["company"],
            f["date"],
            f"{f['value']:,.0f}",
            Paragraph(link_html, styles["Normal"]),
        ])

    table = Table(data, colWidths=[7*cm, 2.5*cm, 3*cm, 6*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))
    story.append(table)
    doc.build(story)

def generate_summary(filings):
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        if not filings:
            f.write("Aucun achat insider > 100 000 $ détecté aujourd’hui.\n")
        else:
            for fl in filings:
                f.write(f"- {fl['company']} ({fl['date']}) : ${fl['value']:,.0f} → {fl['link']}\n")

if __name__ == "__main__":
    filings = fetch_form4_filings()
    detailed = []
    for f in filings:
        d = parse_form4_details(f)
        if d:
            detailed.append(d)

    print(f"✅ {len(detailed)} achats > 100 000 $ trouvés.")
    generate_pdf(detailed)
    generate_summary(detailed)
    print("✅ Rapport généré avec succès.")
