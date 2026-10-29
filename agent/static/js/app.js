/**
 * OmniResearch Web Application Client Script
 * Handles real-time event streaming, history management, interactive citations, and settings.
 */

let activeReport = null;
let activeBaseline = null;
let timerInterval = null;
let startTime = 0;

document.addEventListener('DOMContentLoaded', () => {
    initHistory();
    initPresets();
    fetchSystemStatus();

    // Keyboard shortcut: Ctrl + Enter to launch
    const textarea = document.getElementById('query-input');
    if (textarea) {
        textarea.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                submitResearch();
            }
        });
    }

    // Keyboard shortcut: Ctrl + K for new inquiry
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            startNewInquiry();
        }
        if (e.key === 'Escape') {
            closeModal();
        }
    });
});

function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('visible');
    setTimeout(() => toast.classList.remove('visible'), 2600);
}

async function fetchSystemStatus() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        const pill = document.getElementById('status-provider');
        if (pill) pill.textContent = data.provider.toUpperCase();
        const select = document.getElementById('provider-select');
        if (select) select.value = data.provider;
    } catch (err) {
        console.error('Failed to load system health:', err);
    }
}

async function initPresets() {
    try {
        const res = await fetch('/api/examples');
        const list = await res.json();
        const presetsWrap = document.getElementById('presets-wrap');
        const sidebarList = document.getElementById('benchmark-list');

        if (presetsWrap) presetsWrap.innerHTML = '';
        if (sidebarList) sidebarList.innerHTML = '';

        list.forEach((item, idx) => {
            // Sidebar item
            if (sidebarList) {
                const li = document.createElement('li');
                li.className = 'inquiry-item';
                li.textContent = item.query;
                li.onclick = () => selectQuery(item.query);
                sidebarList.appendChild(li);
            }

            // Quick chip
            if (presetsWrap && idx < 4) {
                const chip = document.createElement('div');
                chip.className = 'preset-chip';
                chip.textContent = item.query.length > 52 ? item.query.substring(0, 50) + '...' : item.query;
                chip.onclick = () => selectQuery(item.query);
                presetsWrap.appendChild(chip);
            }
        });
    } catch (err) {
        console.error('Failed to load benchmark presets:', err);
    }
}

function selectQuery(q) {
    const input = document.getElementById('query-input');
    if (input) {
        input.value = q;
        submitResearch();
    }
}

function startNewInquiry() {
    const input = document.getElementById('query-input');
    if (input) {
        input.value = '';
        input.focus();
    }
    const results = document.getElementById('results-wrap');
    if (results) results.style.display = 'none';
    const crumb = document.getElementById('crumb-inquiry');
    if (crumb) crumb.textContent = 'New Inquiry';
}

async function submitResearch() {
    const input = document.getElementById('query-input');
    const query = input ? input.value.trim() : '';
    if (!query) {
        showToast('Please specify a research question.');
        return;
    }

    const compareBaseline = document.getElementById('baseline-toggle') ? document.getElementById('baseline-toggle').checked : false;
    const providerSelect = document.getElementById('provider-select');
    const provider = providerSelect ? providerSelect.value : 'auto';

    const btn = document.getElementById('submit-btn');
    const stepper = document.getElementById('stepper-card');
    const results = document.getElementById('results-wrap');

    if (btn) btn.disabled = true;
    if (stepper) stepper.style.display = 'block';
    if (results) results.style.display = 'none';

    const crumb = document.getElementById('crumb-inquiry');
    if (crumb) crumb.textContent = query.length > 36 ? query.substring(0, 36) + '...' : query;

    // Reset stepper UI
    for (let i = 1; i <= 6; i++) {
        const step = document.getElementById(`step-${i}`);
        if (step) {
            step.className = 'stepper-item';
            const badge = step.querySelector('.stepper-badge');
            if (badge) badge.textContent = i;
        }
    }
    const firstStep = document.getElementById('step-1');
    if (firstStep) firstStep.classList.add('active');

    startTime = Date.now();
    const timerElem = document.getElementById('stepper-timer');
    timerInterval = setInterval(() => {
        if (timerElem) {
            const sec = ((Date.now() - startTime) / 1000).toFixed(2);
            timerElem.textContent = `${sec}s`;
        }
    }, 50);

    try {
        // Stream progress events from SSE endpoint
        const response = await fetch('/api/research/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                provider: provider,
                compare_baseline: compareBaseline
            })
        });

        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';

            for (const chunk of lines) {
                if (chunk.startsWith('data: ')) {
                    const rawJson = chunk.slice(6).trim();
                    if (!rawJson) continue;
                    try {
                        const event = JSON.parse(rawJson);
                        handleStreamEvent(event);
                    } catch (e) {
                        console.error('Failed to parse SSE payload:', e);
                    }
                }
            }
        }
    } catch (err) {
        showToast(`Execution error: ${err.message}`);
    } finally {
        clearInterval(timerInterval);
        if (btn) btn.disabled = false;
        if (stepper) stepper.style.display = 'none';
        if (results && activeReport) results.style.display = 'block';
    }
}

