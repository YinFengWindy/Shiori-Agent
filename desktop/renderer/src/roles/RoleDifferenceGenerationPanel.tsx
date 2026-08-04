import { Check, CircleNotch, MagicWand, WarningCircle } from "@phosphor-icons/react";

import type { RoleDifferenceGenerationState } from "./roleDifferenceGeneration";

type RoleDifferenceGenerationPanelProps = {
  baseAssetPath: string;
  bridgeReady: boolean;
  state: RoleDifferenceGenerationState;
  onGenerate: () => void;
};

/** Renders the base-image action and the five-stage difference progress strip. */
export function RoleDifferenceGenerationPanel({
  baseAssetPath,
  bridgeReady,
  state,
  onGenerate,
}: RoleDifferenceGenerationPanelProps) {
  const progress = `${Math.round((state.completed / state.stages.length) * 100)}%`;
  const busy = state.status === "running";

  return (
    <div className="mb-4 grid gap-3 rounded-[18px] border border-[#E4EAF0] bg-white px-4 py-3" data-testid="role-difference-generation-panel">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-[#2A3440]">自动生成差分</div>
          <div className="mt-1 truncate text-xs text-[#7A8593]">
            {baseAssetPath ? "已选择基准图" : "请先选择一张基准图"}
          </div>
        </div>
        <button
          className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[#272536] text-white transition hover:bg-[#3B3850] disabled:cursor-default disabled:bg-[#D8DDE5] disabled:text-[#8A94A2]"
          type="button"
          aria-label={busy ? "正在生成差分" : "自动生成差分"}
          title={busy ? "正在生成差分" : "自动生成差分"}
          disabled={!bridgeReady || !baseAssetPath || busy}
          onClick={onGenerate}
        >
          {busy ? <CircleNotch className="h-5 w-5 animate-spin" aria-hidden="true" /> : <MagicWand className="h-5 w-5" weight="fill" aria-hidden="true" />}
        </button>
      </div>
      {state.status !== "idle" ? (
        <div className="grid gap-2" aria-live="polite">
          <div className="h-1.5 overflow-hidden rounded-full bg-[#EEF1F5]">
            <div className="h-full rounded-full bg-[#7C6EE6] transition-[width] duration-300" style={{ width: progress }} />
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {state.stages.map((stage) => (
              <div className="grid min-w-0 justify-items-center gap-1 text-center" key={stage.id}>
                <span className={stage.status === "completed" ? "text-[#31805A]" : stage.status === "failed" ? "text-[#B44F4F]" : stage.status === "generating" ? "text-[#7C6EE6]" : "text-[#B7BEC8]"}>
                  {stage.status === "completed" ? <Check className="h-4 w-4" weight="bold" aria-hidden="true" /> : stage.status === "failed" ? <WarningCircle className="h-4 w-4" weight="fill" aria-hidden="true" /> : stage.status === "generating" ? <CircleNotch className="h-4 w-4 animate-spin" aria-hidden="true" /> : <span className="block h-2 w-2 rounded-full bg-current" aria-hidden="true" />}
                </span>
                <span className="truncate text-[10px] text-[#7A8593]">{stage.label}</span>
              </div>
            ))}
          </div>
          {state.status === "success" ? <div className="text-xs text-[#31805A]">已生成并加入{state.categoryName || "新差分分类"}</div> : null}
          {state.status === "error" ? <div className="text-xs leading-5 text-[#B44F4F]">{state.error || "差分生成失败"}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
