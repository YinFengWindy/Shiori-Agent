import { toFileUrl } from "../shared/format";
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
    <section className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-3 rounded-[20px] bg-[#FBFCFE] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
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
                "rounded-[16px] border p-2 text-left transition focus:outline-none",
                selected ? "border-black bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)]" : "border-transparent bg-white/60 hover:bg-white/85",
              )}
              type="button"
              onClick={() => onSelect(item)}
            >
              <div className="aspect-square w-full overflow-hidden rounded-[14px] bg-[#F1F5F9]">
                {previewPath ? (
                  <img className="h-full w-full object-contain" src={toFileUrl(previewPath)} alt="history preview" />
                ) : null}
              </div>
            </button>
          );
        }) : (
          <div className="rounded-[14px] bg-white px-3 py-5 text-center text-[12px] text-[#737781] shadow-[0_6px_18px_rgba(15,23,42,0.04)]">
            暂无绘图记录
          </div>
        )}
      </div>
      <div className="grid gap-2 pt-2">
        <button
          className="rounded-md bg-white px-3 py-2 text-[12px] text-[#B7BEC8] transition disabled:cursor-default"
          type="button"
          disabled
        >
          下载全部
        </button>
        <button
          className="rounded-md bg-white px-3 py-2 text-[12px] text-[#B7BEC8] transition disabled:cursor-default"
          type="button"
          disabled
        >
          清空历史
        </button>
      </div>
    </section>
  );
}
