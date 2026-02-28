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

## 快速联调（不走微信）

```bash
# 单条消息：只看策略命中和回复
python3 scripts/chat_simulator.py -m "不同价格有什么区别啊？" --no-llm

# 交互模式：连续多轮测试（输入 /exit 退出）
python3 scripts/chat_simulator.py --no-llm
```

- 输出会包含：`reply_source / intent / route_reason / rule_id / media_plan / reply_text`
- 还会输出本轮触发摘要：`视频=是/否 | 地址图片=是/否 | 联系方式图片=是/否`
- 默认使用独立调试数据目录：`data/simulator`，不会污染正式会话记忆
- 去掉 `--no-llm` 可切到真实模型回复（需已配置 API Key）

## UI 页面

- 微信小店
- 知识库管理
- 模型配置
- 图片与视频管理
- Agent 策略/状态

## 说明

- 已移除 Flask 测试架构。
- 已移除旧关键词并行触发链路，统一由 Agent 决策。
