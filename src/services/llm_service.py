"""
LLM服务模块
负责与各大语言模型API的交互
"""

import json
import os
import ssl
import urllib.request
import urllib.error
from typing import Optional, List, Dict
from PySide6.QtCore import QObject, Signal, QThread


class LLMWorker(QThread):
    """LLM请求工作线程"""

    result_ready = Signal(str, bool, str)  # (request_id, success, result/error)

    def __init__(self, request_id: str, model_name: str, config: dict,
                 messages: List[Dict], system_prompt: str):
        super().__init__()
        self.request_id = request_id
        self.model_name = model_name
        self.config = config
        self.messages = messages
        self.system_prompt = system_prompt

    def run(self):
        """执行API调用"""
        try:
            result = self._call_api()
            self.result_ready.emit(self.request_id, True, result)
        except Exception as e:
            self.result_ready.emit(self.request_id, False, str(e))

    def _call_api(self) -> str:
        """调用具体的API"""
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "")
        model = self.config.get("model", "")

        if not api_key:
            raise ValueError("API密钥未配置")

        # 根据不同模型调用不同API
        if self.model_name == "ChatGPT":
            return self._call_openai(api_key, base_url, model)
        elif self.model_name == "Gemini":
            return self._call_gemini(api_key, base_url, model)
        elif self.model_name == "阿里千问":
            return self._call_qwen(api_key, base_url, model)
        elif self.model_name == "DeepSeek":
            return self._call_deepseek(api_key, base_url, model)
        elif self.model_name == "kimi":
            return self._call_kimi(api_key, base_url, model)
        else:
            raise ValueError(f"不支持的模型: {self.model_name}")

    def _call_openai(self, api_key: str, base_url: str, model: str) -> str:
        """调用OpenAI API"""
        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *self.messages
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        # 创建SSL上下文，跳过证书验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data['choices'][0]['message']['content']

    def _call_gemini(self, api_key: str, base_url: str, model: str) -> str:
        """调用Gemini API"""
        url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"

        # 构建对话历史
        contents = []
        for msg in self.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 500
            }
        }

        headers = {"Content-Type": "application/json"}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        # 创建SSL上下文，跳过证书验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            if 'candidates' in data and data['candidates']:
                return data['candidates'][0]['content']['parts'][0]['text']
            raise ValueError("Gemini API返回格式错误")

    def _call_qwen(self, api_key: str, base_url: str, model: str) -> str:
        """调用阿里千问API"""
        url = f"{base_url}/api/v1/services/aigc/text-generation/generation"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # 构建提示词
        prompt = self.system_prompt + "\n\n"
        for msg in self.messages:
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

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        # 创建SSL上下文，跳过证书验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data['output']['text']

    def _call_deepseek(self, api_key: str, base_url: str, model: str) -> str:
        """调用DeepSeek API"""
        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *self.messages
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        # 创建SSL上下文，跳过证书验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data['choices'][0]['message']['content']

    def _call_kimi(self, api_key: str, base_url: str, model: str) -> str:
        """调用Kimi API"""
        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *self.messages
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        # 创建SSL上下文，跳过证书验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data['choices'][0]['message']['content']


class LLMService(QObject):
    """LLM服务，管理大语言模型的调用"""

    reply_ready = Signal(str, str)      # (request_id, reply_text)
    error_occurred = Signal(str, str)   # (request_id, error_message)

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self._workers: Dict[str, LLMWorker] = {}
        self._system_prompt = """你是假发行业资深顾问，专门服务高端假发定制客户，绝大多数客户为中老年群体。你的沟通风格要像一位经验丰富、耐心亲切的造型顾问，态度温和、尊重、专业，具备极强的销售敏感度。

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

    def generate_reply(self, user_message: str, conversation_history: List[Dict] = None,
                       request_id: str = None) -> str:
        """生成回复

        Args:
            user_message: 用户最新消息
            conversation_history: 对话历史
            request_id: 请求ID（用于追踪）

        Returns:
            request_id
        """
        import uuid
        request_id = request_id or str(uuid.uuid4())

        # 获取当前模型配置
        model_name = self.config_manager.get_current_model()
        model_config = self.config_manager.get_model_config(model_name)

        if not model_config.get("api_key"):
            self.error_occurred.emit(request_id, f"{model_name} 的API密钥未配置")
            return request_id

        # 构建消息列表
        messages = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        # 创建工作线程
        worker = LLMWorker(
            request_id=request_id,
            model_name=model_name,
            config=model_config,
            messages=messages,
            system_prompt=self._system_prompt
        )

        worker.result_ready.connect(self._on_worker_result)
        self._workers[request_id] = worker

        worker.start()
        return request_id

    def _on_worker_result(self, request_id: str, success: bool, result: str):
        """处理工作线程结果"""
        # 清理工作线程
        if request_id in self._workers:
            del self._workers[request_id]

        if success:
            self.reply_ready.emit(request_id, result)
        else:
            self.error_occurred.emit(request_id, result)

    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self._system_prompt = prompt

    def get_system_prompt(self) -> str:
        """获取当前系统提示词"""
        return self._system_prompt

    def test_connection(self, model_name: str = None) -> tuple:
        """测试模型连接

        Returns:
            (success: bool, message: str)
        """
        model_name = model_name or self.config_manager.get_current_model()
        config = self.config_manager.get_model_config(model_name)

        if not config.get("api_key"):
            return False, "API密钥未配置"

        if not config.get("base_url"):
            return False, "API地址未配置"

        try:
            # 发送简单测试请求
            worker = LLMWorker(
                request_id="test",
                model_name=model_name,
                config=config,
                messages=[{"role": "user", "content": "你好"}],
                system_prompt="你是一个助手"
            )
            worker.run()  # 同步执行
            return True, "连接成功"
        except Exception as e:
            return False, f"连接失败: {str(e)}"

    def cancel_request(self, request_id: str):
        """取消请求"""
        if request_id in self._workers:
            worker = self._workers[request_id]
            if worker.isRunning():
                worker.terminate()
            del self._workers[request_id]
