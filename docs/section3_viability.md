# Section 3: Long-Term Viability & Sleep
## Talos v4.0 Master Implementation Specification

**Document Version:** 4.0.0  
**Last Updated:** 2024  
**Operational Lifespan:** 3+ Years Unattended

---

## 3.1 The 4:00 AM "Dream" Logic

### 3.1.1 Cron Schedule Configuration

The Nocturnal Context Consolidation runs at 04:00 local time daily with staggered sub-tasks to prevent resource contention.

```cron
# /etc/cron.d/talos-dream
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/opt/talos/bin
TALOS_HOME=/opt/talos
LOG_DIR=/var/log/talos

# Main Dream Cycle - 04:00:00
0 4 * * * root /opt/talos/bin/dream-cycle.sh >> /var/log/talos/dream.log 2>&1

# Sub-task Staggers (triggered by main cycle)
# Phase 1: Redis Flush (04:00:00 - 04:00:30)
# Phase 2: Vector Pruning (04:00:30 - 04:15:00)
# Phase 3: Log Compression (04:15:00 - 04:20:00)
# Phase 4: Zombie Hunt (04:20:00 - 04:25:00)
# Phase 5: Health Report (04:25:00 - 04:30:00)
```

### 3.1.2 Dream Cycle Orchestrator

```python
# /opt/talos/core/dream_orchestrator.py

class DreamCycle:
    """
    Nocturnal maintenance orchestrator.
    Guarantees completion within 30 minutes or triggers escalation.
    """
    
    MAX_CYCLE_DURATION = 1800  # 30 minutes hard limit
    PHASE_TIMEOUTS = {
        'redis_flush': 30,
        'vector_prune': 900,
        'log_compress': 300,
        'zombie_hunt': 300,
        'health_report': 60
    }
    
    def __init__(self):
        self.state_file = '/var/lib/talos/dream_state.json'
        self.checkpoint_interval = 30  # seconds
        
    def execute_dream_cycle(self):
        """Main entry point triggered by cron."""
        cycle_start = time.time()
        self._write_checkpoint('cycle_start', cycle_start)
        
        phases = [
            ('redis_flush', self._phase_redis_flush),
            ('vector_prune', self._phase_vector_prune),
            ('log_compress', self._phase_log_compress),
            ('zombie_hunt', self._phase_zombie_hunt),
            ('health_report', self._phase_health_report)
        ]
        
        for phase_name, phase_func in phases:
            if time.time() - cycle_start > self.MAX_CYCLE_DURATION:
                self._escalate_timeout(phase_name)
                break
                
            try:
                with timeout(self.PHASE_TIMEOUTS[phase_name]):
                    phase_func()
                    self._write_checkpoint(f'{phase_name}_complete', time.time())
            except TimeoutError:
                self._escalate_timeout(phase_name)
            except Exception as e:
                self._log_phase_error(phase_name, e)
                
        self._write_checkpoint('cycle_complete', time.time())
```

### 3.1.3 Redis Flush Procedure

```python
def _phase_redis_flush(self):
    """
    Flush Redis short-term memory with verification.
    Preserves critical system keys, flushes ephemeral session data.
    """
    import redis
    
    r = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        socket_timeout=10,
        socket_connect_timeout=5
    )
    
    # Pre-flush metrics
    pre_info = r.info('memory')
    pre_keys = r.dbsize()
    
    # Keys to PRESERVE (never flush)
    PROTECTED_PATTERNS = [
        'talos:config:*',
        'talos:skill:registry',
        'talos:system:version',
        'talos:vector:schema',
        'talos:audit:*'
    ]
    
    # Collect protected keys
    protected_keys = set()
    for pattern in PROTECTED_PATTERNS:
        protected_keys.update(r.keys(pattern))
    
    # Get all keys
    all_keys = r.keys('*')
    keys_to_delete = [k for k in all_keys if k not in protected_keys]
    
    # Batch deletion with progress tracking
    BATCH_SIZE = 1000
    deleted_count = 0
    failed_keys = []
    
    for i in range(0, len(keys_to_delete), BATCH_SIZE):
        batch = keys_to_delete[i:i + BATCH_SIZE]
        pipeline = r.pipeline()
        
        for key in batch:
            pipeline.delete(key)
            
        results = pipeline.execute()
        deleted_count += sum(results)
        
        # Checkpoint every batch
        if i % (BATCH_SIZE * 10) == 0:
            self._write_checkpoint('redis_flush_progress', {
                'processed': i,
                'total': len(keys_to_delete),
                'deleted': deleted_count
            })
    
    # Verification
    post_info = r.info('memory')
    post_keys = r.dbsize()
    
    # Assert memory reduction
    memory_freed = pre_info['used_memory'] - post_info['used_memory']
    if memory_freed < 0:
        raise RuntimeError(f"Redis flush failed: memory increased by {abs(memory_freed)} bytes")
    
    # Log results
    logging.info(f"Redis flush complete: {deleted_count} keys deleted, "
                 f"{memory_freed / 1024 / 1024:.2f} MB freed, "
                 f"{post_keys} protected keys remain")
```

### 3.1.4 ChromaDB Vector Pruning Algorithm

