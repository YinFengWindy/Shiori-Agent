import { toFileUrl } from "../shared/format";
import type { ImageGenerateResult, ImageHistoryRecord } from "./types";

type ImagePreviewPanelProps = {
  activeRecord: ImageHistoryRecord | null;
  generating: boolean;
  latestResult: ImageGenerateResult | null;
  requestSummary: {
    mode: string;
    width: string;
    height: string;
    model: string;
    seed: string;
  } | null;
  error: string;
};

export function ImagePreviewPanel({
  activeRecord,
  generating,
  latestResult,
  requestSummary: _requestSummary,
  error,
}: ImagePreviewPanelProps) {
  const previewPath = activeRecord?.output_paths[0] ?? latestResult?.output_paths[0] ?? "";

  return (
    <section className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-3 rounded-[22px] border border-[#E7EAF0] bg-[rgba(255,255,255,0.96)] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
      <div className="grid min-h-[420px] place-items-center overflow-hidden rounded-[18px] bg-white">
        {previewPath ? (
          <img className="max-h-full w-full object-contain" src={toFileUrl(previewPath)} alt="generated result" />
        ) : generating ? (
          <div className="text-sm text-[#6B7280]">生成中...</div>
        ) : (
          <div className="text-sm text-[#6B7280]">等待生成</div>
        )}
      </div>

      <div className="grid gap-3">
        {error ? (
          <div className="rounded-md border border-[rgba(176,58,58,0.18)] bg-[#FFF1F1] px-3 py-2 text-[12px] leading-5 text-[#9A2F2F]">
            {error}
          </div>
        ) : null}
      </div>
    </section>
  );
}
