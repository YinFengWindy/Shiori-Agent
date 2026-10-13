/**
 * Captures the website showcase's stills from the real desktop app: one
 * screenshot per feature (the ids of apps/site/src/content/showcase.ts) into
 * `apps/site/src/assets/showcase/<id>.webp`. The site build only reads those
 * committed files; run this (`pnpm run site:stills`) after the app's look
 * changes and commit the output.
 *
 * Each still gets a fresh, isolated workspace from scripts/showcase_workspace.py
 * (run with the repository .venv): a role card and its pictures copied from a
 * real workspace, plus demo chats, memories, affection and channel accounts.
 * The built desktop app (`pnpm --filter shiori-desktop build`) then opens on
 * it in Electron, driven by Playwright, with its own home and user-data
 * directories so the user's own setup is never read or touched. The window
 * is 1440×900: sharp text at 2× the showcase's largest CSS width.
 *
 * The source workspace is `SHIORI_SHOWCASE_SOURCE` (default
 * `~/.shiori/workspace`) and the role `SHIORI_SHOWCASE_ROLE` (default 吟风).
 * Each WebP must fit `SHOWCASE_STILL_MAX_BYTES`, which the site's build test
 * checks too.
 *
 * Usage: `tsx scripts/stills.ts [id ...]` (default: every still).
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { _electron, type Page } from "playwright";
import sharp from "sharp";
import { SHOWCASE_STILL_MAX_BYTES, type ShowcaseClipId } from "../../site/src/content/showcase";
import { clipIdsFromArgs } from "./clipArgs";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../..");
const desktop = resolve(repo, "apps/desktop");
const outDir = resolve(repo, "apps/site/src/assets/showcase");
const source = process.env.SHIORI_SHOWCASE_SOURCE ?? join(homedir(), ".shiori", "workspace");
const roleName = process.env.SHIORI_SHOWCASE_ROLE ?? "吟风";

const WINDOW = { width: 1440, height: 900 } as const;
/** WebP quality: UI text stays crisp while every still fits the byte budget. */
const WEBP_QUALITY = 80;

const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true });

/** Chat with the role panel open on her status (mood, thought, tags, affection). */
async function openChatWithStatus(page: Page) {
  await button(page, "展开角色面板").click();
  await button(page, "状态").click();
}

async function openRoleTab(page: Page, tab: string) {
  await page.getByRole("button", { name: /^查看角色 .+ 详情$/ }).click();
  await page.getByTestId("role-detail-page").waitFor();
  await button(page, tab).click();
}

interface Scene {
  /** Brings the scene on screen, from the app's start page (the role's chat). */
  open: (page: Page) => Promise<void>;
  /**
   * Text of the scene's first and last rows (a message, a list entry): both
   * must be wholly visible, so the still cuts nothing off at an edge.
   */
  whole: readonly string[];
}

/** What each still shows. */
const SCENES: Record<ShowcaseClipId, Scene> = {
  // The memory timeline of the role page.
  memory: {
    open: (page) => openRoleTab(page, "记忆"),
    whole: ["你答应周六下午陪我去旧书店", "你说小时候在海边住过一个夏天"],
  },
  // The whole affection tab, scrolled to its end under the sticky tabs: the
  // stage bar, the small steps that led to 朋友 and the stage's tone.
  affection: {
    open: async (page) => {
      await openRoleTab(page, "好感度");
      await page.getByText("已经聊过很多次，算是熟悉了").waitFor();
      await page.getByTestId("role-detail-page").evaluate((element) => element.scrollTo({ top: element.scrollHeight }));
    },
    whole: ["41", "约好周六下午，还记得要靠窗的位子", "已经聊过很多次，算是熟悉了", "阶段语气"],
  },
  // Her two messages after a quiet day, the last one previewed in the list.
  proactive: {
    open: openChatWithStatus,
    whole: ["那就周六下午？顺便去吃你说的那家草莓蛋糕。", "只是周六靠窗的位子，要提前订而已。"],
  },
  // The phone, open on the QQ group where she answers for the user.
  channels: {
    open: async (page) => {
      await openChatWithStatus(page);
      await button(page, "打开手机").click();
      await page.getByRole("button", { name: /^QQ/ }).click();
      await page.getByRole("button").filter({ hasText: "周末读书会" }).click();
    },
    whole: ["我去手机上回一下群消息。", "周六有人去河边那家旧书店吗？", "书店又不是你们家开的。"],
  },
  // Her reply with its three tool calls unfolded.
  plugins: {
    open: async (page) => {
      await openChatWithStatus(page);
      await button(page, "3 次工具调用").click();
    },
    whole: ["那就周六下午？顺便去吃你说的那家草莓蛋糕。", "read_file", "……这种小事，下次自己记着啦。"],
  },
};

/**
 * Fails unless the element showing `text` is wholly on screen: inside the
 * window, and at each of its corners nothing that paints (a background or a
 * backdrop blur) stacked above it, so no scroll edge, header or overlay (the
 * phone) cuts into it. Bare layout wrappers above it, like the phone's
 * full-height positioning layer, do not count. Matches the last element with
 * the text: a chat message is also previewed, shortened, in the list before it.
 */
