# 桌面端

Electron 主进程在 `src/`，只放通用原语。React 在 `renderer/src/`。插件 UI 在仓库的 `plugins/<id>/{ui,surface,background}/`，不要写进主进程。

- `pnpm test` 跑 `desktop:test`（并列的 `*.test.ts` / `*.test.tsx`）再跑 `site:test`。`*.e2e.ts` 不在这条路径里。
- **NEVER** 为覆盖率加 `*.test.ts`。新测试必须能单独失败。**NEVER** 加只断言 mock 被调用或构造入参原样返回的用例；优先补已有文件。桌面端改动不扩大 Python 选择；桥接契约在 `apps/backend/desktop_bridge`。
- 打包与发布脚本测试是 `pnpm --filter shiori-desktop run test:package`。插件 UI 构建冒烟是 `pnpm run desktop:test:plugin-ui`。
- 颜色、圆角、控件类名走 `docs/_handbook/design-system.md` 和 `@yinfengwindy/shiori-sdk`。焦点样式由 `styles.css` 统一提供。
- 所有权与桥接见 `docs/knowledge/modules/desktop-and-bridge.md`。
