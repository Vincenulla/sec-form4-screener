#!/usr/bin/env python3
import datetime, os, pathlib

today = datetime.date.today().isoformat()
summary_file = "summary.txt"
pdf_file = f"reports/form4_report_{today}.pdf"

summary_text = "Aucun résumé trouvé."
if os.path.exists(summary_file):
    summary_text = open(summary_file).read().strip()

html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Form 4 Report {today}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2em; }}
pre {{ background:#f6f6f6; padding:1em; border-radius:8px; }}
a.pdf {{ display:inline-block; margin-top:1em; padding:8px 12px; background:#0073e6; color:white; text-decoration:none; border-radius:4px; }}
a.pdf:hover {{ background:#005bb5; }}
</style>
</head>
<body>
<h1>Form 4 – Rapport du {today}</h1>
<p>Voici le résumé des 3 plus gros achats d’initiés du jour :</p>
<pre>{summary_text}</pre>
<a href="{pdf_file}" class="pdf">📎 Télécharger le rapport PDF</a>
<hr>
<p style="font-size:small;">Généré automatiquement à 22h via GitHub Actions.</p>
</body>
</html>
"""

os.makedirs("public/history", exist_ok=True)
with open(f"public/history/{today}.html", "w") as f:
    f.write(html)

pathlib.Path("public/index.html").write_text(html)
print("✅ Pages HTML créées dans public/")
