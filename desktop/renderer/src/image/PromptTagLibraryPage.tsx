import { PromptTagLibraryPanel } from "./PromptTagLibraryPanel";

type PromptTagLibraryPageProps = {
  bridgeReady: boolean;
  onBackToApp: () => void;
};

/** Renders the full-screen prompt-tag knowledge-base page. */
export function PromptTagLibraryPage({ bridgeReady, onBackToApp }: PromptTagLibraryPageProps) {
  return (
    <section className="h-full overflow-hidden bg-white" data-testid="prompt-tag-library-page">
      <div className="h-full w-full">
        <PromptTagLibraryPanel bridgeReady={bridgeReady} onBackToApp={onBackToApp} />
      </div>
    </section>
  );
}
