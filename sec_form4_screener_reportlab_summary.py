import requests
from bs4 import BeautifulSoup
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import re

# Configuration
USER_AGENT = "Mozilla/5.0 (compatible; SECForm4Screener/2.0; +mailto:vincent.form4bot@gmail.com)"
HEADERS_JSON = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json"
}
HEADERS_HTML = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"
}
PDF_FILE = "Form4_Report.pdf"
SUMMARY_FILE = "email_summary.txt"
MIN_VALUE = 100_000


def fetch_from_edgar_next():
    """Try to fetch recent Form 4 filings via EDGAR Next endpoint.
    Returns a list of filings dicts with keys: title, link_html, date."""
    print("Attempting EDGAR Next API...")
    api_url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": 'formType:"4"',
        "from": "0",
        "size": "100",
        "sort": "filedAt:desc"
    }
    try:
        r = requests.get(api_url, headers=HEADERS_JSON, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        # data may contain hits in different shapes: check both
        hits = []
        if isinstance(data, dict):
            if "hits" in data and isinstance(data["hits"], dict) and "hits" in data["hits"]:
                hits = data["hits"]["hits"]
            elif "hits" in data and isinstance(data["hits"], list):
                hits = data["hits"]
            elif "results" in data and isinstance(data["results"], list):
                hits = data["results"]
        filings = []
        for h in hits:
            # Several possible shapes: try safely
            src = h.get("_source") if isinstance(h, dict) and "_source" in h else h
            accession = src.get("accessionNo") or src.get("adsh") or src.get("accession") or ""
            cik = ""
            if isinstance(src.get("ciks"), list) and src.get("ciks"):
                cik = src.get("ciks")[0]
            else:
                cik = src.get("cik") or src.get("companyCik") or ""
            company = ""
            if isinstance(src.get("displayNames"), list) and src.get("displayNames"):
                company = src.get("displayNames")[0]
            else:
                company = src.get("companyName") or src.get("issuerName") or ""
            filedAt = src.get("filedAt") or src.get("filed") or src.get("filedAtDate") or ""
            if accession and cik:
                accession_clean = accession.replace("-", "")
                link_html = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{accession}-index.htm"
            else:
                # fallback to any available URL
                link_html = src.get("link") or src.get("url") or ""
            if not link_html:
                continue
            filings.append({
                "title": f"Form 4 – {company}" if company else "Form 4",
                "link_html": link_html,
                "date": filedAt[:10] if filedAt else ""
            })
        print(f"EDGAR Next: found {len(filings)} filings")
        return filings
    except Exception as e:
        print("EDGAR Next API unavailable or blocked:", e)
        return []


def fetch_from_rss():
    """Fallback: fetch atom RSS from sec.gov (may be blocked)."""
    print("Attempting RSS fallback...")
    rss_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&count=100&output=atom"
    try:
        r = requests.get(rss_url, headers=HEADERS_HTML, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "xml")
        entries = soup.find_all("entry")
        filings = []
        for e in entries:
            title = e.find("title").text.strip() if e.find("title") else "Form 4"
            link_tag = e.find("link")
            link = link_tag["href"] if link_tag and link_tag.get("href") else ""
            updated = e.find("updated").text[:10] if e.find("updated") else ""
            if link:
                filings.append({"title": title, "link_html": link, "date": updated})
        print(f"RSS fallback: found {len(filings)} filings")
        return filings
    except Exception as e:
        print("RSS fallback failed:", e)
        return []


def fetch_recent_filings():
    """Unified fetch: try EDGAR Next then RSS fallback."""
    filings = fetch_from_edgar_next()
    if filings:
        return filings
    return fetch_from_rss()


def safe_float(text):
    """Try to extract a float from text (strip commas, remove currency)."""
    if not text:
        return 0.0
    t = re.sub(r"[^\d\.\-]", "", text)
    try:
        return float(t)
    except:
        return 0.0


def parse_transaction_value(trans):
    """Try different paths to compute transaction value for a nonDerivativeTransaction bs4 tag."""
    # 1) direct transactionValue node
    vnode = trans.find("transactionValue")
    if vnode and vnode.get_text(strip=True):
        return safe_float(vnode.get_text(strip=True))
    # 2) transactionAmounts/transactionValue or transactionAmounts/transactionValue/value
    ta = trans.find("transactionAmounts")
    if ta:
        tv = ta.find("transactionValue")
        if tv and tv.get_text(strip=True):
            return safe_float(tv.get_text(strip=True))
        # try nested value node
        v = ta.find("value")
        if v and v.get_text(strip=True):
            return safe_float(v.get_text(strip=True))
    # 3) compute shares * price if available
    shares = None
    price = None
    s_node = trans.find("transactionShares")
    if s_node:
        # transactionShares may contain a nested 'value' or direct text
        v = s_node.find("value")
        shares = safe_float(v.get_text(strip=True) if v else s_node.get_text(strip=True))
    p_node = trans.find("transactionPricePerShare")
    if p_node:
        v = p_node.find("value")
        price = safe_float(v.get_text(strip=True) if v else p_node.get_text(strip=True))
    if shares and price:
        return shares * price
    # last resort: try any numeric in the trans text that looks like a large amount
    nums = re.findall(r"\$?[\d{1,3},]+\.\d+|\$?[\d,]{6,}", trans.get_text())
    for n in nums:
        val = safe_float(n)
        if val >= 1000:
            return val
    return 0.0


def parse_form4_details(filing):
    """Parse the form 4 XML and compute total purchases (nonDerivativeTransaction with code 'P')."""
    try:
        xml_url = filing["link_html"].replace("-index.htm", ".xml")
        # sometimes link_html may already be .htm or other; try to standardize
        if xml_url.endswith(".htm"):
            xml_url = xml_url.replace(".htm", ".xml")
        r = requests.get(xml_url, headers=HEADERS_HTML, timeout=30)
        if r.status_code != 200:
            print("Could not fetch XML:", xml_url, "status:", r.status_code)
            return None
        xml = BeautifulSoup(r.text, "lxml-xml")

        issuer_name = xml.find("issuerName").get_text(strip=True) if xml.find("issuerName") else ""
        # rptOwnerName may appear in reportingOwner or rptOwner
        insider_name = ""
        if xml.find("rptOwnerName"):
            insider_name = xml.find("rptOwnerName").get_text(strip=True)
        else:
            ro = xml.find("reportingOwner")
            if ro and ro.find("rptOwnerName"):
                insider_name = ro.find("rptOwnerName").get_text(strip=True)

        total_value = 0.0
        # consider nonDerivativeTransaction and derivativeTransaction where appropriate
        for trans in xml.find_all("nonDerivativeTransaction"):
            try:
                code_tag = trans.find("transactionCoding")
                code = ""
                if code_tag and code_tag.find("transactionCode"):
                    code = code_tag.find("transactionCode").get_text(strip=True)
                else:
                    # older forms may have <transactionCode> directly
                    if trans.find("transactionCode"):
                        code = trans.find("transactionCode").get_text(strip=True)
                if code != "P":
                    continue
                val = parse_transaction_value(trans)
                total_value += val
            except Exception:
                continue

        # Some filings may list multiple transactions; we aggregated total_value
        if total_value >= MIN_VALUE:
            return {
                "issuer": issuer_name or filing.get("title", "").replace("Form 4 -", "").strip(),
                "insider": insider_name or "Unknown",
                "date": filing.get("date", "")[:10],
                "value": total_value,
                "link_html": filing["link_html"]
            }
        else:
            if total_value > 0:
                print(f"Ignored (below threshold): {filing.get('title')} value={total_value:.2f}")
            return None
    except Exception as e:
        print("Error parsing form4 details for", filing.get("link_html"), ":", e)
        return None


def generate_pdf(filings):
    print("Generating PDF...")
    doc = SimpleDocTemplate(PDF_FILE, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("SEC Form 4 - Insider Buys > 100k USD", styles["Heading1"]))
    story.append(Spacer(1, 12))
    if not filings:
        story.append(Paragraph("No insider purchases > 100k USD found today.", styles["Normal"]))
    else:
        data = [["Company", "Insider", "Date", "Value (USD)", "Link"]]
        for f in filings:
            link_html = f'<a href="{f["link_html"]}">Open</a>'
            data.append([f["issuer"], f["insider"], f["date"], f"${f['value']:,.0f}", Paragraph(link_html, styles["Normal"])])
        table = Table(data, colWidths=[2.2*inch, 1.7*inch, 1.0*inch, 1.3*inch, 1.0*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE")
        ]))
        story.append(table)
    doc.build(story)
    print("PDF created:", PDF_FILE)


def generate_summary_file(filings):
    with open(SUMMARY_FILE, "w", encoding="utf-8") as fh:
        if not filings:
            fh.write("No insider purchases > 100k USD found today.\n")
        else:
            for f in filings:
                fh.write(f"{f['issuer']} | {f['insider']} | {f['date']} | ${f['value']:,.0f} | {f['link_html']}\n")
    print("Summary file written:", SUMMARY_FILE)


def main():
    print("Starting screener at", datetime.utcnow().isoformat())
    filings = fetch_recent_filings()
    print("Fetched filings count:", len(filings))
    results = []
    for filing in filings:
        d = parse_form4_details(filing)
        if d:
            results.append(d)
    print("Matches found:", len(results))
    generate_pdf(results)
    generate_summary_file(results)
    print("Done.")


if __name__ == "__main__":
    main()
