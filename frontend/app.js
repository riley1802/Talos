/* Talos v4.0 Dashboard — vanilla JS */
'use strict';

const API = '';  // same origin
let startTime = Date.now();
let ws = null;
let currentTab = 'active';

// ── Auth header ───────────────────────────────────────────────────────────────
function authHeaders() {
  const u = sessionStorage.getItem('talos_user') || 'admin';
  const p = sessionStorage.getItem('talos_pass') || '';
  return { 'Authorization': 'Basic ' + btoa(u + ':' + p) };
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    ...opts,
    headers: { ...authHeaders(), 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  if (res.status === 401) {
    promptLogin();
    throw new Error('Unauthorized');
  }
  return res;
}

function promptLogin() {
  const user = prompt('Username:', 'admin');
  const pass = prompt('Password:');
  if (user && pass) {
    sessionStorage.setItem('talos_user', user);
    sessionStorage.setItem('talos_pass', pass);
    location.reload();
  }
}

// ── WebSocket logs ────────────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/logs`);

  ws.onmessage = (e) => appendLog(e.data);
  ws.onclose   = () => { setTimeout(connectWS, 3000); };
  ws.onerror   = () => ws.close();
}

function appendLog(line) {
  const out = document.getElementById('log-output');
  const div = document.createElement('div');
  div.className = 'line ' + getLogClass(line);
  div.textContent = line;
  out.appendChild(div);
  // Auto-scroll if near bottom
  if (out.scrollHeight - out.scrollTop < out.clientHeight + 80) {
    out.scrollTop = out.scrollHeight;
  }
  // Keep max 500 lines
  while (out.children.length > 500) out.removeChild(out.firstChild);
}

function getLogClass(line) {
  const l = line.toUpperCase();
  if (l.includes('"CRITICAL"') || l.includes('CRITICAL')) return 'log-critical';
  if (l.includes('"ERROR"')    || l.includes('ERROR'))    return 'log-error';
  if (l.includes('"WARNING"')  || l.includes('WARN'))     return 'log-warn';
  if (l.includes('"DEBUG"')    || l.includes('DEBUG'))    return 'log-debug';
  return 'log-info';
}

// ── Metrics polling ───────────────────────────────────────────────────────────
async function pollMetrics() {
  try {
    const res = await apiFetch('/metrics');
    if (!res.ok) return;
    const m = await res.json();

    document.getElementById('vram-state').textContent   = m.vram?.state || '—';
    document.getElementById('gemini-tokens').textContent =
      `${m.gemini?.tokens_used_today || 0}/${50000}`;
    document.getElementById('vector-count').textContent  = m.total_vectors || '—';
    document.getElementById('skill-count').textContent   =
      `${m.skills?.active || 0}A / ${m.skills?.quarantine || 0}Q`;

    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const h = Math.floor(elapsed / 3600);
    const min = Math.floor((elapsed % 3600) / 60);
    const s = elapsed % 60;
    document.getElementById('uptime').textContent =
      `UP ${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  } catch (e) { /* silently ignore */ }
}

async function pollHealth() {
  try {
    const res = await fetch(API + '/health');
    const h = await res.json();
    const badge = document.getElementById('status-badge');
    badge.textContent = h.status === 'ok' ? 'ONLINE' : 'DEGRADED';
    badge.className = 'badge ' + (h.status === 'ok' ? 'badge-ok' : 'badge-warn');
  } catch (e) {
    document.getElementById('status-badge').textContent = 'OFFLINE';
    document.getElementById('status-badge').className = 'badge badge-error';
  }
}

// ── Chat ──────────────────────────────────────────────────────────────────────
function appendChatMessage(role, text) {
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  document.getElementById('chat-messages').appendChild(div);
  document.getElementById('chat-messages').scrollTop = 9999;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const btn   = document.getElementById('chat-send');
  const text  = input.value.trim();
  if (!text) return;

  input.value = '';
  btn.disabled = true;
  appendChatMessage('user', text);

  try {
    const res = await apiFetch('/chat', {
      method: 'POST',
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    if (res.status === 403) {
      appendChatMessage('blocked', `Blocked: ${data.detail}`);
    } else {
      appendChatMessage('talos', data.response || '(no response)');
    }
  } catch (e) {
    appendChatMessage('blocked', `Error: ${e.message}`);
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

document.getElementById('chat-send').addEventListener('click', sendChat);
document.getElementById('chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// ── Skills ────────────────────────────────────────────────────────────────────
async function loadSkills(tab) {
  try {
    const res = await apiFetch(`/skills?state=${tab}`);
    if (!res.ok) return;
    const skills = await res.json();
    renderSkills(skills, tab);
  } catch (e) { /* ignore */ }
}

function renderSkills(skills, tab) {
  const list = document.getElementById('skills-list');
  list.innerHTML = '';
  if (!skills.length) {
    list.innerHTML = '<div style="color:var(--muted);padding:12px;font-size:11px;">No skills</div>';
    return;
  }
  for (const s of skills) {
    const card = document.createElement('div');
    card.className = 'skill-card';
    card.innerHTML = `
      <div class="skill-id">${s.skill_id}</div>
      <div class="skill-meta">v${s.version} · ${s.code?.language || '?'} · ${s.quarantine_state}</div>
      <div class="skill-actions">
        ${tab === 'quarantine' && s.quarantine_state === 'awaiting_promotion'
          ? `<button class="btn-sm btn-promote" data-id="${s.skill_id}">PROMOTE</button>`
          : ''}
        <button class="btn-sm btn-deprecate" data-id="${s.skill_id}">DEPRECATE</button>
      </div>`;
    list.appendChild(card);
  }

  list.querySelectorAll('.btn-promote').forEach(btn => {
    btn.addEventListener('click', () => promoteSkill(btn.dataset.id));
  });
  list.querySelectorAll('.btn-deprecate').forEach(btn => {
    btn.addEventListener('click', () => deprecateSkill(btn.dataset.id));
  });
}

async function promoteSkill(skillId) {
  const code = prompt(`Enter TTS code for skill "${skillId}":`);
  if (!code) return;
  const res = await apiFetch(`/skills/${skillId}/promote`, {
    method: 'POST', body: JSON.stringify({ tts_code: code }),
  });
  const data = await res.json();
  alert(res.ok ? 'Skill promoted!' : `Failed: ${data.detail}`);
  loadSkills(currentTab);
}

async function deprecateSkill(skillId) {
  if (!confirm(`Deprecate skill "${skillId}"?`)) return;
  await apiFetch(`/skills/${skillId}`, { method: 'DELETE' });
  loadSkills(currentTab);
}

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentTab = tab.dataset.tab;
    loadSkills(currentTab);
  });
});

// ── Init ──────────────────────────────────────────────────────────────────────
connectWS();
pollHealth();
pollMetrics();
loadSkills('active');

setInterval(pollHealth,  10000);
setInterval(pollMetrics, 5000);
setInterval(() => loadSkills(currentTab), 15000);
