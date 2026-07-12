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
        <button className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white text-[#111111] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] focus:outline-none" type="button" aria-label="返回生图工作台" title="返回生图工作台" onClick={onBackToImageStudio}>
          <BackIcon className="h-5 w-5 fill-current" />
        </button>
        <PromptTagLibraryPanel bridgeReady={bridgeReady} />
      </div>
    </section>
  );
}
