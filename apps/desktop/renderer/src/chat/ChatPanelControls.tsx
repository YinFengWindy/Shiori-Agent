import { Images, ListChecks, SidebarSimple, Smiley, type Icon } from "@phosphor-icons/react";
import { compactPressableClass, cx } from "../shared/styles";
import { Tooltip } from "../shared/ui/Tooltip";
import type { ChatPanelBadges } from "./chatPanelBadges";
import type { ChatSidebarMode } from "./ChatRightSidebar";

const badgeDotClass = "absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-accent ring-2 ring-surface";

/** The chat header's toggle for the role panel (状态 / 任务 / 图片), with a dot while something new is unseen. */
export function ChatPanelToggle({ open, badged, onToggle }: { open: boolean; badged: boolean; onToggle: () => void }) {
  const label = open ? "收起角色面板" : "展开角色面板";
  return (
    <Tooltip label={badged ? `${label} · 有新内容` : label} side="left">
      <button
        className={cx(
          compactPressableClass,
          "absolute right-4 top-4 z-[5] m-0 grid h-7 w-7 place-items-center rounded-md border-0 bg-transparent p-0 text-ink-muted hover:bg-black/5 hover:text-ink-secondary",
          open && "text-accent-text",
        )}
        type="button"
        aria-label={badged ? `${label}（有新内容）` : label}
        aria-expanded={open}
        data-testid="chat-panel-toggle"
        onClick={onToggle}
      >
        <SidebarSimple className="h-[18px] w-[18px]" mirrored weight={open ? "fill" : "regular"} aria-hidden="true" />
        {badged ? <span className={badgeDotClass} data-testid="chat-panel-toggle-badge" aria-hidden="true" /> : null}
      </button>
    </Tooltip>
  );
}

type SegmentSpec = { mode: ChatSidebarMode; label: string; icon: Icon };

const segments: SegmentSpec[] = [
  { mode: "status", label: "状态", icon: Smiley },
  { mode: "tasks", label: "任务", icon: ListChecks },
  { mode: "images", label: "图片", icon: Images },
];

/**
 * Segment switcher at the foot of the role panel. The status segment only
 * has something to show once the role has a mood illustration bound or has
 * replied at least once (each reply records its current thought); until then
 * it stays visible but unavailable, and its tooltip says why.
 */
export function ChatPanelSegments({
  mode,
  badges,
  statusAvailable,
  onSelect,
}: {
  mode: ChatSidebarMode;
  badges: ChatPanelBadges;
  statusAvailable: boolean;
  onSelect: (mode: ChatSidebarMode) => void;
}) {
  return (
    <div className="inline-flex w-fit justify-self-center rounded-full border border-line-soft bg-surface-soft p-1" role="group" aria-label="角色面板分区">
      {segments.map(({ mode: segment, label, icon: SegmentIcon }) => {
        const active = segment === mode;
        const unavailable = segment === "status" && !statusAvailable;
        const badged = (segment === "status" && badges.status) || (segment === "images" && badges.images);
        const tooltip = unavailable ? `${label} · 角色回复后出现` : badged ? `${label} · 有新内容` : label;
        return (
          <Tooltip key={segment} label={tooltip} side="top">
            <button
              className={cx(
                compactPressableClass,
                "relative grid h-7 w-7 place-items-center rounded-full",
                active ? "bg-gradient-accent text-ink shadow-soft" : "text-ink-secondary hover:text-ink",
                unavailable && "cursor-default opacity-45 hover:text-ink-secondary",
              )}
              type="button"
              aria-label={badged ? `${label}（有新内容）` : label}
              aria-pressed={active}
              // aria-disabled (not disabled) so the tooltip explaining why still opens on hover and focus.
              aria-disabled={unavailable || undefined}
              data-testid={`chat-panel-segment-${segment}`}
              onClick={() => { if (!unavailable) onSelect(segment); }}
            >
              <SegmentIcon className="h-[15px] w-[15px]" aria-hidden="true" />
              {badged ? <span className={badgeDotClass} data-testid={`chat-panel-segment-${segment}-badge`} aria-hidden="true" /> : null}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
