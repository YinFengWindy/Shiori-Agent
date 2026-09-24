import type { SelectOption } from "../shared/ui/Select";

const everydayProfiles: SelectOption[] = [
  { value: "daily", label: "日常" },
  { value: "quiet", label: "低打扰" },
];

const devVerifyProfile: SelectOption = { value: "dev_verify", label: "开发验证" };

/**
 * Proactive strategy choices. 开发验证 is a developer tool, so it is offered
 * only in dev mode, or when the role already uses it (the picker must still
 * be able to show and leave the saved value).
 */
export function proactiveProfileOptions(devMode: boolean, currentProfile: string): SelectOption[] {
  return devMode || currentProfile === devVerifyProfile.value ? [...everydayProfiles, devVerifyProfile] : everydayProfiles;
}
