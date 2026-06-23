import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DesktopBridgeClient } from "./bridgeClient.js";
import type { IpcMainInvokeEvent } from "electron";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const rendererDist = resolve(desktopRoot, "renderer-dist", "index.html");

const bridge = new DesktopBridgeClient();

function createWindow() {
  const win = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: "#f4efe6",
    webPreferences: {
      preload: resolve(here, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    },
  });
  win.webContents.on("console-message", (_event, _level, message) => {
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.log(`[desktop-ui-console] ${message}`);
    }
  });
  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
      console.error(`[desktop-ui-load-fail] ${errorCode} ${errorDescription}`);
    }
  });
  void win.loadFile(rendererDist);
  if (process.env.MIRA_DESKTOP_UI_SMOKE === "1") {
    win.webContents.on("did-finish-load", async () => {
      try {
        console.log("[desktop-ui-smoke] renderer loaded");
        const result = await win.webContents.executeJavaScript(`
          (async () => {
            const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const smokeId = Date.now().toString(36);
            const roleAName = "Smoke UI Role A " + smokeId;
            const roleBName = "Smoke UI Role B " + smokeId;
            const roleBEditedName = roleBName + " Edited";
            const setFieldValue = (element, value) => {
              const prototype = element instanceof HTMLTextAreaElement
                ? HTMLTextAreaElement.prototype
                : HTMLInputElement.prototype;
              const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
              descriptor?.set?.call(element, value);
              element.dispatchEvent(new Event("input", { bubbles: true }));
              element.dispatchEvent(new Event("change", { bubbles: true }));
            };
            const findRoleButtons = () =>
              Array.from(document.querySelectorAll('[data-testid="role-list"] button'));
            const findRoleButtonByName = (name) =>
              findRoleButtons().find((button) => (button.textContent || "").includes(name));
            const clickByText = (text) => {
              const button = Array.from(document.querySelectorAll("button"))
                .find((item) => (item.textContent || "").trim() === text && !item.disabled);
              if (!button) {
                return false;
              }
              button.click();
              return true;
            };
            let name, desc, prompt, create, hero;
            for (let i = 0; i < 40; i++) {
              name = document.querySelector('[data-testid="new-role-name"]');
              desc = document.querySelector('[data-testid="new-role-description"]');
              prompt = document.querySelector('[data-testid="new-role-prompt"]');
              create = document.querySelector('[data-testid="create-role-button"]');
              hero = document.querySelector('[data-testid="session-hero"]');
              if (name && desc && prompt && create && hero) {
                break;
              }
              await sleep(100);
            }
            if (!name || !desc || !prompt || !create || !hero) {
              return {
                ok: false,
                reason: "missing-elements",
                html: document.body.innerHTML.slice(0, 800),
              };
            }
            for (let i = 0; i < 40; i++) {
              if (!create.disabled) {
                break;
              }
              await sleep(100);
            }
            setFieldValue(name, roleAName);
            setFieldValue(desc, "ui smoke role A");
            setFieldValue(prompt, "you are ui smoke role A");
            create.click();
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if (hero.textContent && hero.textContent.includes(roleAName)) {
                break;
              }
            }
            if (!hero.textContent || !hero.textContent.includes(roleAName)) {
              return { ok: false, reason: "first-role-not-opened", hero: hero.textContent || "" };
            }
            setFieldValue(name, roleBName);
            setFieldValue(desc, "ui smoke role B");
            setFieldValue(prompt, "you are ui smoke role B");
            create.click();
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if (hero.textContent && hero.textContent.includes(roleBName)) {
                break;
              }
            }
            if (!hero.textContent || !hero.textContent.includes(roleBName)) {
              return { ok: false, reason: "second-role-not-opened", hero: hero.textContent || "" };
            }
            if (!clickByText("Edit Role")) {
              return { ok: false, reason: "edit-role-toggle-missing" };
            }
            let editName, editDesc, editPrompt, saveRoleButton, pickAvatarButton, pickIllustrationsButton;
            for (let i = 0; i < 40; i++) {
              editName = document.querySelector('[data-testid="edit-role-name"]');
              editDesc = document.querySelector('[data-testid="edit-role-description"]');
              editPrompt = document.querySelector('[data-testid="edit-role-prompt"]');
              saveRoleButton = document.querySelector('[data-testid="save-role-button"]');
              pickAvatarButton = document.querySelector('[data-testid="pick-avatar-button"]');
              pickIllustrationsButton = document.querySelector('[data-testid="pick-illustrations-button"]');
              if (editName && editDesc && editPrompt && saveRoleButton && pickAvatarButton && pickIllustrationsButton) {
                break;
              }
              await sleep(100);
            }
            if (!editName || !editDesc || !editPrompt || !saveRoleButton || !pickAvatarButton || !pickIllustrationsButton) {
              return { ok: false, reason: "role-editor-elements-missing" };
            }
            setFieldValue(editName, roleBEditedName);
            setFieldValue(editDesc, "ui smoke role B edited");
            setFieldValue(editPrompt, "you are ui smoke role B edited");
            pickAvatarButton.click();
            await sleep(150);
            pickIllustrationsButton.click();
            await sleep(150);
            if (saveRoleButton.disabled) {
              return { ok: false, reason: "save-role-disabled-after-edit" };
            }
            saveRoleButton.click();
            for (let i = 0; i < 50; i++) {
              await sleep(100);
              if (hero.textContent && hero.textContent.includes(roleBEditedName)) {
                break;
              }
            }
            if (!hero.textContent || !hero.textContent.includes(roleBEditedName)) {
              return { ok: false, reason: "edited-role-not-reflected", hero: hero.textContent || "" };
            }
            const heroImage = document.querySelector(".hero-illustration");
            if (!heroImage) {
              return { ok: false, reason: "hero-illustration-missing-after-upload" };
            }
            const roleAButton = findRoleButtonByName(roleAName);
            if (!roleAButton) {
              return { ok: false, reason: "missing-role-a-button", count: findRoleButtons().length };
            }
            roleAButton.click();
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if (hero.textContent && hero.textContent.includes(roleAName)) {
                return {
                  ok: true,
                  hero: hero.textContent,
                  roleCount: findRoleButtons().length,
                };
              }
            }
            return { ok: false, reason: "role-switch-failed", hero: hero.textContent || "" };
          })();
        `);
        console.log(`[desktop-ui-smoke] ${JSON.stringify(result)}`);
        app.exit(result?.ok ? 0 : 1);
      } catch (error) {
        console.error("[desktop-ui-smoke] failed", error);
        app.exit(1);
      }
    });
  } else if (process.env.MIRA_DESKTOP_SMOKE === "1") {
    win.webContents.on("did-finish-load", async () => {
      try {
        console.log("[desktop-smoke] renderer loaded");
        const result = await win.webContents.executeJavaScript("window.miraDesktop.smoke()");
        console.log(`[desktop-smoke] ${JSON.stringify(result)}`);
        app.exit(0);
      } catch (error) {
        console.error("[desktop-smoke] failed", error);
        app.exit(1);
      }
    });
  }
  return win;
}

