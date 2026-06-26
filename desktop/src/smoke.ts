import { app, type BrowserWindow } from "electron";
import type { DesktopBridgeClient } from "./bridgeClient.js";

/** Attaches Electron-window smoke handlers used by desktop smoke scripts. */
export function attachWindowSmokeHandlers(win: BrowserWindow): void {
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
            if (!clickByText("新对话")) {
              return { ok: false, reason: "new-chat-entry-missing" };
            }
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
            if (!clickByText("角色")) {
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
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if ((document.body.textContent || "").includes("avatar-smoke")) {
                break;
              }
            }
            if (!(document.body.textContent || "").includes("avatar-smoke")) {
              return { ok: false, reason: "avatar-selection-not-reflected" };
            }
            pickIllustrationsButton.click();
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if ((document.body.textContent || "").includes("illustration-smoke")) {
                break;
              }
            }
            if (!(document.body.textContent || "").includes("illustration-smoke")) {
              return { ok: false, reason: "illustration-selection-not-reflected" };
            }
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
            let conversationPanel = null;
            let conversationIllustration = null;
            for (let i = 0; i < 40; i++) {
              conversationPanel = document.querySelector(".conversation-panel");
              conversationIllustration = document.querySelector(".chat-surface .conversation-illustration-image");
              const backgroundImage = conversationIllustration
                ? getComputedStyle(conversationIllustration).backgroundImage
                : "";
              if (backgroundImage.includes("mira-asset://") && backgroundImage.includes("illustration-")) {
                break;
              }
              await sleep(100);
            }
            const backgroundImage = conversationIllustration
              ? getComputedStyle(conversationIllustration).backgroundImage
              : "";
            if (!backgroundImage.includes("mira-asset://") || !backgroundImage.includes("illustration-")) {
              return { ok: false, reason: "chat-illustration-background-missing", backgroundImage };
            }
            const composer = document.querySelector(".composer");
            const composerWrap = document.querySelector(".composer-wrap");
            const chatHeader = document.querySelector(".chat-header");
            const composerTextarea = composer?.querySelector("textarea");
            if (!composer || !composerWrap || !conversationPanel || !chatHeader) {
              return { ok: false, reason: "composer-layout-missing" };
            }
            if (!composerTextarea) {
              return { ok: false, reason: "composer-textarea-missing" };
            }
            const composerRect = composer.getBoundingClientRect();
            const composerWrapRect = composerWrap.getBoundingClientRect();
            const composerTrackRect = composer.parentElement?.getBoundingClientRect();
            const composerTrackStyle = composer.parentElement
              ? getComputedStyle(composer.parentElement)
              : null;
            const composerTrackPadding = composerTrackStyle
              ? parseFloat(composerTrackStyle.paddingLeft) + parseFloat(composerTrackStyle.paddingRight)
              : 0;
            const expectedComposerWidth = composerTrackRect
              ? Math.min(700, composerTrackRect.width) - composerTrackPadding
              : composerRect.width;
            const conversationRect = conversationPanel.getBoundingClientRect();
            const chatHeaderRect = chatHeader.getBoundingClientRect();
            if (Math.abs(chatHeaderRect.height - 55) > 1) {
              return {
                ok: false,
                reason: "chat-header-height-mismatch",
                height: chatHeaderRect.height,
              };
            }
            if (Math.abs(composerRect.width - expectedComposerWidth) > 1 || composerRect.height < 60) {
              return {
                ok: false,
                reason: "composer-size-mismatch",
                width: composerRect.width,
                expectedWidth: expectedComposerWidth,
                height: composerRect.height,
              };
            }
            if (Math.abs(composerWrapRect.bottom - (conversationRect.bottom - 40)) > 1 || Math.abs(composerRect.bottom - (conversationRect.bottom - 40)) > 1) {
              return {
                ok: false,
                reason: "composer-not-bottom-fixed",
                composerBottom: composerRect.bottom,
                wrapBottom: composerWrapRect.bottom,
                conversationBottom: conversationRect.bottom,
              };
            }
            const beforeHeight = composerRect.height;
            const longDraft = Array.from({ length: 12 }, (_, index) => "smoke line " + index).join("\\n");
            setFieldValue(composerTextarea, longDraft);
            await sleep(100);
            const expandedComposerRect = composer.getBoundingClientRect();
            const textareaOverflowY = getComputedStyle(composerTextarea).overflowY;
            if (expandedComposerRect.height <= beforeHeight + 20) {
              return {
                ok: false,
                reason: "composer-did-not-expand",
                beforeHeight,
                afterHeight: expandedComposerRect.height,
              };
            }
            if (composerTextarea.scrollHeight > composerTextarea.clientHeight + 1) {
              return {
                ok: false,
                reason: "composer-textarea-scrollbar-visible",
                scrollHeight: composerTextarea.scrollHeight,
                clientHeight: composerTextarea.clientHeight,
                overflowY: textareaOverflowY,
              };
            }
            if (textareaOverflowY !== "hidden") {
              return {
                ok: false,
                reason: "composer-textarea-overflow-not-hidden",
                overflowY: textareaOverflowY,
              };
            }
            setFieldValue(composerTextarea, "send via enter");
            await sleep(50);
            const plainEnterDispatched = composerTextarea.dispatchEvent(new KeyboardEvent("keydown", {
              key: "Enter",
              bubbles: true,
              cancelable: true,
            }));
            if (plainEnterDispatched !== false) {
              return {
                ok: false,
                reason: "composer-enter-not-intercepted",
              };
            }
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if (composerTextarea.value === "") {
                break;
              }
            }
            if (composerTextarea.value !== "") {
              return {
                ok: false,
                reason: "composer-enter-did-not-send",
                value: composerTextarea.value,
              };
            }
            setFieldValue(composerTextarea, "keep composing");
            await sleep(50);
            const ctrlEnterDispatched = composerTextarea.dispatchEvent(new KeyboardEvent("keydown", {
              key: "Enter",
              ctrlKey: true,
              bubbles: true,
              cancelable: true,
            }));
            if (ctrlEnterDispatched !== true) {
              return {
                ok: false,
                reason: "composer-ctrl-enter-was-blocked",
              };
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
        if (result?.ok === true) {
          const resizeResult = await win.webContents.executeJavaScript(`
            (async () => {
              const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
              const shell = document.querySelector(".desktop-shell");
              const rolePane = document.querySelector(".role-pane");
              const handle = document.querySelector(".sidebar-resize-handle");
              const toggle = document.querySelector(".titlebar-sidebar");
              const chatPane = document.querySelector(".chat-pane");
              if (!shell || !rolePane || !handle || !toggle || !chatPane) {
                return { ok: false, reason: "sidebar-resize-elements-missing" };
              }
              const dragTo = (x) => {
                handle.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, clientX: rolePane.getBoundingClientRect().right, pointerId: 1 }));
                window.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, cancelable: true, clientX: x, pointerId: 1 }));
                window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, cancelable: true, clientX: x, pointerId: 1 }));
              };
              dragTo(720);
              await sleep(50);
              let roleRect = rolePane.getBoundingClientRect();
              if (Math.abs(roleRect.width - 720) > 1) {
                return { ok: false, reason: "sidebar-max-resize-mismatch", width: roleRect.width };
              }
              dragTo(360);
              await sleep(50);
              roleRect = rolePane.getBoundingClientRect();
              if (Math.abs(roleRect.width - 360) > 1) {
                return { ok: false, reason: "sidebar-min-resize-mismatch", width: roleRect.width };
              }
              dragTo(340);
              await sleep(50);
              if (getComputedStyle(rolePane).display !== "none") {
                return { ok: false, reason: "sidebar-drag-collapse-missing", display: getComputedStyle(rolePane).display };
              }
              toggle.click();
              await sleep(50);
              roleRect = rolePane.getBoundingClientRect();
              if (getComputedStyle(rolePane).display === "none" || Math.abs(roleRect.width - 360) > 1) {
                return {
                  ok: false,
                  reason: "sidebar-toggle-expand-failed",
                  display: getComputedStyle(rolePane).display,
                  width: roleRect.width,
                };
              }
              return { ok: true };
            })();
          `);
          if (resizeResult?.ok !== true) {
            console.log(`[desktop-ui-smoke] ${JSON.stringify(resizeResult)}`);
            app.exit(1);
            return;
          }
          win.setSize(900, 760);
          await win.webContents.executeJavaScript(`window.dispatchEvent(new Event("resize"));`);
          await new Promise((resolve) => setTimeout(resolve, 150));
          const narrowResult = await win.webContents.executeJavaScript(`
            (() => {
              const rolePane = document.querySelector(".role-pane");
              const chatPane = document.querySelector(".chat-pane");
              const composer = document.querySelector(".composer");
              if (!rolePane || !chatPane || !composer) {
                return { ok: false, reason: "narrow-layout-elements-missing" };
              }
              const roleDisplay = getComputedStyle(rolePane).display;
              const chatRect = chatPane.getBoundingClientRect();
              const composerRect = composer.getBoundingClientRect();
              const composerTrackRect = composer.parentElement?.getBoundingClientRect();
              const composerTrackStyle = composer.parentElement
                ? getComputedStyle(composer.parentElement)
                : null;
              const composerTrackPadding = composerTrackStyle
                ? parseFloat(composerTrackStyle.paddingLeft) + parseFloat(composerTrackStyle.paddingRight)
                : 0;
              const expectedComposerWidth = composerTrackRect
                ? Math.min(700, composerTrackRect.width) - composerTrackPadding
                : composerRect.width;
              const expectedComposerCenter = chatRect.left + chatRect.width / 2;
              const actualComposerCenter = composerRect.left + composerRect.width / 2;
              if (roleDisplay !== "none") {
                return { ok: false, reason: "role-pane-not-collapsed", roleDisplay };
              }
              if (chatRect.left > 1 || Math.abs(chatRect.width - window.innerWidth) > 2) {
                return {
                  ok: false,
                  reason: "chat-pane-not-full-width",
                  chatLeft: chatRect.left,
                  chatWidth: chatRect.width,
                  windowWidth: window.innerWidth,
                };
              }
              if (Math.abs(composerRect.width - expectedComposerWidth) > 1 || Math.abs(actualComposerCenter - expectedComposerCenter) > 2) {
                return {
                  ok: false,
                  reason: "narrow-composer-not-centered",
                  composerWidth: composerRect.width,
                  expectedWidth: expectedComposerWidth,
                  centerOffset: actualComposerCenter - expectedComposerCenter,
                };
              }
              return { ok: true };
            })();
          `);
          if (narrowResult?.ok !== true) {
            console.log(`[desktop-ui-smoke] ${JSON.stringify(narrowResult)}`);
            app.exit(1);
            return;
          }
          win.setSize(540, 760);
          await win.webContents.executeJavaScript(`window.dispatchEvent(new Event("resize"));`);
          await new Promise((resolve) => setTimeout(resolve, 150));
          const compactResult = await win.webContents.executeJavaScript(`
            (() => {
              const composer = document.querySelector(".composer");
              const composerWrap = document.querySelector(".composer-wrap");
              if (!composer || !composerWrap) {
                return { ok: false, reason: "compact-layout-elements-missing" };
              }
              const composerRect = composer.getBoundingClientRect();
              const composerTrackRect = composer.parentElement?.getBoundingClientRect();
              const composerTrackStyle = composer.parentElement
                ? getComputedStyle(composer.parentElement)
                : null;
              const composerTrackPadding = composerTrackStyle
                ? parseFloat(composerTrackStyle.paddingLeft) + parseFloat(composerTrackStyle.paddingRight)
                : 0;
              const expectedWidth = composerTrackRect
                ? Math.min(700, composerTrackRect.width) - composerTrackPadding
                : composerRect.width;
              if (composerRect.width > 652 || Math.abs(composerRect.width - expectedWidth) > 2) {
                return {
                  ok: false,
                  reason: "compact-composer-not-shrunk",
                  composerWidth: composerRect.width,
                  expectedWidth,
                  trackWidth: composerTrackRect?.width,
                };
              }
              return { ok: true };
            })();
          `);
          if (compactResult?.ok !== true) {
            console.log(`[desktop-ui-smoke] ${JSON.stringify(compactResult)}`);
            app.exit(1);
            return;
          }
        }
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
}

/** Runs the bridge-level smoke test exposed to the renderer preload API. */
export async function runBridgeSmoke(bridge: DesktopBridgeClient) {
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
}
