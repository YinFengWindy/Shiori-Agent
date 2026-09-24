import type React from "react";
import { Chats, GearSix, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { cx, pressableClass } from "../shared/styles";
import { Tooltip } from "../shared/ui/Tooltip";
import { formatShortcut, viewShortcutLabel } from "./globalShortcuts";

/** The rail's fixed built-in workspace targets (search is an action, never an active view). */
export type BuiltinNavRailViewId = "messages" | "roles" | "settings";

/**
 * Identifies the workspace a rail entry points to; null when no view entry
 * is active. Also accepts a plugin's `plugin:<id>` nav.page id alongside the
 * fixed built-in surfaces, without another exhaustive union to maintain.
 * `(string & {})` (rather than plain `string`) keeps compile-time literal
 * narrowing for the built-in ids instead of collapsing to `string`.
 */
export type NavRailViewId = BuiltinNavRailViewId | (string & {});

/** Builds the stable rail id for a plugin's nav.page entry. */
export function pluginNavRailViewId(pageId: string): NavRailViewId {
  return `plugin:${pageId}`;
}

/** Icon contract shared by built-in phosphor icons and a plugin's own icon component. */
type NavRailIcon = React.ComponentType<{ className?: string }>;

/** One top-level view in the rail, in rail order; `shortcut` is its Ctrl+digit label when it has one. */
export type NavRailView = {
  id: NavRailViewId;
  label: string;
  icon?: NavRailIcon;
  onSelect: () => void;
  showUnreadBadge?: boolean;
  shortcut?: string;
};

/** A plugin-contributed nav.page entry rendered alongside the built-in rail icons. */
export type NavRailPluginEntry = {
  pageId: string;
  label: string;
  icon?: NavRailIcon;
  onSelect: () => void;
};

/**
 * The rail's view entries in display order — 消息, 角色, then plugin pages —
 * each with its Ctrl+digit label. Shared by the rail and the global
 * shortcuts so the number shown in a tooltip is the number that works.
 */
export function buildNavRailViews({
  onBackToChat,
  onOpenRolesWorkspace,
  pluginEntries = [],
}: {
  onBackToChat: () => void;
  onOpenRolesWorkspace: () => void;
  pluginEntries?: NavRailPluginEntry[];
}): NavRailView[] {
  const views: Omit<NavRailView, "shortcut">[] = [
    { id: "messages", label: "消息", icon: Chats, onSelect: onBackToChat, showUnreadBadge: true },
    { id: "roles", label: "角色", icon: Users, onSelect: onOpenRolesWorkspace },
    ...pluginEntries.map((entry) => ({
      id: pluginNavRailViewId(entry.pageId),
      label: entry.label,
      icon: entry.icon,
      onSelect: entry.onSelect,
    })),
  ];
  return views.map((view, index) => ({ ...view, shortcut: viewShortcutLabel(index) }));
}

/** `aria-keyshortcuts` spelling of a displayed shortcut label. */
function ariaKeyShortcut(label: string | undefined): string | undefined {
  return label?.replace("⌘", "Meta+");
}

type NavRailProps = {
  activeView: NavRailViewId | null;
  unreadTotal: number;
  views: NavRailView[];
  onOpenSearch: () => void;
  onOpenSettings: () => void;
};

const railButtonClass = cx(
  pressableClass,
  "relative grid h-9 w-9 place-items-center rounded-md text-ink-muted focus-visible:bg-white/70 hover:bg-white/70 hover:text-ink",
);

// Search is an action, not a place: an outlined round button with a divider
// under it, so it never reads as the first of the view entries below.
const railActionButtonClass = cx(
  pressableClass,
  "grid h-9 w-9 place-items-center rounded-full border border-line-soft bg-white/45 text-ink-muted hover:border-line-accent hover:bg-white/80 hover:text-accent-text focus-visible:bg-white/80",
);

const railIconClass = "h-[19px] w-[19px]";

/** Renders the primary icon navigation rail shown across every workspace. */
export function NavRail({
  activeView,
  unreadTotal,
  views,
  onOpenSearch,
  onOpenSettings,
}: NavRailProps) {
  function renderView(view: NavRailView): React.ReactNode {
    const active = view.id === activeView;
    const showBadge = Boolean(view.showUnreadBadge && unreadTotal > 0);
    const Icon = view.icon;
    return (
      <Tooltip key={view.id} label={showBadge ? `${view.label} · ${unreadTotal} 条未读` : view.label} shortcut={view.shortcut}>
        <button
          className={cx(
            railButtonClass,
            active
              && "bg-white text-accent shadow-soft hover:bg-white hover:text-accent",
          )}
          type="button"
          aria-label={showBadge ? `${view.label}（${unreadTotal} 条未读）` : view.label}
          aria-keyshortcuts={ariaKeyShortcut(view.shortcut)}
          aria-current={active ? "page" : undefined}
          onClick={view.onSelect}
        >
          {Icon ? <span aria-hidden="true"><Icon className={railIconClass} /></span> : null}
          {showBadge ? (
            <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-danger" aria-hidden="true" />
          ) : null}
        </button>
      </Tooltip>
    );
  }

  const searchShortcut = formatShortcut("K");
  return (
    <nav className="nav-rail flex w-12 shrink-0 flex-col items-center gap-1 py-2.5" aria-label="主导航">
      <Tooltip label="搜索" shortcut={searchShortcut}>
        <button
          className={railActionButtonClass}
          type="button"
          aria-label="搜索"
          aria-keyshortcuts={ariaKeyShortcut(searchShortcut)}
          aria-haspopup="dialog"
          onClick={onOpenSearch}
        >
          <MagnifyingGlass className="h-[17px] w-[17px]" weight="bold" aria-hidden="true" />
        </button>
      </Tooltip>
      <span className="my-1.5 h-px w-6 rounded-full bg-line-soft" aria-hidden="true" />
      {views.map(renderView)}
      <div className="mt-auto">
        {renderView({ id: "settings", label: "设置", icon: GearSix, onSelect: onOpenSettings, shortcut: formatShortcut(",") })}
      </div>
    </nav>
  );
}
