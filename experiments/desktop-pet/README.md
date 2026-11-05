# 桌宠动效实验

这是一个独立静态页面，不引用业务前端、API 或 Electron 主进程。

```bash
python3 -m http.server 4177
```

打开 <http://127.0.0.1:4177/experiments/desktop-pet/>。页面使用用户提供的 `data/tmp/xiaoyan1.jpg` 作为临时实验素材；点击角色可显示气泡，拖动角色可模拟桌面移动，右侧按钮可开关浮游、呼吸和灵光动效。
