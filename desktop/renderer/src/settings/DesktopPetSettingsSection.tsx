import { useEffect, useMemo, useState } from "react";
import { SettingsField } from "./SettingsField";
import { SettingsToggleField } from "./SettingsFieldPrimitives";
import { inputClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type PetSettings = { enabled: boolean; roleId: string | null; packageId: string | null };

/** Manages the one role-owned desktop-pet binding outside the TOML settings form. */
export function DesktopPetSettingsSection() {
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [settings, setSettings] = useState<PetSettings | null>(null);
  const [roleId, setRoleId] = useState("");
  const [packageId, setPackageId] = useState("");
  const [error, setError] = useState("");

  const selectedRole = useMemo(() => roles.find((role) => role.id === roleId) ?? null, [roles, roleId]);
  const packages = selectedRole?.pet_packages ?? [];

  async function refresh(): Promise<void> {
    const [rolesResponse, nextSettings] = await Promise.all([
      window.miraDesktop.invoke({ method: "roles.list", payload: {} }),
      window.miraDesktop.petSettings(),
    ]);
    if (rolesResponse.error) throw new Error(rolesResponse.error.message);
    const nextRoles = rolesResponse.payload.roles as RoleRecord[];
    setRoles(nextRoles);
    setSettings(nextSettings);
    setRoleId(nextSettings.roleId ?? nextRoles.find((role) => (role.pet_packages?.length ?? 0) > 0)?.id ?? "");
    setPackageId(nextSettings.packageId ?? "");
  }

  useEffect(() => {
    void refresh().catch((reason) => setError(String(reason)));
  }, []);

  async function saveBinding(nextRoleId: string, nextPackageId: string): Promise<void> {
    if (!nextRoleId || !nextPackageId) return;
    try {
      setError("");
      setSettings(await window.miraDesktop.savePetBinding(nextRoleId, nextPackageId));
    } catch (reason) {
      setError(String(reason));
    }
  }

  async function importPackage(): Promise<void> {
    if (!roleId) return;
    const source = await window.miraDesktop.pickPetPackage();
    if (!source) return;
    const response = await window.miraDesktop.invoke({ method: "roles.pets.import", payload: { role_id: roleId, source } });
    if (response.error) {
      setError(response.error.message);
      return;
    }
    await refresh();
  }

  return (
    <section>
      <SettingsToggleField label="启用桌宠" checked={settings?.enabled ?? false} disabled={!settings?.roleId || !settings?.packageId} onChange={() => void window.miraDesktop.togglePet().then(setSettings).catch((reason) => setError(String(reason)))} />
      <SettingsField label="角色">
        <select className={inputClass} value={roleId} onChange={(event) => { setRoleId(event.target.value); setPackageId(""); }}>
          <option value="">选择角色</option>
          {roles.filter((role) => (role.pet_packages?.length ?? 0) > 0).map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
        </select>
      </SettingsField>
      <SettingsField label="素材包">
        <div className="flex gap-2">
          <select className={inputClass} value={packageId} disabled={!roleId} onChange={(event) => { const next = event.target.value; setPackageId(next); void saveBinding(roleId, next); }}>
            <option value="">选择素材包</option>
            {packages.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
          </select>
          <button className="rounded-md border border-[#D9E0E8] px-3 text-sm text-[#32363C] hover:bg-[#F5F7FA] focus:outline-none focus:ring-2 focus:ring-primary/20" type="button" disabled={!roleId} onClick={() => void importPackage()}>导入</button>
        </div>
      </SettingsField>
      {error ? <div className="py-3 text-sm text-[#A33A3A]">{error}</div> : null}
    </section>
  );
}
