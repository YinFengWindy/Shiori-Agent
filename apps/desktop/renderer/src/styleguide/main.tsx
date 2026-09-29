import React from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import * as Icons from "../shared/ui/icons";
import { SelectExamples } from "./SelectExamples";
import { PetalIcon, SparkleIcon, badgeClass, cardClass, ghostButtonClass, inputClass, textareaClass } from "@shiori/plugin-sdk";
import {
  dangerButtonClass,
  dangerGhostButtonClass,
  panelTitleClass,
  primaryButtonClass,
} from "../shared/styles";

const RAMPS: Record<string, string[]> = {
  neutral: ["50", "100", "150", "200", "300", "400", "500", "600", "700", "800", "900", "950"],
  pink: ["50", "100", "150", "200", "300", "400", "500", "600", "700", "800", "900"],
  lavender: ["50", "100", "150", "200", "300", "400", "500", "600", "700"],
  blue: ["50", "100", "150", "200"],
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2 className="mb-4 font-display text-headline text-ink">{title}</h2>
      {children}
    </section>
  );
}

function Swatch({ varName, label }: { varName: string; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="h-10 w-10 rounded-md border border-line-soft"
        style={{ background: `var(${varName})` }}
      />
      <span className="text-[10px] text-ink-muted">{label}</span>
    </div>
  );
}

const FONT_CANDIDATES = [
  { label: "现状优化栈(0MB)", stack: '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", sans-serif' },
  { label: "MiSans(需打包 ≈9MB)", stack: '"MiSans", "Microsoft YaHei UI", sans-serif' },
  { label: "HarmonyOS Sans SC(需打包 ≈10MB)", stack: '"HarmonyOS Sans SC", "Microsoft YaHei UI", sans-serif' },
];

const SAMPLE_TEXT = "让角色拥有自己的生活——吟风等你回来,记得汇报今天的锻炼。0123456789 AaGg";

