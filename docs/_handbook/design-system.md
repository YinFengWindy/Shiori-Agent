# Shiori 设计系统

## 先理解它是什么

Shiori 的视觉是**三层单向依赖**：色阶原语 → 语义 token → Tailwind 语义类 / 共享类名。
组件只碰最外层，永远不直接写死颜色、圆角、阴影。

```
第一层  primitives            --pink-500 / --neutral-800 / --lavender-300
        （styles.css 顶部，色相命名，组件里禁止直接使用）
          ↓
第二层  semantic tokens       --color-accent-solid / --color-text-muted / --radius-md
        （styles.css 中段，按用途命名，对比度已逐条校验）
          ↓
第三层  Tailwind 语义类        bg-surface / text-ink-muted / rounded-md / shadow-soft
        共享类名              inputClass / primaryButtonClass / cardClass
        （tailwind.config.ts + shared/styles.ts，组件只用这一层）
```

**为什么要三层**：暗色主题落地时只需要覆盖第二层，第一层色阶和第三层组件代码都不用动。
任何绕过分层的写法（组件里出现 `#ffb8d1`、`rounded-[14px]`、`var(--pink-300)`）都会让这个前提失效。

**权威文件**（本文档是导读，冲突时以代码为准）：

| 文件 | 内容 |
|---|---|
| `apps/desktop/renderer/src/styles.css` | 全部 token 定义、全局 base 规则、工具类、动效 |
| `apps/desktop/renderer/tailwind.config.ts` | token → Tailwind 语义类的映射、排版阶梯 |
| `apps/desktop/renderer/src/shared/styles.ts` | 组件级共享类名常量 |
| `apps/desktop/renderer/src/shared/ui/icons/SPEC.md` | 品牌母题图形的绘制规则 |

**活的样式手册**：`apps/desktop/renderer/styleguide.html`（入口 `src/styleguide/main.tsx`）能把全部色阶、
共享类名、图标渲染出来。它**没有**进 `vite.config.ts` 的 build inputs，是 dev-only 的，
跑 `pnpm desktop:dev` 后在 vite dev server 上开 `/styleguide.html` 查看。改动 token 或共享类名后应该去这里目测一遍。

## 第一层：primitives

在 OKLCH 空间生成：每条色阶恒定色相、感知亮度均匀、彩度在中段达峰。**组件里不要直接引用。**

| 色阶 | 色相 | 档位 | 用途 |
|---|---|---|---|
| `--neutral-*` | 345（暖木兰灰） | 50–950 | 文本、边框、中性背景 |
| `--pink-*` | 356（樱粉） | 50–900 | 品牌强调色、hover/active、选区 |
| `--blue-*` | 240（粉蓝） | 50–300 | 应用底色渐变、强调渐变的冷端 |
| `--lavender-*` | 302（薰衣草） | 50–700 | 次级强调 |
| `--success-* / --warning-* / --danger-*` | — | soft / 300 / solid / text 四档 | 状态 |

两个特例：`--blue-grad` / `--pink-grad` / `--lavender-grad` 是**渐变专用端点**，比同族色阶更深，
目的是让白字在整条渐变扫过时都保持 ≥4.5:1（端点 4.78 / 5.20，oklab 中点 4.93 —— 数值见 `styles.css` 里 `--blue-grad` 定义处的注释）。

## 第二层：semantic tokens

按用途命名，注释里带对比度实测值。新增语义 token 时必须同样标注对比度。

**表面**：`--color-bg-app`（应用底）、`-soft`、`-surface`（纯白卡片）、`-glass` / `-glass-strong`（半透明）、`-hover`、`-active`

**文本**（对比度基于 `--color-bg-surface`）：

| token | 对比度 | 用途 |
|---|---|---|
| `--color-text-primary` | 15.6:1 | 正文主色 |
| `--color-text-secondary` | 8.2:1 | 次级文本 |
| `--color-text-muted` | 5.5:1 | 弱化说明 |
| `--color-text-faint` | 4.2:1 | **仅限 placeholder 与装饰**，不达 AA 正文标准 |
| `--color-text-accent` | 6.0:1 | 强调文本 |
| `--color-text-lavender` | 5.8:1 | 次级强调文本 |

