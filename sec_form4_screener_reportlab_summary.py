import requests
from bs4 import BeautifulSoup
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import os

# ----------- 1. Récupération des filings "Form 4" -----------

def get_recent_filings():
    URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.find_all("tr")
    filings = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            form = cols[3].text.strip()
            if form == "4":
                company = cols[0].text.strip()
                link = cols[1].find("a")
                if link:
                    href = "https://www.sec.gov" + link.get("href")
                else:
                    href = ""
                date_filed = cols[4].text.strip() if len(cols) > 4 else ""
                filings.append((company, href, date_filed))
    return filings

# ----------- 2. Vérification achat > 100k$ -----------

def is_buy_filing(url):
    """Retourne True si le Form 4 contient un achat > 100 000 $"""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        text = r.text.lower()
        if "transactionacquireddisposedcode" not in text or ">p<" not in text:
            return False

        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.find_all("tr")

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            joined = " ".join(cells).lower()

            if "p" not in joined or ("$" not in joined and "usd" not in joined):
                continue

            shares = None
            price = None
            for c in cells:
                c_clean = c.replace(",", "").replace("$", "").strip()
                try:
                    if "." in c_clean and len(c_clean) <= 8:
                        val = float(c_clean)
                        if val < 10000:
                            price = val
                    elif c_clean.isdigit() and len(c_clean) >= 3:
                        shares = float(c_clean)
                except:
                    continue

            if shares and price:
                total_value = shares * price
                if total_value > 100000:
                    print(f"💰 {url} → {total_value:,.0f} USD")
                    return True

        return False

    except Exception as e:
        print(f"Erreur sur {url}: {e}")
        return False

# ----------- 3. Génération du PDF -----------

def generate_pdf(buy_filings):
    output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    pdf_path = os.path.join(output_dir, f"SEC_Form4_Report_{today}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    styles = getSampleStyleSheet()
    Story = []

    Story.append(Paragraph(f"Rapport quotidien des achats (Form 4) – {today}", styles["Title"]))
    Story.append(Spacer(1, 12))

    if not buy_filings:
        Story.append(Paragraph("Aucun achat > 100 000 $ détecté aujourd’hui.", styles["Normal"]))
    else:
        data = [["Entreprise", "Date", "Lien SEC"]]
        for company, link, date_filed in buy_filings:
            data.append([company, date_filed, link])

        table = Table(data, colWidths=[200, 80, 250])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        Story.append(table)

    Story.append(Spacer(1, 12))
    Story.append(Paragraph(
        "Source : <a href='https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent'>SEC – Current Filings</a>",
        styles["Normal"]
    ))

    doc.build(Story)
    return pdf_path

# ----------- 4. Génération du résumé -----------

def generate_summary(buy_filings):
    summary_path = "summary.txt"
    with open(summary_path, "w") as f:
        if not buy_filings:
            f.write("Aucun achat > 100 000 $ détecté aujourd'hui.")
        else:
            f.write("Top des achats détectés :\n\n")
            for company, link, date_filed in buy_filings[:5]:
                f.write(f"{company} – {date_filed}\nLien SEC : {link}\n\n")
    return summary_path

# ----------- 5. Partie principale -----------

if __name__ == "__main__":
    print("🔍 Récupération des filings récents…")
    filings = get_recent_filings()

    buy_filings = []
    for company, link, date_filed in filings[:40]:  # limite 40 pour vitesse
        if link and is_buy_filing(link):
            buy_filings.append((company, link, date_filed))

    pdf_path = generate_pdf(buy_filings)
    summary_path = generate_summary(buy_filings)

    print(f"✅ Rapport PDF généré : {pdf_path}")
    print(f"✅ Résumé généré : {summary_path}")