function App() {
  const brand = Object.entries({ ...Icons, PetalIcon, SparkleIcon }).filter(
    ([name, value]) => name.endsWith("Icon") && typeof value === "function",
  ) as Array<[string, React.ComponentType<{ className?: string }>]>;

  return (
    <div className="min-h-screen overflow-auto bg-gradient-app p-10 text-body text-ink">
      <div className="mx-auto max-w-5xl">
        <header className="mb-10">
          <h1 className="m-0 font-display text-display text-gradient-accent">Shiori 设计地基样板</h1>
          <p className="mt-2 text-body-lg text-ink-secondary">
            阶段 1 验收:色彩 token、字阶、基础控件、图标集(contact sheet)
          </p>
        </header>

        <SelectExamples />
        <Section title="色阶原语">
          {Object.entries(RAMPS).map(([ramp, steps]) => (
            <div key={ramp} className="mb-3 flex items-end gap-2">
              <span className="w-16 text-body-sm text-ink-muted">{ramp}</span>
              {steps.map((s) => (
                <Swatch key={s} varName={`--${ramp}-${s}`} label={s} />
              ))}
            </div>
          ))}
          <div className="mt-4 flex items-end gap-2">
            <span className="w-16 text-body-sm text-ink-muted">status</span>
            {["--success-600", "--warning-600", "--danger-600", "--success-100", "--warning-100", "--danger-100"].map((v) => (
              <Swatch key={v} varName={v} label={v.replace("--", "")} />
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <span className="w-16 text-body-sm text-ink-muted">gradient</span>
            <div className="h-10 w-48 rounded-md bg-gradient-accent" />
            <div className="h-10 w-48 rounded-md bg-gradient-accent-soft" />
            <span className="text-gradient-accent text-title-sm font-semibold">文字渐变效果</span>
          </div>
        </Section>

        <Section title="字阶(语义)">
          <div className="flex flex-col gap-2 rounded-lg border border-line-soft bg-surface p-6 shadow-soft">
            <span className="text-display">display 28 — 让角色拥有自己的生活</span>
            <span className="text-headline">headline 22 — 让角色拥有自己的生活</span>
            <span className="text-title">title 18 — 编辑角色资料与设定</span>
            <span className="text-title-sm">title-sm 16 — 渠道与主动推送</span>
            <span className="text-body-lg">body-lg 15 — 聊天正文:哼,舍得回来啦?本小姐都等到快九点了。</span>
            <span className="text-body">body 14 — 表单与常规界面文字,中文正文的最低舒适字号。</span>
            <span className="text-body-sm">body-sm 13 — 辅助说明文字,配 ink-muted 使用。</span>
            <span className="text-caption text-ink-muted">caption 12 — 时间戳与元信息 · 12:34 · 33,737 tokens</span>
            <span className="text-body tabular-nums">tabular-nums — 寂寞值 100 / 099 / 001(数字等宽不跳动)</span>
          </div>
        </Section>

        <Section title="字体候选(在装有对应字体的机器上预览)">
          <div className="flex flex-col gap-3">
            {FONT_CANDIDATES.map((f) => (
              <div key={f.label} className="rounded-lg border border-line-soft bg-surface p-4 shadow-soft">
                <div className="mb-1 text-caption text-ink-muted">{f.label}</div>
                <div className="text-body-lg" style={{ fontFamily: f.stack }}>{SAMPLE_TEXT}</div>
                <div className="text-title" style={{ fontFamily: f.stack }}>标题字重演示 · 吟风的生活空间</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="基础控件">
          <div className="flex flex-col gap-6">
            <div className="flex flex-wrap items-center gap-3">
              <button className={primaryButtonClass}>主要操作</button>
              <button className={ghostButtonClass}>次要操作</button>
              <button className={dangerButtonClass}>删除角色</button>
              <button className={dangerGhostButtonClass}>移除素材</button>
              <button className={primaryButtonClass} disabled>禁用状态</button>
              <span className={badgeClass}>
                <SparkleIcon className="h-3 w-3" />
                害羞
              </span>
            </div>
            <div className="grid max-w-2xl grid-cols-2 gap-4">
              <input className={inputClass} placeholder="给当前角色发送消息…" />
              <input className={inputClass} defaultValue="吟风" />
              <textarea className={textareaClass} placeholder="系统提示词…" defaultValue="你将扮演一位二次元原创少女角色。" />
              <div className={cardClass + " p-4"}>
                <h3 className={panelTitleClass}>卡片标题</h3>
                <p className="m-0 mt-1 text-body-sm text-ink-muted">cardClass + panelTitleClass 组合效果。</p>
              </div>
            </div>
            <div className="rounded-xl bg-gradient-accent p-8">
              <div className="surface-glass max-w-md rounded-lg p-5">
                <div className="text-title-sm text-ink">玻璃面板 surface-glass</div>
                <p className="m-0 mt-1 text-body-sm text-ink-secondary">
                  浮在角色立绘 / 渐变背景上的半透明表面,聊天消息卡将使用这一层。
                </p>
                <button className={primaryButtonClass + " mt-3 py-2"}>来了</button>
              </div>
            </div>
            <div>
              <span className="text-body-sm text-ink-muted">键盘焦点环(Tab 键试试):</span>
              <button className={ghostButtonClass + " ml-3"}>可聚焦控件</button>
            </div>
          </div>
        </Section>

        <Section title="品牌母题">
          <div className="flex items-center gap-6 text-accent">
            {brand.map(([name, Comp]) => (
              <div key={name} className="flex flex-col items-center gap-2">
                <Comp className="h-10 w-10" />
                <span className="text-caption text-ink-muted">{name.replace(/Icon$/, "")}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 text-lavender">
              {brand.map(([name, Comp]) => (
                <Comp key={name} className="h-6 w-6" />
              ))}
            </div>
          </div>
        </Section>

      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
