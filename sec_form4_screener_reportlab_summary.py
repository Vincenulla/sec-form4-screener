import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
import os

# ⚠️ Mets ici ton adresse e-mail (obligatoire pour les requêtes SEC)
USER_AGENT = "Form4Screener/1.0 (ton.email@exemple.com)"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}

def fetch_form4_filings(limit=50):
    """Récupère les derniers dépôts Form 4 via l’API EDGAR Next."""
    print("🔎 Fetching recent Form 4 filings from SEC EDGAR Next…")
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        f"?keys=formType%3A%224%22&category=custom&forms=4"
        f"&start=0&count={limit}&sortField=filedAt&sortOrder=desc"
    )
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    filings = []
    for f in data.get("hits", []):
        link = f.get("linkToFilingDetails", "")
        if "/Archives/" not in link:
            continue
        acc_path = link.split("/Archives/")[-1]
        xml_url = "https://www.sec.gov/Archives/" + acc_path.replace("-index.htm", ".xml")
        html_url = "https://www.sec.gov/Archives/" + acc_path
        filings.append({
            "company": f.get("displayNames", ["?"])[0],
            "filedAt": f.get("filedAt", ""),
            "accession": acc_path,
            "xml_url": xml_url,
            "html_url": html_url
        })
    print(f"✅ Found {len(filings)} filings.")
    return filings


def parse_form4(xml_url):
    """Analyse un Form 4 XML pour extraire les achats (> 100 k $)."""
    try:
        r = requests.get(xml_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content)

        issuer = root.findtext(".//issuerName") or "Unknown issuer"
        insider = root.findtext(".//reportingOwnerName") or "Unknown insider"

        total_value = 0.0
        for t in root.findall(".//nonDerivativeTransaction"):
            code = t.findtext(".//transactionAcquiredDisposedCode/value")
            if code != "A":
                continue  # skip sales/disposals
            price = t.findtext(".//transactionPricePerShare/value")
            shares = t.findtext(".//transactionShares/value")
            if price and shares:
                try:
                    total_value += float(price) * float(shares)
                except ValueError:
                    continue

        return {"issuer": issuer, "insider": insider, "value": total_value}
    except Exception:
        return None


def generate_pdf(results):
    """Génère le rapport PDF des achats détectés."""
    doc = SimpleDocTemplate("Form4_Report.pdf", pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("📈 Daily Insider Buying Screener — Form 4", styles["Title"]),
        Spacer(1, 0.3 * inch)
    ]

    for r in results:
        story.append(Paragraph(f"<b>{r['issuer']}</b> — {r['insider']}", styles["Normal"]))
        story.append(Paragraph(f"Valeur d’achat : <b>${r['value']:,.0f}</b>", styles["Normal"]))
        story.append(Paragraph(
            f"<a href='{r['html_url']}'>🔗 Form 4 (HTML)</a> — "
            f"<a href='{r['xml_url']}'>XML</a>",
            styles["Normal"]
        ))
        story.append(Spacer(1, 0.25 * inch))

    doc.build(story)
    print("✅ PDF generated: Form4_Report.pdf")


def main():
    print(f"🚀 Starting Form 4 screener at {datetime.utcnow().isoformat()}")
    filings = fetch_form4_filings(limit=60)
    results = []

    for f in filings:
        info = parse_form4(f["xml_url"])
        if info and info["value"] > 100000:
            info.update({"html_url": f["html_url"], "xml_url": f["xml_url"]})
            results.append(info)

    print(f"✅ Matching purchases > $100 000 : {len(results)} found.")

    if results:
        generate_pdf(results)
        with open("email_summary.txt", "w") as f:
            for r in results:
                f.write(
                    f"{r['issuer']} — {r['insider']} — ${r['value']:,.0f}\n"
                    f"{r['html_url']}\n\n"
                )
        print("✅ Summary written to email_summary.txt")
    else:
        print("ℹ️ No matching purchases found today.")


if __name__ == "__main__":
    main()
