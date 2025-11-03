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
    "User-Agent": "Mozilla/5.0 (compatible; SECForm4Screener/1.2; +mailto:vincent.form4bot@gmail.com)",
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
            link_html = e.find("link")["href"]
            updated = e.find("updated").text[:10]
            if "Form 4" not in title:
                continue
            filings.append({"title": title, "link_html": link_html, "date": updated})
        print(f"✅ {len(filings)} filings trouvés via RSS.")
        return filings
    except Exception as e:
        print("❌ Error fetching RSS:", e)
        return []


def parse_form4_details(filing):
    """Analyse le fichier XML d’un Form 4 pour extraire insider, société et montant acheté."""
    try:
        xml_url = filing["link_html"].replace("-index.htm", ".xml")
        r = requests.get(xml_url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None
        xml = BeautifulSoup(r.text, "xml")

        # Nom de la société et de l’insider
        issuer_name = xml.find("issuerName").text.strip() if xml.find("issuerName") else "Unknown"
        insider_name = xml.find("rptOwnerName").text.strip() if xml.find("rptOwnerName") else "Unknown"

        total_value = 0
        for trans in xml.find_all("nonDerivativeTransaction"):
            try:
                code = trans.transactionCoding.transactionCode.text.strip()
                if code != "P":  # 'P' = Purchase
                    continue

                # Valeur de la transaction
                val_node = trans.find("transactionValue")
                if val_node and val_node.text.replace(".", "", 1).isdigit():
                    total_value += float(val_node.text)
                else:
                    # Si valeur manquante, reconstituer = shares × price
                    shares = trans.find("transactionShares")
                    price = trans.find("transactionPricePerShare")
                    if shares and price:
                        try:
                            s = float(shares.text.replace(",", ""))
                            p = float(price.text.replace(",", ""))
                            total_value += s * p
                        except:
                            pass
            except Exception:
                continue

        if total_value >= 100000:
            return {
                "issuer": issuer_name,
                "insider": insider_name,
                "date": filing["date"],
                "value": total_value,
                "link_html": filing["link_html"],
            }
        return None

    except Exception as e:
        print(f"⚠️ Erreur parsing {filing['title']}: {e}")
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

    data = [["Société", "Insider", "Date", "Montant ($)", "Lien SEC"]]
    for f in filings:
        link_html = f"<a href='{f['link_html']}' color='blue'>{f['link_html']}</a>"
        data.append([
            f["issuer"],
            f["insider"],
            f["date"],
            f"{f['value']:,.0f}",
            Paragraph(link_html, styles["Normal"]),
        ])

    table = Table(data, colWidths=[5*cm, 4*cm, 2.5*cm, 3*cm, 5*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    doc.build(story)


def generate_summary(filings):
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        if not filings:
            f.write("Aucun achat insider > 100 000 $ détecté aujourd’hui.\n")
        else:
            for fl in filings:
                f.write(f"- {fl['issuer']} | {fl['insider']} ({fl['date']}) : "
                        f"${fl['value']:,.0f} → {fl['link_html']}\n")


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
