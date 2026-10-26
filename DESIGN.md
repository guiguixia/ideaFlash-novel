# Design

## Source of truth

- Status: Active
- Last refreshed: 2026-10-23
- Primary product surfaces: 我的作品、作品工作台、体验副本、开始体验、作品设置
- Evidence reviewed: `README.md`、`web/src/App.tsx`、`web/src/styles/globals.css`、现有 `ExperienceSnapshot` / `ExperienceSession` 模型与接口

## Brand

- Personality: 安静、沉浸、可信赖的故事实验室；让作者感觉是在进入和打磨自己的世界。
- Trust signals: 清楚标注作品来源、仅自己可体验、体验版本与会话相互隔离。
- Avoid: 小说生产流水线、公开社区/榜单语义、把创作和体验拆成两套视觉产品。

## Product goals

- Goals:
  - 将产品定义为私有互动故事创作与体验平台，而非小说写作工作台。
  - 用户能创建原创故事，或导入小说/影视文本资料，生成私有体验副本并进入体验。
  - 所有来源统一在同一作品工作台内完成资料管理、创作配置、体验副本管理和游玩。
- Non-goals:
  - 不做章节正文、小说正史、审校、扫榜、市场报告或公开社区。
  - 当前及可预见阶段不提供公开发布、分享链接或他人游玩。
  - 不将体验记录自动沉淀成小说内容。
- Success signals:
  - 用户能在不离开当前作品工作台的前提下，从资料/设定到进入体验。
  - 用户能理解导入作品与原创故事的差异，但不会觉得它们是两套产品。

## Personas and jobs

- Primary personas: 想体验已有文本世界的个人用户；想创建私有互动故事并反复试玩的故事创作者。
- User jobs:
  - 导入小说后选择连续章节，创建一个可体验的私有副本。
  - 导入影视文本资料后选择片段或场景，创建私有副本。
  - 从最小故事设定开始，创建原创互动故事并测试开局、角色和世界规则。
- Key contexts of use: 桌面优先；长时间阅读、编辑、角色扮演和多轮对话。

## Information architecture

- Primary navigation: 我的作品；新建原创故事；导入小说；导入影视资料；设置。
- Core routes/screens:
  - 我的作品：按类型展示作品，不展示公共市场或趋势。
  - 作品工作台：概览、资料/故事设定、体验副本、开始体验、角色与世界、体验记录、设置。
  - 体验会话：完整场景叙事、会话历史、输入行动、会话控制。
- Content hierarchy:
  - `Work` 是用户拥有的作品容器。
  - `ExperienceScript` 是由原创设定或导入资料生成的私有体验版本/副本。
  - `ExperienceSession` 是某个体验副本上的一次游玩分支。
  - 所有访问权限均为 owner-only。

## Design principles

- 同一作品，同一外壳：三种来源永远使用同一个作品工作台布局与导航。
- 来源决定编辑面，而非决定产品形态：原创编辑故事设定；导入作品编辑体验范围、视角和玩家身份。
- 先看清再行动：创建副本前展示范围、视角、预计角色和私密性。
- 体验是运行态，创作是配置态：会话不自动改写作品；更新配置后生成新体验版本。
- Tradeoffs: 统一体验优先于将每个来源做成高度专用的流程；第一期舍弃公开发布以换取清晰的版权与权限边界。

## Visual language

- Color: 沿用现有中性画布、白色工作区、低饱和品牌强调色与明确的状态色。
- Typography: 沿用 MiSans 与现有字号层级；长文本优先 15-16px、1.6 左右行高。
- Spacing/layout rhythm: 桌面三栏，左 220-250px 导航，中间自适应主画布，右 280-320px 上下文面板；卡片间距 12-20px。
- Shape/radius/elevation: 复用现有 14-22px 工作区圆角和轻边框；避免游戏化拟物面板。
- Motion: 页面模式切换使用短淡入；体验消息自然出现；不使用持续/强烈动画。
- Imagery/iconography: 沿用 Lucide 图标；来源、私密、版本使用文字标签配图标，而非大面积插画。

