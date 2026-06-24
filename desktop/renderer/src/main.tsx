import type React from "react";
import { startTransition, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ChatSurface } from "./chat/ChatSurface";
import { DiagnosticsPanel } from "./diagnostics/DiagnosticsPanel";
import { RoleEditor } from "./roles/RoleEditor";
import { RoleSidebar } from "./roles/RoleSidebar";
import { toFileUrl } from "./shared/format";
import { cx } from "./shared/styles";
import type { EventLog, NewRoleFormState, RoleFormState, RoleRecord, SessionPayload } from "./shared/types";
import { TitleBar } from "./shell/TitleBar";
import "./styles.css";

const sidebarMinWidth = 360;
const sidebarMaxWidth = 720;
const sidebarDefaultWidth = 360;
const sidebarAutoCollapseWindowWidth = 980;

function createEmptyRoleForm(): RoleFormState {
  return {
    name: "",
    description: "",
    systemPrompt: "",
    avatarSource: "",
    illustrationSources: [],
  };
}

function createEmptyNewRoleForm(): NewRoleFormState {
  return {
    name: "",
    description: "",
    systemPrompt: "",
  };
}

function App(): React.ReactElement {
  const [health, setHealth] = useState("connecting");
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeSession, setActiveSession] = useState<SessionPayload | null>(null);
  const [draft, setDraft] = useState("");
  const [events, setEvents] = useState<EventLog[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [creating, setCreating] = useState(false);
  const [savingRole, setSavingRole] = useState(false);
  const [sending, setSending] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showRoleEditor, setShowRoleEditor] = useState(false);
  const [showNewRoleComposer, setShowNewRoleComposer] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(sidebarDefaultWidth);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const [activeIllustration, setActiveIllustration] = useState("");
  const [clearAvatar, setClearAvatar] = useState(false);
  const [clearIllustrations, setClearIllustrations] = useState(false);
  const [roleForm, setRoleForm] = useState(createEmptyRoleForm);
  const [newRoleForm, setNewRoleForm] = useState(createEmptyNewRoleForm);
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const openRoleRequestIdRef = useRef(0);

  function toggleSidebar(): void {
    if (sidebarCollapsed) {
      setSidebarWidth((current) => Math.min(sidebarMaxWidth, Math.max(sidebarMinWidth, current)));
      setSidebarCollapsed(false);
      return;
    }
    setSidebarCollapsed(true);
  }

  function beginSidebarResize(event: React.PointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    setResizingSidebar(true);

    function stopResize(): void {
      setResizingSidebar(false);
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    }

    function resize(moveEvent: PointerEvent): void {
      if (moveEvent.clientX < sidebarMinWidth) {
        setSidebarCollapsed(true);
        stopResize();
        return;
      }
      setSidebarCollapsed(false);
      setSidebarWidth(Math.min(sidebarMaxWidth, moveEvent.clientX));
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }

  function chooseIllustration(
    role: RoleRecord | null,
    session: SessionPayload | null,
    fallbackIllustration: string,
  ): string {
    if (!role) return "";
    const sessionIllustration = String(session?.metadata.active_illustration ?? "");
    if (role.illustrations_abs.includes(sessionIllustration)) {
      return sessionIllustration;
    }
    if (role.illustrations_abs.includes(fallbackIllustration)) {
      return fallbackIllustration;
    }
    return role.illustrations_abs[0] ?? "";
  }

  async function loadRolesFromBridge(): Promise<RoleRecord[] | null> {
    const rolesRes = await window.miraDesktop.invoke({
      method: "roles.list",
      payload: {},
    });
    if (rolesRes.error) {
      setError(rolesRes.error.message);
      return null;
    }
    const nextRoles = (rolesRes.payload.roles as RoleRecord[]) ?? [];
    setRoles(nextRoles);
    return nextRoles;
  }

  useEffect(() => {
    const savedRoleId = window.localStorage.getItem("miraDesktop.activeRoleId") ?? "";
    const savedIllustration = window.localStorage.getItem("miraDesktop.activeIllustration") ?? "";
    if (savedRoleId) {
      setActiveRoleId(savedRoleId);
    }
    if (savedIllustration) {
      setActiveIllustration(savedIllustration);
    }
  }, []);

  useEffect(() => {
    if (activeRoleId) {
      window.localStorage.setItem("miraDesktop.activeRoleId", activeRoleId);
    } else {
      window.localStorage.removeItem("miraDesktop.activeRoleId");
    }
  }, [activeRoleId]);

  useEffect(() => {
    if (activeIllustration) {
      window.localStorage.setItem("miraDesktop.activeIllustration", activeIllustration);
    } else {
      window.localStorage.removeItem("miraDesktop.activeIllustration");
    }
  }, [activeIllustration]);

  useEffect(() => {
    function collapseSidebarForNarrowWindow(): void {
      if (window.innerWidth < sidebarAutoCollapseWindowWidth) {
        setSidebarCollapsed(true);
      }
    }

    collapseSidebarForNarrowWindow();
    window.addEventListener("resize", collapseSidebarForNarrowWindow);
    return () => window.removeEventListener("resize", collapseSidebarForNarrowWindow);
  }, []);

  async function rememberIllustration(roleId: string, illustration: string): Promise<void> {
    await window.miraDesktop.invoke({
      method: "session.updateDisplayState",
      payload: {
        role_id: roleId,
        active_illustration: illustration,
      },
    });
  }

  /** Loads the authoritative session for a role without mutating renderer state. */
  async function fetchRoleSession(roleId: string): Promise<{
    error: string | null;
    session: SessionPayload | null;
  }> {
    try {
      const res = await window.miraDesktop.invoke({
        method: "session.openByRole",
        payload: { role_id: roleId },
      });
      if (res.error) {
        return {
          error: res.error.message,
          session: null,
        };
      }
      return {
        error: null,
        session: res.payload.session as SessionPayload,
      };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : String(error),
        session: null,
      };
    }
  }

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeSession?.messages.length, sending]);

  useEffect(() => {
    const off = window.miraDesktop.onEvent((event) => {
      startTransition(() => {
        setEvents((items) => [...items, { method: event.method, payload: event.payload }].slice(-12));
        if (!activeSession) return;
        if (String(event.payload.session_key ?? "") !== activeSession.key) return;

        if (event.method === "chat.delta") {
          const delta = String(event.payload.content_delta ?? "");
          if (!delta) return;
          setActiveSession((current) => {
            if (!current) return current;
            const messages = [...current.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "assistant" && !last.id) {
              last.content += delta;
            } else {
              messages.push({ role: "assistant", content: delta });
            }
            return { ...current, messages };
          });
          return;
        }

        if (event.method === "session.updated") {
          const session = event.payload.session as SessionPayload | undefined;
          if (!session || session.key !== activeSession.key) return;
          setActiveSession(session);
          const role = roles.find((item) => item.id === activeRoleId) ?? null;
          setActiveIllustration((current) =>
            chooseIllustration(role, session, current),
          );
          return;
        }

        if (event.method === "chat.done") {
          setSending(false);
          setNotice("Reply completed.");
        }

        if (event.method === "chat.error") {
          setSending(false);
          setError(String(event.payload.message ?? "chat failed"));
        }

        if (event.method === "bridge.exit") {
          setSending(false);
          setHealth("offline");
          setError(String(event.payload.message ?? "bridge exited"));
          setNotice("Bridge stopped. You can refresh or restart it.");
        }
      });
    });
    return off;
  }, [activeSession]);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      const bridgeStatus = await window.miraDesktop.bridgeStatus();
      if (cancelled) return;
      if (!bridgeStatus.running && bridgeStatus.lastError) {
        setHealth("offline");
        setError(bridgeStatus.lastError);
        return;
      }
      const healthRes = await window.miraDesktop.invoke({
        method: "health",
        payload: {},
      });
      if (cancelled) return;
      if (healthRes.error) {
        setHealth("offline");
        setError(healthRes.error.message);
        return;
      }
      setHealth("online");
      setError("");

      const nextRoles = await loadRolesFromBridge();
      if (cancelled) return;
      if (!nextRoles) {
        return;
      }
      const preferredRoleId =
        nextRoles.find((item) => item.id === activeRoleId)?.id ??
        nextRoles.find((item) => item.id === window.localStorage.getItem("miraDesktop.activeRoleId"))?.id ??
        nextRoles[0]?.id;
      if (preferredRoleId) {
        const preferredRole = nextRoles.find((item) => item.id === preferredRoleId) ?? null;
        void openRole(preferredRoleId, preferredRole);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshSession(): Promise<void> {
    if (!activeRoleId) return;
    await openRole(activeRoleId);
    setNotice("Session refreshed.");
  }

  async function refreshBridge(): Promise<void> {
    setError("");
    setHealth("connecting");
    const res = await window.miraDesktop.invoke({
      method: "health",
      payload: {},
    });
    if (res.error) {
      setHealth("offline");
      setError(res.error.message);
      return;
    }
    setHealth("online");
    const nextRoles = await loadRolesFromBridge();
    if (!nextRoles) {
      return;
    }
    if (activeRoleId) {
      const activeRole = nextRoles.find((item) => item.id === activeRoleId) ?? null;
      if (activeRole) {
        await openRole(activeRole.id, activeRole);
      } else if (nextRoles[0]) {
        await openRole(nextRoles[0].id, nextRoles[0]);
      } else {
        setActiveRoleId("");
        setActiveSession(null);
        setActiveIllustration("");
      }
    } else if (nextRoles[0]) {
      await openRole(nextRoles[0].id, nextRoles[0]);
    }
    setNotice("Bridge refreshed.");
  }

  async function restartBridge(): Promise<void> {
    setError("");
    setHealth("connecting");
    const result = await window.miraDesktop.restartBridge();
    if (!result.ok) {
      setHealth("offline");
      setError(result.lastError || "bridge restart failed");
      return;
    }
    setNotice("Bridge restarted.");
    await refreshBridge();
  }

  async function openRole(roleId: string, roleOverride: RoleRecord | null = null): Promise<void> {
    const requestId = openRoleRequestIdRef.current + 1;
    openRoleRequestIdRef.current = requestId;
    const { error: sessionError, session } = await fetchRoleSession(roleId);
    if (openRoleRequestIdRef.current !== requestId) {
      return;
    }
    if (!session) {
      setError(sessionError ?? "failed to open role session");
      return;
    }
    setActiveRoleId(roleId);
    setActiveSession(session);
    setError("");
    const role = roleOverride ?? roles.find((item) => item.id === roleId) ?? null;
    if (role) {
      setRoleForm({
        name: role.name,
        description: role.description,
        systemPrompt: role.system_prompt,
        avatarSource: "",
        illustrationSources: [],
      });
      setClearAvatar(false);
      setClearIllustrations(false);
      setShowRoleEditor(false);
      const savedIllustration =
        window.localStorage.getItem("miraDesktop.activeIllustration") ?? "";
      setActiveIllustration(
        chooseIllustration(
          role,
          session,
          savedIllustration,
        ),
      );
    } else {
      setActiveIllustration("");
    }
  }

  async function sendMessage(): Promise<void> {
    const content = draft.trim();
    const roleId = activeRoleId;
    const previousSession = activeSession;
    const sessionKey = activeSession?.key ?? "";
    if (!content || !roleId || !sessionKey) return;
    setSending(true);
    setError("");
    setDraft("");
    setActiveSession((current) =>
      current?.key === sessionKey
        ? {
            ...current,
            messages: [...current.messages, { role: "user", content }],
          }
        : current,
    );
    try {
      const res = await window.miraDesktop.invoke({
        method: "chat.send",
        payload: { role_id: roleId, content },
      });
      if (res.error) {
        const { session: recoveredSession } = await fetchRoleSession(roleId);
        if (recoveredSession) {
          setActiveSession((current) =>
            current?.key === sessionKey ? recoveredSession : current,
          );
        } else if (previousSession) {
          setActiveSession((current) =>
            current?.key === sessionKey ? previousSession : current,
          );
        }
        setError(res.error.message);
        return;
      }
      const nextSession = res.payload.session as SessionPayload;
      setActiveSession((current) =>
        current?.key === nextSession.key ? nextSession : current,
      );
    } catch (error) {
      const { session: recoveredSession } = await fetchRoleSession(roleId);
      if (recoveredSession) {
        setActiveSession((current) =>
          current?.key === sessionKey ? recoveredSession : current,
        );
      } else if (previousSession) {
        setActiveSession((current) =>
          current?.key === sessionKey ? previousSession : current,
        );
      }
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setSending(false);
    }
  }

  async function cancelMessage(): Promise<void> {
    if (!activeRoleId) return;
    const res = await window.miraDesktop.invoke({
      method: "chat.cancel",
      payload: { role_id: activeRoleId },
    });
    if (res.error) {
      setError(res.error.message);
      return;
    }
    setSending(false);
    setNotice(String(res.payload.message ?? "Cancelled."));
  }

  async function createRole(): Promise<void> {
    const name = newRoleForm.name.trim();
    const systemPrompt = newRoleForm.systemPrompt.trim();
    if (!name || !systemPrompt) {
      setError("Role name and system prompt are required.");
      return;
    }
    setCreating(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.create",
      payload: {
        name,
        description: newRoleForm.description,
        system_prompt: systemPrompt,
      },
    });
    setCreating(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const role = res.payload.role as RoleRecord;
    setNewRoleForm(createEmptyNewRoleForm());
    const nextRoles = await loadRolesFromBridge();
    setNotice("Role created.");
    await openRole(role.id, nextRoles?.find((item) => item.id === role.id) ?? role);
  }

  async function saveRole(): Promise<void> {
    if (!activeRoleId) return;
    setSavingRole(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: activeRoleId,
        name: roleForm.name,
        description: roleForm.description,
        system_prompt: roleForm.systemPrompt,
        avatar_source: roleForm.avatarSource || undefined,
        illustration_sources: roleForm.illustrationSources,
        clear_avatar: clearAvatar,
        clear_illustrations: clearIllustrations,
      },
    });
    setSavingRole(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const nextRoles = await loadRolesFromBridge();
    setRoleForm((current) => ({ ...current, avatarSource: "", illustrationSources: [] }));
    setClearAvatar(false);
    setClearIllustrations(false);
    setNotice("Role saved.");
    await openRole(updated.id, nextRoles?.find((item) => item.id === updated.id) ?? updated);
  }

  async function deleteRole(): Promise<void> {
    if (!activeRoleId) return;
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.delete",
      payload: { role_id: activeRoleId },
    });
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const nextRoles = (await loadRolesFromBridge()) ?? [];
    setActiveRoleId("");
    setActiveSession(null);
    setActiveIllustration("");
    setNotice("Role deleted.");
    if (nextRoles[0]) {
      await openRole(nextRoles[0].id, nextRoles[0]);
    }
  }

  async function pickAvatar(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: false });
    if (!files[0]) return;
    setClearAvatar(false);
    setRoleForm((current) => ({ ...current, avatarSource: files[0] }));
  }

  async function pickIllustrations(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: true });
    if (!files.length) return;
    setClearIllustrations(false);
    setRoleForm((current) => ({ ...current, illustrationSources: files }));
  }

  function clearAvatarSelection(): void {
    setClearAvatar(true);
    setRoleForm((current) => ({ ...current, avatarSource: "" }));
  }

  function clearIllustrationsSelection(): void {
    setClearIllustrations(true);
    setRoleForm((current) => ({ ...current, illustrationSources: [] }));
    setActiveIllustration("");
  }

  const activeRole = roles.find((role) => role.id === activeRoleId) ?? null;
  const bridgeReady = health === "online";
  const roleFormDirty = Boolean(
    activeRole
      && (
        roleForm.name !== activeRole.name
        || roleForm.description !== activeRole.description
        || roleForm.systemPrompt !== activeRole.system_prompt
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || clearAvatar
        || clearIllustrations
      )
  );

  const previewAvatar = clearAvatar
    ? null
    : (roleForm.avatarSource || activeRole?.avatar_abs || null);

  const previewIllustrations = clearIllustrations
    ? []
    : (roleForm.illustrationSources.length
        ? roleForm.illustrationSources
        : (activeRole?.illustrations_abs ?? []));
  const visibleIllustration = activeIllustration || previewIllustrations[0] || "";
  const visibleIllustrationUrl = visibleIllustration ? toFileUrl(visibleIllustration) : "";

  useEffect(() => {
    if (previewIllustrations.length === 0) {
      if (activeIllustration) {
        setActiveIllustration("");
      }
      return;
    }
    if (!previewIllustrations.includes(activeIllustration)) {
      setActiveIllustration(previewIllustrations[0] ?? "");
    }
  }, [previewIllustrations, activeIllustration]);

  function resetRoleForm(): void {
    if (!activeRole) return;
    setRoleForm({
      name: activeRole.name,
      description: activeRole.description,
      systemPrompt: activeRole.system_prompt,
      avatarSource: "",
      illustrationSources: [],
    });
    setClearAvatar(false);
    setClearIllustrations(false);
    setNotice("Role form reset.");
  }

  return (
    <div className="app-frame grid h-screen grid-rows-app overflow-hidden bg-[var(--app-bg)]">
      <TitleBar sidebarCollapsed={sidebarCollapsed} onToggleSidebar={toggleSidebar} />
      <div
        className={cx(
          "desktop-shell grid min-h-0 overflow-hidden bg-transparent",
          resizingSidebar && "sidebar-resizing cursor-col-resize select-none",
        )}
        style={{
          gridTemplateColumns: sidebarCollapsed ? "minmax(0, 1fr)" : `${sidebarWidth}px minmax(0, 1fr)`,
        }}
      >
        <RoleSidebar
          roles={roles}
          activeRoleId={activeRoleId}
          bridgeReady={bridgeReady}
          collapsed={sidebarCollapsed}
          creating={creating}
          showNewRoleComposer={showNewRoleComposer}
          newRoleForm={newRoleForm}
          onToggleNewRoleComposer={() => setShowNewRoleComposer((value) => !value)}
          onToggleRoleEditor={() => setShowRoleEditor((value) => !value)}
          onUpdateNewRoleForm={setNewRoleForm}
          onCreateRole={() => void createRole()}
          onOpenRole={(roleId) => void openRole(roleId)}
          onBeginResize={beginSidebarResize}
        />
        <main className="chat-pane relative grid min-h-0 grid-cols-[minmax(0,1fr)] overflow-hidden rounded-l-[16px] border-l border-t border-[#ded7cb] bg-white">
          <ChatSurface
            activeRole={activeRole}
            activeRoleId={activeRoleId}
            activeSession={activeSession}
            bridgeReady={bridgeReady}
            conversationEndRef={conversationEndRef}
            draft={draft}
            notice={notice}
            sending={sending}
            visibleIllustrationUrl={visibleIllustrationUrl}
            onCancelMessage={() => void cancelMessage()}
            onSendMessage={() => void sendMessage()}
            onUpdateDraft={setDraft}
          />
          {showRoleEditor ? (
            <RoleEditor
              activeRole={activeRole}
              activeRoleId={activeRoleId}
              activeIllustration={activeIllustration}
              bridgeReady={bridgeReady}
              clearAvatar={clearAvatar}
              clearIllustrations={clearIllustrations}
              previewAvatar={previewAvatar}
              previewIllustrations={previewIllustrations}
              roleForm={roleForm}
              roleFormDirty={roleFormDirty}
              savingRole={savingRole}
              onUpdateRoleForm={setRoleForm}
              onSetActiveIllustration={setActiveIllustration}
              onRememberIllustration={(roleId, illustration) => void rememberIllustration(roleId, illustration)}
              onPickAvatar={() => void pickAvatar()}
              onPickIllustrations={() => void pickIllustrations()}
              onClearAvatar={clearAvatarSelection}
              onClearIllustrations={clearIllustrationsSelection}
              onDeleteRole={() => void deleteRole()}
              onResetRoleForm={resetRoleForm}
              onSaveRole={() => void saveRole()}
            />
          ) : null}
          <DiagnosticsPanel error={error} events={events} expanded={showDiagnostics} />
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
