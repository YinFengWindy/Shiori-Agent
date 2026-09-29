/*
 * 吟风 for plugin UIs (runtime API 2.4.0). A plugin opts in per call with
 * `persona`: `true` / `"generic"` for the surface's generic line, or a scene
 * key for the host's line for that scene. The words are always the host's —
 * a plugin picks a scene, never a sentence. The 看板娘 switch (设置 › 外观)
 * still wins: off, everything renders plain.
 */

/** Visual and semantic weight of one transient feedback message. */
export type FeedbackTone = "success" | "info" | "warning" | "error";

/** One optional follow-up the user can take straight from the message. */
export type FeedbackAction = {
  label: string;
  onSelect: () => void;
};

/**
 * A scene a plugin may name when it asks 吟风 to front something. The host
 * owns one line per scene (`personaSceneLines`, checked against this union).
 * `generic` is not a scene: `persona: true` / `"generic"` means the
 * surface's own generic line.
 */
export type PersonaSceneKey =
  /** A service the plugin needs has not been set up yet. */
  | "not_configured"
  /** The credentials were refused. */
  | "unauthorized"
  /** The account ran out of quota / credits. */
  | "quota"
  /** The remote service could not be reached. */
  | "network"
  /** The remote service answered with an error of its own. */
  | "upstream"
  /** Confirming something that cannot be undone (usually a deletion). */
  | "destructive"
  /** Confirming that unsaved edits are thrown away. */
  | "discard"
  /** Any other confirmation. */
  | "confirm";

/** How a plugin asks for 吟风: not at all (`false`, the default), generically, or by scene. */
export type PluginPersona = boolean | "generic" | PersonaSceneKey;

/** Options of a plugin toast. */
export type PluginFeedbackOptions = {
  /** Technical cause folded behind 「详情」. */
  detail?: string;
  /** One follow-up the user can take from the toast. */
  action?: FeedbackAction;
  /**
   * Let 吟风 front this toast. `true` / `"generic"` follow the host's rule
   * for the tone (a line for error / warning, only her face for success /
   * info); a scene key uses that scene's line. Default false.
   */
  persona?: PluginPersona;
  /**
   * With `persona`: show only her face (with the persona's expression), not
   * her line — for when the plugin already shows the same line on screen
   * (e.g. a failure card fronted by the same scene). Default false.
   */
  personaQuiet?: boolean;
};

/** A plugin's reporter into the host toast queue (`host.feedback`), one method per tone. */
export type PluginHostFeedback = Record<FeedbackTone, (message: string, options?: PluginFeedbackOptions) => void>;
