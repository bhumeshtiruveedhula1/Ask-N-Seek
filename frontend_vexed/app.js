/* ════════════════════════════════════════════════════════════════
   GARUDA GAMANA  frontend_vexed/app.js
   Merges frontend/ features + preserves vexed galaxy + chat bot
   API_BASE → bridge_server.py on http://localhost:8000
   ════════════════════════════════════════════════════════════════ */

const API_BASE = 'http://localhost:8000';

// ═══════════════════════════════════════════════════════════════
// SHARED STATE
// ═══════════════════════════════════════════════════════════════
let state = {
  collection: null,
  currentCollection: null,
  results: [],
  currentResults: [],
  history: [],
  currentQuery: '',
  isUploading: false,
  _uploadStartTime: null,
  currentClipEnd: null,
  detectedClasses: {},
  _pollTimer: null,
};

// ═══════════════════════════════════════════════════════════════
// NAVIGATION  (vexed view switching)
// ═══════════════════════════════════════════════════════════════
const views = {
  'dashboard': ['chat-section'],
  'upload':    ['hero', 'upload-section'],
  'results':   ['top-objects-section', 'search-section', 'results-section'],
};

const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) entry.target.classList.add('visible');
  });
}, { threshold: 0.1 });

function switchView(targetView) {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.target === targetView);
  });

  Object.keys(views).forEach(viewName => {
    const isTarget = viewName === targetView;
    views[viewName].forEach(sectionId => {
      const el = document.getElementById(sectionId);
      if (!el) return;
      if (isTarget) {
        el.classList.remove('hidden');
        setTimeout(() => revealObserver.observe(el), 10);
      } else {
        el.classList.add('hidden');
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.target));
  });
  switchView('dashboard');
});

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// ═══════════════════════════════════════════════════════════════
// GALAXY PARTICLE SYSTEM  (vexed — fully preserved)
// ═══════════════════════════════════════════════════════════════
const canvas = document.getElementById('particle-canvas');
const ctx    = canvas.getContext('2d');
let particles = [];

function resize() {
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resize);
resize();

class Particle {
  constructor() {
    this.angle  = Math.random() * Math.PI * 2;
    const maxRadius = Math.max(canvas.width, canvas.height);
    this.radius = Math.pow(Math.random(), 2.5) * maxRadius;
    this.size   = Math.random() * 1.5 + 0.2;
    this.speed  = (Math.random() * 0.002 + 0.0005) * (200 / Math.max(this.radius, 50));
    const colors = ['#ffffff', '#f8f8ff', '#00e5ff', '#87cefa', '#4682b4'];
    this.color   = colors[Math.floor(Math.random() * colors.length)];
    this.opacity = Math.random() * 0.8 + 0.1;
  }
  update() {
    this.angle -= this.speed;
    this.x = canvas.width  / 2 + Math.cos(this.angle) * this.radius;
    this.y = canvas.height / 2 + Math.sin(this.angle) * (this.radius * 0.6);
  }
  draw() {
    ctx.fillStyle   = this.color;
    ctx.globalAlpha = this.opacity;
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1.0;
    ctx.shadowBlur  = this.size > 1.2 ? 8 : 0;
    ctx.shadowColor = this.color;
  }
}

for (let i = 0; i < 800; i++) particles.push(new Particle());

let animationFrameId = null;

function animateParticles() {
  ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  particles.forEach(p => { p.update(); p.draw(); });
  animationFrameId = requestAnimationFrame(animateParticles);
}
animateParticles();

