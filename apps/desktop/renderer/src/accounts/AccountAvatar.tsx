import { PuzzlePieceIcon } from "@phosphor-icons/react";
import type { ComponentType } from "react";
import { cx } from "../shared/styles";

const sizes = {
  md: { box: "h-9 w-9", icon: "h-5 w-5", badge: "h-4 w-4", badgeIcon: "h-2.5 w-2.5" },
  lg: { box: "h-12 w-12", icon: "h-6 w-6", badge: "h-5 w-5", badgeIcon: "h-3 w-3" },
} as const;

/**
 * An account's own picture with its channel's mark as a corner badge, or —
 * when there is no picture (`avatarUrl` empty, or no account yet) — the
 * channel mark alone on a tile. Decorative: the account name sits beside it.
 */
export function AccountAvatar({ avatarUrl, Icon, size = "md" }: {
  /** Image `data:` URI of the platform account's picture; `""` when unknown. */
  avatarUrl: string;
  /** The channel's mark; a generic plugin mark when the channel has none. */
  Icon?: ComponentType<{ className?: string }>;
  size?: keyof typeof sizes;
}) {
  const ChannelIcon = Icon ?? PuzzlePieceIcon;
  const scale = sizes[size];
  if (!avatarUrl) {
    return <span aria-hidden="true" data-avatar="channel"
      className={cx("grid shrink-0 place-items-center rounded-md bg-surface-soft text-ink-secondary", scale.box)}>
      <ChannelIcon className={scale.icon} />
    </span>;
  }
  return <span aria-hidden="true" data-avatar="account" className={cx("relative shrink-0", scale.box)}>
    <img src={avatarUrl} alt="" className="h-full w-full rounded-full bg-surface-soft object-cover" />
    <span className={cx("absolute -bottom-0.5 -right-0.5 grid place-items-center rounded-full bg-surface text-ink-secondary ring-2 ring-surface", scale.badge)}>
      <ChannelIcon className={scale.badgeIcon} />
    </span>
  </span>;
}
