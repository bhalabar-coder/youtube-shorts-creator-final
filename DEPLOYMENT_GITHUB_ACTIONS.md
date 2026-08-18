# Deploying via GitHub Actions (free, no card required)

This runs the pipeline on a fresh GitHub-hosted machine every morning at
7:00 AM IST, using `.github/workflows/daily-short.yml` (already included
in this project).

No persistent server — each run starts clean, installs Ollama, pulls the
model, generates the video, uploads it, and shuts down.

---

## 1. Push this project to a GitHub repo

```bash
cd ai-youtube-shorts
git init
git add .
git commit -m "Initial commit"
```

Create a repo at https://github.com/new (private is fine, no card
needed), then:
```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

A **private** repo keeps your generated scripts/topics out of public
view and still gets 2,000 free Action minutes/month — a daily 15–20
minute run uses roughly 450–600 minutes/month, well within that.

---

## 2. Do the YouTube login locally (same as before)

The runner has no browser, so this step still happens on your own
machine, once:

1. Put `client_secret.json` (from Google Cloud Console) in
   `credentials/client_secret.json`.
2. Run:
   ```bash
   python setup_youtube_auth.py
   ```
   This creates `credentials/token.json`.

---

## 3. Add secrets to the repo (Settings → Secrets and variables → Actions)

Base64-encode the two YouTube files so they can be stored as text
secrets:

```bash
base64 -w0 credentials/client_secret.json   # copy the output
base64 -w0 credentials/token.json           # copy the output
```
(On macOS, drop `-w0` and use `base64 -i credentials/client_secret.json`.)

Add these **Repository secrets**:

| Name | Value |
|---|---|
| `YOUTUBE_CLIENT_SECRET_B64` | output of the first base64 command |
| `YOUTUBE_TOKEN_B64` | output of the second base64 command |
| `PEXELS_API_KEY` | your Pexels key |
| `PIXABAY_API_KEY` | your Pixabay key (optional) |

Optionally add a **Repository variable** (not secret) `MODEL_NAME` if you
want a different Ollama model than the default `llama3.2`.

**Never commit `credentials/` or `.env` to the repo** — they're already
in `.gitignore`. Secrets only ever live in GitHub's encrypted secrets
store and as env vars inside the run.

---

## 4. Confirm the schedule

`.github/workflows/daily-short.yml` already contains:
```yaml
on:
  schedule:
    - cron: "30 1 * * *"   # 01:30 UTC = 07:00 IST
  workflow_dispatch: {}
```
GitHub Actions cron always runs in UTC, so IST (UTC+5:30) is encoded as
the UTC-equivalent time — no server timezone setting needed like the VM
approach.

`workflow_dispatch` also lets you trigger a run manually from the
**Actions** tab any time, which is the easiest way to test it before
trusting the schedule.

---

## 5. Test it

Go to your repo → **Actions** tab → **Daily YouTube Short** → **Run
workflow** (this uses `workflow_dispatch`). Watch the logs. If it
succeeds, the video is both uploaded to YouTube and attached to the run
as a downloadable artifact for 7 days (handy for debugging without
waiting for the next scheduled run).

---

## Things that behave differently from a persistent VM

- **No disk persistence between runs.** Ollama and the Whisper model are
  downloaded fresh every run (the workflow caches `~/.ollama` via
  `actions/cache` to speed this up, but cache isn't guaranteed to
  survive indefinitely — GitHub evicts caches unused for 7+ days, which
  won't happen if you're running daily).
- **Topic history is committed back to the repo** after each run (see
  the `Persist topic history` step) so topic rotation still works across
  days — this is the one piece of state the workflow deliberately
  writes back to git.
- **Scheduled workflows can be silently disabled** by GitHub if a repo
  has zero activity for 60 days. A daily commit from the topic-history
  step counts as activity, so this shouldn't bite you — but if you ever
  pause the schedule for two months, re-enable it manually from the
  Actions tab afterward.
- **Runner resources**: GitHub's standard Ubuntu runners currently ship
  with several GB of RAM and multiple vCPUs — enough for `llama3.2` (3B)
  plus MoviePy rendering of a ~30s vertical video. If you switch to a
  larger model, watch the run time against the 45-minute timeout set in
  the workflow.
