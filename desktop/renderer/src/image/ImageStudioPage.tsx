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
  requestSummary: {
    mode: string;
    width: string;
    height: string;
    steps: string;
    model: string;
    seed: string;
  } | null;
  selectedRecordId: string;
  historyDrawerOpen: boolean;
  onSelectRecord: (record: ImageHistoryRecord) => void;
  onToggleHistoryDrawer: () => void;
};

/** Renders the image studio preview workspace and the collapsible history drawer. */
export function ImageStudioPage({
  activeRecord,
  error,
  generating,
  history,
  latestResult,
  requestSummary,
  selectedRecordId,
  historyDrawerOpen,
  onSelectRecord,
  onToggleHistoryDrawer,
}: ImageStudioPageProps) {
  const [historyDrawerMounted, setHistoryDrawerMounted] = useState(historyDrawerOpen);

  useEffect(() => {
    if (historyDrawerOpen) {
      setHistoryDrawerMounted(true);
      return undefined;
    }
    const timer = window.setTimeout(() => setHistoryDrawerMounted(false), 240);
    return () => window.clearTimeout(timer);
  }, [historyDrawerOpen]);

  return (
    <section className="image-studio-page relative h-full overflow-hidden bg-[linear-gradient(180deg,#F7F8FB_0%,#EEF2F7_100%)]">
      <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_auto] gap-0">
        <div className="min-h-0 overflow-hidden px-4 pb-4 pt-4">
          <div className="mx-auto grid h-full min-h-0 w-full max-w-none">
            <ImagePreviewPanel
              activeRecord={activeRecord}
              generating={generating}
              latestResult={latestResult}
              requestSummary={requestSummary}
              error={error}
            />
          </div>
        </div>
        <div
          className={cx(
            "relative h-full border-l border-[#E0E6EE] bg-[rgba(244,247,251,0.92)] transition-[width] duration-300 ease-out",
            historyDrawerOpen ? "w-[126px]" : "w-[56px]",
          )}
        >
          <button
            className="absolute right-3 top-3 z-[2] flex h-8 w-8 items-center justify-center rounded-md text-[#8A9099] transition hover:bg-white/70 hover:text-[#5B616A] focus:outline-none focus:ring-2 focus:ring-primary/20"
            type="button"
            aria-label={historyDrawerOpen ? "收起历史抽屉" : "展开历史抽屉"}
            onClick={onToggleHistoryDrawer}
          >
            <span className={cx("text-lg leading-none transition-transform duration-300", historyDrawerOpen ? "" : "rotate-180")}>›</span>
          </button>
          {historyDrawerMounted ? (
            <div
              className={cx(
                "h-full min-h-0 px-2 pb-3 pt-3 transition-[opacity,transform] duration-200",
                historyDrawerOpen ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-8 opacity-0",
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