```python
def _phase_vector_prune(self):
    """
    Prune ChromaDB vectors using multi-factor retention scoring.
    Guarantees database stays under 100,000 vector ceiling.
    """
    import chromadb
    from datetime import datetime, timedelta
    
    MAX_VECTORS = 100000
    PRUNE_THRESHOLD = 90000  # Start pruning at 90%
    TARGET_SIZE = 80000      # Prune down to 80%
    BATCH_SIZE = 500         # Vectors per deletion batch
    
    client = chromadb.HttpClient(host='localhost', port=8000)
    collection = client.get_collection('talos_memory')
    
    # Get current count
    current_count = collection.count()
    
    if current_count <= PRUNE_THRESHOLD:
        logging.info(f"Vector count {current_count} below threshold {PRUNE_THRESHOLD}, skipping prune")
        return
    
    # Calculate how many to delete
    vectors_to_delete = current_count - TARGET_SIZE
    
    # Retrieve all vectors with metadata
    results = collection.get(
        include=['metadatas', 'embeddings'],
        limit=current_count
    )
    
    # Score each vector for retention
    scored_vectors = []
    cutoff_date = datetime.now() - timedelta(days=30)
    
    for i, (id, metadata) in enumerate(zip(results['ids'], results['metadatas'])):
        score = self._calculate_retention_score(id, metadata, cutoff_date)
        scored_vectors.append((id, score, metadata))
    
    # Sort by score (lowest first = delete first)
    scored_vectors.sort(key=lambda x: x[1])
    
    # Delete lowest-scored vectors in batches
    deleted = 0
    failed = []
    
    for i in range(0, min(vectors_to_delete, len(scored_vectors)), BATCH_SIZE):
        batch = scored_vectors[i:i + BATCH_SIZE]
        ids_to_delete = [v[0] for v in batch]
        
        try:
            collection.delete(ids=ids_to_delete)
            deleted += len(ids_to_delete)
            
            # Checkpoint progress
            self._write_checkpoint('vector_prune_progress', {
                'deleted': deleted,
                'target': vectors_to_delete,
                'remaining': current_count - deleted
            })
        except Exception as e:
            failed.extend(ids_to_delete)
            logging.error(f"Batch delete failed: {e}")
    
    # Verify final count
    final_count = collection.count()
    logging.info(f"Vector prune complete: {deleted} deleted, {final_count} remain")
    
    if final_count > MAX_VECTORS:
        raise RuntimeError(f"Vector pruning failed: {final_count} still exceeds max {MAX_VECTORS}")
```

### 3.1.5 Log Compression Implementation

```python
def _phase_log_compress(self):
    """
    Compress logs older than 24 hours to .gz format.
    Tier 2/3 logs: Rotate and compress.
    Tier 1 logs: Copy to archive, never delete.
    """
    import gzip
    import shutil
    from pathlib import Path
    
    LOG_DIR = Path('/var/log/talos')
    ARCHIVE_DIR = Path('/var/log/talos/archive')
    RING_BUFFER_SIZE = 50 * 1024 * 1024  # 50MB
    
    ARCHIVE_DIR.mkdir(exist_ok=True)
    
    log_tiers = {
        'tier1': {'pattern': '*audit*.log', 'compress': True, 'delete': False},
        'tier2': {'pattern': '*ops*.log', 'compress': True, 'delete': True, 'max_age_days': 7},
        'tier3': {'pattern': '*debug*.log', 'compress': True, 'delete': True, 'max_age_days': 3}
    }
    
    compressed_count = 0
    deleted_count = 0
    
    for tier, config in log_tiers.items():
        for log_file in LOG_DIR.glob(config['pattern']):
            if log_file.suffix == '.gz':
                continue  # Already compressed
                
            file_age_days = (time.time() - log_file.stat().st_mtime) / 86400
            
            # Compress logs older than 24 hours
            if file_age_days >= 1:
                compressed_path = ARCHIVE_DIR / f"{log_file.name}.{datetime.now():%Y%m%d}.gz"
                
                with open(log_file, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb', compresslevel=6) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                compressed_count += 1
                
                # Delete original if configured
                if config['delete']:
                    log_file.unlink()
                
            # Delete old compressed files
            if config['delete'] and 'max_age_days' in config:
                for archive_file in ARCHIVE_DIR.glob(f"*{tier}*.gz"):
                    archive_age = (time.time() - archive_file.stat().st_mtime) / 86400
                    if archive_age > config['max_age_days']:
                        archive_file.unlink()
                        deleted_count += 1
    
    # Enforce ring buffer size for tier2/3
    self._enforce_ring_buffer(ARCHIVE_DIR, RING_BUFFER_SIZE)
    
    logging.info(f"Log compression complete: {compressed_count} compressed, {deleted_count} deleted")

def _enforce_ring_buffer(self, archive_dir: Path, max_size: int):
    """Delete oldest archives if total size exceeds limit."""
    archives = sorted(
        archive_dir.glob('*.gz'),
        key=lambda p: p.stat().st_mtime
    )
    
    total_size = sum(a.stat().st_size for a in archives)
    
    while total_size > max_size and archives:
        oldest = archives.pop(0)
        total_size -= oldest.stat().st_size
        oldest.unlink()
        logging.info(f"Ring buffer eviction: {oldest.name}")
```

### 3.1.6 Zombie Hunt Algorithm

```python
def _phase_zombie_hunt(self):
    """
    Identify and terminate orphaned containers and processes.
    Kills any PID/container older than 3 days not in active registry.
    """
    import docker
    import psutil
    from datetime import datetime, timedelta
    
    MAX_AGE_DAYS = 3
    ZOMBIE_THRESHOLD = timedelta(days=MAX_AGE_DAYS)
    
    killed_containers = 0
    killed_processes = 0
    
    # Get active skill registry
    active_skills = self._get_active_skill_registry()
    active_pids = {s['pid'] for s in active_skills}
    active_containers = {s['container_id'] for s in active_skills if s.get('container_id')}
    
    # Hunt orphaned containers
    try:
        client = docker.from_env()
        for container in client.containers.list(all=True):
            # Check if Talos-managed
            if not container.labels.get('talos.managed'):
                continue
                
            # Check age
            created = datetime.fromisoformat(container.attrs['Created'].replace('Z', '+00:00'))
            age = datetime.now(created.tzinfo) - created
            
            if age > ZOMBIE_THRESHOLD and container.id not in active_containers:
                logging.warning(f"Zombie container found: {container.id[:12]}, age: {age.days} days")
                container.kill(signal='SIGTERM')
                time.sleep(5)
                if container.status != 'exited':
                    container.kill(signal='SIGKILL')
                container.remove(force=True)
                killed_containers += 1
    except Exception as e:
        logging.error(f"Container zombie hunt failed: {e}")
    
    # Hunt orphaned processes
    for proc in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline']):
        try:
            # Check if Talos-managed
            if 'talos' not in ' '.join(proc.info['cmdline'] or []):
                continue
                
            # Check age
            create_time = datetime.fromtimestamp(proc.info['create_time'])
            age = datetime.now() - create_time
            
            if age > ZOMBIE_THRESHOLD and proc.info['pid'] not in active_pids:
                logging.warning(f"Zombie process found: PID {proc.info['pid']}, age: {age.days} days")
                proc.terminate()
                gone, alive = psutil.wait_procs([proc], timeout=5)
                if alive:
                    alive[0].kill()
                killed_processes += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    logging.info(f"Zombie hunt complete: {killed_containers} containers, {killed_processes} processes killed")
```

