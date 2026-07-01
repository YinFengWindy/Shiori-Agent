import type React from "react";
import { ImageFormPanel } from "./ImageFormPanel";
import type { ImageStudioFormState } from "./types";
import type { RoleRecord } from "../shared/types";
import { cx } from "../shared/styles";

export type ImageStudioSidebarSectionId = "generate";

type ImageStudioSidebarProps = {
  activeRole: RoleRecord | null;
  activeSection: ImageStudioSidebarSectionId;
  autoWritebackRoleAssets: boolean;
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  form: ImageStudioFormState;
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
  activeRole,
  activeSection,
  autoWritebackRoleAssets,
  bridgeReady,
  collapsed,
  animating,
  width,
  form,
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
      <div className="mb-3 px-2">
        <div className="rounded-2xl border border-[#D9E0E8] bg-white/75 px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.05)]">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#8A9099]">Image Studio</div>
          <div className="mt-1 text-sm font-semibold text-[#20242A]">
            {activeSection === "generate" ? "生成参数" : "生图工作台"}
          </div>
        </div>
      </div>
      <div className="scrollbar-soft min-h-0 overflow-y-auto px-2 pb-1">
        <ImageFormPanel
          activeRole={activeRole}
          autoWritebackRoleAssets={autoWritebackRoleAssets}
          bridgeReady={bridgeReady}
          form={form}
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
