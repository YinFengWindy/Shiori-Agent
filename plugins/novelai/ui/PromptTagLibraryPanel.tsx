import { useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { errorMessage } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import type { PromptTagWorkspaceSectionId } from "./novelAiPageStore";
import { PromptTagEntryEditor } from "./PromptTagEntryEditor";
import { PromptTagGrid } from "./PromptTagGrid";
import type { PromptTagEntry } from "./types";
import { usePromptTagLibrary } from "./usePromptTagLibrary";

type PromptTagLibraryPanelProps = {
  client: PluginRpcClient;
  bridgeReady: boolean;
  section: PromptTagWorkspaceSectionId;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
};

/** Routes the prompt-tag workspace between its card list and the entry editor; deletes ask first. */
export function PromptTagLibraryPanel({ client, bridgeReady, section, onOpenSection }: PromptTagLibraryPanelProps) {
  const { ui } = usePluginHostServices();
  const library = usePromptTagLibrary(client, bridgeReady, section, onOpenSection);
  const [pendingDelete, setPendingDelete] = useState<PromptTagEntry | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  async function confirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await library.remove(pendingDelete.id);
      setPendingDelete(null);
    } catch (error) {
      setDeleteError(errorMessage(error));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section className="scrollbar-stable h-full overflow-y-auto px-6 py-6" data-testid="prompt-tag-library">
      <div className="mx-auto w-full max-w-[1120px]">
        {section === "list" ? (
          <PromptTagGrid
            entries={library.entries}
            loaded={library.loaded}
            onOpen={library.open}
            onCreate={() => onOpenSection("create")}
            onDelete={(entry) => { setDeleteError(""); setPendingDelete(entry); }}
          />
        ) : (
          <PromptTagEntryEditor
            draft={library.draft}
            creating={library.creating}
            error={library.error}
            saving={library.saving}
            bridgeReady={bridgeReady}
            dirty={library.dirty}
            onChange={library.setDraft}
            onSave={() => void library.save()}
            onBack={() => onOpenSection("list")}
            onReset={library.reset}
          />
        )}
      </div>
      {/* The host dialog (runtime API 2.4.0); 吟风 leads it with the host's line for a deletion. */}
      <ui.ConfirmDialog
        open={Boolean(pendingDelete)}
        persona="destructive"
        title="删除提示词"
        description={pendingDelete ? `“${pendingDelete.name}” 删除后无法恢复。` : ""}
        confirmLabel="删除"
        busy={deleting}
        error={deleteError}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
      />
    </section>
  );
}
