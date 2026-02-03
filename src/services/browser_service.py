"""
浏览器服务模块
负责与QWebEngineView的交互，注入JavaScript执行页面操作
"""

import json
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtCore import QUrl


class BrowserService(QObject):
    """浏览器服务，封装QWebEngineView的操作"""

    page_loaded = Signal(bool)          # 页面加载完成
    message_received = Signal(dict)     # 收到消息
    js_execution_result = Signal(str, object)  # JS执行结果 (id, result)
    error_occurred = Signal(str)        # 错误信号

    def __init__(self, web_view: QWebEngineView):
        super().__init__()
        self.web_view = web_view
        self.page = web_view.page()
        self._page_ready = False
        self._pending_callbacks: dict = {}

        # 配置浏览器设置
        self._setup_browser()

        # 连接信号
        self.page.loadFinished.connect(self._on_load_finished)

    def _setup_browser(self):
        """配置浏览器设置"""
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

    def _on_load_finished(self, success: bool):
        """页面加载完成回调"""
        self._page_ready = success
        self.page_loaded.emit(success)

    def navigate(self, url: str):
        """导航到指定URL"""
        self._page_ready = False
        self.web_view.setUrl(QUrl(url))

    def reload(self):
        """刷新页面"""
        self.web_view.reload()

    def is_ready(self) -> bool:
        """检查页面是否加载完成"""
        return self._page_ready

    def run_javascript(self, script: str, callback: Callable = None,
                       timeout_ms: int = 10000) -> Optional[str]:
        """执行JavaScript代码

        Args:
            script: JavaScript代码
            callback: 回调函数，接收执行结果 (success, data/error)
            timeout_ms: 超时时间（毫秒）

        Returns:
            如果没有callback，返回执行ID用于追踪
        """
        import uuid
        exec_id = str(uuid.uuid4())[:8]

        if callback:
            self._pending_callbacks[exec_id] = callback

            def handle_result(result):
                if exec_id in self._pending_callbacks:
                    cb = self._pending_callbacks.pop(exec_id)
                    # JavaScript 执行成功，将结果传递给 callback
                    # result 可能是 dict, list, str, int, None 等
                    # 如果是字符串且以 { 开头，尝试解析 JSON
                    if isinstance(result, str) and result.strip().startswith('{'):
                        try:
                            import json as json_mod
                            parsed = json_mod.loads(result)
                            cb(True, parsed)
                        except Exception:
                            cb(True, result)
                    else:
                        cb(True, result)

            # PySide6 的 runJavaScript 可以直接接受回调函数
            # 它会在 JavaScript 执行完成并序列化结果后调用回调
            try:
                self.page.runJavaScript(script, handle_result)
            except Exception as e:
                if exec_id in self._pending_callbacks:
                    self._pending_callbacks.pop(exec_id)
                callback(False, str(e))

            # 设置超时
            if timeout_ms > 0:
                QTimer.singleShot(timeout_ms, lambda: self._on_timeout(exec_id))

            return exec_id
        else:
            # 没有回调，直接执行
            self.page.runJavaScript(script)
            return exec_id

    def _on_timeout(self, exec_id: str):
        """处理超时"""
        if exec_id in self._pending_callbacks:
            callback = self._pending_callbacks.pop(exec_id)
            callback(False, "执行超时")

    def find_and_click_first_unread(self, callback: Callable):
        """查找并点击第一个未读消息

        Args:
            callback: 回调函数，接收 (success, info)
        """
        script = r"""
        (function() {
            function safeText(el) { return (el && (el.textContent || el.innerText) || "").trim(); }
            function isVisible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect || rect.width < 3 || rect.height < 3) return false;
                return true;
            }
            function parseCssColorToRgb(colorStr) {
                if (!colorStr) return null;
                colorStr = String(colorStr).trim();
                var m = colorStr.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\)$/i);
                if (m) {
                    var r = parseInt(m[1], 10), g = parseInt(m[2], 10), b = parseInt(m[3], 10);
                    var a = (m[4] === undefined) ? 1 : parseFloat(m[4]);
                    return { r: r, g: g, b: b, a: a };
                }
                return null;
            }
            function isRedColor(rgb) {
                if (!rgb) return false;
                if (rgb.a !== undefined && rgb.a === 0) return false;
                return (rgb.r > 180 && rgb.g < 140 && rgb.b < 140);
            }
            function findRedStyleInfo(el) {
                var cur = el;
                for (var i = 0; i < 4 && cur; i++) {
                    var st = window.getComputedStyle(cur);
                    if (st) {
                        var bg = st.backgroundColor || '';
                        var bc = st.borderColor || '';
                        var bgRgb = parseCssColorToRgb(bg);
                        if (bgRgb && isRedColor(bgRgb)) return { type: 'background', value: bg, level: i };
                        var bcRgb = parseCssColorToRgb(bc);
                        if (bcRgb && isRedColor(bcRgb)) return { type: 'border', value: bc, level: i };
                    }
                    cur = cur.parentElement;
                }
                return null;
            }
            function findClickableAncestor(el) {
                if (!el) return null;
                var cur = el;
                for (var i = 0; i < 12 && cur; i++) {
                    var tag = (cur.tagName || '').toUpperCase();
                    var role = (cur.getAttribute && cur.getAttribute('role')) ? cur.getAttribute('role') : '';

                    // 强优先：会话列表项通常是 LI / role=listitem
                    if (tag === 'LI' || role === 'listitem') return cur;

                    // 常见：data-id / data-session-id 之类的可点击会话容器
                    try {
                        var did = cur.getAttribute && (cur.getAttribute('data-id') || cur.getAttribute('data-session-id') || cur.getAttribute('data-chat-id'));
                        if (did) return cur;
                    } catch (e) {}

                    // 其次：按钮/链接
                    if (tag === 'A' || tag === 'BUTTON' || role === 'button' || role === 'link') return cur;

                    // 兜底：pointer 且尺寸合理（避免选到整页容器）
                    var st = window.getComputedStyle(cur);
                    var r = cur.getBoundingClientRect ? cur.getBoundingClientRect() : null;
                    if (st && (st.cursor === 'pointer' || st.cursor === 'hand') && r) {
                        var tooBig = (r.width >= window.innerWidth * 0.8) || (r.height >= window.innerHeight * 0.6);
                        var tooSmall = (r.width < 120) || (r.height < 30);
                        var inLeftPane = (r.left < window.innerWidth * 0.55);
                        if (!tooBig && !tooSmall && inLeftPane && isVisible(cur)) return cur;
                    }

                    cur = cur.parentElement;
                }

                return null;
            }

            function findSessionListItem(badgeEl) {
                // 从徽标向上查找真正的会话列表项（通常包含用户名和预览）
                var cur = badgeEl;
                for (var i = 0; i < 8 && cur; i++) {
                    var r = cur.getBoundingClientRect();
                    // 会话项通常宽度较大（>100px）且高度适中（>30px）
                    if (r && r.width > 100 && r.height > 30) {
                        var tag = (cur.tagName || '').toUpperCase();
                        if (tag === 'LI' || tag === 'DIV') {
                            // 检查是否包含用户名或预览文本（排除纯徽标）
                            var txt = safeText(cur);
                            if (txt && txt.length > 2 && !/^\d+$/.test(txt)) {
                                return cur;
                            }
                        }
                    }
                    cur = cur.parentElement;
                }
                return null;
            }

            function isProbablyNumberBadge(el) {
                if (!el || !isVisible(el)) return false;
                var t = safeText(el);
                if (!t || !/^\d+$/.test(t)) return false;
                var num = parseInt(t, 10);
                if (!num || num <= 0 || num > 999) return false;
                var r = el.getBoundingClientRect();
                if (!r) return false;
                if (r.width > 90 || r.height > 90) return false;
                if (r.width < 4 || r.height < 4) return false;
                if (r.left > window.innerWidth * 0.7) return false;
                return true;
            }
            function isProbablyDotBadge(el) {
                if (!el || !isVisible(el)) return false;
                var t = safeText(el);
                if (t) return false;
                var r = el.getBoundingClientRect();
                if (!r) return false;
                if (r.width > 20 || r.height > 20) return false;
                if (r.width < 4 || r.height < 4) return false;
                if (r.left > window.innerWidth * 0.7) return false;
                return true;
            }

            try {
                var allNodes = Array.from(document.querySelectorAll('span,div,i,em,strong,sup,b'));
                var debugInfo = { totalNodes: allNodes.length, candidates: [] };
                var candidates = [];

                for (var idx = 0; idx < allNodes.length; idx++) {
                    var n = allNodes[idx];
                    var isNum = isProbablyNumberBadge(n);
                    var isDot = !isNum && isProbablyDotBadge(n);
                    if (!isNum && !isDot) continue;

                    var redInfo = findRedStyleInfo(n);
                    if (!redInfo) continue;

                    var rect = n.getBoundingClientRect();

                    // 过滤：左侧导航栏上的红点/数字（通常非常靠左且较靠上）
                    if (rect && rect.left < 60 && rect.top < 120) {
                        continue;
                    }

                    var sessionEl = findClickableAncestor(n);
                    var sessionRect = null;
                    var hasSession = false;
                    if (sessionEl && sessionEl.getBoundingClientRect) {
                        sessionRect = sessionEl.getBoundingClientRect();
                        if (sessionRect) {
                            var tooBig = (sessionRect.width >= window.innerWidth * 0.8) || (sessionRect.height >= window.innerHeight * 0.6);
                            var tooSmall = (sessionRect.width < 120) || (sessionRect.height < 30);
                            var inLeftPane = (sessionRect.left < window.innerWidth * 0.55);
                            var notHeader = (sessionRect.top > 90);
                            if (!tooBig && !tooSmall && inLeftPane && notHeader) {
                                hasSession = true;
                            }
                        }
                    }

                    candidates.push({
                        rectTop: rect.top,
                        rectLeft: rect.left,
                        badgeText: isNum ? safeText(n) : 'dot',
                        red: redInfo,
                        hasSession: hasSession,
                        sessionRect: sessionRect
                    });

                    if (debugInfo.candidates.length < 10) {
                        var st = window.getComputedStyle(n);
                        debugInfo.candidates.push({
                            text: isNum ? safeText(n) : '',
                            bg: st ? st.backgroundColor : '',
                            border: st ? st.borderColor : '',
                            rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
                            red: redInfo
                        });
                    }
                }

                if (candidates.length === 0) {
                    return JSON.stringify({ found: false, clicked: false, reason: 'no_unread', debug: debugInfo });
                }

                // 优先选择“确认为会话项”的未读
                var preferred = candidates.filter(function(c) { return !!c.hasSession; });
                var usable = preferred.length ? preferred : candidates;
                usable.sort(function(a, b) {
                    var at = (a.sessionRect && a.sessionRect.top) ? a.sessionRect.top : a.rectTop;
                    var bt = (b.sessionRect && b.sessionRect.top) ? b.sessionRect.top : b.rectTop;
                    return at - bt;
                });
                var target = usable[0];

                // 重新定位一次目标节点（避免闭包里对象被序列化）
                var badgeNodes = Array.from(document.querySelectorAll('span,div,i,em,strong,sup,b'));
                var bestEl = null;
                var bestDist = 1e9;
                for (var j = 0; j < badgeNodes.length; j++) {
                    var el = badgeNodes[j];
                    if (!isVisible(el)) continue;
                    var br = el.getBoundingClientRect();
                    if (br && br.left < 60 && br.top < 120) continue;
                    var t = safeText(el);
                    if (target.badgeText !== 'dot') {
                        if (t !== target.badgeText) continue;
                        if (!/^\d+$/.test(t)) continue;
                    } else {
                        if (t) continue;
                    }
                    var ri = findRedStyleInfo(el);
                    if (!ri) continue;
                    // 优先选择具有合理会话祖先的徽标
                    var sEl = findClickableAncestor(el);
                    if (target.hasSession && !sEl) continue;
                    var r2 = el.getBoundingClientRect();
                    var dist = Math.abs(r2.top - target.rectTop) + Math.abs(r2.left - target.rectLeft);
                    if (dist < bestDist) { bestDist = dist; bestEl = el; }
                }

                if (!bestEl) {
                    return JSON.stringify({
                        found: true,
                        clicked: false,
                        reason: 'badge_node_lost',
                        badgeText: target.badgeText,
                        totalUnread: candidates.length,
                        debug: debugInfo
                    });
                }

                // 参考 hari_main.py：点击“会话项”本身
                // 如果能找到合理的会话容器，优先点击容器；否则才点击徽标
                var sessionClickEl = findClickableAncestor(bestEl);
                var clickEl = sessionClickEl ? sessionClickEl : bestEl;
                if (clickEl && clickEl.scrollIntoView) {
                    try { clickEl.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                }
                if (clickEl) {
                    var clicked = false;
                    try {
                        // 方式1：直接点击会话项（参考 hari_main.py）
                        clickEl.click();
                        clicked = true;
                    } catch (e1) {
                        // 方式2：基于坐标的点击（会话项中心）
                        var rect = clickEl.getBoundingClientRect();
                        var centerX = rect.left + rect.width / 2;
                        var centerY = rect.top + rect.height / 2;
                        try {
                            var targetEl = document.elementFromPoint(centerX, centerY);
                            if (targetEl) {
                                targetEl.click();
                                clicked = true;
                            }
                        } catch (e2) {}
                    }
                    // 方式3：模拟鼠标事件
                    try {
                        var rect = clickEl.getBoundingClientRect();
                        var centerX = rect.left + rect.width / 2;
                        var centerY = rect.top + rect.height / 2;
                        var downEvt = new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX: centerX, clientY: centerY });
                        var upEvt = new MouseEvent('mouseup', { bubbles: true, cancelable: true, clientX: centerX, clientY: centerY });
                        var clickEvt = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: centerX, clientY: centerY });
                        clickEl.dispatchEvent(downEvt);
                        clickEl.dispatchEvent(upEvt);
                        clickEl.dispatchEvent(clickEvt);
                        clicked = true;
                    } catch (e3) {}
                    return JSON.stringify({
                        found: true,
                        clicked: clicked,
                        badgeText: target.badgeText,
                        totalUnread: candidates.length,
                        debug: Object.assign({}, debugInfo, {
                            clickTarget: {
                                tagName: clickEl.tagName,
                                rect: { left: clickEl.getBoundingClientRect().left, top: clickEl.getBoundingClientRect().top, width: clickEl.getBoundingClientRect().width, height: clickEl.getBoundingClientRect().height },
                                point: { x: clickEl.getBoundingClientRect().left + clickEl.getBoundingClientRect().width / 2, y: clickEl.getBoundingClientRect().top + clickEl.getBoundingClientRect().height / 2 },
                                isSessionItem: !!sessionClickEl
                            }
                        })
                    });
                }

                return JSON.stringify({
                    found: true,
                    clicked: false,
                    reason: 'no_clickable',
                    badgeText: target.badgeText,
                    totalUnread: candidates.length,
                    debug: debugInfo
                });
            } catch (e) {
                return JSON.stringify({
                    found: false,
                    clicked: false,
                    reason: 'exception',
                    error: String(e && (e.stack || e.message || e))
                });
            }
        })()
        """;
        self.run_javascript(script, callback)

    def enter_session(self, element_info: dict, callback: Callable = None):
        """点击进入会话

        Args:
            element_info: 元素位置信息 {x, y}
            callback: 回调函数
        """
        script = f"""
        (function() {{
            var el = document.elementFromPoint({element_info.get('x', 0)}, {element_info.get('y', 0)});
            if (el) {{
                var clickable = el;
                for (var i = 0; i < 8 && clickable; i++) {{
                    if (clickable.tagName === 'LI' || clickable.getAttribute('role') === 'listitem' ||
                        typeof clickable.onclick === 'function') {{
                        break;
                    }}
                    clickable = clickable.parentElement;
                }}
                if (clickable) {{
                    clickable.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        if callback:
            self.run_javascript(script, callback)
        else:
            self.page.runJavaScript(script)

    def grab_chat_data(self, callback: Callable):
        """抓取聊天数据 - 基于微信小店实际结构优化版

        Args:
            callback: 回调函数，接收 (success, data)
        """
        script = r"""
        (function() {
            function safeText(el) {
                if (!el) return "";
                return (el.textContent || el.innerText || "").trim();
            }

            function isVisible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect || rect.width < 5 || rect.height < 5) return false;
                return true;
            }

            function getCurrentChatUser() {
                var result = { name: null, method: null, allCandidates: [] };

                function isValidUserName(text) {
                    if (!text || text.length < 1 || text.length > 20) return false;
                    if (/\s/.test(text)) return false;
                    if (/[0-9]/.test(text)) return false;
                    if (/[：:？?!！。，,.]/.test(text)) return false;
                    if (/^星期[一二三四五六日]/.test(text)) return false;
                    if (/\d{1,2}:\d{2}/.test(text)) return false;
                    var filterWords = ['转接', '结束', '接待', '开始', '继续', '回复', '进入',
                                       '用户超时', '客服已结束', '你已超过', '未回复', '会话已结束',
                                       '会话', '全部', '当前会话'];
                    for (var f = 0; f < filterWords.length; f++) {
                        if (text.indexOf(filterWords[f]) !== -1) return false;
                    }
                    return true;
                }

                var headerAreas = document.querySelectorAll('.chat-header, .chat-title, .session-title, [class*="header"]');
                for (var i = 0; i < headerAreas.length; i++) {
                    var area = headerAreas[i];
                    if (!isVisible(area)) continue;
                    var r = area.getBoundingClientRect();
                    if (r.left < 300 || r.top > 150) continue;
                    var text = safeText(area);
                    if (isValidUserName(text)) {
                        result.allCandidates.push({source: 'header', text: text});
                        if (!result.name) { result.name = text; result.method = 'header'; }
                    }
                }

                var headings = document.querySelectorAll('h1, h2, h3, h4');
                for (var j = 0; j < headings.length; j++) {
                    var h = headings[j];
                    if (!isVisible(h)) continue;
                    var r = h.getBoundingClientRect();
                    if (r.left < 300 || r.top > 150) continue;
                    var text = safeText(h);
                    if (isValidUserName(text)) {
                        result.allCandidates.push({source: 'heading', text: text});
                        if (!result.name) { result.name = text; result.method = 'heading'; }
                    }
                }

                var selectedItems = document.querySelectorAll('[class*="current"], .selected, [aria-selected="true"]');
                var best = null, bestScore = -1e9;
                for (var k = 0; k < selectedItems.length; k++) {
                    var item = selectedItems[k];
                    if (!isVisible(item)) continue;
                    var r = item.getBoundingClientRect();
                    if (r.left > 260) continue;
                    if (r.top < 130) continue;
                    var text = safeText(item);
                    var nameSelectors = ['.name', '.nickname', '.user-name', '.title', '[class*="name"]', '[class*="title"]'];
                    for (var m = 0; m < nameSelectors.length; m++) {
                        var nameEl = item.querySelector(nameSelectors[m]);
                        if (nameEl) { var t = safeText(nameEl); if (t) { text = t; break; } }
                    }
                    if (!isValidUserName(text)) continue;
                    var score = 0;
                    try {
                        if (String(item.className || '').indexOf('current') !== -1) score += 200;
                        if (String(item.className || '').indexOf('selected') !== -1) score += 150;
                        if (item.getAttribute && item.getAttribute('aria-selected') === 'true') score += 120;
                    } catch (e) {}
                    score += Math.floor(r.top / 10);
                    result.allCandidates.push({source: 'list-item', text: text, score: score});
                    if (score > bestScore) { bestScore = score; best = { text: text, method: 'list-item' }; }
                }
                if (best && !result.name) { result.name = best.text; result.method = best.method; }

                return result;
            }

            function getChatMessages() {
                var result = { messages: [], userMessages: [], replyMessages: [], debug: [] };

                function findComposer() {
                    var roleBox = document.querySelector('[role="textbox"]');
                    if (roleBox && isVisible(roleBox)) return roleBox;
                    var textareas = Array.from(document.querySelectorAll('textarea')).filter(isVisible);
                    if (textareas.length) return textareas[0];
                    var ceList = Array.from(document.querySelectorAll('[contenteditable="true"]')).filter(isVisible);
                    if (ceList.length) return ceList[0];
                    return null;
                }

                var composer = findComposer();
                if (!composer) { result.debug.push("未找到输入框"); return result; }

                var chatArea = null, composerRect = composer.getBoundingClientRect();
                var cur = composer, bestArea = 0;
                for (var up = 0; up < 12 && cur; up++) {
                    cur = cur.parentElement;
                    if (!cur || !isVisible(cur)) continue;
                    var r = cur.getBoundingClientRect();
                    if (r.left < 260) continue;
                    if (r.width < 320 || r.height < 300) continue;
                    var area = r.width * r.height;
                    if (area > bestArea) { bestArea = area; chatArea = cur; }
                }

                if (!chatArea) { result.debug.push("未找到聊天区域"); return result; }

                var chatRect = chatArea.getBoundingClientRect();
                var messageArea = null, bestMsgArea = 0;
                var divs = Array.from(chatArea.querySelectorAll('div'));
                for (var i = 0; i < divs.length; i++) {
                    var el = divs[i];
                    if (!isVisible(el)) continue;
                    if (el === composer || (el.contains && el.contains(composer))) continue;
                    var r = el.getBoundingClientRect();
                    if (!r) continue;
                    if (r.left < chatRect.left - 5) continue;
                    if (r.top < chatRect.top) continue;
                    if (r.bottom > composerRect.top + 5) continue;
                    if (r.height < 200 || r.width < 300) continue;
                    var st = window.getComputedStyle(el);
                    var oy = (st && st.overflowY) ? st.overflowY : '';
                    if (oy !== 'auto' && oy !== 'scroll' && oy !== 'overlay') continue;
                    var area = r.width * r.height;
                    if (area > bestMsgArea) { bestMsgArea = area; messageArea = el; }
                }
                if (!messageArea) messageArea = chatArea;

                var msgRect = messageArea.getBoundingClientRect();
                var centerX = msgRect.left + msgRect.width * 0.5;
                var timeRegex = /^(星期[一二三四五六日](\s*\d{1,2}:\d{2})?|\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})$/;
                var systemRegex = /(用户超时未回|客服已结束|你已超.*未回复|会话已结束|两天内仍可再次联系|你撤回了一条消息|对方撤回了一条消息)/;

                var allTexts = [];
                var walker = document.createTreeWalker(messageArea, NodeFilter.SHOW_TEXT, null, false);
                var textNode;
                while (textNode = walker.nextNode()) {
                    var parent = textNode.parentElement;
                    if (!parent || !isVisible(parent)) continue;
                    var text = textNode.textContent.trim();
                    if (!text || text.length === 0) continue;
                    text = text.replace(/^星期[一二三四五六日]\s*\d{1,2}:\d{2}\s*/,'');
                    text = text.replace(/^\d{4}-\d{2}-\d{2}\s*\d{1,2}:\d{2}\s*/,'');
                    if (timeRegex.test(text)) continue;
                    if (systemRegex.test(text)) continue;
                    var r = parent.getBoundingClientRect();
                    if (r.top < msgRect.top + 20) continue;
                    if (r.width < 10 || r.height < 10) continue;
                    var isUser = r.right < centerX - 30;
                    var isReply = r.left > centerX + 30;
                    allTexts.push({ text: text, isUser: isUser, isReply: isReply, top: r.top, left: r.left, right: r.right, width: r.width });
                }

                result.debug.push("原始文本节点: " + allTexts.length);

                var mergedMessages = [];
                var currentMsg = null;
                allTexts.sort(function(a, b) { return a.top - b.top; });

                for (var j = 0; j < allTexts.length; j++) {
                    var item = allTexts[j];
                    if (/^\d+$/.test(item.text) && item.text.length < 5) continue;
                    if (!currentMsg) { currentMsg = item; }
                    else {
                        var sameSide = (item.isUser && currentMsg.isUser) || (item.isReply && currentMsg.isReply);
                        var closeVertical = Math.abs(item.top - currentMsg.top) < 25;
                        var closeHorizontal = Math.abs(item.left - currentMsg.left) < 100;
                        if (sameSide && closeVertical && closeHorizontal) {
                            currentMsg.text += " " + item.text;
                            currentMsg.width = Math.max(currentMsg.width, item.width);
                        } else {
                            mergedMessages.push(currentMsg);
                            currentMsg = item;
                        }
                    }
                }
                if (currentMsg) mergedMessages.push(currentMsg);
                result.debug.push("合并后消息: " + mergedMessages.length);

                for (var k = 0; k < mergedMessages.length; k++) {
                    var msg = mergedMessages[k];
                    if (msg.text.length < 2 || msg.text.length > 500) continue;
                    if (systemRegex.test(msg.text)) continue;
                    result.messages.push({ text: msg.text, isUser: msg.isUser, isReply: msg.isReply, position: {top: msg.top, left: msg.left} });
                    if (msg.isUser) result.userMessages.push(msg);
                    else if (msg.isReply) result.replyMessages.push(msg);
                }
                result.messages.sort(function(a, b) { return a.position.top - b.position.top; });
                return result;
            }

            var userResult = getCurrentChatUser();
            var msgResult = getChatMessages();

            return {
                timestamp: new Date().toISOString(),
                user: userResult,
                messages: msgResult
            };
        })()
        """
        self.run_javascript(script, callback)

    def send_message(self, text: str, callback: Callable = None):
        """发送消息

        Args:
            text: 要发送的文本
            callback: 回调函数
        """
        # 转义文本中的特殊字符
        escaped_text = json.dumps(text)

        script = f"""
        (function() {{
            function isVisible(el) {{
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect || rect.width < 5 || rect.height < 5) return false;
                return true;
            }}

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

            function dispatchEnter(target) {{
                if (!target) return false;
                try {{
                    var enterEvent = new KeyboardEvent('keydown', {{
                        bubbles: true,
                        cancelable: true,
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13
                    }});
                    target.dispatchEvent(enterEvent);
                    return true;
                }} catch (e) {{
                    return false;
                }}
            }}

            var composer = findComposer();
            if (!composer) {{
                return {{ success: false, error: '未找到输入框' }};
            }}

            var success = setComposerValue(composer, {escaped_text});
            if (!success) {{
                return {{ success: false, error: '设置文本失败' }};
            }}

            setTimeout(function() {{
                dispatchEnter(composer);
            }}, 200);

            return {{ success: true, composer_found: true }};
        }})()
        """
        if callback:
            self.run_javascript(script, callback)
        else:
            self.page.runJavaScript(script)

    def get_page_url(self) -> str:
        """获取当前页面URL"""
        return self.web_view.url().toString()
