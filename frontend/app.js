/* ═══════════════════════════════════════════════════════════════



   ASK-N-SEEK — App Logic v2.4



   Fully wired to real bridge_server.py backend.



   Features: real ingestion, scenario presets, vocab check,



             score bars, diagnosis, query history, video seek.



   ═══════════════════════════════════════════════════════════════ */







const API_BASE = 'http://localhost:8000';



const POLL_INTERVAL_MS = 800;







// ═══════════════════════════════════════════════════════════════



// STATE



// ═══════════════════════════════════════════════════════════════



let state = {



  collection: null,       // active Qdrant collection name



  results: [],            // current search results



  history: [],            // [{query, count, time, topScore}]



  currentQuery: '',



  isUploading: false,



  currentJobId: null,     // active ingestion job id



  pollTimer: null,        // setInterval handle for ingestion polling

  detectedClasses: [],    // [{class, count}] from /ingest/status top_classes



  videoPath: null,        // currently loaded video src



};







// ═══════════════════════════════════════════════════════════════



// PARTICLE SYSTEM (Hero)



// ═══════════════════════════════════════════════════════════════



function initParticles() {



  const container = document.getElementById('particles');



  if (!container) return;



  for (let i = 0; i < 50; i++) {



    const p = document.createElement('div');



    p.className = 'particle';



    p.style.left = Math.random() * 100 + '%';



    p.style.top = Math.random() * 100 + '%';



    p.style.animationDelay = Math.random() * 15 + 's';



    p.style.animationDuration = (10 + Math.random() * 10) + 's';



    p.style.width = (1 + Math.random() * 2) + 'px';



    p.style.height = p.style.width;



    p.style.opacity = 0.2 + Math.random() * 0.5;



    container.appendChild(p);



  }



}







// ═══════════════════════════════════════════════════════════════



// SCROLL REVEAL



// ═══════════════════════════════════════════════════════════════



function initScrollReveal() {



  const observer = new IntersectionObserver((entries) => {



    entries.forEach(entry => {



      if (entry.isIntersecting) entry.target.classList.add('visible');



    });



  }, { threshold: 0.15, rootMargin: '0px 0px -50px 0px' });







  document.querySelectorAll('.quote-text, .quote-attribution, .reveal').forEach(el => {



    observer.observe(el);



  });



}







// ═══════════════════════════════════════════════════════════════



// NAVIGATION SCROLL EFFECT



// ═══════════════════════════════════════════════════════════════



function initNavScroll() {



  const nav = document.querySelector('.nav');



  window.addEventListener('scroll', () => {



    nav.classList.toggle('scrolled', window.scrollY > 100);



  });



}







// ═══════════════════════════════════════════════════════════════



// BRIDGE HEALTH CHECK & MODE INDICATOR



// ═══════════════════════════════════════════════════════════════



async function checkBridgeHealth() {



  const dot = document.getElementById('statusDot');



  const text = document.getElementById('statusText');



  try {



    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });



    const data = await res.json();



    const isConnected = data.backend_mode === 'connected';



    dot.className = 'status-dot ' + (isConnected ? 'connected' : 'mock');



    text.textContent = isConnected



      ? `Backend connected — ${data.collection || 'ready'}`



      : `Mock mode — start bridge_server.py with real backend`;



  } catch {



    dot.className = 'status-dot offline';



    text.textContent = 'Bridge offline — start: cd frontend && python bridge_server.py';



  }



}







// ═══════════════════════════════════════════════════════════════



// SCENARIO PRESETS — fetched from /scenarios



// ═══════════════════════════════════════════════════════════════



// PROMPT 4: Preset → required class names (from scenario_presets.py ids)
const PRESET_CLASS_MAP = {
  'safety_violation': { primary: 'person',   secondary: 'helmet'  },
  'traffic_incident': { primary: 'car',       secondary: 'person'  },
  'lost_item':        { primary: 'backpack',  secondary: null       },
  'access_control':   { primary: 'person',   secondary: 'badge'   },
  'crowd_check':      { primary: 'person',   secondary: null       },
};

