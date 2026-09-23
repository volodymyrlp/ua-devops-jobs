#!/usr/bin/env python3
"""Collect fresh DevOps / SysAdmin / Cloud vacancies from job sites that allow plain HTTP.

Usage:
  python3 fetch_jobs.py [--days 3] [--all]      -> prints JSON with new jobs
  python3 fetch_jobs.py --mark-seen run.json     -> saves job ids from run.json as seen

Only the Python standard library is used, so it runs on any Mac without pip.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

STATE_FILE = os.path.expanduser("~/.local/share/ua-devops-jobs/seen.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"

# the role must look like one of these
ROLE_RE = re.compile(
    r"devops|dev ops|\bsre\b|site reliability|sysadmin|sys admin|system admin|systems admin|"
    r"сисадмін|системн\w* адмін|адміністратор|cloud|platform engineer|infrastructure|"
    r"інфраструктур|kubernetes|\blinux\b|network engineer|мережев\w* інженер|helpdesk|help desk|"
    r"it support|технічн\w* підтримк|devsecops|mlops|release engineer|build engineer",
    re.I,
)
# too senior for trainee / junior
SENIOR_RE = re.compile(
    r"senior|\bsr\.?\b|\blead\b|team ?lead|tech ?lead|principal|\bhead\b|architect|\bstaff\b|"
    r"middle|\bmid\b|mid-level|manager|director|старш|провідн|керівник|сеньйор|мідл|\bl3\b",
    re.I,
)
# russian traces: cities, currency, domains
RU_RE = re.compile(
    r"москв|moscow|санкт-петербург|saint petersburg|\bрф\b|россия|russia\b|₽|\bруб\b|\bрублей\b|"
    r"\.ru\b|yandex|яндекс|сбер|sber\b|\bvk\.com|kaspersky|касперск",
    re.I,
)


def get(url, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code < 500:
            raise
        # 502/503 are usually short, try once more
        time.sleep(5)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")


def clean(text, limit=300):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def rss_items(xml):
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def tag(name):
            m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
            if not m:
                return ""
            val = m.group(1)
            if val.startswith("<![CDATA["):
                val = val[9:-3]
            return html.unescape(val)
        items.append({"title": tag("title"), "link": tag("link"), "desc": tag("description"), "date": tag("pubDate")})
    return items


def parse_date(value):
    if not value:
        return None
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone(timedelta(hours=3)))  # ukrainian sites give local time
    return d


def job(source, title, url, company="", location="", salary="", date=None, snippet="", region="ua"):
    return {
        "id": url.split("?")[0].rstrip("/"),
        "source": source,
        "region": region,  # ua = ukrainian market, intl = international remote
        "title": clean(title, 200),
        "company": clean(company, 100),
        "location": clean(location, 100),
        "salary": salary,
        "date": date.isoformat() if date else "",
        "url": url,
        "snippet": clean(snippet),
    }


# ---- sources ----

def djinni():
    out = []
    for kw in ["DevOps", "Sysadmin", "Cloud"]:
        # no_exp and 1y = trainee / junior level on Djinni
        xml = get("https://djinni.co/jobs/rss/", {"primary_keyword": kw, "exp_level": ["no_exp", "1y"]})
        for it in rss_items(xml):
            out.append(job("Djinni", it["title"], it["link"], date=parse_date(it["date"]), snippet=it["desc"]))
    return out


def dou():
    out = []
    for cat in ["DevOps", "SysAdmin"]:
        for exp in ["0-1", "1-3"]:
            xml = get("https://jobs.dou.ua/vacancies/feeds/", {"category": cat, "exp": exp})
            for it in rss_items(xml):
                # title looks like "DevOps Engineer в Company, $4000–5000, віддалено"
                title, company, rest = it["title"], "", ""
                m = re.match(r"(.*?) в (.*?)(?:, (.*))?$", it["title"])
                if m:
                    title, company, rest = m.group(1), m.group(2), m.group(3) or ""
                salary = ""
                parts = [p.strip() for p in rest.split(",") if p.strip()]
                if parts and re.search(r"[$€₴]|грн", parts[0]):
                    salary = clean(parts.pop(0), 60)
                out.append(job("DOU", title, it["link"], company, ", ".join(parts), salary,
                               parse_date(it["date"]), it["desc"]))
    return out


def robota():
    out = []
    for kw in ["devops", "системний адміністратор", "cloud engineer", "sre", "linux адміністратор"]:
        data = json.loads(get("https://api.rabota.ua/vacancy/search", {"keyWords": kw, "count": 40}))
        for v in data.get("documents", []):
            salary = ""
            if v.get("salaryFrom") or v.get("salaryTo"):
                salary = f"{v.get('salaryFrom') or ''}–{v.get('salaryTo') or ''} грн".strip("–")
            elif v.get("salary"):
                salary = f"{v['salary']} грн"
            url = f"https://robota.ua/company{v['notebookId']}/vacancy{v['id']}"
            out.append(job("Robota.ua", v.get("name", ""), url, v.get("companyName", ""), v.get("cityName", ""),
                           salary, parse_date(v.get("date")), v.get("shortDescription", "")))
    return out


def remoteok():
    out = []
    for tag in ["devops", "sysadmin", "cloud"]:
        data = json.loads(get("https://remoteok.com/api", {"tag": tag}))
        for v in data[1:]:  # first element is a legal notice
            salary = ""
            if v.get("salary_min"):
                salary = f"${v['salary_min']}–{v.get('salary_max') or ''}"
            out.append(job("RemoteOK", v.get("position", ""), v.get("url", ""), v.get("company", ""),
                           v.get("location") or "Remote", salary, parse_date(v.get("date")),
                           v.get("description", ""), region="intl"))
    return out


def weworkremotely():
    out = []
    xml = get("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss")
    for it in rss_items(xml):
        company, title = "", it["title"]
        if ": " in title:
            company, title = title.split(": ", 1)
        out.append(job("We Work Remotely", title, it["link"], company, "Remote", "",
                       parse_date(it["date"]), it["desc"], region="intl"))
    return out


# @dou_jobs was dropped: it only repeats the DOU feed
TELEGRAM = {"remote_devops_jobs": "intl"}


def telegram():
    out = []
    for channel, region in TELEGRAM.items():
        page = get(f"https://t.me/s/{channel}")
        for block in page.split('class="tgme_widget_message_wrap')[1:]:
            post = re.search(r'data-post="([^"]+)"', block)
            text = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
            when = re.search(r'datetime="([^"]+)"', block)
            if not post or not text:
                continue
            body = clean(text.group(1), 600)
            # posts look like "Company name : X  Title : Y  Salary : Z"
            title = re.search(r"Title\s*:\s*(.+?)\s+(?:Grades|Salary|Location|Tags|Job desc|Apply|$)", body)
            company = re.search(r"Company name\s*:\s*(.+?)\s+Title", body)
            grades = re.search(r"Grades\s*:\s*(.+?)\s+(?:Job desc|Salary|Location|$)", body)
            if title:
                title = title.group(1)
                # put the grade into the title so the senior filter can see it
                if grades:
                    title += f" [{grades.group(1)}]"
            else:
                title = clean(text.group(1).split("<br")[0], 200) or body[:120]
            out.append(job(f"Telegram @{channel}", title, f"https://t.me/{post.group(1)}",
                           company.group(1) if company else "", "Remote",
                           date=parse_date(when.group(1) if when else ""), snippet=body, region=region))
    return out


def linkedin():
    # public guest search, no login. LinkedIn does not like bots, so only 4 small requests
    searches = [
        ("devops", "Ukraine", {}, "ua"),
        ("system administrator", "Ukraine", {}, "ua"),
        ("cloud engineer", "Ukraine", {}, "ua"),
        # the guest API ignores the remote filter (f_WT), so search "remote" by words.
        # this finds foreign companies that hire remote people in Ukraine
        ("remote devops", "Ukraine", {}, "ua"),
    ]
    out = []
    for keywords, location, extra, region in searches:
        params = {"keywords": keywords, "location": location,
                  "f_TPR": "r259200",  # last 3 days
                  "f_E": "1,2"}  # internship + entry level
        params.update(extra)
        page = get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search", params)
        for card in page.split("<li")[1:]:
            title = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', card, re.S)
            company = re.search(r'base-search-card__subtitle">.*?>\s*(.*?)\s*</a>', card, re.S)
            loc = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', card, re.S)
            when = re.search(r'datetime="([^"]+)"', card)
            url = re.search(r'href="(https://[a-z]+\.linkedin\.com/jobs/view/[^"?]+)', card)
            if not title or not url:
                continue
            out.append(job("LinkedIn", title.group(1), url.group(1),
                           company.group(1) if company else "", loc.group(1) if loc else "",
                           date=parse_date(when.group(1) if when else ""), region=region))
    return out


SOURCES = [djinni, dou, robota, linkedin, remoteok, weworkremotely, telegram]


# ---- filters ----

def keep(j, since):
    text = f"{j['title']} {j['company']} {j['location']} {j['snippet']}"
    if not ROLE_RE.search(j["title"] + " " + (j["snippet"] if j["source"].startswith("Telegram") else "")):
        return "not a devops/sysadmin/cloud role"
    if SENIOR_RE.search(j["title"]):
        return "too senior"
    if RU_RE.search(text):
        return "russian trace"
    if j["date"] and datetime.fromisoformat(j["date"]) < since:
        return "too old"
    return None


def same_job_key(j):
    # the same vacancy often comes from two sites, e.g. DOU and LinkedIn.
    # compare the title and the first word of the company name
    title = re.sub(r"\W+", " ", j["title"].lower()).strip()
    company = (re.sub(r"\W+", " ", j["company"].lower()).split() or [""])[0]
    return f"{title}|{company}" if company else None


def load_seen():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def mark_seen(run_file):
    with open(run_file) as f:
        jobs = json.load(f)
    jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    seen = load_seen() | {j["id"] for j in jobs}
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=0)
    print(f"saved {len(jobs)} ids, {len(seen)} total in {STATE_FILE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="skip jobs older than this")
    ap.add_argument("--all", action="store_true", help="ignore the seen list")
    ap.add_argument("--mark-seen", metavar="RUN_JSON")
    args = ap.parse_args()

    if args.mark_seen:
        mark_seen(args.mark_seen)
        return

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    seen = set() if args.all else load_seen()
    jobs, errors, stats, dropped = [], [], {}, {}
    ids, keys = set(), set()

    for source in SOURCES:
        try:
            found = source()
        except Exception as e:  # one broken site should not kill the whole report
            errors.append(f"{source.__name__}: {e}")
            continue
        new = 0
        for j in found:
            if j["id"] in ids or j["id"] in seen:
                continue
            reason = keep(j, since)
            if reason:
                dropped[reason] = dropped.get(reason, 0) + 1
                continue
            key = same_job_key(j)
            if key in keys:
                dropped["duplicate"] = dropped.get("duplicate", 0) + 1
                continue
            if key:
                keys.add(key)
            ids.add(j["id"])
            jobs.append(j)
            new += 1
        stats[source.__name__] = {"fetched": len(found), "new": new}

    jobs.sort(key=lambda j: j["date"], reverse=True)
    json.dump({"jobs": jobs, "stats": stats, "dropped": dropped, "errors": errors},
              sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
