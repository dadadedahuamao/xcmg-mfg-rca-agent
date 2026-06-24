
/* ====== SCRIPT_BLOCK ====== */
(function () {
  'use strict';

  // ============ 常量 ============
  var API_BASE = '/api/v1/rca';
  var CHAT_API_BASE = '/api/v1/chat';
  var ANALYZE_TIMEOUT_MS = 120000;

  var STORAGE_KEYS = {
    SESSIONS: 'rca_sessions',
    CURRENT: 'rca_current_session',
    LOGIN: 'rca_logged_in'
  };

  var ANOMALY_TYPES = {
    overstation_check:   '超站检查',
    equipment_conflict:  '设备冲突',
    material_shortage:   '物料短缺',
    quality_abnormal:    '质量异常',
    interface_timeout:   '接口超时',
    schedule_risk:       '排程风险'
  };

  var ANOMALY_TEMPLATES = {
    overstation_check:  '工位 WS-03 连续 3 小时超站，影响下游 5 个工位',
    equipment_conflict: '设备 EQ-01 与 EQ-02 在排程中存在时间冲突',
    material_shortage:  '物料 MAT-001 库存不足，影响工单 WO-2024-001',
    quality_abnormal:   '产品 PROD-A 批次 BATCH-001 质量检测不合格',
    interface_timeout:  'MES 与 APS 接口同步超时，持续 30 分钟',
    schedule_risk:      '排程计划 PLAN-2024-06-21 存在产能不足风险'
  };

  var STATUS_LABELS = {
    confirmed: { text: '✅ 已确认', cls: 'confirmed' },
    rejected:  { text: '❌ 已排除', cls: 'rejected' },
    pending:   { text: '🔍 待验证', cls: 'pending' }
  };

  // RCA 工作流 8 节点 -> 中文标题（供进度时间线渲染使用）。
  // 节点键必须与后端 rca_step_events.node_name 保持一致。
  var RCA_PROGRESS_STEPS = {
    analyze_symptom:     '分析异常症状',
    generate_hypotheses: '生成根因假设',
    select_tool:         '选择查询工具',
    execute_tool:        '执行工具调用',
    observe_evidence:    '观察证据结果',
    draft_rca:           '起草根因结论',
    reflect:             '反思与校核',
    generate_report:     '生成分析报告'
  };

  // 8 节点的展示顺序（与 RCA_PROGRESS_STEPS 的 key 对齐）。
  var RCA_PROGRESS_STEP_ORDER = [
    'analyze_symptom',
    'generate_hypotheses',
    'select_tool',
    'execute_tool',
    'observe_evidence',
    'draft_rca',
    'reflect',
    'generate_report'
  ];

  // ============ 状态 ============
  var state = {
    sessions: [],
    sessionsLoadError: null,
    currentSessionId: null,
    draftSession: null,
    isLoading: false,
    abortController: null,
    selectedAnomalyType: null,
    searchKeyword: '',
    modalSearchKeyword: '',
    modalOpen: false,
    activeMenuSessionId: null,
    pendingDeleteSessionId: null,
    pendingRenameSessionId: null,
    editingMessageId: null,
    copiedMessageId: null,
    copiedTimer: null,
    collapsedSessionGroups: {},
    sidebarCollapsed: false,
    // 进度时间线状态（Task 6 脚手架，Task 7/8 接入 SSE 后填充）。
    // lastSeq: 已渲染的最大事件 seq，用于去重；steps: 各节点状态聚合；
    // expanded: 折叠卡片中各 step 的展开/折叠状态。
    progress: {
      lastSeq: 0,
      steps: {},
      expanded: {}
    }
  };

  // ============ DOM 引用 ============
  var dom = {};
  function cacheDom() {
    dom.loginView      = document.getElementById('loginView');
    dom.appView        = document.getElementById('appView');
    dom.loginForm      = document.getElementById('loginForm');
    dom.loginUsername  = document.getElementById('loginUsername');
    dom.loginPassword  = document.getElementById('loginPassword');
    dom.passwordToggle = document.getElementById('passwordToggle');
    dom.passwordEyeClosed = document.getElementById('passwordEyeClosed');
    dom.passwordEyeOpen = document.getElementById('passwordEyeOpen');
    dom.loginError     = document.getElementById('loginError');
    dom.loginSubmit    = document.getElementById('loginSubmit');
    dom.sidebar        = document.getElementById('sidebar');
    dom.sidebarToggleInner = document.getElementById('sidebarToggleInner');
    dom.sidebarToggleOuter = document.getElementById('sidebarToggleOuter');
    dom.newChatBtn     = document.getElementById('newChatBtn');
    dom.searchChatBtn  = document.getElementById('searchChatBtn');
    dom.sessionsList   = document.getElementById('sessionsList');
    dom.logoutBtn      = document.getElementById('logoutBtn');
    dom.searchModal        = document.getElementById('searchModal');
    dom.searchModalPanel   = document.getElementById('searchModalPanel');
    dom.modalSearchInput   = document.getElementById('modalSearchInput');
    dom.closeSearchModal   = document.getElementById('closeSearchModal');
    dom.searchModalResults = document.getElementById('searchModalResults');
    dom.renameDialog   = document.getElementById('renameDialog');
    dom.renameInput    = document.getElementById('renameInput');
    dom.renameCancelBtn = document.getElementById('renameCancelBtn');
    dom.renameConfirmBtn = document.getElementById('renameConfirmBtn');
    dom.deleteDialog   = document.getElementById('deleteDialog');
    dom.deleteDialogTitle = document.getElementById('deleteDialogTitle');
    dom.deleteCancelBtn = document.getElementById('deleteCancelBtn');
    dom.deleteConfirmBtn = document.getElementById('deleteConfirmBtn');
    dom.topbarTitle    = document.getElementById('topbarTitle');
    dom.messages       = document.getElementById('messages');
    dom.messagesWrap   = document.getElementById('messagesWrap');
    dom.quickRow       = document.getElementById('quickRow');
    dom.inputTextarea  = document.getElementById('inputTextarea');
    dom.sendBtn        = document.getElementById('sendBtn');
    dom.sendIcon       = document.getElementById('sendIcon');
    dom.stopIcon       = document.getElementById('stopIcon');
  }

  // ============ 安全 localStorage ============
  function safeLoad(key, fallback) {
    try {
      let raw = localStorage.getItem(key);
      if (raw == null) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }
  function safeSave(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ }
  }
  function safeGetRaw(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function safeSetRaw(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
  }
  function safeRemove(key) {
    try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
  }

  // ============ 工具函数 ============
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function findMessageById(session, id) {
    if (!session || !Array.isArray(session.messages)) return null;
    for (let i = 0; i < session.messages.length; i++) {
      if (session.messages[i] && session.messages[i].id === id) return session.messages[i];
    }
    return null;
  }
  function findMessageIndexById(session, id) {
    if (!session || !Array.isArray(session.messages)) return -1;
    for (let i = 0; i < session.messages.length; i++) {
      if (session.messages[i] && session.messages[i].id === id) return i;
    }
    return -1;
  }
  function uid(prefix) {
    return (prefix || 'id-') + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }
  function nowIso() { return new Date().toISOString(); }
  function fmtTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      const h = String(d.getHours()).padStart(2, '0');
      const m = String(d.getMinutes()).padStart(2, '0');
      return h + ':' + m;
    } catch (e) { return ''; }
  }
  function formatDateTime(value) {
    if (!value) return '-';
    var normalized = String(value).trim();
    if (!normalized) return '-';
    var match = normalized.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})/);
    if (match) return match[1] + ' ' + match[2];
    var parsed = new Date(normalized);
    if (isNaN(parsed.getTime())) return normalized;
    var y = parsed.getFullYear();
    var mo = String(parsed.getMonth() + 1).padStart(2, '0');
    var d = String(parsed.getDate()).padStart(2, '0');
    var h = String(parsed.getHours()).padStart(2, '0');
    var mi = String(parsed.getMinutes()).padStart(2, '0');
    var s = String(parsed.getSeconds()).padStart(2, '0');
    return y + '-' + mo + '-' + d + ' ' + h + ':' + mi + ':' + s;
  }
  function fmtPercent(v) {
    if (v == null || isNaN(v)) return '0%';
    var n = Number(v);
    if (n <= 1) n = n * 100;
    return Math.round(n) + '%';
  }
  function getGroupLabel(iso) {
    if (!iso) return '更早';
    var t = new Date(iso).getTime();
    if (isNaN(t)) return '更早';
    var now = new Date();
    var startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    var dayMs = 86400000;
    if (t >= startOfToday) return '今天';
    if (t >= startOfToday - dayMs) return '昨天';
    if (t >= startOfToday - 7 * dayMs) return '前 7 天';
    return '更早';
  }
  function getSidebarGroupLabel(iso) {
    if (!iso) return '更早';
    var t = new Date(iso).getTime();
    if (isNaN(t)) return '更早';
    var now = new Date();
    var startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    var dayMs = 86400000;
    if (t >= startOfToday) return '今天';
    if (t >= startOfToday - 7 * dayMs) return '7天内';
    return '更早';
  }

  // ============ 登录 / 登出 ============
  function isLoggedIn() {
    return safeGetRaw(STORAGE_KEYS.LOGIN) === 'true';
  }
  function handleLogin(e) {
    if (e) e.preventDefault();
    var u = (dom.loginUsername.value || '').trim();
    var p = dom.loginPassword.value || '';
    if (u === 'admin' && p === 'admin123') {
      safeSetRaw(STORAGE_KEYS.LOGIN, 'true');
      dom.loginError.classList.add('hidden');
      dom.loginError.textContent = '';
      enterApp();
    } else {
      dom.loginError.textContent = '用户名或密码错误';
      dom.loginError.classList.remove('hidden');
    }
  }
  function togglePasswordVisibility() {
    if (!dom.loginPassword || !dom.passwordToggle) return;
    var visible = dom.loginPassword.type === 'text';
    if (visible) {
      dom.loginPassword.type = 'password';
      dom.passwordToggle.setAttribute('aria-label', '显示密码');
      dom.passwordToggle.setAttribute('title', '显示密码');
      if (dom.passwordEyeClosed) dom.passwordEyeClosed.classList.remove('hidden');
      if (dom.passwordEyeOpen) dom.passwordEyeOpen.classList.add('hidden');
    } else {
      dom.loginPassword.type = 'text';
      dom.passwordToggle.setAttribute('aria-label', '隐藏密码');
      dom.passwordToggle.setAttribute('title', '隐藏密码');
      if (dom.passwordEyeClosed) dom.passwordEyeClosed.classList.add('hidden');
      if (dom.passwordEyeOpen) dom.passwordEyeOpen.classList.remove('hidden');
    }
  }
  function handleLogout() {
    if (state.isLoading && state.abortController) {
      try { state.abortController.abort(); } catch (e) { /* ignore */ }
    }
    state.isLoading = false;
    state.abortController = null;
    safeRemove(STORAGE_KEYS.LOGIN);
    dom.loginUsername.value = '';
    dom.loginPassword.value = '';
    dom.loginError.classList.add('hidden');
    dom.appView.classList.add('hidden');
    dom.loginView.classList.remove('hidden');
  }
  function enterApp() {
    dom.loginView.classList.add('hidden');
    dom.appView.classList.remove('hidden');
    state.sessionsLoadError = null;
    loadSessions().then(function () {
      var cur = safeGetRaw(STORAGE_KEYS.CURRENT);
      if (cur && findSession(cur) && !findSession(cur).archived) {
        state.currentSessionId = cur;
      } else if (firstVisibleSession()) {
        state.currentSessionId = firstVisibleSession().id;
      } else {
        state.currentSessionId = null;
      }
      renderSidebar();
      if (state.currentSessionId) {
        loadMessagesForSession(state.currentSessionId);
      } else {
        renderMessages();
      }
      setTimeout(function () { dom.inputTextarea.focus(); }, 50);
    });
  }

  // ============ 会话管理 ============
  function loadSessions() {
    // 会话列表权威来源：后端 /api/v1/chat/conversations
    // 不再从 localStorage 读取；本函数返回 Promise，调用方决定何时刷新 UI
    return fetch(CHAT_API_BASE + '/conversations', {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    }).then(function (res) {
      if (!res.ok) {
        throw new Error('HTTP ' + res.status);
      }
      return res.json();
    }).then(function (list) {
      if (!Array.isArray(list)) list = [];
      // 字段映射：后端 snake_case -> 前端 camelCase，并补齐 messages 数组
      state.sessions = list
        .filter(function (s) { return s && typeof s.id === 'string'; })
        .map(function (s) {
          return {
            id: s.id,
            title: s.title || '新对话',
            pinned: !!s.pinned,
            archived: !!s.archived,
            createdAt: s.created_at || '',
            updatedAt: s.updated_at || s.last_message_at || s.created_at || '',
            lastMessageAt: s.last_message_at || '',
            metadata: s.metadata || {},
            messages: []
          };
        });
      state.sessionsLoadError = null;
      sortSessions();
    }).catch(function (err) {
      // 后端不可用：不写入 rca_sessions，不崩溃，仅记录错误并提示用户
      state.sessions = [];
      state.sessionsLoadError = '无法加载会话列表（后端 API 不可用）';
      // eslint-disable-next-line no-console
      console.error('[loadSessions] 会话列表加载失败：', err && err.message ? err.message : err);
    });
  }
  function saveSessions() {
    // 会话列表由后端管理；本地仅持久化当前会话 ID 和登录状态
    if (state.currentSessionId) safeSetRaw(STORAGE_KEYS.CURRENT, state.currentSessionId);
    else safeRemove(STORAGE_KEYS.CURRENT);
  }
  function sortSessions() {
    state.sessions.sort(function (a, b) {
      if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
      var ta = new Date(a.updatedAt || a.createdAt || 0).getTime();
      var tb = new Date(b.updatedAt || b.createdAt || 0).getTime();
      return tb - ta;
    });
  }
  function findSession(id) {
    for (let i = 0; i < state.sessions.length; i++) {
      if (state.sessions[i].id === id) return state.sessions[i];
    }
    return null;
  }
  function firstVisibleSession() {
    for (let i = 0; i < state.sessions.length; i++) {
      if (!state.sessions[i].archived) return state.sessions[i];
    }
    return null;
  }
  function currentSession() {
    if (state.draftSession) return state.draftSession;
    if (!state.currentSessionId) return null;
    return findSession(state.currentSessionId);
  }
  function createSession() {
    var id = uid('s-');
    var now = nowIso();
    state.draftSession = {
      id: id,
      title: '新对话',
      messages: [],
      createdAt: now,
      updatedAt: now
    };
    state.currentSessionId = null;
    state.selectedAnomalyType = null;
    renderSidebar();
    renderMessages();
    setTimeout(function () { dom.inputTextarea.focus(); }, 50);
    return state.draftSession;
  }
  function loadMessagesForSession(id) {
    var session = findSession(id);
    if (session) {
      session.messages = []; // 清空，显示加载中
      renderMessages();
      fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(id) + '/messages')
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then(function (messages) {
          // 映射后端消息为前端格式
          session.messages = (messages || []).map(function (m) {
            return {
              id: m.id,
              role: m.role,
              content: m.content || '',
              timestamp: m.created_at || '',
              anomalyType: m.anomaly_type || undefined,
              taskId: m.task_id || undefined,
              report: m.report_snapshot || undefined,
              error: !!m.error,
              errorType: (m.metadata && m.metadata.errorType) || undefined,
              errorDesc: (m.metadata && m.metadata.errorDesc) || undefined
            };
          });
          // 为有 taskId 的 assistant 消息附加 progressRestore 标记（Task 8 使用）
          for (var i = 0; i < session.messages.length; i++) {
            var marker = restoreProgressForTaskMessage(session.messages[i]);
            if (marker) {
              session.messages[i].progressRestore = marker;
            }
          }
          renderMessages();
          restoreProgressHistoryForSession(session);
        })
        .catch(function (err) {
          console.error('[switchSession] 加载消息失败：', err);
          session.messages = [];
          renderMessages();
        });
    } else {
      renderMessages();
    }
  }
  function switchSession(id) {
    if (id === state.currentSessionId) return;
    state.draftSession = null;
    state.currentSessionId = id;
    state.selectedAnomalyType = null;
    saveSessions();
    renderSidebar();
    // 从后端加载该会话的消息
    loadMessagesForSession(id);
  }
  function deleteSession(id) {
    let idx = -1;
    var removed = null;
    var wasCurrent = false;
    var nextSession = null;
    for (let i = 0; i < state.sessions.length; i++) {
      if (state.sessions[i].id === id) { idx = i; removed = state.sessions[i]; break; }
    }
    if (idx < 0) return;
    wasCurrent = state.currentSessionId === id;
    state.sessions.splice(idx, 1);
    if (wasCurrent) {
      nextSession = firstVisibleSession();
      state.currentSessionId = nextSession ? nextSession.id : null;
    }
    renderSidebar();
    renderMessages();
    fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(id), {
      method: 'DELETE'
    }).then(function (res) {
      if (!res.ok && res.status !== 204) throw new Error('HTTP ' + res.status);
    }).catch(function (err) {
      console.error('[deleteSession] 删除失败：', err);
      // 回滚
      state.sessions.splice(idx, 0, removed);
      if (wasCurrent) {
        state.currentSessionId = id;
      }
      renderSidebar();
      renderMessages();
      alert('删除失败，请重试');
    });
  }
  function ensureSession() {
    var s = currentSession();
    if (s) return s;
    return createSession();
  }
  function commitDraftSession(session) {
    if (!session || state.draftSession !== session) return Promise.resolve(session);
    // 同步部分：先把 draft 提升为正式
    var draftId = session.id;
    state.draftSession = null;
    state.currentSessionId = draftId;
    state.sessions.unshift(session);
    // 异步部分：调后端创建会话，返回 Promise
    return fetch(CHAT_API_BASE + '/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: session.title || '新对话' })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (created) {
      // 用后端返回的真实 id 替换 draftId
      var realId = created.id;
      for (let i = 0; i < state.sessions.length; i++) {
        if (state.sessions[i].id === draftId) {
          state.sessions[i].id = realId;
          state.sessions[i].createdAt = created.created_at || state.sessions[i].createdAt;
          state.sessions[i].updatedAt = created.updated_at || state.sessions[i].updatedAt;
          break;
        }
      }
      if (state.currentSessionId === draftId) {
        state.currentSessionId = realId;
        saveSessions();
      }
      sortSessions();
      renderSidebar();
      return session;
    }).catch(function (err) {
      console.error('[commitDraftSession] 创建会话失败：', err);
      // 回滚
      for (let i = 0; i < state.sessions.length; i++) {
        if (state.sessions[i].id === draftId) {
          state.sessions.splice(i, 1);
          break;
        }
      }
      state.draftSession = session;
      state.currentSessionId = null;
      renderSidebar();
      renderMessages();
      alert('创建会话失败，请重试');
      throw err;
    });
  }
  function updateSessionTitle(session, firstUserText, commitPromise) {
    if (!session || !firstUserText) return;
    if (session.title && session.title !== '新对话') return;
    // 调用后端 summarize-title API 生成 LLM 摘要标题
    (commitPromise || Promise.resolve(session)).then(function () {
      return fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(session.id) + '/summarize-title', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_message: String(firstUserText) })
      });
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      if (data && data.title) {
        session.title = data.title;
        sortSessions();
        renderSidebar();
        renderMessages({ preserveScroll: true });
      }
    }).catch(function (err) {
      // API 不可用时使用安全本地 fallback（不是简单截断）
      var t = String(firstUserText).trim().replace(/\s+/g, ' ');
      if (t.length > 30) {
        // 本地 fallback：提取有意义的前缀而非简单截断
        var keywords = ['超站', '设备冲突', '物料短缺', '质量异常', '接口超时', '排程风险',
                        'http', 'https', '错误', '报错', '失败', '超时', '怎么', '如何', '为什么'];
        for (var i = 0; i < keywords.length; i++) {
          var idx = t.toLowerCase().indexOf(keywords[i].toLowerCase());
          if (idx >= 0) {
            session.title = t.substring(Math.max(0, idx - 2), Math.min(t.length, idx + 12));
            break;
          }
        }
        if (!session.title || session.title === '新对话') {
          session.title = '异常分析';
        }
      } else {
        session.title = t || '异常分析';
      }
      sortSessions();
      renderSidebar();
      renderMessages({ preserveScroll: true });
    });
  }

  // ============ 渲染 - 侧边栏 ============
  function renderSidebar() {
    if (state.sessionsLoadError) {
      dom.sessionsList.innerHTML =
        '<div class="sessions-empty sessions-load-error">' +
        escapeHtml(state.sessionsLoadError) +
        '</div>';
      return;
    }
    var kw = (state.searchKeyword || '').trim().toLowerCase();
    var filtered = state.sessions.filter(function (s) {
      if (s.archived) return false;
      if (!kw) return true;
      var t = (s.title || '').toLowerCase();
      return t.indexOf(kw) >= 0;
    });
    if (filtered.length === 0) {
      dom.sessionsList.innerHTML = '<div class="sessions-empty">' +
        (kw ? '未找到匹配的对话' : '暂无历史对话') +
        '</div>';
      return;
    }
    var groups = { '今天': [], '7天内': [], '更早': [] };
    filtered.forEach(function (s) {
      var label = getSidebarGroupLabel(s.updatedAt || s.createdAt);
      if (!groups[label]) groups[label] = [];
      groups[label].push(s);
    });
    var order = ['今天', '7天内', '更早'];
    var html = '';
    order.forEach(function (label) {
      var list = groups[label];
      var collapsed = !!state.collapsedSessionGroups[label];
      var collapsedClass = collapsed ? ' collapsed' : '';
      if (!list || list.length === 0) return;
      html += '<div class="sessions-group' + collapsedClass + '">';
      html += '<div class="sessions-group-title">';
      html += '<button type="button" class="sessions-group-title-btn" data-session-group-toggle="' + escapeHtml(label) + '" aria-expanded="' + (collapsed ? 'false' : 'true') + '">';
      html += '<span class="sessions-group-heading-cluster">';
      html += '<span class="sessions-group-label">' + escapeHtml(label) + '</span>';
      html += '<svg class="sessions-group-chevron" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>';
      html += '</span>';
      html += '<span class="sessions-group-count">' + list.length + '</span>';
      html += '</button>';
      html += '</div>';
      list.forEach(function (s) {
        var active = s.id === state.currentSessionId ? ' active' : '';
        var menuOpen = s.id === state.activeMenuSessionId ? ' menu-open' : '';
        html += '<div class="session-item' + active + menuOpen + '" data-id="' + escapeHtml(s.id) + '">';
        html += '<div class="session-title" title="' + escapeHtml(s.title) + '">' + escapeHtml(s.title) + '</div>';
        if (s.pinned) {
          html += '<svg class="session-pin" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M5 17h14"/><path d="M7 17l2-8-2-4h10l-2 4 2 8"/></svg>';
        }
        html += '<button type="button" class="session-more" data-menu="' + escapeHtml(s.id) + '" title="更多" aria-label="更多操作">';
        html += '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
        html += '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>';
        html += '</svg></button>';
        if (s.id === state.activeMenuSessionId) html += renderSessionMenuHtml(s);
        html += '</div>';
      });
      html += '</div>';
    });
    dom.sessionsList.innerHTML = html;
  }

  function renderSessionMenuHtml(session) {
    var pinnedText = session && session.pinned ? '取消置顶' : '置顶聊天';
    return [
      '<div class="session-menu" data-session-menu="', escapeHtml(session.id), '">',
        '<button type="button" class="session-menu-item" data-action="rename" data-action-id="', escapeHtml(session.id), '">',
          '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
          '重命名',
        '</button>',
        '<button type="button" class="session-menu-item" data-action="pin" data-action-id="', escapeHtml(session.id), '">',
          '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M5 17h14"/><path d="M7 17l2-8-2-4h10l-2 4 2 8"/></svg>',
          escapeHtml(pinnedText),
        '</button>',
        '<button type="button" class="session-menu-item" data-action="archive" data-action-id="', escapeHtml(session.id), '">',
          '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg>',
          '归档',
        '</button>',
        '<div class="session-menu-sep"></div>',
        '<button type="button" class="session-menu-item danger" data-action="delete" data-action-id="', escapeHtml(session.id), '">',
          '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>',
          '删除',
        '</button>',
      '</div>'
    ].join('');
  }

  function openRenameDialog(id) {
    var session = findSession(id);
    if (!session) return;
    state.pendingRenameSessionId = id;
    state.activeMenuSessionId = null;
    dom.renameInput.value = session.title || '';
    dom.renameDialog.classList.remove('hidden');
    renderSidebar();
    setTimeout(function () { dom.renameInput.focus(); dom.renameInput.select(); }, 30);
  }
  function closeRenameDialog() {
    state.pendingRenameSessionId = null;
    dom.renameDialog.classList.add('hidden');
    dom.renameInput.value = '';
  }
  function confirmRenameSession() {
    var id = state.pendingRenameSessionId;
    var session = findSession(id);
    var title = (dom.renameInput.value || '').trim().replace(/\s+/g, ' ');
    if (!session || !title) return;
    var truncated = title.length > 30 ? title.slice(0, 30) + '…' : title;
    fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(id), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: truncated })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function () {
      session.title = truncated;
      sortSessions();
      closeRenameDialog();
      renderSidebar();
      renderMessages();
    }).catch(function (err) {
      console.error('[confirmRenameSession] 重命名失败：', err);
      alert('重命名失败，请重试');
    });
  }
  function toggleSessionGroup(label) {
    if (!label) return;
    state.collapsedSessionGroups[label] = !state.collapsedSessionGroups[label];
    state.activeMenuSessionId = null;
    renderSidebar();
  }
  function togglePinSession(id) {
    var session = findSession(id);
    if (!session) return;
    var oldPinned = session.pinned;
    session.pinned = !oldPinned;
    state.activeMenuSessionId = null;
    sortSessions();
    renderSidebar();
    fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(id), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: !oldPinned })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).catch(function (err) {
      console.error('[togglePinSession] 置顶失败：', err);
      session.pinned = oldPinned;
      sortSessions();
      renderSidebar();
      alert('操作失败，请重试');
    });
  }
  function archiveSession(id) {
    var session = findSession(id);
    if (!session) return;
    var oldArchived = session.archived;
    session.archived = true;
    state.activeMenuSessionId = null;
    if (state.currentSessionId === id) {
      state.currentSessionId = null;
      state.draftSession = null;
      safeRemove(STORAGE_KEYS.CURRENT);
    }
    renderSidebar();
    renderMessages();
    fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(id), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archived: true })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).catch(function (err) {
      console.error('[archiveSession] 归档失败：', err);
      session.archived = oldArchived;
      if (state.currentSessionId === null) {
        state.currentSessionId = id;
      }
      renderSidebar();
      renderMessages();
      alert('归档失败，请重试');
    });
  }
  function openDeleteDialog(id) {
    var session = findSession(id);
    if (!session) return;
    state.pendingDeleteSessionId = id;
    state.activeMenuSessionId = null;
    dom.deleteDialogTitle.textContent = session.title || '新对话';
    dom.deleteDialog.classList.remove('hidden');
    renderSidebar();
  }
  function closeDeleteDialog() {
    state.pendingDeleteSessionId = null;
    dom.deleteDialog.classList.add('hidden');
    dom.deleteDialogTitle.textContent = '';
  }
  function confirmDeleteSession() {
    var id = state.pendingDeleteSessionId;
    closeDeleteDialog();
    if (id) deleteSession(id);
  }

  // ============ 搜索聊天 - 模态框 ============
  function openSearchModal() {
    if (!dom.searchModal) return;
    state.modalOpen = true;
    state.modalSearchKeyword = '';
    if (dom.modalSearchInput) dom.modalSearchInput.value = '';
    dom.searchModal.classList.remove('hidden');
    renderSearchModalResults();
    setTimeout(function () {
      if (dom.modalSearchInput) dom.modalSearchInput.focus();
    }, 30);
  }
  function closeSearchModal() {
    if (!dom.searchModal) return;
    state.modalOpen = false;
    state.modalSearchKeyword = '';
    dom.searchModal.classList.add('hidden');
    if (dom.modalSearchInput) dom.modalSearchInput.value = '';
  }
  function renderSearchModalResults() {
    if (!dom.searchModalResults) return;
    var kw = (state.modalSearchKeyword || '').trim().toLowerCase();
    var filtered = state.sessions.filter(function (s) {
      if (s.archived) return false;
      if (!kw) return true;
      var t = (s.title || '').toLowerCase();
      return t.indexOf(kw) >= 0;
    });
    var html = '';
    html += '<button type="button" class="search-modal-new" id="modalNewChatBtn">';
    html += '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
    html += '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>';
    html += '</svg>';
    html += '新聊天';
    html += '</button>';

    if (filtered.length === 0) {
      html += '<div class="search-modal-empty">' +
        (kw ? '未找到匹配的聊天' : '暂无历史聊天') +
        '</div>';
      dom.searchModalResults.innerHTML = html;
      return;
    }

    var groups = { '今天': [], '7天内': [], '更早': [] };
    filtered.forEach(function (s) {
      var label = getSidebarGroupLabel(s.updatedAt || s.createdAt);
      if (!groups[label]) groups[label] = [];
      groups[label].push(s);
    });
    var order = ['今天', '7天内', '更早'];
    order.forEach(function (label) {
      var list = groups[label];
      if (!list || list.length === 0) return;
      html += '<div class="search-modal-group">';
      html += '<div class="search-modal-group-title">' + escapeHtml(label) + '</div>';
      list.forEach(function (s) {
        html += '<button type="button" class="search-modal-item" data-modal-id="' + escapeHtml(s.id) + '">';
        html += '<svg class="search-modal-item-icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
        html += '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>';
        html += '</svg>';
        html += '<div class="search-modal-item-title">' + escapeHtml(s.title || '新对话') + '</div>';
        html += '</button>';
      });
      html += '</div>';
    });
    dom.searchModalResults.innerHTML = html;
  }

  // ============ 渲染 - 主消息区 ============
  function renderMessages(options) {
    var shouldScrollToBottom = !(options && options.preserveScroll);
    var s = currentSession();
    if (!s) {
      dom.topbarTitle.textContent = '';
      dom.messages.innerHTML = buildEmptyStateHtml();
      attachEmptyStateHandlers();
      renderQuickRow();
      return;
    }
    dom.topbarTitle.textContent = '';
    if (!s.messages || s.messages.length === 0) {
      dom.messages.innerHTML = buildEmptyStateHtml();
      attachEmptyStateHandlers();
      renderQuickRow();
      if (shouldScrollToBottom) scrollToBottom();
      return;
    }
    var html = '';
    s.messages.forEach(function (m) {
      html += renderMessageHtml(m);
    });
    if (state.isLoading) html += renderLoadingHtml();
    dom.messages.innerHTML = html;
    attachMessageHandlers();
    renderQuickRow();
    if (shouldScrollToBottom) scrollToBottom();
  }

  function buildEmptyStateHtml() {
    var cards = '';
    Object.keys(ANOMALY_TYPES).forEach(function (key) {
      var label = ANOMALY_TYPES[key];
      var desc = ANOMALY_TEMPLATES[key];
      cards += '<button type="button" class="empty-card" data-empty-type="' + escapeHtml(key) + '">';
      cards += '<div class="empty-card-title">' + escapeHtml(label) + '</div>';
      cards += '<div class="empty-card-desc">' + escapeHtml(desc) + '</div>';
      cards += '</button>';
    });
    return [
      '<div class="empty-state">',
        '<div class="empty-logo">RCA</div>',
        '<h2 class="empty-title">异常根因分析智能体</h2>',
        '<p class="empty-subtitle">选择异常类型或直接描述问题，系统将自动分析并给出根因报告</p>',
        '<div class="empty-grid">', cards, '</div>',
      '</div>'
    ].join('');
  }
  function attachEmptyStateHandlers() {
    const cards = dom.messages.querySelectorAll('[data-empty-type]');
    for (let i = 0; i < cards.length; i++) {
      cards[i].addEventListener('click', function () {
        var type = this.getAttribute('data-empty-type');
        selectAnomalyType(type);
        dom.inputTextarea.value = ANOMALY_TEMPLATES[type] || '';
        autoResizeTextarea();
        dom.inputTextarea.focus();
      });
    }
  }
  function attachMessageHandlers() {
    const retries = dom.messages.querySelectorAll('[data-retry-msg]');
    for (let i = 0; i < retries.length; i++) {
      retries[i].addEventListener('click', function () {
        var type = this.getAttribute('data-retry-type') || 'overstation_check';
        var desc = this.getAttribute('data-retry-desc') || '';
        retryAnalysis(type, desc);
      });
    }
    // 进度时间线 step 折叠/展开（Task 7）
    const stepToggles = dom.messages.querySelectorAll('[data-progress-step-toggle]');
    for (let s = 0; s < stepToggles.length; s++) {
      stepToggles[s].addEventListener('click', function (e) {
        e.preventDefault();
        var key = this.getAttribute('data-progress-step-toggle');
        if (!key) return;
        toggleProgressStep(key, this);
      });
    }
    const copyBtns = dom.messages.querySelectorAll('[data-copy-message]');
    for (let i = 0; i < copyBtns.length; i++) {
      copyBtns[i].addEventListener('click', function () {
        copyMessageText(this.getAttribute('data-copy-message'));
      });
    }
    const editBtns = dom.messages.querySelectorAll('[data-edit-message]');
    for (let i = 0; i < editBtns.length; i++) {
      editBtns[i].addEventListener('click', function () {
        startEditingMessage(this.getAttribute('data-edit-message'));
      });
    }
    const cancelBtns = dom.messages.querySelectorAll('[data-edit-cancel]');
    for (let i = 0; i < cancelBtns.length; i++) {
      cancelBtns[i].addEventListener('click', cancelEditingMessage);
    }
    const submitBtns = dom.messages.querySelectorAll('[data-edit-submit]');
    for (let i = 0; i < submitBtns.length; i++) {
      submitBtns[i].addEventListener('click', function () {
        submitEditingMessage(this.getAttribute('data-edit-submit'));
      });
    }
    const editTextareas = dom.messages.querySelectorAll('[data-edit-textarea]');
    for (let i = 0; i < editTextareas.length; i++) {
      editTextareas[i].addEventListener('keydown', function (e) {
        if (e.key === 'Escape' || e.key === 'Esc') {
          e.preventDefault();
          cancelEditingMessage();
        }
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          submitEditingMessage(this.getAttribute('data-edit-textarea'));
        }
      });
      editTextareas[i].focus();
      editTextareas[i].selectionStart = editTextareas[i].value.length;
      editTextareas[i].selectionEnd = editTextareas[i].value.length;
    }
  }
  function scrollToBottom() {
    requestAnimationFrame(function () {
      dom.messagesWrap.scrollTop = dom.messagesWrap.scrollHeight;
    });
  }

  // 切换单个 progress step 的折叠/展开状态（Task 7）
  function toggleProgressStep(key, toggleEl) {
    if (!key) return;
    if (!state.progress) state.progress = { lastSeq: 0, steps: {}, expanded: {} };
    if (!state.progress.expanded) state.progress.expanded = {};
    var wasOpen = !!state.progress.expanded[key];
    state.progress.expanded[key] = !wasOpen;
    // 找到最近的 .rca-progress-step li 节点与 detail 节点
    var li = toggleEl && toggleEl.closest ? toggleEl.closest('.rca-progress-step') : null;
    if (!li) return;
    var detail = document.getElementById('rca-progress-detail-' + key);
    if (detail) {
      if (state.progress.expanded[key]) {
        detail.removeAttribute('hidden');
      } else {
        detail.setAttribute('hidden', '');
      }
    }
    li.classList.toggle('is-expanded', state.progress.expanded[key]);
    toggleEl.setAttribute('aria-expanded', state.progress.expanded[key] ? 'true' : 'false');
  }

  function copyMessageText(messageId) {
    var session = currentSession();
    var msg = findMessageById(session, messageId);
    if (!msg || msg.role !== 'user') return;
    var text = msg.content || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        markMessageCopied(messageId);
      }).catch(function () {
        copyMessageTextFallback(text);
        markMessageCopied(messageId);
      });
      return;
    }
    copyMessageTextFallback(text);
    markMessageCopied(messageId);
  }
  function copyMessageTextFallback(text) {
    var ta = document.createElement('textarea');
    ta.value = text || '';
    ta.setAttribute('readonly', 'readonly');
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }
  function markMessageCopied(messageId) {
    state.copiedMessageId = messageId;
    if (state.copiedTimer) clearTimeout(state.copiedTimer);
    renderMessages({ preserveScroll: true });
    state.copiedTimer = setTimeout(function () {
      if (state.copiedMessageId !== messageId) return;
      state.copiedMessageId = null;
      renderMessages({ preserveScroll: true });
    }, 1600);
  }
  function startEditingMessage(messageId) {
    if (state.isLoading) return;
    var session = currentSession();
    var msg = findMessageById(session, messageId);
    if (!msg || msg.role !== 'user') return;
    state.editingMessageId = messageId;
    renderMessages({ preserveScroll: true });
  }
  function cancelEditingMessage() {
    state.editingMessageId = null;
    renderMessages({ preserveScroll: true });
  }
  function submitEditingMessage(messageId) {
    if (state.isLoading) return;
    var session = currentSession();
    var idx = findMessageIndexById(session, messageId);
    if (!session || idx < 0) return;
    var msg = session.messages[idx];
    if (!msg || msg.role !== 'user') return;
    var editor = dom.messages.querySelector('[data-edit-textarea="' + messageId + '"]');
    var text = editor ? (editor.value || '').trim() : '';
    if (!text) return;
    var now = nowIso();
    msg.content = text;
    msg.timestamp = now;
    session.messages.splice(idx + 1);
    session.updatedAt = now;
    state.editingMessageId = null;
    var commitPromise = Promise.resolve(session);
    updateSessionTitle(session, text, commitPromise);
    sortSessions();
    saveSessions();
    renderSidebar();
    setLoadingUI(true);
    renderMessages();
    routeChatMessage(msg.anomalyType || 'overstation_check', text, session, commitPromise);
  }

  // ============ 渲染 - 消息 ============
  function renderAssistantMarkdownHtml(text) {
    var escaped = escapeHtml(text || '');
    var lines = escaped.split(new RegExp('\\r?\\n'));
    var html = [];
    var inList = false;
    var paragraph = [];
    var H_OPEN = ['<h1>', '<h2>', '<h3>'];
    var H_CLOSE = ['</h1>', '</h2>', '</h3>'];
    var codeRe = new RegExp('`([^`]+)`', 'g');
    var boldRe = new RegExp('\\*\\*([^*]+)\\*\\*', 'g');
    // 支持 # ## ### #### 四级标题、**加粗**、`code`、"- " "* " 列表、段落合并
    var headingRe = new RegExp('^(#{1,4})\\s+(.+)$');
    var bulletRe = new RegExp('^[-*]\\s+(.+)$');
    function inlineMarkdown(line) {
      return line
        .replace(codeRe, '<code>$1</code>')
        .replace(boldRe, '<strong>$1</strong>');
    }
    function flushParagraph() {
      if (!paragraph.length) return;
      html.push('<p>' + inlineMarkdown(paragraph.join(' ')) + '</p>');
      paragraph = [];
    }
    function closeList() {
      flushParagraph();
      if (inList) {
        html.push('</ul>');
        inList = false;
      }
    }
    lines.forEach(function (line) {
      var trimmed = line.trim();
      if (!trimmed) {
        closeList();
        return;
      }
      var heading = trimmed.match(headingRe);
      if (heading) {
        closeList();
        var level = Math.min(3, Math.max(1, heading[1].length));
        var hi = level - 1;
        html.push(H_OPEN[hi] + inlineMarkdown(heading[2]) + H_CLOSE[hi]);
        return;
      }
      var bullet = trimmed.match(bulletRe);
      if (bullet) {
        flushParagraph();
        if (!inList) {
          html.push('<ul>');
          inList = true;
        }
        html.push('<li>' + inlineMarkdown(bullet[1]) + '</li>');
        return;
      }
      closeList();
      paragraph.push(trimmed);
    });
    closeList();
    return '<div class="msg-markdown">' + html.join('') + '</div>';
  }

  function renderMessageHtml(m) {
    var msgId = '';
    var copied = false;
    var copyIcon = '';
    if (!m || !m.role) return '';
    if (m.role === 'user') {
      if (m.id && m.id === state.editingMessageId) return renderEditingMessageHtml(m);
      msgId = escapeHtml(m.id || '');
      copied = !!(m.id && m.id === state.copiedMessageId);
      copyIcon = copied
        ? '<svg data-copy-check="1" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
        : '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><rect x="2" y="2" width="13" height="13" rx="2"/></svg>';
      return [
        '<div class="msg user">',
          '<div class="msg-shell">',
            '<div class="msg-content">', escapeHtml(m.content || ''), '</div>',
            '<div class="msg-actions">',
              '<button type="button" class="msg-action-btn" data-copy-message="', msgId, '" data-tooltip="复制消息" title="复制消息" aria-label="复制消息">',
                copyIcon,
              '</button>',
              '<button type="button" class="msg-action-btn" data-edit-message="', msgId, '" data-tooltip="编辑消息" title="编辑消息" aria-label="编辑消息">',
                '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
              '</button>',
            '</div>',
            '<div class="msg-time">', escapeHtml(fmtTime(m.timestamp)), '</div>',
          '</div>',
        '</div>'
      ].join('');
    }
    if (m.role === 'assistant') {
      // assistant 消息内容：progress timeline（可选）+ error / report / 文本
      var parts = [];
      // 1) progress 时间线（Task 8：在同一消息内显示折叠进度卡片）
      if (m.progress && m.progress.steps) {
        parts.push(renderProgressHtml(m.progress));
      }
      // 2) error 优先
      if (m.error) {
        parts.push(renderErrorContentHtml(m));
      } else if (m.report_snapshot || m.report) {
        // 3) 最终报告（renderReportHtml 同时兼容 report_snapshot 与 report）
        parts.push(renderReportHtml(m.report_snapshot || m.report));
      } else if (m.content) {
        // 4) 普通文本
        parts.push(renderAssistantMarkdownHtml(m.content));
      }
      var progressAttr = m.progress ? ' data-progress-message="1"' : '';
      var progressClass = m.progress ? ' msg-progress' : '';
      return [
        '<div class="msg assistant' + progressClass + '"' + progressAttr + '>',
          '<div class="msg-avatar">RCA</div>',
          '<div class="msg-content">',
            parts.join(''),
            '<div class="msg-time">', escapeHtml(fmtTime(m.timestamp)), '</div>',
          '</div>',
        '</div>'
      ].join('');
    }
    return '';
  }
  function renderEditingMessageHtml(m) {
    var msgId = escapeHtml(m.id || '');
    return [
      '<div class="msg user">',
        '<div class="msg-shell">',
          '<div class="msg-edit-card">',
            '<textarea class="msg-edit-textarea" data-edit-textarea="', msgId, '" rows="3">', escapeHtml(m.content || ''), '</textarea>',
            '<div class="msg-edit-actions">',
              '<button type="button" class="msg-edit-btn" data-edit-cancel="', msgId, '">取消</button>',
              '<button type="button" class="msg-edit-btn primary" data-edit-submit="', msgId, '">发送</button>',
            '</div>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
  }
  function renderLoadingHtml() {
    return [
      '<div class="msg assistant">',
        '<div class="msg-avatar">RCA</div>',
        '<div class="msg-content">',
          '<div style="display:flex; align-items:center;">',
            '<div class="loading-dots"><span></span><span></span><span></span></div>',
            '<span class="loading-text">正在分析根因...</span>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
  }

  // ============ 进度时间线（Task 6 脚手架 + Task 7 折叠卡片）============
  // 默认渲染 8 步概览；每个 step 可通过 data-progress-step-toggle 按钮展开/折叠。
  // 状态由 renderProgressHtml(progress) 入参 steps[key].status 驱动；
  // 5 种状态：pending / running / success / failed / cancelled。
  // 从 stepState 中提取 detail 文本，优先结构化字段 detail_json（object/list 用 JSON.stringify
  // 缩进格式化），退回 detail / log / tool 旧字段；返回纯字符串（不含 HTML，需 renderProgressHtml
  // 再经 escapeHtml 插入，避免 XSS）。
  function formatProgressStepDetail(stepState) {
    if (!stepState || typeof stepState !== 'object') return '';
    var detailJson = stepState.detail_json;
    if (detailJson !== undefined && detailJson !== null) {
      if (typeof detailJson === 'string') {
        if (detailJson.length > 0) return detailJson;
      } else if (typeof detailJson === 'object') {
        try {
          var pretty = JSON.stringify(detailJson, null, 2);
          if (typeof pretty === 'string' && pretty.length > 0) return pretty;
        } catch (e) {
          // 循环引用等异常降级为空串，由 detail / log / tool 兜底
        }
      }
    }
    return stepState.detail || stepState.log || stepState.tool || '';
  }
  function formatProgressTraceMeta(evt) {
    var meta = [];
    var detailJson = evt && evt.detail_json;
    if (detailJson && typeof detailJson === 'object') {
      if (detailJson.tool_name) meta.push('工具: ' + detailJson.tool_name);
      if (Array.isArray(detailJson.selected_tools) && detailJson.selected_tools.length > 0) meta.push('工具: ' + detailJson.selected_tools.join('、'));
      if (detailJson.duration_ms != null) meta.push('耗时: ' + detailJson.duration_ms + 'ms');
      if (detailJson.evidence_count != null) meta.push('证据: ' + detailJson.evidence_count);
    }
    return meta.join(' · ');
  }
  function renderProgressTraceRoundHtml(evt) {
    if (evt && evt.node_name === 'generate_report') return '';
    var detailJson = evt && evt.detail_json;
    if (!detailJson || typeof detailJson !== 'object' || detailJson.round == null) return '';
    var roundNo = Number(detailJson.round) + 1;
    if (!isFinite(roundNo)) return '';
    return ' 第 <span class="rca-progress-trace-round-number">' + escapeHtml(String(roundNo)) + '</span> 轮';
  }
  function getProgressTraceRound(evt) {
    var detailJson = evt && evt.detail_json;
    if (!detailJson || typeof detailJson !== 'object' || detailJson.round == null) return '0';
    return String(detailJson.round);
  }
  function mergeProgressTraceEvents(events) {
    var merged = [];
    var byKey = {};
    for (var i = 0; i < events.length; i++) {
      var evt = events[i] || {};
      var eventType = evt.event_type || evt.type || '';
      var nodeName = evt.node_name || evt.title || 'task';
      var round = getProgressTraceRound(evt);
      var key = nodeName + '::' + round;
      var item = byKey[key];
      if (!item) {
        item = {};
        for (var p in evt) {
          if (Object.prototype.hasOwnProperty.call(evt, p)) item[p] = evt[p];
        }
        item.trace_lines = [];
        byKey[key] = item;
        merged.push(item);
      }
      if (eventType === 'node_started') {
        item.started_event = evt;
        item.trace_lines[0] = evt.summary || ('正在执行 ' + (evt.node_name || nodeName));
        if (!item.event_type) item.event_type = eventType;
      } else if (eventType === 'node_completed') {
        item.completed_event = evt;
        item.event_type = eventType;
        item.summary = evt.summary || item.summary;
        item.detail_json = evt.detail_json || item.detail_json;
        item.trace_lines[1] = evt.summary || ((RCA_PROGRESS_STEPS[evt.node_name] || evt.node_name || nodeName) + ' 执行完成');
      } else if (eventType === 'node_error') {
        item.error_event = evt;
        item.event_type = eventType;
        item.summary = evt.summary || item.summary;
        item.detail_json = evt.detail_json || item.detail_json;
        item.trace_lines.push(evt.summary || ((RCA_PROGRESS_STEPS[evt.node_name] || evt.node_name || nodeName) + ' 执行失败'));
      } else if (evt.summary) {
        item.trace_lines.push(evt.summary);
      }
    }
    return merged;
  }
  function renderProgressTraceHtml(progress) {
    var events = (progress && Array.isArray(progress.events)) ? progress.events : [];
    if (!events.length) return '';
    var traceEvents = mergeProgressTraceEvents(events);
    var html = '<div class="rca-progress-trace" data-rca-progress-trace="1">';
    html += '<div class="rca-progress-trace-title">执行轨迹</div>';
    html += '<ol class="rca-progress-trace-list">';
    for (var i = 0; i < traceEvents.length; i++) {
      var evt = traceEvents[i] || {};
      var nodeTitle = RCA_PROGRESS_STEPS[evt.node_name] || evt.title || evt.node_name || '任务事件';
      var status = mapEventTypeToStatus(evt.event_type || evt.type || '');
      var meta = formatProgressTraceMeta(evt);
      var traceLines = Array.isArray(evt.trace_lines) ? evt.trace_lines.filter(Boolean) : [];
      html += '<li class="rca-progress-trace-item rca-progress-trace-item--' + escapeHtml(status) + '">';
      html += '<span class="rca-progress-trace-index">#' + escapeHtml(String(i + 1)) + '</span>';
      html += '<span class="rca-progress-trace-main">';
      html += '<span class="rca-progress-trace-heading">';
      html += '<span class="rca-progress-trace-name">' + escapeHtml(nodeTitle) + '</span>';
      html += renderProgressTraceRoundHtml(evt);
      html += '</span>';
      if (traceLines[0]) html += '<span class="rca-progress-trace-summary">' + escapeHtml(traceLines[0]) + '</span>';
      if (meta) html += '<span class="rca-progress-trace-meta">' + escapeHtml(meta) + '</span>';
      for (var j = 1; j < traceLines.length; j++) {
        html += '<span class="rca-progress-trace-summary">' + escapeHtml(traceLines[j]) + '</span>';
      }
      html += '</span>';
      html += '</li>';
    }
    html += '</ol></div>';
    return html;
  }
  function renderProgressHtml(progress) {
    var steps = (progress && progress.steps) ? progress.steps : {};
    // 统计已完成数（success 视为完成）
    var total = RCA_PROGRESS_STEP_ORDER.length;
    var done = 0;
    for (var i = 0; i < total; i++) {
      var k = RCA_PROGRESS_STEP_ORDER[i];
      var st = (steps[k] && steps[k].status) || 'pending';
      if (st === 'success' || st === 'failed' || st === 'cancelled') done++;
    }
    var html = '';
    html += '<div class="rca-progress" data-rca-progress="1">';
    html +=   '<div class="rca-progress-header">';
    html +=     '<span class="rca-progress-header-title">分析进度</span>';
    html +=     '<span class="rca-progress-header-count" data-rca-progress-count="1">' + done + ' / ' + total + '</span>';
    html +=   '</div>';
    html +=   '<ol class="rca-progress-list">';
    for (var j = 0; j < RCA_PROGRESS_STEP_ORDER.length; j++) {
      var key = RCA_PROGRESS_STEP_ORDER[j];
      var title = RCA_PROGRESS_STEPS[key] || key;
      var stepState = steps[key] || { status: 'pending' };
      var status = stepState.status || 'pending';
      var summary = stepState.summary || '';
      var detail = formatProgressStepDetail(stepState);
      var hasDetail = !!detail;
      var expandedClass = '';
      var detailHidden = ' hidden';
      var ariaExpanded = 'false';
      // Task 8 接入 SSE 后，state.progress.expanded[key] 持久化展开状态；
      // 此处先读取展开态（默认折叠）
      var expandedMap = (state && state.progress && state.progress.expanded) ? state.progress.expanded : {};
      if (expandedMap[key]) {
        expandedClass = ' is-expanded';
        detailHidden = '';
        ariaExpanded = 'true';
      }
      html += '<li class="rca-progress-step ' + 'rca-progress-step--' + escapeHtml(status) + expandedClass + '" data-step="' + escapeHtml(key) + '" data-status="' + escapeHtml(status) + '">';
      html +=   '<button type="button" class="rca-progress-step-toggle" data-progress-step-toggle="' + escapeHtml(key) + '"';
      if (expandedMap[key]) {
        html += ' aria-expanded="true"';
      } else {
        html += ' aria-expanded="false"';
      }
      html += ' aria-controls="rca-progress-detail-' + escapeHtml(key) + '">';
      html +=     '<span class="rca-progress-step-marker" aria-hidden="true"></span>';
      html +=     '<span class="rca-progress-step-text">';
      html +=       '<span class="rca-progress-step-title">' + escapeHtml(title) + '</span>';
      if (summary) {
        html +=     '<span class="rca-progress-step-summary">' + escapeHtml(summary) + '</span>';
      }
      html +=     '</span>';
      html +=     '<svg class="rca-progress-step-chevron" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>';
      html +=   '</button>';
      if (hasDetail) {
        html += '<div class="rca-progress-step-detail" id="rca-progress-detail-' + escapeHtml(key) + '"' + detailHidden + '>' + escapeHtml(detail) + '</div>';
      } else {
        html += '<div class="rca-progress-step-detail" id="rca-progress-detail-' + escapeHtml(key) + '"' + detailHidden + '></div>';
      }
      html += '</li>';
    }
    html +=   '</ol>';
    html +=   renderProgressTraceHtml(progress);
    html += '</div>';
    return html;
  }

  // 同一 assistant 消息追加报告的占位函数（Task 8 实现）。
  // 入参：session 当前会话对象；report 后端返回的报告；opts.taskId 可选任务 ID；
  //       opts.messageId 必传，指定要追加报告的 assistant 消息 id。
  // 行为：找到该消息，将 report 写入 .report 与 .report_snapshot，标记 progressStatus='completed'，
  //       触发 renderMessages 与持久化 PATCH 同步。
  function appendReportToProgressMessage(session, report, opts) {
    if (!session || !report) return null;
    var messageId = opts && opts.messageId;
    if (!messageId) return null;
    var idx = findMessageIndexById(session, messageId);
    if (idx < 0) return null;
    var msg = session.messages[idx];
    msg.report = report;
    msg.report_snapshot = report;
    msg.progressStatus = 'completed';
    msg.updatedAt = nowIso();
    setLoadingUI(false);
    renderMessages();
    // 持久化报告快照：若后端支持 PATCH message 则尝试；否则静默失败
    if (session.id) {
      fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(session.id) + '/messages/' + encodeURIComponent(messageId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_snapshot: report })
      }).then(function (res) {
        if (!res.ok) {
          // 后端可能不支持 PATCH；静默失败
          // eslint-disable-next-line no-console
          console.warn('[appendReportToProgressMessage] PATCH 报告快照失败 (HTTP ' + res.status + ')');
        }
      }).catch(function (err) {
        // eslint-disable-next-line no-console
        console.warn('[appendReportToProgressMessage] PATCH 异常：', err && err.message ? err.message : err);
      });
    }
    return msg;
  }

  // 识别历史 assistant 消息中的 task_id 并准备进度恢复状态（Task 5 标记，Task 8 使用）。
  // 入参：msg 消息对象（来自 switchSession 加载后的 session.messages）。
  // 返回：若 msg 有 taskId 且为 assistant 角色，返回 { taskId, messageId } 标记对象；
  //       否则返回 null。
  // Task 8 SSE 重放时通过此标记找到可恢复进度的历史消息。
  function restoreProgressForTaskMessage(msg) {
    if (!msg || msg.role !== 'assistant') return null;
    if (!msg.taskId) return null;
    return { taskId: msg.taskId, messageId: msg.id };
  }
  function restoreProgressHistoryForSession(session) {
    if (!session || !Array.isArray(session.messages) || state.isLoading) return;
    for (var i = 0; i < session.messages.length; i++) {
      var msg = session.messages[i];
      if (!msg || !msg.progressRestore || !msg.progressRestore.taskId) continue;
      var taskId = msg.progressRestore.taskId;
      var messageId = msg.progressRestore.messageId || msg.id;
      state.progress = {
        lastSeq: (msg.progress && msg.progress.lastSeq) || 0,
        steps: (msg.progress && msg.progress.steps) || {},
        events: (msg.progress && msg.progress.events) || [],
        expanded: state.progress.expanded || {}
      };
      msg.progress = {
        lastSeq: state.progress.lastSeq,
        steps: state.progress.steps,
        events: state.progress.events
      };
      openProgressStream('/api/v1/rca/tasks/' + encodeURIComponent(taskId) + '/events', taskId, messageId, session);
      break;
    }
  }
  function renderErrorContentHtml(m) {
    var desc = m.errorDesc || '';
    var type = m.errorType || 'overstation_check';
    return [
      '<div class="error-msg">',
        '<div class="error-msg-title">❌ 分析失败</div>',
        '<div>', escapeHtml(m.content || '未知错误'), '</div>',
        '<button type="button" class="error-msg-retry" data-retry-msg="1" data-retry-type="', escapeHtml(type), '" data-retry-desc="', escapeHtml(desc), '">重试</button>',
      '</div>'
    ].join('');
  }

  // ============ 渲染 - RCA 报告 ============
  function renderReportHtml(report) {
    if (!report || typeof report !== 'object') {
      return '<div class="report-empty">报告数据缺失</div>';
    }
    var taskId      = report.task_id || '-';
    var status      = report.status || 'completed';
    var anomalyType = report.anomaly_type || '';
    var desc        = report.description || '';
    var rootCause   = report.root_cause || null;
    var hypotheses  = Array.isArray(report.hypotheses) ? report.hypotheses : [];
    var evidence    = Array.isArray(report.evidence) ? report.evidence : [];
    var confidence  = (report.confidence == null) ? 0 : Number(report.confidence);
    var rounds      = (report.reflection_rounds == null) ? 0 : Number(report.reflection_rounds);
    var finalReport = report.final_report || null;
    var createdAt   = report.created_at || '';
    var completedAt = report.completed_at || '';

    if (finalReport == null && (!hypotheses.length && !evidence.length && rootCause == null)) {
      return [
        '<div class="report-card">',
          '<div class="report-head">',
            '<div class="report-title-main">ℹ️ 分析任务回执</div>',
          '</div>',
          '<div class="report-section">',
            '<div class="report-section-title">基本信息</div>',
            '<div class="report-section-body">',
              '<div class="report-kv"><div class="report-kv-key">任务 ID</div><div class="report-kv-val">', escapeHtml(taskId), '</div></div>',
              '<div class="report-kv"><div class="report-kv-key">状态</div><div class="report-kv-val">', escapeHtml(String(status)), '</div></div>',
              '<div class="report-kv"><div class="report-kv-key">异常类型</div><div class="report-kv-val">', escapeHtml(ANOMALY_TYPES[anomalyType] || anomalyType || '-'), '</div></div>',
              '<div class="report-kv"><div class="report-kv-key">描述</div><div class="report-kv-val">', escapeHtml(desc || '-'), '</div></div>',
            '</div>',
          '</div>',
        '</div>'
      ].join('');
    }

    var rootCauseHtml = rootCause
      ? '<div>' + escapeHtml(rootCause) + '</div>'
      : '<div class="report-empty">分析未能确定明确根因</div>';
    var category = (finalReport && finalReport.root_cause_category) || null;
    var categoryHtml = '<div class="report-kv"><div class="report-kv-key">分类</div><div class="report-kv-val">' +
      escapeHtml(category || '未分类') + '</div></div>';
    var anomalyLabel = ANOMALY_TYPES[anomalyType] || anomalyType || '-';
    var confPct = fmtPercent(confidence);
    var confNum = confidence <= 1 ? confidence * 100 : confidence;
    if (isNaN(confNum)) confNum = 0;
    var hypothesesHtml = renderHypothesesHtml(hypotheses);
    var evidenceHtml   = renderEvidenceHtml(evidence);
    var recsHtml       = renderRecommendationsHtml(finalReport);

    return [
      '<div class="report-card">',
        '<div class="report-head">',
          '<div class="report-title-main">✅ 根因分析完成</div>',
          '<div class="report-confidence-wrap">',
            '<div class="report-confidence-bar"><div class="report-confidence-fill" style="width:', confNum, '%"></div></div>',
            '<div class="report-confidence-text">', confPct, '</div>',
          '</div>',
          '<div class="report-reflection">反思轮次: ', rounds, '</div>',
        '</div>',
        '<div class="report-section">',
          '<div class="report-section-title">异常概述</div>',
          '<div class="report-section-body">',
            '<div class="report-kv"><div class="report-kv-key">异常类型</div><div class="report-kv-val">', escapeHtml(anomalyLabel), '</div></div>',
            '<div class="report-kv"><div class="report-kv-key">描述</div><div class="report-kv-val">', escapeHtml(desc || '-'), '</div></div>',
          '</div>',
        '</div>',
        '<div class="report-section">',
          '<div class="report-section-title">根因结论</div>',
          '<div class="report-section-body">', rootCauseHtml, categoryHtml, '</div>',
        '</div>',
        '<div class="report-section">',
          '<div class="report-section-title">假设列表 (', hypotheses.length, ')</div>',
          '<div class="report-section-body">', hypothesesHtml, '</div>',
        '</div>',
        '<div class="report-section">',
          '<div class="report-section-title">证据列表 (', evidence.length, ')</div>',
          '<div class="report-section-body">', evidenceHtml, '</div>',
        '</div>',
        '<div class="report-section">',
          '<div class="report-section-title">改进建议</div>',
          '<div class="report-section-body">', recsHtml, '</div>',
        '</div>',
        '<div class="report-section">',
          '<div class="report-section-title">元信息</div>',
          '<div class="report-section-body">',
            '<div class="report-kv"><div class="report-kv-key">任务 ID</div><div class="report-kv-val">', escapeHtml(taskId), '</div></div>',
            '<div class="report-kv"><div class="report-kv-key">创建时间</div><div class="report-kv-val">', escapeHtml(formatDateTime(createdAt)), '</div></div>',
            '<div class="report-kv"><div class="report-kv-key">完成时间</div><div class="report-kv-val">', escapeHtml(formatDateTime(completedAt)), '</div></div>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
  }

  function renderHypothesesHtml(list) {
    if (!list || list.length === 0) return '<div class="report-empty">未生成假设</div>';
    var html = '<ul class="report-list">';
    list.forEach(function (h) {
      var id = h.id || '-';
      var probPct = fmtPercent(h.probability);
      var st = h.status || 'pending';
      var stCfg = STATUS_LABELS[st] || { text: st, cls: 'pending' };
      var desc = h.description || '';
      var support = Array.isArray(h.supporting_evidence) ? h.supporting_evidence : [];
      var refute  = Array.isArray(h.refuting_evidence) ? h.refuting_evidence : [];
      html += '<li class="report-hyp">';
      html += '<div class="report-hyp-head">';
      html +=   '<span class="report-hyp-id">' + escapeHtml(String(id)) + '</span>';
      html +=   '<span class="report-status ' + stCfg.cls + '">' + escapeHtml(stCfg.text) + '</span>';
      html +=   '<span class="report-prob">概率 ' + probPct + '</span>';
      html += '</div>';
      html += '<div class="report-hyp-desc">' + escapeHtml(desc) + '</div>';
      if (support.length > 0) {
        html += '<div class="report-sub"><b>支持证据：</b>' + support.map(function (e) { var s = (e && typeof e === 'object') ? (e.id || e.content || JSON.stringify(e)) : String(e); return escapeHtml(s); }).join('、') + '</div>';
      }
      if (refute.length > 0) {
        html += '<div class="report-sub"><b>反对证据：</b>' + refute.map(function (e) { var s = (e && typeof e === 'object') ? (e.id || e.content || JSON.stringify(e)) : String(e); return escapeHtml(s); }).join('、') + '</div>';
      }
      html += '</li>';
    });
    html += '</ul>';
    return html;
  }

  function renderEvidenceHtml(list) {
    if (!list || list.length === 0) return '<div class="report-empty">未收集到证据</div>';
    var html = '<ul class="report-list">';
    list.forEach(function (ev) {
      var id      = ev.id || '-';
      var source  = ev.source || '-';
      var tool    = ev.tool_name || '-';
      var content = ev.content == null ? '-' : (typeof ev.content === 'string' ? ev.content : JSON.stringify(ev.content));
      var rel     = fmtPercent(ev.relevance_score);
      var conf    = fmtPercent(ev.confidence);
      html += '<li class="report-evi">';
      html += '<div class="report-evi-head">';
      html +=   '<span class="report-evi-id">' + escapeHtml(String(id)) + '</span>';
      html +=   '<span class="report-status pending">来源: ' + escapeHtml(String(source)) + '</span>';
      html +=   '<span class="report-score">相关度 ' + rel + ' · 置信度 ' + conf + '</span>';
      html += '</div>';
      html += '<div class="report-evi-content">' + escapeHtml(String(content)) + '</div>';
      html += '<div class="report-evi-meta"><span>工具: ' + escapeHtml(String(tool)) + '</span></div>';
      html += '</li>';
    });
    html += '</ul>';
    return html;
  }

  function renderRecommendationsHtml(finalReport) {
    var recs = null;
    if (finalReport) {
      if (Array.isArray(finalReport.recommendations)) recs = finalReport.recommendations;
      else if (Array.isArray(finalReport.improvement_suggestions)) recs = finalReport.improvement_suggestions;
      else if (Array.isArray(finalReport.suggestions)) recs = finalReport.suggestions;
    }
    if (!recs || recs.length === 0) return '<div class="report-empty">暂无建议</div>';
    var html = '<ol class="report-recs">';
    recs.forEach(function (r) {
      if (r && typeof r === 'object') {
        const t = r.title || r.action || r.description || JSON.stringify(r);
        html += '<li>' + escapeHtml(String(t)) + '</li>';
      } else {
        html += '<li>' + escapeHtml(String(r)) + '</li>';
      }
    });
    html += '</ol>';
    return html;
  }

  // ============ 快捷按钮 ============
  function renderQuickRow() {
    var html = '';
    Object.keys(ANOMALY_TYPES).forEach(function (key) {
      var active = state.selectedAnomalyType === key ? ' active' : '';
      html += '<button class="quick-btn' + active + '" data-quick="' + escapeHtml(key) + '">' +
              escapeHtml(ANOMALY_TYPES[key]) + '</button>';
    });
    dom.quickRow.innerHTML = html;
    const btns = dom.quickRow.querySelectorAll('[data-quick]');
    for (let i = 0; i < btns.length; i++) {
      btns[i].addEventListener('click', function () {
        const key = this.getAttribute('data-quick');
        if (state.isLoading) return;
        if (state.selectedAnomalyType === key) {
          state.selectedAnomalyType = null;
        } else {
          state.selectedAnomalyType = key;
          if (!dom.inputTextarea.value.trim()) {
            dom.inputTextarea.value = ANOMALY_TEMPLATES[key] || '';
            autoResizeTextarea();
          }
        }
        renderQuickRow();
        dom.inputTextarea.focus();
      });
    }
  }
  function selectAnomalyType(key) {
    state.selectedAnomalyType = key;
    renderQuickRow();
  }

  // ============ 输入区 ============
  function autoResizeTextarea() {
    var ta = dom.inputTextarea;
    if (!ta) return;
    ta.style.height = 'auto';
    var h = Math.min(200, Math.max(40, ta.scrollHeight));
    ta.style.height = h + 'px';
  }
  function setLoadingUI(isLoading) {
    state.isLoading = isLoading;
    dom.inputTextarea.disabled = isLoading;
    if (isLoading) {
      dom.sendIcon.classList.add('hidden');
      dom.stopIcon.classList.remove('hidden');
      dom.sendBtn.title = '停止';
      dom.sendBtn.setAttribute('aria-label', '停止');
    } else {
      dom.sendIcon.classList.remove('hidden');
      dom.stopIcon.classList.add('hidden');
      dom.sendBtn.title = '发送';
      dom.sendBtn.setAttribute('aria-label', '发送');
    }
  }

  // ============ 发送 / API ============
  function handleSendClick() {
    if (state.isLoading) {
      // 关闭 SSE 订阅，不再接收后续事件；不调用后端 cancel API
      closeProgressStream();
      if (state.abortController) {
        try { state.abortController.abort(); } catch (e) { /* ignore */ }
      }
      state.abortController = null;
      setLoadingUI(false);
      renderMessages({ preserveScroll: true });
      return;
    }
    sendMessage();
  }

  function persistUserMessage(session, userMsg, text) {
    return fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(session.id) + '/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'user', content: text })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (saved) {
      if (saved && saved.id) userMsg.id = saved.id;
      return saved;
    });
  }

  function sendMessage() {
    if (state.isLoading) return;
    var text = (dom.inputTextarea.value || '').trim();
    if (!text) return;
    var type = state.selectedAnomalyType || 'overstation_check';
    var session = ensureSession();
    var commitPromise = commitDraftSession(session); // 同步部分立即执行，返回 Promise
    var userMsg = {
      id: uid('m-'),
      role: 'user',
      content: text,
      timestamp: nowIso(),
      anomalyType: type
    };
    session.messages.push(userMsg);
    session.updatedAt = userMsg.timestamp;
    updateSessionTitle(session, text, commitPromise);
    sortSessions();
    saveSessions();
    dom.inputTextarea.value = '';
    autoResizeTextarea();
    renderSidebar();
    setLoadingUI(true);
    renderMessages();
    // 持久化 user 消息成功后再进入回复/RCA 路由，避免重启后只剩 assistant 回复。
    var userPersistPromise = commitPromise.then(function () {
      return persistUserMessage(session, userMsg, text);
    });
    userPersistPromise.then(function () {
      routeChatMessage(type, text, session, commitPromise);
    }).catch(function (err) {
      console.error('[sendMessage] user 消息持久化失败：', err);
      setLoadingUI(false);
      renderMessages({ preserveScroll: true });
      alert('消息保存失败，请重试');
    });
  }

  function routeChatMessage(type, text, session, commitPromise) {
    callChatExecuteAPI(text, session.id)
      .then(function (result) {
        if (result && (result.intent === 'rca_analysis' || result.route === 'rca')) {
          runAnalysis(type, text, session, commitPromise);
          return;
        }
        appendChatAssistantMessage(session, result, commitPromise);
      })
      .catch(function (err) {
        appendChatAssistantMessage(session, {
          intent: 'general_chat',
          content: '请求处理失败：' + (err && err.message ? err.message : '未知错误'),
          metadata: { error: true }
        }, commitPromise);
      });
  }

  function callChatExecuteAPI(message, conversationId) {
    return fetch(CHAT_API_BASE + '/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message, conversation_id: conversationId || null })
    }).then(function (res) {
      if (!res.ok) {
        const err = new Error('聊天执行失败 (HTTP ' + res.status + ')');
        err.status = res.status;
        throw err;
      }
      return res.json();
    });
  }

  function appendChatAssistantMessage(session, result, commitPromise) {
    var content = (result && result.content) || '';
    var metadata = {
      intent: (result && result.intent) || 'general_chat',
      items: result && result.items ? result.items : undefined,
      details: result && result.metadata ? result.metadata : undefined
    };
    var aiMsg = {
      id: uid('m-'),
      role: 'assistant',
      content: content,
      timestamp: nowIso(),
      metadata: metadata
    };
    session.messages.push(aiMsg);
    session.updatedAt = aiMsg.timestamp;
    sortSessions();
    saveSessions();
    setLoadingUI(false);
    renderSidebar();
    renderMessages();
    (commitPromise || Promise.resolve(session)).then(function () {
      return fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(session.id) + '/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: 'assistant',
          content: content,
          metadata: metadata
        })
      });
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (saved) {
      if (saved && saved.id) aiMsg.id = saved.id;
    }).catch(function (persistErr) {
      console.error('[appendChatAssistantMessage] assistant 消息持久化失败：', persistErr);
    });
  }

  function retryAnalysis(type, desc) {
    if (state.isLoading) return;
    var session = currentSession();
    if (!session) return;
    setLoadingUI(true);
    renderMessages();
    runAnalysis(type || 'overstation_check', desc || '', session);
  }

  // ============ Task 8: EventSource 进度流 ============
  // 进度流的运行时资源：保存当前 EventSource 实例及关联上下文，
  // 便于 closeProgressStream 清理；与 state.progress（含 lastSeq/steps/expanded）解耦。
  var progressStream = {
    source: null,
    taskId: null,
    messageId: null,
    session: null
  };

  // 后端事件类型 -> 前端 step status 映射（5 种 status：pending/running/success/failed/cancelled）
  function mapEventTypeToStatus(eventType) {
    switch (eventType) {
      case 'task_started':
      case 'node_started':
        return 'running';
      case 'task_done':
      case 'node_completed':
        return 'success';
      case 'task_error':
      case 'node_error':
        return 'failed';
      case 'heartbeat':
        return 'pending';
      default:
        return 'pending';
    }
  }

  function buildProgressEventsUrl(events_url, afterSeq) {
    var seq = Number(afterSeq || 0);
    var sep = events_url.indexOf('?') >= 0 ? '&' : '?';
    return events_url + sep + 'after=' + encodeURIComponent(String(seq));
  }

  function getActiveProgressMessageId(fallbackMessageId) {
    return progressStream.messageId || fallbackMessageId;
  }

  // 订阅 SSE 进度流（Task 8 主入口，QA 修复：使用命名事件 addEventListener）
  // 入参：events_url 来自 /analyze 响应；taskId 后端任务 ID；messageId 对应 assistant 消息；
  //       session 当前会话。
  // 行为：使用 new EventSource(events_url) 创建连接；
  //       为后端 4 种命名事件（step/done/error/heartbeat）分别 addEventListener；
  //       解析 e.data 后调用 handleProgressEvent；done/error 监听器显式注入
  //       event_type 字段（事件名 == 事件类型，handleProgressEvent 通过 type 字段路由）。
  // 浏览器 EventSource.onmessage 只接收未命名 `message` 事件，命名事件必须用
  // addEventListener('step', ...)/('done', ...)/('error', ...)/('heartbeat', ...)。
  function openProgressStream(events_url, taskId, messageId, session) {
    if (!events_url || typeof EventSource === 'undefined') return;
    // 清理可能残留的旧连接
    closeProgressStream();
    var streamUrl = buildProgressEventsUrl(events_url, state.progress.lastSeq || 0);
    var es = new EventSource(streamUrl);
    progressStream.source = es;
    progressStream.taskId = taskId;
    progressStream.messageId = messageId;
    progressStream.session = session;

    // step 事件：保留后端传来的 event_type（node_started/node_completed 等）
    es.addEventListener('step', function (e) {
      try {
        var payload = JSON.parse(e.data);
        if (!payload.event_type && payload.type) {
          payload.event_type = payload.type;
        }
        handleProgressEvent(payload, taskId, getActiveProgressMessageId(messageId), session);
      } catch (parseErr) {
        // 忽略非 JSON 帧
      }
    });

    // done 事件：显式注入 event_type='done'（事件名 == 事件类型）
    es.addEventListener('done', function (e) {
      try {
        var payload = JSON.parse(e.data);
        payload.event_type = 'done';
        handleProgressEvent(payload, taskId, getActiveProgressMessageId(messageId), session);
      } catch (parseErr) {
        // 忽略非 JSON 帧
      }
    });

    // error 事件：显式注入 event_type='error'（注意：这是 EventSource 的 named
    // 'error' 事件，与连接级 error 不同；连接级 onerror 仍用于网络重连）
    es.addEventListener('error', function (e) {
      if (!e.data) return;
      try {
        var payload = JSON.parse(e.data);
        payload.event_type = 'error';
        handleProgressEvent(payload, taskId, getActiveProgressMessageId(messageId), session);
      } catch (parseErr) {
        // 非 JSON 的连接错误帧交给 EventSource 自身重连处理，不合成任务失败
      }
    });

    // heartbeat 事件：注入 event_type='heartbeat'，handleProgressEvent 内部
    // 仅推进 lastSeq、不改变 steps
    es.addEventListener('heartbeat', function (e) {
      try {
        var payload = e.data ? JSON.parse(e.data) : {};
        payload.event_type = 'heartbeat';
        handleProgressEvent(payload, taskId, getActiveProgressMessageId(messageId), session);
      } catch (parseErr) {
        handleProgressEvent({ event_type: 'heartbeat' }, taskId, messageId, session);
      }
    });

    // 连接级 onerror：浏览器自动重连；不主动 close，done/error 事件到达时再清理
    es.onerror = function () {
      // 不做主动操作；EventSource 会按浏览器策略重连
    };
  }

  // 消费单个 SSE 事件帧（Task 8 核心状态机）
  // 入参：event 解析后的对象（含 seq/node_name/event_type/title/summary/detail/detail_json）；
  //       taskId/messageId/session 透传自 openProgressStream。
  // 行为：按 event.seq > state.progress.lastSeq 去重；heartbeat 不改变 steps；
  //       done 事件关闭 SSE 并调 callReportAPI + appendReportToProgressMessage；
  //       error 事件标记消息失败；step 事件按 event_type 映射后写入 state.progress.steps[node_name]，
  //       并同步到消息的 progress 字段。
  function handleProgressEvent(event, taskId, messageId, session) {
    if (!event) return;
    var type = event.event_type || event.type || '';
    if (event.seq != null) {
      if (event.seq <= state.progress.lastSeq) return;
      state.progress.lastSeq = event.seq;
    } else if (event.seq == null && type !== 'done' && type !== 'error' && type !== 'heartbeat') {
      return;
    }
    // 保留 expanded
    if (!state.progress.expanded) state.progress.expanded = {};

    var dispatchHandled = false;
    switch (type) {
      case 'heartbeat':
        // heartbeat：仅推进 lastSeq，不修改 steps
        dispatchHandled = true;
        break;
      case 'done':
        // 终态：done 事件
        closeProgressStream();
        var doneIdx = findMessageIndexById(session, messageId);
        if (doneIdx >= 0 && (session.messages[doneIdx].report || session.messages[doneIdx].report_snapshot)) {
          session.messages[doneIdx].progressStatus = 'completed';
          setLoadingUI(false);
          renderMessages({ preserveScroll: true });
          dispatchHandled = true;
          break;
        }
        callReportAPI(taskId)
          .then(function (report) {
            appendReportToProgressMessage(session, report, { taskId: taskId, messageId: messageId });
          })
          .catch(function (err) {
            var msgIdx = findMessageIndexById(session, messageId);
            if (msgIdx >= 0) {
              var msg = session.messages[msgIdx];
              msg.error = true;
              msg.content = '获取报告失败：' + (err && err.message ? err.message : '未知错误');
              msg.errorType = msg.errorType || msg.anomalyType || 'overstation_check';
              msg.errorDesc = msg.errorDesc || msg.description || '';
              msg.progressStatus = 'failed';
            }
            setLoadingUI(false);
            renderMessages();
          });
        dispatchHandled = true;
        break;
      case 'error':
        // 终态：error 事件
        closeProgressStream();
        var errMsgIdx = findMessageIndexById(session, messageId);
        if (errMsgIdx >= 0) {
          var errMsg = session.messages[errMsgIdx];
          errMsg.error = true;
          errMsg.content = event.title || event.summary || '任务执行失败';
          errMsg.progressStatus = 'failed';
        }
        setLoadingUI(false);
        renderMessages();
        dispatchHandled = true;
        break;
      default:
        break;
    }
    if (dispatchHandled) return;

    // step 事件：仅处理带 node_name 的事件
    var nodeName = event.node_name || '';
    if (!nodeName) return;
    var status = mapEventTypeToStatus(type);
    if (!state.progress.steps) state.progress.steps = {};
    if (!state.progress.events) state.progress.events = [];
    state.progress.events.push({
      seq: event.seq,
      node_name: event.node_name || '',
      event_type: type,
      status: status,
      title: event.title || '',
      summary: event.summary || '',
      detail_json: event.detail_json || null
    });
    state.progress.steps[nodeName] = {
      status: status,
      title: event.title || '',
      summary: event.summary || '',
      detail: event.detail || '',
      detail_json: event.detail_json || null
    };
    // 同步到消息对象的 progress 字段
    var msgIdx2 = findMessageIndexById(session, messageId);
    if (msgIdx2 >= 0) {
      session.messages[msgIdx2].progress = {
        lastSeq: state.progress.lastSeq,
        steps: state.progress.steps,
        events: state.progress.events
      };
    }
    renderMessages({ preserveScroll: true });
  }

  // 关闭当前 SSE 连接并清理资源。
  // 严禁调用后端 cancel API；本函数仅结束前端接收，保留后端任务继续运行。
  function closeProgressStream() {
    if (progressStream.source) {
      try { progressStream.source.close(); } catch (e) { /* ignore */ }
    }
    progressStream.source = null;
    progressStream.taskId = null;
    progressStream.messageId = null;
    progressStream.session = null;
  }

  function runAnalysis(type, description, session, commitPromise) {
    // 1) 立即创建带 progress 字段的 assistant 消息，避免用户在等待分析时空白
    var aiMsg = {
      id: uid('m-'),
      role: 'assistant',
      content: '',
      progress: { lastSeq: 0, steps: {}, events: [] },
      progressStatus: 'running',
      taskId: null,
      eventsUrl: null,
      anomalyType: type,
      errorType: type,
      errorDesc: description,
      timestamp: nowIso()
    };
    session.messages.push(aiMsg);
    session.updatedAt = aiMsg.timestamp;
    sortSessions();
    saveSessions();
    setLoadingUI(true);
    renderSidebar();
    renderMessages();

    // 2) 重置 state.progress（保留 expanded 跨任务的诉求由 toggleProgressStep 自行处理）
    state.progress = {
      lastSeq: 0,
      steps: {},
      events: [],
      expanded: state.progress.expanded || {}
    };

    var conversationReady = commitPromise || Promise.resolve(session);

    // 3) 调 async /analyze 接口；不串行调 /reports
    callAnalyzeAPI(type, description)
      .then(function (analyzeResp) {
        if (!analyzeResp || !analyzeResp.task_id) {
          throw new Error('后端返回缺少 task_id');
        }
        // 把 taskId/events_url 写入 assistant 消息
        aiMsg.taskId = analyzeResp.task_id;
        aiMsg.eventsUrl = analyzeResp.events_url || null;
        // 4) 打开 SSE 订阅；不再串行 callReportAPI
        openProgressStream(analyzeResp.events_url, analyzeResp.task_id, aiMsg.id, session);
        // 持久化 progress 消息（task_id 进入数据库；report_snapshot 由 appendReportToProgressMessage 后续 PATCH）
        conversationReady.then(function () {
          return fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(session.id) + '/messages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              role: 'assistant',
              content: '',
              anomaly_type: type,
              task_id: analyzeResp.task_id
            })
          });
        }).then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        }).then(function (saved) {
          if (saved && saved.id) {
            aiMsg.id = saved.id;
            // 同步 messageId 到 progressStream，确保后续 PATCH 用到真实 ID
            if (progressStream.messageId && progressStream.session === session) {
              progressStream.messageId = saved.id;
            }
          }
        }).catch(function (persistErr) {
          // eslint-disable-next-line no-console
          console.error('[runAnalysis] progress 消息持久化失败：', persistErr);
        });
      })
      .catch(function (err) {
        // 错误处理：把同一条 progress 消息标记为 error
        var errText;
        if (err && err.name === 'AbortError') {
          errText = '请求已被取消或超时（120 秒）';
        } else if (err && err.status === 404) {
          errText = '任务不存在（404）';
        } else if (err && err.message) {
          errText = err.message;
        } else {
          errText = '未知错误';
        }
        aiMsg.error = true;
        aiMsg.content = errText;
        aiMsg.errorType = type;
        aiMsg.errorDesc = description;
        aiMsg.progressStatus = 'failed';
        closeProgressStream();
        setLoadingUI(false);
        renderMessages();
        // 持久化错误消息
        conversationReady.then(function () {
          return fetch(CHAT_API_BASE + '/conversations/' + encodeURIComponent(session.id) + '/messages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              role: 'assistant',
              content: errText,
              error: true,
              metadata: { errorType: type, errorDesc: description }
            })
          });
        }).then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        }).then(function (saved) {
          if (saved && saved.id) aiMsg.id = saved.id;
        }).catch(function (persistErr) {
          // eslint-disable-next-line no-console
          console.error('[runAnalysis] 错误消息持久化失败：', persistErr);
        });
      });
  }

  function callAnalyzeAPI(type, description, signal) {
    // POST /api/v1/rca/analyze
    var body = {
      event: {
        anomaly_type: type,
        description: description,
        source_system: 'MES'
      }
    };
    return fetch(API_BASE + '/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: signal
    }).then(function (res) {
      if (!res.ok) {
        const err = new Error('分析请求失败 (HTTP ' + res.status + ')');
        err.status = res.status;
        throw err;
      }
      return res.json();
    });
  }

  function callReportAPI(taskId, signal) {
    // GET /api/v1/rca/reports/{task_id}
    return fetch(API_BASE + '/reports/' + encodeURIComponent(taskId), {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: signal
    }).then(function (res) {
      if (res.status === 404) {
        const e404 = new Error('任务不存在: ' + taskId);
        e404.status = 404;
        throw e404;
      }
      if (!res.ok) {
        const err = new Error('获取报告失败 (HTTP ' + res.status + ')');
        err.status = res.status;
        throw err;
      }
      return res.json();
    });
  }

  // ============ 侧边栏交互 ============
  function toggleSidebar(force) {
    var collapsed = (typeof force === 'boolean') ? force : !state.sidebarCollapsed;
    state.sidebarCollapsed = collapsed;
    if (collapsed) {
      dom.sidebar.classList.add('collapsed');
      dom.sidebarToggleOuter.classList.remove('hidden');
    } else {
      dom.sidebar.classList.remove('collapsed');
      dom.sidebarToggleOuter.classList.add('hidden');
    }
  }

  // ============ 事件绑定 ============
  function bindEvents() {
    dom.loginForm.addEventListener('submit', handleLogin);
    dom.loginUsername.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); handleLogin(e); }
    });
    dom.loginPassword.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); handleLogin(e); }
    });
    if (dom.passwordToggle) dom.passwordToggle.addEventListener('click', togglePasswordVisibility);
    dom.logoutBtn.addEventListener('click', handleLogout);
    dom.newChatBtn.addEventListener('click', function () {
      if (state.isLoading) return;
      createSession();
    });
    dom.searchChatBtn.addEventListener('click', function () {
      if (state.isLoading) return;
      openSearchModal();
    });
    dom.modalSearchInput.addEventListener('input', function () {
      state.modalSearchKeyword = this.value || '';
      renderSearchModalResults();
    });
    dom.closeSearchModal.addEventListener('click', function () {
      closeSearchModal();
    });
    dom.searchModal.addEventListener('click', function (e) {
      if (e.target === dom.searchModal) closeSearchModal();
    });
    dom.searchModalResults.addEventListener('click', function (e) {
      var newBtn = e.target.closest && e.target.closest('#modalNewChatBtn');
      var item = e.target.closest && e.target.closest('[data-modal-id]');
      var id = null;
      if (newBtn) {
        e.preventDefault();
        closeSearchModal();
        if (state.isLoading) return;
        createSession();
        return;
      }
      if (item) {
        e.preventDefault();
        id = item.getAttribute('data-modal-id');
        closeSearchModal();
        if (id) switchSession(id);
      }
    });
    document.addEventListener('keydown', function (e) {
      if (state.activeMenuSessionId && (e.key === 'Escape' || e.key === 'Esc')) {
        e.preventDefault();
        state.activeMenuSessionId = null;
        renderSidebar();
        return;
      }
      if (!state.modalOpen) return;
      if (e.key === 'Escape' || e.key === 'Esc') {
        e.preventDefault();
        closeSearchModal();
      }
    });
    dom.sidebarToggleInner.addEventListener('click', function () { toggleSidebar(true); });
    dom.sidebarToggleOuter.addEventListener('click', function () { toggleSidebar(false); });

    dom.sessionsList.addEventListener('click', function (e) {
      var menuBtn = e.target.closest && e.target.closest('[data-menu]');
      var actionBtn = e.target.closest && e.target.closest('[data-action]');
      var menuEl = e.target.closest && e.target.closest('[data-session-menu]');
      var groupToggle = e.target.closest && e.target.closest('[data-session-group-toggle]');
      if (groupToggle) {
        e.preventDefault();
        e.stopPropagation();
        toggleSessionGroup(groupToggle.getAttribute('data-session-group-toggle'));
        return;
      }
      if (menuBtn) {
        e.preventDefault();
        e.stopPropagation();
        const menuId = menuBtn.getAttribute('data-menu');
        state.activeMenuSessionId = state.activeMenuSessionId === menuId ? null : menuId;
        renderSidebar();
        return;
      }
      if (actionBtn) {
        e.preventDefault();
        e.stopPropagation();
        const action = actionBtn.getAttribute('data-action');
        const actionId = actionBtn.getAttribute('data-action-id');
        if (action === 'rename') openRenameDialog(actionId);
        else if (action === 'pin') togglePinSession(actionId);
        else if (action === 'archive') archiveSession(actionId);
        else if (action === 'delete') openDeleteDialog(actionId);
        return;
      }
      if (menuEl) {
        e.stopPropagation();
        return;
      }
      var item = e.target.closest && e.target.closest('.session-item');
      if (item) {
        state.activeMenuSessionId = null;
        const id = item.getAttribute('data-id');
        if (id) switchSession(id);
      }
    });
    document.addEventListener('click', function (e) {
      if (!state.activeMenuSessionId) return;
      if (e.target.closest && (e.target.closest('[data-session-menu]') || e.target.closest('[data-menu]'))) return;
      state.activeMenuSessionId = null;
      renderSidebar();
    });
    dom.renameCancelBtn.addEventListener('click', closeRenameDialog);
    dom.renameConfirmBtn.addEventListener('click', confirmRenameSession);
    dom.renameDialog.addEventListener('click', function (e) {
      if (e.target === dom.renameDialog) closeRenameDialog();
    });
    dom.renameInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); confirmRenameSession(); }
      if (e.key === 'Escape' || e.key === 'Esc') { e.preventDefault(); closeRenameDialog(); }
    });
    dom.deleteCancelBtn.addEventListener('click', closeDeleteDialog);
    dom.deleteConfirmBtn.addEventListener('click', confirmDeleteSession);
    dom.deleteDialog.addEventListener('click', function (e) {
      if (e.target === dom.deleteDialog) closeDeleteDialog();
    });

    dom.sendBtn.addEventListener('click', handleSendClick);
    dom.inputTextarea.addEventListener('input', autoResizeTextarea);
    dom.inputTextarea.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        if (!state.isLoading) sendMessage();
      }
    });
  }

  // ============ 初始化 ============
  function init() {
    cacheDom();
    bindEvents();
    autoResizeTextarea();
    if (isLoggedIn()) {
      enterApp();
    } else {
      dom.loginView.classList.remove('hidden');
      dom.appView.classList.add('hidden');
      setTimeout(function () { dom.loginUsername.focus(); }, 50);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
