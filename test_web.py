"""
LLM测试Web服务
独立运行的Flask应用，用于快速测试大模型回复逻辑
完整还原项目逻辑：模拟消息抓取 -> 知识库匹配 -> LLM回复
"""

import os
import sys
import uuid
import time
import json
import shutil
from pathlib import Path
from datetime import datetime
from threading import Event, Lock
from flask import Flask, request, jsonify, send_file, Response

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.config_manager import ConfigManager
from src.data.knowledge_repository import KnowledgeRepository
from src.services.knowledge_service import KnowledgeService
from src.services.llm_service import LLMService
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_manager import SessionManager

app = Flask(__name__)

# 全局服务实例
_config_manager = None
_knowledge_service = None
_knowledge_repository = None
_llm_service = None
_reply_coordinator = None
_session_manager = None

# 请求取消管理
_pending_requests = {}
_cancel_flag = Lock()

# 对话历史（内存中保存）
_conversation_history = {}

# 用户回复去重缓存
_user_reply_cache = {}  # {user_hash: set(reply_hash)}
_reply_cache_lock = Lock()

# 日志队列
_logs = []
_logs_lock = Lock()
MAX_LOGS = 500

# 上传图片存储目录
UPLOAD_DIR = PROJECT_ROOT / "test_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 图片目录（与主项目一致）
IMAGES_DIR = PROJECT_ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)


def add_log(message: str, level: str = "info"):
    """添加日志"""
    with _logs_lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        _logs.append({
            "time": timestamp,
            "message": message,
            "level": level
        })
        if len(_logs) > MAX_LOGS:
            _logs.pop(0)
    print(f"[{timestamp}] {message}")


def check_and_optimize_reply(user_name: str, user_message: str, original_reply: str) -> tuple:
    """检查回复是否重复，如果重复则让大模型优化
    
    Args:
        user_name: 用户名
        user_message: 用户消息
        original_reply: 原始回复
    
    Returns:
        (optimized_reply, is_duplicate, source)
    """
    import hashlib
    
    # 生成用户标识（基于用户名）
    user_hash = hashlib.md5(user_name.encode()).hexdigest()[:8]
    
    # 生成回复内容的哈希值
    reply_hash = hashlib.md5(original_reply.encode()).hexdigest()[:8]
    
    with _reply_cache_lock:
        # 初始化用户缓存
        if user_hash not in _user_reply_cache:
            _user_reply_cache[user_hash] = set()
        
        # 检查是否重复
        if reply_hash in _user_reply_cache[user_hash]:
            add_log(f"🔄 检测到重复回复，让大模型优化话术...")
            add_log(f"📝 原始回复: {original_reply[:50]}...")
            
            # 构造优化提示
            optimize_prompt = f"""请优化以下客服回复，要求：
1. 保持核心信息不变
2. 改变表达方式和句式结构
3. 避免与之前回复重复
4. 保持温暖专业的语气
5. 长度控制在30-80字

用户问题：{user_message}
原始回复：{original_reply}

请提供优化后的回复："""
            
            # 调用大模型优化
            optimized_reply, error = call_llm_directly(
                user_message=optimize_prompt,
                conversation_history=[]
            )
            
            if error:
                add_log(f"❌ 优化失败，使用原始回复: {error}", "error")
                return original_reply, True, "知识库(重复)"
            
            if optimized_reply and optimized_reply.strip():
                add_log(f"✨ 大模型优化成功: {optimized_reply[:50]}...")
                # 记录优化后的回复
                optimized_hash = hashlib.md5(optimized_reply.encode()).hexdigest()[:8]
                _user_reply_cache[user_hash].add(optimized_hash)
                return optimized_reply, True, "大模型(优化)"
            else:
                add_log(f"❌ 大模型返回空回复，使用原始回复", "error")
                return original_reply, True, "知识库(重复)"
        else:
            # 首次回复，记录到缓存
            _user_reply_cache[user_hash].add(reply_hash)
            add_log(f"🆕 首次回复，记录到缓存")
            return original_reply, False, "原始"


