/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type React from "react";
import type { DesktopApi, BridgeResponse } from "../../../src/bridge/shared";
import type { SessionMessage, SessionPayload } from "../shared/types";
import { createDesktopSessionPaginationController } from "./useDesktopSessionPagination";

type InvokeRequest = Parameters<DesktopApi["invoke"]>[0];
type InvokeResponse = Awaited<ReturnType<DesktopApi["invoke"]>>;

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function createSession(
  key: string,
  messages: SessionMessage[],
  nextBeforeSeq = 10,
): SessionPayload {
  const roleId = key.replace(/^role:/, "");
  return {
    key,
    created_at: "2026-07-06T12:00:00+08:00",
    updated_at: "2026-07-06T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: roleId },
    messages,
    pagination: {
      limit: 2,
      has_more: true,
      oldest_seq: messages.reduce<number | null>(
        (oldest, message) => typeof message.seq === "number"
          ? Math.min(oldest ?? message.seq, message.seq)
          : oldest,
        null,
      ),
      newest_seq: messages.reduce<number | null>(
        (newest, message) => typeof message.seq === "number"
          ? Math.max(newest ?? message.seq, message.seq)
          : newest,
        null,
      ),
      total_count: messages.length + 2,
      before_seq: null,
      next_before_seq: nextBeforeSeq,
    },
  };
}

function pageResponse(
  session: SessionPayload,
  messages: SessionMessage[],
  overrides: Partial<NonNullable<SessionPayload["pagination"]>> = {},
): InvokeResponse {
  const pagination = {
    ...session.pagination!,
    ...overrides,
    messages,
  };
  const response: BridgeResponse = {
    id: "response-1",
    type: "response",
    method: "session.messagesPage",
    payload: {
      session: {
        key: session.key,
        created_at: session.created_at,
        updated_at: "2026-07-06T12:01:00+08:00",
        last_consolidated: session.last_consolidated,
        metadata: session.metadata,
      },
      page: pagination,
    },
    error: null,
  };
  return response;
}

function aroundResponse(sessionKey: string, messageId: string, messages: SessionMessage[]): InvokeResponse {
  const response: BridgeResponse = {
    id: "response-around-1",
    type: "response",
    method: "session.messagesAround",
    payload: {
      around: {
        session_key: sessionKey,
        target_message_id: messageId,
        messages,
      },
    },
    error: null,
  };
  return response;
}

function createHarness(initialSession: SessionPayload) {
  const activeRoleIdRef: React.MutableRefObject<string> = { current: "" };
  const activeSessionRef: React.MutableRefObject<SessionPayload | null> = { current: initialSession };
  const generationRef = { current: {} as Record<string, number> };
  const loadingOlderRef = { current: {} as Record<string, boolean> };
  const requests: InvokeRequest[] = [];
  const pending: Deferred<InvokeResponse>[] = [];
  let error = "";
  let updateCount = 0;

  const setError = ((next: React.SetStateAction<string>) => {
    error = typeof next === "function" ? next(error) : next;
  }) as React.Dispatch<React.SetStateAction<string>>;
  const updateCommittedActiveSession = (updater: (current: SessionPayload | null) => SessionPayload | null) => {
    updateCount += 1;
    activeSessionRef.current = updater(activeSessionRef.current);
  };
  const invoke: DesktopApi["invoke"] = (request) => {
    requests.push(request);
    const requestDeferred = deferred<InvokeResponse>();
    pending.push(requestDeferred);
    return requestDeferred.promise;
  };
  const controller = createDesktopSessionPaginationController({
    activeRoleIdRef,
    activeSessionRef,
    setError,
    updateCommittedActiveSession,
    invoke,
    generationRef,
    loadingOlderRef,
  });

  return {
    activeRoleIdRef,
    activeSessionRef,
    controller,
    error: () => error,
    invoke,
    loadingOlderRef,
    pending,
    requests,
    updateCount: () => updateCount,
  };
}