## Components

- Existing components to reuse: 顶部栏、侧边栏、工作区卡片、表单、角色卡、会话气泡、任务状态。
- New/changed components:
  - `WorkTypeBadge`：原创故事 / 导入小说 / 导入影视资料。
  - `PrivacyBadge`：仅自己可体验。
  - `ExperienceScriptCard`：范围/场景、玩家身份、视角、版本、最近会话。
  - `CreateExperienceScriptFlow`：按来源变化的副本创建抽屉/向导。
  - `RuntimeContextPanel`：场景、在场角色、会话状态、版本信息。
- Variants and states: 未构建、构建中、可体验、失败、已归档；当前会话、历史会话、旧版本会话。
- Token/component ownership: 继续使用 `web/src/styles/globals.css` 中的主题 token，不创建第二套设计系统。

## Accessibility

- Target standard: 键盘可完成导航、表单和会话发送；关键状态不只靠颜色表达。
- Keyboard/focus behavior: 侧栏与卡片可 Tab 聚焦；Enter 发送行动；Esc 关闭创建副本抽屉。
- Contrast/readability: 作品来源、私密性、构建状态均使用文字标签；正文和体验回复满足长阅读对比度。
- Screen-reader semantics: 导航使用 `nav`，会话历史使用有语义的消息列表，异步回复使用 live region。
- Reduced motion and sensory considerations: 尊重系统减少动态效果设置。

## Responsive behavior

- Supported breakpoints/devices: 桌面优先；平板收起右侧上下文栏；移动端将三栏改为抽屉与单栏。
- Layout adaptations: 主画布不横向压缩会话输入；角色/版本列表在窄屏转为顶部切换器。
- Touch/hover differences: 所有 hover 操作都有可点击按钮替代。

## Interaction states

- Loading: 副本构建显示阶段和可离开提示；会话回复显示正在叙事。
- Empty: 没有副本时以“创建第一个体验副本”引导；原创故事没有体验版本时引导建立开局。
- Error: 保留来源资料与用户输入，提供重试和错误说明。
- Success: 副本构建成功后直接提供“进入体验”和“稍后体验”。
- Disabled: 导入作品未选择有效范围时禁用生成；构建中禁用重复提交。
- Offline/slow network: 会话提交后保留待发送文本，并标识请求状态。

## Content voice

- Tone: 直接、克制、沉浸，不使用“正史”“采纳章节”“发布作品”等小说工作台术语。
- Terminology:
  - 写作 → 创作
  - 书架 → 我的作品
  - 小说工作台 → 作品工作台
  - 发布到剧本 → 生成体验副本
  - 副本体验 → 开始体验
- Microcopy rules: 明确说明“仅自己可体验”；导入作品强调“选择章节/片段范围”，原创故事强调“开局/场景版本”。

## Implementation constraints

- Framework/styling system: React + TypeScript + Tailwind CSS，复用当前组件与主题 token。
- Design-token constraints: 不引入额外 UI 库或独立 token 层。
- Performance constraints: 导入正文按范围加载；体验快照冻结后按需加载文本；会话历史分页。
- Compatibility constraints: 维持现有本地账号与单用户数据隔离逻辑。
- Test/screenshot expectations: 新工作台需覆盖三种来源的导航一致性、创建副本流程、私密访问与会话版本隔离。

## Open questions

- [ ] 影视资料第一期只接受剧本、字幕、梗概等文本，还是支持视频文件；影响导入管线与存储成本。
- [ ] 原创故事是否允许一个作品拥有多个并行的开局/场景版本；建议允许。
- [ ] 导入作品的“二次创作配置”是否只包含玩家身份、视角与范围，还是还允许添加原创角色/场景；影响来源边界与运行时模型。
