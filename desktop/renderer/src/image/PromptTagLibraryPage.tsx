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
        <button className="flex w-fit items-center gap-2 rounded-md border border-transparent px-3 py-2 text-sm text-[#6E737A] transition hover:border-[#D9E0E8] hover:bg-white/70" type="button" onClick={onBackToImageStudio}>
          <BackIcon className="h-4 w-4 fill-current" />
          <span>返回生图工作台</span>
        </button>
        <div className="rounded-lg border border-[#D9E0E8] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]">
          <h1 className="mb-5 text-lg font-semibold text-[#263241]">提示词库</h1>
          <PromptTagLibraryPanel bridgeReady={bridgeReady} />
        </div>
      </div>
    </section>
  );
}
