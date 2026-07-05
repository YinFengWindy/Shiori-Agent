import type React from "react";
import { useState } from "react";
import { cx, ghostButtonClass, inputClass } from "../shared/styles";
import type { SettingsSectionStatus, SettingsStatusTone } from "./settingsMetadata";

type SettingsStatusBadgeProps = {
  label: string;
  tone?: SettingsStatusTone;
};

type SettingsSectionIntroProps = {
  title: string;
  summary: string;
  statuses: SettingsSectionStatus[];
};

type SettingsCardProps = {
  title: string;
  summary: string;
  children: React.ReactNode;
};

type SettingsFieldProps = {
  label: string;
  description: string;
  badge?: SettingsStatusBadgeProps | null;
  children: React.ReactNode;
  hint?: React.ReactNode;
};

type SettingsFieldHintProps = {
  usage: string;
  blank?: string;
  effect?: string;
  recommendation?: string;
  configPath?: string;
};

type SettingsExpandableBlockProps = {
  label?: string;
  children: React.ReactNode;
  defaultExpanded?: boolean;
};

type SecretInputProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

function toneClass(tone: SettingsStatusTone = "neutral"): string {
  switch (tone) {
    case "success":
      return "border-[rgba(57,138,89,0.18)] bg-[#EDF7F0] text-[#2E6D46]";
    case "warning":
      return "border-[rgba(166,117,37,0.18)] bg-[#FBF4E8] text-[#8A5A18]";
    default:
      return "border-[#E2E6EC] bg-[#F6F8FB] text-[#5A6370]";
  }
}

/** Renders a compact settings state badge such as 已配置 or 使用默认. */
export function SettingsStatusBadge({ label, tone = "neutral" }: SettingsStatusBadgeProps) {
  return (
    <span className={cx("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium leading-none", toneClass(tone))}>
      {label}
    </span>
  );
}

/** Renders the subsection title, summary, and current state badges. */
export function SettingsSectionIntro({ title, summary, statuses }: SettingsSectionIntroProps) {
  return (
    <div className="grid gap-3">
      <div className="grid gap-1.5">
        <h2 className="text-[24px] font-semibold tracking-[-0.02em] text-[#1E232B]">{title}</h2>
        <p className="max-w-[760px] text-sm leading-6 text-[#66707D]">{summary}</p>
      </div>
      {statuses.length ? (
        <div className="flex flex-wrap gap-2">
          {statuses.map((status) => (
            <SettingsStatusBadge key={`${status.label}-${status.tone ?? "neutral"}`} label={status.label} tone={status.tone} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Renders a settings card with a title, summary, and slotted field content. */
export function SettingsCard({ title, summary, children }: SettingsCardProps) {
  return (
    <section className="overflow-hidden rounded-[22px] border border-[#E7EBF1] bg-white shadow-[0_14px_34px_rgba(15,23,42,0.05)]">
      <div className="border-b border-[#EEF1F5] px-6 py-5">
        <div className="grid gap-1.5">
          <h3 className="text-base font-semibold text-[#1F2430]">{title}</h3>
          <p className="text-sm leading-6 text-[#697384]">{summary}</p>
        </div>
      </div>
      <div className="grid">{children}</div>
    </section>
  );
}

/** Renders a settings field with title, description, control, and optional structured hint block. */
export function SettingsField({ label, description, badge, children, hint }: SettingsFieldProps) {
  return (
    <div className="grid gap-3 border-b border-[#EEF1F5] px-6 py-5 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <div className="text-sm font-medium text-[#171B22]">{label}</div>
          <div className="max-w-[700px] text-[13px] leading-6 text-[#6B7280]">{description}</div>
        </div>
        {badge ? <SettingsStatusBadge label={badge.label} tone={badge.tone} /> : null}
      </div>
      {children}
      {hint ? <div>{hint}</div> : null}
    </div>
  );
}

function HintRow({ label, value, mono = false }: { label: string; value?: string; mono?: boolean }) {
  if (!value) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1 text-[12px] leading-5 text-[#5C6674]">
      <span className="font-medium text-[#313843]">{label}</span>
      <span className={mono ? "font-mono text-[11px]" : undefined}>{value}</span>
    </div>
  );
}

/** Renders structured 用途 / 留空 / 影响 / 推荐 / config path hints under a settings field. */
export function SettingsFieldHint({ usage, blank, effect, recommendation, configPath }: SettingsFieldHintProps) {
  return (
    <div className="grid gap-1.5 rounded-[16px] border border-[#EBEEF3] bg-[#F8FAFC] px-4 py-3">
      <HintRow label="用途：" value={usage} />
      <HintRow label="留空：" value={blank} />
      <HintRow label="影响：" value={effect} />
      <HintRow label="推荐：" value={recommendation} />
      <HintRow label="路径：" value={configPath} mono />
    </div>
  );
}

/** Renders an in-card low-frequency settings block that can be expanded without losing form state. */
export function SettingsExpandableBlock({
  label = "展开更多选项",
  children,
  defaultExpanded = false,
}: SettingsExpandableBlockProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="grid gap-3 rounded-[18px] border border-dashed border-[#D8E0EA] bg-[#FBFCFD] px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm text-[#4E5662]">低频或高级项收在这里，展开后不会影响已输入内容。</div>
        <button
          className={cx("text-sm", ghostButtonClass, "rounded-md px-3 py-2")}
          type="button"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "收起更多选项" : label}
        </button>
      </div>
      {expanded ? <div className="grid gap-4">{children}</div> : null}
    </div>
  );
}

/** Shared password-like input that can be toggled visible without changing value semantics. */
export function SecretInput({ value, onChange, placeholder }: SecretInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="flex items-center gap-3">
      <input
        className={cx(inputClass, "flex-1 bg-white")}
        type={visible ? "text" : "password"}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        className={cx("shrink-0 rounded-md px-3 py-2 text-sm", ghostButtonClass)}
        type="button"
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? "隐藏" : "显示"}
      </button>
    </div>
  );
}

/** Shared muted read-only input for derived settings values. */
export function ReadOnlySettingInput({ value, placeholder }: { value: string; placeholder?: string }) {
  return (
    <input
      className={cx(inputClass, "bg-[#F4F6F9] text-[#707988]")}
      value={value}
      readOnly
      placeholder={placeholder}
    />
  );
}