// PROMPT 4: Build tooltip text from detectedClasses for a given preset
function _presetTooltip(presetId, detectedClasses) {
  const map = PRESET_CLASS_MAP[presetId];
  if (!map) return '';
  const find = (cls) => detectedClasses.find(d => d.class && d.class.toLowerCase() === cls.toLowerCase());
  const lines = [];
  const p = find(map.primary);
  if (p) lines.push(p.class + ': ' + p.count + ' detected');
  if (map.secondary) {
    const s = find(map.secondary);
    if (s) lines.push(s.class + ': ' + s.count + ' detected');
    else    lines.push(map.secondary + ': not detected');
  }
  if (lines.length === 0) lines.push('None of the required objects detected');
  return lines.join('
');
}

// PROMPT 4: Determine if a preset is relevant given detectedClasses
function _presetIsRelevant(presetId, detectedClasses) {
  const map = PRESET_CLASS_MAP[presetId];
  if (!map) return false;
  const classNames = detectedClasses.map(d => (d.class || '').toLowerCase());
  return classNames.includes(map.primary.toLowerCase());
}

// Cache of fetched scenarios (so refreshPresets doesn't re-fetch)
let _cachedScenarios = null;

async function loadScenarios() {
  const grid = document.getElementById('presetsGrid');
  try {
    const res = await fetch(`${API_BASE}/scenarios`);
    _cachedScenarios = await res.json();
    renderPresetsGrid(_cachedScenarios, state.detectedClasses);
  } catch {
    grid.innerHTML = '<div class="preset-loading" style="color:rgba(255,255,255,0.3)">Scenarios unavailable - bridge offline</div>';
  }
}

// Called after ingestion completes with updated detectedClasses
function refreshPresets(detectedClasses) {
  if (_cachedScenarios) {
    renderPresetsGrid(_cachedScenarios, detectedClasses);
  }
  renderQuickChips(detectedClasses);
}

// Core render: builds preset buttons with relevance state + tooltip
function renderPresetsGrid(scenarios, detectedClasses) {
  const grid = document.getElementById('presetsGrid');
  if (!grid) return;
  const hasDetected = detectedClasses && detectedClasses.length > 0;
  grid.innerHTML = '';

  scenarios.forEach(s => {
    const btn = document.createElement('button');
    btn.dataset.query = s.query;
    btn.dataset.id = s.id;

    // Task 1: Relevance check
    const relevant = hasDetected && _presetIsRelevant(s.id, detectedClasses);
    const dimmed   = hasDetected && !relevant;

    // Base class
    let cls = 'scenario-btn';
    if (relevant) cls += ' relevant';
    if (dimmed)   cls += ' dimmed';
    btn.className = cls;

    // Detected tag (only when relevant)
    const detectedTag = relevant
      ? '<span class="preset-detected-tag"><span class="preset-detected-dot"></span>Detected</span>'
      : '';

    // Task 3: Tooltip text
    const ttLines = hasDetected
      ? _presetTooltip(s.id, detectedClasses)
      : 'Upload a video to see relevance';
    const tooltipHtml = '<span class="preset-tooltip">' + ttLines.replace(/
/g, '<br>') + '</span>';

    btn.innerHTML = '<span class="preset-label">' + s.label + '</span>' +
                    '<span class="preset-query">' + s.query + '</span>' +
                    detectedTag + tooltipHtml;

    if (!dimmed) {
      btn.addEventListener('click', () => {
        document.getElementById('queryInput').value = s.query;
        performSearch(s.query);
        document.getElementById('search').scrollIntoView({ behavior: 'smooth' });
      });
    }

    grid.appendChild(btn);
  });
}

// Task 2: Render quick-search chips from top detected classes
function renderQuickChips(detectedClasses) {
  const section = document.getElementById('quickChipsSection');
  const row     = document.getElementById('quickChipsRow');
  if (!section || !row) return;

  if (!detectedClasses || detectedClasses.length === 0) {
    section.style.display = 'none';
    return;
  }

  // Top 5 chips
  const top5 = detectedClasses.slice(0, 5);
  row.innerHTML = top5.map(item => {
    const cls = item.class || String(item);
    const cnt = item.count || '';
    return '<button class="quick-chip" onclick="performSearch('' + cls.replace(/'/g, "\'") + ''); document.getElementById('search').scrollIntoView({behavior:'smooth'})">' +
           cls + (cnt ? '<span class="quick-chip-count">' + cnt + '</span>' : '') +
           '</button>';
  }).join('');

  section.style.display = 'block';
}







// ═══════════════════════════════════════════════════════════════



// UPLOAD ZONE — Real ingestion via /ingest/start + /ingest/status



// ═══════════════════════════════════════════════════════════════



