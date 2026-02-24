# Talos v4.0 (Ironclad) - Complete User Guide

**Your Autonomous, Self-Improving AI Agent**

---

## Table of Contents

1. [Introduction](#introduction)
2. [System Architecture](#system-architecture)
3. [Installation & Setup](#installation--setup)
4. [Configuration Guide](#configuration-guide)
5. [Using Talos](#using-talos)
6. [Skill System](#skill-system)
7. [Memory & Context](#memory--context)
8. [Security Features](#security-features)
9. [Maintenance & Monitoring](#maintenance--monitoring)
10. [Troubleshooting](#troubleshooting)
11. [Best Practices](#best-practices)
12. [Advanced Topics](#advanced-topics)
13. [API Reference](#api-reference)
14. [FAQ](#faq)

---

## Introduction

### What is Talos?

Talos is an **autonomous, containerized AI agent** designed for **local sovereignty** and **recursive self-improvement**. Unlike cloud-centric AI systems, Talos operates entirely on your own infrastructure (Linux Mint), giving you complete control over your data and AI capabilities.

### Key Features

| Feature | Description |
|---------|-------------|
| 🏠 **Local-First** | All data stays on your machine. No cloud dependencies. |
| 🧠 **Self-Improving** | Creates new skills through code generation and testing |
| 🔒 **Security-Hardened** | Quarantine system, 3-strike deprecation, prompt injection firewall |
| ⚡ **Resource-Bounded** | Hard limits on memory, disk, and GPU usage |
| 🔄 **Auto-Maintenance** | Daily "dream" cycle prunes old data and optimizes performance |
| 🌐 **Multi-Channel** | Telegram, WhatsApp, Discord integration |
| 🛡️ **Fail-Safe** | Degrades gracefully under resource pressure |

### Use Cases

- **Personal AI Assistant** - Manage tasks, answer questions, automate workflows
- **Code Generation** - Create and test new tools and scripts
- **Knowledge Management** - Build a personal knowledge base with vector search
- **System Automation** - Control Docker containers, monitor systems
- **Research Assistant** - Web scraping, data analysis, report generation

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TALOS v4.0 ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │   USER LAYER    │    │   USER LAYER    │    │   USER LAYER    │     │
│  │  Web Dashboard  │    │  Telegram Bot   │    │  Discord Bot    │     │
│  │   (Port 8080)   │    │   (Bot API)     │    │   (Bot API)     │     │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘     │
│           │                      │                      │              │
│           └──────────────────────┼──────────────────────┘              │
│                                  │                                      │
│  ┌───────────────────────────────┴───────────────────────────────┐     │
│  │                    ORCHESTRATION LAYER                        │     │
│  │              (Node.js/TypeScript + tini PID 1)                │     │
│  │                                                               │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │     │
│  │  │   Health    │  │   Watchdog  │  │   Process Supervisor│   │     │
│  │  │   Check     │  │  (30s block)│  │    (Zombie Reaper)  │   │     │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │     │
│  └───────────────────────────────┬───────────────────────────────┘     │
│                                  │                                      │
│  ┌───────────────────────────────┴───────────────────────────────┐     │
│  │                  INTELLIGENCE LAYER                           │     │
│  │                     (Python + Shell)                          │     │
│  │                                                               │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │     │
│  │  │  Qwen Coder │  │   Qwen VL   │  │   Gemini Flash      │   │     │
│  │  │   (Logic)   │  │   (Vision)  │  │   (Escalation)      │   │     │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │     │
│  │                                                               │     │
│  │  ┌─────────────────────────────────────────────────────────┐ │     │
│  │  │              VRAM MUTEX (30s timeout)                   │ │     │
│  │  │     Exclusive GPU access for model swapping             │ │     │
│  │  └─────────────────────────────────────────────────────────┘ │     │
│  └───────────────────────────────┬───────────────────────────────┘     │
│                                  │                                      │
│  ┌───────────────────────────────┴───────────────────────────────┐     │
│  │                    MEMORY VAULT (Tiered)                      │     │
│  ├───────────────────────────────────────────────────────────────┤     │
│  │                                                               │     │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │     │
│  │  │  SHORT-TERM     │  │   LONG-TERM     │  │    LOGS      │  │     │
│  │  │    (Redis)      │  │   (ChromaDB)    │  │ (JSON-L)     │  │     │
│  │  │   512MB LRU     │  │  100K vectors   │  │ 50MB ring    │  │     │
│  │  │  Conversation   │  │  Knowledge Base │  │  buffer      │  │     │
│  │  └─────────────────┘  └─────────────────┘  └──────────────┘  │     │
│  │                                                               │     │
│  └───────────────────────────────┬───────────────────────────────┘     │
│                                  │                                      │
│  ┌───────────────────────────────┴───────────────────────────────┐     │
│  │                   SKILL SYSTEM                                │     │
│  ├───────────────────────────────────────────────────────────────┤     │
│  │                                                               │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │     │
│  │  │  QUARANTINE  │→ │    ACTIVE    │  │ DEPRECATED   │        │     │
│  │  │  (Testing)   │  │  (Production)│  │  (Retired)   │        │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │     │
│  │         ↑                                               ↑     │     │
│  │         └──────────── 3-Strike System ──────────────────┘     │     │
│  │                                                               │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │                   SECURITY LAYER                              │     │
│  ├───────────────────────────────────────────────────────────────┤     │
│  │  • Socket Proxy (Restricted Docker API)                       │     │
│  │  • Prompt Injection Firewall                                  │     │
│  │  • TTS Verification (4-digit codes)                           │     │
│  │  • Skill Quarantine (3 successful runs required)              │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Diagram

```
User Request
     │
     ▼
┌─────────────────┐
│  Input Firewall │ ←── Prompt Injection Scan
│   (Sanitizer)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Context Builder│ ←── Retrieve from ChromaDB
│   (RAG System)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLM Router    │ ←── Qwen Coder (default)
│                 │     Gemini Flash (escalation)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Response Parser │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Action Executor │ ←── Skills / Docker / Browser
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Memory Store   │ ←── Save to Redis + ChromaDB
└─────────────────┘
```

### Resource Management Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    RESOURCE MANAGEMENT                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐│
│  │    Redis     │     │   ChromaDB   │     │    Disk      ││
│  │   512MB Max  │     │  100K Vectors│     │   95% Alert  ││
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘│
│         │                    │                    │        │
│         │  LRU Eviction      │  Prune Oldest 10%  │        │
│         │  (Automatic)       │  (At 90% capacity) │        │
│         │                    │                    │        │
│         ▼                    ▼                    ▼        │
│  ┌────────────────────────────────────────────────────────┐│
│  │              4:00 AM "DREAM" CYCLE                     ││
│  │  • Flush Redis cache                                   ││
│  │  • Compact ChromaDB (delete old temporary vectors)    ││
│  │  • Compress logs                                       ││
│  │  • Kill zombie processes (>3 days old)                ││
│  └────────────────────────────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Installation & Setup

### Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | Linux Mint 21+ | Linux Mint 21.2+ |
| RAM | 8 GB | 16 GB |
| Disk | 50 GB SSD | 100 GB NVMe |
| GPU | NVIDIA GTX 1060 6GB | RTX 3060 12GB+ |
| Docker | 20.10+ | 24.0+ |
| Internet | For initial setup | For Gemini API |

### Step 1: System Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y     curl     wget     git     jq     htop     nvtop     docker.io     docker-compose     redis-tools

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker installation
docker --version
docker-compose --version
```

### Step 2: Directory Structure Setup

```bash
# Create Talos directory hierarchy
mkdir -p ~/talos/{skills/{quarantine,active,deprecated},keys,logs/{tier1,tier2,tier3},data/{redis,chromadb},config,backups,tmp}

# Set permissions
chmod 700 ~/talos/keys
chmod 750 ~/talos/skills/quarantine
chmod 750 ~/talos/skills/deprecated
chmod 700 ~/talos/data/redis
chmod 700 ~/talos/data/chromadb
chmod 1777 ~/talos/tmp

# Verify structure
tree ~/talos || find ~/talos -type d
```

### Step 3: Environment Configuration

Create `~/talos/config/talos.env`:

```bash
# Core Identity
TALOS_VERSION=4.0.0
TRUST_LEVEL=0

# Resource Limits
REDIS_MAX_MEMORY=512mb
CHROMADB_MAX_VECTORS=100000
VRAM_MUTEX_TIMEOUT=300

# API Keys (REQUIRED)
GEMINI_API_KEY=your_gemini_api_key_here

# Web Interface
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=admin123
WEB_PORT=8080
WEB_BIND_ADDRESS=127.0.0.1

# Optional: Tailscale VPN
# TAILSCALE_AUTH_KEY=tskey-auth-xxxxxxxxxxxx

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security
STRIKE_THRESHOLD=3
SANDBOX_MEMORY_LIMIT=512m
SANDBOX_PIDS_LIMIT=50
```

Set secure permissions:
```bash
chmod 600 ~/talos/config/talos.env
```

### Step 4: Docker Compose Setup

Create `~/talos/docker-compose.yml`:

```yaml
version: '3.8'

services:
  # Main Talos Orchestrator
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
      - ~/talos/tmp:/talos/tmp
    ports:
      - "127.0.0.1:8080:8080"  # Web Dashboard
      - "127.0.0.1:8081:8081"  # Health Check
      - "127.0.0.1:9090:9090"  # Metrics
    networks:
      - talos-network
    depends_on:
      - redis
      - chromadb
      - socket-proxy
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # Redis - Short-term Memory
  redis:
    image: redis:7-alpine
    container_name: talos-redis
    restart: unless-stopped
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - ~/talos/data/redis:/data
    networks:
      - talos-network

  # ChromaDB - Long-term Memory (Vectors)
  chromadb:
    image: chromadb/chroma:latest
    container_name: talos-chromadb
    restart: unless-stopped
    volumes:
      - ~/talos/data/chromadb:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - PERSIST_DIRECTORY=/chroma/chroma
    networks:
      - talos-network

  # Socket Proxy - Secure Docker Access
  socket-proxy:
    image: tecnativa/docker-socket-proxy:latest
    container_name: talos-socket-proxy
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - CONTAINERS=1  # Allow container operations only
      - IMAGES=0      # Block image operations
      - VOLUMES=0     # Block volume operations
      - NETWORKS=0    # Block network operations
      - BUILD=0       # Block build operations
      - EXEC=0        # Block exec operations
    networks:
      - talos-network

  # Browser Automation Container
  browser:
    image: mcr.microsoft.com/playwright:v1.40.0-jammy
    container_name: talos-browser
    restart: unless-stopped
    environment:
      - REAPER_TIMEOUT_MS=300000  # 5 min inactivity timeout
    networks:
      - talos-network
    profiles:
      - browser  # Only start when needed

networks:
  talos-network:
    driver: bridge
```

### Step 5: Start Talos

```bash
cd ~/talos

# Pull latest images
docker-compose pull

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f talos

# Verify health
curl http://localhost:8081/health | jq .
```

### Step 6: Access the Dashboard

```bash
# Via local browser (if GUI available)
firefox http://localhost:8080

# Via SSH tunnel (remote access)
ssh -L 8080:localhost:8080 user@talos-host

# Via Tailscale (if configured)
# Access at http://talos-node:8080 from Tailscale network
```

---

## Configuration Guide

### Environment Variables Reference

#### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TALOS_VERSION` | 4.0.0 | Version identifier |
| `TRUST_LEVEL` | 0 | 0-5: Higher = more permissive with skills |
| `TALOS_INSTANCE_ID` | auto | Unique instance identifier |

#### AI Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | (required) | Google Gemini Flash API key |
| `GEMINI_MODEL_NAME` | gemini-1.5-flash | Model to use |
| `GEMINI_MAX_TOKENS` | 8192 | Max tokens per request |
| `GEMINI_TEMPERATURE` | 0.7 | Creativity (0.0-2.0) |
| `QWEN_MODEL_PATH` | /models/qwen | Local Qwen model (optional) |

#### Resource Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_MAX_MEMORY` | 512mb | Redis memory ceiling |
| `CHROMADB_MAX_VECTORS` | 100000 | Vector database limit |
| `VRAM_MUTEX_TIMEOUT` | 300 | GPU lock timeout (seconds) |
| `VRAM_MAX_ALLOCATION` | 4096 | Max GPU VRAM (MB) |

#### Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BASIC_AUTH_USER` | admin | Dashboard username |
| `BASIC_AUTH_PASS` | (required) | Dashboard password (16+ chars) |
| `STRIKE_THRESHOLD` | 3 | Auto-deprecate skills at N strikes |
| `SKILL_SIGNATURE_VERIFY` | true | Require signed skills |
| `RECURSIVE_SELF_IMPROVE` | false | Allow self-modification |

#### Sandbox Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_MEMORY_LIMIT` | 512m | Skill container memory |
| `SANDBOX_PIDS_LIMIT` | 50 | Max processes per skill |
| `SANDBOX_TIMEOUT` | 60 | Skill execution timeout |

#### Network Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TAILSCALE_AUTH_KEY` | (optional) | Tailscale VPN key |
| `TAILSCALE_HOSTNAME` | talos-node | Tailscale device name |
| `WEB_PORT` | 8080 | Dashboard port |
| `WEB_BIND_ADDRESS` | 127.0.0.1 | Bind address (security) |

#### Logging Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | DEBUG, INFO, WARN, ERROR |
| `LOG_FORMAT` | json | json or text |
| `LOG_TIER1_RETENTION_DAYS` | 90 | Audit log retention |
| `METRICS_ENABLED` | true | Prometheus metrics |
| `METRICS_PORT` | 9090 | Metrics endpoint port |

### Configuration Files

#### config.yaml

```yaml
# /talos/config/config.yaml
talos:
  # System settings
  system:
    name: "Talos"
    instance_id: "auto"
    timezone: "UTC"

  # AI Configuration
  ai:
    default_model: "qwen-coder-7b"
    escalation_model: "gemini-flash"
    context_window: 10
    similarity_threshold: 0.75
    system_prompts:
      local_model: "default"        # Built-in TALOS_LOCAL_SYSTEM_PROMPT
      escalation_model: "default"    # Built-in TALOS_GEMINI_SYSTEM_PROMPT
      # Override with a custom file:
      # local_model: "/talos/config/custom_local_prompt.txt"

  # Memory Configuration
  memory:
    redis:
      host: "redis"
      port: 6379
      max_memory: "512mb"
    chromadb:
      host: "chromadb"
      port: 8000
      max_vectors: 100000

  # Skill System
  skills:
    auto_load: true
    signature_verify: true
    quarantine_required: true
    min_successful_runs: 3
    strike_threshold: 3

  # MCP Servers (local stdio-based tool servers, see §2.6)
  mcp_servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/documents"]
      description: "Read/write access to user documents"
      enabled: true
      timeout_seconds: 30
      auto_start: false          # Start on first [USE_MCP:] call
    sqlite:
      command: "python"
      args: ["-m", "mcp_sqlite", "--db", "/talos/data/knowledge.db"]
      description: "Query the local knowledge database"
      enabled: true
      timeout_seconds: 15
      auto_start: false

  # Security
  security:
    trust_level: 0
    prompt_injection_detection: true
    tts_verification: true

  # Maintenance
  maintenance:
    dream_cycle_time: "04:00"
    log_compression: true
    zombie_hunt: true

  # Dashboard (see §5)
  dashboard:
    auto_open: true              # Open browser on boot
    host: "127.0.0.1"            # Localhost only
    port: 8080
    metrics_interval: 1.0        # Seconds between metric pushes
    token_daily_limit: 50000     # Daily soft limit
    theme: "dark"
```

---

## Using Talos

### Web Dashboard

The Web Dashboard (`http://localhost:8080`) is your primary interface with Talos. It opens automatically when Talos starts (controlled by `dashboard.auto_open` in config). See §5 in the Master Spec for full implementation details.

#### Dashboard Layout

The dashboard has 4 panels:

| Panel | Purpose |
|---|---|
| **Header Bar** | System status badge (🟢/🟡/🔴), uptime, active model, emergency stop button |
| **Performance Panel** | Live CPU/RAM/GPU/VRAM gauges + per-model token counters (Qwen & Gemini) with daily totals |
| **Chat Panel** | Interactive Talos conversation — type messages, see `[USE_SKILL:]` and `[USE_MCP:]` calls rendered as badges |
| **Log Viewer** | Streaming logs with level filter (DEBUG/INFO/WARN/ERROR), component filter, and free-text search |

```
┌─────────────────────────────────────────────────────────────────────┐
│  ◉ TALOS v4.0     ⏱ Uptime: 14d 3h     🟢 Healthy     ⛔ E-STOP   │
├───────────────────────────────────┬─────────────────────────────────┤
│  CPU ◔ 23%  RAM ◑ 4.2GB          │  Talos: Hello! How can I help?  │
│  GPU ◔ 45%  VRAM ◑ 2.1GB         │                                 │
│                                   │  You: Check system health       │
│  TOKEN USAGE                      │                                 │
│  Qwen:   12,450 / 8,230 = 20,680 │  Talos: All systems healthy.    │
│  Gemini:  4,100 / 3,890 =  7,990 │  CPU 23%, GPU 45%, disk 45%...  │
│  Daily:  ████████░░ 28,670        │                                 │
│                                   │  [Type a message...        ⏎]  │
├───────────────────────────────────┴─────────────────────────────────┤
│  ▼Level  ▼Component  🔍 Search...                        ⏸ Auto    │
│  11:41:02 INFO  orchestrator  Request processed in 234ms           │
│  11:40:58 WARN  token_tracker Daily tokens: 28,670/50,000          │
│  11:40:55 INFO  orchestrator  [USE_SKILL: weather] invoked         │
└─────────────────────────────────────────────────────────────────────┘
```

#### Token Counters

The performance panel tracks token usage in real time:

- **Per-model breakdown**: Prompt tokens, completion tokens, and totals for both Qwen Coder 7B and Gemini Flash
- **Daily progress bar**: Visual indicator showing daily consumption against the configurable limit (default 50,000)
- **7-day history**: Available via `GET /api/tokens`

Token data is persisted in Redis and survives restarts.

#### Chat Panel

Chat directly with Talos from the dashboard:

1. Type your message in the input box at the bottom
2. Press **Enter** to send
3. Talos responds with the full orchestrator pipeline (firewall → context → LLM → response)
4. Tool calls appear as colored badges: ⚡ for skills, 🔌 for MCP tools

#### Log Viewer

The log viewer streams from `/var/log/talos/orchestrator.log` in real time:

- **Level filter**: Show only WARN and ERROR to focus on issues
- **Component filter**: Isolate logs from a specific module (e.g., `vram_mutex`)
- **Search**: Free-text filter within log messages
- **Click to expand**: Click any log line to see the full JSON detail
- **Auto-scroll**: Toggle with the ⏸ button

#### Starting a Conversation

1. Click the chat input or press `/` to focus
2. Type your message or command
3. Talos will respond and can execute actions

**Example Interactions:**

```
You: Find the latest news about AI
Talos: [⚡ web_scraper]
     → Returns summarized news articles

You: Read my project README
Talos: [🔌 filesystem.read_file]
     → Displays file contents

You: Create a Python script to analyze CSV files
Talos: [Generates skill "csv_analyzer"]
     → Skill quarantined for testing
     → After 3 successful runs, promoted to active
```

### Telegram/Discord Integration

#### Setting Up Telegram

1. Message @BotFather on Telegram
2. Create new bot: `/newbot`
3. Copy the API token
4. Add to `talos.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```
5. Restart Talos: `docker-compose restart talos`

#### Telegram Commands

```
/start - Begin conversation
/help  - Show available commands
/status - Check system health
/skills - List active skills
/memory - Show memory usage
/panic  - Emergency stop (requires code)
```

### Using Skills

#### Built-in Skills

| Skill | Description | Example |
|-------|-------------|---------|
| `web_scraper` | Extract data from websites | "Scrape headlines from bbc.com" |
| `file_manager` | Read/write files | "Read my todo.txt file" |
| `docker_control` | Manage containers | "List running containers" |
| `code_executor` | Run Python/Shell code | "Calculate fibonacci(100)" |
| `browser_automation` | Control browser | "Take screenshot of google.com" |

#### Creating Custom Skills

You can ask Talos to create new skills:

```
You: Create a skill that converts CSV to JSON

Talos: I'll create a "csv_to_json" skill for you.

       [Generates Python code]
       [Saves to quarantine]

       The skill is now in quarantine. It needs:
       1. 3 successful test runs
       2. Your approval with TTS code

       Would you like me to test it now?
```

#### Skill Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                     SKILL LIFECYCLE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Creation                                                  │
│      │                                                      │
│      ▼                                                      │
│   ┌──────────────┐                                          │
│   │  QUARANTINE  │ ←── Isolated testing environment         │
│   │   (3 runs)   │     • Cannot affect production            │
│   └──────┬───────┘     • Sandboxed (512MB, 50 PIDs)         │
│          │                                                  │
│          │ 3 successful runs                                 │
│          ▼                                                  │
│   ┌──────────────┐                                          │
│   │   TESTING    │ ←── User approval required               │
│   │ (TTS Verify) │     • 4-digit code shown in dashboard    │
│   └──────┬───────┘     • Must type code to approve          │
│          │                                                  │
│          │ User confirms                                     │
│          ▼                                                  │
│   ┌──────────────┐                                          │
│   │    ACTIVE    │ ←── Production use                       │
│   │  (Available) │     • Loaded into main toolset           │
│   └──────┬───────┘     • Can be invoked by name             │
│          │                                                  │
│          │ Errors accumulate                                 │
│          ▼                                                  │
│   ┌──────────────┐                                          │
│   │  STRIKES     │ ←── 3-Strike System                      │
│   │  (1/2/3)     │     • Strike 1: Warning logged           │
│   └──────┬───────┘     • Strike 2: Alert shown              │
│          │             • Strike 3: Auto-deprecate            │
│          │ 3 strikes                                         │
│          ▼                                                  │
│   ┌──────────────┐                                          │
│   │  DEPRECATED  │ ←── Moved to archive                     │
│   │  (Retired)   │     • No longer available                │
│   └──────────────┘     • Can be manually restored           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Skill System

### What Are Skills?

Skills are **containerized Python/Shell scripts** that extend Talos' capabilities. They:
- Run in isolated Docker containers
- Have limited resources (512MB RAM, 50 processes)
- Can access the internet (if approved)
- Can be created by you or generated by Talos

### Skill Structure

```
skill_name/
├── skill.json          # Metadata and manifest
├── main.py            # Entry point (Python)
├── requirements.txt   # Python dependencies
├── README.md          # Documentation
└── tests/
    └── test_main.py   # Unit tests
```

### skill.json Format

```json
{
  "name": "web_scraper",
  "version": "1.0.0",
  "description": "Extract data from websites using requests and BeautifulSoup",
  "author": "Talos",
  "trust_level": 1,
  "entry_point": "main.py",
  "language": "python",
  "dependencies": ["requests", "beautifulsoup4"],
  "permissions": {
    "network": true,
    "filesystem": "read-only",
    "docker": false
  },
  "resources": {
    "memory": "512m",
    "timeout": 60
  }
}
```

### Installing Skills

#### Method 1: From GitHub

```bash
# Download skill to quarantine
cd ~/talos/skills/quarantine
git clone https://github.com/example/talos-skill-web_scraper.git

# Talos will automatically detect and test
```

#### Method 2: Via Dashboard

1. Go to **Skills** → **Install New**
2. Paste GitHub URL or upload ZIP
3. Talos validates and quarantines
4. Approve after testing

#### Method 3: Auto-Generated

```
You: Create a skill that monitors website uptime

Talos: [Generates skill code]
     → Saved to quarantine
     → Runs 3 test iterations
     → Requests your approval
```

### Managing Skills

```bash
# List active skills
ls ~/talos/skills/active/

# View skill logs
cat ~/talos/logs/tier2/skill_web_scraper.log

# Manually deprecate a skill
mv ~/talos/skills/active/bad_skill ~/talos/skills/deprecated/

# Restore deprecated skill
mv ~/talos/skills/deprecated/good_skill ~/talos/skills/quarantine/
# Then re-run promotion workflow
```

---

## Memory & Context

### Memory Architecture

Talos uses a **three-tier memory system**:

```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY HIERARCHY                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TIER 1: SHORT-TERM (Redis)                                 │
│  ├── Current conversation context                           │
│  ├── Recent messages (last 10)                              │
│  ├── Session state                                          │
│  └── Cache: 512MB, LRU eviction                             │
│                                                             │
│  TIER 2: LONG-TERM (ChromaDB)                               │
│  ├── Knowledge base (facts, preferences)                    │
│  ├── Skill execution history                                │
│  ├── Previous conversations (summarized)                    │
│  └── Limit: 100,000 vectors                                 │
│                                                             │
│  TIER 3: ARCHIVE (Disk)                                     │
│  ├── Full conversation logs                                 │
│  ├── Skill code and versions                                │
│  ├── System audit logs (90 days)                            │
│  └── Compressed logs (rotated)                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### How Context Works

When you send a message, Talos:

1. **Retrieves relevant context** from ChromaDB (RAG)
2. **Adds recent conversation** from Redis
3. **Selects the model-specific system prompt** via `PromptManager`
   - Local model → `TALOS_LOCAL_SYSTEM_PROMPT`
   - Escalation model → `TALOS_GEMINI_SYSTEM_PROMPT`
4. **Sends to LLM** for processing

### Context Window Management

```
Context Budget: 32,768 tokens (Qwen Coder)

Allocation:
├── System Prompt:     ~500 tokens (TALOS_LOCAL_SYSTEM_PROMPT or
│                       TALOS_GEMINI_SYSTEM_PROMPT, see §2.3)
├── Retrieved Context: ~8,000 tokens (from ChromaDB)
├── Recent Messages:   ~4,000 tokens (from Redis)
└── Available for User: ~20,000 tokens
```

### Vector Search (RAG)

Talos converts text to embeddings and stores them in ChromaDB:

```python
# Example: How RAG works internally
user_query = "What did we discuss about AI safety?"

# 1. Convert to embedding
query_vector = embed(user_query)  # 1536 dimensions

# 2. Search ChromaDB
results = chroma_db.query(
    query_embeddings=[query_vector],
    n_results=5,  # Top 5 matches
    where={"type": "conversation"}
)

# 3. Add to context
context = "\n".join([r.document for r in results])
```

### Memory Persistence

| Data Type | Persistence | Backup |
|-----------|-------------|--------|
| Redis | Ephemeral (LRU) | No |
| ChromaDB | Persistent (disk) | Yes |
| Logs | Persistent (rotated) | Yes |
| Config | Persistent | Yes |

---

## Security Features

### Multi-Layer Security Model

```
┌─────────────────────────────────────────────────────────────┐
│                   SECURITY LAYERS                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  LAYER 1: INPUT SANITIZATION                                │
│  ├── Prompt Injection Firewall                              │
│  │   └── Blocks: "Ignore previous", "System Override"       │
│  ├── Keyword filtering                                      │
│  └── Rate limiting                                          │
│                                                             │
│  LAYER 2: SKILL ISOLATION                                   │
│  ├── Quarantine system (3 runs required)                    │
│  ├── Sandboxed execution (Docker containers)                │
│  ├── Resource limits (512MB, 50 PIDs)                       │
│  └── 3-Strike auto-deprecation                              │
│                                                             │
│  LAYER 3: ACCESS CONTROL                                    │
│  ├── Basic Authentication (dashboard)                       │
│  ├── TTS verification (4-digit codes)                       │
│  └── Tailscale VPN (optional)                               │
│                                                             │
│  LAYER 4: INFRASTRUCTURE                                    │
│  ├── Socket Proxy (restricted Docker API)                   │
│  ├── Directory permissions (700, 750)                       │
│  └── Non-root container execution                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Prompt Injection Protection

Talos scans all inputs for attack patterns:

| Pattern | Action |
|---------|--------|
| "Ignore previous instructions" | Block + Log |
| "System Override" | Block + Alert |
| "sudo" command | Block + Log |
| "rm -rf /" | Block + Alert |
| XML tag injection | Sanitize + Log |

### Skill Quarantine

New skills are isolated until proven safe:

```
1. Skill Created
      ↓
2. Moved to ~/talos/skills/quarantine/
      ↓
3. 3 Test executions in sandbox
   - Each run: 60 second timeout
   - Resource monitoring
   - Network activity logged
      ↓
4. User Approval Required
   - TTS code displayed in dashboard
   - Must type code to approve
      ↓
5. Promoted to Active
   - Moved to ~/talos/skills/active/
   - Loaded into toolset
```

### TTS Verification

Critical actions require a **4-digit code** displayed in the dashboard:

```
[Dashboard Log]
[14:23:45] Skill "file_deleter" requests permission to delete files
[14:23:45] TTS CODE: 7392
[14:23:45] User must speak/type this code to proceed
```

This prevents:
- Audio-based social engineering
- "Yes" bias in voice assistants
- Unauthorized destructive actions

---

## Maintenance & Monitoring

### The 4:00 AM "Dream" Cycle

Every day at 4:00 AM, Talos performs automatic maintenance:

```
┌─────────────────────────────────────────────────────────────┐
│                    DREAM CYCLE (04:00)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1: Redis Flush (0-30s)                               │
│  ├── Preserve: config, skill registry, audit logs           │
│  ├── Delete: session data, temporary cache                  │
│  └── Verify: memory usage reduced                           │
│                                                             │
│  Phase 2: Vector Pruning (30s-15min)                        │
│  ├── Score all vectors (frequency + recency + priority)    │
│  ├── Delete bottom 10% (if >90K vectors)                    │
│  └── Preserve: "permanent" tagged vectors                   │
│                                                             │
│  Phase 3: Log Compression (15-20min)                        │
│  ├── Compress logs older than 24h to .gz                    │
│  ├── Delete tier2/3 logs beyond 50MB ring buffer            │
│  └── Preserve tier1 audit logs                              │
│                                                             │
│  Phase 4: Zombie Hunt (20-25min)                            │
│  ├── Find containers >3 days old                            │
│  ├── Find processes >3 days old                             │
│  └── Terminate orphans                                      │
│                                                             │
│  Phase 5: Health Report (25-30min)                          │
│  ├── System metrics                                         │
│  ├── Resource usage trends                                  │
│  └── Alert if issues detected                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Monitoring Dashboard

Access metrics at `http://localhost:9090/metrics`:

```yaml
# Example Prometheus metrics
talos_memory_usage_bytes 536870912
talos_chromadb_vectors_total 45231
talos_skills_active 12
talos_skills_quarantined 2
talos_requests_total{status="success"} 1543
talos_request_duration_seconds_bucket{le="0.5"} 892
talos_gpu_memory_usage_bytes 2147483648
```

### Health Check Endpoint

```bash
# Check system health
curl http://localhost:8081/health | jq .
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T08:30:00Z",
  "checks": {
    "redis": {"status": "ok", "response_ms": 2},
    "chromadb": {"status": "ok", "vectors": 45231},
    "disk": {"status": "ok", "used_percent": 45},
    "memory": {"status": "ok", "used_percent": 62}
  }
}
```

### Log Files

| Log File | Location | Retention |
|----------|----------|-----------|
| Audit Log | `~/talos/logs/tier1/audit.log` | 90 days |
| Operations | `~/talos/logs/tier2/ops.log` | 50MB ring |
| Debug | `~/talos/logs/tier3/debug.log` | 50MB ring |
| Boot Log | `~/talos/logs/tier2/boot.log` | 10 rotations |
| Panic Log | `~/talos/logs/tier1/panic.log` | 90 days |

View logs:
```bash
# Real-time tail
tail -f ~/talos/logs/tier2/ops.log

# Search for errors
grep ERROR ~/talos/logs/tier2/ops.log | tail -20

# JSON parsing with jq
cat ~/talos/logs/tier2/ops.log | jq '. | select(.level == "ERROR")'
```

---

## Troubleshooting

### Common Issues

#### Issue: Talos won't start

```bash
# Check Docker containers
docker-compose ps

# View logs
docker-compose logs talos

# Check for port conflicts
sudo netstat -tlnp | grep 8080

# Verify environment file
ls -la ~/talos/config/talos.env
cat ~/talos/config/talos.env | grep GEMINI

# Restart services
docker-compose down
docker-compose up -d
```

#### Issue: Redis connection failed

```bash
# Check Redis container
docker-compose logs redis

# Test Redis connection
docker-compose exec redis redis-cli ping

# Check Redis memory
redis-cli info memory | grep used_memory

# Restart Redis
docker-compose restart redis
```

#### Issue: ChromaDB vector limit reached

```bash
# Check current count
curl http://localhost:8000/api/v1/collections | jq .

# Manual prune (if needed)
docker-compose exec talos python /app/scripts/emergency_prune.py

# Increase limit (temporary)
# Edit talos.env: CHROMADB_MAX_VECTORS=150000
# Restart: docker-compose restart talos
```

#### Issue: Skill keeps getting strikes

```bash
# Check skill logs
docker-compose logs talos | grep "skill_name"

# View strike details
cat ~/talos/logs/tier2/skill_strikes.log

# Reset strikes (if needed)
# 1. Stop Talos
# 2. Edit database: DELETE FROM skill_strikes WHERE skill_id = 'xxx';
# 3. Start Talos
```

#### Issue: GPU out of memory

```bash
# Check GPU status
nvidia-smi

# Clear GPU cache
docker-compose exec talos python -c "import torch; torch.cuda.empty_cache()"

# Restart Talos (nuclear option)
docker-compose restart talos
```

### Emergency Procedures

#### Panic Stop (System Unresponsive)

```bash
# Method 1: Dashboard
# Click "PANIC STOP" button in Emergency Controls

# Method 2: API
curl -X POST http://localhost:8080/api/v1/emergency/panic   -H "Authorization: Bearer $TOKEN"

# Method 3: Signal file
touch ~/talos/SIGNAL_PANIC

# Method 4: Force kill
docker-compose kill -s SIGKILL talos
```

#### Recovery After Crash

```bash
# Check for recovery state
ls -la ~/talos/data/emergency_state.json

# Restore from backup
./restore.sh ~/talos/backups/backup_20240115.tar.gz

# Manual database repair
docker-compose exec chromadb chroma repair
```

### Getting Help

1. **Check logs first**: `docker-compose logs talos | tail -100`
2. **Health endpoint**: `curl http://localhost:8081/health`
3. **Documentation**: Review this guide
4. **Community**: GitHub Issues / Discord

---

## Best Practices

### Security

✅ **DO:**
- Use strong passwords (16+ characters)
- Enable Tailscale for remote access
- Regularly review quarantined skills
- Monitor audit logs for anomalies
- Keep TRUST_LEVEL at 0 for production

❌ **DON'T:**
- Expose port 8080 to the internet
- Run as root user
- Approve skills without reviewing code
- Disable signature verification
- Share TTS codes

### Performance

✅ **DO:**
- Monitor Redis memory usage
- Archive old conversations
- Use priority tags for important memories
- Regular backups
- Keep Docker images updated

❌ **DON'T:**
- Store massive files in ChromaDB
- Let logs fill up disk
- Ignore "degraded" health status
- Run multiple GPU models simultaneously
- Skip the dream cycle

### Skill Development

✅ **DO:**
- Write clear documentation
- Include error handling
- Add unit tests
- Use standard library packages only
- Request only necessary permissions

❌ **DON'T:**
- Hardcode credentials
- Make network requests without declaring
- Use excessive resources
- Ignore sandbox timeouts
- Submit untested code

---

## Advanced Topics

### Custom Model Integration

Add your own LLM to Talos:

```python
# ~/talos/skills/active/my_model/main.py
from talos.llm import BaseLLM

class MyCustomLLM(BaseLLM):
    def __init__(self):
        self.model = load_my_model()

    async def generate(self, prompt, **kwargs):
        return self.model.generate(prompt)

# Register in config.yaml
llm:
  custom_models:
    - name: "my-model"
      class: "my_model.main.MyCustomLLM"
```

### Webhook Integration

Receive notifications from external systems:

```yaml
# config.yaml
webhooks:
  github:
    url: "https://talos.local:8080/webhooks/github"
    secret: "${GITHUB_WEBHOOK_SECRET}"
    events: ["push", "pull_request"]

  alertmanager:
    url: "https://talos.local:8080/webhooks/alerts"
    actions:
      - name: "high_cpu"
        command: "scale_up"
```

### Multi-Instance Setup

Run multiple Talos instances for high availability:

```yaml
# docker-compose.ha.yml
version: '3.8'

services:
  talos-primary:
    image: talos/v4:latest
    environment:
      - TALOS_ROLE=primary
      - TALOS_REPLICAS=http://talos-secondary:8080

  talos-secondary:
    image: talos/v4:latest
    environment:
      - TALOS_ROLE=replica
      - TALOS_PRIMARY=http://talos-primary:8080
```

---

## API Reference

### REST API Endpoints

#### Chat

```http
POST /api/v1/chat
Content-Type: application/json
Authorization: Bearer $TOKEN

{
  "message": "Hello Talos",
  "session_id": "optional-session-id",
  "context_depth": 10
}
```

Response:
```json
{
  "response": "Hello! How can I help you today?",
  "session_id": "abc123",
  "skills_used": [],
  "tokens_used": 25
}
```

#### Skills

```http
# List skills
GET /api/v1/skills

# Get skill details
GET /api/v1/skills/{skill_id}

# Execute skill
POST /api/v1/skills/{skill_id}/execute
{
  "parameters": {"url": "https://example.com"}
}

# Create skill (auto-quarantine)
POST /api/v1/skills
{
  "name": "my_skill",
  "code": "...",
  "language": "python"
}
```

#### Memory

```http
# Search memory
GET /api/v1/memory/search?q=AI safety&limit=5

# Add memory
POST /api/v1/memory
{
  "content": "User prefers dark mode",
  "tags": ["preference", "ui"],
  "priority": "high"
}

# Delete memory
DELETE /api/v1/memory/{memory_id}
```

#### System

```http
# Health check
GET /api/v1/health

# Metrics
GET /api/v1/metrics

# Logs
GET /api/v1/logs?level=ERROR&limit=100

# Emergency stop
POST /api/v1/emergency/panic
{
  "reason": "System unresponsive",
  "preserve_state": true
}
```

### WebSocket API

Real-time communication:

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'chat',
    message: 'Hello'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.response);
};
```

---

## FAQ

### General Questions

**Q: Is Talos free?**
A: Yes, Talos is FOSS (Free and Open Source Software). You only pay for:
- Your own hardware/electricity
- Gemini API usage (free tier available)
- Optional cloud backup storage

**Q: Can I run Talos without a GPU?**
A: Yes, but performance will be slower. Talos will use CPU for Qwen models and fall back to Gemini Flash for complex tasks.

**Q: How much does it cost to run?**
A: For a typical home setup:
- Electricity: ~$10-20/month (24/7 operation)
- Gemini API: Free tier (1,500 requests/day)
- Hardware: One-time $500-1500

**Q: Is my data private?**
A: Yes. All data stays on your machine. Only API calls to Gemini leave your network (and Google doesn't train on Gemini API data).

### Technical Questions

**Q: Can I use OpenAI/Anthropic instead of Gemini?**
A: Not in the base version (FOSS requirement). You can create a custom skill that calls OpenAI API.

**Q: How do I backup my data?**
A: Talos auto-backups daily to `~/talos/backups/`. For manual backup:
```bash
tar -czf backup_$(date +%Y%m%d).tar.gz ~/talos/
```

**Q: Can Talos access the internet?**
A: Yes, via the `web_scraper` skill and browser automation. Each skill declares its network requirements.

**Q: What happens if Redis fills up?**
A: Redis uses LRU (Least Recently Used) eviction. Old data is automatically deleted to make room for new data.

**Q: How do I update Talos?**
A: 
```bash
cd ~/talos
docker-compose pull
docker-compose up -d
```

### Skill Questions

**Q: Can skills damage my system?**
A: No. Skills run in sandboxed Docker containers with:
- No access to host filesystem (except ~/talos/skills/)
- Network access only if declared
- Resource limits (512MB RAM, 50 processes)
- 60-second timeout

**Q: How long does quarantine take?**
A: Minimum 24 hours (to observe behavior) + 3 successful test runs. Typically 1-3 days.

**Q: Can I skip quarantine?**
A: No. This is a security feature. You can lower TRUST_LEVEL to auto-approve more, but quarantine is mandatory.

**Q: What programming languages are supported?**
A: Python (primary), JavaScript/Node.js, and Bash. Python recommended for new skills.

### Troubleshooting Questions

**Q: Talos is slow, how do I speed it up?**
A: 
1. Check GPU memory: `nvidia-smi`
2. Reduce context window: `MEMORY_CONTEXT_WINDOW=5`
3. Clear old vectors: Trigger manual dream cycle
4. Upgrade hardware (more RAM, better GPU)

**Q: How do I reset everything?**
A:
```bash
# Stop Talos
docker-compose down

# Delete all data (DANGEROUS)
sudo rm -rf ~/talos/data/*
sudo rm -rf ~/talos/logs/*

# Restart (will reinitialize)
docker-compose up -d
```

**Q: Where do I get a Gemini API key?**
A: https://makersuite.google.com/app/apikey - Free tier includes 1,500 requests/day.

---

## Quick Reference Card

### Essential Commands

```bash
# Start Talos
docker-compose up -d

# Stop Talos
docker-compose down

# View logs
docker-compose logs -f talos

# Check health
curl http://localhost:8081/health

# Backup manually
tar -czf backup_$(date +%Y%m%d).tar.gz ~/talos/

# Update Talos
docker-compose pull && docker-compose up -d

# Emergency stop
docker-compose kill -s SIGKILL talos
```

### Directory Quick Reference

| Path | Purpose |
|------|---------|
| `~/talos/skills/active/` | Production skills |
| `~/talos/skills/quarantine/` | Testing skills |
| `~/talos/data/chromadb/` | Vector database |
| `~/talos/logs/tier1/` | Audit logs |
| `~/talos/config/talos.env` | Environment variables |
| `~/talos/backups/` | Auto-backups |

### Port Reference

| Port | Service | Access |
|------|---------|--------|
| 8080 | Web Dashboard | Localhost only |
| 8081 | Health Check | Localhost only |
| 9090 | Metrics | Localhost only |
| 6379 | Redis | Internal only |
| 8000 | ChromaDB | Internal only |
| 2375 | Docker Proxy | Internal only |

---

**Document Version:** 1.0  
**Last Updated:** February 19, 2026  
**For Talos Version:** 4.0.0-Ironclad

---

*"The best AI assistant is the one you control."*

---
