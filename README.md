# 微信小店自动化客服助手（PySide6 Agent 版）

这是一个基于 **PySide6 + QWebEngine** 的微信小店自动化客服系统。

核心主链路已统一为：

`自动扫描未读 -> 自动点击进入 -> 抓取聊天记录 -> Agent 决策 -> 发送文本/媒体 -> 记忆持久化`

## 核心配置文件

- 系统提示词：`docs/system_prompt_private_ai_customer_service.md`
- 客服回复规则：`docs/private_ai_customer_service_playbook.md`
- 知识库：`config/knowledge_base.json`
- 模型配置：`config/model_settings.json`
- 记忆文件：`config/agent_memory.json`（自动生成）

## Agent 策略

1. 地址问题优先走地址路由。
2. 非地址问题优先命中知识库；未命中再调用 LLM。
3. 媒体由 Agent 统一决策：地址图 / 联系方式图 / 延迟视频。
4. 会话记忆跨重启持久化，TTL 默认 30 天。

## 运行

```bash
pip install -r requirements.txt
python3 main.py
```

## UI 页面

- 微信小店
- 知识库管理
- 模型配置
- 图片与视频管理
- Agent 策略/状态

## 说明

- 已移除 Flask 测试架构。
- 已移除旧关键词并行触发链路，统一由 Agent 决策。
