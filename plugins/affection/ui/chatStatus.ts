import type { AffectionSummary, PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/** What the affection plugin's `chat_status` method answers for one role. */
export type AffectionChatStatus = {
  role_id: string;
  /** Null until the role's affection is initialized. */
  affection: AffectionSummary | null;
  /** At most four tags from the relationship snapshot; empty until it is generated. */
  relation_tags: string[];
  /** 0–100; 0 until a loneliness runtime exists. */
  loneliness: number;
};

/** Reads the chat sidebar's data for the role; another role's answer is an error. */
export async function readAffectionChatStatus(client: PluginRpcClient, roleId: string) {
  const response = await client.call<AffectionChatStatus>("chat_status", { role_id: roleId });
  if (response.role_id !== roleId) throw new Error("角色不匹配");
  return response;
}
