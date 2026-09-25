import { createFeedbackReporter } from "../feedback/feedbackStore";

/**
 * The host's feedback reporter: the same store and toaster as `feedback`,
 * but every error defaults to 吟风's generic persona, so she fronts it
 * whenever the 看板娘 is on (a call can pass a more specific persona).
 * Plugin UIs keep the plain `feedback`: their messages are theirs, and a
 * plugin must not lean on the host mascot.
 */
export const mascotFeedback = createFeedbackReporter({ error: { persona: "generic" } });