function initUpload() {



  const zone = document.getElementById('uploadZone');



  const fileInput = document.getElementById('fileInput');



  const progress = document.getElementById('uploadProgress');



  const progressFill = document.getElementById('progressFill');



  const progressLog = document.getElementById('progressLog');







  if (!zone) return;







  // Glow on hover



  zone.addEventListener('mousemove', (e) => {



    const rect = zone.getBoundingClientRect();



    zone.style.setProperty('--mouse-x', ((e.clientX - rect.left) / rect.width * 100) + '%');



    zone.style.setProperty('--mouse-y', ((e.clientY - rect.top) / rect.height * 100) + '%');



  });







  // Drag & drop



  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });



  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));



  zone.addEventListener('drop', (e) => {



    e.preventDefault();



    zone.classList.remove('drag-over');



    const file = e.dataTransfer.files[0];



    if (file && file.type.startsWith('video/')) handleUpload(file);



  });



  zone.addEventListener('click', () => { if (!state.isUploading) fileInput.click(); });



  fileInput.addEventListener('change', (e) => { if (e.target.files[0]) handleUpload(e.target.files[0]); });







  async function handleUpload(file) {



    if (state.isUploading) return;



    state.isUploading = true;



    zone.classList.add('uploading');



    progress.classList.add('active');



    progressLog.innerHTML = '';



    progressFill.style.width = '0%';



    document.getElementById('ingestStats').style.display = 'none';



    document.getElementById('collectionBadge').style.display = 'none';



    // TASK 2: Reset top objects + meta bar



    document.getElementById('topObjectsSection').style.display = 'none';



    document.getElementById('topObjectsGrid').innerHTML = '';



    document.getElementById('ingestMetaBar').style.display = 'flex';



    document.getElementById('ingestPct').textContent = '0%';



    document.getElementById('ingestElapsed').textContent = 'Elapsed: 0:00';



    document.getElementById('ingestPhaseLabel').textContent = 'Starting';



    state._uploadStartTime = Date.now();







    // Reset phase indicators



    document.querySelectorAll('.phase').forEach(p => p.classList.remove('active', 'complete'));







    addLog(`Uploading: ${file.name} (${(file.size / 1_048_576).toFixed(1)} MB)`, 'info');







    // POST multipart upload



    const formData = new FormData();



    formData.append('video', file);







    let jobId;



    try {



      const res = await fetch(`${API_BASE}/ingest/start`, {



        method: 'POST',



        body: formData,



      });



      if (!res.ok) {



        const err = await res.json().catch(() => ({ error: res.statusText }));



        throw new Error(err.error || res.statusText);



      }



      const data = await res.json();



      jobId = data.job_id;



      state.currentJobId = jobId;



      addLog(`Upload accepted - job ${jobId}`, 'pass');



    } catch (err) {



      addLog(`Upload failed: ${err.message}`, 'fail');



      state.isUploading = false;



      return;



    }







    // Poll /ingest/status/{job_id}



    if (state.pollTimer) clearInterval(state.pollTimer);



    state.pollTimer = setInterval(() => pollIngestionStatus(jobId), POLL_INTERVAL_MS);



  }







  function addLog(msg, type) {



    // TASK 1: Colored terminal log lines



    const div = document.createElement('div');



    div.className = 'qlog-line ' + (type ? 'qlog-' + type : 'qlog-info');



    const ts = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });



    div.textContent = '[' + ts + '] ' + msg;



    progressLog.appendChild(div);



    progressLog.scrollTop = progressLog.scrollHeight;



  }







  window._addIngestLog = addLog; // expose for pollIngestionStatus



}







// Phase name → data-phase attribute mapping



const PHASE_ORDER = [



  'scene_detection', 'extraction', 'detection', 'color', 'spatial', 'indexing', 'complete'



];







async function pollIngestionStatus(jobId) {



  try {



    const res = await fetch(`${API_BASE}/ingest/status/${jobId}`);



    if (!res.ok) {



      if (res.status === 404) {



        clearInterval(state.pollTimer);



        window._addIngestLog('Job not found', 'fail');



      }



      return;



    }



    const job = await res.json();







    // Update progress bar



    const pct = job.progress || 0;



    document.getElementById('progressFill').style.width = pct + '%';







    // TASK 2: Meta bar - percentage, elapsed, phase label



    document.getElementById('ingestPct').textContent = pct + '%';



    if (state._uploadStartTime) {



      const elapsedMs = Date.now() - state._uploadStartTime;



      const elapsedSec = Math.floor(elapsedMs / 1000);



      const mm = Math.floor(elapsedSec / 60);



      const ss = String(elapsedSec % 60).padStart(2, '0');



      document.getElementById('ingestElapsed').textContent = 'Elapsed: ' + mm + ':' + ss;



    }



    const phaseDisplayLabel = job.phase ? job.phase.replace(/_/g, ' ') : 'Processing';



    document.getElementById('ingestPhaseLabel').textContent = phaseDisplayLabel;







    // Update phase indicators



    const phase = job.phase || '';



    const phaseIdx = PHASE_ORDER.indexOf(phase);



    document.querySelectorAll('.phase').forEach((el, idx) => {



      el.classList.remove('active', 'complete');



      if (phaseIdx >= 0) {



        if (idx < phaseIdx) el.classList.add('complete');



        else if (idx === phaseIdx) el.classList.add('active');



      }



    });







    // Log message



    if (job.message) window._addIngestLog(`[${phase}] ${job.message}`, 'info');







    // Show stats



    if (job.stats && Object.keys(job.stats).length > 0) {



      const statsEl = document.getElementById('ingestStats');



      statsEl.style.display = 'block';



      statsEl.innerHTML = `



        <div class="stat-row"><span>Scenes:</span><span>${job.stats.scenes || 0}</span></div>



        <div class="stat-row"><span>Keyframes:</span><span>${job.stats.keyframes || 0}</span></div>



        <div class="stat-row"><span>Objects:</span><span>${job.stats.objects || 0}</span></div>



      `;



    }







    // Complete



    if (job.status === 'complete') {



      clearInterval(state.pollTimer);



      state.isUploading = false;



      state.collection = job.collection_name;



      window._addIngestLog(`Ready - collection: ${job.collection_name}`, 'pass');







      // Show collection badge



      const badge = document.getElementById('collectionBadge');



      badge.style.display = 'flex';



      document.getElementById('collectionName').textContent = job.collection_name;







      // TASK 3: Render top detected objects
      state.detectedClasses = job.top_classes || [];
      _renderTopObjects(state.detectedClasses);
      // PROMPT 4: Refresh presets + quick chips with detected class info
      refreshPresets(state.detectedClasses);







      // Auto-scroll to search



      setTimeout(() => {



        document.getElementById('search').scrollIntoView({ behavior: 'smooth' });



        document.getElementById('queryInput').focus();



      }, 800);







      // Refresh bridge status



      checkBridgeHealth();



    }







    if (job.status === 'error') {



      clearInterval(state.pollTimer);



      state.isUploading = false;



      window._addIngestLog(`Ingestion failed: ${job.message}`, 'fail');



    }







  } catch (err) {



    // Network error during polling — don't stop, retry



    console.warn('Polling error:', err);



  }



}







