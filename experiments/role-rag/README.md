# 角色知识 RAG 实验

该实验只读取桌面端本地资料库中的 `source_segments`，并在 `output/` 下建立索引；不会修改业务数据库、体验副本或角色私聊链路。

## 1. 配置 Embedding API

使用 OpenAI 兼容的 Embedding 接口。以下以硅基流动为例，模型名称请以账号模型广场当前可用项为准：

```bash
export RAG_EMBEDDING_BASE_URL="https://api.siliconflow.cn/v1"
export RAG_EMBEDDING_API_KEY="你的 API Key"
export RAG_EMBEDDING_MODEL="BAAI/bge-m3"
```

## 2. 建立《斗破苍穹》前 50 章索引

可先确认当前桌面资料库内可用的章节和切片数量（不调用 API）：

```bash
backend/.venv/bin/python experiments/role-rag/rag_experiment.py inspect --chapters 50
```

```bash
backend/.venv/bin/python experiments/role-rag/rag_experiment.py build --chapters 50
```

默认按 500 字切片、50 字重叠；输出为本地 `output/doupo-50.jsonl`。

## 3. 测试语义召回

```bash
backend/.venv/bin/python experiments/role-rag/rag_experiment.py search "萧炎为什么无法修炼"
backend/.venv/bin/python experiments/role-rag/rag_experiment.py search "戒指里有什么秘密"
```

每条结果会显示相似度、来源章节、片段序号和原文。实验通过后，再决定是否将其接入角色私聊。
