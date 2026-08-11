import { PromptLibraryIcon } from "../shared/icons";
import { usePluginCatalogContext } from "./PluginCatalogContext";

type PluginNavigationHostProps = {
  buttonClass: string;
  onOpenImageStudio: () => void;
  onOpenPromptTagLibrary: () => void;
};

const novelAiLogoDark = new URL("../assets/novelai-logo-dark.svg", import.meta.url).href;

/** Preserves the existing NovelAI navigation layout while gating it by loaded contributions. */
export function PluginNavigationHost({ buttonClass, onOpenImageStudio, onOpenPromptTagLibrary }: PluginNavigationHostProps) {
  const contributions = usePluginCatalogContext().contributions("navigation");
  const imageStudio = contributions.find(({ contribution }) => contribution.renderer === "novelai.image-studio")?.contribution;
  const promptTags = contributions.find(({ contribution }) => contribution.renderer === "novelai.prompt-tags")?.contribution;
  if (!imageStudio && !promptTags) return null;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_34px] gap-1">
      {imageStudio ? (
        <button className={buttonClass} type="button" onClick={onOpenImageStudio}>
          <span className="sidebar-entry-icon sidebar-entry-image grid h-5 w-5 place-items-center" aria-hidden="true">
            <img className="h-4 w-4" src={novelAiLogoDark} alt="" />
          </span>
          <span>{imageStudio.title}</span>
        </button>
      ) : <span />}
      {promptTags ? (
        <button
          className="grid min-h-[34px] place-items-center rounded-[10px] border border-transparent bg-transparent text-[#3f3f3f] transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF]"
          type="button"
          aria-label={`打开${promptTags.title}`}
          title={`打开${promptTags.title}`}
          onClick={onOpenPromptTagLibrary}
        >
          <PromptLibraryIcon className="h-4 w-4 fill-current" />
        </button>
      ) : null}
    </div>
  );
}