function handleStreamEvent(event) {
    if (event.type === 'progress') {
        const stage = event.stage;
        if (stage === 'Planning') advanceStep(1);
        else if (stage === 'ToolExecution') advanceStep(2);
        else if (stage === 'Filtering') advanceStep(4);
        else if (stage === 'Synthesis') advanceStep(5);
        else if (stage === 'Critique') advanceStep(6);
    } else if (event.type === 'complete') {
        for (let i = 1; i <= 6; i++) {
            const s = document.getElementById(`step-${i}`);
            if (s) {
                s.className = 'stepper-item completed';
                const b = s.querySelector('.stepper-badge');
                if (b) b.textContent = '✓';
            }
        }

        activeReport = event.report;
        activeBaseline = event.baseline || null;
        saveHistoryEntry(activeReport.user_question, activeReport);
        renderDossier(activeReport, activeBaseline);
        showToast('Research dossier compiled.');
    } else if (event.type === 'error') {
        showToast(`Agent error: ${event.error}`);
    }
}

function advanceStep(stepIndex) {
    for (let i = 1; i < stepIndex; i++) {
        const s = document.getElementById(`step-${i}`);
        if (s) {
            s.className = 'stepper-item completed';
            const b = s.querySelector('.stepper-badge');
            if (b) b.textContent = '✓';
        }
    }
    const current = document.getElementById(`step-${stepIndex}`);
    if (current) current.className = 'stepper-item active';
}

function renderDossier(report, baseline) {
    document.getElementById('report-question').textContent = report.user_question;
    document.getElementById('report-summary').textContent = report.short_answer;

    // Confidence badge
    const confPill = document.getElementById('report-confidence');
    if (confPill) {
        confPill.textContent = `${report.confidence_level} Confidence`;
        confPill.className = `confidence-pill confidence-${report.confidence_level}`;
    }

    // Key findings
    const findingsList = document.getElementById('findings-list');
    if (findingsList) {
        findingsList.innerHTML = '';
        report.key_findings.forEach(f => {
            const div = document.createElement('div');
            div.className = 'finding-item';
            div.innerHTML = f.replace(/\\[(S\\d+)\\]/g, (match, p1) => {
                return `<span class="citation-tag" onclick="focusSource('${p1}')" onmouseenter="peekSource('${p1}')">[${p1}]</span>`;
            });
            findingsList.appendChild(div);
        });
    }

    // Limitations
    const limList = document.getElementById('limitations-list');
    if (limList) {
        limList.innerHTML = '';
        report.limitations_or_assumptions.forEach(l => {
            const li = document.createElement('li');
            li.textContent = l;
            limList.appendChild(li);
        });
    }

    // Next steps
    const stepsList = document.getElementById('steps-list');
    if (stepsList) {
        stepsList.innerHTML = '';
        report.suggested_next_steps.forEach(s => {
            const li = document.createElement('li');
            li.textContent = s;
            stepsList.appendChild(li);
        });
    }

    // Sources
    const sourcesContainer = document.getElementById('sources-container');
    const sourcesCount = document.getElementById('sources-count');
    if (sourcesCount) sourcesCount.textContent = `${report.sources_used.length} Verified`;

    if (sourcesContainer) {
        sourcesContainer.innerHTML = '';
        report.sources_used.forEach(src => {
            const a = document.createElement('a');
            a.className = 'source-entry';
            a.id = `source-${src.source_id}`;
            a.href = src.url;
            a.target = '_blank';

            let domain = '';
            try { domain = new URL(src.url).hostname; } catch (e) { domain = src.url; }

            a.innerHTML = `
                <div class="source-header-row">
                    <span class="source-tag">[${src.source_id}]</span>
                    <span class="source-score">${Math.round(src.relevance_score * 100)}% match</span>
                </div>
                <div class="source-title-text">${src.title}</div>
                <div class="source-snippet-text">${src.snippet}</div>
                <div class="source-domain-link">${domain} ↗</div>
            `;
            sourcesContainer.appendChild(a);
        });
    }

    // Telemetry
    const telemetryBox = document.getElementById('telemetry-box');
    if (telemetryBox && report.trace) {
        const t = report.trace;
        telemetryBox.innerHTML = `
            <div class="telemetry-item"><span class="telemetry-name">Total Latency:</span><span class="telemetry-data">${t.total_duration_seconds}s</span></div>
            <div class="telemetry-item"><span class="telemetry-name">Tools Executed:</span><span class="telemetry-data">${t.tools_called} (${t.tools_succeeded} success)</span></div>
            <div class="telemetry-item"><span class="telemetry-name">Sources Retrieved:</span><span class="telemetry-data">${t.sources_retrieved}</span></div>
            <div class="telemetry-item"><span class="telemetry-name">Noise Filtered:</span><span class="telemetry-data">${t.sources_filtered_out} sources</span></div>
            <div class="telemetry-item"><span class="telemetry-name">Token Estimate:</span><span class="telemetry-data">~${t.tokens_estimated}</span></div>
        `;
    }

    // Baseline contrast
    const baselineWrap = document.getElementById('baseline-wrap');
    if (baselineWrap) {
        if (baseline) {
            baselineWrap.style.display = 'block';
            document.getElementById('baseline-text').textContent = baseline.raw_output;
        } else {
            baselineWrap.style.display = 'none';
        }
    }
}