**边框**：`--color-border-soft` / `--color-border` / `--color-border-strong` / `--color-border-accent`
**焦点**：`--color-ring`（3.1:1，键盘焦点描边）、`--color-ring-soft`（22% 透明的字段光晕）
**强调**：`--color-accent-solid`（白字 4.6:1）、`-hover`（6.0:1）、`-soft`、`-softer`
**状态**：每族三件套 `-soft`（背景）/ `-solid`（实心）/ `-text`（文本）

**渐变**：

| token | 场景 |
|---|---|
| `--gradient-app` | 应用整体底色（body 上 `fixed`） |
| `--gradient-accent` | 主操作按钮等控件面，配 ink 文字（13:1） |
| `--gradient-accent-strong` | 文字渐变、细数据标记（浅色版会消失的场景） |
| `--gradient-accent-soft` | 极浅底纹 |
| `--gradient-accent-medium` | 进度条 / 计量条 |

**圆角**：`--radius-sm` 8px / `--radius-md` 12px / `--radius-lg` 16px / `--radius-xl` 20px
**阴影**：`--shadow-soft`（常规抬起）/ `--shadow-panel`（面板）/ `--shadow-pop`（弹出层），全部带粉调
**动效**：`--duration-fast` 140ms / `--duration-base` 220ms / `--ease-out-soft`
**字体**：`--font-sans`（正文）/ `--font-display`（标题）

## 第三层：Tailwind 语义类

`tailwind.config.ts` 把第二层映射成语义类名。**新代码只用这一层。**

| 类名族 | 档位 | 对应 |
|---|---|---|
| `bg-surface` | `-soft` `-app` `-hover` `-active` | 表面 token |
| `text-ink` | `-secondary` `-muted` `-faint` | 文本 token |
| `border-line` | `-soft` `-strong` `-accent` | 边框 token |
| `*-accent` | `-hover` `-soft` `-softer` `-text` | 强调 token |
| `*-lavender` | `-soft` `-text` | 次级强调 |
| `*-success` / `*-warning` / `*-danger` | `-soft` `-text` | 状态 |
| `rounded-{sm,md,lg,xl}` | — | 圆角 token（`rounded-full` 走 Tailwind 默认的 9999px） |
| `shadow-{soft,panel,pop}` | — | 阴影 token |
| `ease-out-soft` | — | 缓动 token |

**排版阶梯**（中文正文不低于 14px，caption 下限 12px）：

```
caption 12px · body-sm 13px · body 14px · body-lg 15px
title-sm 16px/600 · title 18px/600 · headline 22px/650 · display 28px/700
```

标题用 `font-display`，正文用默认 `font-sans`。story 模块保留 `font-serif` 作为装饰面，不要迁移。

## legacy 别名：不要在新代码里用

restyle 之前的一批变量名仍然存在，它们都已指回语义层，渲染结果与新写法完全一致，只是命名不表意：

- CSS 变量：`--bg` `--bg-soft` `--chat-bg` `--panel` `--panel-strong` `--text` `--muted` `--accent` `--accent-deep` `--stroke` `--shadow` `--app-bg`
- Tailwind 类：`bg-bg` `bg-panel` `text-text` `text-muted` `border-stroke` `*-primary` `*-accent-deep`

碰到就顺手换成语义写法，但不要为此单开重构。

## 共享类名（`shared/styles.ts`）

控件外观的唯一来源，**不要在组件里另起一套手写串**。

| 常量 | 用途 |
|---|---|
| `cx(...)` | 零依赖的条件类名拼接 |
| `inputClass` / `textareaClass` | 聊天输入框以外的所有表单字段 |
| `primaryButtonClass` | 主操作（渐变面 + ink 文字） |
| `ghostButtonClass` | 次级操作 |
| `dangerButtonClass` / `dangerGhostButtonClass` | 破坏性操作的实心版 / 安静版 |
| `iconButtonClass` | 纯图标方形按钮（返回、重置、工具），统一 `rounded-md` |
| `primaryButtonSurfaceClass` / `ghostButtonSurfaceClass` / `dangerGhostButtonSurfaceClass` | 不含尺寸的按钮外观，配 `compactButtonSizeClass`（36px 带文字按钮）或自带尺寸使用 |
| `cardClass` | 空状态、诊断行等卡片面 |
| `badgeClass` | 状态与标签胶囊 |
| `panelHeadClass` / `panelTitleClass` | 面板头部布局与标题 |
| `sidebarNavItemClass` / `secondarySidebarSurfaceClass` | 侧栏导航项与次级侧栏背景 |
| `bodyTextClass` | 非标题栏内容的小号正文 |
| `focusResetClass` | 自带状态样式的控件的 focus 复位 |

