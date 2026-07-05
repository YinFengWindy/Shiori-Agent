import type React from "react";
import { cx, ghostButtonClass, inputClass, textareaClass } from "../shared/styles";
import type {
  RoleRecord,
  SettingsChannelGroup,
  SettingsChannelRoleBinding,
  SettingsPeerAgent,
  SettingsQQBotGroup,
} from "../shared/types";

type GroupEditorProps = {
  group: SettingsChannelGroup;
  onChange: (next: SettingsChannelGroup) => void;
  onRemove: () => void;
};

type QQBotGroupEditorProps = {
  group: SettingsQQBotGroup;
  onChange: (next: SettingsQQBotGroup) => void;
  onRemove: () => void;
};

type ChannelRoleBindingEditorProps = {
  channel: SettingsChannelRoleBinding["channel"];
  binding: SettingsChannelRoleBinding;
  roles: RoleRecord[];
  label: string;
  placeholder: string;
  hint: string;
  onChange: (next: SettingsChannelRoleBinding) => void;
  onRemove: () => void;
};

type PeerAgentEditorProps = {
  agent: SettingsPeerAgent;
  parseNumber: (value: string, fallback: number) => number;
  parseLauncher: (value: string) => string[];
  formatLauncher: (values: string[]) => string;
  onChange: (next: SettingsPeerAgent) => void;
  onRemove: () => void;
};

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinLines(values: string[]): string {
  return values.join("\n");
}

function EditorShell({
  title,
  children,
  onRemove,
}: {
  title: string;
  children: React.ReactNode;
  onRemove: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-[18px] border border-[#E5EAF0] bg-[#FBFCFE] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-[#1F2430]">{title}</div>
        <button className={cx("rounded-md px-3 py-2 text-sm text-[#A14D32]", ghostButtonClass)} type="button" onClick={onRemove}>
          删除
        </button>
      </div>
      {children}
    </div>
  );
}

/** Edits a single QQ group rule entry shown inside the channel settings cards. */
export function GroupEditor({ group, onChange, onRemove }: GroupEditorProps) {
  return (
    <EditorShell title="QQ 群组规则" onRemove={onRemove}>
      <input className={cx(inputClass, "bg-white")} value={group.groupId} onChange={(event) => onChange({ ...group, groupId: event.target.value })} placeholder="群组 ID" />
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={joinLines(group.allowFrom)} onChange={(event) => onChange({ ...group, allowFrom: splitLines(event.target.value) })} placeholder="每行一个允许来源" />
      <label className="flex items-center gap-3 rounded-md border border-[#E5EAF0] bg-white px-4 py-3 text-sm text-[#4A4F57]">
        <input type="checkbox" checked={group.requireAt} onChange={(event) => onChange({ ...group, requireAt: event.target.checked })} />
        <span>仅在被 @ 时响应</span>
      </label>
    </EditorShell>
  );
}

/** Edits a single QQBot group rule entry shown inside the channel settings cards. */
export function QQBotGroupEditor({ group, onChange, onRemove }: QQBotGroupEditorProps) {
  return (
    <EditorShell title="QQBot 群组规则" onRemove={onRemove}>
      <input className={cx(inputClass, "bg-white")} value={group.groupOpenid} onChange={(event) => onChange({ ...group, groupOpenid: event.target.value })} placeholder="群组 OpenID" />
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={joinLines(group.allowFrom)} onChange={(event) => onChange({ ...group, allowFrom: splitLines(event.target.value) })} placeholder="每行一个允许来源" />
      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex items-center gap-3 rounded-md border border-[#E5EAF0] bg-white px-4 py-3 text-sm text-[#4A4F57]">
          <input type="checkbox" checked={group.requireAt} onChange={(event) => onChange({ ...group, requireAt: event.target.checked })} />
          <span>仅在被 @ 时响应</span>
        </label>
        <label className="flex items-center gap-3 rounded-md border border-[#E5EAF0] bg-white px-4 py-3 text-sm text-[#4A4F57]">
          <input type="checkbox" checked={group.allowProactive} onChange={(event) => onChange({ ...group, allowProactive: event.target.checked })} />
          <span>允许主动消息</span>
        </label>
      </div>
    </EditorShell>
  );
}

/** Edits a single transport-role binding entry used by the settings page. */
export function ChannelRoleBindingEditor({
  channel,
  binding,
  roles,
  label,
  placeholder,
  hint,
  onChange,
  onRemove,
}: ChannelRoleBindingEditorProps) {
  return (
    <EditorShell title="渠道角色绑定" onRemove={onRemove}>
      <div className="grid gap-1">
        <div className="text-xs font-medium text-[#4A4F57]">{label}</div>
        <div className="text-[12px] leading-5 text-[#7B7F87]">{hint}</div>
      </div>
      <input className={cx(inputClass, "bg-white")} value={binding.chatId} onChange={(event) => onChange({ ...binding, channel, chatId: event.target.value })} placeholder={placeholder} />
      <select className={cx(inputClass, "bg-white")} value={binding.roleId} onChange={(event) => onChange({ ...binding, channel, roleId: event.target.value })}>
        <option value="">选择角色</option>
        {roles.map((role) => (
          <option key={role.id} value={role.id}>{role.name}</option>
        ))}
      </select>
    </EditorShell>
  );
}

/** Edits a single peer agent registration row. */
export function PeerAgentEditor({
  agent,
  parseNumber,
  parseLauncher,
  formatLauncher,
  onChange,
  onRemove,
}: PeerAgentEditorProps) {
  return (
    <EditorShell title="Peer Agent" onRemove={onRemove}>
      <div className="grid gap-3 md:grid-cols-2">
        <input className={cx(inputClass, "bg-white")} value={agent.name} onChange={(event) => onChange({ ...agent, name: event.target.value })} placeholder="名称" />
        <input className={cx(inputClass, "bg-white")} value={agent.baseUrl} onChange={(event) => onChange({ ...agent, baseUrl: event.target.value })} placeholder="基础地址" />
        <input className={cx(inputClass, "bg-white")} value={agent.cwd} onChange={(event) => onChange({ ...agent, cwd: event.target.value })} placeholder="工作目录" />
        <input className={cx(inputClass, "bg-white")} value={agent.healthPath} onChange={(event) => onChange({ ...agent, healthPath: event.target.value })} placeholder="健康检查路径" />
        <input className={cx(inputClass, "bg-white")} value={String(agent.startupTimeoutSeconds)} onChange={(event) => onChange({ ...agent, startupTimeoutSeconds: parseNumber(event.target.value, agent.startupTimeoutSeconds) })} placeholder="启动超时秒数" />
        <input className={cx(inputClass, "bg-white")} value={String(agent.shutdownTimeoutSeconds)} onChange={(event) => onChange({ ...agent, shutdownTimeoutSeconds: parseNumber(event.target.value, agent.shutdownTimeoutSeconds) })} placeholder="关闭超时秒数" />
      </div>
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={agent.description} onChange={(event) => onChange({ ...agent, description: event.target.value })} placeholder="描述" />
      <textarea className={cx(textareaClass, "min-h-24 bg-white font-mono text-[12px]")} value={formatLauncher(agent.launcher)} onChange={(event) => onChange({ ...agent, launcher: parseLauncher(event.target.value) })} placeholder="每行一个启动命令片段" />
    </EditorShell>
  );
}
