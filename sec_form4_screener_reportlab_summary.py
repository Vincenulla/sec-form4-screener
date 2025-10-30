import requests
from bs4 import BeautifulSoup
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import os

# ----------- 1. Récupération des filings "Form 4" sur le site de la SEC -----------

URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "html.parser")

rows = soup.find_all("tr")

form4_filings = []
for row in rows:
    cols = row.find_all("td")
    if len(cols) >= 4:
        form = cols[3].text.strip()
        if "4" == form:  # on ne garde que les Form 4
            company = cols[0].text.strip()
            link = cols[1].find("a")
            if link:
                href = "https://www.sec.gov" + link.get("href")
            else:
                href = ""
            date_filed = cols[4].text.strip() if len(cols) > 4 else ""
            form4_filings.append((company, href, date_filed))

# ----------- 2. Filtrage simple des achats (buy) -----------

def is_buy_filing(url):
    """Retourne True si le Form 4 contient un achat (code 'P') dont le montant est > 100k$."""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        text = r.text.lower()

        # On détecte les transactions d'achat
        if "transactionacquireddisposedcode" not in text or ">p<" not in text:
            return False

        # Recherche de lignes contenant le prix et la quantité
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(cells) < 5:
                    continue

                # On cherche les codes de transaction (P pour Purchase)
                if "p" in cells[0].lower() or "p" in "".join(cells).lower():
                    # Extraction approximative de quantité et prix
                    try:
                        shares = None
                        price = None
                        for c in cells:
                            if "$" in c or "usd" in c.lower():
                                price = float(c.replace("$", "").replace(",", "").split()[0])
                            elif c.replace(",", "").isdigit():
                                shares = float(c.replace(",", ""))

                        if shares and price:
                            total_value = shares * price
                            if total_value > 50000:
                                return True
                    except Exception:
                        continue
        return False

    except Exception:
        return False

# ----------- 2b. Génération du résumé (summary.txt) -----------

summary_path = "summary.txt"
with open(summary_path, "w") as f:
    if not buy_filings:
        f.write("Aucun achat (Form 4) détecté aujourd'hui.")
    else:
        f.write("Top des achats détectés :\n\n")
        for company, link, date_filed in buy_filings[:5]:
            f.write(f"{company} – {date_filed}\nLien SEC : {link}\n\n")

# ----------- 3. Génération du PDF -----------

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
    Story.append(Paragraph("Aucun achat (Form 4) détecté aujourd’hui.", styles["Normal"]))
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
Story.append(Paragraph("Source : <a href='https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent'>SEC – Current Filings</a>", styles["Normal"]))

doc.build(Story)

print(f"✅ Rapport PDF généré : {pdf_path}")
print(f"✅ Résumé généré : {summary_path}")