def call_llm_directly(user_message: str, conversation_history: list = None) -> tuple:
    """直接调用LLM API，不依赖Qt信号机制"""
    try:
        # 获取当前模型配置
        model_name = _config_manager.get_current_model()
        model_config = _config_manager.get_model_config(model_name)
        
        add_log(f"📡 使用模型: {model_name}")
        add_log(f"🔗 API地址: {model_config.get('base_url', '')}")
        
        api_key = model_config.get("api_key", "")
        base_url = model_config.get("base_url", "")
        model = model_config.get("model", "")
        
        if not api_key:
            return None, "API密钥未配置"
        
        # 构建消息列表
        messages = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})
        
        # 获取系统prompt
        system_prompt = _llm_service.get_system_prompt()
        add_log(f"📝 系统prompt长度: {len(system_prompt)}")
        
        # 根据模型调用不同API
        if model_name == "阿里千问":
            return _call_qwen_direct(api_key, base_url, model, messages, system_prompt)
        elif model_name == "DeepSeek":
            return _call_deepseek_direct(api_key, base_url, model, messages, system_prompt)
        elif model_name == "ChatGPT":
            return _call_openai_direct(api_key, base_url, model, messages, system_prompt)
        else:
            return None, f"不支持的模型: {model_name}"
            
    except Exception as e:
        add_log(f"❌ LLM调用异常: {str(e)}", "error")
        return None, f"LLM调用异常: {str(e)}"


def _call_qwen_direct(api_key: str, base_url: str, model: str, messages: list, system_prompt: str) -> tuple:
    """直接调用阿里千问API"""
    import json
    import ssl
    import urllib.request
    
    try:
        url = f"{base_url}/api/v1/services/aigc/text-generation/generation"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 构建提示词（千问格式）
        prompt = system_prompt + "\n\n"
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            prompt += f"{role}: {msg['content']}\n"
        prompt += "助手: "
        
        payload = {
            "model": model,
            "input": {"prompt": prompt},
            "parameters": {
                "temperature": 0.7,
                "max_tokens": 500
            }
        }
        
        add_log(f"📤 发送请求到千问API...")
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        # 创建SSL上下文
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if 'output' in data and 'text' in data['output']:
                result = data['output']['text']
                add_log(f"✅ 千问API调用成功")
                return result, None
            else:
                error_msg = f"千问API返回格式错误: {data}"
                add_log(f"❌ {error_msg}", "error")
                return None, error_msg
                
    except urllib.error.HTTPError as e:
        error_msg = f"千问API HTTP错误 {e.code}: {e.reason}"
        add_log(f"❌ {error_msg}", "error")
        return None, error_msg
    except Exception as e:
        error_msg = f"千问API调用异常: {str(e)}"
        add_log(f"❌ {error_msg}", "error")
        return None, error_msg


def _call_deepseek_direct(api_key: str, base_url: str, model: str, messages: list, system_prompt: str) -> tuple:
    """直接调用DeepSeek API"""
    import json
    import ssl
    import urllib.request
    
    try:
        url = f"{base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        add_log(f"📤 发送请求到DeepSeek API...")
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        # 创建SSL上下文
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if 'choices' in data and len(data['choices']) > 0:
                result = data['choices'][0]['message']['content']
                add_log(f"✅ DeepSeek API调用成功")
                return result, None
            else:
                error_msg = f"DeepSeek API返回格式错误: {data}"
                add_log(f"❌ {error_msg}", "error")
                return None, error_msg
                
    except urllib.error.HTTPError as e:
        error_msg = f"DeepSeek API HTTP错误 {e.code}: {e.reason}"
        add_log(f"❌ {error_msg}", "error")
        return None, error_msg
    except Exception as e:
        error_msg = f"DeepSeek API调用异常: {str(e)}"
        add_log(f"❌ {error_msg}", "error")
        return None, error_msg


