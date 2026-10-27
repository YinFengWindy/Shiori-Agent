import fs from "node:fs/promises";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

// The host supplies this fixed runner. Model input is data, never Node code,
// a Space id, a profile id, or a filesystem path.
export async function run(request) {
  const statePath = `${request.root}/space.json`;
  const stopPath = `${request.root}/stopped`;
  const checkAdmission = () => {
    if (existsSync(stopPath)) throw new Error("Browser Use 会话已停止");
  };
  const readState = () => JSON.parse(readFileSync(statePath, "utf8"));
  let result;
  try {
    if (typeof taskSpace !== "function") {
      throw new Error("ego(lite) 接口不兼容，需要支持 TaskSpace/Page API 的版本");
    }
    if (request.operation === "start") {
      checkAdmission();
      const task = await taskSpace(request.name);
      // Synchronous publication closes the startup/cancellation acknowledgment
      // gap: cleanup can now address this exact task without creating one.
      writeFileSync(statePath, JSON.stringify({ id: task.spaceId, handedOff: false }), "utf8");
      if (existsSync(stopPath)) {
        const receipt = await task.finish({ keep: [] });
        writeFileSync(`${request.root}/disposed.json`, JSON.stringify(receipt), "utf8");
        throw new Error("Browser Use 会话已停止");
      }
      result = { spaceId: task.spaceId };
    } else if (request.operation === "close") {
      const state = readState();
      if (existsSync(`${request.root}/disposed.json`)) {
        result = JSON.parse(readFileSync(`${request.root}/disposed.json`, "utf8"));
      } else if (state.handedOff) {
        // The user owns the handed-off Pages; retained scripts are admission
        // gated and cannot reclaim the task without an explicit resume action.
        result = { preservedForUser: true, spaceId: state.id };
      } else {
        const task = await taskSpace(state.id);
        result = await task.finish({ keep: [] });
        writeFileSync(`${request.root}/disposed.json`, JSON.stringify(result), "utf8");
      }
    } else {
      checkAdmission();
      const state = readState();
      const task = request.operation === "resume"
        ? await takeOverTaskSpace(state.id)
        : await taskSpace(state.id);
      if (request.operation === "resume" && existsSync(stopPath)) {
        await task.handOff();
      }
      checkAdmission();
      const arguments_ = request.arguments;
      const page = task.page(arguments_.page || "p1");
      switch (request.operation) {
        case "open":
          await page.goto(arguments_.url, { timeout: request.timeout });
          checkAdmission();
          result = await page.snapshot();
          break;
        case "snapshot":
          result = await page.snapshot({ scope: arguments_.full_page ? "full_page" : "only_within_viewport" });
          break;
        case "actions":
          for (const action of arguments_.actions) {
            checkAdmission();
            switch (action.action) {
              case "click":
                await page.click(action.selector, { timeout: request.timeout, label: "click selected page control" });
                break;
              case "fill": await page.fill(action.selector, action.text, { timeout: request.timeout }); break;
              case "press": await page.press(action.selector, action.key); break;
              case "select": await page.selectOption(action.selector, action.values); break;
              case "hover": await page.hover(action.selector, { timeout: request.timeout, label: "inspect selected page control" }); break;
              case "scroll":
                await page.mouse.move(action.x, action.y, { label: "point at scrollable page" });
                checkAdmission();
                await page.mouse.wheel(action.delta_x || 0, action.delta_y, { label: "scroll selected page area" });
                break;
              case "wait": await page.waitForSelector(action.selector, { timeout: request.timeout }); break;
              default: throw new Error(`不支持的 ego 动作：${action.action}`);
            }
          }
          checkAdmission();
          result = await page.snapshot();
          break;
        case "tabs":
          if (arguments_.action === "new") {
            const created = await task.newPage();
            checkAdmission();
            result = { page: created.label };
          } else if (arguments_.action === "close") {
            // Only task-managed labels can be addressed. User-created tabs are
            // not adopted automatically and remain protected by the SDK.
            if (page.openedBy === "unknown") throw new Error("不能关闭用户拥有的页面");
            await page.close();
            result = { closed: arguments_.page };
          } else {
            result = (await task.tabs()).map(({ label, title, url, openedBy }) => ({ label, title, url, openedBy }));
          }
          break;
        case "screenshot":
          await page.screenshot({ path: `${request.root}/screenshot.png`, fullPage: !!arguments_.full_page });
          result = { screenshot: true };
          break;
        case "handoff":
          await task.handOff();
          writeFileSync(statePath, JSON.stringify({ id: state.id, handedOff: true }), "utf8");
          result = { handoff: true, message: "请在 ego(lite) 中完成登录或操作，确认后继续。" };
          break;
        case "resume":
          writeFileSync(statePath, JSON.stringify({ id: state.id, handedOff: false }), "utf8");
          result = await page.snapshot();
          break;
        default: throw new Error(`不支持的 ego 操作：${request.operation}`);
      }
      checkAdmission();
    }
    result = { ok: true, result };
  } catch (error) {
    result = {
      ok: false,
      error: String(error),
      details: {
        name: typeof error?.name === "string" ? error.name : undefined,
        kind: typeof error?.kind === "string" ? error.kind : undefined,
        error_code: typeof error?.error_code === "string" ? error.error_code : undefined,
        executionStopped: typeof error?.executionStopped === "boolean" ? error.executionStopped : undefined,
        mayHaveLateEffects: typeof error?.mayHaveLateEffects === "boolean" ? error.mayHaveLateEffects : undefined,
      },
    };
  }
  await fs.writeFile(request.output, JSON.stringify(result), "utf8");
}