function pauseParticles() {
  if (animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
}
function resumeParticles() {
  if (!animationFrameId) animateParticles();
}

// ═══════════════════════════════════════════════════════════════
// DROP ZONE SPOTLIGHT  (vexed — preserved)
// ═══════════════════════════════════════════════════════════════
const dropZoneEl = document.getElementById('uploadZone');
if (dropZoneEl) {
  dropZoneEl.addEventListener('mousemove', (e) => {
    const rect = dropZoneEl.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    dropZoneEl.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(255,255,255,0.08) 0%, transparent 50%)`;
  });
  dropZoneEl.addEventListener('mouseleave', () => {
    dropZoneEl.style.background = 'transparent';
  });
}

// ═══════════════════════════════════════════════════════════════
// BACKEND HEALTH + SCENARIO PRESETS  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
const SCENARIO_NEEDS = {
  safety_violation: ['person'],
  traffic_incident: ['car', 'person'],
  lost_item:        ['backpack'],
  access_control:   ['person'],
  crowd_check:      ['person'],
};

async function checkBackend() {
  const dot = document.getElementById('globalBridgeDot');
  const txt = document.getElementById('globalBridgeText');

  try {
    const res  = await fetch(API_BASE + '/health');
    const data = await res.json();

    const connected = data.backend_mode === 'connected';
    const color     = connected ? '#10b981' : '#fbbf24';
    const label     = connected ? 'Backend connected' : 'Mock mode — no real backend';

    dot.style.background = color;
    dot.style.boxShadow  = '0 0 6px ' + color;
    txt.textContent      = label;

    // Fetch scenario presets
    try {
      const sRes      = await fetch(API_BASE + '/scenarios');
      const scenarios = await sRes.json();
      const list      = Array.isArray(scenarios) ? scenarios : (scenarios.scenarios || []);
      if (list.length > 0) {
        renderPresets(list);
        document.getElementById('scenarioPresets').style.display = 'block';
      }
    } catch (_) { /* scenarios optional */ }

  } catch (_) {
    dot.style.background = '#ef4444';
    dot.style.boxShadow  = '0 0 6px #ef4444';
    txt.textContent      = 'Bridge offline — start: uvicorn bridge_server:app --port 8000';
  }
}

function renderPresets(scenarios) {
  const grid         = document.getElementById('presetsGrid');
  const videoUploaded = Object.keys(state.detectedClasses).length > 0;

  grid.innerHTML = scenarios.map(s => {
    const needs    = SCENARIO_NEEDS[s.id] || [];
    let   relevant = false;
    if (videoUploaded && needs.length > 0) {
      relevant = needs.every(cls => state.detectedClasses[cls]);
    }
    const dimmed    = videoUploaded && needs.length > 0 && !relevant;
    const extraClass = dimmed ? 'dimmed' : (relevant ? 'relevant' : '');
    return `<button class="scenario-btn ${extraClass}" id="preset-${s.id}" onclick="handlePresetClick(${JSON.stringify(s.query)})">
      ${s.label}<span class="preset-tooltip">${s.query}</span>
    </button>`;
  }).join('');
}

window.handlePresetClick = function(query) {
  const input = document.getElementById('queryInput');
  if (input) input.value = query;
  performSearch(query);
};

// ═══════════════════════════════════════════════════════════════
// QUICK CHIPS + DYNAMIC SUGGESTIONS  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function renderQuickChips(topClasses) {
  const chips = document.getElementById('quickChips');
  if (!chips || !topClasses || topClasses.length === 0) return;

  const top5 = topClasses.slice(0, 5);
  chips.innerHTML = top5.map(item => {
    const cls           = item.class || item.class_name || '';
    const maxConcurrent = item.max_concurrent != null ? item.max_concurrent : (item.count || 0);
    const framesDetected = item.frames_detected != null ? item.frames_detected : (item.count || 0);
    const tooltip       = maxConcurrent === 1
      ? `Seen in ${framesDetected} frame${framesDetected !== 1 ? 's' : ''}, 1 at a time`
      : `Up to ${maxConcurrent} visible at once · across ${framesDetected} frame${framesDetected !== 1 ? 's' : ''}`;
    return `<button class="quick-chip" onclick="performSearch(${JSON.stringify(cls)})" title="${tooltip}">
      ${cls}<span class="quick-chip-count">· ${maxConcurrent}</span>
    </button>`;
  }).join('');
  chips.style.display = 'flex';
}

function generateSuggestions(topClasses) {
  const container = document.getElementById('suggestions-container');
  const row       = document.getElementById('dynamic-suggestions');
  if (!row || !container) return;

  const detected = new Set((topClasses || []).map(i => i.class || i.class_name || ''));
  const chips    = [];

  if (detected.has('person'))                           chips.push('person without helmet');
  if (detected.has('person'))                           chips.push('more than two people');
  if (detected.has('car'))                              chips.push('car left of person');
  if (detected.has('backpack') || detected.has('handbag')) chips.push('backpack without owner');
  chips.push('purple elephant');

  const final = chips.slice(0, 6);
  if (final.length === 0) { container.style.display = 'none'; return; }

  row.innerHTML       = final.map(q => `<button class="suggestion-chip" data-query="${q}">${q}</button>`).join('');
  container.style.display = 'block';
}

// ═══════════════════════════════════════════════════════════════
// TOP OBJECTS + INGEST STATS  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function renderTopObjects(topClasses) {
  const grid    = document.getElementById('topObjectsGrid');
  const section = document.getElementById('topObjectsSection');
  if (!grid || !topClasses || topClasses.length === 0) return;

  state.detectedClasses = {};
  topClasses.forEach(item => {
    const cls = item.class || item.class_name || '';
    state.detectedClasses[cls] = item.count || 0;
  });

  grid.innerHTML = topClasses.map(item => {
    const cls            = item.class || item.class_name || '';
    const framesDetected = item.frames_detected != null ? item.frames_detected : (item.count || 0);
    const maxConcurrent  = item.max_concurrent  != null ? item.max_concurrent  : 1;
    const tooltip        = maxConcurrent === 1 && framesDetected > 1
      ? `1 object seen across ${framesDetected} frames`
      : `Max ${maxConcurrent} at once, detected in ${framesDetected} frames`;
    return `<div class="top-object-card" title="${tooltip}">
      <span class="top-object-name">${cls}</span>
      <span class="top-object-sub">detected in ${framesDetected} frame${framesDetected !== 1 ? 's' : ''}</span>
      <span class="top-object-badge">max ${maxConcurrent} at once</span>
    </div>`;
  }).join('');

  section.style.display = 'block';
}

function renderIngestStats(stats) {
  const el = document.getElementById('ingestStats');
  if (!el || !stats) return;
  const scenes    = stats.scenes    || stats.scene_count    || 0;
  const keyframes = stats.frames    || stats.keyframes       || stats.frame_count || 0;
  const objects   = stats.total_objects || stats.objects    || stats.object_count || 0;
  el.innerHTML = `
    <div class="stat-col"><div class="stat-label">Scenes</div><div class="stat-value">${scenes}</div></div>
    <div class="stat-col"><div class="stat-label">Keyframes</div><div class="stat-value">${keyframes}</div></div>
    <div class="stat-col"><div class="stat-label">Objects</div><div class="stat-value">${objects}</div></div>`;
  el.style.display = 'grid';
}

// ═══════════════════════════════════════════════════════════════
// FORMAT HELPERS
// ═══════════════════════════════════════════════════════════════
function formatElapsedSecs(secs) {
  const t = Math.floor(secs);
  const m = Math.floor(t / 60);
  const s = t % 60;
  return m + ':' + (s < 10 ? '0' : '') + s;
}

function formatTime(s) {
  const m   = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
}

// ═══════════════════════════════════════════════════════════════
// UPLOAD + 6-PHASE INGESTION  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function initUpload() {
  const zone      = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileInput');
  const browseBtn = document.querySelector('.browse-btn');

  if (!zone) return;

  zone.addEventListener('dragover',  (e) => { e.preventDefault(); zone.style.borderColor = 'rgba(255,255,255,0.5)'; });
  zone.addEventListener('dragleave', ()  => { zone.style.borderColor = ''; });
  zone.addEventListener('drop',      (e) => {
    e.preventDefault();
    zone.style.borderColor = '';
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('video/')) handleUpload(file);
  });

  zone.addEventListener('click', () => { if (!state.isUploading) fileInput.click(); });

  if (browseBtn) {
    browseBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
  }

  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleUpload(file);
  });
}

async function handleUpload(file) {
  state.isUploading      = true;
  state._uploadStartTime = Date.now();

  const ingestStatus = document.getElementById('ingest-status');
  const progressFill = document.getElementById('progressFill');
  const progressLog  = document.getElementById('progressLog');
  const metaBar      = document.getElementById('ingestMetaBar');
  const topSection   = document.getElementById('topObjectsSection');
  const topGrid      = document.getElementById('topObjectsGrid');
  const badge        = document.getElementById('collectionBadge');
  const ingestStats  = document.getElementById('ingestStats');

  // Show ingest UI
  if (ingestStatus) ingestStatus.classList.remove('hidden');

  // Reset
  if (progressFill) progressFill.style.width = '0%';
  if (progressLog)  progressLog.innerHTML    = '';
  if (metaBar)      metaBar.style.display    = 'flex';
  if (topSection)   topSection.style.display = 'none';
  if (topGrid)      topGrid.innerHTML        = '';
  if (badge)        badge.style.display      = 'none';
  if (ingestStats)  ingestStats.style.display = 'none';

  const pctEl   = document.getElementById('ingestPct');
  const phaseEl = document.getElementById('ingestPhaseLabel');
  const elapsed = document.getElementById('ingestElapsed');
  if (pctEl)   pctEl.textContent   = '0%';
  if (phaseEl) phaseEl.textContent = 'Queued';
  if (elapsed) elapsed.textContent = 'Elapsed: 0:00';

  addProgressLog('Upload started: ' + file.name, 'qlog-info');
  pauseParticles();

  const formData = new FormData();
  formData.append('video', file);

  let jobId = null;
  try {
    const res  = await fetch(API_BASE + '/ingest/start', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) {
      addProgressLog('Error: ' + data.error, 'qlog-fail');
      state.isUploading = false;
      resumeParticles();
      return;
    }
    jobId = data.job_id;
    addProgressLog('Job started: ' + jobId, 'qlog-info');
  } catch (e) {
    addProgressLog('Upload failed: ' + e.message, 'qlog-fail');
    state.isUploading = false;
    resumeParticles();
    return;
  }

  if (jobId) pollIngestionStatus(jobId);
}

function pollIngestionStatus(jobId) {
  if (state._pollTimer) clearInterval(state._pollTimer);

  state._pollTimer = setInterval(async () => {
    try {
      const res  = await fetch(API_BASE + '/ingest/status/' + jobId);
      const data = await res.json();

      if (data.error) {
        clearInterval(state._pollTimer);
        addProgressLog('Poll error: ' + data.error, 'qlog-fail');
        state.isUploading = false;
        resumeParticles();
        return;
      }

      const pct     = data.progress || data.progress_pct || 0;
      const phase   = data.phase    || 'queued';
      const elapsedS = data.elapsed_seconds || 0;
      const msg     = data.message || '';

      const pctEl    = document.getElementById('progressFill');
      const pctLabel = document.getElementById('ingestPct');
      const phaseLabel = document.getElementById('ingestPhaseLabel');
      const elapsedEl  = document.getElementById('ingestElapsed');

      if (pctEl)      pctEl.style.width        = pct + '%';
      if (pctLabel)   pctLabel.textContent      = pct + '%';
      if (phaseLabel) phaseLabel.textContent    = phase.replace(/_/g, ' ');
      if (elapsedEl)  elapsedEl.textContent     = 'Elapsed: ' + formatElapsedSecs(elapsedS);

      updatePhaseIndicators(phase);

      if (msg) {
        const logClass = data.status === 'error' ? 'qlog-fail'
          : (phase === 'complete' ? 'qlog-pass'
          : (pct < 30 ? 'qlog-info' : (pct < 80 ? 'qlog-warn' : 'qlog-info')));
        addProgressLog(msg, logClass);
      }

      // COMPLETE
      if (data.status === 'complete' || phase === 'complete') {
        clearInterval(state._pollTimer);
        state.isUploading = false;
        resumeParticles();

        const collName = data.collection_name || data.collection || '';
        state.currentCollection = collName;
        state.collection        = collName;

        addProgressLog('Ingestion complete!', 'qlog-pass');
        const pf = document.getElementById('progressFill');
        if (pf) pf.style.width = '100%';
        if (pctLabel) pctLabel.textContent = '100%';

        // Collection badge
        const badge   = document.getElementById('collectionBadge');
        const nameEl  = document.getElementById('collectionName');
        if (badge && nameEl) {
          nameEl.textContent  = collName || 'session_collection';
          badge.style.display = 'flex';
        }

        // Top objects + chips + suggestions
        const topClasses = data.top_classes || [];
        if (topClasses.length > 0) {
          renderTopObjects(topClasses);
          renderQuickChips(topClasses);
          generateSuggestions(topClasses);
        }
        renderIngestStats(data.stats);

        // Update preset relevance
        try {
          const sRes      = await fetch(API_BASE + '/scenarios');
          const scenarios = await sRes.json();
          const list      = Array.isArray(scenarios) ? scenarios : (scenarios.scenarios || []);
          if (list.length > 0) renderPresets(list);
        } catch (_) {}

        // Switch to results view and reveal search
        switchView('results');
        const searchSec = document.getElementById('search-section');
        if (searchSec) searchSec.scrollIntoView({ behavior: 'smooth' });
      }

      // ERROR
      if (data.status === 'error') {
        clearInterval(state._pollTimer);
        state.isUploading = false;
        resumeParticles();
        addProgressLog('Ingestion error: ' + msg, 'qlog-fail');
      }

    } catch (e) {
      addProgressLog('Network: ' + e.message, 'qlog-warn');
    }
  }, 800);
}

function addProgressLog(msg, cls) {
  const log = document.getElementById('progressLog');
  if (!log) return;
  const div = document.createElement('div');
  div.className   = cls || '';
  div.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function updatePhaseIndicators(currentPhase) {
  const PHASE_ORDER = ['queued','starting','scene_detection','keyframe','yolo','color','spatial','qdrant','complete'];
  const currentIdx  = PHASE_ORDER.indexOf(currentPhase);

  document.querySelectorAll('.phase').forEach((phaseEl, idx) => {
    phaseEl.classList.remove('active', 'complete');
    if (idx < currentIdx) phaseEl.classList.add('complete');
    if (idx === currentIdx) phaseEl.classList.add('active');
  });
}

// ═══════════════════════════════════════════════════════════════
// SEARCH + VOCAB CHECK  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function initSearch() {
  const input = document.getElementById('queryInput');
  const btn   = document.getElementById('searchBtn');

  if (!input) return;

  // Static preset buttons (fallback when /scenarios unavailable)
  document.querySelectorAll('#staticPresets .preset-btn').forEach(b => {
    b.addEventListener('click', () => {
      input.value = b.dataset.query;
      performSearch(b.dataset.query);
    });
  });

  // Dynamic suggestion chips
  document.getElementById('dynamic-suggestions')?.addEventListener('click', (e) => {
    const chip = e.target.closest('.suggestion-chip');
    if (chip) { input.value = chip.dataset.query; performSearch(chip.dataset.query); }
  });

  btn.addEventListener('click', () => {
    const q = input.value.trim();
    if (q) performSearch(q);
  });

  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && input.value.trim()) performSearch(input.value.trim());
  });
}

async function performSearch(query, skipHistory) {
  query = (query || '').trim();
  if (!query) return;

  state.currentQuery = query;
  const input      = document.getElementById('queryInput');
  const btn        = document.getElementById('searchBtn');
  const warningsEl = document.getElementById('vocabWarnings');

  if (input) input.value = query;

  // Spinner
  if (btn) btn.textContent = '...';

  // Vocab check
  try {
    const fd = new FormData();
    fd.append('query', query);
    const vRes     = await fetch(API_BASE + '/vocab/check', { method: 'POST', body: fd });
    const warnings = await vRes.json();
    if (warnings && warnings.length > 0) {
      warningsEl.innerHTML = warnings.map(w => {
        if (w.type === 'suggestion' && w.suggestion) {
          return `<p>&#9888;&#65039; "${w.token}" not in vocabulary. Did you mean: "${w.suggestion}"?</p>`;
        }
        return `<p>&#10060; "${w.token}" — unknown token</p>`;
      }).join('');
      warningsEl.classList.add('active');
    } else {
      warningsEl.classList.remove('active');
      warningsEl.innerHTML = '';
    }
  } catch (_) {
    warningsEl.classList.remove('active');
  }

  // Query
  try {
    const collection = state.currentCollection || state.collection || null;
    const body       = { query };
    if (collection) body.collection_name = collection;

    const res  = await fetch(API_BASE + '/query', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    const data = await res.json();

    const results         = data.results || [];
    state.currentResults  = results;
    state.results         = results;

    renderResults(data);

    if (!skipHistory) {
      const topScore = results.length > 0 ? (results[0].confidence_score || results[0].confidence || 0) : 0;
      addToHistory(query, results.length, topScore);
    }

    const resultsSec = document.getElementById('results-section');
    if (resultsSec) resultsSec.scrollIntoView({ behavior: 'smooth' });

  } catch (e) {
    renderResults({ results: [], diagnosis: { html: `<p style="color:#f87171;">Search failed: ${e.message}. Is bridge_server running on port 8000?</p>` } });
    if (warningsEl) {
      warningsEl.innerHTML = `<p style="color:#f87171;">Connection error: ${e.message}</p>`;
      warningsEl.classList.add('active');
    }
  }

  if (btn) btn.textContent = 'Search';
}

