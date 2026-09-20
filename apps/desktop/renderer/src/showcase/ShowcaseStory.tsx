import { StoryPage } from "../../../../../plugins/story/ui/StoryPage";
import { PluginHostServicesProvider } from "../plugins/PluginHostServicesProvider";
import type { createDemoStoryHost } from "./demoStoryHost";
import { demoRole } from "./demoContent";

/** Keep Story's real launcher, creation wizard, playback, archive and gallery intact. */
export default function ShowcaseStory({ host, onExit }: { host: ReturnType<typeof createDemoStoryHost>; onExit: () => void }) {
  return <div className="showcase-story h-full min-h-0"><PluginHostServicesProvider services={host.services}><StoryPage client={host.client} pageId="story" activeRoleId={demoRole.id} onExit={onExit} /></PluginHostServicesProvider></div>;
}
