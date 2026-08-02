import { ArrowLeft, BookOpenText, Plus } from "@phosphor-icons/react";
import { useState } from "react";
import type { RoleRecord } from "../shared/types";
import { StoryCreateFlow } from "./StoryCreateFlow";
import { StoryGameSurface } from "./StoryGameSurface";
import type { StoryBridgeClient } from "./bridgeClient";
import { useStoryController } from "./useStoryController";

type StoryWorkspaceProps = {
  client: StoryBridgeClient;
  roles: RoleRecord[];
  onExit: () => void;
};

/** Selects a Story or opens the bounded player-authored creation flow. */
export function StoryWorkspace({ client, roles, onExit }: StoryWorkspaceProps) {
  const controller = useStoryController(client);
  const [creating, setCreating] = useState(false);

  if (controller.story) {
    return <StoryGameSurface story={controller.story} busy={controller.busy} error={controller.error} onExit={controller.closeStory} onSend={controller.submitInput} onContinue={controller.continueStory} />;
  }
  if (creating) {
    return <StoryCreateFlow roles={roles} busy={controller.busy} onBack={() => setCreating(false)} onCreate={async (input) => { if (await controller.createStory(input)) setCreating(false); }} />;
  }
  return (
    <section className="mx-auto grid h-full w-full max-w-3xl grid-rows-[auto_minmax(0,1fr)] px-5 py-6 sm:px-8" data-testid="story-library">
      <header className="flex items-center justify-between border-b border-[#D8D0C6] pb-4"><button className="grid h-9 w-9 place-items-center rounded-md text-[#544D45] hover:bg-[#E7E2DA]" type="button" aria-label="返回聊天" title="返回聊天" onClick={onExit}><ArrowLeft size={20} /></button><h1 className="m-0 flex items-center gap-2 font-serif text-2xl"><BookOpenText size={24} />Story</h1><button className="grid h-9 w-9 place-items-center rounded-md bg-[#8E4F3A] text-white hover:bg-[#77402F]" type="button" aria-label="新 Story" title="新 Story" disabled={!roles.length} onClick={() => setCreating(true)}><Plus size={20} /></button></header>
      <div className="scrollbar-soft min-h-0 overflow-y-auto py-5">
        {controller.stories.map((story) => <button key={story.story_id} className="grid w-full gap-1 border-b border-[#E0D8CE] px-1 py-4 text-left transition hover:bg-[#EEE8DE]" type="button" onClick={() => void controller.loadStory(story.story_id)}><strong className="font-serif text-lg font-medium">{story.title}</strong><span className="text-sm text-[#766D62]">{story.created_at}</span></button>)}
        {!controller.loading && !controller.stories.length ? <button className="flex min-h-24 w-full items-center justify-center gap-2 rounded-md border border-dashed border-[#CFC7BD] text-[#765B4C] hover:bg-[#EEE8DE]" type="button" disabled={!roles.length} onClick={() => setCreating(true)}><Plus size={18} />新 Story</button> : null}
        {controller.error ? <p className="m-0 mt-4 text-sm text-[#9A3F35]" role="alert">{controller.error}</p> : null}
      </div>
    </section>
  );
}
