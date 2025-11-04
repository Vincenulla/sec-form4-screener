import requests
import datetime
import xml.etree.ElementTree as ET
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.colors import blue
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SECForm4Screener/1.0; contact@example.com)"}
EDGAR_NEXT_URL = "https://efts.sec.gov/LATEST/search-index"
TODAY = datetime.date.today()

def fetch_form4_filings():
    print("Fetching Form 4 filings via EDGAR Next...")
    params = {
        "keys": 'formType:"4"',
        "category": "custom",
        "forms": "4",
        "start": 0,
        "count": 50,
        "sortField": "filedAt",
        "sortOrder": "desc"
    }
    r = requests.get(EDGAR_NEXT_URL, headers=HEADERS, params=params)
    if r.status_code != 200:
        print(f"⚠️ EDGAR Next error {r.status_code}, fallback...")
        return []
    data = r.json()
    return data.get("hits", [])

def parse_form4_xml(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 404 and url.endswith(".xml"):
            url = url.replace(".xml", ".txt")  # fallback .txt
            resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 404 and url.endswith(".txt"):
            url = url.replace(".txt", ".htm")  # fallback .htm
            resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"Could not fetch filing at {url}, status {resp.status_code}")
            return None

        if url.endswith(".xml") or url.endswith(".txt"):
            tree = ET.fromstring(resp.content)
            issuer = tree.findtext(".//issuerName") or "N/A"
            insider = tree.findtext(".//rptOwnerName") or "N/A"
            trans_type = tree.findtext(".//transactionCode")
            shares = float(tree.findtext(".//transactionShares/value") or 0)
            price = float(tree.findtext(".//transactionPricePerShare/value") or 0)
            total = shares * price
            return {
                "issuer": issuer,
                "insider": insider,
                "type": trans_type,
                "amount": total,
                "link": url
            }
        else:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()
            if "P" in text and "$" in text:
                return {"issuer": "N/A", "insider": "N/A", "type": "P", "amount": 0, "link": url}
    except Exception as e:
        print(f"Error parsing {url}: {e}")
    return None

def main():
    print(f"Starting screener at {datetime.datetime.now().isoformat()}")
    filings = fetch_form4_filings()
    print(f"Fetched {len(filings)} filings")

    matches = []
    for f in filings:
        base_url = f"https://www.sec.gov/Archives/{f['linkToFilingDetails'].split('/Archives/')[-1]}"
        xml_url = base_url.replace("-index.htm", ".xml")
        parsed = parse_form4_xml(xml_url)
        if parsed and parsed["type"] == "P" and parsed["amount"] > 100000:
            matches.append(parsed)

    print(f"Matches found: {len(matches)}")

    doc = SimpleDocTemplate("Form4_Report.pdf", pagesize=letter)
    styles = getSampleStyleSheet()
    Story = [Paragraph("📈 Form 4 – Achats insiders > 100 000 $", styles["Title"]), Spacer(1, 0.25 * inch)]

    if not matches:
        Story.append(Paragraph("Aucun achat insider > 100 000 $ trouvé aujourd'hui.", styles["Normal"]))
    else:
        for m in matches:
            ptext = f"<b>{m['issuer']}</b> — {m['insider']}<br/>Achat: ${m['amount']:,.0f}<br/><a href='{m['link']}' color='blue'>Lien vers le Form 4</a>"
            Story.append(Paragraph(ptext, styles["Normal"]))
            Story.append(Spacer(1, 0.2 * inch))

    doc.build(Story)

    with open("email_summary.txt", "w") as f:
        if matches:
            for m in matches:
                f.write(f"{m['issuer']} — {m['insider']} — ${m['amount']:,.0f}\n{m['link']}\n\n")
        else:
            f.write("Aucun achat insider > 100 000 $ trouvé aujourd'hui.\n")

    print("✅ Done.")

if __name__ == "__main__":
    main()