// ═══════════════════════════════════════════════════════════════



// SEARCH — Real backend call



// ═══════════════════════════════════════════════════════════════







// ---------------------------------------------------------------



// TASK 3: Top Detected Objects Grid



// ---------------------------------------------------------------



function _renderTopObjects(topClasses) {



  const section = document.getElementById('topObjectsSection');



  const grid = document.getElementById('topObjectsGrid');



  if (!topClasses || topClasses.length === 0) {



    section.style.display = 'none';



    return;



  }



  grid.innerHTML = topClasses.map(function(item) {



    return '<div class="top-object-card">' +



      '<span class="top-object-name">' + (item.class || String(item)) + '</span>' +



      '<span class="top-object-sep">·</span>' +



      '<span class="top-object-count">' + item.count + '</span>' +



      '</div>';



  }).join('');



  section.style.display = 'block';



}







function initSearch() {



  const input = document.getElementById('queryInput');



  const btn = document.getElementById('searchBtn');







  if (!input) return;







  btn.addEventListener('click', () => {



    if (input.value.trim()) performSearch(input.value.trim());



  });







  input.addEventListener('keydown', (e) => {



    if (e.key === 'Enter' && input.value.trim()) performSearch(input.value.trim());



  });



}







async function performSearch(query) {



  state.currentQuery = query;







  // Show loading state on button



  const btn = document.getElementById('searchBtn');



  btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">



    <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="20">



      <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/>



    </circle></svg>`;







  // Show query log



  const queryLog = document.getElementById('queryLog');



  const queryLogInner = document.getElementById('queryLogInner');



  queryLog.style.display = 'block';



  queryLogInner.innerHTML = '';



  addQueryLog('info', `⏳ Processing: "${query}"…`);







  // Step 1: Vocab check (non-blocking)



  try {



    const vocabForm = new FormData();



    vocabForm.append('query', query);



    const vocabRes = await fetch(`${API_BASE}/vocab/check`, { method: 'POST', body: vocabForm });



    const warnings = await vocabRes.json();



    renderVocabWarnings(warnings);



  } catch {



    // Vocab check failure is non-fatal



  }







  // Step 2: Query



  addQueryLog('info', `🔎 Searching Qdrant${state.collection ? ` (${state.collection})` : ''}…`);







  try {



    const res = await fetch(`${API_BASE}/query`, {



      method: 'POST',



      headers: { 'Content-Type': 'application/json' },



      body: JSON.stringify({



        query: query,



        collection_name: state.collection,



      }),



    });







    if (!res.ok) {



      const err = await res.json().catch(() => ({ message: res.statusText }));



      throw new Error(err.message || res.statusText);



    }







    const data = await res.json();







    if (data.cached) {



      addQueryLog('pass', '⚡ Result served from cache');



    }







    addQueryLog(



      data.status === 'match' ? 'pass' : 'fail',



      data.status === 'match'



        ? `✅ ${data.results.length} result(s) — best score ${(data.best_score || 0).toFixed(3)} ≥ threshold ${(data.threshold || 0.3197).toFixed(4)}`



        : `🔴 No match — best score ${(data.best_score || 0).toFixed(3)} < threshold ${(data.threshold || 0.3197).toFixed(4)}`



    );







    state.results = data.results || [];



    renderResults(data, query);



    addToHistory(query, state.results.length, data.best_score || 0);







  } catch (err) {



    addQueryLog('fail', `❌ Search failed: ${err.message}`);



    document.getElementById('diagnosisPanel').style.display = 'block';



    document.getElementById('diagnosisPanel').innerHTML = `



      <div style="padding:24px;color:rgba(255,255,255,0.5);">



        <h3>Backend Error</h3>



        <p style="margin-top:8px;font-size:0.9rem;">${err.message}</p>



        <p style="margin-top:8px;font-size:0.8rem;">Is bridge_server.py running on port 8000?</p>



      </div>`;



  }







  // Restore search button



  btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">



    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`;







  // Scroll to results



  document.getElementById('results').scrollIntoView({ behavior: 'smooth' });



}







