"""静态聊天页面交互断言。"""

from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
INDEX_HTML = STATIC_DIR / "index.html"
STYLES_CSS = STATIC_DIR / "styles.css"
APP_JS = STATIC_DIR / "app.js"


def read_index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def read_styles_css() -> str:
    return STYLES_CSS.read_text(encoding="utf-8")


def read_app_js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_index_html_links_external_assets():
    """index.html 应通过 <link> 和 <script src> 引用拆分后的 CSS/JS。"""
    html = read_index_html()

    assert '<link rel="stylesheet" href="/styles.css" />' in html
    assert '<script src="/app.js"></script>' in html
    # 不应再内嵌 <style> 或 <script> 代码块
    assert "<style>" not in html
    assert "<script>" not in html


def test_login_inputs_do_not_expose_default_credentials_and_password_toggle_exists():
    """登录页不应展示默认账号密码，密码框应支持眼睛按钮切换明文。"""
    html = read_index_html()
    css = read_styles_css()
    js = read_app_js()

    assert 'id="loginUsername" placeholder=""' in html
    assert 'id="loginPassword" placeholder=""' in html
    assert 'placeholder="admin"' not in html
    assert 'placeholder="admin123"' not in html
    assert 'id="passwordToggle"' in html
    assert 'aria-label="显示密码"' in html
    assert 'password-field-wrap' in html
    assert '.password-field-wrap' in css
    assert '.password-toggle' in css
    assert 'dom.passwordToggle' in js
    assert 'function togglePasswordVisibility' in js
    assert "dom.loginPassword.type = 'text'" in js
    assert "dom.loginPassword.type = 'password'" in js


def test_password_toggle_switches_open_and_closed_eye_icons():
    """密码眼睛按钮应有闭眼/睁眼两种图标，并随状态切换。"""
    html = read_index_html()
    css = read_styles_css()
    js = read_app_js()

    assert 'id="passwordEyeClosed"' in html
    assert 'id="passwordEyeOpen"' in html
    assert 'class="password-eye password-eye-open hidden"' in html
    assert '.password-eye.hidden' in css
    assert 'dom.passwordEyeClosed' in js
    assert 'dom.passwordEyeOpen' in js
    assert "dom.passwordEyeClosed.classList.add('hidden')" in js
    assert "dom.passwordEyeOpen.classList.remove('hidden')" in js
    assert "dom.passwordEyeClosed.classList.remove('hidden')" in js
    assert "dom.passwordEyeOpen.classList.add('hidden')" in js


def test_user_message_bubble_has_readable_width_and_actions():
    """用户消息气泡应更宽，并带复制、编辑操作。"""
    css = read_styles_css()
    js = read_app_js()

    # CSS 选择器定义气泡宽度
    assert ".msg.user .msg-shell" in css
    assert "max-width: min(760px, 78vw)" in css
    # 动态 HTML 模板生成消息结构和按钮
    assert "msg-actions" in js
    assert "data-copy-message" in js
    assert "data-edit-message" in js
    assert "title=\"复制消息\"" in js
    assert "title=\"编辑消息\"" in js


def test_user_message_bubble_height_is_compact():
    """用户消息气泡应降低默认高度和字体大小，避免单行消息显得过厚。"""
    css = read_styles_css()
    user_bubble = css.split(".msg.user .msg-content {")[1].split("}")[0]

    assert "padding: 8px 20px" in user_bubble
    assert "font-size: 14px" in user_bubble
    assert "line-height: 1.35" in user_bubble
    assert "border-radius: 22px" in user_bubble


def test_chat_input_textarea_hides_default_scrollbar():
    """聊天输入框默认不应显示原生滚动条，但仍保留可滚动能力。"""
    css = read_styles_css()

    assert "overflow-y: auto" in css.split(".input-textarea {")[1].split("}")[0]
    assert "scrollbar-width: none" in css.split(".input-textarea {")[1].split("}")[0]
    assert ".input-textarea::-webkit-scrollbar" in css
    assert "display: none" in css.split(".input-textarea::-webkit-scrollbar")[1].split("}")[0]


def test_chat_page_topbar_does_not_show_product_title():
    """聊天页左上角不应显示产品标题。"""
    html = read_index_html()
    js = read_app_js()

    assert '<div class="topbar-title" id="topbarTitle">XCMG RCA Agent</div>' not in html
    assert "dom.topbarTitle.textContent = 'XCMG RCA Agent'" not in js
    assert "dom.topbarTitle.textContent = s.title || 'XCMG RCA Agent'" not in js


def test_index_html_has_favicon_link():
    """index.html 应引用浏览器标签页图标。"""
    html = read_index_html()

    assert '<link rel="icon" type="image/png" href="/assest/xcmg.png" />' in html


def test_user_message_copy_and_edit_behaviors_exist():
    """用户消息应支持复制当前内容，以及进入编辑发送状态。"""
    js = read_app_js()

    # JS 行为函数
    assert "function copyMessageText" in js
    assert "navigator.clipboard.writeText" in js
    assert "function startEditingMessage" in js
    assert "function renderEditingMessageHtml" in js
    assert "function submitEditingMessage" in js
    # 动态 HTML 模板的 data 属性与文案
    assert "data-edit-submit" in js
    assert "data-edit-cancel" in js
    assert "编辑消息" in js


def test_assistant_plain_text_renders_markdown_safely():
    """助手普通回复应安全渲染 Markdown 标题、加粗、列表，而不是显示原始标记。"""
    js = read_app_js()
    css = read_styles_css()

    assert "function renderAssistantMarkdownHtml" in js
    body = _extract_function_body(js, "renderAssistantMarkdownHtml")
    assert body, "必须定义 renderAssistantMarkdownHtml"
    assert "escapeHtml" in body, "Markdown 渲染前必须先转义原始文本"
    assert "msg-markdown" in js, "助手普通文本必须包裹 msg-markdown 容器"
    assert "renderAssistantMarkdownHtml(m.content)" in js
    assert "parts.push('<div>' + escapeHtml(m.content) + '</div>')" not in js
    assert "<h1>" in js and "<h2>" in js and "<h3>" in js
    assert "<strong>" in js and "<ul>" in js and "<li>" in js
    assert "<code>" in js, "行内代码 `code` 也应被渲染"
    assert "paragraph" in js or "段落" in js, "连续非空行应合并为段落"
    body2 = _extract_function_body(js, "renderAssistantMarkdownHtml")
    assert "## " in body2 and "#### " in body2, "必须识别 ## 和 #### 标题"
    assert '"* "' in body2 or "'* '" in body2, "必须识别 * 开头的列表项"
    assert ".msg-markdown" in css
    assert ".msg-markdown h1" in css
    assert ".msg-markdown h2" in css
    assert ".msg-markdown h3" in css
    assert ".msg-markdown ul" in css
    assert ".msg-markdown li" in css
    assert ".msg-markdown strong" in css
    assert ".msg-markdown code" in css or ".msg-markdown p" in css


def test_assistant_markdown_font_size_matches_user_bubble():
    """Agent 普通回复正文应与用户气泡字体一致，加粗/标题字号同步缩小。"""
    css = read_styles_css()
    user_bubble = css.split(".msg.user .msg-content {")[1].split("}")[0]
    markdown = css.split(".msg-markdown {")[1].split("}")[0]
    h1 = css.split(".msg-markdown h1 {")[1].split("}")[0]
    h2 = css.split(".msg-markdown h2 {")[1].split("}")[0]
    h3 = css.split(".msg-markdown h3 {")[1].split("}")[0]
    code = css.split(".msg-markdown code {")[1].split("}")[0]

    assert "font-size: 14px" in user_bubble
    assert "font-size: 14px" in markdown
    assert "font-size: 16px" in h1
    assert "font-size: 15px" in h2
    assert "font-size: 14px" in h3
    assert "font-size: 12px" in code


def test_message_actions_are_hover_revealed_and_copy_has_success_state():
    """复制/编辑默认隐藏，仅悬浮当前消息时显示；复制成功应显示对勾。"""
    css = read_styles_css()
    js = read_app_js()

    # CSS：默认隐藏 + hover 时显示
    assert ".msg-actions {" in css
    assert "opacity: 0" in css
    assert "pointer-events: none" in css
    assert ".msg.user:hover .msg-actions" in css
    assert "opacity: 1" in css
    assert "pointer-events: auto" in css
    # JS：复制成功状态变量 + 动态 HTML 模板
    assert "copiedMessageId" in js
    assert "data-copy-check" in js
    assert "setTimeout(function () {" in js


def test_edit_mode_preserves_scroll_position():
    """点击编辑只重绘当前消息，不应自动滚动到底部。"""
    js = read_app_js()

    assert "renderMessages({ preserveScroll: true })" in js
    assert "function renderMessages(options)" in js
    assert "var shouldScrollToBottom = !(options && options.preserveScroll);" in js
    assert "if (shouldScrollToBottom) scrollToBottom();" in js


def test_sidebar_session_items_are_compact():
    """左侧会话项的纵向空白应缩小，列表更紧凑。"""
    css = read_styles_css()

    assert "position: relative; height: 30px; padding: 0 var(--space-3);" in css


def test_sidebar_groups_are_dark_and_collapsible():
    """左侧会话分组标题应为深黑色，并支持折叠/展开。"""
    css = read_styles_css()
    js = read_app_js()

    assert "color: var(--color-text);" in css
    # 动态 HTML 模板 + JS 行为
    assert "data-session-group-toggle" in js
    assert "collapsedSessionGroups" in js
    assert "toggleSessionGroup" in js
    assert "sessions-group-title-btn" in js
    assert "sessions-group-chevron" in js
    assert "aria-expanded" in js


