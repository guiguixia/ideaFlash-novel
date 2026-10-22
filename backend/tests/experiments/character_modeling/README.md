# Character Modeling Experiments

真实 LLM 回归实验不进入普通 CI。使用本地只读 `novel.db` 的 novel 16，显式运行后记录人物证据和 token。

可显式运行以下只读入口：

```bash
cd Novel/backend
.venv/bin/python tests/experiments/character_modeling/evidence_timeline_experiment.py <novel_id> <人物名>
```

该入口只做本地检索/压缩检查。剧本人物抽取的正式入口位于“创建体验副本”任务，不再在整本剧本导入时执行 Top3 自动建模。

实验不得写入正式数据库；临时脚本和结果放 `/private/tmp`。