function addQueryLog(type, msg) {



  const inner = document.getElementById('queryLogInner');



  const div = document.createElement('div');



  div.className = `qlog-line qlog-${type}`;



  div.textContent = msg;



  inner.appendChild(div);



  inner.scrollTop = inner.scrollHeight;



}







// ═══════════════════════════════════════════════════════════════



// VOCAB WARNINGS RENDER



// ═══════════════════════════════════════════════════════════════



function renderVocabWarnings(warnings) {



  const el = document.getElementById('vocabWarnings');



  if (!warnings || warnings.length === 0) {



    el.innerHTML = '';



    el.classList.remove('active');



    return;



  }



  const items = warnings.map(w => {



    if (w.type === 'suggestion') {



      return `<span class="vocab-warn-item">⚠️ "<strong>${w.token}</strong>" not in vocabulary — did you mean: "<em>${w.suggestion}</em>"?</span>`;



    }



    return `<span class="vocab-warn-item">⚠️ "<strong>${w.token}</strong>" not recognized — try a different term.</span>`;



  });



  el.innerHTML = items.join('');



  el.classList.add('active');



}







// ═══════════════════════════════════════════════════════════════



// RENDER RESULTS



// ═══════════════════════════════════════════════════════════════



function renderResults(data, query) {



  const header = document.getElementById('resultsHeader');



  const countEl = document.getElementById('resultsCount');



  const queryEl = document.getElementById('resultsQuery');



  const grid = document.getElementById('resultsGrid');



  const diagnosis = document.getElementById('diagnosisPanel');



  const videoArea = document.getElementById('videoPlayerArea');







  header.style.display = 'block';



  const results = data.results || [];



  countEl.textContent = `${results.length} Result${results.length !== 1 ? 's' : ''}`;



  queryEl.textContent = `for "${query}"`;







  // No-match diagnosis



  if (data.status === 'no_match' || results.length === 0) {



    grid.innerHTML = '';



    videoArea.style.display = 'none';







    if (data.diagnosis && data.diagnosis.html) {



      // Real diagnosis HTML from backend



      diagnosis.style.display = 'block';



      diagnosis.innerHTML = data.diagnosis.html;



    } else {



      diagnosis.style.display = 'block';



      diagnosis.innerHTML = `



        <div class="no-match-inner">



          <div class="no-match-icon">🔍</div>



          <h3>No Confident Match</h3>



          <p>We found related objects, but nothing matched all constraints together.</p>



          <div class="diagnosis-score-bar">



            <div class="bar-track">



              <div class="bar-fill" style="width:${Math.round((data.best_score || 0) * 100)}%"></div>



              <div class="bar-threshold" style="left:${Math.round((data.threshold || 0.3197) * 100)}%"></div>



            </div>



            <div class="bar-labels">



              <span>0.0</span>



              <span>Threshold: ${(data.threshold || 0.3197).toFixed(4)}</span>



              <span>1.0</span>



            </div>



          </div>



          <p class="no-match-tip">💡 Try broadening your query — remove one constraint at a time.</p>



        </div>`;



    }



    return;



  }







  diagnosis.style.display = 'none';



  videoArea.style.display = 'block';







  grid.innerHTML = results.map((r, i) => {



    const confClass = r.confidence_score >= 0.75 ? 'high' : r.confidence_score >= 0.5 ? 'medium' : 'low';



    const confLabel = r.confidence_score >= 0.75 ? 'HIGH' : r.confidence_score >= 0.5 ? 'MED' : 'LOW';







    // BBox overlays



    let bboxHtml = '';



    (r.matched_objects || []).forEach((obj, idx) => {



      const bx = obj.bbox || [0.1 + idx * 0.25, 0.1, 0.3 + idx * 0.25, 0.5];



      bboxHtml += `<div class="bbox-box" style="left:${bx[0]*100}%;top:${bx[1]*100}%;width:${(bx[2]-bx[0])*100}%;height:${(bx[3]-bx[1])*100}%">



        <span class="bbox-label">${obj.class_name || '?'}${obj.color ? ' / ' + obj.color : ''}</span></div>`;



    });







    // Smart Score Bars (Task 7)



    const scoreBarsHtml = renderScoreBars(r.score_breakdown, data.parsed);







    return `



      <div class="result-card" id="result-card-${i}" onclick="playResult(${i})" style="opacity:0;animation:fade-in 0.5s ease ${i*0.1}s forwards">



        <div class="result-card-visual">



          <div class="result-frame-placeholder">

              <div class="ts-visual">

                <span class="ts-time">${r.timestamp.toFixed(1)}s</span>

                <span class="ts-label">Timestamp</span>

                <span class="ts-click-hint">Click to play clip</span>

                <span class="ts-scene">Scene ${r.scene_id}</span>

              </div>



            <div class="bbox-overlay">${bboxHtml}</div>



          </div>



        </div>



        <div class="result-card-body">



          <div class="result-card-header">



            <span class="result-video-id">📹 ${r.video_id}</span>



            <span class="result-confidence ${confClass}">${confLabel} ${r.confidence_score.toFixed(3)}</span>



          </div>



          <div class="result-meta">



            <span>⏱ ${r.timestamp.toFixed(1)}s</span>



            <span>·</span>



            <span>Scene ${r.scene_id}</span>



            <span>·</span>



            <span>${(r.matched_objects || []).length} object(s)</span>



          </div>



          <p class="result-explanation">💡 ${r.explanation || ''}</p>



          ${scoreBarsHtml}



          <p class="result-hint">Click to seek video ↓</p>



        </div>



      </div>`;



  }).join('');







    // Populate hidden select (backward compat)

  const picker = document.getElementById('resultPicker');

  if (picker) {

    picker.innerHTML = '<option value="">Jump to result</option>' +

      results.map((r, i) =>

        `<option value="${i}">${r.video_id} @ ${r.timestamp.toFixed(1)}s [${r.confidence_score.toFixed(3)}]</option>`

      ).join('');

  }



  // Show player area when results exist (so jump list is visible)

  if (results.length > 0) {

    document.getElementById('videoPlayerArea').style.display = 'block';

  }



  // Task 4: Build styled jump list

  const jumpList = document.getElementById('resultJumpList');

  const jumpHeader = document.getElementById('jumpListHeader');

  const jumpCount = document.getElementById('jumpListCount');

  if (jumpList) {

    if (results.length > 0) {

      jumpHeader.style.display = 'flex';

      jumpCount.textContent = results.length + ' result' + (results.length !== 1 ? 's' : '');

      jumpList.innerHTML = results.map((r, i) => `

        <div class="result-jump-item" id="jump-item-${i}" onclick="playResult(${i})">

          <span class="jump-index">${i + 1}</span>

          <span class="jump-vid">${r.video_id}</span>

          <span class="jump-ts">${r.timestamp.toFixed(1)}s</span>

          <span class="jump-score">${r.confidence_score.toFixed(3)}</span>

        </div>`).join('');

    } else {

      jumpHeader.style.display = 'none';

      jumpList.innerHTML = '';

    }

  }

}