def test_sidebar_group_chevron_is_right_aligned_and_hover_revealed():
    """分组箭头应紧跟分组名右侧，默认隐藏，悬浮标题时显示。"""
    css = read_styles_css()
    js = read_app_js()

    cluster_index = js.index('<span class="sessions-group-heading-cluster">')
    label_index = js.index('<span class="sessions-group-label">')
    chevron_index = js.index('<svg class="sessions-group-chevron"')
    count_index = js.index('<span class="sessions-group-count">')
    cluster_close_index = js.index('</span>', chevron_index)
    assert cluster_index < label_index < chevron_index < cluster_close_index < count_index
    assert ".sessions-group-heading-cluster {" in css
    assert ".sessions-group-chevron {\n  width: 14px" in css
    assert "margin-left: auto" not in css.split(".sessions-group-chevron {")[1].split("}")[0]
    assert ".sessions-group-label { flex: 0 0 auto; }" in css
    assert ".sessions-group-count {\n  margin-left: auto" in css
    assert "opacity: 0;\n  transform: translateX(-2px);" in css
    assert ".sessions-group-title-btn:hover .sessions-group-chevron,\n.sessions-group-title-btn:focus-visible .sessions-group-chevron" in css
    assert "opacity: 1;\n  transform: translateX(0);" in css
    assert 'points="9 6 15 12 9 18"' in js
    assert ".sessions-group:not(.collapsed) .sessions-group-chevron { transform: rotate(90deg); }" in css


# ═══════════════════════════════════════════════════════════════
# 聊天持久化静态约束 — RED 阶段
# ═══════════════════════════════════════════════════════════════

def test_no_localstorage_sessions_persistence():
    """app.js 中不得使用 localStorage 持久化会话列表。

    当前代码仍存在 `safeSave(STORAGE_KEYS.SESSIONS` 和
    `localStorage.setItem('rca_sessions'`，此测试预期失败。
    """
    js = read_app_js()

    assert "safeSave(STORAGE_KEYS.SESSIONS" not in js, (
        "禁止使用 safeSave(STORAGE_KEYS.SESSIONS 持久化会话列表"
    )
    assert "localStorage.setItem('rca_sessions'" not in js, (
        "禁止使用 localStorage.setItem('rca_sessions') 持久化会话列表"
    )


def test_localstorage_allowed_keys():
    """app.js 中允许保留 rca_current_session 和 rca_logged_in。

    这两个 key 用于当前会话标识和登录状态，不涉及会话列表持久化。
    """
    js = read_app_js()

    # 允许保留的 key
    assert "rca_current_session" in js, (
        "rca_current_session 用于标识当前活跃会话，应保留"
    )
    assert "rca_logged_in" in js, (
        "rca_logged_in 用于登录状态，应保留"
    )


def test_no_safe_save_for_sessions_list():
    """safeSave 调用不得传入 SESSIONS key。"""
    js = read_app_js()

    assert "safeSave(STORAGE_KEYS.SESSIONS" not in js, (
        "safeSave 不得用于 SESSIONS key，会话列表应由服务端管理"
    )


def test_send_message_waits_for_user_message_persistence_before_routing():
    """发送链路必须等 user 消息保存成功后再进入回复/RCA 路由。

    否则浏览器刷新或重启后，可能只持久化 assistant 回复，丢失 user 发言。
    """
    js = read_app_js()
    body = _extract_function_body(js, "sendMessage")
    assert body, "必须定义 function sendMessage"

    assert "persistUserMessage(" in body, "sendMessage 必须通过 helper 持久化 user 消息"
    assert "userPersistPromise" in body, "sendMessage 必须保留 user 消息持久化 Promise"
    route_pos = body.find("routeChatMessage(")
    persist_then_pos = body.find("userPersistPromise.then")
    assert persist_then_pos >= 0 and route_pos > persist_then_pos, (
        "routeChatMessage 必须在 userPersistPromise.then(...) 内部执行"
    )


def test_persist_user_message_updates_local_id_from_backend():
    """user 消息保存成功后必须用后端真实 id 替换本地临时 id。"""
    js = read_app_js()
    body = _extract_function_body(js, "persistUserMessage")
    assert body, "必须定义 function persistUserMessage(session, userMsg, text)"

    assert "role: 'user'" in body, "persistUserMessage 必须保存 role=user"
    assert "content: text" in body, "persistUserMessage 必须保存用户原文 content"
    assert "userMsg.id = saved.id" in body, "保存成功后必须同步后端真实消息 id"


def test_enter_app_loads_messages_for_initial_selected_session():
    """重启进入应用后，自动选中的历史会话也必须加载消息。"""
    js = read_app_js()
    body = _extract_function_body(js, "enterApp")
    assert body, "必须定义 function enterApp"

    assert "loadMessagesForSession(" in js, "必须抽取会话消息加载 helper"
    assert "loadMessagesForSession(state.currentSessionId" in body, (
        "enterApp 自动恢复 currentSessionId 后必须加载该会话消息"
    )


# ═══════════════════════════════════════════════════════════════
# 标题摘要 — RED 阶段
# ═══════════════════════════════════════════════════════════════

def test_update_session_title_no_longer_truncates_user_input():
    """updateSessionTitle 不应再直接截断用户输入作为标题。

    旧行为：`t.slice(0, 30) + '…'` 直接截断原文。
    新行为：应调用后端 summarize-title API 获取 LLM 摘要。
    """
    js = read_app_js()

    # 旧截断逻辑不应存在
    assert "t.slice(0, 30)" not in js, (
        "updateSessionTitle 不应再直接截断用户输入前30字符作为标题"
    )


def test_summarize_title_api_call_exists_in_frontend():
    """前端应调用 POST /api/v1/chat/conversations/{id}/summarize-title。"""
    js = read_app_js()

    assert "summarize-title" in js, (
        "前端必须调用 summarize-title API 端点生成标题"
    )


def test_summarize_title_api_called_after_first_user_message():
    """发送首条消息后应调用标题摘要 API。"""
    js = read_app_js()

    # 确认 sendMessage 流程中包含标题摘要调用
    assert "summarize-title" in js, (
        "sendMessage 中应包含对 summarize-title 的调用"
    )


def test_session_title_summary_waits_for_committed_conversation_id():
    """新建会话标题摘要必须等待真实后端会话 ID，避免刷新后回到“新对话”。"""
    js = read_app_js()
    send_body = _extract_function_body(js, "sendMessage")
    update_body = _extract_function_body(js, "updateSessionTitle")

    assert send_body, "必须定义 sendMessage"
    assert update_body, "必须定义 updateSessionTitle"
    assert "updateSessionTitle(session, text, commitPromise)" in send_body, (
        "sendMessage 必须把 commitPromise 传给 updateSessionTitle"
    )
    assert "commitPromise" in update_body and ".then(function" in update_body, (
        "updateSessionTitle 必须等待 commitPromise 完成后再请求 summarize-title"
    )
    summarize_pos = update_body.find("/summarize-title")
    wait_pos = update_body.find(".then(function")
    assert wait_pos >= 0 and summarize_pos >= 0 and wait_pos < summarize_pos, (
        "summarize-title 请求必须发生在 commitPromise.then 之后，确保使用真实会话 ID"
    )


def test_send_message_routes_intent_before_rca_workflow():
    """sendMessage 必须先走聊天意图路由，不能无条件触发 RCA 工作流。"""
    js = read_app_js()
    body = _extract_function_body(js, "sendMessage")

    assert body, "必须定义 sendMessage"
    assert "routeChatMessage" in body or "callChatExecuteAPI" in body, (
        "sendMessage 必须先调用聊天意图路由，而不是直接进入 RCA"
    )
    assert "runAnalysis(type, text, session, commitPromise);" not in body, (
        "sendMessage 不得无条件调用 runAnalysis 触发 8 步 RCA 工作流"
    )
    assert "'/execute'" in js or '"/execute"' in js, (
        "前端必须调用 /api/v1/chat/execute 做意图识别"
    )


# ═══════════════════════════════════════════════════════════════
# Task 6: 前端 progress timeline 状态与静态测试骨架
# ═══════════════════════════════════════════════════════════════

# 8 个 RCA 工作流节点键（必须严格匹配，与后端节点名一致）
RCA_PROGRESS_STEP_KEYS = [
    "analyze_symptom",
    "generate_hypotheses",
    "select_tool",
    "execute_tool",
    "observe_evidence",
    "draft_rca",
    "reflect",
    "generate_report",
]


def _has_chinese_char(text: str) -> bool:
    """判断字符串是否至少包含一个中文字符。"""
    if not text:
        return False
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _extract_function_body(js: str, name: str) -> str:
    """通过 brace 计数提取 function name(...) { ... } 的函数体字符串。

    正确处理嵌套大括号，比 `.*?` 非贪婪 regex 更稳健。
    返回函数体（不含首尾的 `{` / `}`），若未找到则返回空字符串。
    """
    import re as _re

    pattern = _re.compile(
        r"function\s+" + _re.escape(name) + r"\s*\([^)]*\)\s*\{"
    )
    m = pattern.search(js)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    n = len(js)
    in_str = None  # None | "'" | '"' | '`'
    while i < n and depth > 0:
        ch = js[i]
        # 跳过字符串字面量，避免对引号/花括号计数
        if in_str is not None:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "/":
            # 行注释，跳到行尾
            nl = js.find("\n", i)
            i = nl + 1 if nl >= 0 else n
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "*":
            end = js.find("*/", i + 2)
            i = end + 2 if end >= 0 else n
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js[start:i]
        i += 1
    return ""


