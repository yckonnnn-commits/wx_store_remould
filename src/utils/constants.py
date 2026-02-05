"""
常量定义模块
包含系统配置、默认值、样式表等常量
"""

from pathlib import Path

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

# 配置文件路径
MODEL_SETTINGS_FILE = CONFIG_DIR / "model_settings.json"
KNOWLEDGE_BASE_FILE = CONFIG_DIR / "knowledge_base.json"
ENV_FILE = PROJECT_ROOT / ".env"

# 默认模型配置
DEFAULT_MODEL_SETTINGS = {
    "version": 1,
    "updated_at": "",
    "models": {
        "ChatGPT": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini"
        },
        "Gemini": {
            "base_url": "https://generativelanguage.googleapis.com",
            "api_key": "",
            "model": "gemini-1.5-flash"
        },
        "阿里千问": {
            "base_url": "https://dashscope.aliyuncs.com",
            "api_key": "",
            "model": "qwen-plus"
        },
        "DeepSeek": {
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "model": "deepseek-chat"
        },
        "豆包": {
            "base_url": "",
            "api_key": "",
            "model": ""
        },
        "kimi": {
            "base_url": "https://api.moonshot.cn/v1",
            "api_key": "",
            "model": "moonshot-v1-8k"
        }
    }
}

