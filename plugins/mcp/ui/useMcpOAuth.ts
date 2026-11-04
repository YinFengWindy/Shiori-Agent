import { useEffect, useRef, useState } from "react";
import { type PluginHostServices } from "@yinfengwindy/shiori-sdk";
import { rpcMethods, type RpcMethod } from "../rpcMethods.generated";
import type { McpSnapshot } from "./types";

/** Browser access is armed only by this renderer's explicit login click. */
export function useMcpOAuth(snapshot: McpSnapshot | null, run: (method: RpcMethod, payload: Record<string, unknown>) => Promise<boolean>, host: PluginHostServices) {
  const requested = useRef(new Map<string, { instanceId: string; previousOperationId: string | null; operationId: string | null }>());
  const opened = useRef(new Set<string>());
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    for (const server of snapshot?.servers ?? []) {
      const operation = server.operation;
      const request = requested.current.get(server.id);
      if (!request) continue;
      if (snapshot?.instance_id !== request.instanceId) { requested.current.delete(server.id); continue; }
      // Busy renders and unrelated events can still contain the preceding login.
      // Only a new operation can consume this click, including a failed retry.
      if (!operation || operation.id === request.previousOperationId) continue;
      if (request.operationId === null && operation.kind === "login") request.operationId = operation.id;
      if (operation.id !== request.operationId) continue;
      if (operation.status !== "running") { requested.current.delete(server.id); continue; }
      if (!operation.authorization_url || opened.current.has(operation.id)) continue;
      opened.current.add(operation.id);
      void host.openExternal(operation.authorization_url).catch(() => {
        if (requested.current.get(server.id) !== request) return;
        setError("无法打开浏览器，请重新登录");
        void run(rpcMethods["operations.cancel"], { server_id: server.id });
      });
    }
  }, [snapshot, host, run]);
  const login = async (server: string) => {
    if (!snapshot) return;
    const request = { instanceId: snapshot.instance_id, previousOperationId: snapshot.servers.find((row) => row.id === server)?.operation?.id ?? null, operationId: null };
    setError(null); requested.current.set(server, request);
    if (!await run(rpcMethods["servers.login"], { server_id: server }) && requested.current.get(server) === request) requested.current.delete(server);
  };
  return { login, error };
}
