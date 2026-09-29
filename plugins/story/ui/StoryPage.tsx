import { useEffect, useMemo, useState } from "react";
import { usePluginHostServices, type PluginNavPageComponentProps, type RoleRecord } from "@shiori/plugin-sdk";
import { createStoryBridgeClient } from "./storyBridgeClient";
import { useStoryController } from "./useStoryController";
import { useStoryWorkspacePresentation } from "./useStoryWorkspacePresentation";
import { StoryAppSurface } from "./StoryAppSurface";

/** Owns the full Story route; the shell supplies only RPC, host services and an exit callback. */
export function StoryPage({ client, onExit }: PluginNavPageComponentProps) {
  const host = usePluginHostServices();
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [error, setError] = useState("");
  const storyClient = useMemo(() => createStoryBridgeClient(client), [client]);
  const controller = useStoryController(storyClient);
  useEffect(() => {
    let active = true;
    void host.listRoles().then((next) => { if (active) setRoles(next); }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => { active = false; };
  }, [host]);
  const exit = () => {
    if (!onExit) throw new Error("故事页面缺少退出入口");
    onExit();
  };
  const presentation = useStoryWorkspacePresentation({ roles, client: storyClient, controller, onExit: exit });
  return <StoryAppSurface>{error ? <p className="p-6 text-danger-text" role="alert">{error}</p> : presentation.content}</StoryAppSurface>;
}
