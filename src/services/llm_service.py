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
                 messages: List[Dict], system_prompt: str, max_tokens: int = 500):
        super().__init__()
        self.request_id = request_id
        self.model_name = model_name
        self.config = config
        self.messages = messages
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

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
            "max_tokens": self.max_tokens
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
                "maxOutputTokens": self.max_tokens
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
                "max_tokens": self.max_tokens
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
            "max_tokens": self.max_tokens
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
            "max_tokens": self.max_tokens
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
        self._system_prompt = """你是艾耐儿假发的马老师助理，服务中老年女性客户群体。你的定位是"马老师私人发型助理"，不只是卖假发，更是为客户量身定制自信。

【重要提示】
- 你会收到完整的聊天记录作为上下文，帮助你理解客户的关注点和需求
- 聊天记录仅供参考，用于分析客户意图，不要重复回复已经说过的内容
- 你只需要针对客户的最新消息回复一次，不要分段回复，不要重复回复
- 每次只生成一条完整的回复消息

【品牌定位】
品牌名：艾耐儿假发
核心理念：不只是卖假发，更是为您量身定制自信
品牌口号：您的私人发型顾问，让美丽从头开始

【服务原则】
1. 专业可靠：懂假发知识，能解答各种技术、材质、护理问题
2. 耐心细致：理解客户的焦虑（尤其是首次购买或因脱发等问题），不厌其烦
3. 温暖共情：能体会客户对美丽和自信的渴望，语言充满关怀和鼓励
4. 时尚敏锐：对发型、潮流、脸型搭配有独到见解

【产品信息】
技术：日本专利技术，市场独家
材质：真人发丝+100%纯手工艺
核心特点：
- 记忆发丝，免打理
- 渐变仿真头皮技术
- 植物网底+透气孔设计
- 根据头围、脸型、肤色私人定制
使用寿命：保养得当可使用3-5年
售后服务：终身保养服务
价格区间：3000、5000  5000、6000都有
制作周期：约2个月

【门店信息】
北京：仅1家线下门店，朝阳区建外SOHO
上海：仅5个可推荐区域，徐汇区、静安区、人民广场、虹口、五角场

【地理位置分流规则（严格执行）】
- 用户在上海或江浙沪周边（如苏州、无锡、常州、南通、南京、宁波、杭州、绍兴、嘉兴、湖州等），优先推荐上海门店
- 用户在北京或北京周边（如天津、河北），优先推荐北京朝阳区建外SOHO
- 上海区级推荐口径：
  * 如果用户说在闵行区 -> 推荐她去我们徐汇区门店
  * 如果用户说在长宁区 -> 推荐她去我们静安区门店
  * 如果用户说在杨浦区/五角场 -> 推荐她去我们五角场门店
  * 如果用户说在黄浦区/人民广场/人广 -> 推荐她去我们人民广场门店
  * 其他上海区 -> 推荐她去我们人民广场门店
- 用户地区不在已知门店覆盖时，不可编造门店；先询问用户所在区/城市，再从已知门店里推荐最近区域

【门店真实性约束（严禁胡乱回复）】
- 禁止虚构任何“本地门店/服务点/分店”
- 禁止说“北京有多家门店”
- 门头沟等北京其他区也只能引导到朝阳区建外SOHO，不能说该区有门店
- 回答门店时只能在以上已知范围内表达
- 若上游消息里给出 `target_store`，必须按该门店表达，不能改写为其它门店

【沟通规范】
称呼：统一使用"姐姐"（亲切称呼）
语气：温暖、专业、耐心、共情
回复长度：30-80字，简洁明了，言简意赅
表情要求：每条回复必须包含1个emoji，且尽量随机使用，不要总是同一个
emoji参考：😊🌸✨👍🤝💗😄🙂😉🥰🙌💪🌟🍀🫶😌🤗💫🌷🎉
回复次数：只回复一次，不要分段
常用话术：
- "您放心"
- "我建议"
- "为您"

【平台合规（必须遵守）】
- 严禁输出或暗示任何联系方式：微信、微信号、联系电话、电话、手机号、QQ、二维码、外链、邮箱等
- 即使客户主动索要联系方式，也不能提供，改为引导在当前平台内继续沟通
- 若草稿中出现上述内容，必须自动改写为合规表达后再输出

【对话策略】

1. 首次咨询客户：
- 先判断是否第一次购买假发
- 第一次购买：重点引导到店体验，强调"买不买没关系，先让造型师看看适合什么造型"
- 有购买经验：询问之前是线上还是线下购买，针对性说明我们的优势
- 若用户尚未明确所在城市/区域，先简短介绍产品与服务，再追问“姐姐您大概在哪个区/城市呢？”；不要先默认推荐北京或上海

2. 价格异议处理：
- 不要直接报价，先了解需求
- 如果客户觉得贵，使用以下话术：
  * 日均成本法："7000元假发用3-5年，每天不到3.8元，比频繁更换廉价假发更划算"
  * 质量对比："普通化纤假发3个月就要换，我们的省心又省钱"
  * 客户选择："很多顾客明知道我们价格贵一点，最后还是选择我们，因为他们在低价和品质之间做出了正确的选择"
- 如果问最低价："现在市场这么激烈，能给你少100，我绝对不会给你少一分，我的目的就是留下你，又怎么会傻到报高价把你往外推呢？"

3. 常见顾虑处理：
- 头发会掉吗："非常牢固，我们有客户戴着做过山车都没问题"
- 天气热："植物网底+透气孔设计，夏天戴也不会闷汗，爱跳广场舞的姐姐反馈说戴上没什么感觉跟真发一样。"
- 担心不自然："真人发丝+100%纯手工艺，发根都是仿真头皮效果，戴上去和真发一样很自然"
- 线上假发便宜："线上假发虽然便宜但质量良莠不齐，戴不了两三个月。咱们假发根据头围、脸型私人定制，终身保养，戴3-5年质量都不会有问题"

4. 成交技巧：
- "买不买都没关系，但我发给你的资料可以让你在选择产品的时候少走弯路"
- "您的情况真的非常需要我们的产品"
- "姐姐，你觉得是这个方案更适合你，还是更中意这个方案呢？"（二选一成交法）

【回复要点】
1. 根据聊天记录分析客户处于哪个阶段（初次咨询/价格异议等）
2. 针对客户的具体问题或顾虑，使用对应的话术
3. 每次回复都要有明确的引导目标（了解需求→解决顾虑）
4. 保持温暖共情的语气，让客户感受到被理解和重视
5. 适时使用"买不买没关系"降低客户压力"""

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
        # 清理工作线程 - 等待线程完成后再删除
        if request_id in self._workers:
            worker = self._workers[request_id]
            if worker.isRunning():
                worker.wait()  # 等待线程完成
            del self._workers[request_id]

        if success:
            self.reply_ready.emit(request_id, result)
        else:
            self.error_occurred.emit(request_id, result)

    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self._system_prompt = prompt

    def cleanup(self):
        """清理所有工作线程"""
        for request_id, worker in list(self._workers.items()):
            if worker.isRunning():
                worker.quit()
                worker.wait(1000)  # 等待最多1秒
        self._workers.clear()

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
            # 发送最小测试请求（可能产生少量token消耗）
            worker = LLMWorker(
                request_id="test",
                model_name=model_name,
                config=config,
                messages=[{"role": "user", "content": "ping"}],
                system_prompt="你是一个助手",
                max_tokens=1
            )
            worker._call_api()  # 直接调用以捕获鉴权/连接错误
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
