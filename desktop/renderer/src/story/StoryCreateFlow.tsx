import { ArrowLeft, Play } from "@phosphor-icons/react";
import { useState } from "react";
import type { RoleRecord } from "../shared/types";
import type { StoryCreationInput } from "./types";

type StoryCreateFlowProps = {
  roles: RoleRecord[];
  busy: boolean;
  onCreate: (input: StoryCreationInput) => Promise<void>;
  onBack: () => void;
};

function chinaNow(): string {
  return `${new Intl.DateTimeFormat("sv-SE", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "Asia/Shanghai",
  }).format(new Date()).replace(" ", "T")}+08:00`;
}

/** Collects the player-owned metadata required to freeze a Story opening. */
export function StoryCreateFlow({ roles, busy, onCreate, onBack }: StoryCreateFlowProps) {
  const [form, setForm] = useState<StoryCreationInput>({
    title: "",
    background: "",
    startsAt: chinaNow(),
    roleId: roles[0]?.id ?? "",
    playerProfile: { displayName: "", appearance: "", identity: "" },
  });

  const update = (key: keyof StoryCreationInput, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  return (
    <section className="mx-auto grid h-full w-full max-w-3xl content-center gap-6 px-5 py-8" data-testid="story-create-flow">
      <div className="flex items-center justify-between">
        <button className="grid h-9 w-9 place-items-center rounded-md text-[#564F46] hover:bg-[#E7E2DA]" type="button" aria-label="返回 Story 书库" title="返回 Story 书库" onClick={onBack}><ArrowLeft size={20} /></button>
        <h1 className="m-0 font-serif text-2xl text-[#29261F]">新 Story</h1>
        <span className="h-9 w-9" />
      </div>
      <form
        className="grid gap-4 border-y border-[#D8D0C6] py-5"
        onSubmit={(event) => {
          event.preventDefault();
          void onCreate(form);
        }}
      >
        <label className="grid gap-1.5 text-sm text-[#544D45]">标题<input className="rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20" required value={form.title} onChange={(event) => update("title", event.target.value)} /></label>
        <label className="grid gap-1.5 text-sm text-[#544D45]">开场<select className="rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20" required value={form.roleId} onChange={(event) => update("roleId", event.target.value)}>{roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
        <label className="grid gap-1.5 text-sm text-[#544D45]">背景<textarea className="min-h-20 rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20" required value={form.background} onChange={(event) => update("background", event.target.value)} /></label>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="grid gap-1.5 text-sm text-[#544D45]">名字<input className="rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20" required value={form.playerProfile.displayName} onChange={(event) => setForm((current) => ({ ...current, playerProfile: { ...current.playerProfile, displayName: event.target.value } }))} /></label>
          <label className="grid gap-1.5 text-sm text-[#544D45]">外貌<input className="rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20" required value={form.playerProfile.appearance} onChange={(event) => setForm((current) => ({ ...current, playerProfile: { ...current.playerProfile, appearance: event.target.value } }))} /></label>
          <label className="grid gap-1.5 text-sm text-[#544D45]">身份<input className="rounded-md border border-[#CFC7BD] bg-white px-3 py-2.5 text-[#25211C] transition focus:border-[#9B5D44] focus:outline-none focus:ring-2 focus:ring-[#9B5D44]/20" required value={form.playerProfile.identity} onChange={(event) => setForm((current) => ({ ...current, playerProfile: { ...current.playerProfile, identity: event.target.value } }))} /></label>
        </div>
        <button className="flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#8E4F3A] px-4 py-2.5 text-sm text-white transition hover:bg-[#77402F] disabled:opacity-45" type="submit" disabled={busy || !roles.length}><Play size={18} weight="fill" />开始</button>
      </form>
    </section>
  );
}
