import { PromptTagLibraryPanel } from "./PromptTagLibraryPanel";
import { BackIcon } from "../shared/icons";

type PromptTagLibraryPageProps = {
  bridgeReady: boolean;
  onBackToImageStudio: () => void;
};

/** Renders the full-screen prompt-tag knowledge-base page. */
export function PromptTagLibraryPage({ bridgeReady, onBackToImageStudio }: PromptTagLibraryPageProps) {
  return (
    <section className="h-full overflow-y-auto bg-[linear-gradient(180deg,#F7F8FB_0%,#EEF2F7_100%)]" data-testid="prompt-tag-library-page">
      <div className="mx-auto grid w-full max-w-[1120px] gap-5 px-8 pb-10 pt-6">
        <button className="flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-[#6E737A] transition hover:border-[#D9E0E8] hover:bg-white/70" type="button" aria-label="返回生图工作台" title="返回生图工作台" onClick={onBackToImageStudio}>
          <BackIcon className="h-4 w-4 fill-current" />
        </button>
        <PromptTagLibraryPanel bridgeReady={bridgeReady} />
      </div>
    </section>
  );
}