def test_progress_timeline_frontend_scaffold_exists():
    """静态前端必须存在进度时间线脚手架：
    1) `RCA_PROGRESS_STEPS` 常量定义 8 个工作流节点 -> 中文标题映射；
    2) `state.progress` 形状中包含 `lastSeq` 字段；
    3) `renderProgressHtml(progress)` 函数存在；
    4) 同一消息追加报告的占位/函数名（用于 Task 8）已声明；
    5) 不引入真实 SSE/EventSource 集成；
    6) 不破坏现有 `renderLoadingHtml` / `renderReportHtml`。
    """
    js = read_app_js()

    # 1) RCA_PROGRESS_STEPS 存在
    assert "RCA_PROGRESS_STEPS" in js, (
        "必须声明 RCA_PROGRESS_STEPS 常量以承载 8 节点中文标题"
    )
    # 取出 RCA_PROGRESS_STEPS 对象字面量区域（从声明到下一个独立分号或大括号对齐结束）
    start = js.index("RCA_PROGRESS_STEPS")
    region = js[start:start + 4000]  # 8 节点不可能超过这个长度

    # 8 个键必须全部出现
    for key in RCA_PROGRESS_STEP_KEYS:
        assert key in region, f"RCA_PROGRESS_STEPS 缺少节点键: {key}"

    # 中文标题（值必须为非空字符串且至少含一个汉字）
    # 用引号包住的字符串值做最小验证：值里至少有 \u4e00-\u9fff 字符
    import re

    # 抓取所有形如 key: '...' 或 key: "..." 的值
    kv_pattern = re.compile(
        r"(?P<key>" + "|".join(re.escape(k) for k in RCA_PROGRESS_STEP_KEYS) + r")\s*:\s*['\"](?P<val>[^'\"]+)['\"]"
    )
    matches = {m.group("key"): m.group("val") for m in kv_pattern.finditer(region)}
    assert len(matches) == 8, (
        f"RCA_PROGRESS_STEPS 应有 8 个键值对，实际解析出 {len(matches)} 个: {sorted(matches.keys())}"
    )
    for key, val in matches.items():
        assert _has_chinese_char(val), (
            f"RCA_PROGRESS_STEPS['{key}'] 必须是中文标题，实际为: {val!r}"
        )

    # 2) state.progress 必须存在并包含 lastSeq 字段
    # 允许 'progress: {' 或嵌套写法 'progress: {\n ... lastSeq: 0' 之类
    state_match = re.search(
        r"var\s+state\s*=\s*\{(?P<body>.*?)\n\s*\};",
        js,
        flags=re.DOTALL,
    )
    assert state_match, "未找到 var state = { ... } 定义"
    state_body = state_match.group("body")
    progress_match = re.search(
        r"progress\s*:\s*\{(?P<progress_body>.*?)\n\s*\}",
        state_body,
        flags=re.DOTALL,
    )
    assert progress_match, (
        "state.progress 必须作为对象存在，形状至少包含 lastSeq"
    )
    progress_body = progress_match.group("progress_body")
    assert re.search(r"lastSeq\s*:\s*0", progress_body), (
        f"state.progress 必须声明 lastSeq: 0 初始值，实际: {progress_body!r}"
    )

    # 3) renderProgressHtml 函数存在
    assert re.search(
        r"function\s+renderProgressHtml\s*\(\s*progress\s*\)",
        js,
    ), "必须定义 function renderProgressHtml(progress)"

    # 4) 同一消息追加报告的占位/函数名必须存在（供 Task 8 实现）
    #    接受以下任一命名：appendReportToProgressMessage / appendReportToSameMessage / mergeReportIntoProgress
    same_message_markers = [
        "appendReportToProgressMessage",
        "appendReportToSameMessage",
        "mergeReportIntoProgress",
    ]
    assert any(marker in js for marker in same_message_markers), (
        "必须声明同一消息追加报告的占位函数（Task 8 实现用）"
    )

    # 5) EventSource 仅允许出现在 openProgressStream 中（Task 8 接入点）
    #    渲染层（renderProgressHtml 等）仍不应包含 EventSource
    render_body = _extract_function_body(js, "renderProgressHtml")
    assert render_body and "new EventSource" not in render_body, (
        "renderProgressHtml 不应包含 EventSource 实例化（应仅在 openProgressStream 中）"
    )
    format_body = _extract_function_body(js, "formatProgressStepDetail")
    if format_body:
        assert "new EventSource" not in format_body, (
            "formatProgressStepDetail 不应包含 EventSource 实例化"
        )

    # 6) 现有 loading / report / messages 渲染行为必须保留
    assert "function renderLoadingHtml" in js, "必须保留 renderLoadingHtml"
    assert "function renderReportHtml" in js, "必须保留 renderReportHtml"
    assert "function renderMessages" in js, "必须保留 renderMessages"
    assert "preserveScroll" in js, "必须保留 preserveScroll 滚动保留行为"


def test_rca_progress_steps_keys_are_distinct():
    """RCA_PROGRESS_STEPS 的 8 个键必须唯一，且不能出现重复或额外键。"""
    js = read_app_js()
    import re

    assert "RCA_PROGRESS_STEPS" in js, "必须存在 RCA_PROGRESS_STEPS"
    start = js.index("RCA_PROGRESS_STEPS")
    region = js[start:start + 4000]

    kv_pattern = re.compile(
        r"(?P<key>" + "|".join(re.escape(k) for k in RCA_PROGRESS_STEP_KEYS) + r")\s*:"
    )
    keys = [m.group("key") for m in kv_pattern.finditer(region)]
    assert sorted(keys) == sorted(RCA_PROGRESS_STEP_KEYS), (
        f"RCA_PROGRESS_STEPS 节点键集合不匹配，期望 {RCA_PROGRESS_STEP_KEYS}，实际 {sorted(set(keys))}"
    )
    assert len(keys) == len(set(keys)), "RCA_PROGRESS_STEPS 节点键必须唯一"


def test_progress_state_initializes_lastSeq_zero():
    """state.progress.lastSeq 必须初始化为 0，避免首事件被 lastSeq 误过滤。"""
    import re

    js = read_app_js()

    # 找到包含 lastSeq 的对象字面量
    assert re.search(
        r"progress\s*:\s*\{[^{}]*lastSeq\s*:\s*0",
        js,
        flags=re.DOTALL,
    ), "state.progress.lastSeq 必须初始化为 0"


def test_render_progress_html_signature_present():
    """renderProgressHtml 函数签名必须明确接收 progress 参数。"""
    import re

    js = read_app_js()
    assert re.search(
        r"function\s+renderProgressHtml\s*\(\s*progress\s*\)",
        js,
    ), "renderProgressHtml 必须声明形参 progress"


def test_same_message_append_marker_declared_as_function():
    """同消息追加报告的占位必须以函数形式声明，便于 Task 8 替换实现。"""
    import re

    js = read_app_js()
    same_message_markers = [
        "appendReportToProgressMessage",
        "appendReportToSameMessage",
        "mergeReportIntoProgress",
    ]
    found = None
    for marker in same_message_markers:
        if marker in js:
            found = marker
            break
    assert found is not None, (
        "必须声明同一消息追加报告的占位函数（Task 8 实现用）"
    )
    # 必须以 function 形式声明，避免仅作为字符串
    assert re.search(
        r"function\s+" + re.escape(found) + r"\s*\(",
        js,
    ), f"{found} 必须以 function 形式声明"


# ═══════════════════════════════════════════════════════════════
# Task 7: 折叠式进度卡片 UI 与样式
# ═══════════════════════════════════════════════════════════════

def test_progress_card_renders_8_step_overview_by_default():
    """renderProgressHtml 默认应渲染 8 步概览（每节点一行）。"""
    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 function renderProgressHtml(progress)"

    # 必须遍历 RCA_PROGRESS_STEP_ORDER（默认 8 步）
    assert "RCA_PROGRESS_STEP_ORDER" in body, (
        "renderProgressHtml 必须遍历 RCA_PROGRESS_STEP_ORDER（8 步顺序）"
    )
    # 必须输出外层容器与 step 列表
    assert "rca-progress" in body, "必须输出 .rca-progress 容器"
    assert "rca-progress-list" in body, "必须输出 .rca-progress-list"


def test_progress_step_status_classes_are_distinct():
    """5 种状态（pending/running/success/failed/cancelled）必须有 distinct CSS 类。"""
    css = read_styles_css()

    # 状态类必须各自定义（与现有 .report-status 风格保持一致）
    for status in ("pending", "running", "success", "failed", "cancelled"):
        assert f".rca-progress-step--{status}" in css, (
            f"CSS 必须定义 .rca-progress-step--{status} 状态类"
        )


def test_progress_step_uses_accessible_toggle_with_aria_expanded():
    """每个 step 必须使用带 aria-expanded 的可访问按钮，键盘可操作。"""
    js = read_app_js()
    import re

    # 必须有 data-progress-step-toggle 稳定属性
    assert "data-progress-step-toggle" in js, (
        "必须使用 data-progress-step-toggle 作为稳定 toggle 属性"
    )
    # 必须配合 aria-expanded 提供无障碍支持
    assert re.search(
        r"aria-expanded\s*=\s*['\"]?(?:false|true|'false'|'true'|\")",
        js,
    ), "必须输出 aria-expanded 属性以提供可访问性"
    # 必须用 <button> 元素承载 toggle（保证键盘焦点与回车键）
    assert re.search(
        r"<button[^>]*data-progress-step-toggle",
        js,
    ), "折叠切换必须用 <button> 元素以支持键盘操作"


def test_progress_step_uses_status_modifier_class():
    """每个 step 必须有 rca-progress-step--{status} 修饰类，便于状态视觉。"""
    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 renderProgressHtml"

    # 必须拼接 rca-progress-step-- + status 修饰类
    import re as _re
    assert _re.search(
        r"rca-progress-step\s+rca-progress-step--\s*\+\s*|"
        r"rca-progress-step--\s*\+|"
        r"['\"]rca-progress-step--['\"]\s*\+",
        body,
    ), "renderProgressHtml 必须拼接 rca-progress-step--{status} 修饰类"


