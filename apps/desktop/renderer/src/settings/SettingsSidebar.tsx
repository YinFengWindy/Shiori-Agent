import type React from "react";
import { Brain, BookBookmark, Info, Microphone, Palette, PuzzlePiece, SlidersHorizontal, type Icon } from "@phosphor-icons/react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { SidebarResizeHandle } from "../shared/SidebarResizeHandle";
import { cx, secondarySidebarSurfaceClass, sidebarContentMotionClass, sidebarNavItemClass } from "../shared/styles";
import { registerBuiltinSettingsSections } from "./registerBuiltinSettingsSections";

registerBuiltinSettingsSections();

/**
 * The seven settings.section ids registered by `registerBuiltinSettingsSections`.
 * 「频道」随 Telegram / QQ 迁为渠道插件而移除（#363），渠道配置在 设置 › 插件。
 */
export type BuiltinSettingsSectionId =
  | "models"
  | "memory"
  | "voice"
  | "appearance"
  | "advanced"
  | "plugins"
  | "about";

/**
 * Identifies a settings.section registry entry — today always one of the
 * seven built-ins (issue #230: a plugin's own settings no longer registers
 * a top-level section, it nests as a subtab under "plugins" instead, see
 * `pluginUiRegistry`'s `SettingsSubsectionEntry`). This still accepts any
 * string rather than narrowing to `BuiltinSettingsSectionId` because
 * `PluginUiRegistry`'s `SettingsSectionEntry.id` is typed as a plain
 * `string` (the registry has no compile-time way to know only builtins
 * register there — that is a runtime invariant of how the registration
 * call sites behave, not something the registry's own storage enforces);
 * narrowing this alias without also narrowing the registry would just move
 * the cast to every read site instead of removing it. `(string & {})`
 * (rather than plain `string`) keeps compile-time literal
 * narrowing/autocomplete for the built-in ids instead of collapsing the
 * whole union down to `string`.
 */
export type SettingsSectionId = BuiltinSettingsSectionId | (string & {});

/** Sidebar entries for every currently registered settings section. */
export function listSettingsSidebarSections(
  isPluginEnabled?: (pluginId: string) => boolean,
): Array<{ id: SettingsSectionId; label: string }> {
  return pluginUiRegistry
    .listSettingsSections(isPluginEnabled)
    .map((entry) => ({ id: entry.id, label: entry.label }));
}

/** Icons for the built-in sections; a section without one renders its label alone. */
const sectionIcons: Partial<Record<SettingsSectionId, Icon>> = {
  models: Brain,
  memory: BookBookmark,
  voice: Microphone,
  appearance: Palette,
  advanced: SlidersHorizontal,
  plugins: PuzzlePiece,
  about: Info,
};

type SettingsSidebarProps = {
  sections?: Array<{ id: SettingsSectionId; label: string }>;
  activeSection: SettingsSectionId;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSection: (section: SettingsSectionId) => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

export function SettingsSidebar({
  sections = listSettingsSidebarSections(),
  activeSection,
  collapsed,
  animating,
  width,
  onOpenSection,
  onBeginResize,
}: SettingsSidebarProps) {
  const sidebarActionClass = cx(
    sidebarNavItemClass,
    "flex min-h-[38px] items-center gap-2.5 px-3 text-left text-sm text-ink-secondary",
  );

  return (
    <aside
      className={cx(
        "settings-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] py-5",
        secondarySidebarSurfaceClass,
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <nav className="scrollbar-soft grid min-h-0 content-start gap-1 overflow-y-auto px-2 pr-0">
        <div className="grid gap-1">
          {sections.map((section) => {
            const SectionIcon = sectionIcons[section.id];
            const active = activeSection === section.id;
            return <button
              key={section.id}
              className={cx(
                sidebarActionClass,
                active && "bg-white/80 font-medium text-ink shadow-soft hover:bg-white focus-visible:bg-white",
              )}
              type="button"
              aria-current={active ? "page" : undefined}
              onClick={() => onOpenSection(section.id)}
            >
              {SectionIcon ? <SectionIcon className={cx("h-4 w-4 shrink-0", active ? "text-accent-text" : "text-ink-muted")} aria-hidden="true" /> : null}
              <span>{section.label}</span>
            </button>;
          })}
        </div>
      </nav>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
