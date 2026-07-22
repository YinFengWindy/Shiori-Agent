import { useEffect, useState } from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";

type PetSettings = { enabled: boolean; roleId: string | null; packageId: string | null };

type RoleDesktopPetToggleProps = {
  roleId: string;
  available: boolean;
  bridgeReady: boolean;
};

/** Controls whether this role owns the single visible desktop-pet slot. */
export function RoleDesktopPetToggle({ roleId, available, bridgeReady }: RoleDesktopPetToggleProps) {
  const [settings, setSettings] = useState<PetSettings | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const checked = Boolean(settings?.enabled && settings.roleId === roleId);

  useEffect(() => {
    setSettings(null);
    setError("");
    void window.miraDesktop.petSettings().then(setSettings).catch((reason) => setError(String(reason)));
  }, [roleId]);

  async function toggle(): Promise<void> {
    setPending(true);
    setError("");
    try {
      setSettings(await window.miraDesktop.togglePetForRole(roleId));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-xs text-[#374151]">
        <span>桌宠</span>
        <SettingsToggleCard
          checked={checked}
          ariaLabel="桌宠"
          disabled={!bridgeReady || (!available && !checked) || pending || settings === null}
          onChange={() => void toggle()}
        />
      </div>
      {error ? <div className="pt-2 text-xs text-[#A33A3A]">{error}</div> : null}
    </div>
  );
}
