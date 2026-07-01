import { formatTimestamp, toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { ImageHistoryRecord } from "./types";

type ImageHistoryPanelProps = {
  items: ImageHistoryRecord[];
  selectedRecordId: string;
  onSelect: (record: ImageHistoryRecord) => void;
};

export function ImageHistoryPanel({
  items,
  selectedRecordId,
  onSelect,
}: ImageHistoryPanelProps) {
  return (
    <section className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-3 rounded-[20px] border border-[#E4EAF0] bg-[#FBFCFE] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="flex items-center justify-between px-1 pt-1">
        <div className="text-sm font-medium text-[#20242A]">History</div>
      </div>
      <div className="scrollbar-soft grid min-h-0 content-start gap-2 overflow-y-auto pr-1">
        {items.length ? items.map((item) => {
          const previewPath = item.output_paths[0] ?? "";
          const selected = item.id === selectedRecordId;
          return (
            <button
              key={item.id}
              className={cx(
                "grid gap-2 rounded-[14px] border p-2 text-left transition focus:outline-none focus:ring-2 focus:ring-primary/20",
                selected ? "border-[#272536] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)]" : "border-[#E4EAF0] bg-white/80 hover:border-[#9AA3B2]",
              )}
              type="button"
              onClick={() => onSelect(item)}
            >
              <div className="h-[84px] w-full overflow-hidden rounded-[12px] bg-[#F1F5F9]">
                {previewPath ? (
                  <img className="h-full w-full object-cover" src={toFileUrl(previewPath)} alt="history preview" />
                ) : null}
              </div>
              <div className="truncate text-[11px] text-[#6B7280]">{formatTimestamp(item.created_at)}</div>
            </button>
          );
        }) : (
          <div className="rounded-[14px] border border-dashed border-[#D8DCE2] bg-white px-3 py-5 text-center text-[12px] text-[#737781]">
            暂无绘图记录
          </div>
        )}
      </div>
      <div className="grid gap-2 border-t border-[#EEF2F6] pt-2">
        <button
          className="rounded-md border border-[#E4EAF0] bg-white px-3 py-2 text-[12px] text-[#B7BEC8] transition disabled:cursor-default"
          type="button"
          disabled
        >
          下载全部
        </button>
        <button
          className="rounded-md border border-[#E4EAF0] bg-white px-3 py-2 text-[12px] text-[#B7BEC8] transition disabled:cursor-default"
          type="button"
          disabled
        >
          清空历史
        </button>
      </div>
    </section>
  );
}