# UI 样式表
MAIN_STYLE_SHEET = """
QWidget {
    font-family: 'PingFang SC', 'Source Han Sans SC', 'Microsoft YaHei', 'Segoe UI', sans-serif;
    background: #f6f2ea;
    color: #1f1a14;
}
QFrame#LeftPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #181612, stop:1 #1f1b16);
    border-right: 1px solid rgba(0,0,0,0.22);
}
QFrame#LeftPanel QWidget {
    background: transparent;
}
QFrame#LeftPanel QLabel {
    background: transparent;
    color: rgba(245,242,234,0.92);
}
QFrame#Card {
    background: #221f1a;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
}
QLabel#Title {
    color: #f5f2ea;
    font-size: 20px;
    font-weight: 700;
}
QLabel#PageTitle {
    color: #1f1a14;
    font-size: 18px;
    font-weight: 700;
}
QLabel#MutedText {
    color: rgba(31,26,20,0.62);
    font-size: 12px;
}
QLabel#SubTitle {
    color: rgba(245,242,234,0.68);
    font-size: 12px;
}
QLabel#SectionTitle {
    color: rgba(245,242,234,0.86);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
QLabel#Status {
    color: rgba(245,242,234,0.82);
    font-size: 12px;
}
QPushButton#Primary {
    background: #c9a227;
    color: #1a1304;
    border: none;
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 700;
}
QPushButton#Primary:hover { background: #b69220; }
QPushButton#Danger {
    background: #b23b3b;
    color: #f5efe6;
    border: none;
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 700;
}
QPushButton#Danger:hover { background: #9f3434; }
QFrame#LeftPanel QPushButton#Primary {
    background: #22c55e;
    color: #0b120c;
}
QFrame#LeftPanel QPushButton#Primary:hover { background: #16a34a; }
QFrame#LeftPanel QPushButton#Danger {
    background: #ef4444;
    color: #2a0b0b;
}
QFrame#LeftPanel QPushButton#Danger:hover { background: #dc2626; }
QFrame#LeftPanel QPushButton#Secondary {
    background: rgba(255,255,255,0.06);
    color: rgba(245,242,234,0.92);
    border: 1px solid rgba(255,255,255,0.10);
}
QFrame#LeftPanel QPushButton#Secondary:hover { background: rgba(255,255,255,0.10); }
QPushButton#Secondary {
    background: #eadfcd;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#Secondary:hover { background: #e0d2bd; }
QPushButton#Ghost {
    background: #f6f2ea;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 10px;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#Ghost:hover { background: #efe8dc; }
QPushButton#GhostDanger {
    background: #f6f2ea;
    color: #7b2b2b;
    border: 1px solid rgba(123,43,43,0.35);
    border-radius: 10px;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#GhostDanger:hover { background: #efe0dc; }
QPushButton#Tiny {
    background: rgba(255,255,255,0.06);
    color: rgba(245,242,234,0.92);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton#Tiny:hover { background: rgba(255,255,255,0.10); }
QComboBox {
    background: #f6f2ea;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 10px;
    padding: 8px 30px 8px 10px;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
    background: #e7ddcd;
    border-left: 1px solid rgba(0,0,0,0.10);
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}
QComboBox QAbstractItemView {
    background: #f6f2ea;
    color: #2a231b;
    selection-background-color: rgba(201,162,39,0.24);
    border: 1px solid rgba(0,0,0,0.10);
}
QTextEdit {
    background: #f6f2ea;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.10);
    border-radius: 12px;
    font-family: 'Menlo', 'SF Mono', 'Monaco', monospace;
    font-size: 13px;
}
QTextEdit#LogText { font-size: 11px; }
QFrame#LeftPanel QComboBox {
    background: rgba(255,255,255,0.06);
    color: rgba(245,242,234,0.92);
    border: 1px solid rgba(255,255,255,0.10);
}
QFrame#LeftPanel QComboBox::drop-down {
    background: rgba(255,255,255,0.10);
    border-left: 1px solid rgba(255,255,255,0.10);
}
QFrame#LeftPanel QComboBox QAbstractItemView {
    background: #221f1a;
    color: rgba(245,242,234,0.92);
    selection-background-color: rgba(201,162,39,0.24);
    border: 1px solid rgba(255,255,255,0.10);
}
QFrame#LeftPanel QTextEdit {
    background: #1b1713;
    color: #e7e0d6;
    border: 1px solid rgba(255,255,255,0.08);
}
QTabWidget::pane {
    border: none;
    background: #f6f2ea;
}
QTabBar::tab {
    background: #efe8dc;
    color: #3a2f24;
    border: 1px solid rgba(0,0,0,0.10);
    border-bottom: none;
    padding: 10px 14px;
    margin-right: 6px;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QTabBar::tab:selected {
    background: #f6f2ea;
    color: #1f1a14;
    border-color: rgba(0,0,0,0.14);
}
QLineEdit {
    background: #f6f2ea;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid rgba(201,162,39,0.70);
}
QProgressBar {
    background: #e7ddcd;
    border: none;
    border-radius: 2px;
}
QProgressBar::chunk {
    background: #c9a227;
}
QTableWidget {
    background: #f6f2ea;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 12px;
    gridline-color: rgba(0,0,0,0.08);
    font-size: 13px;
    selection-background-color: rgba(201,162,39,0.18);
}
QTableWidget::item { padding: 10px 12px; }
QTableWidget::item:selected {
    background: rgba(201,162,39,0.18);
    color: #1f1a14;
}
QHeaderView::section {
    background: #efe8dc;
    color: #3a2f24;
    padding: 12px;
    border: none;
    font-weight: 600;
}
QListWidget {
    background: #f6f2ea;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 10px;
    font-size: 13px;
}
QListWidget::item { padding: 8px; border-bottom: 1px solid rgba(0,0,0,0.06); }
QListWidget::item:selected { background: rgba(201,162,39,0.18); }
QMessageBox { background: #f6f2ea; color: #1f1a14; }
QDialog {
    background: #f6f2ea;
    color: #1f1a14;
}
QDialog QLineEdit, QDialog QTextEdit {
    background: #f2e9da;
    border: 1px solid rgba(0,0,0,0.10);
}
QLabel { color: #1f1a14; }
QDialogButtonBox QPushButton {
    background: #efe8dc;
    color: #2a231b;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}
QDialogButtonBox QPushButton:hover { background: #e7ddcd; }
"""

