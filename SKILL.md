---
name: ua-devops-jobs
description: Daily job search for a Trainee/Junior DevOps, SysAdmin and Cloud engineer in any city of Ukraine or remote, plus remote international jobs. Collects new vacancies from Djinni, DOU, Robota.ua, LinkedIn, RemoteOK, We Work Remotely and Telegram, filters out senior and russian-linked jobs, and emails a report in Ukrainian to the user's own Gmail. Use this skill whenever the user asks to find, check or send DevOps / сисадмін / cloud вакансії, "пошукай роботу", "які нові вакансії", "надішли звіт про вакансії", or when the daily scheduled job-search task runs — even if they do not name the sites or the skill.
---

# Пошук DevOps / SysAdmin / Cloud вакансій

The user is a DevOps student in Ukraine looking for the first job: Trainee or Junior
DevOps, system administrator, cloud engineer and close roles (SRE, platform, helpdesk
with Linux, network admin). Good places: any city in Ukraine (office or hybrid), remote in Ukraine,
remote for international companies. The report goes to the user's own Gmail in Ukrainian.

Two bundled scripts do the heavy work, so a run is cheap and gives the same format
every day. Your part is the judgement the regex filters cannot do, and sending the email.

## Workflow

### 1. Collect

```bash
python3 ~/.claude/skills/ua-devops-jobs/scripts/fetch_jobs.py > "${TMPDIR:-/tmp}/ua-jobs-run.json"
```

It fetches all sources, drops jobs older than 3 days, senior titles and
obvious russian traces, and skips everything already sent before
(`~/.local/share/ua-devops-jobs/seen.json`). Output: `jobs`, `stats` per source,
`dropped` counts, `errors`. One broken source only adds a line to `errors` and does
not stop the run.

Flags: `--days N` for a longer window, `--all` to ignore the seen list (for tests).

### 2. Review the list

Read `jobs` (title, company, location, snippet). The script uses keywords only, so
some wrong jobs get through. Put the `id` of each job to remove, one per line, into
`${TMPDIR:-/tmp}/ua-jobs-drop.txt` (create an empty file if nothing to drop). Remove:

- **russian-linked companies.** The user does not want to work for them. Signs: HQ
  or legal entity in russia, russian market or clients, rubles, `.ru` products, known
  russian brands, or a company that moved from russia but still serves it. If unsure
  and the snippet gives no hint, keep the job: a false removal costs more than one line.
- **not a real tech role:** e.g. "адміністратор магазину / салону / ресепшн", sales,
  recruiter, marketing, even if the word "адміністратор" or "cloud" matched.
- **jobs outside Ukraine:** an office abroad (Warsaw, Sofia...) or remote only for
  people in other countries, e.g. "Bulgaria (remote), Poland (remote)" or "US only".
  The user lives in Ukraine, so such jobs are not open to them. Any Ukrainian city is fine.
- **clearly senior despite the title:** the snippet asks for 3+ years, or says
  "Senior" or "Lead" in the text.

Keep military units (бригади, ЗСУ): this is normal IT work in Ukraine.

### 3. Build the email

```bash
python3 ~/.claude/skills/ua-devops-jobs/scripts/build_email.py "${TMPDIR:-/tmp}/ua-jobs-run.json" \
  --drop-file "${TMPDIR:-/tmp}/ua-jobs-drop.txt" --out "${TMPDIR:-/tmp}/ua-jobs-email.html"
```

It prints the subject line and writes the HTML: a section for Ukraine and a section for
international remote jobs, junior-friendly jobs first and marked with ⭐, a block of
ready search links for Work.ua, Jooble, OLX and Grc.ua (they block scripts with
Cloudflare, so the user checks them by hand), and small notes about errors and filters.

Do not rewrite the HTML by hand. The script keeps the format the same every day.

### 4. Send

Load the Gmail send tool with ToolSearch (query `gmail send_message`). Its schema is
empty, so here are the fields that work:

- `to`: the user's own address as a plain string. Take it from the task prompt; if
  there is none, ask the user. An array fails with "Invalid email address" because it
  arrives as the text `["..."]`.
- `subject`: the line printed by `build_email.py`
- `htmlBody`: the whole HTML file content, copied exactly
- `body`: one short plain-text line with the job count, for mail apps without HTML

A success returns `{"id": ..., "threadId": ...}`.

Send the report even when there are 0 new jobs. The short "нових немає" email shows
the user that the daily task still works.

If the Gmail tool fails (for example "requires additional permissions" means the
connector must be reconnected in claude.ai settings with send access), do not lose
the report: copy the HTML to `~/Desktop/ua-devops-jobs-<YYYY-MM-DD>.html`, tell the
user what failed, and skip step 5 so the same jobs go into the next email.

If the user asked for a test or dry run ("тест", "не надсилай", "dry run"), do not send.
Show the subject and the HTML file path instead, and skip step 5.

### 5. Remember what was sent

Only after the email was sent:

```bash
python3 ~/.claude/skills/ua-devops-jobs/scripts/fetch_jobs.py --mark-seen "${TMPDIR:-/tmp}/ua-jobs-run.json"
```

This saves all jobs from the run, the dropped ones too, so they do not come back
tomorrow. If sending failed, do not mark them: the next run will try again.

### 6. Reply

One or two lines in Ukrainian: how many jobs went into the report and from which
sources, plus any source from `errors`. The user reads the details in the email.

## Cloud runs without saved state

A scheduled cloud session starts from a clean checkout, so `seen.json` from the last
run is gone. In that case run `fetch_jobs.py --days 1` in step 1: with one run per day
at the same hour, the last 24 hours give almost no repeats and no gaps. Skip step 5
(`--mark-seen`), and if sending fails there is no Desktop, so just report the error in
the final message.

## When a source breaks

Job sites change their HTML and feeds. If a source keeps failing in `errors`, or
suddenly gives 0 jobs while it usually gives some, tell the user and offer to fix
`fetch_jobs.py`. Do not try to get around Cloudflare, captchas or logins: those sites
go to the manual links block.

## Sources

| Source | How | Notes |
|---|---|---|
| Djinni | RSS, `exp_level=no_exp,1y` | DevOps, Sysadmin, Cloud; RSS has no company name |
| DOU | RSS, `exp=0-1,1-3` | DevOps, SysAdmin |
| Robota.ua | public JSON API | 5 keyword searches, all cities |
| LinkedIn | public guest search | 4 requests, entry level, last 3 days; keep the volume low |
| RemoteOK, We Work Remotely | JSON / RSS | international remote, mostly senior, often 0 |
| Telegram `@remote_devops_jobs` | t.me/s web preview | the grade is added to the title as `[senior]` |
| Work.ua, Jooble, OLX, Grc.ua | links only | blocked by Cloudflare or no public API |
