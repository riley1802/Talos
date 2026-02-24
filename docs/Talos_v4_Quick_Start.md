# Talos v4.0 - Quick Start Guide

**Get up and running in 10 minutes**

---

## Prerequisites Checklist

- [ ] Linux Mint 21+ (or Ubuntu 22.04+)
- [ ] 8GB+ RAM (16GB recommended)
- [ ] 50GB+ free disk space (SSD recommended)
- [ ] NVIDIA GPU with 6GB+ VRAM (optional but recommended)
- [ ] Docker 20.10+ installed
- [ ] Internet connection (for initial setup)

---

## 5-Minute Setup

### Step 1: Install Docker

```bash
# Update system
sudo apt update

# Install Docker
sudo apt install -y docker.io docker-compose

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
```

### Step 2: Create Directory Structure

```bash
# One-liner setup
mkdir -p ~/talos/{skills/{quarantine,active,deprecated},keys,logs/{tier1,tier2,tier3},data/{redis,chromadb},config,backups,tmp}

# Set permissions
chmod 700 ~/talos/keys
chmod 750 ~/talos/skills/quarantine
chmod 1777 ~/talos/tmp
```

### Step 3: Get Gemini API Key

1. Go to: https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key (starts with `AIza...`)

### Step 4: Create Environment File

```bash
cat > ~/talos/config/talos.env << 'EOF'
# REQUIRED: Gemini API Key
GEMINI_API_KEY=your_api_key_here

# Web interface password (16+ characters)
BASIC_AUTH_PASS=YourSecurePassword123!

# Everything else uses defaults
EOF

chmod 600 ~/talos/config/talos.env
```

### Step 5: Create Docker Compose

```bash
cat > ~/talos/docker-compose.yml << 'EOF'
version: '3.8'

services:
  talos:
    image: talos/v4:latest
    container_name: talos-orchestrator
    restart: unless-stopped
    env_file:
      - ./config/talos.env
    volumes:
      - ~/talos/skills:/talos/skills
      - ~/talos/keys:/talos/keys:ro
      - ~/talos/logs:/talos/logs
      - ~/talos/data:/talos/data
      - ~/talos/config:/talos/config:ro
      - ~/talos/backups:/talos/backups
    ports:
      - "127.0.0.1:8080:8080"
      - "127.0.0.1:8081:8081"
    networks:
      - talos-network
    depends_on:
      - redis
      - chromadb

  redis:
    image: redis:7-alpine
    container_name: talos-redis
    restart: unless-stopped
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - ~/talos/data/redis:/data
    networks:
      - talos-network

  chromadb:
    image: chromadb/chroma:latest
    container_name: talos-chromadb
    restart: unless-stopped
    volumes:
      - ~/talos/data/chromadb:/chroma/chroma
    networks:
      - talos-network

networks:
  talos-network:
    driver: bridge
EOF
```

### Step 6: Start Talos

```bash
cd ~/talos

# Start services
docker-compose up -d

# Wait 30 seconds for initialization
sleep 30

# Check if healthy
curl -s http://localhost:8081/health | jq .
```

Expected output:
```json
{
  "status": "healthy",
  "checks": {
    "redis": {"status": "ok"},
    "chromadb": {"status": "ok"}
  }
}
```

### Step 7: Access Dashboard

```bash
# Open in browser
firefox http://localhost:8080

# Or via SSH tunnel (if remote)
ssh -L 8080:localhost:8080 user@your-server
```

**Login:**
- Username: `admin`
- Password: (what you set in BASIC_AUTH_PASS)

---

## First 5 Minutes with Talos

### 1. Test Basic Chat

```
You: Hello Talos!
Talos: Hello! I'm Talos, your autonomous AI assistant. How can I help you today?
```

### 2. Test Memory

```
You: My name is Alice
Talos: Nice to meet you, Alice!

You: What's my name?
Talos: Your name is Alice.
```

### 3. Test Skill Creation

```
You: Create a skill that calculates factorial
Talos: I'll create a "factorial" skill for you.

[Generates code...]
[Runs 3 test cases...]

The skill has passed testing and is ready for promotion.
TTS CODE: 4729
Please enter this code in the dashboard to approve.
```

### 4. Approve Skill

1. Go to Dashboard → Skills → Quarantine
2. Find "factorial" skill
3. Click "Review"
4. Enter TTS code: `4729`
5. Click "Approve"

### 5. Use New Skill

```
You: Calculate factorial of 10
Talos: [Uses factorial skill]
     → 10! = 3,628,800
```

---

## Common Tasks

### View Logs

```bash
# All logs
docker-compose logs -f talos

# Just errors
docker-compose logs talos | grep ERROR

# Search for specific skill
docker-compose logs talos | grep "web_scraper"
```

### Backup Data

```bash
# Create backup
cd ~/talos
tar -czf backup_$(date +%Y%m%d).tar.gz data/ config/ skills/active/

# Copy to external drive
cp backup_*.tar.gz /mnt/external-drive/
```

### Update Talos

```bash
cd ~/talos
docker-compose pull
docker-compose up -d
```

### Reset Password

```bash
# Edit environment file
nano ~/talos/config/talos.env

# Change BASIC_AUTH_PASS
# Save and restart
docker-compose restart talos
```

---

## Troubleshooting Quick Fixes

### "Connection refused" on port 8080

```bash
# Check if running
docker-compose ps

# If not running, start it
docker-compose up -d

# Check logs for errors
docker-compose logs talos | tail -50
```

### "Redis connection failed"

```bash
# Restart Redis
docker-compose restart redis

# Wait 10 seconds
sleep 10

# Test
redis-cli ping
# Should return: PONG
```

### "Out of memory" errors

```bash
# Check memory
docker stats --no-stream

# Clear Redis cache
docker-compose exec redis redis-cli FLUSHDB

# Restart
docker-compose restart talos
```

### Forgot password

```bash
# Reset to default
nano ~/talos/config/talos.env
# Change: BASIC_AUTH_PASS=NewPassword123!

# Restart
docker-compose restart talos
```

---

## Next Steps

### 1. Read the Full User Guide

See: `Talos_v4_Complete_User_Guide.md`

### 2. Explore Skills

- Browse quarantined skills in Dashboard
- Approve useful ones
- Try creating your own

### 3. Configure Telegram/Discord

Add to `talos.env`:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
```

### 4. Set Up Backups

Add cron job:
```bash
# Daily backup at 2 AM
echo "0 2 * * * cd ~/talos && tar -czf backups/backup_$(date +\%Y\%m\%d).tar.gz data/ config/" | crontab -
```

### 5. Join Community

- GitHub: github.com/talos-ai/talos
- Discord: discord.gg/talos
- Docs: docs.talos.ai

---

## Quick Command Reference

| Command | Purpose |
|---------|---------|
| `docker-compose up -d` | Start Talos |
| `docker-compose down` | Stop Talos |
| `docker-compose logs -f talos` | View live logs |
| `docker-compose restart talos` | Restart Talos |
| `docker-compose pull` | Update images |
| `curl http://localhost:8081/health` | Check health |
| `redis-cli ping` | Test Redis |
| `nvidia-smi` | Check GPU |

---

**You're all set!** 🎉

Talos is now running and ready to help you.

Need help? Check the full User Guide or visit our community forums.

---

*Quick Start Version 1.0 - February 2026*
