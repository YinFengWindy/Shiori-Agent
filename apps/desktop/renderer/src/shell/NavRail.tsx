import type React from "react";
import { BookOpenText, Chats, GearSix, Images, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { cx } from "../shared/styles";

/** Identifies the workspace a rail entry points to; null when no view entry is active. */
export type NavRailViewId = "messages" | "roles" | "image" | "story" | "settings";

type NavRailEntry = {
  id: NavRailViewId | "search";
  label: string;
  icon: typeof Chats;
  onSelect: () => void;
  showUnreadBadge?: boolean;
};

type NavRailProps = {
  activeView: NavRailViewId | null;
  unreadTotal: number;
  onOpenSearch: () => void;
  onBackToChat: () => void;
  onOpenRolesWorkspace: () => void;
  onOpenImageStudio: () => void;
  onOpenStory: () => void;
  onOpenSettings: () => void;
};

const railButtonClass =
  "relative grid h-10 w-10 place-items-center rounded-md border border-transparent text-[#5f6b76] transition-colors focus:outline-none focus-visible:border-stroke focus-visible:bg-white/80 hover:border-stroke hover:bg-white/80 hover:text-[#2c3440]";

/** Renders the primary icon navigation rail shown across every workspace. */
export function NavRail({
  activeView,
  unreadTotal,
  onOpenSearch,
  onBackToChat,
  onOpenRolesWorkspace,
  onOpenImageStudio,
  onOpenStory,
  onOpenSettings,
}: NavRailProps) {
  const entries: NavRailEntry[] = [
    { id: "search", label: "搜索", icon: MagnifyingGlass, onSelect: onOpenSearch },
    { id: "messages", label: "消息", icon: Chats, onSelect: onBackToChat, showUnreadBadge: true },
    { id: "roles", label: "角色", icon: Users, onSelect: onOpenRolesWorkspace },
    { id: "image", label: "生图", icon: Images, onSelect: onOpenImageStudio },
    { id: "story", label: "故事", icon: BookOpenText, onSelect: onOpenStory },
  ];

  function renderEntry(entry: NavRailEntry): React.ReactNode {
    const active = entry.id === activeView;
    const showBadge = Boolean(entry.showUnreadBadge && unreadTotal > 0);
    return (
      <button
        key={entry.id}
        className={cx(
          railButtonClass,
          active
            && "border-stroke bg-white text-accent shadow-[0_1px_2px_rgba(15,23,42,0.06)] hover:border-stroke hover:bg-white hover:text-accent",
        )}
        type="button"
        aria-label={showBadge ? `${entry.label}（${unreadTotal} 条未读）` : entry.label}
        aria-current={active ? "page" : undefined}
        title={entry.label}
        onClick={entry.onSelect}
      >
        <entry.icon className="h-[21px] w-[21px]" weight={active ? "fill" : "regular"} aria-hidden="true" />
        {showBadge ? (
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-[#DA4B4B]" aria-hidden="true" />
        ) : null}
      </button>
    );
  }

  return (
    <nav className="nav-rail flex w-[52px] shrink-0 flex-col items-center gap-1.5 py-3" aria-label="主导航">
      {entries.map(renderEntry)}
      <div className="mt-auto">{renderEntry({ id: "settings", label: "设置", icon: GearSix, onSelect: onOpenSettings })}</div>
    </nav>
  );
}
