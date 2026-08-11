import { ImageSquare, Tag } from "@phosphor-icons/react";
import { PluginHost } from "./PluginHost";

type PluginNavigationHostProps = {
  buttonClass: string;
  onOpenImageStudio: () => void;
  onOpenPromptTagLibrary: () => void;
};

const navigationRenderers = {
  "novelai.image-studio": { icon: ImageSquare, open: "image-studio" },
  "novelai.prompt-tags": { icon: Tag, open: "prompt-tags" },
} as const;

/** Renders navigation contributions from loaded plugins into the fixed sidebar slot. */
export function PluginNavigationHost({ buttonClass, onOpenImageStudio, onOpenPromptTagLibrary }: PluginNavigationHostProps) {
  const openers = { "image-studio": onOpenImageStudio, "prompt-tags": onOpenPromptTagLibrary } as const;
  return <PluginHost slot="navigation" render={({ contribution }) => {
    const renderer = navigationRenderers[contribution.renderer as keyof typeof navigationRenderers];
    if (!renderer) return null;
    const Icon = renderer.icon;
    return (
      <button className={buttonClass} type="button" onClick={openers[renderer.open]}>
        <span className="grid h-5 w-5 place-items-center text-[#2c2c2c]" aria-hidden="true">
          <Icon className="h-4 w-4" weight="duotone" />
        </span>
        <span>{contribution.title}</span>
      </button>
    );
  }} />;
}