// ═══════════════════════════════════════════════════════════════
// RENDER RESULTS  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function renderResults(data) {
  const results    = data.results  || [];
  const parsed     = data.parsed   || null;
  const diagnosis  = data.diagnosis || null;

  const header     = document.getElementById('resultsHeader');
  const countEl    = document.getElementById('resultsCount');
  const queryEl    = document.getElementById('resultsQuery');
  const grid       = document.getElementById('resultsGrid');
  const diagPanel  = document.getElementById('diagnosisPanel');
  const videoArea  = document.getElementById('videoPlayerArea');
  const jumpSec    = document.getElementById('jumpListSection');

  if (header) header.style.display = 'block';
  if (countEl) countEl.textContent = data.status === 'no_data'
    ? 'Upload a video first'
    : (results.length + ' Result' + (results.length !== 1 ? 's' : ''));
  if (queryEl) queryEl.textContent = 'for "' + state.currentQuery + '"';

  // No video yet
  if (data.status === 'no_data') {
    if (grid) grid.innerHTML = `
      <div class="no-video-placeholder">
        <div style="font-size:48px;">&#128249;</div>
        <h3>No Video Uploaded Yet</h3>
        <p>Upload a video using the Upload tab to start searching.</p>
      </div>`;
    if (diagPanel) diagPanel.style.display = 'none';
    if (videoArea) videoArea.style.display = 'none';
    if (jumpSec)   jumpSec.style.display   = 'none';
    return;
  }

  if (results.length === 0) {
    if (grid) grid.innerHTML = '';
    if (diagnosis) {
      renderDiagnosis(diagnosis);
    } else {
      if (diagPanel) {
        diagPanel.style.display = 'block';
        diagPanel.innerHTML     = '<h3>No Confident Match</h3><p>No results matched your query constraints.</p>';
      }
    }
    if (videoArea) videoArea.style.display = 'none';
    if (jumpSec)   jumpSec.style.display   = 'none';
    return;
  }

  if (diagPanel) diagPanel.style.display = 'none';
  if (videoArea) videoArea.style.display = 'block';

  if (grid) {
    grid.innerHTML = results.map((r, i) => {
      const score      = r.confidence_score || r.confidence || 0;
      const confClass  = score >= 0.75 ? 'high' : score >= 0.5 ? 'medium' : 'low';
      const confLabel  = score >= 0.75 ? 'HIGH' : score >= 0.5 ? 'MED' : 'LOW';
      const ts         = typeof r.timestamp === 'number' ? r.timestamp : 0;
      const sb         = r.score_breakdown || null;

      return `<div class="result-card" onclick="playResult(${i})" style="opacity:0;animation:fade-in 0.5s ease ${i * 0.1}s forwards">
        <div class="ts-visual" onclick="playResult(${i})">
          <div class="ts-time">${ts.toFixed(1)}s</div>
          <div class="ts-label">Timestamp</div>
          <div class="ts-scene">Scene ${r.scene_id || i + 1}</div>
          <div class="ts-click-hint">Click to play</div>
        </div>
        <div class="result-card-body">
          <div class="result-card-header">
            <span class="result-video-id">${r.video_id || 'unknown'}</span>
            <span class="result-confidence ${confClass}">${confLabel} ${score.toFixed(2)}</span>
          </div>
          <p class="result-explanation">${r.explanation || ''}</p>
          ${sb ? renderScoreBars(sb, parsed) : ''}
        </div>
      </div>`;
    }).join('');
  }

  // Populate result picker dropdown
  const picker = document.getElementById('resultPicker');
  if (picker) {
    picker.innerHTML = '<option value="">Jump to result...</option>' +
      results.map((r, i) => {
        const ts    = typeof r.timestamp === 'number' ? r.timestamp : 0;
        const score = r.confidence_score || r.confidence || 0;
        return `<option value="${i}">${r.video_id || 'result'} @ ${ts.toFixed(1)}s [${score.toFixed(2)}]</option>`;
      }).join('');
  }

  renderJumpList();
}

