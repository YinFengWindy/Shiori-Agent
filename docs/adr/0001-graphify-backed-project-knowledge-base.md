---
title: 使用 Graphify 支撑项目知识库
kind: 架构决策记录
status: 已接受
last_verified_commit: 27af068a
source_paths:
  - .graphifyignore
  - .git/hooks/post-commit
  - .git/hooks/post-checkout
  - docs/knowledge/
related:
  - ../knowledge/index.md
  - ../knowledge/quality/graph-health.md
---

# ADR-0001：使用 Graphify 支撑项目知识库

## 背景

Shiori 的能力跨越 Python 后端、Electron/React 桌面端、插件、渠道、运行时数据和多套记忆实现。仅依赖目录浏览很难回答“某功能在哪里、依赖谁、修改会影响什么”，纯手写文档又容易与源码漂移。

## 决策

采用双层知识库：

- `graphify-out/` 保存本地可查询图谱、交互式 HTML 和诊断报告，不进入 Git。
- `docs/knowledge/` 保存经过源码核验的中文稳定知识，进入 Git，允许人工修订。
- `CONTEXT.md` 作为人和 Agent 的统一入口。
- Git `post-commit` 与 `post-checkout` hook 自动更新代码图谱；业务文档仍由人工在相关改动时维护。
- 主图谱纳入业务源码和架构知识，排除测试、评测、依赖、构建产物、运行数据、图片素材、`docs/specs/` 与 `docs/plan/`。

## 原因

Graphify 擅长从符号和关系反查源码，适合发现跨模块影响；人工知识页适合记录稳定语义、边界、失败策略和有证据的设计原因。两者组合比单独使用任一方式更适合长期维护。

## 后果

- 优点：Agent 可先图谱查询再精读源码；人可通过中文能力地图快速定位；提交后图谱自动跟随代码变化。
- 成本：图谱存在提取和边折叠误差；知识页不会自动理解业务语义，仍需随行为变更维护。
- 约束：不能把图谱推断当作源码事实；健康异常必须公开；语义提取未返回 token 用量时必须记录为 `0`，不得估算成真实成本。

## 替代方案

- 只生成 Graphify Wiki：产物数量大，语义质量不稳定，不适合作为提交到仓库的稳定文档。
- 只维护手写文档：缺少符号级反查和跨目录路径发现，容易遗漏影响面。
- 直接提交 `graphify-out/`：图谱体积和更新噪声较大，并且本地路径、缓存和诊断产物不适合版本控制。
