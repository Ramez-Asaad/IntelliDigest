/**
 * app.js — IntelliDigest Frontend Logic (v3)
 * Top-bar + drawer + centered content layout
 */

const API = '';
const TOKEN_KEY = 'intellidigest_access_token';
const USER_EMAIL_KEY = 'intellidigest_user_email';

function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
}
function setAuth(token, email) {
    sessionStorage.setItem(TOKEN_KEY, token);
    if (email) sessionStorage.setItem(USER_EMAIL_KEY, email);
}
function clearAuth() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_EMAIL_KEY);
}

const state = {
    persona: 'casual_reader', summaryMode: 'brief', selectedFiles: [], articles: [], msgs: [],
    supportSessionId: crypto.randomUUID(), supportMsgs: [], ticketCount: 0,
};
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let _appStarted = false;

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
    n8nWebhookUrl: $('#n8nWebhookUrl'),
    telegramChatId: $('#telegramChatId'),
    telegramVerifyBtn: $('#telegramVerifyBtn'),
    n8nStatus: $('#n8nStatus'),
    supportStream: $('#supportStream'), supportInput: $('#supportInput'), supportSend: $('#supportSend'),
    supportNewChat: $('#supportNewChat'), supportWelcome: $('#supportWelcome'),
    supportModalOverlay: $('#supportModalOverlay'), supportModalTitle: $('#supportModalTitle'),
    supportModalBody: $('#supportModalBody'), supportModalCancel: $('#supportModalCancel'),
    supportModalPrimary: $('#supportModalPrimary'),
    btnTickets: $('#btnTickets'), ticketBadge: $('#ticketBadge'),
    ticketsOverlay: $('#ticketsOverlay'), ticketsPanel: $('#ticketsPanel'), ticketsList: $('#ticketsList'),
    btnCloseTickets: $('#btnCloseTickets'),
};

function showAuthGate() {
    const g = $('#authGate');
    if (g) g.classList.remove('auth-gate--hidden');
}
function hideAuthGate() {
    const g = $('#authGate');
    if (g) g.classList.add('auth-gate--hidden');
}
function updateUserChrome() {
    const email = sessionStorage.getItem(USER_EMAIL_KEY);
    const lbl = $('#userEmailLabel');
    const lo = $('#logoutBtn');
    if (lbl) {
        lbl.textContent = email || '';
        lbl.hidden = !email;
    }
    if (lo) lo.hidden = !getToken();
}

function bootApp() {
    if (_appStarted) return;
    _appStarted = true;
    setupDrawer(); setupNav(); setupPersona();
    setupUpload(); setupNews(); setupChat();
    setupSearch(); setupSummary(); setupN8n(); setupTelegramMessageButtons();
    setupSupport(); setupTickets();
    refreshStats(); refreshTicketCount();
}

document.addEventListener('DOMContentLoaded', () => {
    initAuthFlow();
});