// ═══════════════════════════════════════════════════════════════
// SCORE BREAKDOWN BARS  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function renderScoreBars(sb, parsed) {
  const filters = (parsed && parsed.filters) ? parsed.filters : null;

  function getMicroLabel(category) {
    if (!filters) return '';
    if (category === 'color') {
      return filters.color != null ? `color: ${filters.color}` : 'No color filter';
    }
    if (category === 'spatial') {
      if (filters.spatial_relation == null) return 'No spatial constraint';
      const sr = filters.spatial_relation;
      return `${sr.type || 'near'}: ${sr.target_class || '?'}`;
    }
    if (category === 'negation') {
      if (!filters.negated || !filters.negated.length) return 'No negation constraint';
      return `\u00ac ${filters.negated.join(', ')}`;
    }
    if (category === 'object') {
      return filters.class ? `class: ${filters.class}` : '';
    }
    return '';
  }

  const bars = [
    { label: 'Object',   score: sb.object_score   || 0, max: 40, category: 'object' },
    { label: 'Color',    score: sb.color_score     || 0, max: 20, category: 'color' },
    { label: 'Spatial',  score: sb.spatial_score   || 0, max: 20, category: 'spatial' },
    { label: 'Negation', score: sb.negation_score  || 0, max: 20, category: 'negation' },
  ];
  const total   = sb.total || 0;
  const details = sb.details || {};

  let html = '<div class="score-bars">';
  bars.forEach(b => {
    const pct      = Math.min(100, Math.round((b.score / b.max) * 100));
    const note     = getMicroLabel(b.category);
    const barColor = b.score > 0 ? '#00e5ff' : 'rgba(255,255,255,0.12)';
    const txtColor = b.score > 0 ? 'var(--accent-color)' : 'rgba(248,248,255,0.3)';
    const detail   = (details[b.category] || '').replace(/"/g, '&quot;');
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;" title="${detail}">
      <span style="font-family:var(--font-mono);font-size:0.6rem;color:rgba(248,248,255,0.4);min-width:52px;">${b.label}</span>
      <div style="flex:1;height:3px;background:rgba(255,255,255,0.06);">
        <div style="height:100%;width:${pct}%;background:${barColor};transition:width 0.8s ease;"></div>
      </div>
      <span style="font-family:var(--font-mono);font-size:0.6rem;color:${txtColor};min-width:20px;text-align:right;">${b.score}</span>
      ${note ? `<span style="font-size:0.55rem;color:rgba(248,248,255,0.35);min-width:80px;">${note}</span>` : '<span style="min-width:80px;"></span>'}
    </div>`;
  });
  html += `<div style="display:flex;align-items:center;gap:8px;margin-top:4px;border-top:1px solid rgba(255,255,255,0.04);padding-top:6px;">
    <span style="font-family:var(--font-mono);font-size:0.6rem;color:var(--accent-color);min-width:52px;">Total</span>
    <div style="flex:1;height:3px;background:rgba(255,255,255,0.06);">
      <div style="height:100%;width:${Math.min(100,total)}%;background:var(--accent-color);transition:width 0.8s ease;"></div>
    </div>
    <span style="font-family:var(--font-mono);font-size:0.65rem;color:var(--accent-color);font-weight:500;min-width:20px;text-align:right;">${total}</span>
  </div>`;
  html += '</div>';
  return html;
}

// ═══════════════════════════════════════════════════════════════
// JUMP LIST  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function renderJumpList() {
  const section = document.getElementById('jumpListSection');
  const list    = document.getElementById('resultJumpList');
  if (!section || !list) return;

  const results = state.currentResults;
  if (!results || results.length === 0) { section.style.display = 'none'; return; }

  section.style.display = 'block';
  list.innerHTML = results.map((r, i) => {
    const ts    = typeof r.timestamp === 'number' ? r.timestamp : 0;
    const score = r.confidence_score || r.confidence || 0;
    const total = (r.score_breakdown && r.score_breakdown.total) || 0;
    return `<div class="result-jump-item" id="jump-item-${i}" onclick="playResult(${i})">
      <span class="jump-index">${i + 1}</span>
      <span class="jump-vid">${r.video_id || 'result'}</span>
      <span class="jump-ts">${ts.toFixed(1)}s</span>
      <span class="jump-score">${total ? 'score ' + total : score.toFixed(2)}</span>
    </div>`;
  }).join('');
}

// ═══════════════════════════════════════════════════════════════
// DIAGNOSIS PANEL  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function renderDiagnosis(diagnosis) {
  const panel = document.getElementById('diagnosisPanel');
  if (!panel) return;
  panel.style.display = 'block';
  if (diagnosis && diagnosis.html) {
    panel.innerHTML = `<h3>No Confident Match</h3><div style="margin-top:12px;">${diagnosis.html}</div>`;
  } else {
    panel.innerHTML = `<h3>No Confident Match</h3>
      <p>We found related objects, but nothing matched all constraints together.</p>
      <p style="margin-top:10px;font-size:0.8rem;"><strong>Tip:</strong> Try removing one constraint at a time — search for just the object class first.</p>`;
  }
}

// ═══════════════════════════════════════════════════════════════
// VIDEO PLAYER + CLIP CONTROLS  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function initVideoPlayer() {
  const picker      = document.getElementById('resultPicker');
  const video       = document.getElementById('mainVideo');
  const timeEl      = document.getElementById('playerTime');
  const playClipBtn = document.getElementById('playClipBtn');

  if (!video) return;

  if (picker) {
    picker.addEventListener('change', (e) => {
      const idx = parseInt(e.target.value);
      if (!isNaN(idx) && state.currentResults[idx]) playResult(idx);
    });
  }

  video.addEventListener('timeupdate', () => {
    if (timeEl) {
      const mins = Math.floor(video.currentTime / 60);
      const secs = Math.floor(video.currentTime % 60);
      const ms   = Math.floor((video.currentTime % 1) * 100);
      timeEl.textContent = String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0') + '.' + String(ms).padStart(2,'0');
    }
    if (state.currentClipEnd !== null && video.currentTime >= state.currentClipEnd) {
      video.pause();
    }
  });

  if (playClipBtn) playClipBtn.addEventListener('click', replayClip);
}

window.playResult = function(idx) {
  const video        = document.getElementById('mainVideo');
  const picker       = document.getElementById('resultPicker');
  const clipControls = document.getElementById('clipControls');
  const clipInfo     = document.getElementById('clipInfo');
  const result       = state.currentResults[idx];

  if (!result || !video) return;

  const ts       = typeof result.timestamp === 'number' ? result.timestamp : 0;
  const clipStart = Math.max(0, ts - 3);
  const clipEnd   = ts + 3;
  state.currentClipEnd = clipEnd;

  const videoId = result.video_id || '';
  const src     = `${API_BASE}/video/${videoId}?t=${Date.now()}`;

  if (video.src !== src) video.src = src;

  video.addEventListener('loadedmetadata', function onMeta() {
    video.removeEventListener('loadedmetadata', onMeta);
    video.currentTime = clipStart;
    video.play().catch(() => {});
  }, { once: true });

  if (video.readyState >= 1) {
    video.currentTime = clipStart;
    video.play().catch(() => {});
  }

  if (clipControls) clipControls.style.display = 'flex';
  if (clipInfo)     clipInfo.textContent        = ts.toFixed(1) + 's (\u22123s to +3s)';
  if (picker)       picker.value                = String(idx);

  document.querySelectorAll('.result-jump-item').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });

  const videoArea = document.getElementById('videoPlayerArea');
  if (videoArea) videoArea.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

function replayClip() {
  const video = document.getElementById('mainVideo');
  if (!video || state.currentClipEnd === null) return;
  video.currentTime = Math.max(0, state.currentClipEnd - 6);
  video.play().catch(() => {});
}

// seekToTimestamp — mirrors results-bar playResult() logic.
// videoId: the result's own video_id (preferred over state.currentCollection).
function seekToTimestamp(start, end, videoId) {
  const video     = document.getElementById('mainVideo');
  const videoArea = document.getElementById('videoPlayerArea');
  if (!video) return;

  if (videoArea) videoArea.style.display = 'block';

  const vidToUse = videoId || state.currentCollection || '';
  if (vidToUse) {
    const src = `${API_BASE}/video/${vidToUse}?t=${Date.now()}`;
    if (video.src.split('?')[0] !== src.split('?')[0] || !video.src) {
      video.src = src;
      video.addEventListener('loadedmetadata', function onMeta() {
        video.removeEventListener('loadedmetadata', onMeta);
        video.currentTime = start;
        if (end !== undefined && end !== null) state.currentClipEnd = end + 1;
        setTimeout(() => {
          video.play().catch(() => { video.muted = true; video.play().catch(() => {}); });
        }, 100);
      }, { once: true });
      video.load();
      video.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
  }

  // Source already correct — seek directly
  const doSeek = () => {
    video.currentTime = start;
    if (end !== undefined && end !== null) state.currentClipEnd = end + 1;
    setTimeout(() => {
      video.play().catch(() => { video.muted = true; video.play().catch(() => {}); });
    }, 100);
    video.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  if (video.readyState >= 1) {
    doSeek();
  } else {
    video.addEventListener('loadedmetadata', function onMeta2() {
      video.removeEventListener('loadedmetadata', onMeta2);
      doSeek();
    }, { once: true });
    if (video.src) video.load();
  }
}

// ═══════════════════════════════════════════════════════════════
// SESSION HISTORY SIDEBAR  (ported from frontend/)
// ═══════════════════════════════════════════════════════════════
function initHistory() {
  const sidebar = document.getElementById('historySidebar');
  const toggle  = document.getElementById('historyToggle');
  const close   = document.getElementById('closeHistory');

  if (!sidebar || !toggle || !close) return;

  toggle.addEventListener('click', () => sidebar.classList.add('open'));
  close.addEventListener('click',  () => sidebar.classList.remove('open'));

  document.addEventListener('click', (e) => {
    if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });
}

function addToHistory(query, count, topScore) {
  state.history.unshift({ query, count, time: new Date().toLocaleTimeString(), topScore: topScore || 0 });
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById('historyList');
  if (!list) return;
  list.innerHTML = state.history.map(h => {
    const safeQ = h.query.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    return `<div class="history-item" onclick="replayQuery('${safeQ}')">
      <div class="history-item-query">${h.query}</div>
      <div class="history-item-meta">
        <span>${h.time}</span>
        <span>${h.count} results</span>
        <span>score: ${h.topScore.toFixed(2)}</span>
      </div>
    </div>`;
  }).join('');
}

window.replayQuery = function(query) {
  const input = document.getElementById('queryInput');
  if (input) input.value = query;
  document.getElementById('historySidebar')?.classList.remove('open');
  performSearch(query, true);
};

// ═══════════════════════════════════════════════════════════════
// CHAT PANEL  (vexed — FULLY PRESERVED, untouched)
// ═══════════════════════════════════════════════════════════════
const chatInput    = document.getElementById('chat-input');
const chatSendBtn  = document.getElementById('chat-send-btn');
const chatMessages = document.getElementById('chat-messages');
const chatTyping   = document.getElementById('chat-typing');

if (chatSendBtn) {
  chatSendBtn.addEventListener('click', () => {
    const text = chatInput.value.trim();
    if (text) sendChatMessage(text);
  });
}

if (chatInput) {
  chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      const text = chatInput.value.trim();
      if (text) sendChatMessage(text);
    }
  });
}

function appendBubble(type, content) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${type}-bubble`;

  const avatar = document.createElement('div');
  avatar.className = 'bubble-avatar';
  avatar.textContent = type === 'ai' ? '✧' : '◆';

  const contentDiv = document.createElement('div');
  contentDiv.className = 'bubble-content';

  if (typeof content === 'string') {
    const p = document.createElement('p');
    p.textContent = content;
    contentDiv.appendChild(p);
  } else {
    contentDiv.appendChild(content);
  }

  bubble.appendChild(avatar);
  bubble.appendChild(contentDiv);
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return contentDiv;
}

function showTyping() {
  chatTyping.classList.remove('hidden');
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTyping() {
  chatTyping.classList.add('hidden');
}

async function sendChatMessage(text, displayText = null) {
  // displayText: optional text to show in the user bubble.
  // If omitted, the raw `text` is shown. This lets clarification buttons
  // send structured payloads ("color: Red") while showing clean labels ("Red").

  appendBubble('user', displayText || text);
  chatInput.value = '';
  showTyping();

  try {
    const res  = await fetch(API_BASE + '/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      // display_text: what the user sees (e.g. "Red"), used in XAI heading
      // text: the actual payload (may be structured: "color: Red")
      body: JSON.stringify({
        text:         text,
        video_id:     state.currentCollection || '',
        display_text: displayText || null,
      }),
    });
    const data = await res.json();
    hideTyping();

    // ── Build reply fragment ──────────────────────────────────────────
    const fragment = document.createDocumentFragment();

    // ── 1. Main reply text (pre-formatted with newlines) ─────────────
    if (data.reply) {
      const pre = document.createElement('pre');
      pre.className   = 'chat-reply-pre';
      pre.textContent = data.reply;
      fragment.appendChild(pre);
    }

    // ── 2. Language tag (non-English responses) ───────────────────────
    if (data.language_detected && data.language_detected !== 'en') {
      const langNames = { hi: 'Hindi', kn: 'Kannada', ta: 'Tamil', te: 'Telugu', ml: 'Malayalam' };
      const langTag   = document.createElement('div');
      langTag.className   = 'bubble-lang-tag';
      langTag.textContent = `Detected: ${langNames[data.language_detected] || data.language_detected}`;
      fragment.appendChild(langTag);
    }

    // ── 3. STRUCTURED CLARIFICATION CARD (Prompt 1: Interactive Refinement) ──
    if (data.clarification_type === 'structured' && data.questions && data.questions.length > 0) {
      const card = document.createElement('div');
      card.className = 'clarification-card';

      data.questions.forEach(q => {
        const row = document.createElement('div');
        row.className = 'clarification-row';

        const label = document.createElement('span');
        label.className   = 'clarification-question-label';
        label.textContent = q.label;
        row.appendChild(label);

        const btnGroup = document.createElement('div');
        btnGroup.className = 'clarif-btn-group';

        q.options.forEach(opt => {
          const btn = document.createElement('button');
          btn.className   = 'clarif-option-btn';
          btn.textContent = opt;

          btn.addEventListener('click', () => {
            // Disable all buttons in this card (prevent double submit)
            card.querySelectorAll('.clarif-option-btn').forEach(b => {
              b.disabled = true;
              b.style.opacity = '0.45';
            });
            btn.style.opacity    = '1';
            btn.style.background = 'var(--accent)';
            btn.style.color      = '#000';

            // API payload = "color: Red" | "spatial: Yes — near person" etc.
            // Display text = just the option label ("Red", "Any color", "Skip")
            // This keeps the chat bubble clean and human-readable.
            const apiMsg     = `${q.id}: ${opt}`;
            const displayMsg = (opt === 'Skip') ? `Skipped: ${q.label}` : opt;
            sendChatMessage(apiMsg, displayMsg);
          });

          btnGroup.appendChild(btn);
        });

        row.appendChild(btnGroup);
        card.appendChild(row);
      });

      fragment.appendChild(card);
    }

    // ── 4. Result timestamp chips ─────────────────────────────────────
    if (data.results && data.results.length > 0) {
      const strip   = document.createElement('div');
      strip.className = 'chat-result-strip';
      const maxChips  = 8;

      // Sync active video from result's video_id (same logic as results-bar flow)
      if (data.results[0].video_id) {
        state.currentCollection = data.results[0].video_id;
      }

      data.results.slice(0, maxChips).forEach(r => {
        const start   = r.start  !== undefined ? r.start  : (r.window !== undefined ? r.window : r.timestamp);
        const end     = r.end    !== undefined ? r.end    : (start + 6);
        const vidId   = r.video_id || state.currentCollection || '';

        const chip  = document.createElement('span');
        chip.className = 'chat-result-chip';
        chip.innerHTML = `<span class="chip-icon">&#9654;</span> ${formatTime(start)}`;
        chip.title     = r.explanation || `Jump to ${formatTime(start)}`;

        chip.addEventListener('click', (e) => {
          e.stopPropagation();
          // Mirror exact same flow as results-bar: set collection, switch view, then seek
          if (vidId) state.currentCollection = vidId;
          switchView('results');
          // 250ms gives switchView time to unhide #mainVideo before seekToTimestamp fires
          setTimeout(() => seekToTimestamp(start, end, vidId), 250);
        });
        strip.appendChild(chip);
      });

      if (data.results.length > maxChips) {
        const more = document.createElement('span');
        more.className   = 'chat-result-chip';
        more.textContent = `+${data.results.length - maxChips} more`;
        more.style.cursor  = 'default';
        more.style.opacity = '0.5';
        strip.appendChild(more);
      }

      fragment.appendChild(strip);

      // ── Auto-play: seek to BEST result (mirrors results-bar playResult(0)) ──
      const best      = data.results[0];
      const bestStart = best.start  !== undefined ? best.start
                      : best.window !== undefined ? best.window
                      : best.timestamp;
      const bestEnd   = best.end !== undefined ? best.end : (bestStart + 6);
      const bestVidId = best.video_id || state.currentCollection || '';
      if (bestVidId) state.currentCollection = bestVidId;
      setTimeout(() => {
        switchView('results');
        seekToTimestamp(bestStart, bestEnd, bestVidId);
      }, 350);
    }

    appendBubble('ai', fragment);

    // ── 5. PROGRESSIVE FILTER BAR update (Prompt 2) ──────────────────
    if (data.filters_used) {
      updateActiveFiltersBar(data.filters_used);
    }

  } catch (err) {
    hideTyping();
    appendBubble('ai', `Connection error: ${err.message}. Is the backend running on port 8000?`);
  }
}

// ═══════════════════════════════════════════════════════════════
// PROGRESSIVE FILTER CHIPS BAR  (Prompt 2: Progressive Filtering)
// ═══════════════════════════════════════════════════════════════
function updateActiveFiltersBar(filtersUsed) {
  const bar   = document.getElementById('active-filters-bar');
  const chips = document.getElementById('active-filter-chips');
  if (!bar || !chips) return;

  chips.innerHTML = '';

  const defs = [
    { key: 'class',            emoji: '🏷',  label: 'Object',   color: 'chip-green'  },
    { key: 'color',            emoji: '🎨',  label: 'Color',    color: 'chip-blue'   },
    { key: 'spatial_relation', emoji: '📍',  label: 'Spatial',  color: 'chip-purple' },
    { key: 'negated',          emoji: '❌',  label: 'Excluded', color: 'chip-red'    },
    { key: 'temporal_direction',emoji:'⏱',  label: 'Time',     color: 'chip-yellow' },
  ];

  let hasAny = false;
  defs.forEach(({ key, emoji, label, color }) => {
    const val = filtersUsed[key];
    if (!val || (Array.isArray(val) && val.length === 0)) return;

    hasAny = true;
    const chip = document.createElement('span');
    chip.className = `filter-chip ${color}`;

    if (key === 'negated') {
      chip.textContent = `${emoji} ${label}: ${val.join(', ')}`;
    } else if (key === 'spatial_relation' && typeof val === 'object') {
      chip.textContent = `${emoji} ${val.type?.replace('_', ' ')} ${val.target_class}`;
    } else if (key === 'temporal_direction') {
      chip.textContent = `${emoji} ${val === '>' ? 'after prev' : 'before prev'}`;
    } else {
      chip.textContent = `${emoji} ${label}: ${val}`;
    }

    chips.appendChild(chip);
  });

  bar.style.display = hasAny ? 'flex' : 'none';
}

// Wire "Clear All" button → DELETE session + hide bar
document.addEventListener('DOMContentLoaded', () => {
  const clearBtn = document.getElementById('clear-filters-btn');
  if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
      const sid = state.currentCollection || '';
      if (sid) {
        try {
          await fetch(`${API_BASE}/chat/session/${sid}`, { method: 'DELETE' });
        } catch (_) {}
      }
      const bar   = document.getElementById('active-filters-bar');
      const chips = document.getElementById('active-filter-chips');
      if (bar)   bar.style.display = 'none';
      if (chips) chips.innerHTML   = '';
      appendBubble('ai', 'Session cleared. Active filters have been reset.');
    });
  }
});


