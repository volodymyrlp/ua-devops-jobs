#!/usr/bin/env python3
"""Build the HTML email report from fetch_jobs.py output.

Usage:
  python3 build_email.py run.json --out email.html [--drop-file drop.txt]

Prints the email subject. drop.txt has one job id (url) per line, these jobs are skipped.
"""
import argparse
import html
import json
import re
from datetime import datetime

JUNIOR_RE = re.compile(r"junior|trainee|intern|стажер|молодш|початків|entry|associate|\bl1\b", re.I)

# sites that block scripts (Cloudflare), so the report gives ready search links
MANUAL_LINKS = [
    ("Work.ua", "DevOps, вся Україна", "https://www.work.ua/jobs-devops/"),
    ("Work.ua", "DevOps, дистанційно", "https://www.work.ua/jobs-remote-devops/"),
    ("Work.ua", "Системний адміністратор, вся Україна", "https://www.work.ua/jobs-системний+адміністратор/"),
    ("Jooble", "Junior DevOps", "https://ua.jooble.org/SearchResult?ukw=junior%20devops"),
    ("Jooble", "Системний адміністратор", "https://ua.jooble.org/SearchResult?ukw=системний%20адміністратор"),
    ("OLX Робота", "DevOps", "https://www.olx.ua/uk/rabota/q-devops/"),
    ("OLX Робота", "Системний адміністратор", "https://www.olx.ua/uk/rabota/q-системний-адміністратор/"),
    ("Grc.ua", "DevOps", "https://grc.ua/searchjob/k-devops"),
]

REASONS = {
    "not a devops/sysadmin/cloud role": "не та роль",
    "too old": "старі",
    "too senior": "Senior/Middle/Lead",
    "russian trace": "російський слід",
    "duplicate": "дублікати з інших сайтів",
}

MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]


def short_date(iso):
    if not iso:
        return ""
    d = datetime.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]}"


def e(text):
    return html.escape(text or "")


def job_html(j):
    # short on purpose: the whole HTML goes through the Gmail tool call every day
    star = "⭐ " if JUNIOR_RE.search(j["title"]) else ""
    meta = [x for x in [j["company"], j["location"], j["salary"]] if x]
    meta.append(f'{j["source"]}, {short_date(j["date"])}' if j["date"] else j["source"])
    return (f'<p style="margin:0 0 12px"><a href="{e(j["url"])}"><b>{star}{e(j["title"])}</b></a><br>'
            f'<small style="color:#555">{e(" · ".join(meta))}</small></p>')


def section(title, jobs):
    if not jobs:
        return ""
    # junior-friendly first, then newest
    jobs = sorted(jobs, key=lambda j: j["date"], reverse=True)
    jobs = sorted(jobs, key=lambda j: not JUNIOR_RE.search(j["title"]))
    rows = "".join(job_html(j) for j in jobs)
    return f"<h2>{title} ({len(jobs)})</h2>{rows}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--drop-file")
    args = ap.parse_args()

    with open(args.run_json) as f:
        run = json.load(f)
    drop = set()
    if args.drop_file:
        with open(args.drop_file) as f:
            drop = {line.strip() for line in f if line.strip()}

    jobs = [j for j in run["jobs"] if j["id"] not in drop]
    ua = [j for j in jobs if j["region"] == "ua"]
    intl = [j for j in jobs if j["region"] == "intl"]

    by_source = {}
    for j in jobs:
        by_source[j["source"]] = by_source.get(j["source"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items(), key=lambda x: -x[1]))

    today = datetime.now().strftime("%d.%m.%Y")
    subject = f"DevOps / SysAdmin / Cloud вакансії {today}, нових: {len(jobs)}"

    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:680px;margin:auto;color:#222">',
        f'<h1 style="font-size:22px;margin-bottom:4px">Вакансії DevOps / SysAdmin / Cloud, {today}</h1>',
    ]
    if jobs:
        parts.append(f'<p style="color:#555;margin-top:0">Нових вакансій: <b>{len(jobs)}</b> ({e(summary)}). '
                     "⭐ означає, що в назві є Junior, Trainee або Intern.</p>")
    elif run.get("errors") and not run.get("stats"):
        # every source failed, so "no new jobs" would be a lie
        parts.append('<p style="color:#b91c1c">Не вдалося прочитати жоден сайт, тому вакансій немає. '
                     "Причина внизу листа.</p>")
    else:
        parts.append('<p style="color:#555">Нових вакансій з минулого звіту немає. Скіл відпрацював нормально.</p>')

    parts.append(section("🇺🇦 Україна: усі міста і віддалено", ua))
    parts.append(section("🌍 Міжнародні, remote", intl))

    links = "".join(f'<li><a href="{e(u)}">{e(site)}: {e(label)}</a></li>' for site, label, u in MANUAL_LINKS)
    parts.append('<h2 style="font-size:18px;margin:24px 0 4px">🔎 Перевір вручну</h2>'
                 '<p style="font-size:13px;color:#555;margin:0">Ці сайти блокують автоматичний пошук, тому тут готові посилання:</p>'
                 f'<ul style="font-size:14px">{links}</ul>')

    notes = []
    if run.get("errors"):
        notes.append("Не вдалося прочитати: " + "; ".join(run["errors"]))
    if drop:
        notes.append(f"Відсіяно при перевірці: {len(drop)}")
    dropped = run.get("dropped", {})
    if dropped:
        notes.append("Відсіяно фільтрами: " + ", ".join(f"{REASONS.get(k, k)}: {v}" for k, v in dropped.items()))
    if notes:
        parts.append('<p style="font-size:12px;color:#999;margin-top:28px">' + "<br>".join(e(n) for n in notes) + "</p>")
    parts.append("</div>")

    with open(args.out, "w") as f:
        f.write("\n".join(p for p in parts if p))
    print(subject)


if __name__ == "__main__":
    main()
