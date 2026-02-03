# 迁移指南

## 从 v1.x 迁移到 v2.0

### 文件结构变化

| 旧版本 | 新版本 | 说明 |
|--------|--------|------|
| `hari_main.py` | `main.py` + `src/` | 单文件拆分为模块化结构 |
| `model_settings.json` | `config/model_settings.json` | 配置文件移到 config 目录 |
| `knowledge_base.json` | `config/knowledge_base.json` | 知识库移到 config 目录 |

### 配置迁移

配置文件格式保持不变，只需移动到新位置：

```bash
# 手动移动
mv model_settings.json config/
mv knowledge_base.json config/  # 如果存在
```

### 启动方式变化

**旧版本:**
```bash
python hari_main.py
```

**新版本:**
```bash
python main.py
```

### 功能变化

#### 新增功能

1. **会话管理**: 新增 SessionManager 管理用户会话状态
2. **回复协调**: ReplyCoordinator 协调知识库和 AI 回复
3. **模块化配置**: ConfigManager 统一管理配置
4. **服务分层**: 清晰的 Service 层封装

#### 保持不变的功能

- 多模型支持 (ChatGPT, Gemini, 阿里千问, DeepSeek, 豆包, Kimi)
- 知识库管理
- 浏览器自动化
- JavaScript 注入抓取消息
- 自动回复流程

### 扩展开发

#### 添加新模型

1. 在 `src/data/config_manager.py` 的 `DEFAULT_MODEL_SETTINGS` 中添加模型配置
2. 在 `src/services/llm_service.py` 的 `LLMWorker._call_api` 中添加调用逻辑
3. 在 `src/ui/model_config_tab.py` 的模型列表中添加新模型名称

#### 修改系统提示词

编辑 `src/utils/constants.py` 中的 `SYSTEM_PROMPT` 变量。

#### 修改轮询间隔

编辑 `src/utils/constants.py` 中的 `POLL_INTERVAL` 变量（单位：毫秒）。

### 常见问题

**Q: 旧版本的知识库数据如何迁移？**

A: 直接将 `knowledge_base.json` 复制到 `config/` 目录即可，格式完全兼容。

**Q: 配置文件自动迁移吗？**

A: 首次运行时会自动创建默认配置，原有的 `model_settings.json` 需要手动移动到 `config/` 目录。

**Q: 可以同时运行新旧版本吗？**

A: 不建议，因为会占用相同的浏览器资源。请先停止旧版本再运行新版本。

**Q: 如何恢复 v1.x 版本？**

A: 备份的 `hari_main.py` 文件可以直接运行，但建议完全迁移到新版本以获得更好的维护性。

### 回滚方案

如果需要回滚到 v1.x：

```bash
# 从备份恢复
mv hari_main.py.bak hari_main.py

# 运行旧版本
python hari_main.py
```

**注意**: v1.x 版本将不再维护，建议尽早完成迁移。