def test_progress_step_detail_section_renders_when_present():
    """当 step 提供 detail/log/tool 时，必须渲染 detail 区块。"""
    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 renderProgressHtml"

    # 必须存在 detail 容器类
    assert "rca-progress-step-detail" in body, (
        "renderProgressHtml 必须输出 rca-progress-step-detail 详情容器"
    )
    # 必须读取 step.detail / step.log / step.tool 至少一项；
    # QA 修复后该读取下沉到 formatProgressStepDetail helper，body 出现 helper 调用亦视为合规。
    detail_signals = [
        "step.detail",
        "step.log",
        "step.tool",
        ".detail",
        ".log",
        ".tool",
        "formatProgressStepDetail",
    ]
    assert any(signal in body for signal in detail_signals), (
        "renderProgressHtml 必须读取 step 的 detail/log/tool 至少一项"
        "（或通过 formatProgressStepDetail helper 消费）"
    )


def test_progress_step_toggle_handler_attached_via_existing_pattern():
    """折叠切换必须通过 attachMessageHandlers 中的现有事件委托模式绑定。"""
    import re as _re

    body = _extract_function_body(read_app_js(), "attachMessageHandlers")
    assert body, "必须保留 attachMessageHandlers 函数"

    # 必须有 querySelectorAll 找到 progress toggle 元素
    assert _re.search(
        r"querySelectorAll\(\s*['\"]\[data-progress-step-toggle\]['\"]\s*\)",
        body,
    ), "attachMessageHandlers 必须 querySelectorAll('[data-progress-step-toggle]')"
    # 必须对每个 toggle 元素 addEventListener('click', ...)
    assert "addEventListener" in body, "必须保留事件绑定"


def test_progress_step_default_state_is_collapsed():
    """默认渲染时 step 应为折叠状态（aria-expanded='false'）。"""
    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 renderProgressHtml"

    # 模板中 aria-expanded 静态值应使用 'false' 作为默认
    # 接受 'false' 或 escaped 形式
    import re as _re
    assert _re.search(
        r"aria-expanded=['\"]false['\"]",
        body,
    ), "默认 step 必须折叠（aria-expanded='false'）"


def test_progress_step_failed_state_has_distinct_visual_classes():
    """failed 状态必须有可区分的视觉类，不与 cancelled 混用。"""
    css = read_styles_css()

    failed_block = css.split(".rca-progress-step--failed {")[1].split("}")[0]
    cancelled_block = css.split(".rca-progress-step--cancelled {")[1].split("}")[0]

    # 至少有一处颜色/边框/背景定义（不能空块）
    assert failed_block.strip(), "failed 状态样式不能为空"
    assert cancelled_block.strip(), "cancelled 状态样式不能为空"
    # failed 与 cancelled 的视觉块必须不同（粗略：不同颜色变量或值）
    assert failed_block != cancelled_block, (
        "failed 与 cancelled 状态的视觉定义必须不同"
    )


def test_progress_root_classes_defined_in_css():
    """styles.css 必须定义 .rca-progress 容器及其头部、列表、step 样式。"""
    css = read_styles_css()

    for selector in [
        ".rca-progress",
        ".rca-progress-header",
        ".rca-progress-list",
        ".rca-progress-step",
        ".rca-progress-step-toggle",
        ".rca-progress-step-detail",
    ]:
        assert selector in css, f"CSS 必须定义 {selector}"


def test_progress_card_uses_design_tokens_not_arbitrary_values():
    """样式必须复用现有 design tokens（颜色/间距），不引入硬编码魔数。"""
    css = read_styles_css()

    # 抽取 .rca-progress-step--{status} 样式块，确认使用 token
    for status in ("pending", "running", "success", "failed", "cancelled"):
        block = css.split(f".rca-progress-step--{status} {{")[1].split("}")[0]
        # 至少有一个 token 引用：颜色/边框/背景/间距
        token_hits = [
            "var(--accent" in block,
            "var(--color-" in block,
            "var(--space-" in block,
            "var(--radius-" in block,
            "var(--color-text" in block,
            "var(--color-success" in block,
            "var(--color-error" in block,
            "var(--color-border" in block,
        ]
        assert any(token_hits), (
            f".rca-progress-step--{status} 至少应使用一个 design token"
        )


# ============ Task 7 QA follow-up: detail_json 渲染 ============


def test_format_progress_step_detail_helper_exists():
    """必须新增 helper `formatProgressStepDetail(stepState)` 用于集中解析 detail 文本。

    后端事件流携带 `detail_json` 字段（结构化对象/列表），
    渲染层需要一个独立的 helper 把它格式化为可读字符串，
    同时保留对旧字段（detail / log / tool）的兼容。
    """
    js = read_app_js()
    body = _extract_function_body(js, "formatProgressStepDetail")
    assert body, "必须定义 function formatProgressStepDetail(stepState)"

    # 优先读取 detail_json 字段
    assert "detail_json" in body, (
        "formatProgressStepDetail 必须读取 stepState.detail_json"
    )
    # 兼容旧字段 detail / log / tool
    for field in ("detail", "log", "tool"):
        assert field in body, (
            f"formatProgressStepDetail 必须保留对 stepState.{field} 的回退支持"
        )
    # 对象/列表用 JSON.stringify(.., null, 2) 可读格式化
    assert "JSON.stringify" in body, (
        "formatProgressStepDetail 必须用 JSON.stringify 格式化对象/列表"
    )


def test_render_progress_html_uses_format_progress_step_detail_helper():
    """renderProgressHtml 必须通过 helper 读取 detail（间接支持 detail_json）。"""
    import re as _re

    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 renderProgressHtml"

    # helper 调用必须存在
    assert _re.search(
        r"formatProgressStepDetail\s*\(",
        body,
    ), "renderProgressHtml 必须调用 formatProgressStepDetail()"
    # detail_json 解析下沉到 helper；helper 自身的 detail_json 覆盖由
    # test_format_progress_step_detail_helper_exists 单独断言。


def test_render_progress_html_formats_detail_json_via_json_stringify():
    """renderProgressHtml 链路必须用 JSON.stringify(..., null, 2) 格式化 detail_json。

    用 2 空格缩进保证多行可读；测试同时防止后续误改成单行（无 null,2）。
    """
    import re as _re

    body = _extract_function_body(read_app_js(), "formatProgressStepDetail")
    assert body, "必须定义 formatProgressStepDetail"

    # 必须出现 JSON.stringify(..., null, 2) 三参数调用
    assert _re.search(
        r"JSON\.stringify\s*\(\s*[^,]+,\s*null\s*,\s*2\s*\)",
        body,
    ), "formatProgressStepDetail 必须用 JSON.stringify(detail_json, null, 2)"


def test_render_progress_html_still_escapes_detail_into_html():
    """detail 文本插入 HTML 前必须经过 escapeHtml，防止 XSS。"""
    import re as _re

    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 renderProgressHtml"

    # 在输出 .rca-progress-step-detail 容器时仍走 escapeHtml(...)
    assert _re.search(
        r"rca-progress-step-detail[^<]*<",
        body,
    ), "renderProgressHtml 必须保留 rca-progress-step-detail 容器"
    # 至少一处 escapeHtml( 用于把文本插入 HTML
    assert "escapeHtml(" in body, (
        "renderProgressHtml 仍必须用 escapeHtml 转义用户内容"
    )


def test_render_progress_html_does_not_introduce_sse_or_eventsource():
    """renderProgressHtml 内严禁引入 EventSource / SSE 订阅。

    Task 7 既有契约：渲染层只做纯字符串拼接，不应创建 EventSource。
    Task 8 允许在 openProgressStream 中接入 EventSource，但必须在 openProgressStream 之外保持隔离。
    """
    body = _extract_function_body(read_app_js(), "renderProgressHtml")
    assert body, "必须定义 renderProgressHtml"
    assert "new EventSource" not in body, "renderProgressHtml 内禁止引入 EventSource"
    assert "EventSource(" not in body, "renderProgressHtml 内禁止调用 EventSource 构造函数"


# ═══════════════════════════════════════════════════════════════
# Task 5: 前端 task_id 识别与进度恢复标记
# ═══════════════════════════════════════════════════════════════

def test_switch_session_maps_task_id_from_backend():
    """switchSession 加载消息时必须将后端 task_id 映射到前端 taskId 字段。

    后端 chat_messages.task_id 通过 API 返回后，前端消息对象必须携带
    taskId 属性，供后续 progress 恢复逻辑识别哪些 assistant 消息
    有对应的 RCA 任务。
    """
    js = read_app_js()
    import re as _re

    # 共享消息加载 helper 必须包含消息映射逻辑
    body = _extract_function_body(js, "loadMessagesForSession")
    assert body, "必须定义 function loadMessagesForSession(id)"

    # 映射中必须包含 task_id → taskId 的转换
    assert _re.search(
        r"taskId\s*:\s*m\.task_id",
        body,
    ), "switchSession 消息映射必须包含 taskId: m.task_id"
    # 必须保留现有 report 映射（不破坏 report_snapshot 行为）
    assert _re.search(
        r"report\s*:\s*m\.report_snapshot",
        body,
    ), "switchSession 必须保留 report: m.report_snapshot 映射"


