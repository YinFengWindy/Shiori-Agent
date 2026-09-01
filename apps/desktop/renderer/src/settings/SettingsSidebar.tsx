import type React from "react";
import { cx, secondarySidebarSurfaceClass, sidebarNavItemClass } from "../shared/styles";

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

type SettingsSidebarProps = {
  activeSection: SettingsSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSection: (section: SettingsSectionId) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

export function SettingsSidebar({
  activeSection,
  collapsed,
  animating,
  width,
  onOpenSection,
  onBeginResize,
}: SettingsSidebarProps) {
  const sidebarActionClass = cx(
    sidebarNavItemClass,
    "flex min-h-[38px] items-center px-3 text-left text-sm text-[#3a4453]",
  );

  return (
    <aside
      className={cx(
        "settings-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] py-5",
        secondarySidebarSurfaceClass,
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <nav className="scrollbar-soft grid min-h-0 content-start gap-1 overflow-y-auto px-2 pr-0">
        <div className="grid gap-1">
          {settingsSections.map((section) => <button
              key={section.id}
              className={cx(
                sidebarActionClass,
                activeSection === section.id
                  && "bg-white/80 font-medium text-[#3a4453] shadow-[0_1px_2px_rgba(15,23,42,0.05)] hover:bg-white focus-visible:bg-white",
              )}
              type="button"
              onClick={() => onOpenSection(section.id)}
            >
              <span>{section.label}</span>
            </button>)}
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
