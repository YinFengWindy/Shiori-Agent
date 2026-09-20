# Shiori 静态交互演示

这个入口复用桌面端的导航、角色列表、聊天消息、输入框、状态栏，以及完整的 `plugins/story/ui/StoryPage.tsx`。浏览器通过明确的演示适配器读取预设内容，不运行 Python，不连接模型，也不读取个人工作区。

聊天可以自由输入、逐字播放预设回复、中止、复制和引用。回复按固定样例轮换，状态也是样例；不会理解输入。Story 保留原来的主菜单、新建向导、读档、逐句推进、自由行动、剧情记录、设置和 CG 集。输入和新建资料会被记录，但剧情始终播放「雨停之前」的十二段预写内容，不生成新文本或图片。

角色使用吟风及其公开展示用头像。五张 CG 选自经用户授权的吟风角色素材库和日常生成图，已转换为 WebP 并移除元数据，随雨窗、日暮、台灯、夜间散步和烟花场景依次解锁。源图不随仓库携带私人路径、角色配置或聊天记录；这些经过处理的资源统一放在 `renderer/src/showcase/assets/`。竖幅 CG 使用完整展示与同图模糊铺底，不裁切人物来填满横屏。

## 本地运行

在仓库根目录使用项目固定版本的 pnpm 安装依赖后运行：

```powershell
pnpm install --frozen-lockfile
pnpm showcase:dev --host 127.0.0.1 --port 3603
```

单独构建及预览：

```powershell
pnpm build:showcase
pnpm showcase:preview --host 127.0.0.1 --port 3603
```

输出目录是 `apps/desktop/showcase-dist/`，包含 `index.html`、脚本、样式和公开图片。它与桌面端的 `renderer-dist` 分开，构建不需要 Python 或任何 API key。不要直接用 `file://` 打开 HTML；使用 HTTP 静态服务。

## 静态部署

把 `apps/desktop/showcase-dist/` 的全部内容上传到任意静态站点，例如 GitHub Pages、Cloudflare Pages 或普通 Nginx 静态目录。构建命令为 `pnpm build:showcase`，输出目录如上。Vite 使用相对资源路径，支持域名根目录和项目子目录；页面内导航使用 `#chat` / `#story`，不需要服务端路由回退规则。

站点只需部署静态产物，不需要 Node/Python 服务，也不会产生模型调用费用。下载入口指向项目 GitHub 最新 Release。

## 演示存档与维护

对话和 Story 的演示进度只保存在访问者浏览器的 `localStorage` 中，刷新可恢复；顶部「重新开始」经确认后清除本演示存档。没有数据上传，也没有跨设备同步。Story 只保存经过校验的创建资料和播放进度，重新加载时用受信任的样例重建页面数据，避免旧构建的图片路径失效。新建最多保留 12 个演示故事。

聊天内容位于 `renderer/src/showcase/demoContent.ts`，故事章节位于 `demoStoryChapters.ts`，受信任资源清单位于 `demoAssets.ts`；协议适配位于 `demoStoryHost.ts`；真正的 Story 页面仍由插件维护。网页通过 `RendererHost` 显式绑定公开资源与外链，不伪装 Electron preload，不开放原生附件、模型管理、文件系统、插件或设置入口。

调整演示逻辑后运行针对 `renderer/src/showcase/` 的单测；共享组件改动还要覆盖其原有测试，并运行根目录 `pnpm lint`、`pnpm typecheck`、`pnpm build:showcase`。CI 的原有桌面端构建与检查仍然保留。
