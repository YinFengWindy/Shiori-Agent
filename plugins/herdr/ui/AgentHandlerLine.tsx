import type { PluginHostServices, RoleRecord } from "@yinfengwindy/shiori-sdk";
import { RoleAvatar } from "./RoleAvatar";
import type { AgentHandler } from "./types";

/**
 * The role the agent's commands are reported to, with its avatar; without
 * one, that nothing sent to the agent is reported.
 */
export function AgentHandlerLine({ handler, findRole, host }: {
  handler: AgentHandler | null;
  findRole: (roleId: string) => RoleRecord | undefined;
  host: PluginHostServices;
}) {
  if (!handler) {
    return <p className="text-body-sm text-ink-muted" aria-label="接手角色">无人接手，不会回报</p>;
  }
  const role = findRole(handler.role_id);
  const name = role?.name || handler.role_name || handler.role_id;
  return (
    <p className="flex min-w-0 items-center gap-2 pt-1 text-body-sm" aria-label="接手角色">
      <RoleAvatar role={role} host={host} />
      <span className="flex-none text-ink-muted">接手</span>
      <span className="min-w-0 truncate font-medium text-ink">{name}</span>
    </p>
  );
}
