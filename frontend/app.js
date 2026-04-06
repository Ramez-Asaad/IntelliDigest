/**
 * app.js — IntelliDigest Frontend Logic (v3)
 * Top-bar + drawer + centered content layout
 */

const API = '';
const state = { persona: 'casual_reader', summaryMode: 'brief', selectedFiles: [], articles: [], msgs: [] };
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

const el = {
    drawer: $('#drawer'), drawerBackdrop: $('#drawerBackdrop'),
    drawerClose: $('#drawerClose'), toolsBtn: $('#toolsBtn'), heroBtn: $('#heroBtn'),
    personaSelect: $('#personaSelect'), fileInput: $('#fileInput'),
    uploadZone: $('#uploadZone'), uploadStatus: $('#uploadStatus'),
    ingestBtn: $('#ingestBtn'), newsInput: $('#newsInput'), newsBtn: $('#newsBtn'),
    clearKbBtn: $('#clearKbBtn'), clearChatBtn: $('#clearChatBtn'),
    statChunks: $('#statChunks'), statDocs: $('#statDocs'), statArticles: $('#statArticles'), topStatChunks: $('#topStatChunks'),
    chatStream: $('#chatStream'), chatWelcome: $('#chatWelcome'),
    chatInput: $('#chatInput'), sendBtn: $('#sendBtn'), personaIndicator: $('#personaIndicator'),
    newsContainer: $('#newsContainer'), searchInput: $('#searchInput'),
    searchBtn: $('#searchBtn'), searchResults: $('#searchResults'),
    loadingOverlay: $('#loadingOverlay'), loadingText: $('#loadingText'),
    toastContainer: $('#toastContainer'),
    n8nEmail: $('#n8nEmail'), n8nPrompt: $('#n8nPrompt'),
    n8nAdminEmail: $('#n8nAdminEmail'), n8nHostGmail: $('#n8nHostGmail'), n8nMaxEmails: $('#n8nMaxEmails'),
    n8nWebhookUrl: $('#n8nWebhookUrl'),
    n8nTriggerBtn: $('#n8nTriggerBtn'), n8nStatus: $('#n8nStatus'),
};

document.addEventListener('DOMContentLoaded', () => {
    setupDrawer(); setupNav(); setupPersona();
    setupUpload(); setupNews(); setupChat();
    setupSearch(); setupSummary(); setupN8n(); refreshStats();
});

// ═══ DRAWER ═══
function setupDrawer() {
    const open = () => { el.drawer.classList.add('open'); el.drawerBackdrop.classList.add('open'); };
    const close = () => { el.drawer.classList.remove('open'); el.drawerBackdrop.classList.remove('open'); };
    el.toolsBtn.addEventListener('click', open);
    el.heroBtn.addEventListener('click', open);
    el.drawerClose.addEventListener('click', close);
    el.drawerBackdrop.addEventListener('click', close);
    el.clearKbBtn.addEventListener('click', async () => {
        if (!confirm('Clear all documents & articles?')) return;
        await api('/api/clear', { method: 'DELETE' }); toast('KB cleared.', 'info'); refreshStats();
    });
    el.clearChatBtn.addEventListener('click', async () => {
        state.msgs = []; renderChat();
        await api('/api/chat/clear', { method: 'DELETE' }); toast('Chat cleared.', 'info'); refreshStats();
    });
}

