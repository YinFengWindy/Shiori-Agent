import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import type { ImageGenerateResult, ImageHistoryRecord } from "./types";

type ImagePreviewPanelProps = {
  activeRole: RoleRecord | null;
  activeRecord: ImageHistoryRecord | null;
  generating: boolean;
  latestResult: ImageGenerateResult | null;
  requestSummary: {
    mode: string;
    width: string;
    height: string;
    steps: string;
    model: string;
    seed: string;
  } | null;
  error: string;
};

export function ImagePreviewPanel({
  activeRole,
  activeRecord,
  generating,
  latestResult,
  requestSummary,
  error,
}: ImagePreviewPanelProps) {
  const previewPath = activeRecord?.output_paths[0] ?? latestResult?.output_paths[0] ?? "";

  return (
    <section className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-5 rounded-[28px] border border-[#E7EAF0] bg-[rgba(255,255,255,0.88)] p-6 shadow-[0_18px_40px_rgba(15,23,42,0.06)] backdrop-blur-[8px]">
      <div className="grid min-h-[420px] place-items-center overflow-hidden rounded-[24px] border border-[#EEF2F6] bg-[radial-gradient(circle_at_top,rgba(247,249,252,0.96),rgba(241,245,249,0.96))]">
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
        {requestSummary ? (
          <div className="grid gap-2 rounded-[20px] border border-[#E7EAF0] bg-[#FBFCFE] px-4 py-3 text-[12px] leading-5 text-[#5B616A] md:grid-cols-2">
            <div>{`mode: ${requestSummary.mode}`}</div>
            <div>{`size: ${requestSummary.width} × ${requestSummary.height}`}</div>
            <div>{`steps: ${requestSummary.steps}`}</div>
            <div>{`seed: ${requestSummary.seed}`}</div>
            <div className="md:col-span-2">{`model: ${requestSummary.model}`}</div>
          </div>
        ) : null}
        {latestResult || activeRecord ? (
          <div className="grid gap-1 text-[12px] leading-5 text-[#6B7280]">
            <div>{previewPath}</div>
            <div>
              {activeRole
                ? ((activeRecord?.wrote_back_to_role ?? latestResult?.wrote_back_to_role)
                    ? `已写回 ${activeRole.name}`
                    : `当前结果已关联角色 ${activeRole.name}`)
                : "当前不绑定角色"}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
