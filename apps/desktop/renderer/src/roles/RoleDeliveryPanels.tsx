import type { RoleFormState } from "../shared/types";
import { RoleChannelBindingsPanel } from "./RoleChannelBindingsPanel";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";
import { useRoleChannelCatalog } from "./useRoleChannelCatalog";

type RoleDeliveryPanelsProps = {
  activeRoleId: string;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** The role's delivery tab: channel bindings and proactive push, sharing one live channel catalog. */
export function RoleDeliveryPanels({ activeRoleId, roleForm, onUpdate }: RoleDeliveryPanelsProps) {
  const channels = useRoleChannelCatalog();
  const bindings = roleForm.channelBindings ?? [];
  return (
    <div className="grid gap-6">
      <RoleChannelBindingsPanel activeRoleId={activeRoleId} bindings={bindings} channels={channels} onUpdate={onUpdate} />
      <RoleProactiveSettingsPanel bindings={bindings} channels={channels} roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
