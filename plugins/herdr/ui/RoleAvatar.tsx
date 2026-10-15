import { cx, type PluginHostServices, type RoleRecord } from "@yinfengwindy/shiori-sdk";

const avatarClass = "grid h-8 w-8 shrink-0 place-items-center rounded-full border border-line-soft object-cover";

/** The originating role's round avatar, or its initial when it has none or is gone. */
export function RoleAvatar({ role, host }: { role: RoleRecord | undefined; host: PluginHostServices }) {
  const name = role?.name ?? "";
  if (role?.avatar_abs) {
    return <img className={avatarClass} src={host.assets.url(role.avatar_abs)} alt={name} title={name} />;
  }
  return (
    <span className={cx(avatarClass, "bg-surface-soft text-body-sm font-bold text-accent-text")} title={name || undefined} aria-hidden="true">
      {name.slice(0, 1).toUpperCase() || "?"}
    </span>
  );
}
