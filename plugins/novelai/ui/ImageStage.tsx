import { ArrowUUpLeft, Key } from "@phosphor-icons/react";
import { CrossfadeLayers } from "../../../apps/desktop/renderer/src/shared/CrossfadeLayers";
import { toFileUrl } from "../../../apps/desktop/renderer/src/shared/format";
import { compactPressableClass, cx } from "../../../apps/desktop/renderer/src/shared/styles";
import type { GenerationFailure } from "./generationFailure";
import { StageEmpty, StageFailure, StageGenerating } from "./StageStates";
import type { StageView } from "./studioSelectors";
import type { ImageHistoryRecord } from "./types";

type ImageStageProps = {
  view: StageView;
  onOpenSettings?: () => void;
  onDismissFailure?: () => void;
  onReusePrompt: (record: ImageHistoryRecord) => void;
};

const chipClass = "surface-glass inline-flex h-7 items-center rounded-full px-2.5 text-caption tabular-nums text-ink-secondary";

/** A standing token problem shown above the picture, so history stays browsable. */
function StageNotice({ notice, onOpenSettings }: { notice: GenerationFailure; onOpenSettings?: () => void }) {
  return (
    <div className="surface-glass absolute inset-x-3 top-3 z-[2] flex items-center gap-2 rounded-lg px-3 py-2 text-body-sm text-ink-secondary" role="status">
      <Key className="h-4 w-4 shrink-0 text-accent-text" weight="duotone" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{notice.title}{notice.message ? `：${notice.message}` : ""}</span>
      {onOpenSettings ? (
        <button className={cx(compactPressableClass, "shrink-0 rounded-md px-2 py-1 font-medium text-accent-text hover:bg-accent-softer")} type="button" onClick={onOpenSettings}>
          去设置
        </button>
      ) : null}
    </div>
  );
}

function StageImage({ view, onOpenSettings, onReusePrompt }: { view: Extract<StageView, { kind: "image" }>; onOpenSettings?: () => void; onReusePrompt: (record: ImageHistoryRecord) => void }) {
  const { record } = view;
  return (
    <div className="relative h-full" data-testid="novelai-stage-image">
      {view.notice ? <StageNotice notice={view.notice} onOpenSettings={onOpenSettings} /> : null}
      <CrossfadeLayers
        value={view.path}
        layerClassName="absolute inset-0 flex items-center justify-center p-5 pb-14"
        render={(path) => (
          <img
            className={cx("max-h-full max-w-full rounded-lg object-contain shadow-panel", view.reveal && "nai-reveal")}
            src={toFileUrl(path)}
            alt={record?.prompt || "生成结果"}
          />
        )}
      />
      {record ? (
        <div className="absolute inset-x-3 bottom-3 z-[1] flex items-center gap-2">
          <span className={chipClass}>{record.width} × {record.height}</span>
          {record.seed != null ? <span className={chipClass}>种子 {record.seed}</span> : null}
          <button
            className={cx(compactPressableClass, chipClass, "ml-auto gap-1.5 hover:bg-white hover:text-ink")}
            type="button"
            onClick={() => onReusePrompt(record)}
          >
            <ArrowUUpLeft className="h-3.5 w-3.5" aria-hidden="true" />
            复用提示词
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** The canvas: a glass stage showing the current picture, work in flight, a failure, or the empty motif. */
export function ImageStage({ view, onOpenSettings, onDismissFailure, onReusePrompt }: ImageStageProps) {
  return (
    <div className="nai-stage min-h-0" data-testid="novelai-stage">
      {view.kind === "generating" ? <StageGenerating aspect={view.aspect} /> : null}
      {view.kind === "failure" ? <StageFailure failure={view.failure} onOpenSettings={onOpenSettings} onDismiss={onDismissFailure} /> : null}
      {view.kind === "image" ? <StageImage view={view} onOpenSettings={onOpenSettings} onReusePrompt={onReusePrompt} /> : null}
      {view.kind === "empty" ? <StageEmpty /> : null}
    </div>
  );
}
