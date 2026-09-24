import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { useEffect } from "react";
import type { PluginNavPageComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { PetalIcon } from "../../../apps/desktop/renderer/src/shared/ui/icons";
import { ImageStudioPage } from "./ImageStudioPage";
import { PromptTagLibraryPage } from "./PromptTagLibraryPage";
import { openPromptTagWorkspaceSection, refreshRoles, reportPageError, useNovelAiPageStore } from "./novelAiPageStore";

/**
 * The novelai plugin's single `nav.page` entry: the image studio and the
 * prompt-tag library (issue #180). Its sidebar (`NovelAIPageSidebar`) is a
 * separate mount point in the host's sidebar track; the two share state
 * through `novelAiPageStore`.
 *
 * Zero-role guard: the nav rail refuses to navigate here while no role
 * exists (`selectBlockedReasonForNovelAiPage`, a warning toast). That check
 * is best-effort — it answers from a cached roster that may not have loaded
 * on a cold first click, and history back/forward bypasses it — so the
 * empty state below stays as the backstop.
 */
export function NovelAIPage({ client, activeRoleId, onOpenPluginSettings }: PluginNavPageComponentProps) {
  const host = usePluginHostServices();
  const store = useNovelAiPageStore();

  useEffect(() => {
    void refreshRoles(host).catch(reportPageError);
  }, [host]);

  if (store.rolesLoaded && store.roles.length === 0) {
    return (
      <div className="grid h-full place-items-center bg-gradient-app bg-fixed p-6" data-testid="novelai-no-roles">
        <div className="grid justify-items-center gap-3 text-center">
          <span className="grid h-14 w-14 place-items-center rounded-full bg-accent-softer text-accent">
            <PetalIcon className="h-6 w-6" />
          </span>
          <span className="text-body text-ink-secondary">请先创建至少一个角色，再进入生图。</span>
        </div>
      </div>
    );
  }

  if (store.view === "prompt-tags") {
    return (
      <PromptTagLibraryPage
        client={client}
        bridgeReady={store.rolesLoaded}
        section={store.promptTagSection}
        onOpenSection={openPromptTagWorkspaceSection}
      />
    );
  }

  return <ImageStudioPage client={client} activeRoleId={activeRoleId ?? ""} onOpenSettings={onOpenPluginSettings} />;
}