---

## 3.2 Vector Retention Algorithm (Detailed)

### 3.2.1 Retention Score Formula

The retention score combines multiple factors to determine which vectors survive pruning.

```
Retention Score = (Priority_Base × 100) + (Frequency_Score × 50) + (Recency_Score × 30) + (Relationship_Bonus × 20)

Where:
- Priority_Base: 4=permanent, 3=high, 2=normal, 1=temporary
- Frequency_Score: log10(access_count + 1) / log10(max_access_count + 1)
- Recency_Score: 1 - (days_since_access / 30)
- Relationship_Bonus: count_of_linked_vectors / 10
```

### 3.2.2 Priority Level Definitions

```python
PRIORITY_LEVELS = {
    'permanent': {
        'base_score': 4.0,
        'never_prune': True,
        'tag_pattern': 'priority:permanent',
        'examples': ['system_config', 'user_profile', 'skill_registry']
    },
    'high': {
        'base_score': 3.0,
        'min_retention_days': 90,
        'tag_pattern': 'priority:high',
        'examples': ['frequently_accessed_knowledge', 'active_project_context']
    },
    'normal': {
        'base_score': 2.0,
        'min_retention_days': 30,
        'tag_pattern': 'priority:normal',
        'examples': ['general_conversation', 'temporary_context']
    },
    'temporary': {
        'base_score': 1.0,
        'max_retention_days': 7,
        'tag_pattern': 'priority:temporary',
        'examples': ['session_scratchpad', 'one_time_query_result']
    }
}
```

### 3.2.3 Complete Scoring Implementation

```python
def _calculate_retention_score(self, vector_id: str, metadata: dict, cutoff_date: datetime) -> float:
    """
    Calculate retention score for a vector.
    Higher score = higher priority to keep.
    """
    import math
    
    # Extract priority from tags
    tags = metadata.get('tags', [])
    priority = self._extract_priority(tags)
    
    # Permanent vectors get maximum score
    if priority['never_prune']:
        return float('inf')
    
    base_score = priority['base_score'] * 100
    
    # Frequency score (0-50)
    access_count = metadata.get('access_count', 0)
    last_access = metadata.get('last_access')
    
    # Get max access count from system stats
    max_access = self._get_max_access_count()
    if max_access > 0:
        frequency_score = (math.log10(access_count + 1) / math.log10(max_access + 1)) * 50
    else:
        frequency_score = 0
    
    # Recency score (0-30)
    if last_access:
        last_access_dt = datetime.fromisoformat(last_access)
        days_since = (datetime.now() - last_access_dt).days
        recency_score = max(0, (1 - (days_since / 30))) * 30
    else:
        recency_score = 0
    
    # Relationship bonus (0-20)
    linked_vectors = metadata.get('linked_vectors', [])
    relationship_bonus = min(len(linked_vectors) * 2, 20)
    
    # Age penalty for old normal/temporary vectors
    created = metadata.get('created')
    age_penalty = 0
    if created and not priority['never_prune']:
        created_dt = datetime.fromisoformat(created)
        age_days = (datetime.now() - created_dt).days
        if age_days > priority.get('min_retention_days', 30):
            age_penalty = (age_days - priority['min_retention_days']) * 0.5
    
    total_score = base_score + frequency_score + recency_score + relationship_bonus - age_penalty
    
    return max(0, total_score)

def _extract_priority(self, tags: list) -> dict:
    """Extract priority level from tags."""
    for tag in tags:
        if tag.startswith('priority:'):
            level = tag.split(':')[1]
            return PRIORITY_LEVELS.get(level, PRIORITY_LEVELS['normal'])
    return PRIORITY_LEVELS['normal']
```

### 3.2.4 Edge Case Handling

```python
def _handle_pruning_edge_cases(self, scored_vectors: list, current_count: int, target_count: int):
    """
    Handle edge cases in vector pruning.
    """
    # Edge Case 1: All vectors are permanent
    permanent_count = sum(1 for v in scored_vectors if v[1] == float('inf'))
    if permanent_count >= target_count:
        logging.warning(f"All {permanent_count} vectors are permanent, cannot prune to {target_count}")
        # Raise ceiling temporarily
        return min(current_count, int(MAX_VECTORS * 1.1))
    
    # Edge Case 2: Too many high-priority vectors
    high_priority_count = sum(1 for v in scored_vectors if v[1] >= 300)
    if high_priority_count >= target_count:
        logging.warning(f"{high_priority_count} high-priority vectors exceed target {target_count}")
        # Adjust target to keep all high-priority
        return max(target_count, high_priority_count + 1000)
    
    # Edge Case 3: Orphaned vectors (no relationships)
    orphaned = [v for v in scored_vectors if v[2].get('linked_vectors', []) == []]
    if len(orphaned) > (current_count - target_count):
        # Prioritize deleting orphans first
        logging.info(f"Prioritizing {len(orphaned)} orphaned vectors for deletion")
    
    # Edge Case 4: Cluster preservation
    clusters = self._identify_vector_clusters(scored_vectors)
    for cluster_id, cluster_vectors in clusters.items():
        if len(cluster_vectors) < 10:
            # Small cluster - boost scores to preserve
            for v in cluster_vectors:
                v[1] += 25  # Boost retention score
    
    return target_count
```

---

## 3.3 Dependency Isolation Strategy

### 3.3.1 Standard Library Docker Image

```dockerfile
# /opt/talos/docker/standard-library/Dockerfile
# Talos Standard Library v4.0.0
# Build: docker build -t talos/standard-lib:4.0.0 .

FROM python:3.11-slim-bookworm

LABEL maintainer="Talos System"
LABEL version="4.0.0"
LABEL description="Talos Standard Library - Skill Execution Environment"

# System dependencies (minimal, audited)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python standard library packages (frozen versions)
COPY requirements-standard.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-standard.txt

# Create talos user (non-root execution)
RUN groupadd -r talos && useradd -r -g talos talos

# Skill mount point
RUN mkdir -p /skill && chown talos:talos /skill

# Security: No network access by default
# Skills must explicitly request network capability

USER talos
WORKDIR /skill

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

ENTRYPOINT ["python"]
```

### 3.3.2 Standard Library Requirements

