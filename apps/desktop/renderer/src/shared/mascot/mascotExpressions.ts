/** 吟风's expressions, in the order the sprite stack is layered. */
export const mascotExpressions = ["neutral", "smug", "laugh", "shy", "confused", "pout", "sad", "surprised"] as const;

/** One of 吟风's expressions: 普通 / 得意坏笑 / 开心大笑 / 害羞 / 疑惑 / 生气鼓脸 / 担心 / 惊讶. */
export type MascotExpression = (typeof mascotExpressions)[number];

/** 吟风's name, shown on the dialogue name plate. */
export const mascotName = "吟风";
