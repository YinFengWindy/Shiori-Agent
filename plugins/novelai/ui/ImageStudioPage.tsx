import { useState } from "react";
import { cx, sidebarTrackMotionClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { ImageHistoryPanel } from "./ImageHistoryPanel";
import { ImagePreviewPanel } from "./ImagePreviewPanel";
import type {
  ImageGenerateResult,
  ImageHistoryRecord,
} from "./types";

const HISTORY_SIDEBAR_WIDTH = 260;

type ImageStudioPageProps = {
  activeRecord: ImageHistoryRecord | null;
  error: string;
  generating: boolean;
  history: ImageHistoryRecord[];
  latestResult: ImageGenerateResult | null;
  selectedRecordId: string;
  onSelectRecord: (record: ImageHistoryRecord) => void;
};

/**
 * Renders the image studio preview workspace and the collapsible history
 * drawer. The drawer is fixed-width (no drag-resize): it is this page's own
 * secondary panel, not the generation-form sidebar (`ImageStudioSidebar`,
 * rendered separately into the host's resizable `sidebar-track` — issue
 * #226 gap A), so it never had drag-resize before the #180 migration either.
 * The collapse toggle is kept since it affects layout, not chrome.
 */
export function ImageStudioPage({
  activeRecord,
  error,
  generating,
  history,
  latestResult,
  selectedRecordId,
  onSelectRecord,
}: ImageStudioPageProps) {
  const [historySidebarCollapsed, setHistorySidebarCollapsed] = useState(false);
  const historyToggleGlyphClass =
    "relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:w-px before:rounded-full before:bg-current before:content-['']";

  return (
    <section className="image-studio-page relative h-full overflow-hidden bg-gradient-app bg-fixed">
      <button
        className="absolute right-4 top-4 z-[5] m-0 grid h-6 w-6 place-items-center rounded-md border-0 bg-transparent p-0 text-ink-muted transition hover:bg-white/60 hover:text-ink focus:outline-none"
        type="button"
        aria-label={historySidebarCollapsed ? "展开历史侧栏" : "收起历史侧栏"}
        aria-expanded={!historySidebarCollapsed}
        onClick={() => setHistorySidebarCollapsed((current) => !current)}
      >
        <span
          className={cx(
            historyToggleGlyphClass,
            historySidebarCollapsed
              ? "before:bottom-[2.2px] before:right-[0.8px] before:top-[2.2px]"
              : "before:bottom-0 before:right-[3.3px] before:top-0",
          )}
        />
      </button>
      <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_auto] gap-0">
        <div className="min-h-0 overflow-hidden bg-gradient-app bg-fixed px-4 pb-4 pt-4">
          <div className="mx-auto grid h-full min-h-0 w-full max-w-none">
            <ImagePreviewPanel
              activeRecord={activeRecord}
              generating={generating}
              latestResult={latestResult}
              error={error}
            />
          </div>
        </div>
        <div
          className={cx("relative h-full overflow-hidden border-l border-line-soft bg-gradient-app bg-fixed", sidebarTrackMotionClass)}
          style={{ width: historySidebarCollapsed ? 0 : HISTORY_SIDEBAR_WIDTH }}
        >
          {!historySidebarCollapsed ? (
            <div className="h-full min-h-0 pb-3 pl-2 pr-2 pt-3">
              <ImageHistoryPanel
                items={history}
                selectedRecordId={selectedRecordId}
                onSelect={onSelectRecord}
              />
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
