import type { RoleFormState } from "../shared/types";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";
import { useSettingsSnapshot } from "./useSettingsSnapshot";

type RoleDeliveryPanelsProps = {
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** The role's proactive settings; communication accounts live in the profile panel. */
export function RoleDeliveryPanels({ roleForm, onUpdate }: RoleDeliveryPanelsProps) {
  const settings = useSettingsSnapshot();
  return (
    <div className="grid gap-7">
      <RoleProactiveSettingsPanel devMode={settings?.advanced.devMode === true} roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
