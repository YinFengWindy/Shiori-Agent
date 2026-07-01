import { useEffect, useState } from "react";
import type { RoleRecord } from "../shared/types";
import { cx } from "../shared/styles";
import { ImageHistoryPanel } from "./ImageHistoryPanel";
import { ImagePreviewPanel } from "./ImagePreviewPanel";
import type {
  ImageGenerateResult,
  ImageHistoryRecord,
} from "./types";

type ImageStudioPageProps = {
  activeRole: RoleRecord | null;
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
  activeRole,
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
        <div className="min-h-0 overflow-hidden px-8 pb-8 pt-7">
          <div className="mx-auto grid h-full min-h-0 w-full max-w-[1240px] grid-rows-[auto_minmax(0,1fr)] gap-5">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-[#8A9099]">Creative Workspace</div>
                <div className="mt-1 text-[24px] font-semibold leading-none text-[#1E2430]">
                  {activeRole ? `为 ${activeRole.name} 生图` : "生图工作台"}
                </div>
              </div>
              <button
                className="rounded-md border border-[#D8DCE2] bg-white/80 px-4 py-2 text-sm text-[#32363C] transition hover:border-[#AAB3C2] hover:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
                type="button"
                onClick={onToggleHistoryDrawer}
              >
                {historyDrawerOpen ? "收起历史" : "展开历史"}
              </button>
            </div>
            <ImagePreviewPanel
              activeRole={activeRole}
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
            historyDrawerOpen ? "w-[360px]" : "w-[58px]",
          )}
        >
          <button
            className="absolute left-0 top-1/2 z-[2] flex h-16 w-[58px] -translate-y-1/2 items-center justify-center rounded-l-[18px] rounded-r-none border-y border-l-0 border-r border-[#D9E0E8] bg-white/90 text-[#5B616A] shadow-[-6px_10px_24px_rgba(15,23,42,0.08)] transition hover:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
            type="button"
            aria-label={historyDrawerOpen ? "收起历史抽屉" : "展开历史抽屉"}
            onClick={onToggleHistoryDrawer}
          >
            <span className={cx("text-lg leading-none transition-transform duration-300", historyDrawerOpen ? "" : "rotate-180")}>›</span>
          </button>
          {historyDrawerMounted ? (
            <div
              className={cx(
                "h-full min-h-0 px-4 pb-5 pt-5 transition-[opacity,transform] duration-200",
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