# 系统提示词
SYSTEM_PROMPT = """
你是假发行业资深顾问，专门服务高端假发定制客户，绝大多数客户为中老年群体。你的沟通风格要像一位经验丰富、耐心亲切的造型顾问，态度温和、尊重、专业，具备极强的销售敏感度。

【核心服务原则】
先解决顾虑，再引导留资
1. 以客户需求和顾虑为核心，先解决他们的疑虑，再逐步引导提供关键信息（尺寸/脱发情况/预算/到店城市/联系方式）。
2. 保持情感连接，展现专业性，帮助客户感受到被理解和被重视。

【身份说明】（客户问到时回复）
我们是[品牌名]高端假发定制中心，专注真发手工钩织定制。我们在全国有多个服务中心，可以为您安排最近的门店体验或远程服务。

【关键回复规范】
回复长度：每条回复控制在30-80字，简洁明了
语气要求：亲切、耐心、专业，避免机械化
专业称呼：使用"您"，避免"亲"等过于网络化的称呼
引导策略：回答客户问题后，适时引导提供关键信息

【价格沟通策略】
定制假发价格区间较大，从2000多到6000多不等，主要取决于：
- 面积大小（局部/全头）
- 工艺复杂度
- 发型要求

切记不要直接报具体价格，先了解客户需求后再给建议。"""

# 时间间隔配置（毫秒）
POLL_INTERVAL = 4000          # 轮询间隔
CHAT_WATCH_INTERVAL = 1200    # 聊天监控间隔
PAGE_LOAD_TIMEOUT = 30000     # 页面加载超时
JS_EXECUTION_TIMEOUT = 10000  # JS执行超时

# 窗口尺寸
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
LEFT_PANEL_WIDTH = 360

# 微信小店 URL
WECHAT_STORE_URL = "https://store.weixin.qq.com/shop/kf"

