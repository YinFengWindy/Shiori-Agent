import { useEffect, useState } from "react";
import { cx } from "../shared/styles";
import { ImageHistoryPanel } from "./ImageHistoryPanel";
import { ImagePreviewPanel } from "./ImagePreviewPanel";
import type {
  ImageGenerateResult,
  ImageHistoryRecord,
} from "./types";

type ImageStudioPageProps = {
  activeRecord: ImageHistoryRecord | null;
  error: string;
  generating: boolean;
  history: ImageHistoryRecord[];
  latestResult: ImageGenerateResult | null;
  selectedRecordId: string;
  historySidebarCollapsed: boolean;
  historySidebarWidth: number;
  historySidebarAnimating: boolean;
  onSelectRecord: (record: ImageHistoryRecord) => void;
  onToggleHistorySidebar: () => void;
  onBeginHistorySidebarResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders the image studio preview workspace and the collapsible history drawer. */
export function ImageStudioPage({
  activeRecord,
  error,
  generating,
  history,
  latestResult,
  selectedRecordId,
  historySidebarCollapsed,
  historySidebarWidth,
  historySidebarAnimating,
  onSelectRecord,
  onToggleHistorySidebar,
  onBeginHistorySidebarResize,
}: ImageStudioPageProps) {
  const [historySidebarMounted, setHistorySidebarMounted] = useState(!historySidebarCollapsed);
  const historyToggleGlyphClass =
    "relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:w-px before:rounded-full before:bg-current before:content-['']";

  useEffect(() => {
    if (!historySidebarCollapsed) {
      setHistorySidebarMounted(true);
      return undefined;
    }
    const timer = window.setTimeout(() => setHistorySidebarMounted(false), 240);
    return () => window.clearTimeout(timer);
  }, [historySidebarCollapsed]);

  return (
    <section className="image-studio-page relative h-full overflow-hidden bg-[linear-gradient(180deg,#F7F8FB_0%,#EEF2F7_100%)]">
      <button
        className="absolute right-4 top-4 z-[5] m-0 grid h-6 w-6 place-items-center rounded-md border-0 bg-transparent p-0 text-[#747474] transition hover:bg-black/5 hover:text-[#4B4B4B] focus:outline-none"
        type="button"
        aria-label={historySidebarCollapsed ? "展开历史侧栏" : "收起历史侧栏"}
        aria-expanded={!historySidebarCollapsed}
        onClick={onToggleHistorySidebar}
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
        <div className="min-h-0 overflow-hidden bg-white px-4 pb-4 pt-4">
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
          className={cx(
            "relative h-full overflow-hidden border-l border-[#E0E6EE] bg-white",
            historySidebarAnimating && "transition-[width] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          )}
          style={{ width: historySidebarCollapsed ? 0 : historySidebarWidth }}
        >
          {!historySidebarCollapsed ? (
            <div
              className="absolute inset-y-0 left-0 z-[3] w-3 -translate-x-1/2 cursor-col-resize before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-[#D8DEE8] before:content-['']"
              onPointerDown={onBeginHistorySidebarResize}
            />
          ) : null}
          {historySidebarMounted ? (
            <div
              className={cx(
                "h-full min-h-0 pb-3 pt-3 transition-[opacity,transform] duration-200",
                historySidebarCollapsed ? "pointer-events-none translate-x-8 pl-0 pr-0 opacity-0" : "translate-x-0 pl-2 pr-2 opacity-100",
              )}
            >
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
