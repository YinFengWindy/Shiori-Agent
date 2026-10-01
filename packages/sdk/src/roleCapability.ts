/** How a capability badge is tinted: working, switched off, or on but blocked by something. */
export type RoleCapabilityTone = "on" | "off" | "attention";

/** The badge a role capability card shows next to its title. */
export type RoleCapabilityStatus = { label: string; tone: RoleCapabilityTone };

/** Status of a plain on/off capability; `unavailableLabel` wins when the switch cannot be used. */
export function roleToggleStatus(checked: boolean, unavailableLabel = ""): RoleCapabilityStatus {
  if (unavailableLabel) return { label: unavailableLabel, tone: "off" };
  return checked ? { label: "已启用", tone: "on" } : { label: "未启用", tone: "off" };
}