// ═══ NAV ═══
function setupNav() {
    $$('.nav-tab[data-tab]').forEach(b => b.addEventListener('click', () => go(b.dataset.tab)));
    $$('.bb-btn[data-tab]').forEach(b => b.addEventListener('click', () => go(b.dataset.tab)));
}
function go(name) {
    $$('.nav-tab[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    $$('.bb-btn[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    $$('.view').forEach(v => v.classList.toggle('view-active', v.id === name + 'View'));
}

// ═══ PERSONA ═══
const PL = {
    casual_reader: 'Casual Reader', tech_enthusiast: 'Tech Enthusiast',
    business_analyst: 'Business Analyst', academic_researcher: 'Academic Researcher',
    political_observer: 'Political Observer',
};
function setupPersona() {
    el.personaSelect.addEventListener('change', e => {
        state.persona = e.target.value;
        el.personaIndicator.textContent = PL[state.persona] || state.persona;
    });
    el.personaIndicator.textContent = PL[state.persona];
}

// ═══ UPLOAD ═══
function setupUpload() {
    el.uploadZone.addEventListener('click', () => el.fileInput.click());
    el.fileInput.addEventListener('change', e => { state.selectedFiles = Array.from(e.target.files); showFiles(); });
    el.uploadZone.addEventListener('dragover', e => { e.preventDefault(); el.uploadZone.classList.add('dragover'); });
    el.uploadZone.addEventListener('dragleave', () => el.uploadZone.classList.remove('dragover'));
    el.uploadZone.addEventListener('drop', e => {
        e.preventDefault(); el.uploadZone.classList.remove('dragover');
        state.selectedFiles = Array.from(e.dataTransfer.files); showFiles();
    });
    el.ingestBtn.addEventListener('click', ingest);
}
function showFiles() {
    if (state.selectedFiles.length) {
        el.uploadStatus.textContent = state.selectedFiles.map(f => f.name).join(', ');
        el.uploadStatus.hidden = false; el.ingestBtn.disabled = false;
    } else { el.uploadStatus.hidden = true; el.ingestBtn.disabled = true; }
}
async function ingest() {
    if (!state.selectedFiles.length) return;
    loading('Ingesting...'); let ok = 0, ch = 0;
    for (const f of state.selectedFiles) {
        try {
            const fd = new FormData(); fd.append('file', f);
            const r = await api('/api/upload', { method: 'POST', body: fd, raw: true });
            ok++; ch += r.chunks_ingested || 0;
        } catch (e) { toast(`${f.name}: ${e.message}`, 'error'); }
    }
    done(); if (ok) toast(`${ch} chunks from ${ok} file(s).`, 'success');
    state.selectedFiles = []; el.fileInput.value = ''; showFiles(); refreshStats();
}

// ═══ NEWS ═══
function setupNews() {
    el.newsBtn.addEventListener('click', fetchNews);
    el.newsInput.addEventListener('keydown', e => { if (e.key === 'Enter') fetchNews(); });
}
async function fetchNews() {
    const t = el.newsInput.value.trim(); if (!t) { toast('Enter a topic.', 'info'); return; }
    loading(`Fetching "${t}"...`);
    try {
        const r = await api('/api/news/search', { method: 'POST', body: JSON.stringify({ topic: t, max_articles: 5 }) });
        state.articles = r.articles || []; renderNews(); refreshStats();
        if (state.articles.length) { toast(`${state.articles.length} articles.`, 'success'); go('news'); }
        else toast('No articles found.', 'info');
    } catch (e) { toast(e.message, 'error'); }
    done();
}
function renderNews() {
    if (!state.articles.length) {
        el.newsContainer.innerHTML = '<div class="empty"><p>No articles yet. Open <b>Tools</b> to fetch news.</p></div>'; return;
    }
    el.newsContainer.innerHTML = state.articles.map(a => `
        <div class="card">
            <h4>${esc(a.title || 'Untitled')}</h4>
            <div class="meta">${esc(a.source || '')} &middot; ${(a.published_at || '').slice(0, 10)}</div>
            <div class="desc">${esc(a.description || '')}</div>
            ${a.url ? `<a href="${esc(a.url)}" target="_blank" rel="noopener" class="card-link">Read &rarr;</a>` : ''}
        </div>`).join('');
}

// ═══ CHAT ═══
function setupChat() {
    el.sendBtn.addEventListener('click', () => sendMessage());
    el.chatInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
}
async function sendMessage(txt) {
    const m = txt || el.chatInput.value.trim(); if (!m) return;
    el.chatInput.value = '';
    state.msgs.push({ role: 'user', content: m }); renderChat(); scroll();
    const dots = addDots(); el.sendBtn.disabled = true; el.chatInput.disabled = true;
    try {
        const r = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message: m, persona: state.persona }) });
        dots.remove();
        state.msgs.push({ role: 'assistant', content: r.answer, sources: r.sources || [], tools: r.tools_used || [] });
    } catch (e) {
        dots.remove();
        state.msgs.push({ role: 'assistant', content: `Error: ${e.message}`, sources: [], tools: [] });
    }
    renderChat(); scroll(); refreshStats();
    el.sendBtn.disabled = false; el.chatInput.disabled = false; el.chatInput.focus();
}
function renderChat() {
    const s = el.chatStream;
    if (!state.msgs.length) { s.innerHTML = ''; s.appendChild(mkWelcome()); return; }
    const w = s.querySelector('.welcome'); if (w) w.remove();
    s.innerHTML = state.msgs.map(m => {
        if (m.role === 'user') return `<div class="chat-msg user"><div class="msg-bubble">${esc(m.content)}</div></div>`;
        const src = (m.sources && m.sources.length) ? `<div class="msg-sources">${m.sources.filter(x => x.source || x.title).map(x => `<span class="source-tag">${x.url ? '🔗' : '📄'} ${esc(x.title || x.source || '')}</span>`).join('')}</div>` : '';
        const tl = (m.tools && m.tools.length) ? `<div class="msg-tools">${m.tools.join(' · ')}</div>` : '';
        return `<div class="chat-msg assistant"><div class="msg-bubble">${esc(m.content)}${src}${tl}</div></div>`;
    }).join('');
}
function mkWelcome() {
    const d = document.createElement('div'); d.className = 'centered';
    d.innerHTML = `<div class="welcome" id="chatWelcome">
        <div class="welcome-glow"></div>
        <div class="welcome-brand">🧠</div>
        <h3>Ask me anything</h3>
        <p>Your knowledge base is ready. Upload documents or fetch news to get started, then ask questions below.</p>
        <div class="chip-row">
            <button class="chip" onclick="sendMessage('What do you have in the knowledge base?')">What's in the KB?</button>
            <button class="chip" onclick="sendMessage('Summarize the key topics')">Summarize docs</button>
            <button class="chip" onclick="sendMessage('What are the latest developments?')">Latest news</button>
        </div></div>`;
    return d;
}
function addDots() {
    const d = document.createElement('div'); d.className = 'chat-msg assistant';
    d.innerHTML = '<div class="msg-bubble"><div class="thinking"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>';
    el.chatStream.appendChild(d); scroll(); return d;
}
function scroll() { requestAnimationFrame(() => { el.chatStream.scrollTop = el.chatStream.scrollHeight; }) }