function focusSource(sourceId) {
    document.querySelectorAll('.source-entry').forEach(e => e.classList.remove('highlighted'));
    const target = document.getElementById(`source-${sourceId}`);
    if (target) {
        target.classList.add('highlighted');
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function peekSource(sourceId) {
    const target = document.getElementById(`source-${sourceId}`);
    if (target) {
        target.classList.add('highlighted');
        setTimeout(() => target.classList.remove('highlighted'), 1200);
    }
}

// Local Storage History
function saveHistoryEntry(query, report) {
    let history = JSON.parse(localStorage.getItem('omni_inquiries') || '[]');
    history = history.filter(h => h.query !== query);
    history.unshift({ query: query, report: report, date: new Date().toLocaleDateString() });
    if (history.length > 15) history.pop();
    localStorage.setItem('omni_inquiries', JSON.stringify(history));
    initHistory();
}

function initHistory() {
    const history = JSON.parse(localStorage.getItem('omni_inquiries') || '[]');
    const container = document.getElementById('inquiry-list');
    if (!container) return;
    container.innerHTML = '';

    history.forEach(item => {
        const li = document.createElement('li');
        li.className = 'inquiry-item';
        li.textContent = item.query;
        li.onclick = () => {
            const input = document.getElementById('query-input');
            if (input) input.value = item.query;
            activeReport = item.report;
            renderDossier(item.report, null);
            document.getElementById('results-wrap').style.display = 'block';
        };
        container.appendChild(li);
    });
}

function copyMarkdown() {
    if (!activeReport) {
        showToast('No active report to copy.');
        return;
    }
    const r = activeReport;
    let md = `# Research Dossier: ${r.user_question}\n\n`;
    md += `## Executive Summary\n${r.short_answer}\n\n`;
    md += `## Key Findings\n` + r.key_findings.map(f => `- ${f}`).join('\n') + '\n\n';
    md += `## Sources Consulted\n` + r.sources_used.map(s => `- [${s.source_id}] ${s.title}: ${s.url}`).join('\n') + '\n\n';
    md += `## Confidence Level: ${r.confidence_level}\n${r.confidence_rationale}\n\n`;
    md += `## Limitations & Assumptions\n` + r.limitations_or_assumptions.map(l => `- ${l}`).join('\n') + '\n\n';
    md += `## Strategic Next Steps\n` + r.suggested_next_steps.map((n, i) => `${i + 1}. ${n}`).join('\n');

    navigator.clipboard.writeText(md).then(() => {
        showToast('Markdown copied to clipboard.');
    });
}

async function flushCache() {
    try {
        await fetch('/api/cache/clear', { method: 'POST' });
        showToast('Tool cache cleared.');
    } catch (e) {
        showToast('Failed to clear cache.');
    }
}

function openModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.add('active');
}

function closeModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.remove('active');
}

async function saveSettings() {
    const provider = document.getElementById('modal-provider').value;
    const gemini = document.getElementById('modal-gemini').value.trim();
    const openai = document.getElementById('modal-openai').value.trim();

    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: provider,
                gemini_api_key: gemini || null,
                openai_api_key: openai || null
            })
        });
        closeModal();
        fetchSystemStatus();
        showToast('Configuration updated.');
    } catch (e) {
        showToast('Failed to update config.');
    }
}