需要变体时用 `cx(inputClass, "min-h-24 resize-y")` 这种叠加写法（`textareaClass` 本身就是这么来的），
不要复制粘贴整串再改。**只叠加不冲突的类**：同一属性的两个工具类（如 `px-[18px]` 和 `px-3.5`）都会落到元素上、由样式表顺序决定谁赢，
要换尺寸就用上面的 `*SurfaceClass` 自己配尺寸。

溢出菜单（「…」）用 `shared/ui/ActionMenu`（Base UI Menu + `Menu.tsx` 的视觉词汇）。
聊天输入框上的弹层（模型菜单、常用表情面板）用 `chat/useChatComposerPopover`：渲染进 body portal、`position: fixed` 定位在按钮上方，
高度不超过按钮到窗口顶部的空间、放不下就在面板内滚动。输入框卡片是 `overflow: hidden` 且带 `backdrop-filter`（会成为 fixed 后代的包含块），
在卡片里面绝对定位的弹层一定会被裁掉。手写菜单的方向键 / Home / End 焦点移动用 `Menu.tsx` 的 `moveMenuFocus`。

## 工具类（`styles.css` 的 `@layer utilities`）

- `surface-glass` / `surface-glass-strong` —— 玻璃面板（半透明 + 模糊），用在图片或有色背景之上
- `bg-gradient-accent` / `-soft` / `-strong` / `-medium` / `bg-gradient-app` —— 渐变面
- `text-gradient-accent` —— 渐变文字（内部用 strong 版，浅色版做文字会看不见）
- `scrollbar-stable` —— 只做 `scrollbar-gutter: stable`（给滚动条预留车道，内容开始滚动时不左右跳），只用在竖向滚动区；滚动条外观见下一节
- `scrollbar-native` —— 整棵子树退回系统滚动条，目前只有 story 插件的根用（它不在 restyle 范围内）
- `story-*` —— story 模块专属的玻璃底与文字可读性描边，**尚未 token 化**，别往其他模块搬

## 滚动条

全应用**只有一种滚动条**，由 `styles.css` `@layer base` 里的 `:where(*)` 基层规则统一给出，组件不用加任何类就能拿到：
细（`scrollbar-width: thin`）、透明轨道、品牌色滑块——平时 `--color-scrollbar-thumb`（pink-300，1.6:1），
指针停在滚动区上时加深为 `--color-scrollbar-thumb-hover`（pink-500，3.1:1）。竖向和横向（代码块、Markdown 表格、生图历史胶片条、标签栏）是同一套。
宿主页面和插件界面都走它，官网（`site/`，同样引入 `styles.css`）也一样。

- **只用标准属性**：Chromium 在元素设置了 `scrollbar-color` / `scrollbar-width` 后会忽略 `::-webkit-scrollbar` 伪元素，
  所以不要再写 `::-webkit-scrollbar*` 规则（以前的 `scrollbar-soft-accent` / `-muted` hover 变体就是这样一直没生效的）。
- 滚动条悬停色跟着"指针所在的滚动区"走，所以颜色是每个元素各自设置，而不是只在 `:root` 上设一次靠继承。
- 竖向滚动区想避免内容在出现滚动条时跳动，叠 `scrollbar-stable`；横向滚动区不要加（它预留的是竖向车道）。
- 确实需要隐藏滚动条的自带样式表面（桌宠气泡的 `scrollbar-width: none`）直接用普通类覆盖即可——基层规则是 `:where()` 零特异性。
- 不要在组件里另写滚动条颜色、宽度或伪元素样式。

## focus 与无障碍

焦点样式有**单一来源**，组件里不要重复实现：

1. `styles.css` 的 `:where()` 表单焦点基层规则 —— `input / textarea / select / button[role="combobox"]` 的 `:focus` 统一给"强调色边框 + 一层柔光晕"。
   用 `:where()` 包住让特异性归零，所以刻意无边框的控件（如聊天输入区的 `ring-0`）能用工具类覆盖掉。