app.whenReady().then(() => {
  (async () => {
    try {
      await bridge.start();
    } catch (error) {
      console.error("[desktop] bridge start failed", error);
    }
  })();
  bridge.on("event", (payload) => {
    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:event", payload);
    }
  });
  bridge.on("exit", (message) => {
    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:event", {
        id: "bridge-exit",
        type: "event",
        method: "bridge.exit",
        payload: { message },
      });
    }
  });
  ipcMain.handle("desktop:invoke", async (_event: IpcMainInvokeEvent, request: { method: string; payload: Record<string, unknown> }) => {
    return await bridge.invoke(request);
  });
  ipcMain.handle("desktop:bridge-status", async () => {
    return {
      running: bridge.isRunning(),
      lastError: bridge.getLastError(),
    };
  });
  ipcMain.handle("desktop:bridge-restart", async () => {
    try {
      await bridge.restart();
      return {
        ok: true,
        running: bridge.isRunning(),
        lastError: bridge.getLastError(),
      };
    } catch (error) {
      return {
        ok: false,
        running: false,
        lastError: String(error),
      };
    }
  });
  ipcMain.handle("desktop:pick-images", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    if (process.env.MIRA_DESKTOP_PICK_IMAGES_FIXTURE === "1") {
      const fixtureDir = resolve(desktopRoot, ".smoke-fixtures");
      mkdirSync(fixtureDir, { recursive: true });
      const avatarPath = resolve(fixtureDir, "avatar-smoke.png");
      const illustrationPath = resolve(fixtureDir, "illustration-smoke.png");
      writeFileSync(avatarPath, "avatar-smoke");
      writeFileSync(illustrationPath, "illustration-smoke");
      return options?.multiple ? [avatarPath, illustrationPath] : [avatarPath];
    }
    const result = await dialog.showOpenDialog({
      properties: options?.multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [
        {
          name: "Images",
          extensions: ["png", "jpg", "jpeg", "webp", "gif"],
        },
      ],
    });
    if (result.canceled) {
      return [];
    }
    return result.filePaths;
  });
  ipcMain.handle("desktop:smoke", async () => {
    const status = {
      running: bridge.isRunning(),
      lastError: bridge.getLastError(),
    };
    const health = await bridge.invoke({ method: "health", payload: {} });
    const roles = await bridge.invoke({ method: "roles.list", payload: {} });
    await bridge.restart();
    const restarted = {
      ok: true,
      running: bridge.isRunning(),
      lastError: bridge.getLastError(),
    };
    const healthAfterRestart = await bridge.invoke({ method: "health", payload: {} });
    const createdRole = await bridge.invoke({
      method: "roles.create",
      payload: {
        name: "Smoke Role",
        description: "desktop smoke role",
        system_prompt: "you are smoke role",
      },
    });
    const createdPayload = createdRole.payload as {
      role?: { id?: string };
    };
    const roleId = String(createdPayload.role?.id ?? "");
    const openedSession = await bridge.invoke({
      method: "session.openByRole",
      payload: { role_id: roleId },
    });
    const deletedRole = await bridge.invoke({
      method: "roles.delete",
      payload: { role_id: roleId },
    });
    return {
      status,
      health,
      roles,
      restarted,
      healthAfterRestart,
      createdRole,
      openedSession,
      deletedRole,
    };
  });
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  bridge.stop();
});

export { bridge };
