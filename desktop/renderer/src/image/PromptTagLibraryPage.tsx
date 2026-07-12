import { PromptTagLibraryPanel } from "./PromptTagLibraryPanel";

type PromptTagLibraryPageProps = {
  bridgeReady: boolean;
  onBackToImageStudio: () => void;
};

/** Renders the full-screen prompt-tag knowledge-base page. */
export function PromptTagLibraryPage({ bridgeReady, onBackToImageStudio }: PromptTagLibraryPageProps) {
  return (
    <section className="h-full overflow-hidden bg-white" data-testid="prompt-tag-library-page">
      <div className="h-full w-full">
        <PromptTagLibraryPanel bridgeReady={bridgeReady} onBackToImageStudio={onBackToImageStudio} />
      </div>
    </section>
  );
}