2. `styles.css` 的全局 `:focus-visible` 规则 —— 全局 `:focus-visible` 给 2px 的 `--color-ring` 描边，键盘焦点始终可见；
   指针点击不显示描边。
3. `styles.css` 紧随其后的表单字段豁免规则 —— 表单字段和 `button[role="combobox"]` 单独关掉上面那层全局描边，避免和自己的
   边框+光晕叠成双环。

**所以**：组件里出现 `focus:ring-*` / `focus:border-*` / `focus:outline-none` 时，默认是错的。
确有理由退出统一样式的，在注释里写明原因。

其他基线：正文文本对齐 WCAG AA；`--color-text-faint` 只能给 placeholder 和装饰；
新增语义色对时把实测对比度写进注释。

## 动效

- 时长 token（Tailwind 里是 `duration-*`）：

  | token | 值 | 用途 |
  |---|---|---|
  | `--duration-fade` | 120ms | 只有透明度的视图切换（主区域换页） |
  | `--duration-fast` | 140ms | 悬停、颜色变化；裸 `transition` 的默认值 |
  | `--duration-quick` | 160ms | 按压反馈、菜单/下拉/小弹层、角色详情切 tab |
  | `--duration-base` | 220ms | 对话框、提示、侧栏内容淡入 |
  | `--duration-panel` | 260ms | 侧栏宽度（和 `app/appState.ts` 的 `sidebarAnimationDurationMs` 同步，有测试守着） |
  | `--duration-motif` | 480ms | 导航栏图标里品牌小元素的一次性小动画 |
  | `--duration-enter` | 240ms | 聊天新消息入场（只 CSS 用，没有 Tailwind 类） |
  | `--duration-crossfade` | 320ms | 图片换图的交叉淡入（`shared/CrossfadeLayers`，心情立绘、聊天背景） |
  | `--duration-pulse` | 600ms | 一次性的提示脉冲（跳转到引用消息的光环） |
  | `--duration-morph` | 420ms | 共享元素视图过渡（角色卡片 ↔ 详情头部），配 `--ease-drawer`（只 CSS 用） |
  | `--duration-page-rise` | 380ms | 视图过渡里新页面的上浮淡入（只 CSS 用） |
  | `--duration-spring` | 700ms | 倾斜卡片离开后的弹簧回正，配 `--ease-spring`（只 CSS 用） |
  | `--duration-mood-focus` | 480ms | 心情立绘换图：新图从 1.04 倍 + 模糊落定（`CrossfadeLayers` 的 `focus` 变体，只 CSS 用） |
  | `--duration-mood-tint` | 260ms | 心情胶囊换色（只 CSS 用） |
  | `--duration-typing` | 1.2s | 「正在输入…」星芒一轮跳动（只 CSS 用） |
  | `--duration-backdrop-in` | 560ms | 聊天切换角色时新背景从 1.05 倍落定（只 CSS 用） |
  | `--duration-breathe` | 8s | 聊天背景一次完整呼吸 1 → 1.025 → 1（只 CSS 用） |