// ═══════════════════════════════════════════════════════════════
// IN-CHAT VIDEO UPLOAD
// Reuses the same /ingest/start + /ingest/status backend flow.
// Shows a compact inline progress strip directly in the chat section.
// ═══════════════════════════════════════════════════════════════
function initChatUpload() {
  const fileInput  = document.getElementById('chat-file-input');
  const cupDiv     = document.getElementById('chat-upload-progress');
  const cupBar     = document.getElementById('cup-bar');
  const cupLabel   = document.getElementById('cup-label');

  if (!fileInput) return;

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    // Reset for new upload
    fileInput.value = '';
    cupDiv.classList.remove('hidden');
    cupBar.style.width  = '0%';
    cupLabel.textContent = `Uploading "${file.name}"…`;
    appendBubble('ai', `📎 Got it! Processing "${file.name}" — this may take a minute…`);

    // 1. POST to /ingest/start
    let jobId;
    try {
      const fd  = new FormData();
      fd.append('video', file);   // server expects field name 'video' not 'file'
      const res = await fetch(API_BASE + '/ingest/start', { method: 'POST', body: fd });
      if (!res.ok) {
        let errMsg = `HTTP ${res.status}`;
        try { const e = await res.json(); errMsg = e.detail || e.error || errMsg; } catch(_) {}
        throw new Error(errMsg);
      }
      const data = await res.json();
      jobId = data.job_id;
    } catch (err) {
      cupDiv.classList.add('hidden');
      appendBubble('ai', `Upload failed: ${err.message}. Try using the Upload tab instead.`);
      return;
    }

    // 2. Poll /ingest/status/{job_id}
    const phaseEmoji = {
      starting:          '⚙',
      scene_detection:   '🎬',
      keyframe_extract:  '🖼',
      yolo_detection:    '🔍',
      color_extraction:  '🎨',
      spatial_relations: '📍',
      indexing:          '💾',
      complete:          '✅',
      error:             '❌',
    };

    const poll = setInterval(async () => {
      try {
        const res  = await fetch(`${API_BASE}/ingest/status/${jobId}`);
        const data = await res.json();

        const pct    = data.progress || 0;
        const phase  = data.phase    || 'processing';
        const status = data.status   || 'running';

        cupBar.style.width   = `${pct}%`;
        cupLabel.textContent = `${phaseEmoji[phase] || '⚙'} ${phase.replace('_', ' ')} — ${pct}%`;

        if (status === 'complete') {
          clearInterval(poll);
          cupDiv.classList.add('hidden');

          const videoId  = data.collection_name || jobId;
          state.currentCollection = videoId;

          // Clear previous session filters for the new video
          const bar   = document.getElementById('active-filters-bar');
          const chips = document.getElementById('active-filter-chips');
          if (bar)   bar.style.display = 'none';
          if (chips) chips.innerHTML   = '';

          // Show top detected objects as a summary bubble
          const topClasses = (data.top_classes || []).slice(0, 6).map(c => c.class).join(', ');
          const summaryMsg = topClasses
            ? `✅ Video indexed! I detected: ${topClasses}. Ask me anything!`
            : `✅ Video indexed! Now ask me what you're looking for.`;
          appendBubble('ai', summaryMsg);

          // Update collection badge if visible (keep sync with upload section)
          const badge = document.getElementById('collectionBadge');
          const nameEl = document.getElementById('collectionName');
          if (badge) badge.style.display = 'flex';
          if (nameEl) nameEl.textContent  = videoId;

        } else if (status === 'error') {
          clearInterval(poll);
          cupDiv.classList.add('hidden');
          appendBubble('ai', `❌ Ingestion failed: ${data.message || 'Unknown error'}. Try the Upload tab.`);
        }

      } catch (err) {
        clearInterval(poll);
        cupDiv.classList.add('hidden');
        appendBubble('ai', `Polling error: ${err.message}`);
      }
    }, 1500);
  });
}


