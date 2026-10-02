/** Resolve the role carried by the host's canonical role-session key. */
export function roleIdFromSessionKey(key: string): string | null {
  return key.startsWith("role:") && key.length > 5 ? key.slice(5) : null;
}