def _call_openai_direct(api_key: str, base_url: str, model: str, messages: list, system_prompt: str) -> tuple:
    """直接调用OpenAI API"""
    import json
    import ssl
    import urllib.request
    
    try:
        url = f"{base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        add_log(f"📤 发送请求到OpenAI API...")
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        # 创建SSL上下文
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if 'choices' in data and len(data['choices']) > 0:
                result = data['choices'][0]['message']['content']
                add_log(f"✅ OpenAI API调用成功")
                return result, None
            else:
                error_msg = f"OpenAI API返回格式错误: {data}"
                add_log(f"❌ {error_msg}", "error")
                return None, error_msg
                
    except urllib.error.HTTPError as e:
        error_msg = f"OpenAI API HTTP错误 {e.code}: {e.reason}"
        add_log(f"❌ {error_msg}", "error")
        return None, error_msg
    except Exception as e:
        error_msg = f"OpenAI API调用异常: {str(e)}"
        add_log(f"❌ {error_msg}", "error")
        return None, error_msg


def init_services():
    """初始化所有服务"""
    global _config_manager, _knowledge_service, _knowledge_repository, _llm_service, _reply_coordinator, _session_manager
    
    # 配置文件路径 - 使用正确的文件名
    config_file = PROJECT_ROOT / "config" / "model_settings.json"
    knowledge_file = PROJECT_ROOT / "config" / "knowledge_base.json"
    
    # 初始化配置管理器
    _config_manager = ConfigManager(config_file=config_file, env_file=None)
    
    # 初始化知识库
    _knowledge_repository = KnowledgeRepository(knowledge_file)
    _knowledge_service = KnowledgeService(_knowledge_repository)
    
    # 初始化会话管理器
    _session_manager = SessionManager()
    
    # 初始化LLM服务
    _llm_service = LLMService(_config_manager)
    
    # 初始化回复协调器（与原项目保持一致）
    _reply_coordinator = ReplyCoordinator(
        knowledge_service=_knowledge_service,
        llm_service=_llm_service,
        session_manager=_session_manager
    )
    
    add_log("✅ 服务初始化完成", "success")
    add_log(f"📋 当前模型: {_config_manager.get_current_model()}")
    add_log(f"📚 知识库条目: {_knowledge_service.get_count()}")


@app.route('/')
def index():
    """返回测试页面"""
    return send_file(PROJECT_ROOT / "test_chat.html")


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """获取日志"""
    since = int(request.args.get("since", 0))
    with _logs_lock:
        return jsonify({"logs": _logs[since:]})


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    return jsonify({
        "current_model": _config_manager.get_current_model(),
        "available_models": ["阿里千问", "DeepSeek", "ChatGPT", "Gemini", "kimi"],
        "knowledge_count": _knowledge_service.get_count(),
        "system_prompt": _llm_service.get_system_prompt()
    })


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    data = request.json
    
    if "current_model" in data:
        model_name = data["current_model"]
        _config_manager.set_current_model(model_name)
        add_log(f"🔄 切换模型: {model_name}")
    
    if "system_prompt" in data:
        _llm_service.set_system_prompt(data["system_prompt"])
        add_log("📝 更新系统提示词")
    
    return jsonify({"success": True})


