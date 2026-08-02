import { ArrowLeft, PaperPlaneRight, Play } from "@phosphor-icons/react";
import { useState } from "react";
import type { StoryDetails } from "./types";

type StoryGameSurfaceProps = {
  story: StoryDetails;
  busy: boolean;
  error: string;
  onExit: () => void;
  onSend: (input: string) => Promise<void>;
  onContinue: () => Promise<void>;
};

/** Presents only committed text Cues and accepts the next player turn. */
export function StoryGameSurface({ story, busy, error, onExit, onSend, onContinue }: StoryGameSurfaceProps) {
  const [input, setInput] = useState("");
  const generating = busy || story.segment.operation === "generating";

  return (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-[#F5F1E9] text-[#29251F]" data-testid="story-game-surface">
      <header className="flex items-center gap-3 border-b border-[#D8D0C6] px-4 py-3 sm:px-7">
        <button className="grid h-9 w-9 place-items-center rounded-md text-[#544D45] hover:bg-[#E7E2DA]" type="button" aria-label="返回 Story 书库" title="返回 Story 书库" onClick={onExit}><ArrowLeft size={20} /></button>
        <div className="min-w-0"><h1 className="m-0 truncate font-serif text-xl">{story.title}</h1><p className="m-0 truncate text-xs text-[#766D62]">{story.roleSnapshot.name ?? ""}</p></div>
      </header>
      <div className="scrollbar-soft mx-auto flex w-full max-w-3xl min-h-0 flex-col gap-5 overflow-y-auto px-5 py-7 sm:px-8">
        {story.cues.map((cue) => (
          <article key={cue.id} className="border-l-2 border-[#A36C4E] pl-4">
            {cue.speaker ? <p className="m-0 mb-1 text-sm font-semibold text-[#8E4F3A]">{cue.speaker}</p> : null}
            <p className="m-0 whitespace-pre-wrap text-[15px] leading-8 text-[#322C25]">{cue.text}</p>
          </article>
        ))}
        {generating ? <p className="m-0 text-sm text-[#84796C]">...</p> : null}
      </div>
      <div className="border-t border-[#D8D0C6] bg-[#FBF9F5] px-4 py-4 sm:px-7">
        <form className="mx-auto flex w-full max-w-3xl items-end gap-2" onSubmit={(event) => { event.preventDefault(); const next = input.trim(); if (!next || generating) return; setInput(""); void onSend(next); }}>
          <textarea className="min-h-11 flex-1 resize-none rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-sm text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20 disabled:opacity-60" rows={1} disabled={generating} value={input} onChange={(event) => setInput(event.target.value)} />
          <button className="grid h-11 w-11 place-items-center rounded-md bg-[#8E4F3A] text-white transition hover:bg-[#77402F] disabled:opacity-45" type="submit" disabled={generating || !input.trim()} aria-label="发送行动" title="发送行动"><PaperPlaneRight size={20} weight="fill" /></button>
          <button className="flex h-11 items-center gap-1.5 rounded-md border border-[#BFAF9E] px-3 text-sm text-[#5C493D] transition hover:bg-[#EDE7DE] disabled:opacity-45" type="button" disabled={generating} onClick={() => void onContinue()}><Play size={15} weight="fill" />继续</button>
        </form>
        {error ? <p className="mx-auto mt-2 w-full max-w-3xl text-sm text-[#9A3F35]" role="alert">{error}</p> : null}
      </div>
    </section>
  );
}