- 弹簧缓动 `--ease-spring`：阻尼弹簧（ζ 0.42、ω 11）采样成 `linear()`，不支持时退回会过冲的 cubic-bezier；只给「松手回弹」这类一次性回正
- 视图过渡：`shared/viewTransition.ts` 的 `runViewTransition({ update, nameOld, nameNew })` 包一层同文档 View Transition——运行中的过渡先 `skipTransition()` 再开下一段，名字只在上一段 `updateCallbackDone` 之后才分配；过渡期间点到 `<html>` 的点击会先结束过渡再在原处重放。减弱动态效果时不命名任何元素，只剩 140ms 根交叉淡入；没有 API 时直接切换。角色卡片 ↔ 详情用 `roles/roleViewTransition.ts`：元素用 `data-vt-part`（portrait / avatar / name / sub）标记，页面用 `data-role-page`，规则见 styles.css 的 `role-*`
- 聊天切换角色：`chat/chatRoleSwitchTransition.ts` 的 `openChatRole`（同样走 `runViewTransition`）。列表行（`data-chat-role-row`）的头像和名字（`data-vt-part`）变形进聊天头部，旧头部那一对缩小淡出；背景（`data-chat-backdrop`）新图从 1.05 倍落定、盖在旧图上（新角色没有背景时旧图淡出）；对话区（`data-chat-conversation`）淡出再上浮。头部条和对话区也各自命名，否则背景层会盖住它们；视图过渡的 group 按旧视图的绘制顺序叠放，列表在聊天区之前，所以变形的头像和名字要 `z-index: 1`。规则见 styles.css 的 `chat-*`。同一角色的背景 / 心情立绘换图仍由 `shared/CrossfadeLayers` 负责，它的 `resetKey`（角色）一变就直接换，不和视图过渡打架。只有聊天区在屏且确实换了角色才走过渡；离开守卫仍在最外层
- 心情变化演出（`chat/ChatStatusSidebar.tsx`）：立绘用 `CrossfadeLayers variant="focus"`；心情胶囊按 `chat/moodTone.ts` 的五种语气（happy / shy / sad / angry / calm，按关键词匹配角色自定义的心情名，认不出的归 calm）换 `--color-mood-*` 配色，并弹一下（生气改为抖动）；再按语气喷一小簇品牌母题粒子（`chat/moodBurst.ts`：樱瓣飘落 / 小心上浮 / 水滴落下并短暂压暗去饱和 / 胶囊迸火花 / 单个星芒闪烁），约 1.2s，同时存活不超过 28 个，结束即移除。粒子关键帧整体用 linear、缓动写在每一段里（整体 ease-out 会把整段飞行挤在头几帧）。只在「看着的时候真的变了」才播：由 `chat/moodChangeCue.ts` 判定——首次加载、切换角色、重新载入都只移动基线，新心情的 `current_mood_updated_at` 必须晚于这个角色进入视野的时刻。颜色 token 见 styles.css 的 `mood tones` 段
- 星芒打字：「正在输入…」前是三颗品牌星芒（天蓝 / 粉 / 薰衣草，`--color-typing-*`）依次跳动闪烁，组件 `chat/ChatTypingSparkles.tsx`，样式 `.chat-typing-sparkles`
- 背景呼吸与视差（设置 › 外观，默认开）：`chat/useChatBackdropMotion.ts`。背景立绘极慢地呼吸（`.chat-backdrop-breathe`）；视差由 `chat/backdropParallax.ts` 计算——背景最多反向 12px、对话区同向 3px，帧率无关的 lerp，停稳即停 rAF，不留空转帧。背景层四周多出 12px（`-inset-3`）避免露边。窗口隐藏或失焦时呼吸暂停、视差回中；减弱动态效果时两者都关，设置开关显示为关并锁定。偏好只影响渲染，存在渲染进程 localStorage（`shared/appearancePrefs.ts`，键 `shiori.desktop.appearance`，带版本号），不进 config.toml
- 倾斜卡片：`shared/ui/reactBits/TiltedCard`（样式 `.tilt-card`），只在鼠标悬停时跟随指针倾斜（最大 8°）并带光带与高光，离开后弹簧回正；触屏、粗指针和减弱动态效果下保持平放。光效层不接收指针，不影响点击、焦点和卡片菜单。目前只用在角色卡片网格
- 缓动：`--ease-out-soft`（`ease-out-soft`，也是裸 `transition` 的默认值）用于入场、按压、悬停；
  `--ease-drawer`（`ease-drawer`）只给侧栏开合这类抽屉；`--ease-in-out-soft` 只给两端都在屏幕上的对称切换（交叉淡入）
- 聊天新消息入场只对「当前会话挂载后追加的消息」播一次，由 `chat/chatMessageEnterState.ts` 判定：
  切会话、翻历史、虚拟化重挂载都不播
- 按压反馈用 `shared/styles.ts` 的 `pressableClass`（0.97）/ `compactPressableClass`（30px 及以下的图标按钮，0.96）。
  它接管元素的整条 transition，不要再和别的 `transition*` 类叠加。共享按钮类已经带上了
- 弹出层：Base UI 的 Select / Dialog 用 `motion-popup` / `motion-dialog` / `motion-backdrop`，进出场都有；
  手写弹层用 `motion-popover-enter` / `motion-dialog-enter` / `motion-fade-enter`（`@starting-style`），
  只做入场，关闭时直接消失，缩放原点用 Tailwind 的 `origin-*` 指定。右键菜单和命令面板（RoleSearchDialog）刻意不加动效
