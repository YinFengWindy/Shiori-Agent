import type { ChatSendRequest, SessionMessage } from "../shared/types";
import { chatSamples, initialChatMessages } from "./demoContent";
import { readDemoStorage, type DemoStorage } from "./demoStorage";

const storageKey = "shiori-showcase.chat.v1";
type ChatSnapshot = { messages: SessionMessage[]; sampleIndex: number; sending: boolean; mood: string; thought: string; error: string };
const delay = () => new Promise<void>((resolve) => setTimeout(resolve, 28));

function validSnapshot(value: unknown): value is ChatSnapshot {
  if (!value || typeof value !== "object") return false;
  return "messages" in value && Array.isArray(value.messages) && value.messages.length < 200
    && value.messages.every((message: unknown) => !!message && typeof message === "object" && "content" in message && typeof message.content === "string" && "role" in message && typeof message.role === "string")
    && "sampleIndex" in value && typeof value.sampleIndex === "number" && Number.isSafeInteger(value.sampleIndex) && value.sampleIndex >= 0
    && "mood" in value && typeof value.mood === "string" && "thought" in value && typeof value.thought === "string";
}

/** Own deterministic streaming, cancellation and local history for the real chat views. */
export function createDemoChat(storage: DemoStorage, wait = delay) {
  const restored = readDemoStorage(storage, storageKey, validSnapshot);
  let state: ChatSnapshot = restored ? { ...restored, sending: false, error: "", messages: restored.messages.map((message) => ({
    id: typeof message.id === "string" ? message.id : crypto.randomUUID(),
    role: message.role === "user" ? "user" : "assistant", content: message.content,
    timestamp: typeof message.timestamp === "string" ? message.timestamp : undefined,
    // Browser storage may be edited; restore only text and known quote fields.
    metadata: Object.fromEntries(["reply_to_content", "reply_to_message_id", "reply_to_sender"].flatMap((key) => typeof message.metadata?.[key] === "string" ? [[key, message.metadata[key]]] : [])),
  })) } : {
    messages: initialChatMessages(), sampleIndex: 0, sending: false, mood: "平静", thought: "外面又下雨了，希望来的人没有淋湿。", error: "",
  };
  let generation = 0;
  const listeners = new Set<() => void>();
  const update = (next: ChatSnapshot) => { state = next; for (const listener of listeners) listener(); };
  const persist = () => {
    try { storage.setItem(storageKey, JSON.stringify(state)); }
    catch { update({ ...state, error: "无法保存演示记录，请检查浏览器存储设置。" }); }
  };
  const finish = () => {
    update({ ...state, sending: false, messages: state.messages.map((message) => message.streaming ? { ...message, streaming: false } : message) });
    persist();
  };
  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    async send(request: ChatSendRequest) {
      if (state.sending || !request.content.trim()) return false;
      if (request.content.length > 2000) { update({ ...state, error: "演示输入请控制在 2000 字以内。" }); return false; }
      const sample = chatSamples[state.sampleIndex % chatSamples.length];
      const token = ++generation;
      const id = crypto.randomUUID();
      const reply = request.replyTarget;
      update({ ...state, sending: true, error: "", sampleIndex: state.sampleIndex + 1, messages: [...state.messages.slice(-100),
        { id: `${id}-user`, role: "user", content: request.content, timestamp: new Date().toISOString(), metadata: reply ? { reply_to_content: reply.content, reply_to_message_id: reply.messageId, reply_to_sender: reply.sender } : {} },
        { id, role: "assistant", content: "", streaming: true },
      ] });
      try {
        for (let length = 3; length < sample.text.length + 3; length += 3) {
          await wait();
          if (generation !== token) return true;
          update({ ...state, messages: state.messages.map((message) => message.id === id ? { ...message, content: sample.text.slice(0, length) } : message) });
        }
        update({ ...state, mood: sample.mood, thought: sample.thought });
        finish();
    } catch {
        if (generation === token) { update({ ...state, error: "演示播放中断，请重试。" }); finish(); }
      }
      return true;
    },
    cancel() { generation += 1; if (state.sending) finish(); },
    reset() { generation += 1; update({ messages: initialChatMessages(), sampleIndex: 0, sending: false, mood: "平静", thought: "外面又下雨了，希望来的人没有淋湿。", error: "" }); storage.removeItem(storageKey); },
    dispose() { generation += 1; listeners.clear(); },
  };
}