async function initAuthFlow() {
    const params = new URLSearchParams(window.location.search);
    const urlTok = params.get('token');
    const urlEmail = params.get('email');
    const urlAuthErr = params.get('auth_error');
    const recoveryTok = params.get('recovery');

    if (urlTok) {
        setAuth(urlTok, urlEmail || '');
        history.replaceState({}, document.title, window.location.pathname);
    } else if (urlAuthErr) {
        try {
            sessionStorage.setItem('intellidigest_oauth_err', decodeURIComponent(urlAuthErr.replace(/\+/g, ' ')));
        } catch (_) { /* ignore */ }
        history.replaceState({}, document.title, window.location.pathname);
    } else if (recoveryTok) {
        history.replaceState({}, document.title, window.location.pathname);
    }

    const authErr = $('#authError');
    const showErr = (m, asInfo) => {
        if (!authErr) return;
        authErr.textContent = m;
        authErr.hidden = false;
        authErr.classList.toggle('auth-error--info', !!asInfo);
    };
    const hideErr = () => {
        if (authErr) {
            authErr.hidden = true;
            authErr.classList.remove('auth-error--info');
        }
    };

    const pendingOauthErr = sessionStorage.getItem('intellidigest_oauth_err');
    if (pendingOauthErr) {
        showErr(pendingOauthErr);
        sessionStorage.removeItem('intellidigest_oauth_err');
    }

    $('#logoutBtn')?.addEventListener('click', () => {
        clearAuth();
        location.reload();
    });

    let cfg = { google_enabled: false, reset_email_configured: false };
    try {
        cfg = await fetch(`${API}/api/auth/config`).then(r => r.json());
    } catch (_) { /* offline */ }

    function applyAuthConfig() {
        const wrap = $('#authGoogleWrap');
        if (wrap && cfg.google_enabled) wrap.hidden = false;
        const forgot = $('#authForgotLink');
        if (forgot) forgot.hidden = !cfg.reset_email_configured;
    }

    if (recoveryTok) {
        showAuthGate();
        applyAuthConfig();
        const main = $('#authBlockMain');
        const forgot = $('#authBlockForgot');
        const rec = $('#authBlockRecovery');
        const hero = $('#authHeroBlock');
        if (main) main.hidden = true;
        if (forgot) forgot.hidden = true;
        if (rec) rec.hidden = false;
        if (hero) hero.hidden = true;
        const fl = $('#authForgotLink');
        if (fl) fl.hidden = true;

        $('#recoverySubmitBtn')?.addEventListener('click', async () => {
            const pw = ($('#recoveryPassword') || {}).value || '';
            hideErr();
            if (!pw || pw.length < 8) {
                showErr('Enter a password of at least 8 characters.');
                return;
            }
            try {
                const res = await fetch(`${API}/api/auth/reset-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: recoveryTok, new_password: pw }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const d = data.detail;
                    showErr(typeof d === 'string' ? d : `HTTP ${res.status}`);
                    return;
                }
                setAuth(data.access_token, data.user?.email);
                hideAuthGate();
                updateUserChrome();
                bootApp();
            } catch (e) {
                showErr(e.message || 'Request failed');
            }
        });
        return;
    }

    let authMode = 'signin';
    const headline = $('#authHeadline');
    const submitLabel = $('.auth-btn-primary-label');
    const tabSignIn = $('#authTabSignIn');
    const tabReg = $('#authTabRegister');
    const switchText = $('#authSwitchText');
    const switchBtn = $('#authSwitchBtn');

    function setAuthMode(mode) {
        authMode = mode;
        const isIn = mode === 'signin';
        tabSignIn?.classList.toggle('is-active', isIn);
        tabReg?.classList.toggle('is-active', !isIn);
        tabSignIn?.setAttribute('aria-selected', String(isIn));
        tabReg?.setAttribute('aria-selected', String(!isIn));
        if (headline) headline.textContent = isIn ? 'Welcome back' : 'Create your account';
        if (submitLabel) submitLabel.textContent = isIn ? 'Sign in' : 'Create account';
        if (switchText && switchBtn) {
            if (isIn) {
                switchText.textContent = 'New here?';
                switchBtn.textContent = 'Create an account';
            } else {
                switchText.textContent = 'Already have an account?';
                switchBtn.textContent = 'Sign in';
            }
        }
    }

    tabSignIn?.addEventListener('click', () => { hideErr(); setAuthMode('signin'); });
    tabReg?.addEventListener('click', () => { hideErr(); setAuthMode('register'); });
    switchBtn?.addEventListener('click', () => {
        hideErr();
        setAuthMode(authMode === 'signin' ? 'register' : 'signin');
    });

    applyAuthConfig();

    $('#authForgotLink')?.addEventListener('click', () => {
        hideErr();
        const main = $('#authBlockMain');
        const fb = $('#authBlockForgot');
        const hero = $('#authHeroBlock');
        if (main) main.hidden = true;
        if (fb) fb.hidden = false;
        if (hero) hero.hidden = true;
        const fe = $('#forgotEmail');
        const ae = $('#authEmail');
        if (fe && ae) fe.value = ae.value || '';
    });
    $('#forgotBackBtn')?.addEventListener('click', () => {
        hideErr();
        const main = $('#authBlockMain');
        const fb = $('#authBlockForgot');
        const hero = $('#authHeroBlock');
        if (main) main.hidden = false;
        if (fb) fb.hidden = true;
        if (hero) hero.hidden = false;
    });
    $('#forgotSendBtn')?.addEventListener('click', async () => {
        const email = ($('#forgotEmail') || {}).value?.trim() || '';
        hideErr();
        if (!email) {
            showErr('Enter your email.');
            return;
        }
        try {
            const res = await fetch(`${API}/api/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                showErr(data.detail || `HTTP ${res.status}`);
                return;
            }
            showErr(data.message || 'Check your email for next steps.', true);
        } catch (e) {
            showErr(e.message || 'Request failed');
        }
    });

    const submitAuth = async (isRegister) => {
        const email = ($('#authEmail') || {}).value?.trim() || '';
        const password = ($('#authPassword') || {}).value || '';
        hideErr();
        if (!email || !password) {
            showErr('Enter email and password.');
            return;
        }
        const path = isRegister ? '/api/auth/register' : '/api/auth/login';
        const body = { email, password };
        try {
            const res = await fetch(`${API}${path}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const d = data.detail;
                showErr(typeof d === 'string' ? d : (Array.isArray(d) ? d.map(x => x.msg || x).join(' ') : `HTTP ${res.status}`));
                return;
            }
            setAuth(data.access_token, data.user?.email);
            hideAuthGate();
            updateUserChrome();
            bootApp();
        } catch (e) {
            showErr(e.message || 'Request failed');
        }
    };

    $('#authSubmitBtn')?.addEventListener('click', () => submitAuth(authMode === 'register'));
    const submitOnEnter = (e) => {
        if (e.key === 'Enter') submitAuth(authMode === 'register');
    };
    $('#authEmail')?.addEventListener('keydown', submitOnEnter);
    $('#authPassword')?.addEventListener('keydown', submitOnEnter);

    if (!getToken()) {
        showAuthGate();
        setAuthMode('signin');
        return;
    }
    try {
        await api('/api/stats');
    } catch {
        clearAuth();
        showAuthGate();
        setAuthMode('signin');
        return;
    }
    hideAuthGate();
    updateUserChrome();
    bootApp();
}

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
    s.innerHTML = state.msgs.map((m, i) => {
        if (m.role === 'user') return `<div class="chat-msg user"><div class="msg-bubble">${esc(m.content)}</div></div>`;
        const src = (m.sources && m.sources.length) ? `<div class="msg-sources">${m.sources.filter(x => x.source || x.title).map(x => `<span class="source-tag">${x.url ? '🔗' : '📄'} ${esc(x.title || x.source || '')}</span>`).join('')}</div>` : '';
        const tl = (m.tools && m.tools.length) ? `<div class="msg-tools">${m.tools.join(' · ')}</div>` : '';
        const err = (m.content || '').startsWith('Error:');
        const tg = !err ? `<div class="msg-actions"><button type="button" class="btn-tg" data-tg-ctx="chat" data-tg-idx="${i}">Send to Telegram</button></div>` : '';
        return `<div class="chat-msg assistant"><div class="msg-bubble">${esc(m.content)}${src}${tl}</div>${tg}</div>`;
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

// ═══ SUPPORT & TICKETS ═══
let supportModalCallback = null;

function setupSupport() {
    if (!el.supportSend || !el.supportInput) return;
    el.supportSend.addEventListener('click', () => sendSupportMessage());
    el.supportInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendSupportMessage(); }
    });
    if (el.supportNewChat) el.supportNewChat.addEventListener('click', () => promptNewSupportChat());
    if (el.supportModalCancel) el.supportModalCancel.addEventListener('click', closeSupportModal);
    if (el.supportModalPrimary) el.supportModalPrimary.addEventListener('click', onSupportModalPrimary);
    if (el.supportModalOverlay) {
        el.supportModalOverlay.addEventListener('click', e => {
            if (e.target === el.supportModalOverlay) closeSupportModal();
        });
    }
    if (el.supportStream) el.supportStream.addEventListener('click', onSupportTicketActionClick);
    document.querySelectorAll('.support-chips .chip[data-support-msg]').forEach(btn => {
        btn.addEventListener('click', () => {
            const m = btn.getAttribute('data-support-msg');
            if (m && el.supportInput) { el.supportInput.value = m; sendSupportMessage(); }
        });
    });
}

function openSupportModal({ title, bodyHtml, primaryLabel = 'Confirm', onPrimary }) {
    if (!el.supportModalOverlay || !el.supportModalTitle || !el.supportModalBody || !el.supportModalPrimary) return;
    el.supportModalTitle.textContent = title;
    el.supportModalBody.innerHTML = bodyHtml;
    el.supportModalPrimary.textContent = primaryLabel;
    supportModalCallback = onPrimary || null;
    el.supportModalOverlay.classList.add('active');
    el.supportModalOverlay.setAttribute('aria-hidden', 'false');
}

function closeSupportModal() {
    if (!el.supportModalOverlay) return;
    el.supportModalOverlay.classList.remove('active');
    el.supportModalOverlay.setAttribute('aria-hidden', 'true');
    supportModalCallback = null;
    if (el.supportModalBody) el.supportModalBody.innerHTML = '';
}

async function onSupportModalPrimary() {
    if (!supportModalCallback) {
        closeSupportModal();
        return;
    }
    try {
        await supportModalCallback();
        closeSupportModal();
    } catch (e) {
        toast(String(e.message || e), 'error');
    }
}

function onSupportTicketActionClick(e) {
    const btn = e.target.closest('.btn-ticket-act');
    if (!btn) return;
    const act = btn.getAttribute('data-support-act');
    const tid = btn.getAttribute('data-ticket-id');
    if (act === 'new_ticket') {
        e.preventDefault();
        promptNewSupportChat();
    } else if (act === 'close_ticket' && tid) {
        e.preventDefault();
        promptCloseTicketConfirm(tid);
    } else if (act === 'edit_ticket' && tid) {
        e.preventDefault();
        promptEditTicketConfirm(tid);
    }
}

function promptNewSupportChat() {
    openSupportModal({
        title: 'Start a new support chat?',
        bodyHtml: '<p>This clears the conversation in this tab. Your existing tickets stay in the Tickets panel.</p>',
        primaryLabel: 'Confirm — new chat',
        onPrimary: runClearSupportSession,
    });
}

async function runClearSupportSession() {
    try {
        await api('/api/support/sessions/clear', {
            method: 'POST',
            body: JSON.stringify({ session_id: state.supportSessionId }),
        });
    } catch (_) { /* session may not exist server-side */ }
    state.supportSessionId = crypto.randomUUID();
    state.supportMsgs = [];
    renderSupportChat();
    const list = document.getElementById('supportMsgList');
    if (list) list.innerHTML = '';
    if (el.supportWelcome) el.supportWelcome.style.display = '';
    toast('Support conversation cleared.', 'info');
}

async function promptToolbarCloseTicket() {
    let tickets = [];
    try {
        const d = await api('/api/tickets');
        tickets = d.tickets || [];
    } catch (e) {
        toast(e.message, 'error');
        return;
    }
    if (!tickets.length) {
        toast('No tickets yet.', 'info');
        return;
    }
    const opts = tickets.map(t => {
        const sum = (t.issue_summary || '').slice(0, 72);
        return `<option value="${esc(t.id)}">${esc(t.id)} — ${esc(t.status)} — ${esc(sum)}</option>`;
    }).join('');
    openSupportModal({
        title: 'Close a ticket',
        bodyHtml: `
            <p class="support-modal-hint">Confirm that the issue is resolved, then close the ticket.</p>
            <label for="supportModalTicketSelect">Ticket</label>
            <select id="supportModalTicketSelect">${opts}</select>
            <label for="supportModalResolutionNote">Resolution note (optional)</label>
            <textarea id="supportModalResolutionNote" placeholder="Briefly how it was fixed"></textarea>`,
        primaryLabel: 'Confirm — close ticket',
        onPrimary: async () => {
            const sel = document.getElementById('supportModalTicketSelect');
            const tid = sel && sel.value;
            if (!tid) throw new Error('Pick a ticket.');
            const note = (document.getElementById('supportModalResolutionNote') || {}).value?.trim() || '';
            await api(`/api/tickets/${encodeURIComponent(tid)}/close`, {
                method: 'POST',
                body: JSON.stringify({ resolution_note: note }),
            });
            toast('Ticket closed.', 'success');
            refreshTicketCount();
        },
    });
}

function buildTicketEditForm(t) {
    const pr = ['Critical', 'High', 'Medium', 'Low'].map(p =>
        `<option value="${esc(p)}"${(t.priority || '') === p ? ' selected' : ''}>${esc(p)}</option>`
    ).join('');
    return `
        <p class="support-modal-hint">Change any fields, then confirm to save.</p>
        <label for="supportEditName">Name on ticket</label>
        <input type="text" id="supportEditName" value="${esc(t.customer_name || '')}" autocomplete="off">
        <label for="supportEditSummary">Issue summary</label>
        <textarea id="supportEditSummary">${esc(t.issue_summary || '')}</textarea>
        <label for="supportEditCategory">Category</label>
        <input type="text" id="supportEditCategory" value="${esc(t.category || '')}" autocomplete="off">
        <label for="supportEditPriority">Priority</label>
        <select id="supportEditPriority">${pr}</select>
        <label for="supportEditSuggested">Suggested solution / notes</label>
        <textarea id="supportEditSuggested">${esc(t.suggested_solution || '')}</textarea>`;
}

function collectTicketEditPatch(t) {
    const body = {};
    const name = (document.getElementById('supportEditName') || {}).value?.trim() ?? '';
    const summary = (document.getElementById('supportEditSummary') || {}).value?.trim() ?? '';
    const cat = (document.getElementById('supportEditCategory') || {}).value?.trim() ?? '';
    const prio = (document.getElementById('supportEditPriority') || {}).value?.trim() ?? '';
    const sugg = (document.getElementById('supportEditSuggested') || {}).value?.trim() ?? '';
    if (name !== (t.customer_name || '').trim()) body.customer_name = name;
    if (summary !== (t.issue_summary || '').trim()) body.issue_summary = summary;
    if (cat !== (t.category || '').trim()) body.category = cat;
    if (prio !== (t.priority || '').trim()) body.priority = prio;
    if (sugg !== (t.suggested_solution || '').trim()) body.suggested_solution = sugg;
    return body;
}

async function promptToolbarEditTicket() {
    let tickets = [];
    try {
        const d = await api('/api/tickets');
        tickets = d.tickets || [];
    } catch (e) {
        toast(e.message, 'error');
        return;
    }
    if (!tickets.length) {
        toast('No tickets yet.', 'info');
        return;
    }
    const opts = tickets.map(t => {
        const sum = (t.issue_summary || '').slice(0, 56);
        return `<option value="${esc(t.id)}">${esc(t.id)} — ${esc(sum)}</option>`;
    }).join('');
    openSupportModal({
        title: 'Edit a ticket',
        bodyHtml: `
            <label for="supportEditPick">Ticket</label>
            <select id="supportEditPick"><option value="">— Choose —</option>${opts}</select>
            <div id="supportEditFormMount"></div>`,
        primaryLabel: 'Confirm — save changes',
        onPrimary: async () => {
            const pick = document.getElementById('supportEditPick');
            const tid = pick && pick.value;
            if (!tid) throw new Error('Choose a ticket.');
            const t = tickets.find(x => x.id === tid);
            if (!t) throw new Error('Ticket not found.');
            const patch = collectTicketEditPatch(t);
            if (!Object.keys(patch).length) throw new Error('Change at least one field.');
            await api(`/api/tickets/${encodeURIComponent(tid)}`, {
                method: 'PATCH',
                body: JSON.stringify(patch),
            });
            toast('Ticket updated.', 'success');
            refreshTicketCount();
        },
    });
    const pick = document.getElementById('supportEditPick');
    const mount = document.getElementById('supportEditFormMount');
    if (pick && mount) {
        pick.addEventListener('change', () => {
            const tid = pick.value;
            const t = tickets.find(x => x.id === tid);
            mount.innerHTML = t ? buildTicketEditForm(t) : '';
        });
    }
}

async function promptCloseTicketConfirm(ticketId) {
    openSupportModal({
        title: 'Close ticket?',
        bodyHtml: `
            <p class="support-modal-hint">Confirm that <strong>${esc(ticketId)}</strong> is resolved.</p>
            <label for="supportModalResolutionNote">Resolution note (optional)</label>
            <textarea id="supportModalResolutionNote" placeholder="Briefly how it was fixed"></textarea>`,
        primaryLabel: 'Confirm — close ticket',
        onPrimary: async () => {
            const note = (document.getElementById('supportModalResolutionNote') || {}).value?.trim() || '';
            await api(`/api/tickets/${encodeURIComponent(ticketId)}/close`, {
                method: 'POST',
                body: JSON.stringify({ resolution_note: note }),
            });
            toast('Ticket closed.', 'success');
            refreshTicketCount();
        },
    });
}

async function promptEditTicketConfirm(ticketId) {
    let t;
    try {
        const d = await api(`/api/tickets/${encodeURIComponent(ticketId)}`);
        t = d.ticket;
    } catch (e) {
        toast(e.message, 'error');
        return;
    }
    openSupportModal({
        title: `Edit ${esc(ticketId)}`,
        bodyHtml: buildTicketEditForm(t),
        primaryLabel: 'Confirm — save changes',
        onPrimary: async () => {
            const patch = collectTicketEditPatch(t);
            if (!Object.keys(patch).length) throw new Error('Change at least one field.');
            await api(`/api/tickets/${encodeURIComponent(ticketId)}`, {
                method: 'PATCH',
                body: JSON.stringify(patch),
            });
            toast('Ticket updated.', 'success');
            refreshTicketCount();
        },
    });
}

function renderTicketActionButtons(actions, msgIdx) {
    if (!actions || !actions.length) return '';
    const parts = [];
    for (let i = 0; i < actions.length; i++) {
        const a = actions[i];
        if (a.kind === 'new_ticket') {
            parts.push(`<button type="button" class="btn-ticket-act" data-support-act="new_ticket" data-msg-idx="${msgIdx}">${esc(a.label)}</button>`);
        } else if ((a.kind === 'close_ticket' || a.kind === 'edit_ticket') && a.ticket_id) {
            parts.push(`<button type="button" class="btn-ticket-act" data-support-act="${esc(a.kind)}" data-ticket-id="${esc(a.ticket_id)}" data-msg-idx="${msgIdx}">${esc(a.label)}</button>`);
        }
    }
    if (!parts.length) return '';
    return `<div class="support-ticket-actions">${parts.join('')}</div>`;
}

function ensureSupportMsgList() {
    const centered = el.supportStream.querySelector('.centered');
    let list = document.getElementById('supportMsgList');
    if (!list && centered) {
        list = document.createElement('div');
        list.id = 'supportMsgList';
        list.className = 'support-msg-list';
        centered.appendChild(list);
    }
    return list;
}

function renderSupportChat() {
    if (!el.supportStream) return;
    if (!state.supportMsgs.length) {
        if (el.supportWelcome) el.supportWelcome.style.display = '';
        const list = document.getElementById('supportMsgList');
        if (list) list.innerHTML = '';
        return;
    }
    if (el.supportWelcome) el.supportWelcome.style.display = 'none';
    const list = ensureSupportMsgList();
    if (!list) return;
    list.innerHTML = state.supportMsgs.map((m, i) => {
        if (m.role === 'user') {
            return `<div class="chat-msg user"><div class="msg-bubble">${esc(m.content)}</div></div>`;
        }
        const err = (m.content || '').startsWith('Error:');
        const acts = !err ? renderTicketActionButtons(m.ticketActions, i) : '';
        const tg = !err ? `<div class="msg-actions"><button type="button" class="btn-tg" data-tg-ctx="support" data-tg-idx="${i}">Send to Telegram</button></div>` : '';
        return `<div class="chat-msg assistant"><div class="msg-bubble">${formatSupportAssistant(m.content)}</div>${acts}${tg}</div>`;
    }).join('');
    scrollSupportToBottom();
}

function formatSupportAssistant(text) {
    return esc(text || '').replace(/\n/g, '<br>');
}

function scrollSupportToBottom() {
    requestAnimationFrame(() => {
        if (el.supportStream) el.supportStream.scrollTop = el.supportStream.scrollHeight;
    });
}

async function sendSupportMessage(txt) {
    if (!el.supportInput || !el.supportSend) return;
    const m = (txt || el.supportInput.value || '').trim();
    if (!m) return;
    el.supportInput.value = '';
    state.supportMsgs.push({ role: 'user', content: m });
    renderSupportChat();
    const list = ensureSupportMsgList();
    const dots = document.createElement('div');
    dots.className = 'chat-msg assistant';
    dots.innerHTML = '<div class="msg-bubble"><div class="thinking"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>';
    if (list) list.appendChild(dots);
    scrollSupportToBottom();
    el.supportSend.disabled = true; el.supportInput.disabled = true;
    try {
        const r = await api('/api/support/chat', {
            method: 'POST',
            body: JSON.stringify({ message: m, session_id: state.supportSessionId }),
        });
        state.supportSessionId = r.session_id;
        dots.remove();
        state.supportMsgs.push({
            role: 'assistant',
            content: r.response,
            ticketActions: r.ticket_actions || [],
        });
    } catch (e) {
        dots.remove();
        state.supportMsgs.push({ role: 'assistant', content: `Error: ${e.message}` });
    }
    renderSupportChat();
    refreshTicketCount();
    el.supportSend.disabled = false; el.supportInput.disabled = false; el.supportInput.focus();
}

function setupTickets() {
    if (!el.btnTickets || !el.ticketsPanel) return;
    el.btnTickets.addEventListener('click', openTicketsPanel);
    if (el.btnCloseTickets) el.btnCloseTickets.addEventListener('click', closeTicketsPanel);
    if (el.ticketsOverlay) el.ticketsOverlay.addEventListener('click', closeTicketsPanel);
}

function openTicketsPanel() {
    el.ticketsPanel.classList.add('active');
    el.ticketsOverlay.classList.add('active');
    el.ticketsOverlay.setAttribute('aria-hidden', 'false');
    loadTickets();
}

function closeTicketsPanel() {
    el.ticketsPanel.classList.remove('active');
    el.ticketsOverlay.classList.remove('active');
    el.ticketsOverlay.setAttribute('aria-hidden', 'true');
}

async function loadTickets() {
    if (!el.ticketsList) return;
    try {
        const data = await api('/api/tickets');
        renderTickets(data.tickets || []);
    } catch (_) {
        el.ticketsList.innerHTML = '<div class="tickets-empty">Could not load tickets.</div>';
    }
}

function renderTickets(tickets) {
    if (!tickets || !tickets.length) {
        el.ticketsList.innerHTML = '<div class="tickets-empty">No tickets yet. They appear when the assistant creates one.</div>';
        return;
    }
    el.ticketsList.innerHTML = tickets.map(t => {
        const pr = `priority-${(t.priority || 'medium').toLowerCase().replace(/\s+/g, '-')}`;
        const date = t.created_at ? new Date(t.created_at).toLocaleString() : '';
        return `
            <div class="ticket-item">
                <div class="ticket-item-header">
                    <span class="ticket-id">${esc(t.id)}</span>
                    <span class="ticket-status-badge open">${esc(t.status)}</span>
                </div>
                <p class="ticket-item-summary">${esc(t.issue_summary)}</p>
                <div class="ticket-item-meta">
                    <span class="ticket-meta-tag">${esc(t.category)}</span>
                    <span class="ticket-meta-tag ${pr}">${esc(t.priority)}</span>
                    <span class="ticket-meta-tag">${esc(date)}</span>
                </div>
            </div>`;
    }).join('');
}

async function refreshTicketCount() {
    if (!el.ticketBadge) return;
    try {
        const d = await api('/api/tickets');
        const c = d.count || 0;
        el.ticketBadge.textContent = c;
        el.ticketBadge.hidden = c === 0;
        state.ticketCount = c;
    } catch (_) { /* ignore */ }
}

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

// ═══ n8n → Telegram ═══
function setupN8n() {
    if (el.n8nWebhookUrl) el.n8nWebhookUrl.value = localStorage.getItem('n8n.webhook_url') || '';
    if (el.telegramChatId) el.telegramChatId.value = localStorage.getItem('telegram.chat_id') || '';
    if (el.telegramVerifyBtn) el.telegramVerifyBtn.addEventListener('click', sendTelegramVerify);
    checkN8nStatus();
}

function setupTelegramMessageButtons() {
    if (el.chatStream) el.chatStream.addEventListener('click', onTelegramButtonClick);
    if (el.supportStream) el.supportStream.addEventListener('click', onTelegramButtonClick);
}

function onTelegramButtonClick(e) {
    const btn = e.target.closest('.btn-tg[data-tg-ctx]');
    if (!btn) return;
    const ctx = btn.getAttribute('data-tg-ctx');
    const idx = parseInt(btn.getAttribute('data-tg-idx'), 10);
    if (ctx === 'chat' || ctx === 'support') forwardAssistantToTelegram(ctx, idx);
}

function persistTelegramSettings() {
    if (el.n8nWebhookUrl) localStorage.setItem('n8n.webhook_url', el.n8nWebhookUrl.value.trim());
    if (el.telegramChatId) localStorage.setItem('telegram.chat_id', el.telegramChatId.value.trim());
}

async function checkN8nStatus() {
    try {
        const s = await api('/api/n8n/status');
        if (el.n8nStatus && s.configured) {
            el.n8nStatus.textContent = (s.source ? `${s.source}: ` : '') + (s.webhook_url || 'set');
            el.n8nStatus.hidden = false;
        }
    } catch (e) { /* optional */ }
}

async function sendTelegramVerify() {
    const webhook_url = el.n8nWebhookUrl ? el.n8nWebhookUrl.value.trim() : '';
    const telegram_chat_id = el.telegramChatId ? el.telegramChatId.value.trim() : '';
    if (!webhook_url) { toast('Enter your n8n webhook URL.', 'info'); return; }
    if (!telegram_chat_id) { toast('Enter your Telegram chat ID.', 'info'); return; }
    persistTelegramSettings();
    loading('Calling n8n…');
    try {
        await api('/api/n8n/telegram', {
            method: 'POST',
            body: JSON.stringify({
                webhook_url,
                telegram_chat_id,
                action: 'verify_telegram',
                assistant_message: 'IntelliDigest: your Telegram link works. Saved replies will arrive here.',
                channel: 'research_chat',
            }),
        });
        toast('Check Telegram for the test message.', 'success');
    } catch (e) {
        toast(e.message, 'error');
    }
    done();
}

async function forwardAssistantToTelegram(ctx, msgIndex) {
    const webhook_url = el.n8nWebhookUrl ? el.n8nWebhookUrl.value.trim() : '';
    const telegram_chat_id = el.telegramChatId ? el.telegramChatId.value.trim() : '';
    if (!webhook_url) {
        toast('Add your n8n webhook URL in Tools.', 'info');
        el.toolsBtn && el.toolsBtn.click();
        return;
    }
    if (!telegram_chat_id) {
        toast('Add your Telegram chat ID in Tools.', 'info');
        el.toolsBtn && el.toolsBtn.click();
        return;
    }
    persistTelegramSettings();

    let assistant_message = '';
    let user_message = '';
    let persona = state.persona;
    let channel = 'research_chat';

    if (ctx === 'chat') {
        const m = state.msgs[msgIndex];
        if (!m || m.role !== 'assistant') return;
        assistant_message = m.content;
        if (msgIndex > 0 && state.msgs[msgIndex - 1].role === 'user') {
            user_message = state.msgs[msgIndex - 1].content;
        }
    } else {
        const m = state.supportMsgs[msgIndex];
        if (!m || m.role !== 'assistant') return;
        assistant_message = m.content;
        channel = 'support_chat';
        persona = '';
        if (msgIndex > 0 && state.supportMsgs[msgIndex - 1].role === 'user') {
            user_message = state.supportMsgs[msgIndex - 1].content;
        }
    }

    if ((assistant_message || '').startsWith('Error:')) {
        toast('Cannot send error messages to Telegram.', 'info');
        return;
    }

    loading('Sending to Telegram…');
    try {
        await api('/api/n8n/telegram', {
            method: 'POST',
            body: JSON.stringify({
                webhook_url,
                telegram_chat_id,
                action: 'save_message',
                assistant_message,
                user_message,
                persona,
                channel,
            }),
        });
        toast('Sent via n8n. Check Telegram.', 'success');
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
    const tok = getToken();
    if (tok && !o.skipAuth) h['Authorization'] = `Bearer ${tok}`;
    const opts = { method: o.method || 'GET', headers: { ...h, ...o.headers } };
    if (o.body) { opts.body = o.body; if (o.raw) delete opts.headers['Content-Type']; }
    const res = await fetch(`${API}${path}`, opts);
    if (res.status === 401 && getToken()) {
        clearAuth();
        location.reload();
        return {};
    }
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
