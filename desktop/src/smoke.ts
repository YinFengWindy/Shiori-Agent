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
            const clickDropdownItemByText = (text) => {
              const dropdown = Array.from(document.querySelectorAll(".titlebar-dropdown"))
                .find((item) => item.childElementCount > 0);
              if (!dropdown) {
                return false;
              }
              const button = Array.from(dropdown.querySelectorAll("button"))
                .find((item) => (item.textContent || "").trim() === text && !item.disabled);
              if (!button) {
                return false;
              }
              button.click();
              return true;
            };
            const openCreateRolePage = async () => {
              const fileMenu = Array.from(document.querySelectorAll(".titlebar-menu-item"))
                .find((item) => (item.textContent || "").trim() === "文件");
              if (!fileMenu) {
                return { ok: false, reason: "file-menu-missing" };
              }
              fileMenu.click();
              await sleep(50);
              if (!clickByText("新对话")) {
                return { ok: false, reason: "new-chat-entry-missing" };
              }
              let createPage = null;
              let name = null;
              let desc = null;
              let prompt = null;
              let create = null;
              for (let i = 0; i < 40; i++) {
                createPage = document.querySelector('[data-testid="role-create-page"]');
                name = document.querySelector('[data-testid="new-role-name"]');
                desc = document.querySelector('[data-testid="new-role-description"]');
                prompt = document.querySelector('[data-testid="new-role-prompt"]');
                create = document.querySelector('[data-testid="create-role-button"]');
                if (createPage && name && desc && prompt && create) {
                  break;
                }
                await sleep(100);
              }
              if (!createPage || !name || !desc || !prompt || !create) {
                return {
                  ok: false,
                  reason: "create-page-missing",
                  html: document.body.innerHTML.slice(0, 1200),
                };
              }
              const sidebarTrack = document.querySelector(".sidebar-track");
              if (!sidebarTrack || sidebarTrack.getBoundingClientRect().width > 1) {
                return {
                  ok: false,
                  reason: "create-page-sidebar-not-collapsed",
                  sidebarWidth: sidebarTrack?.getBoundingClientRect().width ?? null,
                };
              }
              return { ok: true, name, desc, prompt, create };
            };
            const firstCreatePage = await openCreateRolePage();
            if (!firstCreatePage.ok) {
              return firstCreatePage;
            }
            let name, desc, prompt, create, hero;
            name = firstCreatePage.name;
            desc = firstCreatePage.desc;
            prompt = firstCreatePage.prompt;
            create = firstCreatePage.create;
            for (let i = 0; i < 20; i++) {
              hero = document.querySelector('[data-testid="session-hero"]');
              if (hero) {
                break;
              }
              await sleep(100);
            }
            if (!hero) {
              return {
                ok: false,
                reason: "missing-session-hero",
                html: document.body.innerHTML.slice(0, 800),
              };
            }
            let titlebarRefresh = null;
            let titlebarHelp = null;
            for (let i = 0; i < 20; i++) {
              titlebarRefresh = document.querySelector(".titlebar-refresh");
              titlebarHelp = Array.from(document.querySelectorAll(".titlebar-menu-item"))
                .find((item) => (item.textContent || "").trim() === "帮助");
              if (titlebarRefresh && titlebarHelp) {
                break;
              }
              await sleep(50);
            }
            if (!titlebarRefresh || !titlebarHelp) {
              return {
                ok: false,
                reason: "titlebar-actions-missing",
                titlebarHtml: document.querySelector(".titlebar")?.outerHTML?.slice(0, 1000) ?? "",
                titlebarMenuCount: document.querySelectorAll(".titlebar-menu-item").length,
                refreshCount: document.querySelectorAll(".titlebar-refresh").length,
              };
            }
            titlebarHelp.click();
            await sleep(50);
            if (!(document.body.textContent || "").includes("重启 Bridge")) {
              return {
                ok: false,
                reason: "titlebar-help-menu-missing-actions",
              };
            }
            titlebarHelp.click();
            const viewMenu = Array.from(document.querySelectorAll(".titlebar-menu-item"))
              .find((item) => (item.textContent || "").trim() === "视图");
            if (!viewMenu) {
              return { ok: false, reason: "titlebar-view-menu-missing" };
            }
            viewMenu.click();
            await sleep(50);
            if (!clickDropdownItemByText("设置")) {
              return { ok: false, reason: "settings-entry-missing" };
            }
            let settingsPage = null;
            for (let i = 0; i < 30; i++) {
              settingsPage = document.querySelector('[data-testid="settings-page"]');
              const saveButton = Array.from(document.querySelectorAll("button"))
                .find((item) => (item.textContent || "").trim() === "保存并重启");
              const modelsSection = Array.from(document.querySelectorAll("button"))
                .find((item) => (item.textContent || "").trim() === "模型");
              if (settingsPage && saveButton && modelsSection) {
                break;
              }
              await sleep(100);
            }
            if (!settingsPage) {
              return { ok: false, reason: "settings-page-missing" };
            }
            const settingsBackButton = document.querySelector('[data-testid="settings-back-button"]');
            if (!settingsBackButton) {
              return {
                ok: false,
                reason: "settings-back-missing",
                settingsHtml: settingsPage.outerHTML.slice(0, 1200),
              };
            }
            settingsBackButton.click();
            let sidebarSettingsEntry = null;
            for (let i = 0; i < 40; i++) {
              sidebarSettingsEntry = document.querySelector(".sidebar-top > button");
              hero = document.querySelector('[data-testid="session-hero"]');
              if (hero && sidebarSettingsEntry) {
                break;
              }
              await sleep(100);
            }
            if (!hero) {
              return { ok: false, reason: "session-hero-missing-after-settings-back" };
            }
            if (!sidebarSettingsEntry) {
              return { ok: false, reason: "sidebar-settings-entry-missing" };
            }
            name = firstCreatePage.name;
            desc = firstCreatePage.desc;
            prompt = firstCreatePage.prompt;
            create = firstCreatePage.create;
            setFieldValue(name, roleAName);
            setFieldValue(desc, "ui smoke role A");
            setFieldValue(prompt, "you are ui smoke role A");
            create.click();
            await sleep(20);
            let roleDetailPage = null;
            let detailNameInput = null;
            let createdRoleAButton = null;
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              createdRoleAButton = findRoleButtonByName(roleAName);
              roleDetailPage = document.querySelector('[data-testid="role-detail-page"]');
              detailNameInput = document.querySelector('[data-testid="edit-role-name"]');
              if (createdRoleAButton && roleDetailPage && detailNameInput && detailNameInput.value === roleAName) {
                break;
              }
            }
            if (!createdRoleAButton || !roleDetailPage || !detailNameInput || detailNameInput.value !== roleAName) {
              return {
                ok: false,
                reason: "first-role-not-opened",
                detailValue: detailNameInput?.value || "",
              };
            }
            const secondCreatePage = await openCreateRolePage();
            if (!secondCreatePage.ok) {
              return {
                ok: false,
                reason: secondCreatePage.reason || "second-create-page-missing",
              };
            }
            name = secondCreatePage.name;
            desc = secondCreatePage.desc;
            prompt = secondCreatePage.prompt;
            create = secondCreatePage.create;
            setFieldValue(name, roleBName);
            setFieldValue(desc, "ui smoke role B");
            setFieldValue(prompt, "you are ui smoke role B");
            create.click();
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              roleDetailPage = document.querySelector('[data-testid="role-detail-page"]');
              detailNameInput = document.querySelector('[data-testid="edit-role-name"]');
              if (roleDetailPage && detailNameInput && detailNameInput.value === roleBName) {
                break;
              }
            }
            if (!roleDetailPage || !detailNameInput || detailNameInput.value !== roleBName) {
              return {
                ok: false,
                reason: "second-role-not-opened",
                detailValue: detailNameInput?.value || "",
              };
            }
            if (!clickByText("角色")) {
              return { ok: false, reason: "edit-role-toggle-missing" };
            }
            let roleManagementPage;
            for (let i = 0; i < 30; i++) {
              roleManagementPage = document.querySelector('[data-testid="role-management-page"]');
              if (roleManagementPage) {
                break;
              }
              await sleep(100);
            }
            if (!roleManagementPage) {
              return { ok: false, reason: "role-management-page-missing" };
            }
            const sidebarTrack = document.querySelector(".sidebar-track");
            if (!sidebarTrack || sidebarTrack.getBoundingClientRect().width > 1) {
              return {
                ok: false,
                reason: "role-management-sidebar-not-collapsed",
                sidebarWidth: sidebarTrack?.getBoundingClientRect().width ?? null,
              };
            }
            const roleBManagementCard = Array.from(document.querySelectorAll('[data-testid^="role-management-card-"]'))
              .find((item) => (item.textContent || "").includes(roleBName));
            const roleDetailEntry = roleBManagementCard?.querySelector("button:last-child");
            if (!roleDetailEntry) {
              return { ok: false, reason: "role-detail-entry-missing" };
            }
            roleDetailEntry.click();
            let editName, editDesc, editPrompt, saveRoleButton, pickAvatarButton, pickIllustrationsButton;
            for (let i = 0; i < 40; i++) {
              const roleDetailPage = document.querySelector('[data-testid="role-detail-page"]');
              editName = document.querySelector('[data-testid="edit-role-name"]');
              editDesc = document.querySelector('[data-testid="edit-role-description"]');
              editPrompt = document.querySelector('[data-testid="edit-role-prompt"]');
              saveRoleButton = document.querySelector('[data-testid="save-role-button"]');
              pickAvatarButton = document.querySelector('[data-testid="pick-avatar-button"]');
              pickIllustrationsButton = document.querySelector('[data-testid="pick-illustrations-button"]');
              if (roleDetailPage && editName && editDesc && editPrompt && saveRoleButton && pickAvatarButton && pickIllustrationsButton) {
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
              if (editName.value === roleBEditedName) {
                break;
              }
            }
            if (editName.value !== roleBEditedName) {
              return { ok: false, reason: "edited-role-not-reflected", detailValue: editName.value || "" };
            }
            if (!clickByText("返回角色列表")) {
              return { ok: false, reason: "back-to-role-list-missing" };
            }
            for (let i = 0; i < 30; i++) {
              roleManagementPage = document.querySelector('[data-testid="role-management-page"]');
              if (roleManagementPage) {
                break;
              }
              await sleep(100);
            }
            if (!roleManagementPage) {
              return { ok: false, reason: "role-management-page-missing-after-back" };
            }
            const editedRoleCard = Array.from(document.querySelectorAll('[data-testid^="role-management-card-"]'))
              .find((item) => (item.textContent || "").includes(roleBEditedName));
            const openChatButton = Array.from(editedRoleCard?.querySelectorAll("button") || [])
              .find((item) => (item.textContent || "").trim() === "打开聊天");
            if (!openChatButton) {
              return { ok: false, reason: "open-chat-button-missing" };
            }
            openChatButton.click();
            let chatSurface = null;
            let chatComposer = null;
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              hero = document.querySelector('[data-testid="session-hero"]');
              chatSurface = document.querySelector(".chat-surface");
              chatComposer = document.querySelector(".composer textarea");
              const heroText = hero.textContent || "";
              if (chatSurface && chatComposer && heroText.includes(roleBEditedName)) {
                break;
              }
            }
            if (!chatSurface || !chatComposer) {
              return {
                ok: false,
                reason: "edited-role-chat-not-opened",
                hero: hero.textContent || "",
              };
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
            let sendingHeaderSeen = false;
            for (let i = 0; i < 10; i++) {
              sendingHeaderSeen = (hero.textContent || "").includes("正在输入中...");
              if (!sendingHeaderSeen && composerTextarea.value === "") {
                sendingHeaderSeen = true;
              }
              if (sendingHeaderSeen) {
                break;
              }
              await sleep(50);
            }
            if (!sendingHeaderSeen) {
              return {
                ok: false,
                reason: "chat-header-did-not-show-typing-state",
                hero: hero.textContent || "",
              };
            }
            const cancelStillVisible = Array.from(document.querySelectorAll("button"))
              .some((button) => (button.textContent || "").trim() === "Cancel");
            if (cancelStillVisible) {
              return {
                ok: false,
                reason: "composer-cancel-still-visible-during-send",
              };
            }
            const composerStatusVisible = Boolean(document.querySelector(".composer-status"));
            if (composerStatusVisible) {
              return {
                ok: false,
                reason: "composer-typing-status-still-visible",
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
            for (let i = 0; i < 40; i++) {
              await sleep(100);
              if ((hero.textContent || "").includes(roleBEditedName)) {
                break;
              }
            }
            if (!(hero.textContent || "").includes(roleBEditedName)) {
              return {
                ok: false,
                reason: "chat-header-did-not-reset-after-reply",
                hero: hero.textContent || "",
              };
            }
            if (!clickByText("搜索")) {
              return {
                ok: false,
                reason: "sidebar-search-entry-missing",
              };
            }
            let searchInput;
            for (let i = 0; i < 20; i++) {
              searchInput = document.querySelector('[data-testid="role-search-input"]');
              if (searchInput) {
                break;
              }
              await sleep(50);
            }
            if (!searchInput) {
              return {
                ok: false,
                reason: "search-dialog-input-missing",
              };
            }
            setFieldValue(searchInput, "send via enter");
            let searchResult = null;
            for (let i = 0; i < 60; i++) {
              searchResult = Array.from(document.querySelectorAll('[data-testid^="role-search-result-"]'))
                .find((item) => (item.textContent || "").includes(roleBEditedName));
              if (searchResult) {
                break;
              }
              await sleep(100);
            }
            if (!searchResult) {
              return {
                ok: false,
                reason: "search-result-missing",
                bodyText: (document.body.textContent || "").slice(0, 1200),
              };
            }
            searchResult.click();
            let highlightedMessage = null;
            for (let i = 0; i < 30; i++) {
              await sleep(100);
              highlightedMessage = Array.from(document.querySelectorAll(".message-hit-anchor"))
                .find((item) => (item.textContent || "").includes("send via enter"));
              if (highlightedMessage) {
                break;
              }
            }
            if (!highlightedMessage || !(highlightedMessage.textContent || "").includes("send via enter")) {
              return {
                ok: false,
                reason: "search-result-did-not-highlight-message",
                highlightedText: highlightedMessage?.textContent || "",
              };
            }
            const replyCompletedVisible = (document.body.textContent || "").includes("Reply completed.");
            if (replyCompletedVisible) {
              return {
                ok: false,
                reason: "reply-completed-notice-still-visible",
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
            const returnToRoleAButton = findRoleButtonByName(roleAName);
            if (!returnToRoleAButton) {
              return { ok: false, reason: "missing-role-a-button", count: findRoleButtons().length };
            }
            returnToRoleAButton.click();
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
              const sidebarTrack = document.querySelector(".sidebar-track");
              const rolePane = document.querySelector(".role-pane");
              const handle = document.querySelector(".sidebar-resize-handle");
              const toggle = document.querySelector(".titlebar-sidebar");
              const chatPane = document.querySelector(".chat-pane");
              if (!shell || !sidebarTrack || !rolePane || !handle || !toggle || !chatPane) {
                return { ok: false, reason: "sidebar-resize-elements-missing" };
              }
              const dragTo = (x) => {
                handle.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, clientX: rolePane.getBoundingClientRect().right, pointerId: 1 }));
                window.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, cancelable: true, clientX: x, pointerId: 1 }));
                window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, cancelable: true, clientX: x, pointerId: 1 }));
              };
              dragTo(400);
              await sleep(50);
              let trackRect = sidebarTrack.getBoundingClientRect();
              if (Math.abs(trackRect.width - 400) > 1) {
                return { ok: false, reason: "sidebar-max-resize-mismatch", width: trackRect.width };
              }
              dragTo(220);
              await sleep(50);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (Math.abs(trackRect.width - 220) > 1) {
                return { ok: false, reason: "sidebar-min-resize-mismatch", width: trackRect.width };
              }
              dragTo(180);
              await sleep(50);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (getComputedStyle(rolePane).display === "none" || Math.abs(trackRect.width - 220) > 1) {
                return {
                  ok: false,
                  reason: "sidebar-min-threshold-collapse-mismatch",
                  display: getComputedStyle(rolePane).display,
                  width: trackRect.width,
                };
              }
              dragTo(110);
              await sleep(520);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (rolePane.getAttribute("aria-hidden") !== "true" || trackRect.width > 1) {
                return {
                  ok: false,
                  reason: "sidebar-drag-collapse-missing",
                  ariaHidden: rolePane.getAttribute("aria-hidden"),
                  width: trackRect.width,
                };
              }
              dragTo(140);
              await sleep(520);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (rolePane.getAttribute("aria-hidden") === "true" || Math.abs(trackRect.width - 220) > 1) {
                return {
                  ok: false,
                  reason: "sidebar-drag-expand-missing",
                  ariaHidden: rolePane.getAttribute("aria-hidden"),
                  width: trackRect.width,
                };
              }
              dragTo(320);
              await sleep(50);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (Math.abs(trackRect.width - 320) > 1) {
                return { ok: false, reason: "sidebar-drag-expand-width-mismatch", width: trackRect.width };
              }
              toggle.click();
              await sleep(520);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (rolePane.getAttribute("aria-hidden") !== "true" || trackRect.width > 1) {
                return {
                  ok: false,
                  reason: "sidebar-toggle-collapse-failed",
                  ariaHidden: rolePane.getAttribute("aria-hidden"),
                  width: trackRect.width,
                };
              }
              toggle.click();
              await sleep(520);
              trackRect = sidebarTrack.getBoundingClientRect();
              if (rolePane.getAttribute("aria-hidden") === "true" || Math.abs(trackRect.width - 320) > 1) {
                return {
                  ok: false,
                  reason: "sidebar-toggle-expand-failed",
                  ariaHidden: rolePane.getAttribute("aria-hidden"),
                  width: trackRect.width,
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
          await new Promise((resolve) => setTimeout(resolve, 520));
          const narrowResult = await win.webContents.executeJavaScript(`
            (() => {
              const rolePane = document.querySelector(".role-pane");
              const sidebarTrack = document.querySelector(".sidebar-track");
              const chatPane = document.querySelector(".chat-pane");
              const composer = document.querySelector(".composer");
              if (!rolePane || !sidebarTrack || !chatPane || !composer) {
                return { ok: false, reason: "narrow-layout-elements-missing" };
              }
              const trackRect = sidebarTrack.getBoundingClientRect();
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
              if (rolePane.getAttribute("aria-hidden") !== "true" || trackRect.width > 1) {
                return {
                  ok: false,
                  reason: "role-pane-not-collapsed",
                  ariaHidden: rolePane.getAttribute("aria-hidden"),
                  roleWidth: trackRect.width,
                };
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
          await new Promise((resolve) => setTimeout(resolve, 520));
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
