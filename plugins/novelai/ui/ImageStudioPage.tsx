import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { ImageFilmstrip } from "./ImageFilmstrip";
import { ImageStage } from "./ImageStage";
import { clearFailure, selectRecord, updateStudioForm } from "./novelAiPageStore";
import { PromptPanel } from "./PromptPanel";
import { useImageStudio } from "./useImageStudio";

type ImageStudioPageProps = {
  client: PluginRpcClient;
  activeRoleId: string;
  onOpenSettings?: () => void;
};

/**
 * The studio: the prompt panel on the left, the glass canvas on the right
 * with this role's history as a filmstrip beneath it. The panel keeps a
 * readable width (tabs and labels never truncate) and the canvas takes the
 * rest, from 960px windows up.
 */
export function ImageStudioPage({ client, activeRoleId, onOpenSettings }: ImageStudioPageProps) {
  const studio = useImageStudio(client, activeRoleId, onOpenSettings);
  const { store } = studio;

  return (
    <section
      className="image-studio-page grid h-full min-h-0 grid-cols-[clamp(300px,32%,392px)_minmax(0,1fr)] gap-4 overflow-hidden bg-gradient-app bg-fixed p-4"
      data-testid="novelai-studio"
    >
      <PromptPanel
        form={store.form}
        roles={store.roles}
        settings={studio.settings}
        submitting={store.submitting}
        canSubmit={studio.canSubmit}
        validationError={studio.validationError}
        onChange={updateStudioForm}
        onPickBaseImage={() => void studio.pickBaseImage()}
        onSubmit={() => void studio.submit()}
      />
      <div className="grid min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto] gap-3">
        <ImageStage
          view={studio.stage}
          onOpenSettings={onOpenSettings}
          onDismissFailure={store.failure ? clearFailure : undefined}
          onReusePrompt={(record) => updateStudioForm({ prompt: record.prompt, negativePrompt: record.negative_prompt })}
        />
        <ImageFilmstrip
          items={store.history}
          selectedRecordId={store.selectedRecordId}
          revealRecordId={store.revealRecordId}
          onSelect={selectRecord}
        />
      </div>
    </section>
  );
}