- 侧栏开合用 `sidebarTrackMotionClass`（轨道宽度）+ `sidebarContentMotionClass`（内容淡入位移）
- 展开/收起用 `grid-template-rows: 0fr → 1fr` 的写法（见 `.chat-thinking-content`），不要用 max-height 猜数值；设置页的折叠区（插件「系统组件」、schema 表单「高级」）用 `settings/SettingsDisclosure` 的 `SettingsDisclosure` + `SettingsDisclosureToggle`（样式 `.disclosure-content`，收起时内容 `inert`）
- 减弱动态效果下：`CrossfadeLayers` 的两个变体都只剩透明度淡入淡出（不模糊、不缩放）；心情变化不喷粒子、胶囊不弹，只换颜色；星芒打字静止；聊天背景不呼吸、无视差
- **`styles.css` 末尾有统一的 `@media (prefers-reduced-motion: reduce)` 块**（这里不写行号，行号会漂）：新增循环动画或较大位移的过渡时，
  必须同时在这个块里给出降级（`animation: none` 或退化成 opacity 过渡）。
  Tailwind 类就近处理：挂在 `hover:` / `active:` / `group-hover:` 上的位移和缩放写成 `motion-safe:hover:*`
  （`motion-reduce:transform-none` 在 CSS 里排在这些变体前面，盖不住），其余用 `motion-reduce:*`；motion/react 动画由根节点的 `<MotionConfig reducedMotion="user">` 统一去掉位移，
  需要自己判断的组件用 `useReducedMotion()`；命令式滚动用 `shared/reducedMotion.ts` 的 `prefersReducedMotion()`

## 图标

两套用途完全不同的图形，别混：

| 来源 | 内容 | 规则 |
|---|---|---|
| `shared/icons.tsx` + `@phosphor-icons/react` | 功能图标（保存、删除、上传、发送、关闭……） | **一律复用，不要自绘。** 2026-09 视觉验收时自绘功能图标被逐一打回 |
| `shared/ui/icons`（`brand.tsx`） | 品牌装饰母题：星芒、恶魔翅膀、蝴蝶结、樱瓣 | 只用于空状态、加载、成就等情绪点缀。几何统一在 `brandMotifPaths`（另含只作粒子用的心形、水滴），心情粒子和打字星芒都从这里取形 |

**导航栏图标**是两者的组合（`shared/ui/icons/navGlyphs.tsx`）：Phosphor **regular** 原图，外轮廓不改，里面嵌**一个**品牌小元素。
小元素是独立的 `<g class="nav-glyph-motif">`，平时 `--color-motif`（pink-500），选中时换品牌渐变（渐变 id 每个实例用 `useId` 生成）；
描边仍走导航栏原来的颜色。悬停、键盘聚焦和变为选中时，只有小元素播一次 `--duration-motif` 的小动画，
动画写在 `styles.css` 的 `prefers-reduced-motion: no-preference` 里，减弱动态效果时只保留颜色变化。
不要改成 fill / bold 字重，也不要用 duotone。

| 入口 | Phosphor 原图 | 小元素 | 动画 |
|---|---|---|---|
| 搜索 | MagnifyingGlass | 镜片里的星芒 + 小圆点 | 星芒闪烁（缩放+旋转），圆点淡出再回来 |
| 消息 | Chats | 后面气泡里的心 | 心跳 |
| 角色 | Users | 前面人头上的蝴蝶结 | 左右摆动 ±12° |
| 设置 | GearSix | 齿轮孔里的五瓣樱花 | 转 72° |
| 故事（story 插件） | BookOpenText | 左页的飘带书签 | 书签飘动 |

插件的导航图标契约仍是 `React.ComponentType<{ className?: string }>`，可以直接用上面导出的 glyph，
或用 `withMotif(Phosphor 图标, 小元素, 动画, 组件名)` 组合自己的。第三方服务有官方标识的插件（如 NovelAI 生图）保留其官方图标，不套品牌小元素。