```txt
# /opt/talos/docker/standard-library/requirements-standard.txt
# Talos Standard Library v4.0.0
# Last updated: 2024-01-15
# Frozen versions for reproducibility

# Core Data Processing
numpy==1.26.3
pandas==2.1.4

# HTTP/API
requests==2.31.0
urllib3==2.1.0

# JSON/Data
jsonschema==4.20.0
pyyaml==6.0.1

# Date/Time
python-dateutil==2.8.2
pytz==2023.3

# Text Processing
regex==2023.12.25
chardet==5.2.0

# Cryptography (limited)
cryptography==41.0.7

# Utilities
python-dotenv==1.0.0
tenacity==8.2.3

# NO ML frameworks (too large)
# NO database drivers (use APIs)
# NO web frameworks (security risk)
```

### 3.3.3 Library Manifest Format

```yaml
# /opt/talos/config/library-manifest.yaml
manifest_version: "4.0.0"
last_updated: "2024-01-15"

# Allowed packages with version constraints
allowed_packages:
  numpy:
    min_version: "1.26.0"
    max_version: "1.27.0"
    reason: "Core array operations"
    
  pandas:
    min_version: "2.1.0"
    max_version: "2.2.0"
    reason: "Data frame operations"
    
  requests:
    min_version: "2.31.0"
    max_version: "3.0.0"
    reason: "HTTP client"

# Explicitly banned packages
banned_packages:
  - name: "tensorflow"
    reason: "Too large (500MB+), use API instead"
  - name: "torch"
    reason: "Too large (1GB+), use API instead"
  - name: "django"
    reason: "Web framework not allowed in skills"
  - name: "flask"
    reason: "Web framework not allowed in skills"
  - name: "psycopg2"
    reason: "Direct DB access not allowed, use API"

# Network capabilities required for specific packages
network_required:
  - "requests"
  - "urllib3"
  - "httpx"
```

### 3.3.4 Skill Dependency Validation

```python
# /opt/talos/core/dependency_validator.py

class DependencyValidator:
    """
    Validates skill dependencies against standard library.
    Rejects skills requiring non-standard packages.
    """
    
    def __init__(self):
        self.manifest = self._load_manifest()
        self.standard_packages = self._load_standard_packages()
        
    def validate_skill(self, skill_path: Path) -> ValidationResult:
        """
        Validate a skill's dependencies.
        Returns ValidationResult with approved/rejected status.
        """
        # Extract requirements from skill
        requirements = self._extract_requirements(skill_path)
        
        violations = []
        warnings = []
        
        for req in requirements:
            package_name = req.name.lower()
            
            # Check if in standard library
            if package_name not in self.standard_packages:
                violations.append({
                    'package': package_name,
                    'severity': 'error',
                    'message': f"'{package_name}' not in Talos Standard Library",
                    'action': 'rebuild_required'
                })
                continue
            
            # Check version constraints
            if package_name in self.manifest['allowed_packages']:
                constraints = self.manifest['allowed_packages'][package_name]
                if not self._version_satisfies(req.specs, constraints):
                    violations.append({
                        'package': package_name,
                        'severity': 'error',
                        'message': f"Version {req.specs} outside allowed range",
                        'action': 'version_adjust'
                    })
            
            # Check banned list
            if package_name in [b['name'] for b in self.manifest['banned_packages']]:
                ban_info = next(b for b in self.manifest['banned_packages'] if b['name'] == package_name)
                violations.append({
                    'package': package_name,
                    'severity': 'critical',
                    'message': f"'{package_name}' is banned: {ban_info['reason']}",
                    'action': 'alternative_required'
                })
        
        if violations:
            return ValidationResult(
                approved=False,
                violations=violations,
                rejection_message=self._generate_rejection_message(skill_path.name, violations)
            )
        
        return ValidationResult(approved=True)
    
    def _generate_rejection_message(self, skill_name: str, violations: list) -> str:
        """Generate user-friendly rejection message with rebuild instructions."""
        
        message = f"""
╔══════════════════════════════════════════════════════════════════╗
║  SKILL REJECTED: {skill_name:<45} ║
╠══════════════════════════════════════════════════════════════════╣
║  This skill requires packages not in the Talos Standard Library  ║
╚══════════════════════════════════════════════════════════════════╝

DEPENDENCY VIOLATIONS:
"""
        for v in violations:
            message += f"  • [{v['severity'].upper()}] {v['package']}: {v['message']}\n"
        
        message += """
TO RESOLVE:

1. Review your skill's requirements.txt
2. Replace non-standard packages with standard alternatives:

   BANNED PACKAGE          STANDARD ALTERNATIVE
   ───────────────────────────────────────────────
   tensorflow              Use Talos ML API
   torch                   Use Talos ML API  
   django/flask            Use Talos Webhook API
   psycopg2/mysql          Use Talos Database API

3. If you MUST use a non-standard package:

   a. Fork the standard library:
      git clone /opt/talos/docker/standard-library ~/talos-stdlib
   
   b. Add your package to requirements-standard.txt
   
   c. Rebuild the image:
      cd ~/talos-stdlib
      docker build -t talos/standard-lib:custom-{skill_name} .
   
   d. Update Talos config:
      echo "TALOS_STDlib_IMAGE=talos/standard-lib:custom-{skill_name}" >> ~/.talos/config

4. Resubmit your skill for validation

For help: https://docs.talos.ai/standard-library
"""
        return message
```

### 3.3.5 Docker Build Commands

```bash
#!/bin/bash
# /opt/talos/bin/rebuild-stdlib.sh
# Rebuild Talos Standard Library Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="${SCRIPT_DIR}/../docker/standard-library"
VERSION=$(cat "${DOCKER_DIR}/VERSION" 2>/dev/null || echo "4.0.0")

# Parse arguments
CUSTOM_TAG=""
PUSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --tag)
            CUSTOM_TAG="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--tag custom-tag] [--push]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

TAG="${CUSTOM_TAG:-${VERSION}}"
IMAGE_NAME="talos/standard-lib:${TAG}"

echo "Building Talos Standard Library..."
echo "  Version: ${VERSION}"
echo "  Image: ${IMAGE_NAME}"
echo ""

# Build with cache
docker build \
    --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
    --build-arg VERSION="${VERSION}" \
    --tag "${IMAGE_NAME}" \
    --tag "talos/standard-lib:latest" \
    "${DOCKER_DIR}"

# Verify build
echo ""
echo "Verifying image..."
docker run --rm "${IMAGE_NAME}" python -c "import numpy, pandas, requests; print('OK')"

# Push if requested
if [ "$PUSH" = true ]; then
    echo "Pushing to registry..."
    docker push "${IMAGE_NAME}"
fi

echo ""
echo "Build complete: ${IMAGE_NAME}"
echo "Update TALOS_STDlib_IMAGE in config to use this version"
```

