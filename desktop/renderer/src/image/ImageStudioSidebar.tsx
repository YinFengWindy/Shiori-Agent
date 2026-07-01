import type React from "react";
import { ImageFormPanel } from "./ImageFormPanel";
import type { ImageStudioFormState } from "./types";
import { cx } from "../shared/styles";

export type ImageStudioSidebarSectionId = "generate";

type ImageStudioSidebarProps = {
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  form: ImageStudioFormState;
  modelOptions: ReadonlyArray<{ id: string; label: string }>;
  roleOptions: ReadonlyArray<{ id: string; label: string }>;
  samplerOptions: ReadonlyArray<{ id: string; label: string }>;
  submitting: boolean;
  validationError: string;
  onBackToChat: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onSubmit: () => void;
};

/** Renders the image studio workspace sidebar with generation parameters. */
export function ImageStudioSidebar({
  bridgeReady,
  collapsed,
  animating,
  width,
  form,
  modelOptions,
  roleOptions,
  samplerOptions,
  submitting,
  validationError,
  onBackToChat,
  onBeginResize,
  onChange,
  onPickBaseImage,
  onSubmit,
}: ImageStudioSidebarProps) {
  const sidebarBackClass =
    "mb-3 flex h-8 items-center gap-2 rounded-md border border-transparent bg-transparent px-2 text-left text-sm text-[#6E737A] transition-colors hover:border-[#D9E0E8] hover:bg-white/70 focus-visible:border-[#D9E0E8] focus-visible:bg-white/70 focus-visible:outline-none";

  return (
    <aside
      className={cx(
        "image-studio-sidebar relative grid h-full min-h-0 min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] bg-[#EEF1F5] py-3",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[10px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <button
        data-testid="image-studio-back-button"
        className={sidebarBackClass}
        type="button"
        onClick={onBackToChat}
      >
        <span className="text-base leading-none">←</span>
        <span>返回应用</span>
      </button>
      <div className="scrollbar-soft min-h-0 overflow-y-auto px-2 pb-1">
        <ImageFormPanel
          bridgeReady={bridgeReady}
          form={form}
          modelOptions={modelOptions}
          roleOptions={roleOptions}
          samplerOptions={samplerOptions}
          validationError={validationError}
          submitting={submitting}
          onChange={onChange}
          onPickBaseImage={onPickBaseImage}
          onSubmit={onSubmit}
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
