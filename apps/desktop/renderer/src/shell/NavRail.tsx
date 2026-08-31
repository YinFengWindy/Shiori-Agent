import type React from "react";
import { BookOpenText, Chats, GearSix, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { cx } from "../shared/styles";

const novelAiLogoDark = new URL("../assets/novelai-logo-dark.svg", import.meta.url).href;

/** Identifies the workspace a rail entry points to; null when no view entry is active. */
export type NavRailViewId = "messages" | "roles" | "image" | "story" | "settings";

type NavRailEntry = {
  id: NavRailViewId | "search";
  label: string;
  icon?: typeof Chats;
  imageSrc?: string;
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
  "relative grid h-10 w-10 place-items-center rounded-md text-[#5f6b76] transition-colors focus:outline-none focus-visible:bg-white/80 hover:bg-white/80 hover:text-[#2c3440]";

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
    { id: "image", label: "生图", imageSrc: novelAiLogoDark, onSelect: onOpenImageStudio },
    { id: "story", label: "故事", icon: BookOpenText, onSelect: onOpenStory },
  ];

  function renderEntry(entry: NavRailEntry): React.ReactNode {
    const active = entry.id === activeView;
    const showBadge = Boolean(entry.showUnreadBadge && unreadTotal > 0);
    const Icon = entry.icon;
    return (
      <button
        key={entry.id}
        className={cx(
          railButtonClass,
          active
            && "bg-white text-[#5f6b76] shadow-[0_1px_2px_rgba(15,23,42,0.06)] hover:bg-white hover:text-[#5f6b76]",
        )}
        type="button"
        aria-label={showBadge ? `${entry.label}（${unreadTotal} 条未读）` : entry.label}
        aria-current={active ? "page" : undefined}
        title={entry.label}
        onClick={entry.onSelect}
      >
        {entry.imageSrc ? <img className="h-[21px] w-[21px]" src={entry.imageSrc} alt="" /> : null}
        {!entry.imageSrc && Icon ? <Icon className="h-[21px] w-[21px]" weight="regular" aria-hidden="true" /> : null}
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