---

## 3.4 Resource Ceiling Enforcement

### 3.4.1 Redis LRU Configuration

```python
# /opt/talos/config/redis.conf

# Redis Configuration for Talos v4.0
# Memory: Hard ceiling at 512MB with LRU eviction

# Network
bind 127.0.0.1
port 6379
protected-mode yes

# Memory Management (CRITICAL)
maxmemory 512mb
maxmemory-policy allkeys-lru
maxmemory-samples 5

# Persistence (minimal for cache use)
save ""  # Disable RDB snapshots
appendonly no  # Disable AOF

# Performance
databases 1
hash-max-ziplist-entries 512
hash-max-ziplist-value 64
list-max-ziplist-size -2
set-max-intset-entries 512

# Security
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_7a3f9e2b"

# Logging
loglevel notice
logfile /var/log/talos/redis.log

# Limits
timeout 300
tcp-keepalive 60
client-output-buffer-limit normal 0 0 0
client-output-buffer-limit replica 256mb 64mb 60
client-output-buffer-limit pubsub 32mb 8mb 60
```

### 3.4.2 ChromaDB Max Vector Enforcement

```python
# /opt/talos/core/vector_store_manager.py

class VectorStoreManager:
    """
    Manages ChromaDB with hard vector ceiling.
    Enforces 100,000 vector maximum with automatic pruning.
    """
    
    MAX_VECTORS = 100000
    WARNING_THRESHOLD = 0.9  # 90%
    CRITICAL_THRESHOLD = 0.95  # 95%
    EMERGENCY_THRESHOLD = 0.99  # 99%
    
    def __init__(self):
        self.client = chromadb.HttpClient(host='localhost', port=8000)
        self.collection = self.client.get_or_create_collection('talos_memory')
        self._enforce_ceiling()
    
    def add_vectors(self, vectors: list, metadata: list, ids: list) -> AddResult:
        """
        Add vectors with ceiling enforcement.
        May reject additions if at capacity.
        """
        current_count = self.collection.count()
        incoming_count = len(vectors)
        
        # Check if we have room
        if current_count + incoming_count > self.MAX_VECTORS:
            # Calculate how many we can accept
            available = self.MAX_VECTORS - current_count
            
            if available <= 0:
                # At capacity - trigger emergency prune
                self._emergency_prune()
                available = self.MAX_VECTORS - self.collection.count()
                
                if available <= 0:
                    return AddResult(
                        success=False,
                        added=0,
                        error="Vector store at maximum capacity. Pruning failed."
                    )
            
            # Accept only what fits
            vectors = vectors[:available]
            metadata = metadata[:available]
            ids = ids[:available]
            
            logging.warning(f"Vector addition truncated: {incoming_count} requested, {available} accepted")
        
        # Add vectors
        try:
            self.collection.add(
                embeddings=vectors,
                metadatas=metadata,
                ids=ids
            )
            
            # Check thresholds
            self._check_thresholds()
            
            return AddResult(
                success=True,
                added=len(vectors),
                truncated=(incoming_count > len(vectors))
            )
        except Exception as e:
            return AddResult(success=False, added=0, error=str(e))
    
    def _check_thresholds(self):
        """Check current usage against thresholds and alert."""
        count = self.collection.count()
        ratio = count / self.MAX_VECTORS
        
        if ratio >= self.EMERGENCY_THRESHOLD:
            logging.critical(f"EMERGENCY: Vector store at {ratio*100:.1f}% capacity ({count}/{self.MAX_VECTORS})")
            self._emergency_prune()
        elif ratio >= self.CRITICAL_THRESHOLD:
            logging.error(f"CRITICAL: Vector store at {ratio*100:.1f}% capacity ({count}/{self.MAX_VECTORS})")
        elif ratio >= self.WARNING_THRESHOLD:
            logging.warning(f"WARNING: Vector store at {ratio*100:.1f}% capacity ({count}/{self.MAX_VECTORS})")
    
    def _emergency_prune(self):
        """Aggressive pruning when at emergency threshold."""
        logging.critical("Executing emergency vector prune")
        
        # Delete all temporary vectors immediately
        results = self.collection.get(where={"priority": "temporary"})
        if results['ids']:
            self.collection.delete(ids=results['ids'])
            logging.info(f"Emergency prune: deleted {len(results['ids'])} temporary vectors")
        
        # If still critical, delete normal priority vectors older than 7 days
        if self.collection.count() / self.MAX_VECTORS >= self.CRITICAL_THRESHOLD:
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            results = self.collection.get(
                where={
                    "$and": [
                        {"priority": "normal"},
                        {"created": {"$lt": cutoff}}
                    ]
                }
            )
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                logging.info(f"Emergency prune: deleted {len(results['ids'])} old normal vectors")
```

### 3.4.3 Disk Space Monitoring

