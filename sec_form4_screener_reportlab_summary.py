import requests
from bs4 import BeautifulSoup
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEC Form4 Screener; +https://github.com/Vincenulla)",
    "Accept": "application/json"
}

# ===============================
#  FETCHING FROM EDGAR NEXT API
# ===============================

def fetch_form4_filings():
    print("Fetching current Form 4 filings via EDGAR Next API...")
    try:
        api_url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "keys": "formType:\"4\"",
            "category": "custom",
            "forms": "4",
            "start": 0,
            "count": 100,
            "sortField": "filedAt",
            "sortOrder": "desc"
        }
        r = requests.get(api_url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        filings = []
        for hit in data.get("hits", []):
            accession = hit.get("adsh", "")
            cik = hit.get("cik", "")
            company = hit.get("displayNames", ["Unknown"])[0]
            filedAt = hit.get("filedAt", "Unknown")

            link_html = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.htm"
            filings.append({
                "title": f"Form 4 – {company}",
                "link_html": link_html,
                "date": filedAt
            })
        print(f"✅ {len(filings)} filings trouvés via EDGAR Next API.")
        return filings

    except Exception as e:
        print(f"⚠️ SEC API non accessible ({e}), tentative fallback RSS...")
        return fetch_from_rss_fallback()


def fetch_from_rss_fallback():
    """Fallback sur l’ancien flux RSS si l’API échoue."""
    try:
        RSS_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&count=100&output=atom"
        response = requests.get(RSS_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "xml")

        filings = []
        for entry in soup.find_all("entry"):
            title = entry.find("title").text.strip()
            link = entry.find("link")["href"]
            updated = entry.find("updated").text.strip() if entry.find("updated") else "Unknown"
            filings.append({"title": title, "link_html": link, "date": updated})
        print(f"✅ {len(filings)} filings trouvés via RSS fallback.")
        return filings
    except Exception as e:
        print(f"❌ Error fetching RSS fallback: {e}")
        return []

# ===============================
#  PARSING XML FORM 4 DETAILS
# ===============================

def parse_form4_details(filing):
    """Analyse chaque Form 4 pour extraire l’insider, la société et le montant acheté."""
    try:
        xml_url = filing["link_html"].replace("-index.htm", ".xml")
        r = requests.get(xml_url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"⚠️ Erreur accès XML {xml_url}")
            return None

        xml = BeautifulSoup(r.text, "lxml-xml")

        issuer_name = xml.find("issuerName").text.strip() if xml.find("issuerName") else "Unknown"
        insider_name = xml.find("rptOwnerName").text.strip() if xml.find("rptOwnerName") else "Unknown"

        total_value = 0
        for trans in xml.find_all("nonDerivativeTransaction"):
            try:
                code = trans.transactionCoding.transactionCode.text.strip()
                if code != "P":
                    continue
                shares_node = trans.find("transactionShares")
                price_node = trans.find("transactionPricePerShare")
                shares = float(shares_node.text.replace(",", "")) if shares_node else 0
                price = float(price_node.text.replace(",", "")) if price_node else 0
                value = shares * price
                total_value += value
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

# ===============================
#  PDF REPORT GENERATION
# ===============================

def generate_pdf_report(filings):
    print("Generating PDF report...")
    doc = SimpleDocTemplate("Form4_Report.pdf", pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("📈 Achats insiders > 100 000 $", styles["Heading1"]))
    story.append(Spacer(1, 12))

    if not filings:
        story.append(Paragraph("Aucun achat insider supérieur à 100 000 $ trouvé aujourd’hui.", styles["Normal"]))
    else:
        data = [["Société", "Insider", "Date", "Montant (USD)", "Lien Form 4"]]
        for f in filings:
            link_html = f'<a href="{f["link_html"]}">Ouvrir</a>'
            data.append([
                f["issuer"],
                f["insider"],
                f["date"][:10],
                f"${f['value']:,.0f}",
                Paragraph(link_html, styles["Normal"]),
            ])

        table = Table(data, colWidths=[2.3*inch, 1.7*inch, 1.1*inch, 1.2*inch, 1.0*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        story.append(table)

    doc.build(story)
    print("✅ Rapport généré avec succès.")

# ===============================
#  MAIN EXECUTION
# ===============================

def main():
    filings = fetch_form4_filings()
    buy_filings = []

    for filing in filings:
        details = parse_form4_details(filing)
        if details:
            buy_filings.append(details)

    print(f"✅ {len(buy_filings)} achats > 100 000 $ trouvés.")
    generate_pdf_report(buy_filings)

    # Génération du résumé pour l’e-mail
    with open("email_summary.txt", "w") as f:
        if not buy_filings:
            f.write("Aucun achat insider supérieur à 100 000 $ trouvé aujourd’hui.")
        else:
            for bf in buy_filings:
                f.write(f"{bf['issuer']} – {bf['insider']} : ${bf['value']:,.0f}\n")

if __name__ == "__main__":
    main()
