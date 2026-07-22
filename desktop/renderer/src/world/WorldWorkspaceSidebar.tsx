import { CaretRight, GlobeHemisphereEast, Plus, UserCircle } from "@phosphor-icons/react";
import { cx } from "../shared/styles";
import type { WorldDetails, WorldSummary } from "./types";

type WorldWorkspaceSidebarProps = {
  worlds: WorldSummary[];
  world: WorldDetails;
  onSelectWorld: (worldId: string) => void;
  onSwitchOc: (ocId: string) => void;
  onCreateWorld: () => void;
};

/** Renders world and controlled-character switching in the workspace left rail. */
export function WorldWorkspaceSidebar({ worlds, world, onSelectWorld, onSwitchOc, onCreateWorld }: WorldWorkspaceSidebarProps) {
  return (
    <aside className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] border-r border-[#DFE5EA] bg-[#EFF4F9] p-3">
      <div className="mb-3 flex items-center justify-between px-1">
        <h2 className="m-0 font-serif text-base font-semibold text-[#252A2E]">世界</h2>
        <button className="grid h-8 w-8 place-items-center rounded-md text-[#5D666E] hover:bg-white" type="button" aria-label="创建世界" onClick={onCreateWorld}><Plus /></button>
      </div>
      <div className="min-h-0 space-y-5 overflow-y-auto">
        <nav className="grid gap-1" aria-label="世界列表">
          {worlds.map((item) => (
            <button
              key={item.id}
              className={cx("flex min-h-11 items-center gap-2 rounded-md px-2.5 text-left text-sm transition", item.id === world.id ? "bg-white font-medium shadow-sm" : "hover:bg-white/70")}
              type="button"
              onClick={() => onSelectWorld(item.id)}
            >
              <GlobeHemisphereEast className="h-5 w-5 shrink-0 text-[#6C7771]" />
              <span className="min-w-0 flex-1 truncate">{item.name}</span>
              {item.id === world.id ? <CaretRight className="h-4 w-4" /> : null}
            </button>
          ))}
        </nav>
        <section>
          <h3 className="mb-2 px-2 text-xs font-medium text-[#7A8188]">此刻的人</h3>
          <div className="grid gap-1">
            {world.ocs.map((oc) => (
              <button
                key={oc.id}
                className={cx("flex min-h-12 items-center gap-2 rounded-md border px-2.5 text-left transition", oc.id === world.activeOcId ? "border-[#E39A76] bg-[#FFF8F3]" : "border-transparent hover:bg-white/70")}
                type="button"
                aria-pressed={oc.id === world.activeOcId}
                onClick={() => onSwitchOc(oc.id)}
              >
                {oc.avatarUrl ? <img className="h-8 w-8 rounded-md object-cover" src={oc.avatarUrl} alt="" /> : <UserCircle className="h-8 w-8 text-[#8B9298]" weight="thin" />}
                <span className="min-w-0"><span className="block truncate text-sm font-medium">{oc.name}</span><span className="block truncate text-[11px] text-[#777F86]">{oc.location}</span></span>
              </button>
            ))}
          </div>
        </section>
      </div>
      <div className="border-t border-[#DDE4EA] px-1 pt-3 text-xs text-[#6F777D]">{world.currentTimeLabel}</div>
    </aside>
  );
}
