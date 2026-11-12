# 角色图像实验

产物只写入本目录 `output/`，不调用剧本刷业务接口、不修改数据库，也不保存 API Key。

## 多参考图 → 角色正面立绘（推荐）

以 1–3 张参考图和文字设定生成一张可复用于后续剧情图的单角色正面全身立绘。默认使用百炼 `wan2.7-image`：更适合高精度图像编辑与角色一致性控制；实验仍将参考图限制在更易控的一至三张。需要对比时可额外传入 `--model wan2.6-image`。

```bash
backend/.venv/bin/python experiments/role-image-lab/role_image_experiment.py \
  --provider dashscope \
  --portrait-source /绝对路径/角色正面图.png /绝对路径/角色服装图.png \
  --portrait-prompt "少年炼药师，黑色短发，清秀坚毅；穿深蓝色古风劲装、银色护腕与黑色腰带；中国玄幻动漫赛璐璐画风" \
  --dry-run
```

去掉 `--dry-run` 即会调用模型。每次会在 `output/portrait-<时间>/` 保存：

- `front-portrait.png`：生成的单角色正面图；
- `request.json`：不含 Key 的请求记录；
- `result.json`：是否实际检测到 PNG Alpha 透明通道。

提示词会明确要求“人物与服装、完整全身、正面、透明背景、无场景”。但 `wan2.6-image` 的公开 API 文档未提供透明通道参数，因此模型可能仍返回白底或纯色底 PNG；脚本不会把这种结果误报成透明。它仍能直接作为后续剧情场景的角色参考；若要叠加到桌宠或网页中，需在下一步增加抠图实验。

## 百炼：低成本首测

```bash
export IMAGE_LAB_DASHSCOPE_API_KEY="你的百炼 Key"
backend/.venv/bin/python experiments/role-image-lab/role_image_experiment.py --provider dashscope --dry-run
backend/.venv/bin/python experiments/role-image-lab/role_image_experiment.py --provider dashscope --model wan2.2-t2i-flash
```

如账号采用业务空间专属域名，可额外传入完整的百炼提交地址：

```bash
export IMAGE_LAB_DASHSCOPE_BASE_URL="https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
```

## Gemini：后续对比

```bash
export IMAGE_LAB_GEMINI_API_KEY="你的 Gemini Key"
backend/.venv/bin/python experiments/role-image-lab/role_image_experiment.py --provider gemini --model gemini-3.1-flash-image
```

可以替换 `character.example.json`，或传入 `--character /path/to/character.json`。每次运行会在 `output/<时间>/` 保存主立绘与脱敏请求记录（不含 Key）。

## 正视主立绘 → 开心状态（百炼图像编辑）

图像编辑会将本地正视图以 Base64 作为参考图发送给 `wan2.6-image`，只生成一张结果图。默认要求保持脸、服装、构图和背景，仅改为自然开心的神情：

```bash
export IMAGE_LAB_DASHSCOPE_API_KEY="你的百炼 Key"
backend/.venv/bin/python experiments/role-image-lab/role_image_experiment.py \
  --provider dashscope \
  --edit-source experiments/role-image-lab/output/20261109-151317/front.png
```

先验证请求但不调用模型：

```bash
backend/.venv/bin/python experiments/role-image-lab/role_image_experiment.py \
  --provider dashscope \
  --edit-source experiments/role-image-lab/output/20261109-151317/front.png \
  --dry-run
```