describe("useDesktopSessionPagination request lifecycle", () => {
  it("allows only one older-page request for a cursor while it is in flight", async () => {
    const session = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "最新" },
    ]);
    const harness = createHarness(session);

    const firstRequest = harness.controller.loadOlderMessages();
    const duplicateRequest = harness.controller.loadOlderMessages();

    assert.equal(harness.requests.length, 1);
    assert.equal(harness.requests[0]?.method, "session.messagesPage");
    assert.deepEqual(harness.requests[0]?.payload, {
      role_id: "shiori",
      session_key: "role:shiori",
      before_seq: 10,
      limit: 2,
    });
    assert.equal(await duplicateRequest, false);

    harness.pending[0]!.resolve(pageResponse(session, [
      { id: "role:shiori:8", seq: 8, role: "user", content: "更早" },
    ], {
      has_more: false,
      oldest_seq: 8,
      newest_seq: 10,
      total_count: 2,
      before_seq: 10,
      next_before_seq: null,
    }));

    assert.equal(await firstRequest, true);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), [
      "role:shiori:8",
      "role:shiori:10",
    ]);
  });

  it("drops a resolved page after the active role/session has switched", async () => {
    const oldSession = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "旧会话" },
    ]);
    const nextSession = createSession("role:mira", [
      { id: "role:mira:20", seq: 20, role: "assistant", content: "当前会话" },
    ]);
    const harness = createHarness(oldSession);

    const request = harness.controller.loadOlderMessages(oldSession.key);
    harness.controller.invalidateSessionPagination(oldSession.key);
    harness.activeSessionRef.current = nextSession;
    harness.activeRoleIdRef.current = "mira";
    harness.pending[0]!.resolve(pageResponse(oldSession, [
      { id: "role:shiori:8", seq: 8, role: "user", content: "不应进入当前会话" },
    ], {
      has_more: false,
      oldest_seq: 8,
      newest_seq: 10,
      total_count: 2,
      before_seq: 10,
      next_before_seq: null,
    }));

    assert.equal(await request, false);
    assert.equal(harness.updateCount(), 0);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), ["role:mira:20"]);
    assert.equal(harness.error(), "");
  });

  it("drops a rejected page after the active role/session has switched", async () => {
    const oldSession = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "旧会话" },
    ]);
    const nextSession = createSession("role:mira", [
      { id: "role:mira:20", seq: 20, role: "assistant", content: "当前会话" },
    ]);
    const harness = createHarness(oldSession);

    const request = harness.controller.loadOlderMessages(oldSession.key);
    harness.controller.invalidateSessionPagination(oldSession.key);
    harness.activeSessionRef.current = nextSession;
    harness.activeRoleIdRef.current = "mira";
    harness.pending[0]!.reject(new Error("旧会话分页失败"));

    assert.equal(await request, false);
    assert.equal(harness.updateCount(), 0);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), ["role:mira:20"]);
    assert.equal(harness.error(), "");
  });

  it("drops a rejected around request after a session switch without surfacing its error", async () => {
    const oldSession = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "旧会话" },
    ]);
    const nextSession = createSession("role:mira", [
      { id: "role:mira:20", seq: 20, role: "assistant", content: "当前会话" },
    ]);
    const harness = createHarness(oldSession);

    const request = harness.controller.loadMessagesAround("role:shiori:2", oldSession.key);
    harness.controller.invalidateSessionPagination(oldSession.key);
    harness.activeSessionRef.current = nextSession;
    harness.activeRoleIdRef.current = "mira";
    harness.pending[0]!.reject(new Error("旧会话定位失败"));

    assert.equal(await request, false);
    assert.equal(harness.updateCount(), 0);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), ["role:mira:20"]);
    assert.equal(harness.error(), "");
  });

  it("keeps the current session intact and permits retry after a bridge error", async () => {
    const session = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "最新" },
    ]);
    const harness = createHarness(session);

    const failedRequest = harness.controller.loadOlderMessages();
    harness.pending[0]!.resolve({
      id: "response-error-1",
      type: "response",
      method: "session.messagesPage",
      payload: {},
      error: { code: "TEMPORARY", message: "分页暂时不可用" },
    });

    assert.equal(await failedRequest, false);
    assert.equal(harness.error(), "分页暂时不可用");
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), ["role:shiori:10"]);

    const retryRequest = harness.controller.loadOlderMessages();
    assert.equal(harness.requests.length, 2);
    harness.pending[1]!.resolve(pageResponse(session, [
      { id: "role:shiori:8", seq: 8, role: "user", content: "重试成功" },
    ], {
      has_more: false,
      oldest_seq: 8,
      newest_seq: 10,
      total_count: 2,
      before_seq: 10,
      next_before_seq: null,
    }));

    assert.equal(await retryRequest, true);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), [
      "role:shiori:8",
      "role:shiori:10",
    ]);
  });

  it("merges an older page without replacing optimistic and streaming tail messages", async () => {
    const optimistic = {
      role: "user",
      content: "刚发送的内容",
      metadata: { client_message_id: "client-1" },
    } satisfies SessionMessage;
    const streaming = {
      role: "assistant",
      content: "正在生成",
      streaming: true,
      render_id: "stream-1",
    } satisfies SessionMessage;
    const session = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "最新已保存" },
      optimistic,
      streaming,
    ]);
    const harness = createHarness(session);

    const request = harness.controller.loadOlderMessages();
    harness.pending[0]!.resolve(pageResponse(session, [
      { id: "role:shiori:2", seq: 2, role: "user", content: "更早的消息" },
    ], {
      has_more: false,
      oldest_seq: 2,
      newest_seq: 10,
      total_count: 4,
      before_seq: 10,
      next_before_seq: null,
    }));

    assert.equal(await request, true);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.seq ?? message.render_id), [
      2,
      10,
      undefined,
      "stream-1",
    ]);
    assert.equal(harness.activeSessionRef.current?.messages.at(-2)?.content, "刚发送的内容");
    assert.equal(harness.activeSessionRef.current?.messages.at(-1)?.content, "正在生成");
  });

  it("loads a search context into the expected session after the bridge responds", async () => {
    const session = createSession("role:shiori", [
      { id: "role:shiori:10", seq: 10, role: "assistant", content: "最新" },
    ]);
    const harness = createHarness(session);

    const request = harness.controller.loadMessagesAround(" role:shiori:2 ");
    assert.equal(harness.requests[0]?.method, "session.messagesAround");
    assert.deepEqual(harness.requests[0]?.payload, {
      message_id: "role:shiori:2",
      context: 8,
    });
    harness.pending[0]!.resolve(aroundResponse(session.key, "role:shiori:2", [
      { id: "role:shiori:2", seq: 2, role: "user", content: "命中" },
    ]));

    assert.equal(await request, true);
    assert.deepEqual(harness.activeSessionRef.current?.messages.map((message) => message.id), [
      "role:shiori:2",
      "role:shiori:10",
    ]);
  });
});
