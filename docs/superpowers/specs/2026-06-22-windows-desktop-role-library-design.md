# Windows Desktop Agent + Role Library Design

## Goal
将当前 Agent 升级为 Windows 独立桌面应用，内置运行现有 Python Agent 核心，不接入外部消息渠道，不保留独立 dashboard。主界面只展示聊天对话，角色选择放在聊天界面内完成。

## Scope
- Windows-only。
- 桌面壳采用 Electron。
- Agent 核心继续由 Python 进程运行，随桌面应用一起启动。
- 移除 dashboard 作为用户功能入口。
- 增加本地角色库模块。
- 角色只影响系统提示词 / 说话风格。
- 角色支持本地上传头像和任意张立绘。

## Non-goals
- 不做跨平台适配。
- 不做角色权限控制、工具白名单、记忆策略切换。
- 不做云端同步。
- 不做消息渠道接入。
- 不保留独立 dashboard 页面。

## Architecture
应用由两部分组成：
- Electron 负责窗口、聊天 UI、角色库 UI、文件选择、设置与本地持久化入口。
- Python 负责现有 Agent 核心能力，包括会话、记忆、工具调用、模型推理和会话状态。

Electron 启动时拉起 Python Agent 子进程，并通过本地 IPC 交换：
- 当前会话消息
- 角色选择结果
- 发送消息请求
- Agent 流式输出
- 会话状态更新

不引入独立 dashboard 服务。任何原来只服务 dashboard 的 API、前端资源、构建产物和启动分支都视为迁移目标或删除目标。

## Role Library
角色库是本地文件夹级模块，不是独立服务。

### Role record
每个角色保存为一个目录或一个记录，包含：
- `id`
- `name`
- `description`
- `system_prompt`
- `avatar`
- `illustrations[]`
- `created_at`
- `updated_at`

### Asset model
- 头像和立绘都来自本地上传。
- 每个角色支持任意张图片。
- 图片只作为展示资产，不参与推理逻辑。
- 图片文件建议复制到 workspace 下的角色资产目录，避免原始路径失效。

### Persistence
- 角色定义建议存放在 `workspace/roles/roles.json` 或等价的本地清单中。
- 图片文件建议存放在 `workspace/roles/assets/<role_id>/`。
- 当前会话选中的角色建议记录到 session metadata，便于恢复。

## Chat UI
主界面只保留聊天。

### Layout
- 左侧会话列表或会话切换区。
- 中央聊天流。
- 输入框与发送按钮。
- 聊天页顶部放角色选择入口。

### Role selection flow
- 用户在聊天界面选择角色。
- UI 立即切换当前会话绑定的角色。
- 新消息使用该角色的 `system_prompt` 作为上下文前缀或系统提示词来源。
- 角色切换不修改历史消息。

### Avatar and illustration display
- 聊天页可显示当前角色头像。
- 可从角色的多张立绘中选择一张作为当前展示图。
- 图片切换只影响 UI，不影响对话内容。

## Data flow
1. Electron 启动。
2. Electron 拉起 Python Agent。
3. UI 读取会话列表和当前会话状态。
4. 用户选择角色。
5. 角色选择写入当前 session metadata。
6. 用户发送消息。
7. UI 将消息与当前角色上下文发送给 Python Agent。
8. Python Agent 生成回复并流式返回。
9. UI 更新对话显示和会话状态。

## Removal plan for dashboard
以下内容应从产品路径中移除：
- `main.py` 中的 `dashboard` 启动分支。
- `bootstrap/dashboard_api.py` 的运行入口。
- `frontend/dashboard` 作为默认用户界面。
- `build:dashboard`、`dev` 指向 dashboard 的前端脚本。
- 依赖 dashboard 的默认文档入口。
- 与 dashboard 直接绑定的前端类型声明和运行时代码。

插件或内部模块中若仍有 dashboard 相关 API，应作为后续清理目标，优先保留对 Agent 核心有用的能力。

## Risks
- 当前仓库大量能力已经和 dashboard 耦合，移除时需要分阶段收口，不能只删入口。
- Electron + Python 的本地 IPC 需要明确协议，否则调试成本会高。
- 角色资产如果只存相对路径而不复制进 workspace，后续容易失效。
- 角色系统如果后续想扩展为“行为/工具策略”，需要重新拆边界，当前版本不应预留过多复杂度。

## Acceptance criteria
- Windows 桌面应用可启动并进入单一聊天窗口。
- 本地 Agent 核心可随桌面应用一起运行。
- 用户能在聊天界面创建、编辑、选择角色。
- 角色支持本地上传头像与多张立绘。
- 角色切换后系统提示词会变化。
- `dashboard` 不再作为用户可访问功能存在。