def test_progress_message_can_restore_by_task_id():
    """前端必须提供 restoreProgressForTaskMessage 或等效 helper，
    用于识别历史 assistant 消息中的 task_id 并准备进度恢复状态。

    此 helper 是 Task 8 SSE 重放的前置依赖：历史消息加载后，
    通过 task_id 标记哪些消息可恢复进度时间线。
    """
    js = read_app_js()
    import re as _re

    # 至少存在以下命名之一
    restore_markers = [
        "restoreProgressForTaskMessage",
        "hydrateProgressMessageFromTaskId",
        "prepareProgressRestore",
        "markProgressMessageByTaskId",
    ]
    found = None
    for marker in restore_markers:
        if marker in js:
            found = marker
            break
    assert found is not None, (
        "必须声明进度恢复标记函数（restoreProgressForTaskMessage / "
        "hydrateProgressMessageFromTaskId / prepareProgressRestore / "
        "markProgressMessageByTaskId 之一）"
    )
    # 必须以 function 形式声明
    assert _re.search(
        r"function\s+" + _re.escape(found) + r"\s*\(",
        js,
    ), f"{found} 必须以 function 形式声明"

    # helper 函数体必须读取消息的 taskId 属性
    body = _extract_function_body(js, found)
    assert body, f"必须定义 function {found}(...) 的函数体"
    assert "taskId" in body, (
        f"{found} 必须读取消息的 taskId 属性以识别可恢复的进度消息"
    )


def test_render_message_html_preserves_report_snapshot_behavior():
    """renderMessageHtml 不得移除现有 report_snapshot / report 渲染行为。

    assistant 消息渲染时，report_snapshot 仍通过 renderReportHtml 展示，
    task_id 的引入不应破坏此链路。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "renderMessageHtml")
    assert body, "必须定义 renderMessageHtml"

    # 保留 report_snapshot 判断逻辑
    assert _re.search(
        r"m\.report_snapshot\s*\|\|\s*m\.report",
        body,
    ), "renderMessageHtml 必须保留 m.report_snapshot || m.report 判断"
    # 保留 renderReportHtml 调用
    assert "renderReportHtml" in body, (
        "renderMessageHtml 必须保留 renderReportHtml 调用"
    )


def test_no_sse_or_eventsource_in_render_layer():
    """渲染层（renderMessageHtml/renderReportHtml/renderLoadingHtml/renderProgressHtml）
    严禁引入 EventSource / SSE 订阅。Task 5 既有约束的演进版。

    Task 8 允许在 openProgressStream 中接入 EventSource，但渲染函数必须保持纯字符串拼接，
    不能混入网络资源管理。
    """
    js = read_app_js()
    for fname in ("renderMessageHtml", "renderReportHtml", "renderLoadingHtml", "renderProgressHtml", "renderErrorContentHtml"):
        body = _extract_function_body(js, fname)
        if not body:
            continue
        assert "new EventSource" not in body, (
            f"渲染层 {fname} 禁止创建 EventSource 实例；"
            "SSE 管理应集中在 openProgressStream / closeProgressStream"
        )
        assert "EventSource(" not in body, (
            f"渲染层 {fname} 禁止调用 EventSource 构造函数"
        )


# ═══════════════════════════════════════════════════════════════
# Task 5 QA: switchSession 必须调用 restoreProgressForTaskMessage
# ═══════════════════════════════════════════════════════════════

def test_switch_session_calls_restore_progress_for_task_message():
    """switchSession 加载历史消息后必须调用 restoreProgressForTaskMessage，
    为有 taskId 的 assistant 消息附加 progressRestore 标记。

    当前实现仅映射了 taskId 字段，但未实际调用 helper。
    此测试验证 switchSession 函数体内存在对 helper 的调用。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "loadMessagesForSession")
    assert body, "必须定义 function loadMessagesForSession(id)"

    # 必须调用 restoreProgressForTaskMessage（或等效命名）
    restore_markers = [
        "restoreProgressForTaskMessage",
        "hydrateProgressMessageFromTaskId",
        "prepareProgressRestore",
        "markProgressMessageByTaskId",
    ]
    found = None
    for marker in restore_markers:
        if marker in body:
            found = marker
            break
    assert found is not None, (
        "loadMessagesForSession 必须调用 restoreProgressForTaskMessage "
        "（或等效命名）以附加进度恢复标记"
    )
    # 调用必须出现在 .map() 之后（即消息映射完成后才标记）
    map_pos = body.find(".map(function")
    call_pos = body.find(found)
    assert map_pos >= 0, "loadMessagesForSession 必须包含 .map() 消息映射"
    assert call_pos > map_pos, (
        f"loadMessagesForSession 必须在 .map() 之后调用 {found}，"
        f"实际 .map() 位置 {map_pos}，{found} 位置 {call_pos}"
    )


def test_switch_session_attaches_progress_restore_marker():
    """switchSession 加载消息后必须为有 taskId 的 assistant 消息
    附加 progressRestore 标记（对象或数组），供 Task 8 使用。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "loadMessagesForSession")
    assert body, "必须定义 function loadMessagesForSession(id)"

    # 必须出现 progressRestore 标记（消息对象属性或数组）
    assert _re.search(
        r"progressRestore",
        body,
    ), "switchSession 必须附加 progressRestore 标记到消息或会话"


def test_switch_session_preserves_task_id_mapping():
    """switchSession 消息映射必须保留 taskId: m.task_id 转换。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "loadMessagesForSession")
    assert body, "必须定义 function loadMessagesForSession(id)"

    assert _re.search(
        r"taskId\s*:\s*m\.task_id",
        body,
    ), "switchSession 消息映射必须保留 taskId: m.task_id"


def test_switch_session_preserves_report_snapshot_mapping():
    """switchSession 消息映射必须保留 report: m.report_snapshot 转换。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "loadMessagesForSession")
    assert body, "必须定义 function loadMessagesForSession(id)"

    assert _re.search(
        r"report\s*:\s*m\.report_snapshot",
        body,
    ), "switchSession 必须保留 report: m.report_snapshot 映射"


# ═══════════════════════════════════════════════════════════════
# Task 8: 前端接入异步 analyze + EventSource
# ═══════════════════════════════════════════════════════════════


def test_task8_run_analysis_creates_progress_message_before_analyze():
    """runAnalysis 必须在调用 callAnalyzeAPI 之前/同时创建一条带 progress 的 assistant 消息。

    旧实现：callAnalyzeAPI → callReportAPI → 推送最终 assistant 消息。
    新实现：先 push 一条带 progress 字段的 assistant 消息，再调 callAnalyzeAPI，
    避免用户在等待分析时空白。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "runAnalysis")
    assert body, "必须定义 function runAnalysis(type, description, session)"

    # 找到 callAnalyzeAPI 调用位置
    analyze_pos = body.find("callAnalyzeAPI(")
    assert analyze_pos > 0, "runAnalysis 必须调用 callAnalyzeAPI"

    # callAnalyzeAPI 之前必须存在创建 assistant 消息的痕迹：
    # 1) session.messages.push(aiMsg) 出现
    # 2) aiMsg 对象包含 progress 字段
    push_pos = body.find("session.messages.push(")
    assert push_pos > 0, "runAnalysis 必须在 callAnalyzeAPI 之前 push assistant 消息"

    # push 必须在 callAnalyzeAPI 之前（或同步串行时紧邻）
    assert push_pos < analyze_pos, (
        "runAnalysis 必须在 callAnalyzeAPI 之前先 push assistant 消息，"
        f"实际 push 位置 {push_pos}，callAnalyzeAPI 位置 {analyze_pos}"
    )

    # 必须出现 progress 字段（消息对象中含 progress）
    assert _re.search(
        r"progress\s*:\s*",
        body,
    ), "runAnalysis 创建的 assistant 消息必须包含 progress 字段"

    # 必须保留 taskId 字段以供 EventSource 关联
    assert _re.search(
        r"taskId\s*:\s*",
        body,
    ), "runAnalysis 创建的 assistant 消息必须包含 taskId 字段"


