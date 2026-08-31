import type React from "react";
import { Brain, ChatCircleDots, Cpu, GearSix, Microphone, PlugsConnected } from "@phosphor-icons/react";
import { cx, inputClass, secondarySidebarSurfaceClass, sidebarNavItemClass } from "../shared/styles";

export type SettingsSectionId =
  | "models"
  | "channels"
  | "memory"
  | "integrations"
  | "voice"
  | "advanced";

export const settingsSections: Array<{ id: SettingsSectionId; label: string }> = [
  { id: "models", label: "模型" },
  { id: "channels", label: "频道" },
  { id: "memory", label: "记忆" },
  { id: "integrations", label: "集成" },
  { id: "voice", label: "语音" },
  { id: "advanced", label: "高级" },
];

const settingsSectionIcons = { models: Cpu, channels: ChatCircleDots, memory: Brain, integrations: PlugsConnected, voice: Microphone, advanced: GearSix } as const;

type SettingsSidebarProps = {
  activeSection: SettingsSectionId;
  dirty: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
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
  onOpenSection,
  onSearchChange,
  onBeginResize,
  search,
}: SettingsSidebarProps) {
  const query = search.trim().toLowerCase();
  const visibleSections = settingsSections.filter((section) => sectionMatches(section, query));
  const sidebarActionClass = cx(
    sidebarNavItemClass,
    "flex min-h-[38px] items-center justify-between px-3 text-left text-sm text-[#3a4453]",
  );

  return (
    <aside
      className={cx(
        "settings-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] py-3",
        secondarySidebarSurfaceClass,
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <input
        className={cx(
          inputClass,
          "mb-3 h-10 rounded-md px-4 text-sm",
        )}
        placeholder="搜索设置..."
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      <nav className="scrollbar-soft grid min-h-0 content-start gap-1 overflow-y-auto pr-0 pt-3">
        <div className="grid gap-1">
          {visibleSections.map((section) => {
            const Icon = settingsSectionIcons[section.id];
            return <button
              key={section.id}
              className={cx(
                sidebarActionClass,
                activeSection === section.id
                  && "border-[rgba(202,93,46,0.28)] bg-white/90 font-medium text-accent-deep shadow-[0_1px_2px_rgba(15,23,42,0.05)] hover:border-[rgba(202,93,46,0.4)] hover:bg-white focus-visible:border-[rgba(202,93,46,0.4)] focus-visible:bg-white",
              )}
              type="button"
              onClick={() => onOpenSection(section.id)}
            >
              <span className="inline-flex items-center gap-2">
                <Icon className={cx("h-4 w-4", activeSection === section.id ? "text-accent" : "text-[#8a94a3]")} weight="duotone" aria-hidden="true" />
                {section.label}
              </span>
              {dirty && activeSection === section.id ? <span className="h-2.5 w-2.5 rounded-full bg-primary" /> : null}
            </button>
          })}
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