// Task 4: Highlight active jump item

function _highlightJumpItem(idx) {

  document.querySelectorAll('.result-jump-item').forEach((el, i) => {

    el.classList.toggle('active', i === idx);

  });

}







// ═══════════════════════════════════════════════════════════════



// SMART SCORE BARS (Task 7)



// Categories: Object 0-40, Color 0-20, Spatial 0-20, Negation 0-20



// Gold fill (#c9a96e) exactly matching CSS --color-accent



// ═══════════════════════════════════════════════════════════════



function renderScoreBars(sb, parsed) {

  if (!sb) return '';



  // Task 3: derive constraint presence from parsed filters

  const filters = (parsed && parsed.filters) ? parsed.filters : {};

  const hasColor    = !!(filters.color    && filters.color    !== null);

  const hasSpatial  = !!(filters.spatial_relation && filters.spatial_relation !== null);

  const hasNegation = !!(filters.negated  && filters.negated  !== null && filters.negated !== false);



  function noteFor(cat, val) {

    if (val > 0) return '';

    switch (cat) {

      case 'Color':

        return hasColor    ? '<span class="score-bar-note">Not detected</span>'

                           : '<span class="score-bar-note">No color constraint</span>';

      case 'Spatial':

        return hasSpatial  ? '<span class="score-bar-note">Not detected</span>'

                           : '<span class="score-bar-note">No spatial constraint</span>';

      case 'Negation':

        return hasNegation ? '<span class="score-bar-note">Not detected</span>'

                           : '<span class="score-bar-note">No negation constraint</span>';

      default: return '';

    }

  }



  const cats = [

    { name: 'Object',   val: sb.object_score   || 0, max: 40 },

    { name: 'Color',    val: sb.color_score    || 0, max: 20 },

    { name: 'Spatial',  val: sb.spatial_score  || 0, max: 20 },

    { name: 'Negation', val: sb.negation_score || 0, max: 20 },

  ];



  const bars = cats.map(c => {

    const pct = Math.round((c.val / c.max) * 100);

    const note = noteFor(c.name, c.val);

    return `

      <div class="score-bar-row">

        <span class="score-bar-label">${c.name}</span>

        <div class="score-bar-track">

          <div class="score-bar-fill" style="width:${pct}%"></div>

        </div>

        <span class="score-bar-value">${c.val}/${c.max}${note}</span>

      </div>`;

  }).join('');



  return `

    <div class="score-breakdown">

      <div class="score-breakdown-title">Score Breakdown</div>

      ${bars}

      <div class="score-total">Total: <strong>${sb.total || 0}</strong>/100</div>

    </div>`;

}