新增品牌母题时按 `shared/ui/icons/SPEC.md`：`viewBox="0 0 24 24"`、活动区 20×20、
线性为主（`fill="none"` + `stroke="currentColor"` + `strokeWidth={1.7}` + 圆头）、
duotone 副形用 `fill="currentColor"` + `opacity={0.15}`、颜色只用 `currentColor`、
签名 `({ className = "h-4 w-4" }: IconProps)`、svg 带 `aria-hidden="true"`。

Phosphor 在 `vite.config.ts:25` 被单独拆成 `icons-vendor` chunk，按需引入即可，不必担心体积。

## 看板娘（吟风）

吟风是 Shiori 的看板娘（#362 阶段 10，之后扩展到确认弹窗、全部提示和页面内报错）。首次引导之外，她只出现在下面这些位置，别的地方不要随手加：

| 位置 | 呈现 | 组件 |
|---|---|---|
| 启动画面（后端启动超过 400ms 才出现，超过 8 秒换一句，启动失败给「重启连接」） | 半身立绘 + 台词气泡 + 星芒加载，时间段风景背景 | `app/StartupSplash.tsx`，时机在 `app/startupSplashPhase.ts` |
| 空状态：没有角色（聊天侧栏、角色页）、搜索没有结果 | 中尺寸立绘 + 台词气泡 + 该处原有的操作按钮 | `shared/mascot/MascotSpeech` 的 `MascotEmptyState` |
| 连接断开横幅 | 小头像 + 她的一句话作第一句，原来的说明在后 | `app/BridgeOfflineBanner.tsx` |
| 全部提示（toast） | 小头像替换语气图标；报错 / 警告她先说一句，原文在后，技术细节仍在「详情」；成功 / 普通提示只露脸（规则见下） | `feedbackStore` 的 `persona`，宿主出口 `shared/mascot/mascotFeedback.ts` |
| 确认弹窗 | 标题下一行：大号小头像 `lg` + 台词气泡作弹窗的第一句，表情按意图（删除 → 担心，放弃修改 → 鼓脸，重启 → 惊讶，信任 / 安装 → 疑惑 / 普通）；原来的事实说明（删什么、何时生效）照旧在后 | `shared/ui/ConfirmDialog` 的 `persona`（传 `confirmPersonaLines` 里的一句） |
| 页面内报错 | 小头像 + 她的一句 + 原文 + 可选「详情」/ 操作按钮；三种版式 `row`（表单、列表里的块）、`strip`（贴在卡片边上的一条）、`card`（占住空区域的居中卡片，大号头像 + 气泡） | `shared/feedback/InlineError`（`persona` 取 `inlineErrorLines` 的键） |
| 设置 › 关于 | 右侧半身立绘，版本卡片下面一句台词；点她换一句（连带换表情） | `settings/AboutMascot.tsx` |

规则：

- **台词只写在 `shared/mascot/mascotLines.ts`**，每句不超过 40 字（有测试守着），带一个表情。同一场景多句时用 `pickMascotLine` 随机取、不和上一句重复。她的台词是 owner 认可的「不写叙述文字」例外，只限这张表里的场景。
- **三种尺寸**（`shared/mascot/MascotFigure`，样式 `shared/mascot/mascot.css`）：半身 `MascotHalfFigure`（按 `--mascot-half-crop` 裁在腰下并渐隐，带表情交叉淡入）、中尺寸 `MascotMediumFigure`（`--mascot-medium-width` 180–240px，窄处用 `--mascot-compact-width`）、小头像 `MascotFaceAvatar`（`--mascot-face-size` 2rem，圆形取脸；`size="lg"` 用 `--mascot-face-size-lg` 3rem，给确认弹窗和报错卡片）。立绘阴影 `--mascot-drop-shadow` 挂在裁切框外层，挂在带遮罩的那层会被裁成一个矩形。
- **动效**：出场是淡入 + 上浮 `--mascot-enter-rise`（`.mascot-enter`，`--duration-stage`）；换表情是 `--duration-quick`（160ms）的叠层交叉淡入（`MascotExpressionStack`，首次引导同一套）。减弱动态效果时出场只剩淡入，换表情照旧淡入。
- **开关**：设置 › 外观 ›「看板娘」（`appearancePrefs.mascot`，默认开）。组件用 `useMascotEnabled()` 判断，关掉时渲染原来那套不带她的样式，不留空位；启动画面整个不出现，启动失败交回离线横幅。
- **提示（toast）什么时候带她的一句**：宿主代码用 `mascotFeedback`，每种语气都有默认人设（`feedbackTonePersona`）：
  - 报错 / 警告：**一定带一句**（`generic` / `warning`；没有「详情」的报错用 `genericBrief`，不许诺并不存在的详情），出了事她先开口。
  - 成功 / 普通提示：**只露脸不说话**（`success` 大笑、`info` 普通）。这些是高频提示（已复制、已保存、已加入素材库、角色已保存…），每次一句会刷屏。
  - 成功提示带一句只留给少见的节点：新建角色、导入角色卡、删除角色、连接恢复，由调用处按名字传（`roleCreated` / `roleImported` / `roleDeleted` / `bridgeRecovered`）。新加一句前先问：它会不会一小时出现好几次？会就只露脸。
  - 更具体的报错传具体的键（未选模型 `modelMissing`、角色卡读不了 `roleImportFailed`）。
