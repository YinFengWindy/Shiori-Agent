import type React from "react";
import { cx, inputClass } from "../shared/styles";

export type SettingsSectionId =
  | "models"
  | "channels"
  | "memory"
  | "proactive"
  | "integrations"
  | "advanced";

export const settingsSections: Array<{ id: SettingsSectionId; label: string }> = [
  { id: "models", label: "模型" },
  { id: "channels", label: "频道" },
  { id: "memory", label: "记忆" },
  { id: "proactive", label: "主动推送" },
  { id: "integrations", label: "集成" },
  { id: "advanced", label: "高级" },
];

type SettingsSidebarProps = {
  activeSection: SettingsSectionId;
  dirty: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onBackToChat: () => void;
  onOpenSection: (section: SettingsSectionId) => void;
  onSearchChange: (value: string) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
  search: string;
};

function sectionMatches(section: { id: SettingsSectionId; label: string }, query: string): boolean {
  if (!query) return true;
  return section.label.toLowerCase().includes(query) || section.id.toLowerCase().includes(query);
}

export function SettingsSidebar({
  activeSection,
  dirty,
  collapsed,
  animating,
  width,
  onBackToChat,
  onOpenSection,
  onSearchChange,
  onBeginResize,
  search,
}: SettingsSidebarProps) {
  const query = search.trim().toLowerCase();
  const visibleSections = settingsSections.filter((section) => sectionMatches(section, query));
  const sidebarActionClass =
    "flex min-h-[38px] items-center justify-between rounded-xl border border-transparent px-3 text-left text-sm text-[#32363C] transition-colors hover:border-[#D9E0E8] hover:bg-white/70 focus-visible:border-[#D9E0E8] focus-visible:bg-white/70 focus-visible:outline-none";
  const sidebarBackClass =
    "mb-3 flex h-8 items-center gap-2 rounded-md border border-transparent bg-transparent px-2 text-left text-sm text-[#6E737A] transition-colors hover:border-[#D9E0E8] hover:bg-white/70 focus-visible:border-[#D9E0E8] focus-visible:bg-white/70 focus-visible:outline-none";

  return (
    <aside
      className={cx(
        "settings-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] bg-[#EEF1F5] py-3",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <button data-testid="settings-back-button" className={sidebarBackClass} type="button" onClick={onBackToChat}>
        <span className="text-base leading-none">←</span>
        <span>返回应用</span>
      </button>
      <input
        className={cx(
          inputClass,
          "mb-3 h-10 rounded-xl bg-[#F5F6F8] px-4 py-0 text-sm",
        )}
        placeholder="搜索设置..."
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      <nav className="scrollbar-soft grid min-h-0 content-start gap-4 overflow-y-auto pr-0">
        <div className="grid gap-1">
          {visibleSections.map((section) => (
            <button
              key={section.id}
              className={cx(
                sidebarActionClass,
                activeSection === section.id && "border-[#D9E0E8] bg-white/80 font-medium shadow-[0_1px_2px_rgba(15,23,42,0.05)]",
              )}
              type="button"
              onClick={() => onOpenSection(section.id)}
            >
              <span>{section.label}</span>
              {dirty && activeSection === section.id ? <span className="h-2.5 w-2.5 rounded-full bg-[#2176FF]" /> : null}
            </button>
          ))}
        </div>
      </nav>
      <div
        className={cx(
          "sidebar-resize-handle absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent",
          collapsed ? "w-0" : "w-2",
        )}
        role="separator"
        aria-label="调整侧边栏宽度"
        aria-orientation="vertical"
        onPointerDown={onBeginResize}
      />
    </aside>
  );
}
