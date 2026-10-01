import type { ReactNode } from "react";
import { formatHourMinute } from "../shared/format";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { PetalIcon, SparkleIcon } from "@shiori/sdk";
import { RibbonIcon } from "../shared/ui/icons";

/**
 * 吟风's skin: a bow charm on the top edge, sparkles on the sides and petals
 * drifting along the bottom edge. Sizes come from the --phone-motif-* tokens.
 * Decorative and still (no motion to reduce).
 */
function YinfengBodyMotifs() {
  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 z-[1]">
      <RibbonIcon className="phone-motif-bow absolute -top-5 right-8 rotate-12 text-accent" />
      <SparkleIcon className="phone-motif-lg absolute -left-3.5 top-14 text-lavender" />
      <SparkleIcon className="phone-motif-sm absolute -right-3 bottom-28 text-lavender" />
      <PetalIcon className="phone-motif-sm absolute -right-2.5 top-40 rotate-[30deg] text-accent" />
      <PetalIcon className="phone-motif-lg absolute -bottom-3 left-7 -rotate-45 text-accent" />
      <PetalIcon className="phone-motif-sm absolute -bottom-2.5 left-[34%] rotate-[20deg] text-lavender" />
      <PetalIcon className="phone-motif-sm absolute -bottom-3 right-[30%] -rotate-12 text-accent" />
      <PetalIcon className="phone-motif-lg absolute -bottom-2.5 right-6 rotate-45 text-lavender" />
    </span>
  );
}

/**
 * The phone's body and screen: wallpaper (the role's avatar blurred over the
 * theme gradient, the gradient alone without one), a status bar showing only
 * the real time, the current screen, and the home bar. The body wears
 * 吟风's skin while the 看板娘 is on and a plain one when she is off.
 */
export function PhoneShell({ avatarUrl, now, children }: {
  /** Renderer URL of the role's avatar; `""` when the role has none. */
  avatarUrl: string;
  now: Date;
  children: ReactNode;
}) {
  const themed = useMascotEnabled();
  return (
    <div className="phone-body" data-skin={themed ? "yinfeng" : "plain"} data-testid="phone-body">
      {themed ? <YinfengBodyMotifs /> : null}
      <div className="phone-screen">
        <div className="phone-wallpaper" aria-hidden="true">
          {avatarUrl ? <img className="phone-wallpaper-photo" src={avatarUrl} alt="" /> : null}
        </div>
        <div className="flex h-8 items-end justify-center px-6 pb-0.5">
          <time className="text-caption font-semibold tabular-nums text-ink" dateTime={now.toISOString()}>
            {formatHourMinute(now)}
          </time>
        </div>
        <div className="min-h-0 overflow-hidden">{children}</div>
        <span className="phone-home-bar" aria-hidden="true" />
      </div>
    </div>
  );
}