// ═══════════════════════════════════════════════════════════════
// CONVERSATIONAL OPENER  — video library / upload picker
// ═══════════════════════════════════════════════════════════════
let _chatOpenerShown = false;

async function showChatOpener() {
  if (_chatOpenerShown) return;
  _chatOpenerShown = true;

  // If a video is already active, greet and skip picker
  if (state.currentCollection) {
    appendBubble('ai',
      `👋 Welcome back! Searching in: ${state.currentCollection}\n` +
      `Ask me anything — e.g. "person near red car" or "anyone without helmet".`
    );
    return;
  }

  // Show thinking indicator while we fetch library
  showTyping();

  let libraryVideos = [];
  try {
    const res = await fetch(API_BASE + '/videos/list');
    const data = await res.json();
    libraryVideos = data.videos || [];
  } catch (_) { /* backend not up yet — show upload CTA */ }

  hideTyping();

  if (libraryVideos.length === 0) {
    // No library videos — direct upload CTA
    const frag = document.createDocumentFragment();
    const pre  = document.createElement('pre');
    pre.className   = 'chat-reply-pre';
    pre.textContent =
      "👋 Hi! I'm Garuda Gamana, your AI CCTV analyst.\n\n" +
      "To get started, upload a video and I'll search it for anything you ask — " +
      "people, vehicles, colors, spatial relations, and more.";
    frag.appendChild(pre);

    // Upload button
    const btn = document.createElement('button');
    btn.className   = 'clarif-option-btn';
    btn.textContent = '⬆ Upload a Video';
    btn.style.marginTop = '10px';
    btn.addEventListener('click', () => switchView('upload'));
    frag.appendChild(btn);

    appendBubble('ai', frag);
    return;
  }

  // Library has videos — show picker
  const frag = document.createDocumentFragment();
  const pre  = document.createElement('pre');
  pre.className   = 'chat-reply-pre';
  pre.textContent =
    "👋 Hi! I'm Garuda Gamana.\n\n" +
    "Do you want to search an existing video from your library, or upload a new one?";
  frag.appendChild(pre);

  // Button group
  const btnGroup = document.createElement('div');
  btnGroup.className = 'clarif-btn-group';
  btnGroup.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;';

  libraryVideos.forEach(vid => {
    const b = document.createElement('button');
    b.className   = 'clarif-option-btn';
    b.textContent = `🎬 ${vid.name} (${vid.size_mb} MB)`;
    if (vid.already_ingested) {
      b.title = 'Already indexed — instant search!';
      b.style.borderColor = 'var(--accent)';
    } else {
      b.title = 'Will be indexed before searching (~1 min)';
    }
    b.addEventListener('click', async () => {
      // Disable all buttons
      btnGroup.querySelectorAll('button').forEach(x => { x.disabled = true; x.style.opacity = '0.45'; });
      b.style.opacity = '1'; b.style.background = 'var(--accent)'; b.style.color = '#000';

      appendBubble('user', vid.name);
      showTyping();

      try {
        const res  = await fetch(API_BASE + '/videos/select', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ video_id: vid.video_id }),
        });
        const data = await res.json();
        hideTyping();

        if (data.status === 'ok') {
          // Already ingested — instant active
          state.currentCollection = vid.video_id;
          appendBubble('ai',
            `✅ Switched to "${vid.name}"!\n` +
            `Now ask me anything — e.g. "person near red car" or "any vehicle without helmet".`
          );
        } else if (data.status === 'ingesting') {
          // Needs ingestion — show progress
          state.currentCollection = null;
          const progressDiv = document.createElement('div');
          progressDiv.innerHTML =
            `<div style="margin:8px 0">⚙ Indexing <b>${vid.name}</b>…<br>` +
            `<div class="progress-bar-outer" style="background:#222;border-radius:6px;height:8px;margin-top:6px">` +
            `<div id="lib-prog-bar" class="progress-bar-inner" style="width:0%;height:100%;background:var(--accent);border-radius:6px;transition:width 0.4s"></div>` +
            `</div><span id="lib-prog-label" style="font-size:0.75rem;opacity:0.7">Starting…</span></div>`;
          appendBubble('ai', progressDiv);

          // Poll ingestion status
          const pollLib = setInterval(async () => {
            try {
              const sr   = await fetch(`${API_BASE}/ingest/status/${data.job_id}`);
              const sd   = await sr.json();
              const pct  = sd.progress || 0;
              const phase = sd.phase || 'processing';
              const bar  = document.getElementById('lib-prog-bar');
              const lbl  = document.getElementById('lib-prog-label');
              if (bar) bar.style.width = `${pct}%`;
              if (lbl) lbl.textContent = `${phase.replace('_', ' ')} — ${pct}%`;

              if (sd.status === 'complete') {
                clearInterval(pollLib);
                const videoId = sd.collection_name || vid.video_id;
                state.currentCollection = videoId;
                appendBubble('ai',
                  `✅ "${vid.name}" indexed and ready!\n` +
                  `Ask me anything — e.g. "person near red car".`
                );
              } else if (sd.status === 'error') {
                clearInterval(pollLib);
                appendBubble('ai', `❌ Indexing failed: ${sd.message || 'Unknown error.'}`);
              }
            } catch (_) { clearInterval(pollLib); }
          }, 1500);
        } else {
          hideTyping();
          appendBubble('ai', `❌ ${data.message || 'Could not load video.'}`);
        }
      } catch (err) {
        hideTyping();
        appendBubble('ai', `❌ Error: ${err.message}`);
      }
    });
    btnGroup.appendChild(b);
  });

  // Upload new option
  const uploadBtn = document.createElement('button');
  uploadBtn.className   = 'clarif-option-btn';
  uploadBtn.textContent = '⬆ Upload New Video';
  uploadBtn.addEventListener('click', () => switchView('upload'));
  btnGroup.appendChild(uploadBtn);

  frag.appendChild(btnGroup);
  appendBubble('ai', frag);
}

function initChatOpener() {
  // Show opener on EVERY click of the Chat nav button (not just first time)
  // This allows switching videos at any time
  document.querySelectorAll('.nav-btn').forEach(btn => {
    if (btn.dataset.target === 'dashboard') {
      btn.addEventListener('click', () => {
        // Reset one-shot guard so picker always appears on nav click
        _chatOpenerShown = false;
        setTimeout(showChatOpener, 200);
      });
    }
  });

  // On first load, show opener if dashboard is the default view
  setTimeout(() => {
    const dashSection = document.getElementById('chat-section');
    if (dashSection && !dashSection.classList.contains('hidden')) {
      showChatOpener();
    }
  }, 800);
}


// ═══════════════════════════════════════════════════════════════
// INITIALIZE
// ═══════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  initUpload();
  initSearch();
  initVideoPlayer();
  initHistory();
  initChatUpload();
  initChatOpener();   // ← conversational video picker on first open
  checkBackend();

  console.log('Garuda Gamana v3.0 — Vexed + frontend/ merged. Ready.');
});