- **确认弹窗**：宿主的每个 `ConfirmDialog` 都传 `persona`；没有专属台词时用通用的 `destructive` / `confirm`。不传就是不带她的弹窗（插件的弹窗默认如此）。弹窗里的报错不再加她（她已经在弹窗里了）。
- **页面内报错**：一律用 `InlineError`，不要再手写 `bg-danger-soft` + `text-danger-text` 的报错块；字段级的校验提示（输入框下面的一行小字）不算，照旧。
- **她已经在场时不重复出现**：`MascotOnStage` 标记「她本人已经站在这里」的子树（首次引导、设置 › 关于、带她的确认弹窗），里面的 `InlineError` 只留原文和警告图标。首次引导里的报错由她在对话框里回应，关于页的更新失败由她的台词说（`aboutUpdateLines.failed`）。
- **插件**（runtime API 2.4.0）：插件通过注入的 `host` 服务用 `host.feedback.*`、`host.ui.InlineError`、`host.ui.ConfirmDialog`，传 `persona` 才让她出面：`true` 是该处的通用台词，场景键（`personaSceneLines`：`not_configured` / `unauthorized` / `quota` / `network` / `upstream` / `destructive` / `discard` / `confirm`）是宿主为该场景写的台词。插件只能选场景、不能替她写台词，也不要直接引用 `shared/mascot`；新场景要加在宿主这张表里。开关关掉时插件那边也一律不带她。生图插件的失败卡片和报错提示按错误码选场景，提示词库的删除确认用 `host.ui.ConfirmDialog`；它的空状态仍保留阶段 7 的品牌母题。契约见 `plugin-runtime-contract.md`「Runtime API 2.4」。
- 素材用 `new URL(…, import.meta.url)` 引用，不用 `import x from "*.webp"`：Node 单测没有 webp 加载器，这样显示她的组件才能直接在单测里挂载。

## 动手前的检查清单

- [ ] 颜色 / 圆角 / 阴影 / 时长是不是都走了 token 或语义类？有没有漏下的写死值？
- [ ] 这个控件在 `shared/styles.ts` 里是不是已经有共享类名了？
- [ ] 有没有手写 `focus:*` 覆盖全局焦点样式？
- [ ] 新增动画有没有在 `prefers-reduced-motion` 块里降级？
- [ ] 新语义色对有没有标对比度？文本是不是在 AA 之上？
- [ ] 图标走的是功能图标那一套，还是误用了品牌母题？
- [ ] 跑 `pnpm desktop:dev` 开 `/styleguide.html` 目测过没有？

## 已知遗留

- **暗色主题尚未实现**：`:root` 固定 `color-scheme: light`，全文件无 `prefers-color-scheme` 分支。
  设计上已经预留（`styles.css` 开头 token 分层注释："dark theme later overrides the semantic tier only"），
  但前提是新代码不绕过语义层——每一处写死颜色都是将来暗色主题的一处返工。
- **`--font-brand` 槽位空着**：MiSans / HarmonyOS Sans SC 还没定，字体栈目前从系统层起步（`styles.css` 的 `--font-sans` 定义）。
- **legacy 别名仍在服役**：`tailwind.config.ts` 的 legacy 色名和一批老组件还在用。
- **story 模块自成一套**：`story-*` 工具类里的玻璃底、描边、阴影都是写死值，没有接入 token。