def test_task8_run_analysis_no_longer_chains_call_report_api_after_analyze():
    """runAnalysis 不再走 callAnalyzeAPI().then(callReportAPI()) 串行链。

    旧实现：callAnalyzeAPI(...).then(function(...) { return callReportAPI(...) })
    新实现：报告拉取改在 SSE done 事件中触发，不在 analyze 响应后立刻串行。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "runAnalysis")
    assert body, "必须定义 function runAnalysis"

    # 在 callAnalyzeAPI 之后的 800 字符窗口内不应出现 callReportAPI(
    # （callReportAPI 应在 done 事件触发，与 callAnalyzeAPI 解耦）
    analyze_pos = body.find("callAnalyzeAPI(")
    assert analyze_pos > 0, "runAnalysis 必须调用 callAnalyzeAPI"
    window = body[analyze_pos:analyze_pos + 800]
    assert "callReportAPI(" not in window, (
        "callReportAPI 不应在 runAnalysis 中紧跟 callAnalyzeAPI 同步调用，"
        "必须通过 SSE done 事件异步触发"
    )


def test_task8_open_progress_stream_function_exists_and_uses_event_source():
    """前端必须声明 EventSource 打开/订阅函数，且函数体使用 new EventSource(...)。"""
    js = read_app_js()
    import re as _re

    # 必须存在以 function 形式声明的打开函数
    stream_markers = [
        "openProgressStream",
        "subscribeProgressStream",
        "connectProgressStream",
        "openEventStream",
    ]
    found = None
    for marker in stream_markers:
        if _re.search(r"function\s+" + marker + r"\s*\(", js):
            found = marker
            break
    assert found is not None, (
        "必须以 function 形式声明 EventSource 打开/订阅函数（"
        + "/".join(stream_markers) + " 之一）"
    )

    body = _extract_function_body(js, found)
    assert body, f"必须定义 {found} 函数体"
    assert _re.search(
        r"new\s+EventSource\s*\(",
        body,
    ), f"{found} 函数体必须使用 `new EventSource(` 创建连接"


def test_task8_event_source_uses_events_url_field():
    """EventSource 必须接收 events_url 字段而非自拼 URL。"""
    js = read_app_js()
    import re as _re

    # 必须出现 events_url 字段的引用
    assert "events_url" in js, (
        "前端必须消费 callAnalyzeAPI 响应中的 events_url 字段"
    )

    # 必须出现 new EventSource(<包含 events_url 标识符> 形式
    # 接受 messages.task_id 引用 events_url 或 options.events_url
    assert _re.search(
        r"new\s+EventSource\s*\(\s*[^)]*events_url[^)]*\)",
        js,
    ), "EventSource 必须接收 events_url 作为入参"


def test_task8_progress_event_status_mapping_function():
    """后端事件类型必须映射到前端 5 种 status（pending/running/success/failed/cancelled）。

    映射规则：
    - task_started / node_started → running
    - task_done / node_completed → success
    - task_error / node_error → failed
    - heartbeat → 不改变状态
    """
    js = read_app_js()
    import re as _re

    # 必须存在事件类型到 status 的映射函数
    map_markers = [
        "mapEventToStatus",
        "mapProgressEventType",
        "mapStepEventToStatus",
        "mapEventTypeToStatus",
    ]
    found = None
    for marker in map_markers:
        if _re.search(r"function\s+" + marker + r"\s*\(", js):
            found = marker
            break
    assert found is not None, (
        "必须声明事件类型到 status 的映射函数（"
        + "/".join(map_markers) + " 之一）"
    )

    body = _extract_function_body(js, found)
    assert body, f"必须定义 {found} 函数体"

    # 6 个事件类型常量必须出现在映射函数体内
    for event_type in (
        "task_started",
        "node_started",
        "node_completed",
        "task_done",
        "node_error",
        "task_error",
    ):
        assert event_type in body, (
            f"{found} 必须处理 {event_type} 事件类型"
        )

    # 关键 status 必须出现
    for status in ("running", "success", "failed"):
        assert status in body, (
            f"{found} 必须输出 {status} 状态"
        )


def test_task8_last_seq_dedup_in_progress_consumer():
    """事件消费时必须按 event.seq > lastSeq 过滤，避免重复渲染。"""
    js = read_app_js()
    import re as _re

    # 在打开/订阅/事件处理函数中必须出现 lastSeq 引用 + seq 比较
    # 优先匹配 handleProgressEvent（lastSeq 实际消费点），其次其他命名空间
    consumer_markers = [
        "handleProgressEvent",
        "openProgressStream",
        "subscribeProgressStream",
        "connectProgressStream",
        "openEventStream",
        "consumeProgressEvent",
    ]
    found = None
    for marker in consumer_markers:
        if _re.search(r"function\s+" + marker + r"\s*\(", js):
            body = _extract_function_body(js, marker)
            if body and "lastSeq" in body and "seq" in body:
                found = marker
                break
    assert found is not None, (
        "事件消费函数中必须引用 lastSeq 进行去重（"
        + "/".join(consumer_markers) + " 之一）"
    )

    body = _extract_function_body(js, found)
    # 必须出现 seq 与 lastSeq 的比较
    assert _re.search(
        r"\.seq\s*[<>=!]+\s*lastSeq|lastSeq\s*[<>=!]+\s*[^,;\)]*\.seq",
        body,
    ), f"{found} 函数体必须出现 seq 与 lastSeq 的比较以去重"


def test_task8_close_progress_stream_closes_event_source():
    """closeProgressStream 必须关闭 EventSource 调用 .close()。"""
    js = read_app_js()
    import re as _re

    # 必须存在关闭函数
    close_markers = [
        "closeProgressStream",
        "closeEventStream",
        "stopProgressStream",
        "tearDownProgressStream",
    ]
    found = None
    for marker in close_markers:
        if _re.search(r"function\s+" + marker + r"\s*\(", js):
            found = marker
            break
    assert found is not None, (
        "必须声明关闭 EventSource 的函数（"
        + "/".join(close_markers) + " 之一）"
    )

    body = _extract_function_body(js, found)
    assert body, f"必须定义 {found} 函数体"

    # 关闭函数必须包含 .close() 调用（EventSource.close）
    assert _re.search(
        r"\.close\s*\(\s*\)",
        body,
    ), f"{found} 必须调用 .close() 关闭 EventSource"


def test_task8_stop_button_calls_close_progress_stream():
    """handleSendClick 在 loading 状态下应调 closeProgressStream 关闭 SSE。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "handleSendClick")
    assert body, "必须定义 function handleSendClick"

    # 关闭函数名必须出现在 handleSendClick 函数体内
    close_markers = [
        "closeProgressStream",
        "closeEventStream",
        "stopProgressStream",
        "tearDownProgressStream",
    ]
    found = None
    for marker in close_markers:
        if marker in body:
            found = marker
            break
    assert found is not None, (
        f"handleSendClick 在停止时必须调用关闭 EventSource 的函数（"
        + "/".join(close_markers) + " 之一）"
    )


def test_task8_stop_does_not_claim_backend_cancellation():
    """Stop 按钮严禁调用后端 cancel API；关闭 EventSource 不等于取消后台任务。"""
    js = read_app_js()
    import re as _re

    # 不得出现 cancel API 调用痕迹
    forbidden_patterns = [
        r"abortTask",
        r"cancelTask",
    ]
    for pat in forbidden_patterns:
        assert not _re.search(pat, js), (
            f"前端禁止调用后端 cancel API（命中 {pat}）；"
            "Stop 按钮仅关闭 EventSource"
        )


def test_task8_done_event_triggers_report_fetch():
    """SSE done 事件必须触发 callReportAPI(taskId) 拉取最终报告。"""
    js = read_app_js()
    import re as _re

    # 必须存在 done 事件处理分支
    done_patterns = [
        r"case\s+['\"]done['\"]\s*:",
        r"event\.event\s*===\s*['\"]done['\"]",
        r"event\.type\s*===\s*['\"]done['\"]",
        r"e\.event\s*===\s*['\"]done['\"]",
        r"data\.event\s*===\s*['\"]done['\"]",
    ]
    found_done = any(_re.search(p, js) for p in done_patterns)
    assert found_done, "必须存在对 SSE 'done' 事件类型的处理分支"

    # callReportAPI 必须在某处被调用
    assert "callReportAPI(" in js, "前端必须存在对 callReportAPI 的调用"


def test_task8_append_report_to_progress_message_actually_appends():
    """appendReportToProgressMessage 必须真正把报告写入同一条 assistant 消息。

    当前是 no-op 占位；Task 8 必须实现：将 report 写入 session.messages[i].report，
    并将 report_snapshot 字段也填充，保持历史渲染兼容。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "appendReportToProgressMessage")
    assert body, "必须定义 function appendReportToProgressMessage"

    # 关键：函数体必须实际给消息对象写 report / report_snapshot 字段
    write_patterns = [
        r"\breport\s*=\s*report",
        r"\breport_snapshot\s*=\s*report",
        r"\.report\s*=",
        r"\.report_snapshot\s*=",
    ]
    has_write = any(_re.search(p, body) for p in write_patterns)
    assert has_write, (
        "appendReportToProgressMessage 必须将 report 写入消息对象"
        "（msg.report = / msg.report_snapshot = / session.messages[i].report =）"
    )


def test_task8_render_message_html_supports_progress_field():
    """renderMessageHtml 必须支持消息对象的 progress 字段，渲染 progress timeline。

    新行为：当 assistant 消息含 m.progress 时，渲染 renderProgressHtml(progress)；
    当 m.report 或 m.report_snapshot 存在时，在 progress 下方追加 renderReportHtml。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "renderMessageHtml")
    assert body, "必须定义 renderMessageHtml"

    # 必须存在 progress 字段读取
    assert _re.search(
        r"m\.progress",
        body,
    ), "renderMessageHtml 必须读取 m.progress 字段"

    # 必须存在 renderProgressHtml 调用
    assert _re.search(
        r"renderProgressHtml\s*\(",
        body,
    ), "renderMessageHtml 必须调用 renderProgressHtml 渲染 progress timeline"

    # 保留 report_snapshot 行为
    assert _re.search(
        r"m\.report_snapshot\s*\|\|\s*m\.report",
        body,
    ), "renderMessageHtml 必须保留 m.report_snapshot || m.report 判断"

    # 必须保留 renderReportHtml 调用
    assert "renderReportHtml" in body, (
        "renderMessageHtml 必须保留 renderReportHtml 调用"
    )


