import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/shared";
import type { RoleRecord } from "../shared/types";
import {
  runtimeConfigForSelection,
  selectionFromRole,
  type ModelEffort,
  type RoleModelSelection,
} from "./chatModelSelection";

type ChatModelMenuProps = {
  activeRoleId: string;
  bridgeReady: boolean;
};

/** Owns the compact role-level model and dialogue effort selectors. */
export function ChatModelMenu({ activeRoleId, bridgeReady }: ChatModelMenuProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [submenu, setSubmenu] = useState<"dialogue" | "visual" | null>(null);
  const [detailMenu, setDetailMenu] = useState<"model" | "effort" | null>(null);
  const [registrations, setRegistrations] = useState<ModelRegistrationFormData[]>([]);
  const [selection, setSelection] = useState<RoleModelSelection | null>(null);

  const loadSelection = useEffectEvent(async () => {
    if (!activeRoleId || !bridgeReady) return;
    try {
      const [settings, rolesResponse] = await Promise.all([
        window.miraDesktop.readSettings(),
        window.miraDesktop.invoke({ method: "roles.list", payload: {} }),
      ]);
      if (rolesResponse.error) throw new Error(rolesResponse.error.message);
      const roles = Array.isArray(rolesResponse.payload.roles)
        ? rolesResponse.payload.roles as RoleRecord[]
        : [];
      const role = roles.find((item) => item.id === activeRoleId);
      if (!role) throw new Error("当前角色不存在");
      setRegistrations(settings.formData.models.registrations);
      setSelection(selectionFromRole(role, settings.formData.models.registrations));
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error));
    }
  });

  useEffect(() => {
    setOpen(false);
    setSubmenu(null);
    setDetailMenu(null);
    setSelection(null);
    void loadSelection();
  }, [activeRoleId, bridgeReady]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: PointerEvent) => {
      if (containerRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [open]);

  async function updateSelection(kind: "dialogue" | "visual" | "dialogueEffort" | "visualEffort", value: string): Promise<void> {
    if (!selection || !activeRoleId) return;
    const runtimeConfig = runtimeConfigForSelection(selection, kind, value);
    try {
      const response = await window.miraDesktop.invoke({
        method: "roles.update",
        payload: { role_id: activeRoleId, runtime_config: runtimeConfig },
      });
      if (response.error) throw new Error(response.error.message);
      const role = response.payload.role as RoleRecord | undefined;
      setSelection(role ? selectionFromRole(role, registrations) : {
        dialogueId: String(runtimeConfig.dialogue_model_registration_id),
        visualId: String(runtimeConfig.visual_model_registration_id),
        dialogueEffort: String(runtimeConfig.dialogue_model_effort) as ModelEffort,
        visualEffort: String(runtimeConfig.visual_model_effort) as ModelEffort,
        runtimeConfig,
      });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error));
    }
  }

  const dialogue = registrations.find((item) => item.id === selection?.dialogueId);
  if (!activeRoleId) return null;

  return (
    <div className="relative" ref={containerRef}>
      <button
        className="inline-flex h-[30px] max-w-[190px] items-center rounded-md px-2 text-xs text-[#5B6472] transition hover:bg-[#F3F5F7] hover:text-[#22272E] focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-40"
        type="button"
        aria-label="选择角色模型"
        aria-expanded={open}
        disabled={!bridgeReady || !selection}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="truncate">{dialogue?.model ?? "选择模型"}</span>
      </button>
      {open && selection ? (
        <div className="absolute bottom-9 left-0 z-20 flex rounded-md border border-[#DDE3EA] bg-white p-1.5 shadow-[0_16px_40px_rgba(15,23,42,0.14)]">
          <div className="grid w-[112px] content-start gap-1">
            {(["dialogue", "visual"] as const).map((kind) => (
              <button key={kind} type="button" className="flex h-9 items-center justify-between rounded-md px-2 text-left text-xs text-[#344054] transition hover:bg-[#F3F5F7]" onMouseEnter={() => { setSubmenu(kind); setDetailMenu(null); }} onClick={() => { setSubmenu(kind); setDetailMenu(null); }}>
                <span>{kind === "dialogue" ? "对话模型" : "识图模型"}</span><span aria-hidden="true">›</span>
              </button>
            ))}
          </div>
          {submenu ? (
            <div className="relative ml-1 min-w-[132px] border-l border-[#EEF1F4] pl-2">
              <div className="grid gap-1">
                <button type="button" className="flex h-9 items-center justify-between rounded-md px-2 text-left text-xs text-[#344054] transition hover:bg-[#F3F5F7]" onMouseEnter={() => setDetailMenu("model")} onClick={() => setDetailMenu("model")}><span>模型</span><span aria-hidden="true">›</span></button>
                <button type="button" className="flex h-9 items-center justify-between rounded-md px-2 text-left text-xs text-[#344054] transition hover:bg-[#F3F5F7]" onMouseEnter={() => setDetailMenu("effort")} onClick={() => setDetailMenu("effort")}><span>思考强度</span><span aria-hidden="true">›</span></button>
              </div>
              {detailMenu ? (
                <div className="absolute left-full top-0 ml-1 grid min-w-[150px] gap-1 rounded-md border border-[#DDE3EA] bg-white p-1.5 shadow-[0_16px_40px_rgba(15,23,42,0.14)]">
                  {detailMenu === "model" ? <>
                    {submenu === "visual" ? <button type="button" className="rounded-md px-2 py-2 text-left text-xs text-[#344054] transition hover:bg-[#F3F5F7]" onClick={() => void updateSelection("visual", "")}>沿用对话模型</button> : null}
                    {registrations.map((registration) => <button key={registration.id} type="button" className="rounded-md px-2 py-2 text-left text-xs text-[#344054] transition hover:bg-[#F3F5F7]" onClick={() => void updateSelection(submenu, registration.id)}>{registration.model}</button>)}
                  </> : (["none", "low", "high", "max"] as const).map((effort) => <button key={effort} type="button" className="rounded-md px-2 py-2 text-left text-xs text-[#344054] transition hover:bg-[#F3F5F7]" onClick={() => void updateSelection(submenu === "dialogue" ? "dialogueEffort" : "visualEffort", effort)}>{effort === "none" ? "关闭" : effort === "low" ? "低" : effort === "high" ? "高" : "最大"}</button>)}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