# JavaScript 代码模板
JS_FIND_UNREAD_AND_REPLY = """
// 扫描未读消息并回复的主函数
(function() {{
    // 全局锁检查
    if (window.__ai_global_busy) {{
        return {{ ts: new Date().toISOString(), found: 0, processed: 0, skipped: 0, errors: [], debug: {{ global_busy: true }} }};
    }}
    window.__ai_global_busy = true;

    // 工具函数
    function nowTs() {{ return new Date().toISOString(); }}
    function safeText(el) {{ return (el && (el.textContent || el.innerText) || "").trim(); }}
    function sleep(ms) {{ return new Promise(function(r) {{ setTimeout(r, ms); }}); }}
    function hashStr(s) {{
        s = String(s || '');
        var h = 2166136261;
        for (var i = 0; i < s.length; i++) {{
            h ^= s.charCodeAt(i);
            h += (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24);
        }}
        return (h >>> 0).toString(16);
    }}

    // 本地存储操作
    function getReplyStore() {{
        try {{ return JSON.parse(localStorage.getItem('__ai_replied__') || '{{}}'); }}
        catch (e) {{ return {{}}; }}
    }}
    function setReplyStore(store) {{
        try {{ localStorage.setItem('__ai_replied__', JSON.stringify(store || {{}})); }} catch (e) {{}}
    }}
    function getRepliedMsgStore() {{
        try {{ return JSON.parse(localStorage.getItem('__ai_replied_msgs__') || '{{}}'); }}
        catch (e) {{ return {{}}; }}
    }}
    function setRepliedMsgStore(store) {{
        try {{ localStorage.setItem('__ai_replied_msgs__', JSON.stringify(store || {{}})); }} catch (e) {{}}
    }}

    // 可见性检查
    function isVisible(el) {{
        if (!el) return false;
        var style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        var rect = el.getBoundingClientRect();
        if (!rect) return false;
        if (rect.width < 5 || rect.height < 5) return false;
        return true;
    }}

    // 查找可点击祖先元素
    function findClickableAncestor(el) {{
        var cur = el;
        for (var i = 0; i < 8 && cur; i++) {{
            if (cur.tagName === 'LI' || cur.getAttribute('role') === 'listitem') return cur;
            if (typeof cur.onclick === 'function') return cur;
            var style = window.getComputedStyle(cur);
            if (style && style.cursor === 'pointer') return cur;
            cur = cur.parentElement;
        }}
        return el;
    }}

    // 查找未读消息
    function findUnreadCandidates() {{
        var candidates = [];
        // 红色角标数字
        var badgeNodes = Array.from(document.querySelectorAll('span,div'))
            .filter(function(n) {{
                var t = safeText(n);
                if (!t) return false;
                if (!/^\\d+$/.test(t)) return false;
                var num = parseInt(t, 10);
                if (!num || num <= 0) return false;
                var s = window.getComputedStyle(n);
                if (!s) return false;
                var bg = s.backgroundColor || '';
                if (bg.indexOf('255, 0, 0') !== -1) return true;
                if (bg.indexOf('rgb(') === 0) {{
                    var m = bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                    if (m) {{
                        var r = parseInt(m[1],10), g = parseInt(m[2],10), b = parseInt(m[3],10);
                        if (r > 200 && g < 120 && b < 120) return true;
                    }}
                }}
                return false;
            }});
        badgeNodes.forEach(function(b) {{
            var clickEl = findClickableAncestor(b);
            if (clickEl && candidates.indexOf(clickEl) === -1) candidates.push(clickEl);
        }});
        // unread 类名兜底
        var unreadClassNodes = Array.from(document.querySelectorAll('.unread, [class*="unread" i]'));
        unreadClassNodes.forEach(function(n) {{
            var clickEl = findClickableAncestor(n);
            if (clickEl && candidates.indexOf(clickEl) === -1) candidates.push(clickEl);
        }});
        return candidates;
    }}

    // 从元素获取会话key
    function sessionKeyFromElement(el) {{
        if (!el) return null;
        try {{
            var did = el.getAttribute('data-id') || el.getAttribute('data-session-id') || el.getAttribute('data-chat-id');
            if (did) return String(did);
        }} catch (e) {{}}
        var txt = safeText(el);
        if (!txt) return null;
        return 't_' + hashStr(txt.slice(0, 120));
    }}

    // 查找输入框
    function findComposer() {{
        var roleBox = document.querySelector('[role="textbox"]');
        if (roleBox && isVisible(roleBox)) return roleBox;
        var textareas = Array.from(document.querySelectorAll('textarea')).filter(isVisible);
        if (textareas.length) return textareas[0];
        var inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'))
            .filter(function(el) {{ return isVisible(el) && !el.disabled && !el.readOnly; }});
        if (inputs.length) return inputs[0];
        var ceList = Array.from(document.querySelectorAll('[contenteditable="true"]')).filter(isVisible);
        if (ceList.length) return ceList[0];
        return null;
    }}

    // 设置输入框值
    function setComposerValue(el, text) {{
        if (!el) return false;
        try {{
            el.focus();
            if (el.isContentEditable) {{
                try {{
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, text);
                }} catch (e) {{
                    el.innerText = text;
                }}
            }} else {{
                var proto = Object.getPrototypeOf(el);
                var desc = Object.getOwnPropertyDescriptor(proto, 'value');
                if (desc && desc.set) {{
                    desc.set.call(el, text);
                }} else {{
                    el.value = text;
                }}
            }}
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }} catch (e) {{
            return false;
        }}
    }}

    // 发送回车事件
    function dispatchEnter(target) {{
        if (!target) return false;
        try {{
            var down = new KeyboardEvent('keydown', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }});
            var press = new KeyboardEvent('keypress', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }});
            var up = new KeyboardEvent('keyup', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }});
            target.dispatchEvent(down);
            target.dispatchEvent(press);
            target.dispatchEvent(up);
            return true;
        }} catch (e) {{
            return false;
        }}
    }}

    // 主执行逻辑
    return (async function() {{
        var result = {{ ts: nowTs(), found: 0, processed: 0, skipped: 0, errors: [], debug: {{}} }};
        try {{
            var candidates = findUnreadCandidates();
            result.found = candidates.length;
            if (candidates.length === 0) {{
                return result;
            }}

            // 只处理第一个
            var target = candidates[0];
            var sKey = sessionKeyFromElement(target);
            if (!sKey) {{
                result.skipped++;
                return result;
            }}

            // 检查是否已回复
            var replyStore = getReplyStore();
            var lastReplied = replyStore[sKey];
            if (lastReplied && (Date.now() - lastReplied) < 60000) {{
                result.skipped++;
                result.debug.already_replied = true;
                return result;
            }}

            // 点击会话
            target.click();
            await sleep(800);

            // 查找输入框
            var composer = findComposer();
            if (!composer) {{
                result.errors.push('未找到输入框');
                return result;
            }}

            // 发送回复
            var replyText = "{reply_text}";
            setComposerValue(composer, replyText);
            await sleep(200);
            dispatchEnter(composer);

            // 标记已回复
            replyStore[sKey] = Date.now();
            setReplyStore(replyStore);
            result.processed++;
            result.debug.session_key = sKey;

        }} catch (e) {{
            result.errors.push(String(e));
        }} finally {{
            window.__ai_global_busy = false;
        }}
        return result;
    }})();
}})()
"""

