# Talos v4.0 (Ironclad)

**Autonomous, Self-Improving AI Agent for Local Sovereignty**

---

## Overview

Talos is a **local-first, autonomous AI agent** that runs entirely on your infrastructure. Unlike cloud-based AI assistants, Talos:

- **Keeps your data local** — nothing leaves your machine except optional Gemini API calls
- **Self-improves** — creates and tests new skills automatically
- **Security-hardened** — quarantine system, 3-strike deprecation, prompt injection firewall
- **Resource-bounded** — hard limits prevent runaway resource usage
- **FOSS** — 100% Free and Open Source (MIT)

---

## System Requirements

### Minimum

| Component | Requirement |
|-----------|-------------|
| OS        | Linux Mint 21+ / Ubuntu 22.04+ |
| RAM       | 8 GB |
| Disk      | 50 GB SSD |
| GPU       | NVIDIA GTX 1060 6GB *(optional — falls back to CPU)* |
| Docker    | 20.10+ with Docker Compose v2 |

### Recommended

| Component | Requirement |
|-----------|-------------|
| RAM       | 16 GB |
| Disk      | 100 GB NVMe |
| GPU       | NVIDIA RTX 3060 12GB |
| Docker    | 24.0+ |

---

## Setup

### 1. Install Prerequisites

```bash
# Docker & Compose
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
newgrp docker

# NVIDIA Container Toolkit (only if you have an NVIDIA GPU)
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
```

### 2. Clone the Repository

```bash
git clone <your-repo-url> ~/Documents/talos
cd ~/Documents/talos
```

### 3. Create Host Directories

The genesis script creates the required directory tree at `~/talos/` with correct permissions:

```bash
bash scripts/genesis.sh
```

This creates:

```
~/talos/
├── skills/
│   ├── quarantine/   # chmod 750 — untrusted skills
│   ├── active/       # chmod 755 — approved skills
│   └── deprecated/   # chmod 750 — retired skills
├── keys/             # chmod 700 — secrets
├── logs/
│   ├── tier1/        # Audit (indefinite retention)
│   ├── tier2/        # Ops (30-day retention)
│   └── tier3/        # Debug (7-day retention)
├── data/
│   ├── redis/        # chmod 700
│   └── chromadb/     # chmod 700
├── config/
├── backups/
└── tmp/
```

### 4. Configure Environment

Copy the template and set your secrets:

```bash
cp talos.env ~/talos/config/talos.env
chmod 600 ~/talos/config/talos.env
```

Edit `~/talos/config/talos.env` and set the two **required** values:

```bash
GEMINI_API_KEY=<your key from https://makersuite.google.com/app/apikey>
BASIC_AUTH_PASS=<at least 16 characters>
```

### 5. GPU Configuration (Optional)

If you **don't** have an NVIDIA GPU, comment out the GPU section in `docker-compose.yml`:

```yaml
  ollama:
    # ...
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]
```

Ollama will fall back to CPU-only inference.

### 6. Start Talos

```bash
docker compose up -d
```

Wait for all 5 containers to become healthy:

```bash
docker compose ps
```

Expected output:

```
NAME                STATUS
talos-orchestrator  Up (healthy)
talos-redis         Up (healthy)
talos-chromadb      Up (healthy)
talos-ollama        Up (healthy)
talos-socket-proxy  Up (healthy)
```

### 7. Open the Dashboard

```
http://localhost:8080
```

Log in with username `admin` and the `BASIC_AUTH_PASS` you set.

On first boot, Ollama will pull the Qwen models in the background (~4-9 GB each). Check progress with:

```bash
docker compose logs -f talos 2>&1 | grep -i "pull\|model"
```

---

## Configuration Reference

All configuration lives in `~/talos/config/talos.env`.

### Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `BASIC_AUTH_PASS` | Dashboard password (16+ characters) |

### Optional (defaults shown)

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUST_LEVEL` | `0` | Skill trust level (0-5) |
| `REDIS_MAX_MEMORY` | `512mb` | Redis memory ceiling |
| `CHROMADB_MAX_VECTORS` | `100000` | Max vectors in ChromaDB |
| `VRAM_MUTEX_TIMEOUT` | `300` | GPU lock timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Python log level |
| `GEMINI_MAX_TOKENS_PER_DAY` | `50000` | Daily Gemini token soft limit |
| `DASHBOARD_AUTO_OPEN` | `true` | Auto-open browser on boot |
| `DREAM_CYCLE_HOUR` | `4` | Dream maintenance hour (24h) |
| `TELEGRAM_BOT_TOKEN` | *(empty)* | Set to enable Telegram bot |
| `DISCORD_BOT_TOKEN` | *(empty)* | Set to enable Discord bot |
| `STRIKE_THRESHOLD` | `3` | Failures before skill deprecation |

---

## Architecture

### Services (docker-compose.yml)

| Service | Image | Purpose |
|---------|-------|---------|
| `talos` | `talos/v4:latest` | Python 3.11 FastAPI backend, tini as PID 1 |
| `redis` | `redis:7-alpine` | Short-term memory (512MB LRU, AOF persistence) |
| `chromadb` | `chromadb/chroma:latest` | Long-term vector memory (100K vectors max) |
| `ollama` | `ollama/ollama:latest` | Local LLM server (Qwen Coder 7B + Qwen VL) |
| `socket-proxy` | `tecnativa/docker-socket-proxy` | Restricted Docker API access |

### Backend Modules

```
backend/
├── main.py                  # FastAPI app, routes, lifespan startup
├── orchestrator/
│   ├── loop.py              # Message pipeline: firewall → RAG → route → store
│   └── watchdog.py          # 30-second event loop block detector
├── memory/
│   ├── redis_client.py      # Async Redis connection pool
│   ├── chroma_client.py     # 4 collections, cosine distance, auto-prune at 90K
│   └── rag.py               # Embed → retrieve → score → inject context
├── intelligence/
│   ├── vram_mutex.py        # Exclusive GPU access state machine
│   ├── ollama_client.py     # Qwen Coder 7B + Qwen VL
│   ├── gemini_client.py     # Circuit breaker (CLOSED→OPEN→HALF_OPEN), daily token limit
│   └── router.py            # Local-first routing with Gemini fallback
├── skills/
│   ├── firewall.py          # 4-layer prompt injection detection
│   ├── quarantine.py        # Skill validation state machine
│   ├── strike_system.py     # 3-strike auto-deprecation
│   └── registry.py          # Skill metadata CRUD
├── security/
│   ├── audit_log.py         # Tier-1 append-only JSON-L
│   └── tts_codes.py         # 4-digit verification codes (5-min TTL)
├── maintenance/
│   ├── dream_cycle.py       # 4 AM daily maintenance (5 phases, 30-min cap)
│   └── health.py            # System metrics collection
└── comms/
    ├── websocket.py         # Live log streaming to dashboard
    ├── telegram_bot.py      # Telegram message handler
    └── discord_bot.py       # Discord message handler
