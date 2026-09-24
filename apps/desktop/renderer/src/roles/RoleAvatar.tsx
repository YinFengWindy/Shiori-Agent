import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

const roleAvatarClass = "role-avatar grid h-8 w-8 place-items-center rounded-full border border-line-soft object-cover";

/** A role's small round avatar for sidebar lists; falls back to its initial when no avatar is set. */
export function RoleAvatar({ role }: { role: Pick<RoleRecord, "name" | "avatar_abs"> }) {
  if (role.avatar_abs) {
    return <img className={roleAvatarClass} src={toFileUrl(role.avatar_abs)} alt={`${role.name} 的头像`} />;
  }
  return (
    <span className={cx(roleAvatarClass, "bg-white/55 text-sm font-bold text-accent-text")}>
      {role.name.slice(0, 1).toUpperCase()}
    </span>
  );
}