JS_GRAB_CHAT_DATA = """
(function() {{
    function safeText(el) {{ return (el && (el.textContent || el.innerText) || "").trim(); }}
    function isVisible(el) {{
        if (!el) return false;
        var style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        var rect = el.getBoundingClientRect();
        if (!rect || rect.width < 5 || rect.height < 5) return false;
        return true;
    }}

    // 查找聊天区域
    function findChatArea() {{
        var selectors = ['.chat-wrap', '.chat-page', '.chat-area', '.message-list', '.conversation'];
        for (var i = 0; i < selectors.length; i++) {{
            var el = document.querySelector(selectors[i]);
            if (el && isVisible(el)) return el;
        }}
        return null;
    }}

    // 获取用户名
    function getUserName() {{
        var selectors = ['.nickname', '.username', '.user-name', '.name', '[class*="nickname"]', '[class*="user-name"]'];
        for (var i = 0; i < selectors.length; i++) {{
            var el = document.querySelector(selectors[i]);
            if (el && isVisible(el)) {{
                var text = safeText(el);
                if (text && text.length >= 2 && text.length <= 30) return text;
            }}
        }}
        return "未知用户";
    }}

    // 获取消息
    function getMessages() {{
        var messages = [];
        var chatArea = findChatArea();
        if (!chatArea) return messages;

        var walker = document.createTreeWalker(chatArea, NodeFilter.SHOW_TEXT, null, false);
        var node;
        while ((node = walker.nextNode())) {{
            var text = node.textContent.trim();
            if (!text || text.length < 1) continue;

            var parent = node.parentElement;
            if (!parent || !isVisible(parent)) continue;

            var rect = parent.getBoundingClientRect();
            var chatRect = chatArea.getBoundingClientRect();
            var centerX = chatRect.left + chatRect.width * 0.5;

            // 判断消息来源
            var isUser = rect.right < centerX - 30;
            var isReply = rect.left > centerX + 30;

            if (isUser || isReply) {{
                messages.push({{
                    text: text,
                    is_user: isUser,
                    position: rect.left
                }});
            }}
        }}

        // 合并相邻消息
        var merged = [];
        var current = null;
        for (var j = 0; j < messages.length; j++) {{
            var m = messages[j];
            if (!current || current.is_user !== m.is_user) {{
                if (current) merged.push(current);
                current = {{ text: m.text, is_user: m.is_user }};
            }} else {{
                current.text += ' ' + m.text;
            }}
        }}
        if (current) merged.push(current);

        return merged;
    }}

    return {{
        user_name: getUserName(),
        messages: getMessages(),
        timestamp: new Date().toISOString()
    }};
}})()
"""