// ═══════════════════════════════════════════════════════════════



// VIDEO PLAYER & SEEK (Task 10)



// ═══════════════════════════════════════════════════════════════



function initVideoPlayer() {



  const picker = document.getElementById('resultPicker');



  const video = document.getElementById('mainVideo');



  const timeEl = document.getElementById('playerTime');







  if (!picker) return;







  picker.addEventListener('change', (e) => {



    const idx = parseInt(e.target.value);



    if (!isNaN(idx) && state.results[idx]) playResult(idx);



  });







  video.addEventListener('timeupdate', () => {



    const t = video.currentTime;



    const mins = Math.floor(t / 60);



    const secs = Math.floor(t % 60);



    const ms = Math.floor((t % 1) * 100);



    timeEl.textContent = `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'00')}.${String(ms).padStart(2,'0')}`;

    // Task 2: Auto-pause at clip end (timestamp + 3s)

    if (state.clipEnd !== undefined && t >= state.clipEnd) {

      video.pause();

    }

  });



}







window.playResult = function(idx) {

  const video = document.getElementById('mainVideo');

  const picker = document.getElementById('resultPicker');

  const result = state.results[idx];

  if (!result) return;



  // Task 2: Track clip window for auto-pause

  state.clipStart = Math.max(0, result.timestamp - 3);

  state.clipEnd   = result.timestamp + 3;

  state.activeResultIdx = idx;



  // Update clip info display

  const clipInfo = document.getElementById('clipInfo');

  if (clipInfo) {

    clipInfo.textContent = result.timestamp.toFixed(1) + 's  (− 3s to + 3s)';

  }

  document.getElementById('clipControls').style.display = 'flex';



  // Set video source (only reload if different video)

  const newSrc = API_BASE + '/video/' + encodeURIComponent(result.video_id);

  if (video.dataset.videoId !== result.video_id) {

    video.src = newSrc;

    video.dataset.videoId = result.video_id;

    video.load();

    // Seek after metadata is loaded

    video.addEventListener('loadedmetadata', function _seekOnLoad() {

      video.removeEventListener('loadedmetadata', _seekOnLoad);

      video.currentTime = state.clipStart;

      video.play().catch(() => {});

    });

  } else {

    // Same video, just re-seek

    video.currentTime = state.clipStart;

    video.play().catch(() => {});

  }



  // Sync picker + jump list active state

  if (picker) picker.value = String(idx);

  _highlightJumpItem(idx);



  // Show player area

  const area = document.getElementById('videoPlayerArea');

  area.style.display = 'block';

  area.scrollIntoView({ behavior: 'smooth', block: 'center' });

};



// Task 2: replayClip — re-seeks to t-3 and plays

window.replayClip = function() {

  const video = document.getElementById('mainVideo');

  if (!video || state.clipStart === undefined) return;

  video.currentTime = state.clipStart;

  video.play().catch(() => {});

};



// ═══════════════════════════════════════════════════════════════



// QUERY HISTORY (Task 9)



// ═══════════════════════════════════════════════════════════════



function initHistory() {



  const sidebar = document.getElementById('historySidebar');



  const toggle = document.getElementById('historyToggle');



  const close = document.getElementById('closeHistory');







  toggle.addEventListener('click', () => sidebar.classList.add('open'));



  close.addEventListener('click', () => sidebar.classList.remove('open'));







  document.addEventListener('click', (e) => {



    if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {



      sidebar.classList.remove('open');



    }



  });



}







function addToHistory(query, count, topScore) {



  const item = { query, count, time: new Date().toLocaleTimeString(), topScore };



  state.history.unshift(item);







  // Update counter badge



  const countEl = document.getElementById('historyCount');



  countEl.textContent = state.history.length;



  countEl.style.display = 'inline-block';







  renderHistory();



}







