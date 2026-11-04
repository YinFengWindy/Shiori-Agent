import { useEffect, useRef, useState } from "react";
import { type PluginHostServices } from "@yinfengwindy/shiori-sdk";
import { rpcMethods, type RpcMethod } from "../rpcMethods.generated";
import type { McpSnapshot } from "./types";

/** Browser access is armed only by this renderer's explicit login click. */
export function useMcpOAuth(snapshot: McpSnapshot | null, run: (method: RpcMethod, payload: Record<string, unknown>) => Promise<boolean>, host: PluginHostServices) {
  const requested = useRef(new Set<string>());
  const opened = useRef(new Set<string>());
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    for (const server of snapshot?.servers ?? []) {
      const operation = server.operation;
      if (!requested.current.has(server.id) || operation?.kind !== "login") continue;
      if (operation.status !== "running") { requested.current.delete(server.id); continue; }
      if (!operation.authorization_url || opened.current.has(operation.id)) continue;
      opened.current.add(operation.id);
      void host.openExternal(operation.authorization_url).catch(() => {
        setError("无法打开浏览器，请重新登录");
        void run(rpcMethods["operations.cancel"], { server_id: server.id });
      });
    }
  }, [snapshot, host, run]);
  const login = async (server: string) => {
    setError(null); requested.current.add(server);
    if (!await run(rpcMethods["servers.login"], { server_id: server })) requested.current.delete(server);
  };
  return { login, error };
}