// ═══ SEARCH ═══
function setupSearch() {
    el.searchBtn.addEventListener('click', doSearch);
    el.searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
}
async function doSearch() {
    const q = el.searchInput.value.trim(); if (!q) { toast('Enter a query.', 'info'); return; }
    loading('Searching...');
    try {
        const r = await api(`/api/search?q=${encodeURIComponent(q)}&k=5`);
        if (!r.results || !r.results.length) {
            el.searchResults.innerHTML = '<div class="empty"><p>No results found.</p></div>';
        } else {
            el.searchResults.innerHTML = r.results.map((s, i) => `
                <div class="card">
                    <h4>${esc(s.title || s.source || 'Result ' + (i + 1))}</h4>
                    <div class="meta">Source: ${esc(s.source || 'Unknown')}</div>
                    <div class="desc">${esc(s.content || '')}</div>
                    ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener" class="card-link">Source &rarr;</a>` : ''}
                </div>`).join('');
        }
    } catch (e) { toast(e.message, 'error'); }
    done();
}

// ═══ SUMMARY MODE ═══
function setupSummary() {
    $$('.switch-btn').forEach(b => b.addEventListener('click', () => {
        $$('.switch-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active'); state.summaryMode = b.dataset.mode;
    }));
}

// ═══ n8n INTEGRATION ═══
function setupN8n() {
    if (el.n8nTriggerBtn) {
        el.n8nTriggerBtn.addEventListener('click', triggerN8n);

        // Load saved state
        if (el.n8nWebhookUrl) el.n8nWebhookUrl.value = localStorage.getItem('n8n.webhook_url') || '';
        if (el.n8nAdminEmail) el.n8nAdminEmail.value = localStorage.getItem('n8n.admin_email') || '';
        if (el.n8nHostGmail) el.n8nHostGmail.value = localStorage.getItem('n8n.host_gmail') || '';
        if (el.n8nMaxEmails) el.n8nMaxEmails.value = localStorage.getItem('n8n.max_emails') || '10';
    }
    // Check n8n status on load
    checkN8nStatus();
}

async function checkN8nStatus() {
    try {
        const s = await api('/api/n8n/status');
        if (el.n8nStatus) {
            if (s.configured) {
                el.n8nStatus.textContent = 'Connected: ' + s.webhook_url;
                el.n8nStatus.hidden = false;
            }
        }
    } catch (e) { /* n8n not configured, that's fine */ }
}

async function triggerN8n() {
    const email = el.n8nEmail ? el.n8nEmail.value.trim() : '';
    const prompt = el.n8nPrompt ? el.n8nPrompt.value.trim() : '';
    const admin_email = el.n8nAdminEmail ? el.n8nAdminEmail.value.trim() : '';
    const host_gmail = el.n8nHostGmail ? el.n8nHostGmail.value.trim() : '';
    const max_emails = el.n8nMaxEmails ? parseInt(el.n8nMaxEmails.value) || 10 : 10;
    const webhook_url = el.n8nWebhookUrl ? el.n8nWebhookUrl.value.trim() : '';

    if (!email) { toast('Enter an email address.', 'info'); return; }
    if (!prompt) { toast('Enter what to analyze.', 'info'); return; }

    // Save state
    localStorage.setItem('n8n.webhook_url', webhook_url);
    localStorage.setItem('n8n.admin_email', admin_email);
    localStorage.setItem('n8n.host_gmail', host_gmail);
    localStorage.setItem('n8n.max_emails', max_emails);

    loading('Triggering n8n workflow...');
    try {
        const r = await api('/api/n8n/trigger', {
            method: 'POST',
            body: JSON.stringify({ email, prompt, admin_email, host_gmail, max_emails, webhook_url }),
        });
        toast('n8n workflow triggered! Results will appear in your KB.', 'success');
        if (el.n8nEmail) el.n8nEmail.value = '';
        if (el.n8nPrompt) el.n8nPrompt.value = '';
        // Refresh stats after a delay to catch ingested results
        setTimeout(refreshStats, 5000);
    } catch (e) {
        toast(e.message, 'error');
    }
    done();
}

// ═══ STATS ═══
async function refreshStats() {
    try {
        const s = await api('/api/stats');
        el.statChunks.textContent = s.total_chunks || 0;
        el.statDocs.textContent = s.doc_count || 0;
        el.statArticles.textContent = s.news_count || 0;
        if (el.topStatChunks) el.topStatChunks.textContent = s.total_chunks || 0;
    } catch (e) { console.warn(e); }
}

// ═══ UTILS ═══
async function api(path, o = {}) {
    const h = {}; if (!o.raw) h['Content-Type'] = 'application/json';
    const opts = { method: o.method || 'GET', headers: { ...h, ...o.headers } };
    if (o.body) { opts.body = o.body; if (o.raw) delete opts.headers['Content-Type']; }
    const res = await fetch(`${API}${path}`, opts);
    if (!res.ok) { let m = `HTTP ${res.status}`; try { const d = await res.json(); m = d.detail || m; } catch { } throw new Error(m); }
    return res.json();
}
function loading(t = 'Processing...') { el.loadingText.textContent = t; el.loadingOverlay.classList.add('visible'); }
function done() { el.loadingOverlay.classList.remove('visible'); }
function toast(m, type = 'info') {
    const t = document.createElement('div'); t.className = `toast ${type}`;
    t.innerHTML = `<span>${esc(m)}</span>`;
    el.toastContainer.appendChild(t);
    setTimeout(() => {
        t.style.opacity = '0'; t.style.transform = 'translateX(16px)';
        t.style.transition = 'all 200ms ease-out'; setTimeout(() => t.remove(), 200);
    }, 3500);
}
function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
