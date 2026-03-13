/* ═══════════════════════════════════════════════════════════
   BunkerDesktop — App Logic
   API client · State management · UI interactions
   ═══════════════════════════════════════════════════════════ */

// ── Configuration ──
const API_BASE = window.BUNKERDESKTOP_API || 'http://localhost:9551';
const POLL_INTERVAL = 4000;   // ms
const TOAST_DURATION = 3500;  // ms

// ── State ──
let engineOnline = false;
let sandboxes = [];
let pollTimer = null;
let activeSandboxId = null;   // for terminal
let terminalHistory = [];
let historyIndex = -1;
let logLastSeq = 0;           // for log polling
let logEntries = [];          // all fetched log entries
let logPollTimer = null;
let activeTab = 'logs';       // 'logs' or 'terminal'

// ═══════════════════════════════════════
//  API Client
// ═══════════════════════════════════════

async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  try {
    const resp = await fetch(`${API_BASE}${path}`, opts);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
    }
    return data;
  } catch (err) {
    if (err.message.includes('fetch')) {
      throw new Error('Engine unreachable');
    }
    throw err;
  }
}

const API = {
  // Engine
  engineStatus:    ()           => api('GET',  '/engine/status'),
  engineStop:      ()           => api('POST', '/engine/stop'),
  engineLogs:      (afterSeq)   => api('GET',  `/engine/logs?after=${afterSeq || 0}&limit=200`),

  // Sandboxes
  listSandboxes:   ()           => api('GET',  '/sandboxes'),
  createSandbox:   (opts)       => api('POST', '/sandboxes', opts),
  getSandbox:      (id)         => api('GET',  `/sandboxes/${id}`),
  destroySandbox:  (id)         => api('DELETE', `/sandboxes/${id}`),
  resetSandbox:    (id)         => api('POST', `/sandboxes/${id}/reset`),

  // Sandbox operations
  exec:            (id, cmd, timeout) => api('POST', `/sandboxes/${id}/exec`, { command: cmd, timeout: timeout || 30 }),
  writeFile:       (id, path, content) => api('POST', `/sandboxes/${id}/write-file`, { path, content }),
  readFile:        (id, path)   => api('GET',  `/sandboxes/${id}/read-file?path=${encodeURIComponent(path)}`),
  listDir:         (id, path)   => api('GET',  `/sandboxes/${id}/list-dir?path=${encodeURIComponent(path || '/')}`),
  sandboxStatus:   (id)         => api('GET',  `/sandboxes/${id}/status`),
};

// ═══════════════════════════════════════
//  Navigation
// ═══════════════════════════════════════

function navigate(page, navEl) {
  // Update nav highlighting
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  if (navEl) navEl.classList.add('active');

  // Switch page
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const target = document.getElementById(`page-${page}`);
  if (target) {
    target.classList.add('active');
    // Force re-animation
    target.style.animation = 'none';
    target.offsetHeight; // reflow
    target.style.animation = '';
  }

  // Page-specific hooks
  if (page === 'sandboxes') refreshSandboxCards();
  if (page === 'terminal') {
    if (activeTab === 'logs') {
      startLogPolling();
    } else {
      refreshTerminalSelect();
    }
  } else {
    stopLogPolling();
  }
  if (page === 'settings')  refreshSettings();
}

// ═══════════════════════════════════════
//  Polling / Data Refresh
// ═══════════════════════════════════════

async function refreshAll() {
  await Promise.allSettled([refreshEngine(), refreshSandboxes()]);
}

async function refreshEngine() {
  try {
    const data = await API.engineStatus();
    engineOnline = true;
    updateEngineUI(data);
  } catch {
    engineOnline = false;
    updateEngineUI(null);
  }
}

async function refreshSandboxes() {
  try {
    const data = await API.listSandboxes();
    sandboxes = data.sandboxes || [];
  } catch {
    sandboxes = [];
  }
  updateSandboxBadge();
  renderDashboardTable();
  refreshLogSandboxFilter();
  // If sandbox page is active, update cards too
  if (document.getElementById('page-sandboxes').classList.contains('active')) {
    refreshSandboxCards();
  }
  // Update terminal select
  refreshTerminalSelect();
}