```

### Message Flow

```
User input
  → Prompt Injection Firewall (L1-L4 scan)
  → Lockdown check (Redis)
  → RAG context retrieval (ChromaDB)
  → Model routing (Qwen local → Gemini fallback)
  → Response stored in conversation_history
  → Response returned to user
```

---

## API Endpoints

All endpoints (except `/health`) require HTTP Basic Auth.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status (no auth required) |
| `GET` | `/metrics` | VRAM state, token counts, system stats |
| `POST` | `/chat` | Send message `{"message": "..."}` |
| `GET` | `/skills?state=active` | List skills by state |
| `POST` | `/skills/{id}/tts-request` | Request TTS promotion code |
| `POST` | `/skills/{id}/promote` | Promote skill `{"tts_code": "1234"}` |
| `DELETE` | `/skills/{id}` | Deprecate a skill |
| `POST` | `/admin/dream-cycle` | Manually trigger maintenance |
| `POST` | `/panic` | Emergency lockdown |
| `POST` | `/panic/unlock` | Unlock from lockdown |
| `WS` | `/ws/logs` | Live log stream (backfills 50 lines) |

---

## Daily Operations

### Backup

```bash
bash scripts/backup.sh
```

Creates `~/talos/backups/backup_YYYYMMDD_HHMMSS.tar.gz` containing Redis data, ChromaDB data, active skills, config, and Tier-1 audit logs. Old backups are pruned after 30 days.

### Restore

```bash
bash scripts/restore.sh ~/talos/backups/backup_20260224_120000.tar.gz
```

Verifies the SHA-256 checksum, creates a safety backup of current state, extracts the archive, then prints instructions to restart.

### Dream Cycle (Automatic)

Runs at 4:00 AM daily. Five phases in 30 minutes max:

1. Redis expired key flush
2. ChromaDB vector pruning (temporary vectors older than 30 days)
3. Log compression (gzip Tier-2/3 files > 10MB)
4. Zombie process cleanup
5. Health report (stored in Redis)

Trigger manually: `POST /admin/dream-cycle`

---

## Security

### Layers

| Layer | Mechanism | Details |
|-------|-----------|---------|
| L1 | Prompt Injection Firewall | Regex patterns, base64 decode + re-scan, character ratio check, length limit (10K chars) |
| L2 | Skill Quarantine | New skills need 3 clean sandbox runs + TTS code to promote |
| L3 | 3-Strike System | 3 execution failures auto-deprecate a skill |
| L4 | Basic Auth + TTS Codes | Dashboard auth + 4-digit time-limited codes for critical actions |
| L5 | Socket Proxy | Docker API allowlist (containers start/stop/create only) |
| L6 | Audit Log | Tier-1 append-only JSON-L — never rotated or deleted |

### Emergency Stop

```bash
# Via API
curl -u admin:YOURPASS -X POST http://localhost:8080/panic -d '{"tts_code":"0000"}'

# Via Docker (hard kill)
docker compose kill talos
docker compose up -d talos
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Containers not starting | `docker compose logs <service>` to check errors |
| Redis connection refused | `docker compose restart redis` — wait for healthcheck |
| ChromaDB slow to start | Normal on first boot — allow 30s. Check: `docker compose logs chromadb` |
| Ollama model pull stuck | `docker compose exec ollama ollama list` to check progress |
| GPU not detected | Verify `nvidia-smi` works on host, check NVIDIA Container Toolkit |
| Dashboard 401 | Verify `BASIC_AUTH_PASS` in `~/talos/config/talos.env` matches what you enter |
| Forgot password | Edit `~/talos/config/talos.env`, then `docker compose restart talos` |
| VRAM stuck in LOADING | Check `docker compose logs talos` for mutex timeout — Ollama may need restart |
| System lockdown active | Use `POST /panic/unlock` with the unlock code, or restart the talos container |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Quick Start](docs/Talos_v4_Quick_Start.md) | 5-minute setup guide |
| [Complete User Guide](docs/Talos_v4_Complete_User_Guide.md) | Full feature documentation |
| [Master Implementation Spec](docs/Talos_v4_Master_Implementation_Specification.md) | Technical specification |
| [Architecture Diagrams](docs/Talos_v4_Architecture_Diagrams.md) | Visual architecture reference |
| [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md) | Build progress tracking |
| [Documentation Index](docs/DOCUMENTATION_INDEX.md) | Navigation guide |

---

## License

MIT License
