# Deploying IntelliDigest — 100% Free (Oracle Cloud)

This guide walks you through deploying IntelliDigest to **Oracle Cloud's Always Free Tier** with a custom domain and HTTPS. Total cost: **$0/month, forever**.

## What you get

| Resource | Always Free Allowance |
|---|---|
| **Compute** | ARM VM — up to 4 OCPUs, 24 GB RAM |
| **Boot volume** | 200 GB (persistent — survives reboots) |
| **Egress** | 10 TB/month |
| **Public IP** | 1 reserved (static) |

This is more than enough to run IntelliDigest + n8n in Docker with room to spare.

---

## Prerequisites

- A GitHub account (to clone the repo on the server)
- An Oracle Cloud account (credit card for identity verification only — you will **not** be charged)

---

## Step 1 — Create an Oracle Cloud Account

1. Go to [cloud.oracle.com/registration](https://cloud.oracle.com/registration)
2. Fill in your details and verify your email
3. Add a credit/debit card (identity verification only — **Always Free resources are never billed**)
4. Select a **Home Region** closest to your users (e.g. `eu-frankfurt-1`, `us-ashburn-1`)

> **Important:** Your Home Region cannot be changed later. Choose wisely — it determines latency for your users.

---

## Step 2 — Create an ARM VM Instance

1. Go to **Compute → Instances → Create Instance**
2. Configure:
   - **Name:** `intellidigest`
   - **Image:** Ubuntu 22.04 (or 24.04) — _Canonical_ official image
   - **Shape:** Click **Change Shape** → **Ampere** → `VM.Standard.A1.Flex`
     - **OCPUs:** 2 (save the other 2 for future use, or use all 4)
     - **Memory:** 12 GB (or up to 24 GB)
   - **Networking:** Create a new VCN or use default. Ensure **Assign a public IPv4 address** is checked
   - **SSH Keys:** Upload your public key (`~/.ssh/id_rsa.pub`) or let Oracle generate one (download it immediately!)
3. Click **Create**

Wait 1–2 minutes for the instance to be `RUNNING`.

> **Tip:** If you get a "capacity" error, try a different Availability Domain or wait and retry. ARM instances are popular.

---

## Step 3 — Open Firewall Ports

### 3a. Oracle Security List (cloud-level firewall)

1. Go to **Networking → Virtual Cloud Networks** → click your VCN → **Security Lists** → **Default Security List**
2. Click **Add Ingress Rules** and add these:

| Source CIDR | Protocol | Dest Port | Description |
|---|---|---|---|
| `0.0.0.0/0` | TCP | `80` | HTTP |
| `0.0.0.0/0` | TCP | `443` | HTTPS |

### 3b. OS-level firewall (iptables)

SSH into your VM:

```bash
ssh -i ~/.ssh/your_key ubuntu@<YOUR_PUBLIC_IP>
```

Then open ports 80 and 443:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

---

## Step 4 — Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Add your user to docker group (so you don't need sudo)
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Log out and back in for group to take effect
exit
```

SSH back in, then verify:

```bash
docker --version
docker compose version
```

---

## Step 5 — Clone and Configure the Project

```bash
# Clone your repo
git clone https://github.com/YOUR_USERNAME/IntelliDigest.git
cd IntelliDigest

# Create the pip cache directory (required by Dockerfile)
mkdir -p .pip-cache

# Create your .env file
cp .env.example .env
nano .env
```

### Minimum `.env` for production

```env
# Required — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=<paste-a-64-char-hex-string>

# Optional server-side fallback key (users bring their own via BYOK)
GROQ_API_KEY=<your-groq-key-or-leave-blank>

# Optional — only if you want news fetching
NEWSAPI_KEY=<your-newsapi-key>

# Persistent storage (keep DB + vectors across container restarts)
INTELLIDIGEST_PERSIST_DIR=/app/persist

# Production CORS — set to your domain
ALLOWED_ORIGINS=https://yourdomain.duckdns.org
```

---

## Step 6 — Create a Production Docker Compose

Create `docker-compose.prod.yml`:

```bash
nano docker-compose.prod.yml
```

Paste:

```yaml
services:
  intellidigest:
    build:
      context: .
      pull: false
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - TRANSFORMERS_NO_TF=1
      - USE_TF=0
      - INTELLIDIGEST_PERSIST_DIR=/app/persist
    volumes:
      - app_data:/app/persist
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - intellidigest
    restart: unless-stopped

volumes:
  app_data:
  caddy_data:
  caddy_config:
```

> **Note:** If you also want n8n, add the n8n service from `docker-compose.with-n8n.yml` into this file and expose port `5678` through Caddy as well.

---

## Step 7 — Get a Free Domain (DuckDNS)

1. Go to [duckdns.org](https://www.duckdns.org) and log in with GitHub/Google
2. Create a subdomain, e.g. `intellidigest` → gives you `intellidigest.duckdns.org`
3. Set the IP to your Oracle VM's **public IP address**
4. (Optional) Set up auto-update with a cron job on the VM:

```bash
# Replace YOUR_TOKEN and YOUR_DOMAIN with your DuckDNS values
mkdir -p ~/duckdns
cat > ~/duckdns/duck.sh << 'EOF'
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=YOUR_DOMAIN&token=YOUR_TOKEN&ip=" | curl -k -o ~/duckdns/duck.log -K -
EOF

chmod +x ~/duckdns/duck.sh

# Run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
```

---

## Step 8 — Configure Caddy (HTTPS Reverse Proxy)

Caddy automatically obtains and renews Let's Encrypt certificates for free.

```bash
nano Caddyfile
```

Paste (replace `intellidigest.duckdns.org` with your actual subdomain):

```
intellidigest.duckdns.org {
    reverse_proxy intellidigest:8000
}
```

That's it. Caddy handles:
- ✅ Auto HTTPS via Let's Encrypt
- ✅ HTTP → HTTPS redirect
- ✅ Certificate renewal

---

## Step 9 — Build and Launch

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes ~5–10 minutes (downloading Python deps + sentence-transformers model). Subsequent starts are fast.

### Check logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Just IntelliDigest
docker compose -f docker-compose.prod.yml logs -f intellidigest

# Just Caddy
docker compose -f docker-compose.prod.yml logs -f caddy
```

---

## Step 10 — Verify

1. Open `https://intellidigest.duckdns.org` in your browser
2. You should see the login page with a valid HTTPS certificate 🔒
3. Register an account, set up your LLM API key, and start chatting!

---

## Updating the App

When you push changes to the repo:

```bash
cd ~/IntelliDigest
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Your data (SQLite DB, ChromaDB vectors) lives in Docker volumes and survives rebuilds.

---

## Adding n8n (Optional)

If you want Telegram integration via n8n on the same server, add this to `docker-compose.prod.yml` under `services:`:

```yaml
  n8n:
    image: n8nio/n8n:latest
    environment:
      - N8N_HOST=0.0.0.0
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - WEBHOOK_URL=https://n8n.intellidigest.duckdns.org/
      - N8N_SECURE_COOKIE=true
    volumes:
      - n8n_data:/home/node/.n8n
    restart: unless-stopped
```

Add `n8n_data:` under `volumes:`, and add a second block to your `Caddyfile`:

```
n8n.intellidigest.duckdns.org {
    reverse_proxy n8n:5678
}
```

Register a second DuckDNS subdomain (`n8n-intellidigest`) pointed at the same IP, or use `n8n.intellidigest.duckdns.org` if DuckDNS allows nested subdomains (it doesn't — use a separate subdomain like `intellidigestn8n.duckdns.org`).

---

## Troubleshooting

### "Out of capacity" when creating the VM

ARM instances are popular. Solutions:
- Try a different **Availability Domain** (AD-2, AD-3)
- Try a different region (you can create a second free account in another region)
- Use the [OCI Instance Availability Checker](https://github.com/hitrov/oci-arm-host-capacity) script to auto-retry

### Caddy shows "certificate error"

- Make sure your DuckDNS subdomain points to the correct public IP
- Ensure ports 80 and 443 are open (both Security List and iptables)
- Check Caddy logs: `docker compose -f docker-compose.prod.yml logs caddy`

### App crashes or 503 errors

- Check logs: `docker compose -f docker-compose.prod.yml logs intellidigest`
- Ensure `.env` has `JWT_SECRET` set
- If memory is tight, reduce the VM to 1 OCPU / 6 GB (sentence-transformers needs ~2 GB at peak)

### Docker build fails on ARM

The Dockerfile uses `python:3.13-slim` which has official ARM64 images. If a pip package lacks ARM wheels, add build tools:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ cmake && \
    rm -rf /var/lib/apt/lists/*
```

---

## Architecture on Oracle Cloud

```
┌─────────────────────────────────────────────────┐
│                Oracle Cloud VM                   │
│              (ARM, 2 OCPU, 12 GB)                │
│                                                   │
│   ┌──────────┐    ┌──────────────────────────┐   │
│   │  Caddy   │───▶│   IntelliDigest (8000)   │   │
│   │  :80/443 │    │   FastAPI + LangChain     │   │
│   └──────────┘    │   SQLite + ChromaDB       │   │
│                    └──────────────────────────┘   │
│                                                   │
│   ┌──────────────────────────┐  (optional)       │
│   │       n8n (5678)         │                    │
│   │   Telegram workflows     │                    │
│   └──────────────────────────┘                   │
│                                                   │
│   Docker volumes:                                 │
│   • app_data   → /app/persist (SQLite + Chroma)  │
│   • caddy_data → TLS certificates                │
│   • n8n_data   → n8n workflows                   │
└─────────────────────────────────────────────────┘
         │
         ▼
   intellidigest.duckdns.org
   (DuckDNS free subdomain → Public IP)
```

---

## Summary

| Component | Service | Cost |
|---|---|---|
| Server | Oracle Cloud Always Free (ARM) | **Free** |
| Domain | DuckDNS subdomain | **Free** |
| HTTPS | Caddy + Let's Encrypt | **Free** |
| LLM API | User's own key (BYOK) | **Free for you** |
| Docker | Self-hosted on the VM | **Free** |
| **Total** | | **$0/month** |