function startPolling() {
  if (pollTimer) return;
  refreshAll();
  pollTimer = setInterval(refreshAll, POLL_INTERVAL);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ═══════════════════════════════════════
//  Engine UI Updates
// ═══════════════════════════════════════

function updateEngineUI(data) {
  const statusEl = document.getElementById('stat-status');
  const uptimeEl = document.getElementById('stat-uptime');
  const platformEl = document.getElementById('stat-platform');
  const sandboxCountEl = document.getElementById('stat-sandboxes');
  const indicator = document.getElementById('engine-indicator');
  const pulse = indicator.querySelector('.status-pulse');
  const label = indicator.querySelector('.engine-label');
  const versionEl = document.getElementById('engine-version');

  if (data) {
    statusEl.textContent = 'Running';
    statusEl.style.color = 'var(--green)';
    uptimeEl.textContent = formatUptime(data.uptime_seconds);
    platformEl.textContent = shortenPlatform(data.platform);
    sandboxCountEl.textContent = `${data.sandbox_count} / ${data.max_sandboxes}`;
    pulse.className = 'status-pulse online';
    label.textContent = 'Engine Online';
    if (data.version) versionEl.textContent = `v${data.version}`;

    // About page
    document.getElementById('about-version').textContent = data.version || '-';
    document.getElementById('about-platform').textContent = data.platform || '-';
    document.getElementById('about-api').textContent = API_BASE;
    document.getElementById('about-sandbox-count').textContent = `${data.sandbox_count} / ${data.max_sandboxes}`;
  } else {
    statusEl.textContent = 'Offline';
    statusEl.style.color = 'var(--red)';
    uptimeEl.textContent = '-';
    platformEl.textContent = '-';
    sandboxCountEl.textContent = '-';
    pulse.className = 'status-pulse offline';
    label.textContent = 'Engine Offline';
  }
}

function updateSandboxBadge() {
  const badge = document.getElementById('sandbox-badge');
  badge.textContent = sandboxes.length;
  badge.style.display = sandboxes.length > 0 ? '' : 'none';
}

// ═══════════════════════════════════════
//  Dashboard Table
// ═══════════════════════════════════════

function renderDashboardTable() {
  const wrap = document.getElementById('dashboard-sandbox-table');
  if (sandboxes.length === 0) {
    wrap.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a2 2 0 012-2h8a2 2 0 012 2v2"/></svg>
        <p>No sandboxes running</p>
        <span>Click <strong>+ Create</strong> to spin up an isolated sandbox</span>
      </div>`;
    return;
  }

  let html = `<table>
    <thead><tr>
      <th>Name</th>
      <th>Status</th>
      <th>vCPUs</th>
      <th>Memory</th>
      <th>Created</th>
      <th>Actions</th>
    </tr></thead><tbody>`;

  sandboxes.forEach(s => {
    const name = escapeHtml(s.name || s.id);
    const badge = `<span class="badge badge-running"><span class="badge-dot"></span>Running</span>`;
    const cpus = s.cpus || 1;
    const mem = s.memory ? `${s.memory} MB` : '512 MB';
    const created = s.created_at ? timeAgo(s.created_at) : '-';

    html += `<tr>
      <td><strong class="t-mono">${name}</strong><br><span class="t-muted t-sm t-mono">${escapeHtml(s.id).slice(0, 12)}</span></td>
      <td>${badge}</td>
      <td>${cpus}</td>
      <td>${mem}</td>
      <td class="t-muted">${created}</td>
      <td>
        <button class="btn btn-xs btn-ghost" onclick="openTerminalFor('${s.id}')">Terminal</button>
        <button class="btn btn-xs btn-danger" onclick="destroySandbox('${s.id}')">Destroy</button>
      </td>
    </tr>`;
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;
}

// ═══════════════════════════════════════
//  Sandbox Cards (Sandbox Manager page)
// ═══════════════════════════════════════

function refreshSandboxCards() {
  const container = document.getElementById('sandbox-list');
  if (sandboxes.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1/-1;">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a2 2 0 012-2h8a2 2 0 012 2v2"/></svg>
        <p>No sandboxes yet</p>
        <span>Click <strong>New Sandbox</strong> above to create one</span>
      </div>`;
    return;
  }

  container.innerHTML = sandboxes.map(s => {
    const name = escapeHtml(s.name || s.id);
    const shortId = escapeHtml(s.id).slice(0, 12);
    const cpus = s.cpus || 1;
    const mem = s.memory ? `${s.memory} MB` : '512 MB';
    const created = s.created_at ? timeAgo(s.created_at) : '-';
    const net = s.network ? 'Enabled' : 'Disabled';

    return `
      <div class="sandbox-card">
        <div class="sandbox-card-header">
          <div>
            <div class="sandbox-card-name">${name}</div>
            <div class="sandbox-card-id">${shortId}</div>
          </div>
          <span class="badge badge-running"><span class="badge-dot"></span>Running</span>
        </div>
        <div class="sandbox-card-meta">
          <div class="meta-item"><span class="meta-label">vCPUs</span><span class="meta-value">${cpus}</span></div>
          <div class="meta-item"><span class="meta-label">Memory</span><span class="meta-value">${mem}</span></div>
          <div class="meta-item"><span class="meta-label">Network</span><span class="meta-value">${net}</span></div>
          <div class="meta-item"><span class="meta-label">Created</span><span class="meta-value">${created}</span></div>
        </div>
        <div class="sandbox-card-actions">
          <button class="btn btn-sm btn-ghost" onclick="openTerminalFor('${s.id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
            Terminal
          </button>
          <button class="btn btn-sm btn-success" onclick="resetSandboxAction('${s.id}')">Reset</button>
          <button class="btn btn-sm btn-danger" onclick="destroySandbox('${s.id}')">Destroy</button>
        </div>
      </div>`;
  }).join('');
}

// ═══════════════════════════════════════
//  Sandbox CRUD Actions
// ═══════════════════════════════════════

function showCreateModal() {
  document.getElementById('create-modal').classList.add('show');
  document.getElementById('create-name').focus();
}

function hideCreateModal() {
  document.getElementById('create-modal').classList.remove('show');
}

function closeModal(e) {
  if (e.target === e.currentTarget) hideCreateModal();
}

async function createSandbox(e) {
  e.preventDefault();
  const btn = document.getElementById('create-submit-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Creating...';

  const name = document.getElementById('create-name').value.trim();
  const cpus = parseInt(document.getElementById('create-cpus').value) || 1;
  const memory = parseInt(document.getElementById('create-memory').value) || 512;
  const network = document.getElementById('create-network').checked;

  try {
    const result = await API.createSandbox({ name: name || undefined, cpus, memory, network });
    toast(`Sandbox "${result.name || result.id}" created`, 'success');
    hideCreateModal();
    document.getElementById('create-name').value = '';
    await refreshSandboxes();
  } catch (err) {
    toast(`Failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Create Sandbox';
  }
}

async function quickCreateSandbox() {
  if (!engineOnline) {
    toast('Engine is offline', 'error');
    return;
  }
  showCreateModal();
}

async function destroySandbox(id) {
  try {
    await API.destroySandbox(id);
    toast('Sandbox destroyed', 'success');
    await refreshSandboxes();
  } catch (err) {
    toast(`Destroy failed: ${err.message}`, 'error');
  }
}

async function resetSandboxAction(id) {
  try {
    toast('Resetting sandbox...', 'info');
    await API.resetSandbox(id);
    toast('Sandbox reset complete', 'success');
    await refreshSandboxes();
  } catch (err) {
    toast(`Reset failed: ${err.message}`, 'error');
  }
}

async function stopEngine() {
  if (!engineOnline) return;
  try {
    await API.engineStop();
    toast('Engine stopping...', 'info');
    engineOnline = false;
    updateEngineUI(null);
  } catch (err) {
    toast(`Stop failed: ${err.message}`, 'error');
  }
}

// ═══════════════════════════════════════
//  Logs & Tab Switching
// ═══════════════════════════════════════

function refreshLogSandboxFilter() {
  const select = document.getElementById('log-sandbox-filter');
  const current = select.value;
  select.innerHTML = '<option value="all">All Sandboxes</option>';
  sandboxes.forEach(s => {
    const name = s.name || s.id.slice(0, 12);
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });
  // Restore selection
  if (current && current !== 'all') {
    const exists = Array.from(select.options).some(o => o.value === current);
    if (exists) select.value = current;
  }
}

function switchTab(tab) {
  activeTab = tab;
  document.getElementById('tab-logs').classList.toggle('active', tab === 'logs');
  document.getElementById('tab-terminal').classList.toggle('active', tab === 'terminal');
  document.getElementById('view-logs').style.display = tab === 'logs' ? '' : 'none';
  document.getElementById('view-terminal').style.display = tab === 'terminal' ? '' : 'none';

  if (tab === 'logs') {
    startLogPolling();
    renderLogs();  // re-render when switching to logs
  } else {
    refreshTerminalSelect();
    document.getElementById('terminal-input').focus();
  }
}

function startLogPolling() {
  if (logPollTimer) return;
  pollLogs();
  logPollTimer = setInterval(pollLogs, 2000);
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer);
    logPollTimer = null;
  }
}

async function pollLogs() {
  if (!engineOnline) return;
  try {
    const data = await API.engineLogs(logLastSeq);
    if (data.logs && data.logs.length > 0) {
      logEntries.push(...data.logs);
      // Keep max 1000 entries in memory
      if (logEntries.length > 1000) {
        logEntries = logEntries.slice(-500);
      }
      logLastSeq = data.last_seq;
      renderLogs();
    }
  } catch {
    // Engine offline, skip
  }
}

function renderLogs() {
  const output = document.getElementById('logs-output');
  const filterLevel = document.getElementById('log-level-filter').value;
  const filterSandbox = document.getElementById('log-sandbox-filter').value;

  const levelPriority = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };
  const minPriority = filterLevel === 'all' ? -1 : (levelPriority[filterLevel] || 0);

  const filtered = logEntries.filter(e => {
    const p = levelPriority[e.level] !== undefined ? levelPriority[e.level] : 1;
    if (p < minPriority) return false;
    if (filterSandbox !== 'all') {
      // Filter by sandbox name appearing in the log message as [sandbox-name]
      if (!e.message.includes(`[${filterSandbox}]`)) return false;
    }
    return true;
  });

  const html = filtered.map(e => {
    const levelClass = `log-${e.level.toLowerCase()}`;
    const time = e.message.match(/^(\d{2}:\d{2}:\d{2})/);
    const timeStr = time ? time[1] : '';
    const msg = time ? e.message.substring(time[0].length) : e.message;
    return `<div class="log-entry ${levelClass}"><span class="log-time">${escapeHtml(timeStr)}</span><span class="log-level">${e.level.substring(0, 4)}</span><span class="log-msg">${escapeHtml(msg)}</span></div>`;
  }).join('');

  output.innerHTML = html || '<div class="terminal-welcome"><span class="t-muted">Engine logs will appear here in real-time...</span></div>';

  // Update count
  document.getElementById('log-count').textContent = `${filtered.length} entries`;

  // Auto-scroll
  if (document.getElementById('log-autoscroll').checked) {
    output.scrollTop = output.scrollHeight;
  }
}

function filterLogs() {
  renderLogs();
}

function clearLogs() {
  logEntries = [];
  renderLogs();
}

// ═══════════════════════════════════════
//  Terminal
// ═══════════════════════════════════════

function refreshTerminalSelect() {
  const select = document.getElementById('terminal-sandbox-select');
  const current = select.value;
  select.innerHTML = '<option value="">Select sandbox...</option>';
  sandboxes.forEach(s => {
    const name = s.name || s.id.slice(0, 12);
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = name;
    select.appendChild(opt);
  });
  // Restore selection
  if (current && sandboxes.find(s => s.id === current)) {
    select.value = current;
  } else if (activeSandboxId && sandboxes.find(s => s.id === activeSandboxId)) {
    select.value = activeSandboxId;
  }
}

function terminalSandboxChanged() {
  activeSandboxId = document.getElementById('terminal-sandbox-select').value;
  if (activeSandboxId) {
    appendTerminal(`Connected to sandbox ${activeSandboxId.slice(0, 12)}`, 'info');
  }
}

function openTerminalFor(sandboxId) {
  activeSandboxId = sandboxId;
  navigate('terminal', document.querySelector('[data-page=terminal]'));
  document.getElementById('terminal-sandbox-select').value = sandboxId;
  appendTerminal(`Connected to sandbox ${sandboxId.slice(0, 12)}`, 'info');
  document.getElementById('terminal-input').focus();
}

async function terminalExec(e) {
  e.preventDefault();
  const input = document.getElementById('terminal-input');
  const cmd = input.value.trim();
  if (!cmd) return;

  if (!activeSandboxId) {
    appendTerminal('No sandbox selected. Choose one from the dropdown above.', 'error');
    return;
  }

  // Add to history
  terminalHistory.push(cmd);
  historyIndex = terminalHistory.length;
  input.value = '';

  appendTerminalCmd(cmd);

  try {
    const result = await API.exec(activeSandboxId, cmd);
    const output = result.stdout || result.output || '';
    const stderr = result.stderr || '';
    if (output) appendTerminalResult(output);
    if (stderr) appendTerminalResult(stderr, true);
    if (!output && !stderr) appendTerminalResult('(no output)');
  } catch (err) {
    appendTerminalResult(`Error: ${err.message}`, true);
  }

  // Scroll to bottom
  const outputEl = document.getElementById('terminal-output');
  outputEl.scrollTop = outputEl.scrollHeight;
}

function appendTerminal(text, type = 'info') {
  const div = document.createElement('div');
  div.className = 'terminal-entry';
  div.innerHTML = `<span class="t-muted">── ${escapeHtml(text)}</span>`;
  document.getElementById('terminal-output').appendChild(div);
}

function appendTerminalCmd(cmd) {
  const div = document.createElement('div');
  div.className = 'terminal-entry';
  div.innerHTML = `<div class="terminal-cmd">${escapeHtml(cmd)}</div>`;
  document.getElementById('terminal-output').appendChild(div);
}

function appendTerminalResult(text, isError = false) {
  const div = document.createElement('div');
  div.className = `terminal-result ${isError ? 'terminal-error' : ''}`;
  div.textContent = text;
  const lastEntry = document.getElementById('terminal-output').lastElementChild;
  if (lastEntry) lastEntry.appendChild(div);
}

// Terminal keyboard shortcuts
document.addEventListener('keydown', (e) => {
  const input = document.getElementById('terminal-input');
  if (document.activeElement !== input) return;

  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (historyIndex > 0) {
      historyIndex--;
      input.value = terminalHistory[historyIndex];
    }
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (historyIndex < terminalHistory.length - 1) {
      historyIndex++;
      input.value = terminalHistory[historyIndex];
    } else {
      historyIndex = terminalHistory.length;
      input.value = '';
    }
  }
});

// ═══════════════════════════════════════
//  Settings
// ═══════════════════════════════════════

function refreshSettings() {
  // Settings are mostly static for now
  document.getElementById('setting-port').value = new URL(API_BASE).port || 9551;
}

// ═══════════════════════════════════════
//  Toast Notifications
// ═══════════════════════════════════════

function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.style.setProperty('--toast-duration', `${TOAST_DURATION}ms`);

  const icons = {
    success: '✓',
    error: '✕',
    info: 'ℹ',
  };
  el.innerHTML = `<span style="font-weight:700">${icons[type] || 'ℹ'}</span> ${escapeHtml(message)}`;
  container.appendChild(el);
  setTimeout(() => el.remove(), TOAST_DURATION + 400);
}

// ═══════════════════════════════════════
//  Utility Functions
// ═══════════════════════════════════════

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatUptime(seconds) {
  if (!seconds && seconds !== 0) return '-';
  const s = Math.floor(seconds);
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m ${s%60}s`;
  const h = Math.floor(s/3600);
  const m = Math.floor((s%3600)/60);
  return `${h}h ${m}m`;
}

function shortenPlatform(p) {
  if (!p) return '-';
  // "Linux-6.5.0-xxx" → "Linux 6.5"
  const m = p.match(/^(\w+)-(\d+\.\d+)/);
  return m ? `${m[1]} ${m[2]}` : p.split('-')[0];
}

function timeAgo(isoOrTs) {
  let ts;
  if (typeof isoOrTs === 'number') {
    ts = isoOrTs * 1000;  // Unix timestamp
  } else {
    ts = new Date(isoOrTs).getTime();
  }
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60)   return 'just now';
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}

// ═══════════════════════════════════════
//  Keyboard Shortcuts
// ═══════════════════════════════════════

document.addEventListener('keydown', (e) => {
  // Ctrl+K → focus terminal
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    navigate('terminal', document.querySelector('[data-page=terminal]'));
    document.getElementById('terminal-input').focus();
  }
  // Escape → close modal
  if (e.key === 'Escape') {
    hideCreateModal();
  }
  // Ctrl+N → new sandbox
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
    if (document.getElementById('create-modal').classList.contains('show')) return;
    e.preventDefault();
    showCreateModal();
  }
});

// ═══════════════════════════════════════
//  Boot
// ═══════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  startPolling();
  startLogPolling();  // Always poll logs in background
});