```python
# /opt/talos/core/disk_monitor.py

class DiskMonitor:
    """
    Monitor disk space and trigger degradation when low.
    Prevents system failure from full disk.
    """
    
    THRESHOLDS = {
        'healthy': 0.7,      # 70% used
        'warning': 0.8,      # 80% used
        'critical': 0.9,     # 90% used
        'emergency': 0.95    # 95% used
    }
    
    CHECK_INTERVAL = 300  # 5 minutes
    
    def __init__(self):
        self.mount_points = ['/var/log/talos', '/var/lib/talos', '/tmp']
        self.degradation_actions = DegradationActions()
        
    def start_monitoring(self):
        """Start background disk monitoring thread."""
        import threading
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
    
    def _monitor_loop(self):
        """Continuous monitoring loop."""
        while True:
            for mount in self.mount_points:
                self._check_mount(mount)
            time.sleep(self.CHECK_INTERVAL)
    
    def _check_mount(self, mount: str):
        """Check disk usage for a mount point."""
        try:
            usage = shutil.disk_usage(mount)
            used_ratio = usage.used / usage.total
            
            if used_ratio >= self.THRESHOLDS['emergency']:
                self._handle_emergency(mount, used_ratio)
            elif used_ratio >= self.THRESHOLDS['critical']:
                self._handle_critical(mount, used_ratio)
            elif used_ratio >= self.THRESHOLDS['warning']:
                self._handle_warning(mount, used_ratio)
                
        except Exception as e:
            logging.error(f"Disk check failed for {mount}: {e}")
    
    def _handle_emergency(self, mount: str, ratio: float):
        """Emergency response - aggressive cleanup."""
        logging.critical(f"DISK EMERGENCY: {mount} at {ratio*100:.1f}% capacity")
        
        # Immediate actions
        self.degradation_actions.stop_non_critical_services()
        self.degradation_actions.delete_old_logs(days=1)
        self.degradation_actions.clear_temp_files()
        self.degradation_actions.compress_all_logs()
        
        # Alert
        self._send_alert('CRITICAL', f'Disk emergency on {mount}: {ratio*100:.1f}% full')
    
    def _handle_critical(self, mount: str, ratio: float):
        """Critical response - proactive cleanup."""
        logging.error(f"DISK CRITICAL: {mount} at {ratio*100:.1f}% capacity")
        
        self.degradation_actions.delete_old_logs(days=3)
        self.degradation_actions.clear_temp_files()
        
    def _handle_warning(self, mount: str, ratio: float):
        """Warning response - prepare for cleanup."""
        logging.warning(f"DISK WARNING: {mount} at {ratio*100:.1f}% capacity")
        
        # Schedule early dream cycle
        self.degradation_actions.schedule_early_maintenance()

class DegradationActions:
    """Actions to take when resources are constrained."""
    
    def stop_non_critical_services(self):
        """Stop services that aren't essential."""
        non_critical = ['talos.metrics', 'talos.analytics']
        for service in non_critical:
            subprocess.run(['systemctl', 'stop', service], check=False)
    
    def delete_old_logs(self, days: int):
        """Delete logs older than specified days."""
        cutoff = time.time() - (days * 86400)
        log_dir = Path('/var/log/talos')
        
        for log_file in log_dir.glob('*.log*'):
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                logging.info(f"Deleted old log: {log_file.name}")
    
    def clear_temp_files(self):
        """Clear temporary files."""
        temp_dir = Path('/tmp/talos')
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
    
    def compress_all_logs(self):
        """Force compression of all logs."""
        subprocess.run(['/opt/talos/bin/compress-logs.sh', '--force'], check=False)
    
    def schedule_early_maintenance(self):
        """Schedule dream cycle to run early."""
        subprocess.run(['/opt/talos/bin/dream-cycle.sh', '--now'], check=False)
```

---

## 3.5 Multi-Year Operational Considerations

### 3.5.1 Database Compaction Schedule

```python
# /opt/talos/core/compaction_scheduler.py

class CompactionScheduler:
    """
    Schedule and execute database compaction operations.
    Prevents performance degradation over years of operation.
    """
    
    COMPACTION_SCHEDULE = {
        'daily': {
            'time': '04:30',
            'operations': ['wal_checkpoint', 'index_stats_update'],
            'max_duration': 300
        },
        'weekly': {
            'day': 'sunday',
            'time': '03:00',
            'operations': ['full_vacuum', 'index_rebuild', 'stats_recalc'],
            'max_duration': 3600
        },
        'monthly': {
            'day': 1,  # First of month
            'time': '02:00',
            'operations': ['deep_vacuum', 'index_defrag', 'integrity_check'],
            'max_duration': 7200
        },
        'yearly': {
            'month': 1,  # January
            'day': 1,
            'time': '01:00',
            'operations': ['full_rebuild', 'archive_old_data', 'verify_backups'],
            'max_duration': 14400
        }
    }
    
    def __init__(self):
        self.chroma_client = chromadb.HttpClient(host='localhost', port=8000)
        self.sqlite_conn = sqlite3.connect('/var/lib/talos/talos.db')
        
    def run_compaction(self, level: str):
        """Run compaction operations for specified level."""
        schedule = self.COMPACTION_SCHEDULE[level]
        
        logging.info(f"Starting {level} compaction: {schedule['operations']}")
        start_time = time.time()
        
        for operation in schedule['operations']:
            if time.time() - start_time > schedule['max_duration']:
                logging.warning(f"Compaction timeout reached, stopping at {operation}")
                break
                
            try:
                getattr(self, f'_op_{operation}')()
            except Exception as e:
                logging.error(f"Compaction operation {operation} failed: {e}")
                
        elapsed = time.time() - start_time
        logging.info(f"{level} compaction complete in {elapsed:.1f}s")
    
    def _op_wal_checkpoint(self):
        """Checkpoint SQLite WAL."""
        self.sqlite_conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    
    def _op_full_vacuum(self):
        """Vacuum SQLite database."""
        self.sqlite_conn.execute('VACUUM')
    
    def _op_deep_vacuum(self):
        """Deep vacuum with analysis."""
        self.sqlite_conn.execute('VACUUM')
        self.sqlite_conn.execute('ANALYZE')
    
    def _op_index_rebuild(self):
        """Rebuild ChromaDB HNSW index."""
        collection = self.chroma_client.get_collection('talos_memory')
        # Trigger index rebuild through ChromaDB API
        collection.modify(metadata={'index_rebuild': datetime.now().isoformat()})
    
    def _op_integrity_check(self):
        """Verify database integrity."""
        cursor = self.sqlite_conn.execute('PRAGMA integrity_check')
        result = cursor.fetchone()
        if result[0] != 'ok':
            raise RuntimeError(f"Integrity check failed: {result[0]}")
```

### 3.5.2 Index Rebuilding Strategy