function renderHistory() {



  const list = document.getElementById('historyList');



  if (state.history.length === 0) {



    list.innerHTML = `<div style="color:rgba(255,255,255,0.3);font-size:0.85rem;padding:16px;font-style:italic;">No queries yet.</div>`;



    return;



  }



  list.innerHTML = state.history.map((h, i) => `



    <div class="history-item" onclick="replayQuery(${i})">



      <div class="history-item-query">${escapeHtml(h.query)}</div>



      <div class="history-item-meta">



        <span>${h.time}</span>



        <span>${h.count} result${h.count !== 1 ? 's' : ''}</span>



        <span>score: ${h.topScore.toFixed(3)}</span>



      </div>



    </div>`).join('');



}







window.replayQuery = function(idx) {



  const item = state.history[idx];



  if (!item) return;



  const input = document.getElementById('queryInput');



  input.value = item.query;



  document.getElementById('historySidebar').classList.remove('open');



  // QueryCache will serve this instantly if it was cached



  performSearch(item.query);



  document.getElementById('search').scrollIntoView({ behavior: 'smooth' });



};







function escapeHtml(str) {



  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');



}







// ═══════════════════════════════════════════════════════════════



// INTERACTIVE HOLD & MOVE



// ═══════════════════════════════════════════════════════════════



function initInteractiveTrack() {



  const area = document.getElementById('interactiveArea');



  const track = document.getElementById('interactiveTrack');



  if (!area || !track) return;







  let isDown = false, startX, scrollLeft, velocity = 0, rafId = null;







  area.addEventListener('mousedown', (e) => {



    isDown = true;



    area.style.cursor = 'grabbing';



    startX = e.pageX - area.offsetLeft;



    scrollLeft = getTranslateX(track);



    cancelAnimationFrame(rafId);



  });







  area.addEventListener('mouseleave', () => { isDown = false; area.style.cursor = 'grab'; applyMomentum(); });



  area.addEventListener('mouseup', () => { isDown = false; area.style.cursor = 'grab'; applyMomentum(); });







  area.addEventListener('mousemove', (e) => {



    if (!isDown) return;



    e.preventDefault();



    const x = e.pageX - area.offsetLeft;



    const walk = (x - startX) * 1.5;



    velocity = walk - (getTranslateX(track) - scrollLeft);



    track.style.transform = `translateX(${scrollLeft + walk}px)`;



  });







  area.addEventListener('touchstart', (e) => {



    isDown = true;



    startX = e.touches[0].pageX - area.offsetLeft;



    scrollLeft = getTranslateX(track);



    cancelAnimationFrame(rafId);



  }, { passive: true });







  area.addEventListener('touchend', () => { isDown = false; applyMomentum(); });



  area.addEventListener('touchmove', (e) => {



    if (!isDown) return;



    const x = e.touches[0].pageX - area.offsetLeft;



    const walk = (x - startX) * 1.5;



    velocity = walk - (getTranslateX(track) - scrollLeft);



    track.style.transform = `translateX(${scrollLeft + walk}px)`;



  }, { passive: true });







  function getTranslateX(el) {



    const matrix = new WebKitCSSMatrix(window.getComputedStyle(el).transform);



    return matrix.m41;



  }







  function applyMomentum() {



    const current = getTranslateX(track);



    const newX = current + velocity * 2;



    const minScroll = -(track.scrollWidth - area.clientWidth);



    const target = Math.max(minScroll, Math.min(0, newX));



    track.style.transition = 'transform 0.8s cubic-bezier(0.22, 1, 0.36, 1)';



    track.style.transform = `translateX(${target}px)`;



    setTimeout(() => { track.style.transition = 'transform 0.1s ease-out'; }, 800);



  }



}







// ═══════════════════════════════════════════════════════════════



// SMOOTH SCROLL FOR NAV LINKS



// ═══════════════════════════════════════════════════════════════



function initSmoothScroll() {



  document.querySelectorAll('a[href^="#"]').forEach(anchor => {



    anchor.addEventListener('click', function(e) {



      e.preventDefault();



      const target = document.querySelector(this.getAttribute('href'));



      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });



    });



  });



}







// ═══════════════════════════════════════════════════════════════



// INITIALIZE



// ═══════════════════════════════════════════════════════════════



document.addEventListener('DOMContentLoaded', async () => {



  initParticles();



  initScrollReveal();



  initNavScroll();



  initUpload();



  initSearch();



  initVideoPlayer();



  initHistory();



  initInteractiveTrack();



  initSmoothScroll();







  // Async: health check + load scenarios



  await checkBridgeHealth();



  await loadScenarios();







  console.log('Ask-N-Seek v2.4 — Real Backend Wired ✅');



});



