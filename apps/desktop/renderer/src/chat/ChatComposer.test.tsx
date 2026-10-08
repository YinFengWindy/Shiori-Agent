/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { changeInputValue, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { ChatComposer } from "./ChatComposer";
import { getChatDraft, getChatDraftKey, updateChatDraft } from "./chatDraftStore";
import { getFeedbackSnapshot, resetFeedback } from "../shared/feedback/feedbackStore";
import type { ChatSendRequest } from "../shared/types";

function composerElement(role: string, props: Partial<React.ComponentProps<typeof ChatComposer>> = {}) {
  return <ChatComposer activeRoleId={role} sessionKey={`role:${role}`} bridgeReady sending={false} cancelling={false}
    onSendMessage={async () => true} onCancelChat={() => undefined} onJumpToMessage={() => undefined} {...props} />;
}

function fakeDesktop() {
  return {
    invoke: async () => ({ payload: { roles: [] }, error: null }),
    readSettings: async () => ({ formData: { models: { registrations: [] } } }),
    onEvent: () => () => undefined,
    localAssetUrl: (path: string) => `shiori-asset://local/${path}`,
    pickChatAttachments: async () => [] as string[],
    importChatImages: async (files: File[]) => files.map((file) => `/${file.name}`),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

async function dropFiles(view: Awaited<ReturnType<typeof mountTestComponent>>, files: File[]) {
  const event = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", { value: { types: ["Files"], files } });
  await act(async () => { view.container.querySelector("textarea")!.dispatchEvent(event); });
  return event;
}

function renderChatComposer({
  sending = false,
  cancelling = false,
}: { sending?: boolean; cancelling?: boolean } = {}): string {
  return renderToStaticMarkup(
    <ChatComposer
      activeRoleId="mira"
      sessionKey="role:mira"
      bridgeReady
      sending={sending}
      cancelling={cancelling}
      onSendMessage={async () => true}
      onCancelChat={() => undefined}
      onJumpToMessage={() => undefined}
    />,
  );
}

describe("ChatComposer", () => {
  it("drops multiple images without sending, merges picker duplicates, removes a preview and sends the remainder", async () => {
    const desktop = fakeDesktop();
    const sent: ChatSendRequest[] = [];
    let imported: File[] = [];
    desktop.importChatImages = async (files) => { imported = files; return ["/one.png", "/two.png"]; };
    desktop.pickChatAttachments = async () => ["/one.png", "/three.png"];
    const view = await mountTestComponent(composerElement("images", { onSendMessage: async (request) => { sent.push(request); return true; } }),
      { windowGlobals: { miraDesktop: desktop } });
    try {
      await changeInputValue(view.container.querySelector("textarea")!, "正文");
      const files = [new File(["one"], "one.png"), new File(["two"], "two.png")];
      assert.equal((await dropFiles(view, files)).defaultPrevented, true);
      assert.deepEqual(imported, files);
      assert.equal(sent.length, 0);
      assert.equal(view.container.querySelector("textarea")!.value, "正文");
      assert.equal(view.container.querySelectorAll('[data-testid="composer-attachments"] img').length, 2);
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="添加附件"]')!.click(); });
      assert.equal(view.container.querySelectorAll('[aria-label="移除图片附件"]').length, 3);
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="移除图片附件"]')!.click(); });
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="发送消息"]')!.click(); });
      assert.deepEqual(sent, [{ content: "正文", attachments: ["/two.png", "/three.png"], replyTarget: null }]);
      assert.equal(view.container.querySelector("textarea")!.value, "");
      assert.equal(view.container.querySelector('[data-testid="composer-attachments"]'), null);
      await dropFiles(view, files);
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="发送消息"]')!.click(); });
      assert.deepEqual(sent[1], { content: "", attachments: ["/one.png", "/two.png"], replyTarget: null });
    } finally { await view.cleanup(); }
  });

  it("prevents disabled file navigation while leaving ordinary text drags alone", async () => {
    let imports = 0;
    const desktop = fakeDesktop();
    desktop.importChatImages = async () => { imports += 1; return ["/disabled.png"]; };
    const view = await mountTestComponent(composerElement("disabled", { bridgeReady: false }), { windowGlobals: { miraDesktop: desktop } });
    try {
      for (const props of [{ bridgeReady: false }, { sending: true }, { activeRoleId: "" }]) {
        await view.render(composerElement("disabled", props));
        assert.equal((await dropFiles(view, [new File(["a"], "a.png")])).defaultPrevented, true);
        const transfer = { types: ["Files"], dropEffect: "copy" };
        const over = new Event("dragover", { bubbles: true, cancelable: true });
        Object.defineProperty(over, "dataTransfer", { value: transfer });
        view.container.querySelector("textarea")!.dispatchEvent(over);
        assert.equal(over.defaultPrevented, true);
        assert.equal(transfer.dropEffect, "none");
      }
      assert.equal(imports, 0);
      const text = new Event("drop", { bubbles: true, cancelable: true });
      Object.defineProperty(text, "dataTransfer", { value: { types: ["text/plain"], files: [] } });
      view.container.querySelector("textarea")!.dispatchEvent(text);
      assert.equal(text.defaultPrevented, false);
    } finally { await view.cleanup(); }
  });

  it("finishes asynchronous picker and drop imports in their source draft after navigation and unmount", async () => {
    for (const mode of ["picker", "drop"]) {
      const source = `import-${mode}`;
      const result = deferred<string[]>();
      const desktop = fakeDesktop();
      desktop.pickChatAttachments = () => result.promise;
      desktop.importChatImages = () => result.promise;
      const view = await mountTestComponent(composerElement(source), { windowGlobals: { miraDesktop: desktop } });
      try {
        await changeInputValue(view.container.querySelector("textarea")!, "原会话");
        if (mode === "drop") await dropFiles(view, [new File(["a"], "a.png")]);
        else await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="添加附件"]')!.click(); });
        await view.render(composerElement(`${source}-other`, { sessionKey: `role:${source}` }));
        await changeInputValue(view.container.querySelector("textarea")!, "另一会话");
        await view.render(null);
        await act(async () => { result.resolve(["/late.png"]); });
        await view.render(composerElement(source, { sessionKey: "" }));
        assert.equal(view.container.querySelector("textarea")!.value, "原会话");
        assert.equal(view.container.querySelectorAll('[data-testid="composer-attachments"] img').length, 1);
        await view.render(composerElement(`${source}-other`));
        assert.equal(view.container.querySelector("textarea")!.value, "另一会话");
        assert.equal(view.container.querySelector('[data-testid="composer-attachments"]'), null);
      } finally { await view.cleanup(); }
    }
  });

  it("shows import failures without altering the text or existing attachments", async () => {
    const desktop = fakeDesktop();
    desktop.pickChatAttachments = async () => ["/existing.png"];
    desktop.importChatImages = async () => { throw new Error("图片超过大小限制"); };
    const view = await mountTestComponent(composerElement("import-error"), { windowGlobals: { miraDesktop: desktop } });
    try {
      await changeInputValue(view.container.querySelector("textarea")!, "保留我");
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="添加附件"]')!.click(); });
      resetFeedback();
      await dropFiles(view, [new File(["large"], "large.png")]);
      assert.equal(view.container.querySelector("textarea")!.value, "保留我");
      assert.equal(view.container.querySelectorAll('[data-testid="composer-attachments"] img').length, 1);
      assert.match(getFeedbackSnapshot()[0]?.message ?? "", /附件导入失败.*图片超过大小限制/);
    } finally { await view.cleanup(); }
  });

  it("restores a failed send including its quote while unmounted and protects later edits", async () => {
    const role = "send-race";
    const key = getChatDraftKey(role);
    const request = { content: "待发送", attachments: ["/quoted.png"], replyTarget: { messageId: "m1", content: "被引用", preview: "被引用", sender: "Mira" } };
    updateChatDraft(key, () => request);
    const result = deferred<boolean>();
    const view = await mountTestComponent(composerElement(role, { onSendMessage: () => result.promise }), { windowGlobals: { miraDesktop: fakeDesktop() } });
    try {
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="发送消息"]')!.click(); });
      assert.equal(view.container.querySelector('[aria-label="取消引用"]'), null);
      await view.render(composerElement("send-race-other"));
      await changeInputValue(view.container.querySelector("textarea")!, "其他草稿");
      await view.render(null);
      await act(async () => { result.resolve(false); });
      await view.render(composerElement(role));
      assert.equal(view.container.querySelector("textarea")!.value, "待发送");
      assert.ok(view.container.querySelector('[aria-label="取消引用"]'));
      assert.equal(view.container.querySelectorAll('[data-testid="composer-attachments"] img').length, 1);
      const next = deferred<boolean>();
      await view.render(composerElement(role, { onSendMessage: () => next.promise }));
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[aria-label="发送消息"]')!.click(); });
      await changeInputValue(view.container.querySelector("textarea")!, "新编辑");
      await act(async () => { next.resolve(false); });
      assert.equal(view.container.querySelector("textarea")!.value, "新编辑");
      assert.equal(getChatDraft("role:send-race-other").content, "其他草稿");
    } finally { await view.cleanup(); }
  });
  it("restores the typed draft after switching roles and leaving the page", async () => {
    const composer = (role: string) => <ChatComposer activeRoleId={role} sessionKey={`role:${role}`} bridgeReady={false}
      sending={false} cancelling={false}
      onSendMessage={async () => true} onCancelChat={() => undefined} onJumpToMessage={() => undefined} />;
    const view = await mountTestComponent(composer("draft-a"), { windowGlobals: { miraDesktop: { onEvent: () => () => undefined } } });
    try {
      const input = () => view.container.querySelector("textarea")!;
      await changeInputValue(input(), "A 的草稿");
      await view.render(composer("draft-b"));
      assert.equal(input().value, "");
      await changeInputValue(input(), "B 的草稿");
      await view.render(composer("draft-a"));
      assert.equal(input().value, "A 的草稿");
      await view.render(null);
      await view.render(composer("draft-b"));
      assert.equal(input().value, "B 的草稿");
    } finally { await view.cleanup(); }
  });
  it("renders attachment, emoji, and send actions in the desktop composer", () => {
    const markup = renderChatComposer();

    assert.match(markup, /aria-label="添加附件"/);
    assert.match(markup, /aria-label="打开常用表情面板"/);
    assert.match(markup, /aria-label="发送消息"/);
  });

  it("replaces send with a stable stop action while a reply streams", () => {
    const markup = renderChatComposer({ sending: true });

    assert.match(markup, /aria-label="中止回复"/);
    assert.doesNotMatch(markup, /aria-label="发送消息"/);
  });

  it("disables the stop action while cancellation is in progress", () => {
    const markup = renderChatComposer({ sending: true, cancelling: true });

    assert.match(markup, /aria-label="中止回复"[^>]*disabled=""/);
  });

  it("uses a contained text mirror instead of synchronous textarea measurement", () => {
    const markup = renderChatComposer();

    assert.match(markup, /data-autosize-textarea-mirror=""/);
    assert.match(markup, /contain:layout/);
    assert.doesNotMatch(markup, /field-sizing/);
  });

  it("does not intercept pointer events outside the visible composer", () => {
    const markup = renderChatComposer();

    assert.match(markup, /composer-wrap pointer-events-none/);
    assert.match(markup, /pointer-events-auto mx-auto w-full max-w-\[700px\]/);
  });
});
