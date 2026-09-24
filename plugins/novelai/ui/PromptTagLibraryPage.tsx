import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import type { PromptTagWorkspaceSectionId } from "./novelAiPageStore";
import { PromptTagLibraryPanel } from "./PromptTagLibraryPanel";

type PromptTagLibraryPageProps = {
  client: PluginRpcClient;
  bridgeReady: boolean;
  section: PromptTagWorkspaceSectionId;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
};

/** Renders the full-page prompt-tag library. */
export function PromptTagLibraryPage({ client, bridgeReady, section, onOpenSection }: PromptTagLibraryPageProps) {
  return (
    <section className="h-full overflow-hidden bg-gradient-app bg-fixed" data-testid="prompt-tag-library-page">
      <PromptTagLibraryPanel client={client} bridgeReady={bridgeReady} section={section} onOpenSection={onOpenSection} />
    </section>
  );
}
