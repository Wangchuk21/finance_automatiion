# Finance Automation — Production Deployment Guide

This guide covers deploying the Finance Automation system on a Bhutan Telecom production server using Docker Compose.

---

## Architecture

```
User (Browser)
    │
    ▼
┌────────────────────────────────────────────────────────┐
│  Port 80 (HTTP) or Port 443 (HTTPS)                    │
│                                                        │
│  ┌───────────────────┐        ┌──────────────────────┐ │
│  │     Frontend      │        │       Backend        │ │
│  │   Nginx + React   │───────▶│    FastAPI + Python  │ │
│  │    (Port 3000)    │  /api  │     (Port 8000)      │ │
│  └───────────────────┘        └──────────────────────┘ │
│                                          │             │
│                                          ▼             │
│                               ┌──────────────────────┐ │
│                               │      PostgreSQL      │ │
│                               │     (Port 5432)      │ │
│                               └──────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

---

## Server Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 LTS / Debian 12 | Ubuntu 22.04+ |
| CPU | 2 Cores | 4 Cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB SSD | 50 GB SSD |
| Docker | Docker 24+ & Docker Compose v2+ | Latest |

---

## Quick Start (Deploy in 5 Steps)

### Step 1: On your server, clone the repo

```bash
git clone <repo-url> /opt/finance-automation
cd /opt/finance-automation
```

Or if you already have it:
```bash
cd /opt/finance-automation
git pull
```

### Step 2: Create the production environment file

```bash
cp .env.prod.example .env.prod
nano .env.prod   # or vim
```

Fill in the required fields:
- `SECRET_KEY`: Generate with `openssl rand -base64 32`
- `ANONYMIZATION_SALT`: Generate with `openssl rand -base64 32`
- `TEMP_CONFIRM_CODE`: Strong confirmation code (e.g. `839201`)
- `POSTGRES_PASSWORD`: Strong database password
- `DOMAIN`: Your server IP or domain (e.g. `10.x.x.x` or `finance.bt.bt`)

### Step 3: Run the deploy script

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Validate all required environment variables
2. Build the backend and frontend Docker images
3. Start PostgreSQL, wait for it to be healthy
4. Run Alembic database migrations automatically
5. Start the backend (4 Uvicorn workers) and frontend
6. Restart the TLS reverse proxy (if `docker-compose.tls.yml` is present) so nginx re-resolves the new container IPs
7. Verify service health

> **TLS proxy:** the public HTTPS proxy lives in `docker-compose.tls.yml`, which is server-side only.
> `deploy.sh` includes it automatically when the file exists. Keep that file in the repo (it holds no
> secrets, only config/cert paths) so the proxy is never left out of a deploy.

### Step 4: Verify the deployment

```bash
# Check running containers
docker compose -f docker-compose.prod.yml ps

# Check backend health
curl http://localhost:8000/health

# Check frontend
curl -I http://localhost:3000/
```

Access the application in your browser at:
- **Frontend**: `http://<your-server-ip>:3000`
- **Backend API**: `http://<your-server-ip>:8000`
- **API Health**: `http://<your-server-ip>:8000/health`

---

## Daily Operations & Commands

### View Logs

```bash
# All logs (follow mode)
docker compose -f docker-compose.prod.yml logs -f

# Backend only
docker compose -f docker-compose.prod.yml logs -f backend

# Database only
docker compose -f docker-compose.prod.yml logs -f postgres
```

### Restart Services

```bash
# Restart everything
docker compose -f docker-compose.prod.yml restart

# Restart only backend
docker compose -f docker-compose.prod.yml restart backend
```

### Update Application (After Git Pull)

```bash
git pull
./deploy.sh
```

### Stop Application

```bash
docker compose -f docker-compose.prod.yml down
```

---

## Database Backups

### Run a Manual Backup

```bash
chmod +x backup.sh
./backup.sh
```

Backups are saved to `/opt/finance-automation/backups/` as compressed `.sql.gz` files. Old backups (>30 days) are automatically deleted.

### Setup Daily Automatic Backups (Cron)

```bash
crontab -e
```

Add this line to run a backup every night at 2:00 AM:
```cron
0 2 * * * /opt/finance-automation/backup.sh >> /var/log/finance-backup.log 2>&1
```

### Restore from Backup

```bash
gunzip -c /opt/finance-automation/backups/finance_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i finance-db-prod psql -U finance -d finance
```

---

## Auto-Start on System Boot (Systemd)

To make the application start automatically when the server reboots:

```bash
sudo cp finance-automation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable finance-automation
sudo systemctl start finance-automation
```

To manage the service:
```bash
sudo systemctl status finance-automation
sudo systemctl restart finance-automation
sudo systemctl stop finance-automation
```

---

## Production Security Checklist

- [ ] `SECRET_KEY` generated randomly (`openssl rand -base64 32`)
- [ ] `ANONYMIZATION_SALT` generated randomly
- [ ] `POSTGRES_PASSWORD` is strong (16+ chars)
- [ ] `TEMP_CONFIRM_CODE` set to a strong value
- [ ] `DEBUG=false` in `.env.prod`
- [ ] `.env.prod` file permissions set to `chmod 600 .env.prod`
- [ ] Automated backups enabled via cron
- [ ] Systemd auto-start enabled
- [ ] Port 5432 (PostgreSQL) is NOT exposed to the public internet (bound to 127.0.0.1)

---

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| `Required variable ... not set` | Missing values in `.env.prod` | Edit `.env.prod` and ensure no values say `CHANGE_ME` |
| Database connection failed | PostgreSQL not ready yet | Check `docker compose -f docker-compose.prod.yml logs postgres` |
| 502 Bad Gateway | Backend is starting/crashed, or the proxy cached an old container IP after a redeploy | Check `docker compose -f docker-compose.prod.yml logs backend`; if the app answers on `localhost:8000`, restart the proxy: `docker restart finance-proxy-prod` (or rerun `./deploy.sh`) |
| Migration failed | Schema mismatch | Run `docker compose -f docker-compose.prod.yml exec backend alembic current` |
| Upload fails with 413 | File too large (>50MB) | Adjust `MAX_UPLOAD_SIZE_MB` in `.env.prod` and `client_max_body_size` in nginx config |
