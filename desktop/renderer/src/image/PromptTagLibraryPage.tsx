import { PromptTagLibraryPanel } from "./PromptTagLibraryPanel";
import type { PromptTagWorkspaceSectionId } from "./PromptTagWorkspaceSidebar";

type PromptTagLibraryPageProps = {
  bridgeReady: boolean;
  section: PromptTagWorkspaceSectionId;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
};

/** Renders the full-screen prompt-tag knowledge-base page. */
export function PromptTagLibraryPage({ bridgeReady, section, onOpenSection }: PromptTagLibraryPageProps) {
  return (
    <section className="h-full overflow-hidden bg-white" data-testid="prompt-tag-library-page">
      <div className="h-full w-full">
        <PromptTagLibraryPanel bridgeReady={bridgeReady} section={section} onOpenSection={onOpenSection} />
      </div>
    </section>
  );
}
