import assert from "node:assert/strict";
import test from "node:test";
import { chineseReleaseNotes } from "./daily-release-notes.mjs";

const pull = (number) => `https://github.com/YinFengWindy/Shiori-Agent/pull/${number}`;

test("generated English notes become grouped Chinese entries with app-only changes", () => {
  const generated = [
    "## What's Changed",
    `* fix(roles): 修复角色卡导入误报工作区越界 (#776) by @YinFengWindy in ${pull(777)}`,
    `* feat(chat)!: 会话支持拖入图片 by @YinFengWindy in ${pull(801)}`,
    `* style(desktop): 减淡侧栏与主面板的分界阴影 (#780) by @YinFengWindy in ${pull(781)}`,
    `* refactor: 拆分记忆运行时 (#12) (#13) by @YinFengWindy in ${pull(802)}`,
    `* perf(backend): 加快会话加载 by @dependabot[bot] in ${pull(803)}`,
    `* feat(site): 拆出 apps/site（Astro）并接入 SEO 基础 (#769) by @YinFengWindy in ${pull(775)}`,
    `* fix(site): 叙事段验收反馈——点击推进 by @YinFengWindy in ${pull(783)}`,
    `* docs: 更新 README by @YinFengWindy in ${pull(804)}`,
    `* chore(deps): 升级依赖 by @YinFengWindy in ${pull(805)}`,
    `* ci: 缓存 pnpm by @YinFengWindy in ${pull(806)}`,
    `* test(roles): 补充导入测试 by @YinFengWindy in ${pull(807)}`,
    `* Add Windows installer by @someone in ${pull(808)}`,
    "* fix(tray): 托盘图标在高分屏模糊",
    "",
    "## New Contributors",
    `* @someone made their first contribution in ${pull(808)}`,
    `* feat(x): 不应出现 by @someone in ${pull(809)}`,
    "",
    "**Full Changelog**: https://github.com/YinFengWindy/Shiori-Agent/compare/v0.5.2...v0.5.3",
  ].join("\n");
  assert.equal(chineseReleaseNotes(generated), [
    "## 新增",
    "",
    "- 会话支持拖入图片（#801）",
    "",
    "## 修复",
    "",
    "- 修复角色卡导入误报工作区越界（#777）",
    "- 托盘图标在高分屏模糊",
    "",
    "## 改进",
    "",
    "- 减淡侧栏与主面板的分界阴影（#781）",
    "- 拆分记忆运行时（#802）",
    "- 加快会话加载（#803）",
  ].join("\n"));
});

test("notes with no user-facing entries fall back to one Chinese sentence", () => {
  const generated = [
    "## What's Changed",
    `* chore: 忽略运行时状态文件 by @YinFengWindy in ${pull(789)}`,
    `* feat(site): 博客与顶栏导航 (#773) by @YinFengWindy in ${pull(793)}`,
    "",
    "**Full Changelog**: https://github.com/YinFengWindy/Shiori-Agent/compare/v0.5.3...v0.5.4",
  ].join("\r\n");
  assert.equal(chineseReleaseNotes(generated), "本次更新为内部维护与稳定性改进。");
  assert.equal(chineseReleaseNotes(""), "本次更新为内部维护与稳定性改进。");
});
