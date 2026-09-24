type Listener = () => void;

// A one-way "open the model menu" signal. The request comes from places that
// do not render the composer (an error toast's action raised from the send
// flow), and the menu's open state is owned by `ChatModelMenu` itself, so a
// tiny subscribe/notify channel is narrower than lifting that state up
// through the app frame, chat surface and composer.
const listeners = new Set<Listener>();

/** Asks the mounted chat model menu, if any, to open on its dialogue-model list. */
export function requestChatModelMenu(): void {
  for (const listener of listeners) listener();
}

/** Subscribes a mounted model menu to open requests; returns the unsubscribe function. */
export function subscribeChatModelMenuRequests(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
