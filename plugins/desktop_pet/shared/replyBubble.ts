/** Pet-owned reply presentation; only the lock state has a persistent message. */
export type PetReplyBubble = {
  text: string;
  paused: boolean;
  persistent: boolean;
};

/** Stable empty reply shared by the background and surface. */
export const emptyPetReply: PetReplyBubble = { text: "", paused: false, persistent: false };