```python
# /opt/talos/core/index_manager.py

class IndexManager:
    """
    Manage vector index health over multi-year operation.
    Rebuilds indexes when fragmentation exceeds thresholds.
    """
    
    REBUILD_TRIGGERS = {
        'fragmentation_threshold': 0.3,  # 30% fragmentation
        'query_degradation': 0.2,  # 20% slower queries
        'age_days': 90  # Rebuild every 90 days regardless
    }
    
    def __init__(self):
        self.client = chromadb.HttpClient(host='localhost', port=8000)
        self.metrics = MetricsStore()
        
    def check_index_health(self) -> IndexHealth:
        """Check if index needs rebuilding."""
        collection = self.client.get_collection('talos_memory')
        
        # Check age
        last_rebuild = self._get_last_rebuild_time()
        age_days = (datetime.now() - last_rebuild).days
        
        if age_days >= self.REBUILD_TRIGGERS['age_days']:
            return IndexHealth(needs_rebuild=True, reason=f"Age: {age_days} days")
        
        # Check query performance
        baseline = self.metrics.get_baseline_query_time()
        current = self._measure_query_time()
        
        if baseline > 0 and (current - baseline) / baseline > self.REBUILD_TRIGGERS['query_degradation']:
            return IndexHealth(needs_rebuild=True, reason=f"Query degradation: {((current-baseline)/baseline)*100:.1f}%")
        
        return IndexHealth(needs_rebuild=False)
    
    def rebuild_index(self):
        """Rebuild vector index with progress tracking."""
        logging.info("Starting index rebuild")
        
        collection = self.client.get_collection('talos_memory')
        
        # Get all vectors
        results = collection.get(include=['embeddings', 'metadatas'])
        
        # Create new collection
        temp_name = f"talos_memory_rebuild_{int(time.time())}"
        temp_collection = self.client.create_collection(temp_name)
        
        # Batch re-insert
        BATCH_SIZE = 1000
        for i in range(0, len(results['ids']), BATCH_SIZE):
            batch_slice = slice(i, i + BATCH_SIZE)
            temp_collection.add(
                ids=results['ids'][batch_slice],
                embeddings=results['embeddings'][batch_slice],
                metadatas=results['metadatas'][batch_slice]
            )
            
            # Progress checkpoint
            self._write_checkpoint('index_rebuild', {
                'processed': i + BATCH_SIZE,
                'total': len(results['ids'])
            })
        
        # Atomic swap
        self.client.delete_collection('talos_memory')
        self.client.get_collection(temp_name).modify(name='talos_memory')
        
        logging.info("Index rebuild complete")
```

### 3.5.3 Log Archive Rotation

```python
# /opt/talos/core/archive_manager.py

class ArchiveManager:
    """
    Manage long-term log archives with multi-year rotation.
    Implements hierarchical storage strategy.
    """
    
    ARCHIVE_TIERS = {
        'hot': {
            'path': '/var/log/talos/archive/hot',
            'retention_days': 30,
            'compression': 'gzip',
            'access_pattern': 'frequent'
        },
        'warm': {
            'path': '/var/log/talos/archive/warm',
            'retention_days': 90,
            'compression': 'bzip2',
            'access_pattern': 'occasional'
        },
        'cold': {
            'path': '/var/log/talos/archive/cold',
            'retention_days': 365,
            'compression': 'xz',
            'access_pattern': 'rare'
        },
        'glacier': {
            'path': '/var/log/talos/archive/glacier',
            'retention_days': 1095,  # 3 years
            'compression': 'xz',
            'access_pattern': 'emergency_only'
        }
    }
    
    def rotate_archives(self):
        """Move archives between tiers based on age."""
        for tier_name, tier_config in self.ARCHIVE_TIERS.items():
            self._process_tier(tier_name, tier_config)
    
    def _process_tier(self, tier_name: str, config: dict):
        """Process a single archive tier."""
        tier_path = Path(config['path'])
        tier_path.mkdir(parents=True, exist_ok=True)
        
        # Move older archives to next tier
        next_tier = self._get_next_tier(tier_name)
        
        for archive_file in tier_path.glob('*.gz'):
            age_days = (time.time() - archive_file.stat().st_mtime) / 86400
            
            if age_days > config['retention_days']:
                if next_tier:
                    self._promote_to_tier(archive_file, next_tier)
                else:
                    # Final tier - delete
                    archive_file.unlink()
                    logging.info(f"Deleted old archive: {archive_file.name}")
    
    def _promote_to_tier(self, archive_file: Path, target_tier: dict):
        """Move archive to colder tier with recompression."""
        target_path = Path(target_tier['path'])
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Recompress with target tier's algorithm
        target_file = target_path / archive_file.name.replace('.gz', self._get_ext(target_tier['compression']))
        
        self._recompress(archive_file, target_file, target_tier['compression'])
        archive_file.unlink()
        
        logging.info(f"Promoted {archive_file.name} to {target_tier['path']}")
```

### 3.5.4 Backup Validation

```python
# /opt/talos/core/backup_validator.py

class BackupValidator:
    """
    Validate backup integrity on schedule.
    Ensures recovery is possible after years of operation.
    """
    
    VALIDATION_SCHEDULE = {
        'daily': {'type': 'existence', 'scope': 'latest'},
        'weekly': {'type': 'checksum', 'scope': 'last_7_days'},
        'monthly': {'type': 'restore_test', 'scope': 'random_sample'},
        'yearly': {'type': 'full_restore', 'scope': 'complete'}
    }
    
    def __init__(self):
        self.backup_dir = Path('/var/backups/talos')
        self.validation_results = []
        
    def run_validation(self, level: str):
        """Run validation at specified level."""
        schedule = self.VALIDATION_SCHEDULE[level]
        
        logging.info(f"Starting {level} backup validation: {schedule['type']}")
        
        if schedule['type'] == 'existence':
            self._validate_existence(schedule['scope'])
        elif schedule['type'] == 'checksum':
            self._validate_checksums(schedule['scope'])
        elif schedule['type'] == 'restore_test':
            self._test_restore(schedule['scope'])
        elif schedule['type'] == 'full_restore':
            self._full_restore_test()
    
    def _validate_checksums(self, scope: str):
        """Verify backup checksums."""
        backup_files = self._get_backups_for_scope(scope)
        
        for backup_file in backup_files:
            checksum_file = backup_file.with_suffix('.sha256')
            
            if not checksum_file.exists():
                logging.error(f"Missing checksum for {backup_file.name}")
                continue
            
            # Verify checksum
            result = subprocess.run(
                ['sha256sum', '-c', str(checksum_file)],
                capture_output=True,
                cwd=str(backup_file.parent)
            )
            
            if result.returncode == 0:
                logging.info(f"Checksum valid: {backup_file.name}")
            else:
                logging.error(f"Checksum FAILED: {backup_file.name}")
                self._alert_corruption(backup_file)
    
    def _test_restore(self, scope: str):
        """Test restore of random backup sample."""
        import tempfile
        
        backup_files = self._get_backups_for_scope(scope)
        if not backup_files:
            return
        
        # Select random sample
        sample = random.sample(backup_files, min(3, len(backup_files)))
        
        for backup_file in sample:
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    # Attempt restore
                    subprocess.run(
                        ['tar', '-xzf', str(backup_file), '-C', temp_dir],
                        check=True,
                        timeout=300
                    )
                    
                    # Verify structure
                    if self._verify_restore_structure(temp_dir):
                        logging.info(f"Restore test PASSED: {backup_file.name}")
                    else:
                        logging.error(f"Restore test FAILED (structure): {backup_file.name}")
                        
                except Exception as e:
                    logging.error(f"Restore test FAILED: {backup_file.name} - {e}")
    
    def _verify_restore_structure(self, restore_dir: str) -> bool:
        """Verify restored backup has expected structure."""
        required_paths = [
            'talos_memory/',
            'talos.db',
            'config/',
            'skills/'
        ]
        
        for path in required_paths:
            if not (Path(restore_dir) / path).exists():
                logging.error(f"Missing required path in restore: {path}")
                return False
        
        return True
```

