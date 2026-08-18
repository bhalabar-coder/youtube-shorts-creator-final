# Deploying the AI YouTube Shorts Generator — 7:00 AM IST Daily

There's no user-facing "web app" here — this deploys as an unattended
background job on a small cloud server that wakes up once a day, builds a
video, and uploads it. Everything below uses free tiers.

---

## 0. Pick where it runs

| Option | Cost | Uptime | Effort |
|---|---|---|---|
| **A. Oracle Cloud Always Free VM** (recommended) | $0 forever | 24/7, independent of your PC | ~1 hr one-time setup |
| **B. Your own PC/mini-PC** | $0 | Only if the machine is on and awake at 7 AM IST | ~10 min setup |

If you already have a machine that's always on (NAS, Raspberry Pi, home
server), skip straight to **Section 5** and use Option B instead of
provisioning a VM.

This guide covers **Option A** end-to-end, since that's the only way to
guarantee it runs even if your laptop is closed.

---

## 1. Provision the free VM

1. Sign up at https://signup.oraclecloud.com (needs a card for identity
   verification only — you will not be charged while inside Always Free
   limits).
2. Console → **Compute → Instances → Create Instance**.
3. **Image**: Canonical Ubuntu 24.04 (aarch64/ARM build).
4. **Shape**: click "Change shape" → **Ampere (ARM-based)** →
   `VM.Standard.A1.Flex` → set **2 OCPU / 12 GB RAM** (the current Always
   Free allowance as of mid-2026 — if your tenancy still offers 4/24,
   you can use that instead).
5. Under **Add SSH keys**, either paste your public key
   (`~/.ssh/id_rsa.pub`) or let Oracle generate a key pair and download it.
6. Boot volume: leave default (up to 200 GB is free).
7. Click **Create**. If you hit "Out of host capacity," retry a few times
   or try a different Availability Domain — Ampere A1 capacity is popular
   and regionally constrained.
8. Once running, note the **public IP address**.

SSH in:
```bash
ssh -i /path/to/your/key ubuntu@<PUBLIC_IP>
```

Open only what you need in the VM's firewall (Console → Networking →
Virtual Cloud Network → your subnet → Security Lists) — this app makes
outbound calls only, so you don't need to open any inbound ports besides
SSH (22).

---

## 2. Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y python3-pip python3-venv ffmpeg git unzip

# Set the server's clock to IST so cron times are simple and unambiguous
sudo timedatectl set-timezone Asia/Kolkata
timedatectl   # confirm it now shows Asia/Kolkata
```

---

## 3. Install Ollama and pull the model

```bash
curl -fsSL https://ollama.com/install.sh | sh

# The installer sets Ollama up as a systemd service that starts on boot —
# verify it's running:
sudo systemctl status ollama

ollama pull llama3.2
```

With 12 GB RAM, `llama3.2` (3B) runs comfortably. Don't jump to a 7B+
model on the 2 OCPU/12 GB tier — it'll be noticeably slower and can OOM
alongside MoviePy's rendering step.

---

## 4. Get the project onto the server

From your local machine (where the zip already is):
```bash
scp -i /path/to/your/key ai-youtube-shorts-generator.zip ubuntu@<PUBLIC_IP>:~/
```

On the server:
```bash
unzip ai-youtube-shorts-generator.zip -d ai-youtube-shorts
cd ai-youtube-shorts

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` from the template and fill in your keys:
```bash
cp .env.example .env
nano .env
```
Set `PEXELS_API_KEY` (required), `PIXABAY_API_KEY` (optional), and leave
`OLLAMA_URL`/`MODEL_NAME` as defaults unless you changed them.

---

## 5. YouTube auth — do the login step locally, not on the server

The server has no browser, and `run_local_server()` needs one for the
*first* login. So do that one-time step on your own computer, then copy
the resulting token over:

**On your local machine:**
1. Get `client_secret.json` from Google Cloud Console (APIs & Services →
   Credentials → OAuth client ID → Desktop app), put it in
   `credentials/client_secret.json` in your local copy of the project.
2. Run:
   ```bash
   python setup_youtube_auth.py
   ```
   This opens a browser, you log in and grant access, and it writes
   `credentials/token.json`.

**Copy both files to the server:**
```bash
scp -i /path/to/your/key credentials/client_secret.json credentials/token.json \
    ubuntu@<PUBLIC_IP>:~/ai-youtube-shorts/credentials/
```

From then on, `youtube_agent.py`'s `get_credentials()` reads the cached
token and silently refreshes it — no browser needed on the server, ever.
Refresh tokens don't expire from inactivity as long as the app isn't in
Google's "unverified/testing" mode for more than 7 days per user, so if
your OAuth consent screen is still in **Testing** status, either publish
the app or make sure to re-run the local auth step if you see
`invalid_grant` errors after a week.

---

## 6. Do a full dry run before scheduling anything

```bash
cd ~/ai-youtube-shorts
source venv/bin/activate
python main.py --no-upload
```

Check `output/videos/final_video.mp4` looks right (scp it back to your
machine to preview, or use `ffprobe` on the server to sanity-check
duration/codec). Once that's good, run it once for real to confirm the
headless YouTube upload works:
```bash
python main.py
```

---

## 7. Wrap it in a script with logging

```bash
mkdir -p ~/ai-youtube-shorts/logs
nano ~/ai-youtube-shorts/run.sh
```

```bash
#!/bin/bash
cd /home/ubuntu/ai-youtube-shorts
source venv/bin/activate
python main.py >> logs/cron.log 2>&1
echo "---- run finished: $(date) ----" >> logs/cron.log
```

```bash
chmod +x ~/ai-youtube-shorts/run.sh
```

---

## 8. Schedule it for 7:00 AM IST

Since the server's timezone is already set to `Asia/Kolkata` (Section 2),
a plain cron time of 7:00 means 7:00 IST — no UTC math needed.

```bash
crontab -e
```
Add:
```
0 7 * * * /home/ubuntu/ai-youtube-shorts/run.sh
```

Save and confirm it's registered:
```bash
crontab -l
```

---

## 9. Monitor it

- Check `~/ai-youtube-shorts/logs/cron.log` after 7 AM to confirm success.
- Optional free failure alerting: sign up at https://healthchecks.io
  (free tier), get a ping URL, and add this as the last line of
  `run.sh`:
  ```bash
  curl -fsS -m 10 --retry 3 https://hc-ping.com/<your-check-id> || true
  ```
  Configure the check to expect a daily ping around 7:10 AM IST — if it
  doesn't arrive, Healthchecks emails you.

---

## Notes and gotchas

- **First run is the riskiest.** Whisper (`faster-whisper`) downloads its
  model on first use — make sure `python main.py --no-upload` has been
  run manually at least once so that download isn't happening for the
  first time during an unattended 7 AM job.
- **YouTube API daily quota** is 10,000 units; one upload costs ~1,600,
  so one video/day is nowhere close to the limit.
- **Oracle idle reclaim**: Oracle can reclaim Always Free instances that
  sit idle for a long stretch. A daily cron job generating real CPU/network
  activity works in your favor here — it keeps the instance clearly "in use."
- **Costs stay at $0** as long as you don't exceed the Always Free
  Ampere allowance (2 OCPU/12 GB as of mid-2026) or the 200 GB storage /
  10 TB egress caps — a single daily Short is nowhere near those limits.
