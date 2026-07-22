import { FilmStrip, Flag, Hourglass, MapPin, Stop, UsersThree } from "@phosphor-icons/react";
import type { WorldDetails, WorldOc } from "./types";
import { getWorldStatusLabel } from "./selectors";

type WorldStatusSidebarProps = {
  world: WorldDetails;
  activeOc: WorldOc | null;
  onOpenTimeline: () => void;
  onOpenFocus: () => void;
  onCancel: () => void;
};

/** Renders compact scene, OC, cast, decision, and performance state. */
export function WorldStatusSidebar({ world, activeOc, onOpenTimeline, onOpenFocus, onCancel }: WorldStatusSidebarProps) {
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-[#E0E4E1] bg-white p-4">
      <div className="grid gap-5">
        <section><div className="mb-2 flex items-center justify-between"><h2 className="m-0 font-serif text-base font-semibold">此刻</h2><span className="rounded-md bg-[#EEF2EF] px-2 py-1 text-[11px] text-[#5E6861]">{getWorldStatusLabel(world.status)}</span></div><p className="m-0 flex items-center gap-2 text-sm text-[#515753]"><MapPin />{world.scene.location}</p></section>
        {activeOc ? <section><h3 className="mb-2 text-xs font-medium text-[#7A817C]">当前 OC</h3><div className="grid gap-2 rounded-md border border-[#E2E4DF] bg-[#FAFAF8] p-3"><strong className="text-sm">{activeOc.name}</strong><span className="text-xs leading-5 text-[#666C68]">{activeOc.identity}</span><span className="flex items-start gap-2 text-xs text-[#666C68]"><Flag className="mt-0.5 shrink-0" />{activeOc.primaryGoal}</span></div></section> : null}
        <section><h3 className="mb-2 flex items-center gap-2 text-xs font-medium text-[#7A817C]"><UsersThree />关联角色</h3><div className="grid gap-2">{world.relatedCharacters.map((character) => <div key={character.id} className="flex items-center justify-between gap-2 text-sm"><span className="truncate">{character.name}</span><span className="shrink-0 text-xs text-[#838985]">{character.relationship}</span></div>)}</div></section>
        {world.scene.opportunities.length ? <section><h3 className="mb-2 text-xs font-medium text-[#7A817C]">可知机会</h3><ul className="m-0 grid gap-2 pl-4 text-xs leading-5 text-[#606662]">{world.scene.opportunities.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
        {world.scene.barriers.length ? <section className="rounded-md border border-[#E9C8B6] bg-[#FFF8F3] p-3"><h3 className="m-0 flex items-center gap-2 text-sm font-semibold"><Hourglass />{world.scene.barriers.length} 件事等待决定</h3></section> : null}
        <section className="grid gap-2 border-t border-[#E5E7E3] pt-4">
          {world.performance.active ? <button className="flex h-10 items-center gap-2 rounded-md bg-[#2F3532] px-3 text-sm text-white" type="button" onClick={onOpenFocus}><FilmStrip />{world.performance.label}</button> : null}
          <button className="h-10 rounded-md border border-[#DDE1DD] text-sm hover:bg-[#F5F6F4]" type="button" onClick={onOpenTimeline}>打开时间线</button>
          {world.performance.canCancel ? <button className="flex h-9 items-center justify-center gap-2 rounded-md text-xs text-[#8C5042] hover:bg-[#FFF5F1]" type="button" onClick={onCancel}><Stop weight="fill" />停止推进</button> : null}
        </section>
      </div>
    </aside>
  );
}