def test_task8_render_message_html_renders_progress_and_report_below():
    """renderMessageHtml 中 progress 与 report 必须共存：progress 在上、report 在下。

    通过检查字符串拼接顺序验证：先 renderProgressHtml，后 renderReportHtml。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "renderMessageHtml")
    assert body, "必须定义 renderMessageHtml"

    # 找 renderProgressHtml 与 renderReportHtml 出现位置
    progress_pos = body.find("renderProgressHtml(")
    assert progress_pos > 0, "renderMessageHtml 必须调用 renderProgressHtml"

    report_pos = body.find("renderReportHtml(")
    assert report_pos > 0, "renderMessageHtml 必须调用 renderReportHtml"

    # renderProgressHtml 必须在 renderReportHtml 之前（progress 在上、report 在下）
    assert progress_pos < report_pos, (
        f"renderProgressHtml 应在 renderReportHtml 之前（progress 在上、report 在下），"
        f"实际 progress 位置 {progress_pos}，report 位置 {report_pos}"
    )


def test_task8_state_progress_preserves_expanded_across_updates():
    """更新 state.progress.steps 时不能重置 state.progress.expanded。

    SSE 流式增量更新期间，用户已展开的步骤必须保持展开。
    """
    js = read_app_js()
    import re as _re

    # 事件消费函数中必须保留对 expanded 字段的引用
    consumer_markers = [
        "openProgressStream",
        "subscribeProgressStream",
        "connectProgressStream",
        "openEventStream",
        "handleProgressEvent",
        "consumeProgressEvent",
    ]
    found = None
    for marker in consumer_markers:
        if _re.search(r"function\s+" + marker + r"\s*\(", js):
            body = _extract_function_body(js, marker)
            if body and "expanded" in body:
                found = marker
                break
    assert found is not None, (
        "事件消费函数中必须保留 expanded 引用以保持用户展开状态（"
        + "/".join(consumer_markers) + " 之一）"
    )


def test_task8_heartbeat_event_handled():
    """SSE heartbeat 事件必须有显式处理（不改变 progress 状态，仅记录 seq）。"""
    js = read_app_js()
    import re as _re

    # 必须存在对 heartbeat 事件类型的处理分支
    heartbeat_patterns = [
        r"case\s+['\"]heartbeat['\"]\s*:",
        r"event\.event\s*===\s*['\"]heartbeat['\"]",
        r"event\.type\s*===\s*['\"]heartbeat['\"]",
        r"e\.event\s*===\s*['\"]heartbeat['\"]",
        r"data\.event\s*===\s*['\"]heartbeat['\"]",
    ]
    found_hb = any(_re.search(p, js) for p in heartbeat_patterns)
    assert found_hb, "必须存在对 SSE 'heartbeat' 事件类型的处理分支"


def test_task8_persists_progress_message_with_task_id_and_report_snapshot():
    """runAnalysis 成功路径持久化 assistant 消息时必须携带 task_id 和 report_snapshot。

    持久化通过 POST /messages 携带 role/anomaly_type/task_id/report_snapshot。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "runAnalysis")
    assert body, "必须定义 function runAnalysis"

    # runAnalysis 内部必须至少出现一次 POST /messages 持久化逻辑
    # 静态断言：必须出现 report_snapshot 字面量
    assert "report_snapshot" in body, (
        "runAnalysis 持久化逻辑必须出现 report_snapshot 字段"
    )

    # 必须出现 task_id 字面量
    assert "task_id" in body, (
        "runAnalysis 持久化逻辑必须出现 task_id 字段"
    )


def test_task8_render_message_html_progress_status_marker_exists():
    """renderMessageHtml 在 progress 消息上必须使用 data-progress-message 标记。

    方便 attachMessageHandlers 与 abort 流程识别 progress 消息。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "renderMessageHtml")
    assert body, "必须定义 renderMessageHtml"

    # 必须出现 data-progress-message 属性（在 assistant 消息 div 上）
    assert _re.search(
        r"data-progress-message",
        body,
    ), "renderMessageHtml 在 progress 消息 div 上必须含 data-progress-message 属性"


# ═══════════════════════════════════════════════════════════════
# Task 8 QA 修复: EventSource 命名事件分发
# ═══════════════════════════════════════════════════════════════

# 后端 SSE 实际发出 4 种命名事件
SSE_NAMED_EVENTS = ["step", "done", "error", "heartbeat"]


def test_task8_qa_open_progress_stream_uses_add_event_listener_for_named_events():
    """openProgressStream 必须为后端 4 种命名事件分别注册监听器。

    后端通过 `_format_sse(event_type, ...)` 写入 `event: step` / `event: done` /
    `event: error` / `event: heartbeat` 命名事件；浏览器 EventSource.onmessage
    只处理无 `event:` 行的默认 `message` 事件。Task 8 旧实现仅用 onmessage，
    会导致 step/done/error/heartbeat 全部丢失。必须改用 addEventListener。
    """
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    for evt_name in SSE_NAMED_EVENTS:
        # 必须出现 addEventListener('evt_name', ...) 形式
        pattern = r"addEventListener\s*\(\s*['\"]" + evt_name + r"['\"]\s*,"
        assert _re.search(pattern, body), (
            f"openProgressStream 必须使用 addEventListener('{evt_name}', ...) "
            "订阅后端命名 SSE 事件"
        )


def test_task8_qa_open_progress_stream_parses_event_data_in_listeners():
    """每个 addEventListener 处理器内部必须解析 e.data 并调用 handleProgressEvent。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    # 至少出现 1 次 JSON.parse(e.data) 形式
    assert _re.search(
        r"JSON\.parse\s*\(\s*\w+\.data\s*\)",
        body,
    ), "openProgressStream 命名事件处理器必须用 JSON.parse(e.data) 解析 SSE data 行"

    # 必须出现 handleProgressEvent 调用
    assert "handleProgressEvent(" in body, (
        "openProgressStream 命名事件处理器必须调用 handleProgressEvent"
    )


def test_task8_qa_done_listener_passes_event_type_to_handler():
    """done 事件监听器必须将 event_type 字段规范化为 'done' 传入 handleProgressEvent。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    # 找到 addEventListener('done', 的位置
    idx = body.find("addEventListener('done'")
    if idx < 0:
        idx = body.find('addEventListener("done"')
    assert idx >= 0, "openProgressStream 必须注册 addEventListener('done', ...)"

    # 在 addEventListener('done', 之后 1000 字符内必须含 event_type = 'done'
    window = body[idx:idx + 1000]
    assert "event_type" in window and "'done'" in window, (
        "done 监听器内必须规范化 event_type='done'（含嵌套 try/catch 时也必须存在）"
    )


def test_task8_qa_error_listener_passes_event_type_to_handler():
    """error 事件监听器必须将 event_type 字段规范化为 'error' 传入 handleProgressEvent。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    # addEventListener('error', ...) 必须存在（与连接级 es.onerror 区分）
    add_err_pat = r"addEventListener\s*\(\s*['\"]error['\"]\s*,"
    assert _re.search(add_err_pat, body), (
        "openProgressStream 必须注册 addEventListener('error', ...) 监听器"
    )

    idx = body.find("addEventListener('error'")
    if idx < 0:
        idx = body.find('addEventListener("error"')
    assert idx >= 0
    # 在 addEventListener('error', 之后 1000 字符内必须含 event_type = 'error'
    window = body[idx:idx + 1000]
    assert "event_type" in window and "'error'" in window, (
        "error 监听器内必须规范化 event_type='error'"
    )