@app.route('/api/chat', methods=['POST'])
def chat():
    """发送消息并获取回复 - 完全还原原项目逻辑"""
    data = request.json
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    use_knowledge = data.get("use_knowledge", True)
    user_name = data.get("user_name", "测试用户")
    
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400
    
    start_time = time.time()
    
    # 模拟消息抓取日志
    add_log("=" * 50)
    add_log(f"📋 用户聊天记录：{user_name}")
    add_log("=" * 50)
    
    # 获取或创建会话（使用原项目的会话管理器）
    session = _session_manager.get_or_create_session(session_id, user_name)
    
    # 记录用户消息到会话
    _session_manager.add_message(session_id, user_message, is_user=True)
    
    # 显示历史消息
    history = session.get_conversation_history(6)  # 最近6轮对话
    for msg in history:
        if msg.get("is_user"):
            add_log(f"❤️‍🔥 用户（{user_name}）：{msg['content'][:50]}...")
        else:
            add_log(f"🤖 客服（我）：{msg['content'][:50]}...")
    
    # 显示当前消息
    add_log(f"❤️‍🔥 用户（{user_name}）：{user_message}")
    add_log("=" * 50)
    add_log(f"💬 [{user_name}]: {user_message[:50]}...")
    
    # 使用回复协调器处理消息（与原项目完全一致）
    reply_text = None
    error_msg = None
    reply_event = Event()
    request_id = None
    
    def on_reply(success: bool, reply: str):
        nonlocal reply_text, error_msg
        if success and reply:
            reply_text = reply
        else:
            error_msg = reply or "生成回复失败"
        reply_event.set()
        # 清理待处理请求
        with _cancel_flag:
            if request_id in _pending_requests:
                del _pending_requests[request_id]
    
    # 生成唯一请求ID
    import uuid
    request_id = str(uuid.uuid4())
    
    # 记录待处理请求
    with _cancel_flag:
        _pending_requests[request_id] = {
            "session_id": session_id,
            "user_message": user_message,
            "reply_event": reply_event
        }
    
    try:
        # 首先测试知识库匹配
        add_log(f"🔍 正在匹配知识库...")
        kb_answer = _knowledge_service.find_answer(user_message, threshold=0.6)
        if kb_answer:
            add_log(f"✅ 知识库匹配成功，原始回复: {kb_answer[:50]}...")
            
            # 检查去重并优化
            final_reply, is_duplicate, reply_source = check_and_optimize_reply(
                user_name, user_message, kb_answer
            )
            
            reply_text = final_reply
            actual_source = reply_source
        else:
            add_log(f"❌ 知识库未匹配，调用大模型...")
            
            # 直接调用LLM API
            reply_text, error_msg = call_llm_directly(
                user_message=user_message,
                conversation_history=history[-6:] if history else []
            )
            
            if error_msg:
                add_log(f"❌ 大模型调用失败: {error_msg}", "error")
                return jsonify({"error": error_msg}), 500
            
            if not reply_text:
                add_log(f"❌ 大模型返回空回复", "error")
                return jsonify({"error": "大模型返回空回复"}), 500
            
            add_log(f"🤖 大模型回复: {reply_text[:50]}...")
            actual_source = "大模型"
        
        # 记录到本地历史（用于界面显示）
        if session_id not in _conversation_history:
            _conversation_history[session_id] = []
        
        _conversation_history[session_id].append({"role": "user", "content": user_message})
        _conversation_history[session_id].append({"role": "assistant", "content": reply_text})
        
        # 限制历史长度
        if len(_conversation_history[session_id]) > 20:
            _conversation_history[session_id] = _conversation_history[session_id][-20:]
        
        add_log(f"✅ 回复已发送 (来源: {actual_source}): {reply_text[:50]}...")
        
        # 确定返回给前端的source类型
        if actual_source == "大模型(优化)":
            source_type = "llm"
        elif actual_source == "知识库(重复)":
            source_type = "knowledge"
        elif actual_source == "原始":
            source_type = "knowledge"
        else:
            source_type = actual_source
        
        return jsonify({
            "reply": reply_text,
            "source": source_type,
            "actual_source": actual_source,  # 添加实际来源信息
            "model": _config_manager.get_current_model(),
            "time_ms": int((time.time() - start_time) * 1000)
        })
    
    except Exception as e:
        add_log(f"❌ 处理消息异常: {str(e)}", "error")
        return jsonify({"error": f"处理异常: {str(e)}"}), 500
    finally:
        # 清理待处理请求
        with _cancel_flag:
            if request_id and request_id in _pending_requests:
                del _pending_requests[request_id]


