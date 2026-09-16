/** A registered side effect: a diagnostic label plus the function that undoes it. */
export type BackgroundEffectDispose = () => void | Promise<void>;

type Effect = { label: string; dispose: BackgroundEffectDispose };

/**
 * Two-phase disposal scope for one plugin's `app.background` contribution.
 *
 * Mirrors the backend's `EffectScope` (`agent/plugin_host/effects.py`): every
 * registration is undone on teardown, one failure does not block the rest,
 * and errors are collected rather than thrown. It deliberately does **not**
 * mirror the backend's single-list LIFO `dispose_all` — see #227.
 *
 * #227 found the same bug independently in two backend plugins
 * (`scene_awareness`, `novelai`): both subscribed to events first, then
 * registered a `terminate()`-type effect after, which is the natural,
 * readable order to write. Because `dispose_all` is plain LIFO, teardown ran
 * `terminate()` *before* unsubscribing — so an event arriving mid-terminate
 * created work nothing was left to cancel.
 *
 * This scope keeps two lists instead of one: event-subscription cleanups
 * registered through `addEventEffect` (used only by `ctx.events.on`, see
 * `pluginBackgroundCtx.ts`) and everything else registered through
 * `addEffect` (used by `ctx.effect`). `disposeAll` always drains the event
 * list first — cutting off new work — before draining the effect list, so a
 * plugin's `terminate()` never races a subscription it hasn't unsubscribed
 * yet, **no matter which order `setup()` called `events.on` vs `effect` in**.
 * The correct order is the only order this type can produce; a plugin author
 * cannot get it wrong the way #227 was gotten wrong. Within each list,
 * disposal is still LIFO (most recently registered first), since there is no
 * cross-phase hazard left to resolve there.
 */
export class BackgroundEffectScope {
  private readonly eventEffects: Effect[] = [];
  private readonly effects: Effect[] = [];
  private disposed = false;

  /** Registers an event-subscription cleanup; always disposed before `addEffect` entries. */
  addEventEffect(label: string, dispose: BackgroundEffectDispose): void {
    this.ensureActive(label);
    this.eventEffects.push({ label, dispose });
  }

  /** Registers a general side effect; disposed after every `addEventEffect` entry. */
  addEffect(label: string, dispose: BackgroundEffectDispose): void {
    this.ensureActive(label);
    this.effects.push({ label, dispose });
  }

  /** Disposes every registered effect (event subscriptions first), returning collected errors. */
  async disposeAll(): Promise<Error[]> {
    this.disposed = true;
    const errors: Error[] = [];
    await drain(this.eventEffects, errors);
    await drain(this.effects, errors);
    this.disposed = true;
    return errors;
  }

  /** Rejects admission before a capability acquires listeners or other resources. */
  ensureActive(label: string): void {
    if (this.disposed) {
      throw new Error(`BackgroundEffectScope 已处置，拒绝登记: ${label}`);
    }
  }
}

async function drain(list: Effect[], errors: Error[]): Promise<void> {
  while (list.length) {
    // pop(), not shift(): most-recently-registered disposed first within a phase.
    const effect = list.pop() as Effect;
    try {
      await effect.dispose();
    } catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error));
      console.warn(`[pluginBackground] 副作用清理失败 (${effect.label}): ${normalized.message}`);
      errors.push(normalized);
    }
  }
}
