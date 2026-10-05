/** Portable identity and behavior fields shared by role forms and character cards. */
export type RoleCharacterDefinition = {
  profile: string;
  personality: string;
  behavior_rules: string;
  response_constraints: string;
  nickname: string;
};

/** The three portable character-card containers supported by import and export. */
export type RoleCardExportFormat = "charx" | "png" | "json";

/** Read-only content bound to one immutable backend export snapshot. */
export type RoleCardExportPreview = {
  export_id: string;
  name: string;
  description: string;
  character: RoleCharacterDefinition;
  format: RoleCardExportFormat;
  size: number;
  assets: Array<{ preview_url: string; labels: string[] }>;
};

/** A cancelled native dialog is not a completed export. */
export type RoleCardExportSaveResult = { saved: boolean };