@app.route('/api/knowledge', methods=['GET'])
def get_knowledge():
    """获取知识库数据"""
    try:
        items = _knowledge_repository.get_all()
        # 转换为字典格式
        items_dict = [item.to_dict() for item in items]
        return jsonify({"items": items_dict})
    except Exception as e:
        add_log(f"❌ 获取知识库失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge', methods=['POST'])
def add_knowledge():
    """添加知识库项"""
    try:
        data = request.json
        
        # 创建新知识库项
        item = _knowledge_repository.add(
            question=data['question'],
            answer=data['answer'],
            category=data.get('category', ''),
            tags=data.get('tags', [])
        )
        
        # 保存到文件
        _knowledge_repository.save()
        
        add_log(f"✅ 添加知识库项: {data['question'][:30]}...", "success")
        return jsonify({"success": True, "item": item.to_dict()})
        
    except Exception as e:
        add_log(f"❌ 添加知识库项失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge/<item_id>', methods=['PUT'])
def update_knowledge(item_id):
    """更新知识库项"""
    try:
        data = request.json
        
        # 获取现有项
        item = _knowledge_repository.get_item(item_id)
        if not item:
            return jsonify({"error": "知识库项不存在"}), 404
        
        # 更新项
        item.question = data['question']
        item.answer = data['answer']
        item.category = data.get('category', '')
        item.tags = data.get('tags', [])
        item.updated_at = datetime.now().isoformat()
        
        # 保存到文件
        _knowledge_repository.save()
        
        add_log(f"✅ 更新知识库项: {data['question'][:30]}...", "success")
        return jsonify({"success": True, "item": item.to_dict()})
        
    except Exception as e:
        add_log(f"❌ 更新知识库项失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge/<item_id>', methods=['DELETE'])
def delete_knowledge(item_id):
    """删除知识库项"""
    try:
        # 删除项
        success = _knowledge_repository.delete_item(item_id)
        if not success:
            return jsonify({"error": "知识库项不存在"}), 404
        
        # 保存到文件
        _knowledge_repository.save()
        
        add_log(f"✅ 删除知识库项: {item_id}", "success")
        return jsonify({"success": True})
        
    except Exception as e:
        add_log(f"❌ 删除知识库项失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge/export', methods=['GET'])
def export_knowledge():
    """导出知识库"""
    try:
        items = _knowledge_repository.get_all()
        
        # 创建导出数据
        export_data = {
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "items": [item.to_dict() for item in items]
        }
        
        add_log(f"✅ 导出知识库: {len(items)} 条记录", "success")
        
        # 返回JSON文件
        from flask import Response
        return Response(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=knowledge_base.json'}
        )
        
    except Exception as e:
        add_log(f"❌ 导出知识库失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/knowledge/import', methods=['POST'])
def import_knowledge():
    """导入知识库"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "没有文件"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "没有选择文件"}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({"error": "只支持JSON文件"}), 400
        
        # 读取文件内容
        content = file.read().decode('utf-8')
        data = json.loads(content)
        
        # 导入数据
        imported_count = 0
        if 'items' in data:
            for item_data in data['items']:
                _knowledge_repository.add(
                    question=item_data.get('question', ''),
                    answer=item_data.get('answer', ''),
                    category=item_data.get('category', ''),
                    tags=item_data.get('tags', [])
                )
                imported_count += 1
        
        # 保存到文件
        _knowledge_repository.save()
        
        add_log(f"✅ 导入知识库: {imported_count} 条记录", "success")
        return jsonify({"success": True, "imported": imported_count})
        
    except Exception as e:
        add_log(f"❌ 导入知识库失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/cancel', methods=['POST'])
def cancel_chat():
    """取消当前进行中的聊天请求"""
    try:
        # 取消所有待处理请求
        with _cancel_flag:
            if _pending_requests:
                add_log(f"🛑 正在取消 {len(_pending_requests)} 个待处理请求...")
                for req_id, req_info in list(_pending_requests.items()):
                    # 设置事件以解除等待
                    req_info["reply_event"].set()
                _pending_requests.clear()
                add_log("✅ 所有请求已取消")
                return jsonify({"success": True, "message": "请求已取消"})
            else:
                return jsonify({"success": True, "message": "没有待处理的请求"})
    except Exception as e:
        add_log(f"❌ 取消请求失败: {str(e)}", "error")
        return jsonify({"error": f"取消失败: {str(e)}"}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """获取对话历史"""
    session_id = request.args.get("session_id", "default")
    history = _conversation_history.get(session_id, [])
    return jsonify({"history": history})


@app.route('/api/cache/clear', methods=['POST'])
def clear_reply_cache():
    """清空回复缓存"""
    try:
        with _reply_cache_lock:
            _user_reply_cache.clear()
        add_log(f"🗑️ 回复缓存已清空")
        return jsonify({"success": True})
    except Exception as e:
        add_log(f"❌ 清空缓存失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        with _reply_cache_lock:
            stats = {
                "total_users": len(_user_reply_cache),
                "total_replies": sum(len(replies) for replies in _user_reply_cache.values()),
                "user_details": {}
            }
            
            for user_hash, replies in _user_reply_cache.items():
                stats["user_details"][user_hash] = {
                    "reply_count": len(replies),
                    "replies": list(replies)
                }
        
        return jsonify(stats)
    except Exception as e:
        add_log(f"❌ 获取缓存统计失败: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    """清空对话历史"""
    session_id = request.args.get("session_id", "default")
    if session_id in _conversation_history:
        _conversation_history[session_id] = []
    add_log("🗑️ 对话历史已清空")
    return jsonify({"success": True})


# ==================== 图片管理 API ====================

@app.route('/api/images', methods=['GET'])
def get_images():
    """获取图片列表"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    images = []
    
    for path in IMAGES_DIR.iterdir():
        if path.suffix.lower() in image_extensions:
            images.append({
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "url": f"/api/images/{path.name}"
            })
    
    return jsonify({"images": images, "total": len(images)})


@app.route('/api/images/<filename>')
def serve_image(filename):
    """提供图片文件"""
    filepath = IMAGES_DIR / filename
    if filepath.exists():
        return send_file(filepath)
    return jsonify({"error": "图片不存在"}), 404


@app.route('/api/images/upload', methods=['POST'])
def upload_image():
    """上传图片"""
    if 'image' not in request.files:
        return jsonify({"error": "没有图片文件"}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400
    
    # 生成文件名
    ext = Path(file.filename).suffix or '.jpg'
    filename = f"{uuid.uuid4().hex[:8]}{ext}"
    filepath = IMAGES_DIR / filename
    
    # 避免重名
    counter = 1
    while filepath.exists():
        filename = f"{uuid.uuid4().hex[:8]}_{counter}{ext}"
        filepath = IMAGES_DIR / filename
        counter += 1
    
    file.save(filepath)
    add_log(f"✅ 图片已上传: {filename}")
    
    return jsonify({
        "success": True,
        "filename": filename,
        "url": f"/api/images/{filename}"
    })


@app.route('/api/images/<filename>', methods=['DELETE'])
def delete_image(filename):
    """删除图片"""
    filepath = IMAGES_DIR / filename
    if filepath.exists():
        os.remove(filepath)
        add_log(f"🗑️ 图片已删除: {filename}")
        return jsonify({"success": True})
    return jsonify({"error": "图片不存在"}), 404


if __name__ == "__main__":
    print("=" * 50)
    print("LLM 测试 Web 服务")
    print("=" * 50)
    
    init_services()
    
    print()
    print("启动服务: http://localhost:5001")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
