import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/shared";
import type { RoleRecord } from "../shared/types";

type ChatModelMenuProps = {
  activeRoleId: string;
  bridgeReady: boolean;
};

type RoleModelSelection = {
  dialogueId: string;
  visualId: string;
  runtimeConfig: Record<string, unknown>;
};

function selectionFromRole(role: RoleRecord): RoleModelSelection {
  return {
    dialogueId: String(role.runtime_config.dialogue_model_registration_id ?? ""),
    visualId: String(role.runtime_config.visual_model_registration_id ?? ""),
    runtimeConfig: role.runtime_config,
  };
}

/** Owns the compact role-level dialogue and visual model selectors. */
export function ChatModelMenu({ activeRoleId, bridgeReady }: ChatModelMenuProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
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
      setSelection(selectionFromRole(role));
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error));
    }
  });

  useEffect(() => {
    setOpen(false);
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

  async function updateSelection(kind: "dialogue" | "visual", registrationId: string): Promise<void> {
    if (!selection || !activeRoleId) return;
    const runtimeConfig = {
      ...selection.runtimeConfig,
      dialogue_model_registration_id: kind === "dialogue" ? registrationId : selection.dialogueId,
      visual_model_registration_id: kind === "visual" ? registrationId : selection.visualId,
    };
    try {
      const response = await window.miraDesktop.invoke({
        method: "roles.update",
        payload: { role_id: activeRoleId, runtime_config: runtimeConfig },
      });
      if (response.error) throw new Error(response.error.message);
      const role = response.payload.role as RoleRecord | undefined;
      setSelection(role ? selectionFromRole(role) : {
        dialogueId: String(runtimeConfig.dialogue_model_registration_id),
        visualId: String(runtimeConfig.visual_model_registration_id),
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
        <div className="absolute bottom-9 left-0 z-20 grid w-[280px] gap-3 rounded-md border border-[#DDE3EA] bg-white p-3 shadow-[0_16px_40px_rgba(15,23,42,0.14)]">
          <label className="grid gap-1.5 text-xs text-[#667085]">
            <span>对话模型</span>
            <select className="h-9 rounded-md border border-[#D8DFE7] bg-white px-2 text-sm text-[#182230] transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20" value={selection.dialogueId} onChange={(event) => void updateSelection("dialogue", event.target.value)}>
              {registrations.map((registration) => <option key={registration.id} value={registration.id}>{registration.model}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-xs text-[#667085]">
            <span>视觉模型</span>
            <select className="h-9 rounded-md border border-[#D8DFE7] bg-white px-2 text-sm text-[#182230] transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20" value={selection.visualId} onChange={(event) => void updateSelection("visual", event.target.value)}>
              <option value="">沿用对话模型</option>
              {registrations.map((registration) => <option key={registration.id} value={registration.id}>{registration.model}</option>)}
            </select>
          </label>
        </div>
      ) : null}
    </div>
  );
}