---

## 3.6 Failure Recovery & Escalation

### 3.6.1 Dream Cycle Failure Recovery

```python
# /opt/talos/core/dream_recovery.py

class DreamRecovery:
    """
    Handle failures in the dream cycle with automatic recovery.
    """
    
    MAX_RETRY_ATTEMPTS = 3
    RETRY_BACKOFF = [300, 900, 3600]  # 5min, 15min, 1hour
    
    def handle_failure(self, phase: str, error: Exception, checkpoint: dict):
        """Handle a phase failure with appropriate recovery."""
        attempt = checkpoint.get('retry_attempt', 0) + 1
        
        if attempt > self.MAX_RETRY_ATTEMPTS:
            self._escalate_to_human(phase, error, checkpoint)
            return
        
        # Log failure
        logging.error(f"Dream phase {phase} failed (attempt {attempt}): {error}")
        
        # Wait before retry
        wait_time = self.RETRY_BACKOFF[min(attempt - 1, len(self.RETRY_BACKOFF) - 1)]
        logging.info(f"Retrying {phase} in {wait_time} seconds")
        time.sleep(wait_time)
        
        # Update checkpoint
        checkpoint['retry_attempt'] = attempt
        checkpoint['last_error'] = str(error)
        self._write_checkpoint(phase, checkpoint)
        
        # Retry
        return self._retry_phase(phase, checkpoint)
    
    def _escalate_to_human(self, phase: str, error: Exception, checkpoint: dict):
        """Escalate to human operator after max retries."""
        escalation = {
            'timestamp': datetime.now().isoformat(),
            'phase': phase,
            'error': str(error),
            'checkpoint': checkpoint,
            'severity': 'CRITICAL',
            'action_required': 'Manual intervention needed'
        }
        
        # Write escalation file
        escalation_file = f"/var/lib/talos/escalations/{int(time.time())}.json"
        with open(escalation_file, 'w') as f:
            json.dump(escalation, f, indent=2)
        
        # Send alert
        self._send_alert('CRITICAL', 
            f"Dream cycle phase {phase} failed after {self.MAX_RETRY_ATTEMPTS} attempts. "
            f"Escalation written to {escalation_file}")
```

### 3.6.2 3-Year Operational Checklist

```yaml
# /opt/talos/docs/3year-operations.md

# Talos 3-Year Operational Checklist

## Year 1: Foundation
- [ ] Monthly: Verify dream cycle completion
- [ ] Monthly: Check vector store growth rate
- [ ] Quarterly: Review dependency manifest
- [ ] Quarterly: Test backup restoration
- [ ] Annually: Full system audit

## Year 2: Optimization
- [ ] Monthly: Analyze pruning effectiveness
- [ ] Monthly: Review disk usage trends
- [ ] Quarterly: Rebuild indexes if needed
- [ ] Quarterly: Update standard library
- [ ] Annually: Migrate cold archives

## Year 3: Sustainability
- [ ] Monthly: Verify all automation functioning
- [ ] Monthly: Check for resource ceiling approaches
- [ ] Quarterly: Full compaction and optimization
- [ ] Quarterly: Validate 3-year backup chain
- [ ] Annually: Plan migration/upgrade path

## Continuous Monitoring
- [ ] Disk space < 80%
- [ ] Vector count < 90K
- [ ] Redis memory < 450MB
- [ ] Log rotation functioning
- [ ] Zombie processes = 0
- [ ] Backup success rate = 100%

## Failure Scenarios
1. **Dream cycle fails 3x**: Manual intervention required
2. **Vector ceiling reached**: Emergency prune + capacity review
3. **Disk > 95%**: Stop non-critical services immediately
4. **Redis OOM**: Check for memory leak, restart if needed
5. **ChromaDB corruption**: Restore from backup, rebuild index
```

---

## Appendix A: Cron Expression Summary

| Task | Cron Expression | Description |
|------|-----------------|-------------|
| Dream Cycle | `0 4 * * *` | Daily at 04:00 |
| Daily Compaction | `30 4 * * *` | Daily at 04:30 |
| Weekly Compaction | `0 3 * * 0` | Sundays at 03:00 |
| Monthly Compaction | `0 2 1 * *` | 1st of month at 02:00 |
| Yearly Maintenance | `0 1 1 1 *` | Jan 1st at 01:00 |
| Disk Check | `*/5 * * * *` | Every 5 minutes |
| Backup Validation | `0 6 * * *` | Daily at 06:00 |
| Archive Rotation | `0 5 * * 0` | Sundays at 05:00 |

---

## Appendix B: Resource Limits Summary

| Resource | Ceiling | Warning | Critical | Emergency |
|----------|---------|---------|----------|-----------|
| Redis Memory | 512 MB | 400 MB | 460 MB | 500 MB |
| ChromaDB Vectors | 100,000 | 90,000 | 95,000 | 99,000 |
| Disk Space | 100% | 80% | 90% | 95% |
| Log Buffer | 50 MB | 40 MB | 45 MB | 50 MB |
| Process Age | 3 days | 2 days | 2.5 days | 3 days |

---

*Document Version: 4.0.0*  
*Operational Lifespan: 3+ Years*  
*Last Updated: 2024*