async function assertWhole(page: Page, id: ShowcaseClipId, text: string) {
  const element = page.getByText(text).last();
  await element.waitFor();
  // Runs in the page: no named inner functions, which tsx would wrap in a
  // helper the page does not have.
  const shown = await element.evaluate((node) => {
    const box = node.getBoundingClientRect();
    if (box.top < 0 || box.left < 0 || box.bottom > innerHeight || box.right > innerWidth) return false;
    const corners = [
      [box.left + 1, box.top + 1],
      [box.right - 1, box.top + 1],
      [box.left + 1, box.bottom - 1],
      [box.right - 1, box.bottom - 1],
    ] as const;
    return corners.every(([x, y]) => {
      for (const hit of document.elementsFromPoint(x, y)) {
        if (node.contains(hit) || hit.contains(node)) return true;
        const style = getComputedStyle(hit);
        const transparent = style.backgroundColor === "transparent" || /rgba\(.*,\s*0\)$/.test(style.backgroundColor);
        if (!transparent || style.backgroundImage !== "none" || style.backdropFilter !== "none") return false;
      }
      return false;
    });
  });
  if (!shown) throw new Error(`${id}: 「${text}」 is cut off or covered`);
}

function python() {
  const venv = resolve(repo, ".venv");
  return process.platform === "win32" ? join(venv, "Scripts", "python.exe") : join(venv, "bin", "python");
}

async function capture(id: ShowcaseClipId, scratch: string) {
  const workspace = join(scratch, id, "workspace");
  execFileSync(
    python(),
    [join(here, "showcase_workspace.py"), "--source", source, "--role", roleName, "--scene", id, "--out", workspace],
    { stdio: "inherit", env: { ...process.env, PYTHONIOENCODING: "utf-8" } },
  );
  const home = join(scratch, id, "home");
  mkdirSync(home, { recursive: true });
  const env: Record<string, string> = {
    ...(process.env as Record<string, string>),
    SHIORI_QA_HOME: home,
    SHIORI_DESKTOP_USER_DATA_DIR: join(scratch, id, "user-data"),
    SHIORI_DESKTOP_WORKSPACE: workspace,
  };
  // The built renderer, not a dev server; Electron as itself, not as Node.
  delete env.SHIORI_RENDERER_DEV_SERVER_URL;
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await _electron.launch({
    executablePath: createRequire(join(desktop, "package.json"))("electron") as string,
    // Points Electron's home at the isolated one before the app reads it.
    args: [join(desktop, "tests/onboarding/electronBootstrap.cjs")],
    env,
    timeout: 60_000,
  });
  try {
    // The hidden plugin-host window may open before the main one.
    const isMainWindow = (window: Page) => new URL(window.url()).pathname.replace(/\/index\.html$/, "/").endsWith("/");
    const page = app.windows().find(isMainWindow) ?? (await app.waitForEvent("window", { predicate: isMainWindow }));
    page.setDefaultTimeout(30_000);
    await page.setViewportSize(WINDOW);
    await page.locator(".app-frame").waitFor();
    await page.getByRole("button", { name: "发送消息" }).waitFor();
    const scene = SCENES[id];
    await scene.open(page);
    // Off every control, on the title bar: no hover state in the picture.
    await page.mouse.move(WINDOW.width / 2, 2);
    await page.waitForTimeout(1_200);
    for (const text of scene.whole) await assertWhole(page, id, text);
    return await page.screenshot({ type: "png" });
  } finally {
    await app.close();
  }
}

for (const built of ["dist/main.js", "renderer-dist/index.html"]) {
  if (!existsSync(join(desktop, built))) {
    throw new Error(`apps/desktop/${built} is missing: run \`pnpm --filter shiori-desktop build\` first`);
  }
}
if (!existsSync(join(source, "roles", "roles.json"))) {
  throw new Error(`no workspace with roles at ${source}: set SHIORI_SHOWCASE_SOURCE`);
}

const ids = clipIdsFromArgs(process.argv.slice(2));
mkdirSync(outDir, { recursive: true });
const scratch = mkdtempSync(join(tmpdir(), "shiori-stills-"));
try {
  const oversized: string[] = [];
  for (const id of ids) {
    const png = await capture(id, scratch);
    const output = resolve(outDir, `${id}.webp`);
    // sharp writes no metadata unless asked to.
    await sharp(png).webp({ quality: WEBP_QUALITY, effort: 6, smartSubsample: true }).toFile(output);
    const bytes = statSync(output).size;
    console.log(`${id}.webp: ${(bytes / 1024).toFixed(0)} KB`);
    if (bytes > SHOWCASE_STILL_MAX_BYTES) oversized.push(`${id}.webp`);
  }
  if (oversized.length > 0) throw new Error(`over ${SHOWCASE_STILL_MAX_BYTES} bytes: ${oversized.join(", ")}`);
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
