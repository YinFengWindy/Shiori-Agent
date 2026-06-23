import React, { startTransition, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import type { WindowControlAction } from "../../src/shared";
import "./styles.css";

type RoleRecord = {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  avatar: string | null;
  avatar_abs: string | null;
  illustrations: string[];
  illustrations_abs: string[];
  created_at: string;
  updated_at: string;
};

type SessionMessage = {
  id?: string;
  role: string;
  content: string;
  timestamp?: string;
  reasoning_content?: string | null;
};

type SessionPayload = {
  key: string;
  created_at: string;
  updated_at: string;
  last_consolidated: number;
  metadata: Record<string, unknown>;
  messages: SessionMessage[];
};

type EventLog = {
  method: string;
  payload: Record<string, unknown>;
};

const menuItems = ["文件", "编辑", "视图", "帮助"] as const;

function TitleBar() {
  function controlWindow(action: WindowControlAction) {
    void window.miraDesktop.windowControl(action);
  }

  return (
    <header className="titlebar">
      <div className="titlebar-left">
        <button className="titlebar-icon titlebar-sidebar" type="button" aria-label="Sidebar">
          <span />
        </button>
        <button className="titlebar-icon titlebar-back" type="button" aria-label="Back" disabled>
          <span />
        </button>
        <button className="titlebar-icon titlebar-forward" type="button" aria-label="Forward" disabled>
          <span />
        </button>
        <nav className="titlebar-menu" aria-label="Application menu">
          {menuItems.map((item) => (
            <button key={item} className="titlebar-menu-item" type="button">
              {item}
            </button>
          ))}
        </nav>
      </div>
      <div className="window-controls">
        <button className="window-control" type="button" aria-label="Minimize" onClick={() => controlWindow("minimize")}>
          <span className="window-minimize" />
        </button>
        <button className="window-control" type="button" aria-label="Maximize" onClick={() => controlWindow("toggleMaximize")}>
          <span className="window-maximize" />
        </button>
        <button className="window-control window-control-close" type="button" aria-label="Close" onClick={() => controlWindow("close")}>
          <span className="window-close" />
        </button>
      </div>
    </header>
  );
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
  const [activeIllustration, setActiveIllustration] = useState("");
  const [clearAvatar, setClearAvatar] = useState(false);
  const [clearIllustrations, setClearIllustrations] = useState(false);
  const [roleForm, setRoleForm] = useState({
    name: "",
    description: "",
    systemPrompt: "",
    avatarSource: "",
    illustrationSources: [] as string[],
  });
  const [newRoleForm, setNewRoleForm] = useState({
    name: "",
    description: "",
    systemPrompt: "",
  });
  const conversationEndRef = useRef<HTMLDivElement | null>(null);

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

  async function rememberIllustration(roleId: string, illustration: string): Promise<void> {
    await window.miraDesktop.invoke({
      method: "session.updateDisplayState",
      payload: {
        role_id: roleId,
        active_illustration: illustration,
      },
    });
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
    setActiveRoleId(roleId);
    const res = await window.miraDesktop.invoke({
      method: "session.openByRole",
      payload: { role_id: roleId },
    });
    if (res.error) {
      setError(res.error.message);
      return;
    }
    setActiveSession(res.payload.session as SessionPayload);
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
          res.payload.session as SessionPayload,
          savedIllustration,
        ),
      );
    } else {
      setActiveIllustration("");
    }
  }

  async function sendMessage(): Promise<void> {
    const content = draft.trim();
    if (!content || !activeRoleId) return;
    setSending(true);
    setError("");
    setDraft("");
    setActiveSession((current) =>
      current
        ? {
            ...current,
            messages: [...current.messages, { role: "user", content }],
          }
        : current,
    );
    const res = await window.miraDesktop.invoke({
      method: "chat.send",
      payload: { role_id: activeRoleId, content },
    });
    if (res.error) {
      setSending(false);
      setError(res.error.message);
      return;
    }
    setActiveSession(res.payload.session as SessionPayload);
    setError("");
    setSending(false);
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
    setNewRoleForm({ name: "", description: "", systemPrompt: "" });
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

  function formatTimestamp(value?: string): string {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString();
  }

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
    <div className="app-frame">
      <TitleBar />
      <div className="desktop-shell">
        <aside className="role-pane">
          <div className="sidebar-top">
            <button className="sidebar-entry" type="button" onClick={() => setShowNewRoleComposer((value) => !value)}>
              <span className="sidebar-entry-icon sidebar-entry-new" aria-hidden="true" />
              <span>新对话</span>
            </button>
            <button className="sidebar-entry" type="button">
              <span className="sidebar-entry-icon sidebar-entry-search" aria-hidden="true" />
              <span>搜索</span>
            </button>
            <button className="sidebar-entry" type="button" onClick={() => setShowRoleEditor((value) => !value)} disabled={!activeRoleId}>
              <span className="sidebar-entry-icon sidebar-entry-role" aria-hidden="true" />
              <span>角色</span>
            </button>
            {showNewRoleComposer ? (
              <div className="create-form">
                <input
                  data-testid="new-role-name"
                  value={newRoleForm.name}
                  onChange={(event) => setNewRoleForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="New role name"
                />
                <input
                  data-testid="new-role-description"
                  value={newRoleForm.description}
                  onChange={(event) => setNewRoleForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="Short description"
                />
                <textarea
                  data-testid="new-role-prompt"
                  className="compact-prompt"
                  value={newRoleForm.systemPrompt}
                  onChange={(event) => setNewRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
                  placeholder="Role system prompt"
                />
                <button data-testid="create-role-button" className="primary-btn" type="button" onClick={() => void createRole()} disabled={creating || !bridgeReady}>
                  {creating ? "Creating..." : "Create Role"}
                </button>
              </div>
            ) : null}
          </div>
          <div className="role-list" data-testid="role-list">
            {roles.length ? roles.map((role) => (
              <button
                key={role.id}
                data-testid={`role-card-${role.id}`}
                className={`role-card${role.id === activeRoleId ? " active" : ""}`}
                type="button"
                disabled={!bridgeReady}
                onClick={() => void openRole(role.id)}
              >
                {role.avatar_abs ? (
                  <img
                    className="role-avatar"
                    src={`file:///${role.avatar_abs.replace(/\\/g, "/")}`}
                    alt={`${role.name} avatar`}
                  />
                ) : (
                  <span className="role-avatar role-avatar-fallback">{role.name.slice(0, 1).toUpperCase()}</span>
                )}
                <span className="role-name">{role.name}</span>
              </button>
            )) : (
              <div className="empty-card">No roles yet.</div>
            )}
          </div>
        </aside>
        <main className="chat-pane">
          <section className="chat-surface">
            <header className="chat-header" data-testid="session-hero">
              {activeRole?.avatar_abs ? (
                <img
                  className="chat-header-avatar"
                  src={`file:///${activeRole.avatar_abs.replace(/\\/g, "/")}`}
                  alt={`${activeRole.name} avatar`}
                />
              ) : (
                <span className="chat-header-avatar chat-header-avatar-fallback">
                  {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "M"}
                </span>
              )}
              <div className="chat-header-title">{activeRole ? activeRole.name : "Select a role"}</div>
              {visibleIllustration ? (
                <img
                  className="hero-illustration chat-header-illustration"
                  src={`file:///${visibleIllustration.replace(/\\/g, "/")}`}
                  alt="role illustration"
                />
              ) : null}
            </header>
            <section className="conversation-panel">
              {notice ? <div className="notice-chip">{notice}</div> : null}
              <div className="conversation-list">
                {activeSession?.messages.length ? activeSession.messages.map((message, index) => (
                  <article key={`${message.id ?? message.role}-${index}`} className={`bubble bubble-${message.role}`}>
                    <div className="bubble-role">{message.role}</div>
                    <div className="bubble-content">{message.content}</div>
                    {message.timestamp ? <div className="bubble-time">{formatTimestamp(message.timestamp)}</div> : null}
                  </article>
                )) : (
                  <div className="empty-card">No messages yet. Send the first message to this role.</div>
                )}
                <div ref={conversationEndRef} />
              </div>
              <div className="composer">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Type a message for this role..."
                />
                <div className="composer-actions">
                  <button className="composer-tool-btn" type="button" aria-label="Add attachment">
                    <span />
                  </button>
                  <div className="composer-spacer" />
                  <button className="ghost-btn composer-cancel" type="button" onClick={() => void cancelMessage()} disabled={!activeRoleId || !sending || !bridgeReady}>
                    Cancel
                  </button>
                  <button className="send-btn" type="button" aria-label="Send message" onClick={() => void sendMessage()} disabled={!activeRoleId || !draft.trim() || sending || !bridgeReady}>
                    <span />
                  </button>
                </div>
              </div>
            </section>
          </section>
        {showRoleEditor ? (
          <section className="role-editor">
            <div className="panel-head">
              <h3>Role Editor</h3>
              {roleFormDirty ? <span className="dirty-chip">Unsaved changes</span> : null}
            </div>
            {activeRole ? (
              <div className="editor-form">
                <label>
                  <span>Name</span>
                  <input
                    data-testid="edit-role-name"
                    value={roleForm.name}
                    onChange={(event) => setRoleForm((current) => ({ ...current, name: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Description</span>
                  <input
                    data-testid="edit-role-description"
                    value={roleForm.description}
                    onChange={(event) => setRoleForm((current) => ({ ...current, description: event.target.value }))}
                  />
                </label>
                <label>
                  <span>System Prompt</span>
                  <textarea
                    data-testid="edit-role-prompt"
                    className="role-prompt"
                    value={roleForm.systemPrompt}
                    onChange={(event) => setRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
                  />
                </label>
                <div className="asset-actions">
                  <button data-testid="pick-avatar-button" className="ghost-btn" type="button" onClick={() => void pickAvatar()} disabled={!bridgeReady}>
                    Pick Avatar
                  </button>
                  <button data-testid="pick-illustrations-button" className="ghost-btn" type="button" onClick={() => void pickIllustrations()} disabled={!bridgeReady}>
                    Pick Illustrations
                  </button>
                  <button data-testid="clear-avatar-button" className="ghost-btn" type="button" onClick={clearAvatarSelection} disabled={!bridgeReady}>
                    Clear Avatar
                  </button>
                  <button data-testid="clear-illustrations-button" className="ghost-btn" type="button" onClick={clearIllustrationsSelection} disabled={!bridgeReady}>
                    Clear Illustrations
                  </button>
                  <button className="ghost-btn danger" type="button" onClick={() => void deleteRole()} disabled={!bridgeReady}>
                    Delete Role
                  </button>
                </div>
                {previewAvatar ? (
                  <img
                    className="editor-avatar"
                    src={`file:///${previewAvatar.replace(/\\/g, "/")}`}
                    alt={`${activeRole.name} avatar`}
                  />
                ) : null}
                {previewIllustrations.length ? (
                  <div className="illustration-strip">
                    {previewIllustrations.map((path) => (
                      <button
                        key={path}
                        type="button"
                        className={`illustration-thumb${path === activeIllustration ? " active" : ""}`}
                        onClick={() => {
                          setActiveIllustration(path);
                          if (activeRoleId) {
                            void rememberIllustration(activeRoleId, path);
                          }
                        }}
                      >
                        <img src={`file:///${path.replace(/\\/g, "/")}`} alt="illustration thumb" />
                      </button>
                    ))}
                  </div>
                ) : null}
                {roleForm.avatarSource ? <div className="asset-preview">Avatar: {roleForm.avatarSource}</div> : null}
                {roleForm.illustrationSources.length ? (
                  <div className="asset-preview">
                    Illustrations:
                    <ul>
                      {roleForm.illustrationSources.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}
                <div className="editor-actions">
                  <button className="ghost-btn" type="button" onClick={resetRoleForm} disabled={!roleFormDirty}>
                    Reset
                  </button>
                  <button data-testid="save-role-button" className="primary-btn" type="button" onClick={() => void saveRole()} disabled={savingRole || !activeRoleId || !roleFormDirty || !bridgeReady}>
                    {savingRole ? "Saving..." : "Save Role"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-card">Select a role to edit its prompt and local artwork.</div>
            )}
          </section>
        ) : null}
        {showDiagnostics ? (
          <section className="event-panel">
            <div className="panel-head">
              <h3>Bridge Events</h3>
              {error ? <span className="error-chip">{error}</span> : null}
            </div>
            <div className="event-list">
              {events.length ? events.map((event, index) => (
                <article key={`${event.method}-${index}`} className="event-row">
                  <div className="event-method">{event.method}</div>
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                </article>
              )) : (
                <div className="empty-card">No events yet.</div>
              )}
            </div>
          </section>
        ) : error ? (
          <section className="event-panel collapsed-diagnostics">
            <div className="panel-head">
              <h3>Diagnostics</h3>
              <span className="error-chip">{error}</span>
            </div>
          </section>
        ) : null}
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