def test_task8_qa_heartbeat_listener_passes_event_type_to_handler():
    """heartbeat 事件监听器必须将 event_type 字段规范化为 'heartbeat' 传入 handleProgressEvent。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    add_hb_pat = r"addEventListener\s*\(\s*['\"]heartbeat['\"]\s*,"
    assert _re.search(add_hb_pat, body), (
        "openProgressStream 必须注册 addEventListener('heartbeat', ...) 监听器"
    )

    idx = body.find("addEventListener('heartbeat'")
    if idx < 0:
        idx = body.find('addEventListener("heartbeat"')
    assert idx >= 0
    window = body[idx:idx + 1000]
    assert "event_type" in window and "'heartbeat'" in window, (
        "heartbeat 监听器内必须规范化 event_type='heartbeat'"
    )


def test_task8_qa_step_listener_preserves_event_type():
    """step 事件监听器必须保留后端传来的 event_type（如 node_started）。"""
    js = read_app_js()
    import re as _re

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    # 至少存在 1 个 addEventListener('step', ...) 块
    assert _re.search(
        r"addEventListener\s*\(\s*['\"]step['\"]\s*,",
        body,
    ), "openProgressStream 必须注册 addEventListener('step', ...) 监听器"


def test_task8_qa_terminal_events_do_not_require_seq_before_dispatch():
    """done/error/heartbeat 终端帧可能没有 seq，必须先路由类型再做 step 去重。"""
    js = read_app_js()

    body = _extract_function_body(js, "handleProgressEvent")
    assert body, "必须定义 function handleProgressEvent"

    type_pos = body.find("var type =")
    assert type_pos >= 0, "handleProgressEvent 必须先提取 event_type/type"

    seq_guard_pos = body.find("event.seq == null")
    assert seq_guard_pos >= 0, "handleProgressEvent 必须保留对无 seq step 事件的保护"

    call_report_pos = body.find("callReportAPI")
    assert call_report_pos >= 0, "done 事件必须触发 callReportAPI 获取最终报告"

    assert type_pos < seq_guard_pos < call_report_pos, (
        "handleProgressEvent 必须先根据 event_type 处理 done/error/heartbeat，再只对 step 事件应用 seq 守卫"
    )


def test_task8_qa_error_listener_ignores_connection_errors_without_data():
    """EventSource 连接级 error 没有 data，不能被误判为服务端任务失败。"""
    js = read_app_js()

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    idx = body.find("addEventListener('error'")
    if idx < 0:
        idx = body.find('addEventListener("error"')
    assert idx >= 0, "openProgressStream 必须注册命名 error 监听器"

    window = body[idx:idx + 900]
    assert "if (!e.data) return;" in window, (
        "命名 error 监听器收到无 data 的连接级错误时必须直接 return，不得注入任务失败"
    )
    assert "handleProgressEvent({ event_type: 'error' }" not in window, (
        "命名 error 监听器不得在 data 缺失/解析失败时合成 task error"
    )


def test_task8_qa_run_analysis_waits_for_commit_promise_before_persisting_progress():
    """新建 draft 会话时，progress 消息 POST 必须等待 commitDraftSession 拿到真实会话 ID。"""
    js = read_app_js()
    import re as _re

    send_body = _extract_function_body(js, "sendMessage")
    assert send_body, "必须定义 function sendMessage"
    route_body = _extract_function_body(js, "routeChatMessage")
    assert route_body, "必须定义 function routeChatMessage"
    assert "routeChatMessage(type, text, session, commitPromise)" in send_body, (
        "sendMessage 必须把 commitPromise 传给意图路由，避免 progress 消息 POST 到 draft id"
    )
    assert "runAnalysis(type, text, session, commitPromise)" in route_body, (
        "RCA 分支必须继续把 commitPromise 传给 runAnalysis"
    )

    run_body = _extract_function_body(js, "runAnalysis")
    assert run_body, "必须定义 function runAnalysis"
    assert _re.search(r"function\s+runAnalysis\s*\([^)]*commitPromise", js), (
        "runAnalysis 签名必须接收 commitPromise 或等价会话创建 Promise"
    )
    commit_wait_pos = run_body.find("conversationReady.then")
    post_pos = run_body.find("/messages")
    assert commit_wait_pos >= 0 and post_pos >= 0 and commit_wait_pos < post_pos, (
        "runAnalysis 持久化 progress assistant 消息前必须等待 conversationReady/commitPromise"
    )


# ═══════════════════════════════════════════════════════════════
# Task 9: SSE 重连、去重、失败和历史恢复边界
# ═══════════════════════════════════════════════════════════════


def test_task9_open_progress_stream_appends_after_from_last_seq():
    """前端重连/恢复时必须通过 after=lastSeq 续传，避免重复回放已见事件。"""
    js = read_app_js()

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    assert "buildProgressEventsUrl" in body, (
        "openProgressStream 必须使用 buildProgressEventsUrl(events_url, afterSeq) 统一追加 after 参数"
    )
    assert "state.progress.lastSeq" in body, (
        "openProgressStream 必须读取 state.progress.lastSeq 作为 after 参数"
    )
    assert "new EventSource(streamUrl)" in body, (
        "openProgressStream 必须使用追加 after 后的 streamUrl 创建 EventSource"
    )


def test_task9_switch_session_starts_replay_for_progress_restore_marker():
    """历史会话中带 taskId 的 assistant 消息应触发 SSE replay 恢复步骤历史。"""
    js = read_app_js()

    load_body = _extract_function_body(js, "loadMessagesForSession")
    assert load_body, "必须定义 function loadMessagesForSession"
    assert "restoreProgressForTaskMessage" in load_body, "loadMessagesForSession 必须识别 progressRestore 标记"
    assert "restoreProgressHistoryForSession(session)" in load_body, (
        "loadMessagesForSession 加载消息后必须调用 restoreProgressHistoryForSession(session) 触发历史回放"
    )

    restore_body = _extract_function_body(js, "restoreProgressHistoryForSession")
    assert restore_body, "必须定义 function restoreProgressHistoryForSession"
    assert "/api/v1/rca/tasks/" in restore_body and "/events" in restore_body, (
        "restoreProgressHistoryForSession 必须构造任务 events URL"
    )
    assert "openProgressStream" in restore_body, (
        "restoreProgressHistoryForSession 必须复用 openProgressStream 进行 SSE replay"
    )


def test_task9_report_fetch_failure_keeps_retry_context():
    """done 后获取报告失败时，同一消息应进入失败状态并保留重试所需异常类型/描述。"""
    js = read_app_js()

    body = _extract_function_body(js, "handleProgressEvent")
    assert body, "必须定义 function handleProgressEvent"

    catch_pos = body.find("获取报告失败")
    assert catch_pos >= 0, "done 后报告获取失败必须显示明确错误文案"
    window = body[catch_pos:catch_pos + 700]
    assert "msg.errorType" in window and "msg.errorDesc" in window, (
        "报告获取失败分支必须设置 errorType/errorDesc，保证重试按钮有上下文"
    )


def test_final_qa_progress_stream_uses_latest_message_id_after_persist():
    """SSE 监听器不能闭包捕获临时 messageId；持久化替换 id 后必须使用最新 messageId。"""
    js = read_app_js()

    body = _extract_function_body(js, "openProgressStream")
    assert body, "必须定义 function openProgressStream"

    assert "getActiveProgressMessageId" in body, (
        "openProgressStream 事件监听器必须通过 getActiveProgressMessageId(messageId) 获取最新 messageId"
    )
    assert "handleProgressEvent(payload, taskId, getActiveProgressMessageId(messageId), session)" in body, (
        "step/done/error/heartbeat 监听器调用 handleProgressEvent 时必须传入最新 messageId"
    )


def test_final_qa_completed_history_messages_restore_progress_even_with_report():
    """历史已完成消息已有 report_snapshot 时，也必须回放 progress 历史而不是直接跳过。"""
    js = read_app_js()

    body = _extract_function_body(js, "restoreProgressHistoryForSession")
    assert body, "必须定义 function restoreProgressHistoryForSession"

    assert "msg.report || msg.report_snapshot" not in body, (
        "历史恢复不能因为已有报告就跳过进度回放，否则重新打开会话看不到步骤历史"
    )
    assert "msg.progressRestore" in body and "openProgressStream" in body, (
        "历史恢复必须基于 progressRestore 打开 SSE replay"
    )


def test_progress_timeline_renders_execution_trace_with_round_and_tool_meta():
    """进度卡片不能只有 8 个标准步骤，还必须展示循环/工具多次调用的执行轨迹。"""
    js = read_app_js()
    css = read_styles_css()

    assert "progress.events" in js, "progress 状态必须保留追加式 events 轨迹"
    assert "renderProgressTraceHtml" in js, "必须定义执行轨迹渲染函数"
    assert "rca-progress-trace" in js, "renderProgressHtml 必须渲染执行轨迹区域"
    assert "第" in js and "轮" in js, "执行轨迹必须展示反思/执行轮次"
    assert "tool_name" in js or "selected_tools" in js, "执行轨迹必须展示工具调用/选择信息"
    assert ".rca-progress-trace" in css, "必须为执行轨迹提供样式"


def test_report_meta_times_use_space_separated_datetime_format():
    """报告底部元信息时间必须显示为 YYYY-MM-DD HH:mm:ss，而不是 ISO T/微秒格式。"""
    js = read_app_js()

    assert "function formatDateTime" in js, "必须定义 formatDateTime 格式化报告时间"
    body = _extract_function_body(js, "renderReportHtml")
    assert body, "必须定义 renderReportHtml"
    assert "formatDateTime(createdAt)" in body, "创建时间必须调用 formatDateTime(createdAt)"
    assert "formatDateTime(completedAt)" in body, "完成时间必须调用 formatDateTime(completedAt)"


def test_progress_trace_emphasizes_step_name_and_round_number():
    """执行轨迹中步骤名应加粗，第 x 轮前有空格且数字加粗。"""
    js = read_app_js()
    css = read_styles_css()

    body = _extract_function_body(js, "renderProgressTraceHtml")
    assert body, "必须定义 renderProgressTraceHtml"
    assert "rca-progress-trace-name" in body, "步骤名必须有独立样式容器"
    assert "rca-progress-trace-round-number" in js, "轮次数字必须有独立加粗容器"
    assert " 第 <span" in js or " 第 '" in js, "第几轮前必须保留一个空格"
    assert ".rca-progress-trace-name" in css and "font-weight: 700" in css, "步骤名必须加粗"
    assert ".rca-progress-trace-round-number" in css and "font-weight: 700" in css, "轮次数字必须加粗"


def test_progress_trace_uses_visible_index_and_horizontal_round_label():
    """执行轨迹序号应按可见列表从 #1 开始，轮次应与步骤名横向显示。"""
    js = read_app_js()
    css = read_styles_css()

    body = _extract_function_body(js, "renderProgressTraceHtml")
    assert body, "必须定义 renderProgressTraceHtml"
    assert "String(i + 1)" in body, "执行轨迹展示编号必须按可见列表从 #1 开始"
    assert "evt.seq || i + 1" not in body, "执行轨迹展示编号不能使用后端原始 seq"
    assert "rca-progress-trace-heading" in body, "步骤名与轮次必须放入同一个横向标题行"
    heading_css = css.split(".rca-progress-trace-heading {")[1].split("}")[0]
    assert "display: flex" in heading_css, "标题行必须使用横向 flex 布局"
    assert "flex-direction: column" not in heading_css, "标题行不能纵向排列轮次"


def test_progress_trace_merges_started_and_completed_events_per_round():
    """执行轨迹应把同一步骤同一轮的 started/completed 合并成一张卡。"""
    js = read_app_js()

    assert "function mergeProgressTraceEvents" in js, "必须定义执行轨迹事件合并函数"
    merge_body = _extract_function_body(js, "mergeProgressTraceEvents")
    render_body = _extract_function_body(js, "renderProgressTraceHtml")
    assert merge_body, "必须实现 mergeProgressTraceEvents"
    assert render_body, "必须定义 renderProgressTraceHtml"
    assert "node_started" in merge_body and "node_completed" in merge_body, (
        "必须识别 node_started/node_completed 并合并展示"
    )
    assert "node_name" in merge_body and "round" in merge_body, "合并键必须包含步骤名和轮次"
    assert "trace_lines" in merge_body, "合并后的卡片必须保留开始和完成两类描述行"
    assert "var traceEvents = mergeProgressTraceEvents(events)" in render_body, (
        "渲染必须基于合并后的 traceEvents，而不是原始 events"
    )


def test_progress_trace_renders_running_meta_and_completed_lines_in_order():
    """合并后的执行轨迹应按：正在执行、耗时、执行完成的顺序展示。"""
    js = read_app_js()
    body = _extract_function_body(js, "renderProgressTraceHtml")
    assert body, "必须定义 renderProgressTraceHtml"

    running_index = body.index("traceLines[0]")
    meta_index = body.index("rca-progress-trace-meta")
    completed_index = body.index("traceLines[j]")
    assert running_index < meta_index < completed_index, (
        "执行轨迹内容顺序必须是：正在执行 → 耗时/工具元信息 → 执行完成"
    )


def test_progress_trace_does_not_show_round_for_generate_report():
    """最终报告生成节点不属于反思循环，不应显示第 x 轮。"""
    js = read_app_js()
    body = _extract_function_body(js, "renderProgressTraceRoundHtml")
    assert body, "必须定义 renderProgressTraceRoundHtml"
    assert "generate_report" in body, "轮次渲染必须显式处理 generate_report"
    assert "evt.node_name === 'generate_report'" in body or 'evt.node_name === "generate_report"' in body
