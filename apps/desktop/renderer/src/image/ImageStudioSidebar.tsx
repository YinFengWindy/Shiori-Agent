import type React from "react";
import { ImageFormPanel } from "./ImageFormPanel";
import type { ImageStudioFormState } from "./types";
import { PromptLibraryIcon } from "../shared/icons";
import { cx, secondarySidebarSurfaceClass, sidebarNavItemClass } from "../shared/styles";

export type ImageStudioSidebarSectionId = "generate";

type ImageStudioSidebarProps = {
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  form: ImageStudioFormState;
  nsfwEnabled: boolean;
  addQualityTags: boolean;
  undesiredContentPreset: number;
  roleItems: Array<{ id: string; label: string; avatarAbs: string | null }>;
  submitting: boolean;
  validationError: string;
  onOpenPromptTagLibrary: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onSubmit: () => void;
  onToggleNsfwEnabled: () => void;
  onToggleAddQualityTags: () => void;
  onChangeUndesiredContentPreset: (value: number) => void;
};

/** Renders the image studio workspace sidebar with generation parameters. */
export function ImageStudioSidebar({
  bridgeReady,
  collapsed,
  animating,
  width,
  form,
  nsfwEnabled,
  addQualityTags,
  undesiredContentPreset,
  roleItems,
  submitting,
  validationError,
  onOpenPromptTagLibrary,
  onBeginResize,
  onChange,
  onPickBaseImage,
  onSubmit,
  onToggleNsfwEnabled,
  onToggleAddQualityTags,
  onChangeUndesiredContentPreset,
}: ImageStudioSidebarProps) {
  const promptLibraryClass = cx(
    sidebarNavItemClass,
    "mb-3 flex h-9 items-center gap-2 px-2 text-left text-sm text-[#6b7683]",
  );

  return (
    <aside
      className={cx(
        "image-studio-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] py-3",
        secondarySidebarSurfaceClass,
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <button
        data-testid="open-prompt-tag-library-button"
        className={promptLibraryClass}
        type="button"
        onClick={onOpenPromptTagLibrary}
      >
        <PromptLibraryIcon className="h-4 w-4 fill-current" />
        <span>提示词库</span>
      </button>
      <div className="scrollbar-soft min-h-0 min-w-0 overflow-x-hidden overflow-y-auto px-2 pb-1">
        <ImageFormPanel
          bridgeReady={bridgeReady}
          form={form}
          nsfwEnabled={nsfwEnabled}
          addQualityTags={addQualityTags}
          undesiredContentPreset={undesiredContentPreset}
          roleItems={roleItems}
          validationError={validationError}
          submitting={submitting}
          onChange={onChange}
          onPickBaseImage={onPickBaseImage}
          onSubmit={onSubmit}
          onToggleNsfwEnabled={onToggleNsfwEnabled}
          onToggleAddQualityTags={onToggleAddQualityTags}
          onChangeUndesiredContentPreset={onChangeUndesiredContentPreset}
        />
      </div>
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
