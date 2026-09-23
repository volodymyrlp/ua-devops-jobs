# ua-devops-jobs

Agent skill for Claude Code. It looks for Trainee / Junior DevOps, SysAdmin and Cloud
jobs in Ukraine and sends a short report to Gmail every day.

- `scripts/fetch_jobs.py` collects new jobs from Djinni, DOU, Robota.ua, LinkedIn,
  RemoteOK, We Work Remotely and a Telegram channel. Python standard library only.
- `scripts/build_email.py` turns the result into a compact HTML email.
- `SKILL.md` tells the agent how to review the list and send the email.

Run it by hand:

```bash
python3 scripts/fetch_jobs.py --days 1 > run.json
python3 scripts/build_email.py run.json --out email.html
```

Work.ua, Jooble, OLX and Grc.ua block scripts, so the email only has search links for them.
