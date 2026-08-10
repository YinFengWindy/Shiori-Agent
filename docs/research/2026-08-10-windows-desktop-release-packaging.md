# Shiori Windows 独立桌面应用发版调研

> 调研日期：2026-08-10
> 范围：Windows x64 安装包、Python Runtime 随应用分发、代码签名、GitHub Releases，以及后续自动更新。本文只描述发版方案，不修改现有代码或配置。

## 结论

Shiori 可以打包成用户无需安装 Node.js、Python、uv 或拉取源码即可运行的 Windows 桌面应用。推荐主线是：

1. 用 **PyInstaller 的 one-folder 模式**把 Python Runtime 冻结成一个随应用分发的 sidecar 目录；
2. 用 **electron-builder**打包现有 Electron 主进程、preload、renderer 和 Python sidecar；
3. 第一阶段输出 **NSIS 安装包**，同时保留 unpacked 目录用于排障；
4. 对 Python sidecar、Electron 应用和安装包执行 Windows Authenticode 签名；
5. 先通过 **GitHub Releases 手工下载升级**发布，等安装、配置迁移和回滚稳定后再接 `electron-updater`。

这条路线的重点不是“给当前 `npm run build` 套一个安装器”，而是先拆开两类路径：安装目录中的不可变程序资源，以及 `%APPDATA%` / 用户主目录下可写的配置、日志和工作区。Electron 官方也把“打包、代码签名、发布、更新”视为独立的分发阶段，而不只是源码编译：[Packaging Your Application](https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging)、[Code Signing](https://www.electronjs.org/docs/latest/tutorial/code-signing)。

## “独立应用”的边界

打包完成后，目标用户机器不再需要自行安装 Python、Node.js、npm、uv 或 Git；Electron、Python 解释器和 Python 依赖都由安装包携带。PyInstaller 官方说明，冻结后的应用可在没有安装 Python 解释器和模块的机器上运行，但构建产物是操作系统相关的，Windows 应在 Windows 上构建：[What PyInstaller Does and How It Does It](https://pyinstaller.org/en/stable/operating-mode.html)。

“独立”不等于完全离线。Shiori 仍需要用户提供模型服务配置；Telegram、QQ、NovelAI 等可选能力仍需要网络和各自凭据。用户数据也不应被封进安装包，应继续保存在本地可写目录。

## 当前仓库事实

以下是当前 checkout 的事实，不是建议：

| 项目 | 当前状态 | 发版影响 |
| --- | --- | --- |
| Electron 构建 | 根 `package.json` 的 `npm run build` 只转发到 `desktop/package.json`；后者只执行主进程/preload 的 `tsc` 和 renderer 的 Vite build | 能得到编译产物，但没有安装器或可分发应用目录 |
| 打包工具 | 两份 `package.json` 都没有 Electron Forge、electron-builder、maker、publisher 或 installer 配置 | 当前不存在正式打包链 |
| Python 启动 | `desktop/src/bridgeClient.ts` 固定寻找仓库根目录 `.venv/Scripts/python.exe`，并以仓库根为 `cwd` 执行 `main.py bridge` | 离开源码仓库后无法启动；必须改为启动 packaged sidecar |
| 配置位置 | `desktop/src/main.ts` 和 `desktop/src/settings.ts` 都按 Electron 编译目录向上定位仓库根 `config.toml`；缺失时复制 `config.example.toml` | 安装目录/ASAR 不应作为运行时写目录，升级也可能覆盖它 |
| 用户工作区 | Python 默认工作区是 `~/.shiori/workspace`，Electron 已使用 `app.getPath("userData")` 保存部分桌面状态 | 工作区方向基本正确，但配置、日志和桌面状态需要形成统一且可迁移的边界 |
| 应用资源 | `desktop/src/paths.ts` 和部分 IPC 逻辑从当前 `desktopRoot` 的父目录读取 `assets/` | 打包后目录布局改变，必须按 `process.resourcesPath` 或明确的资源定位 helper 解析 |
| 原生依赖 | `desktop/package.json` 包含 `uiohook-napi`；Python 依赖还包含 `numpy`、`Pillow`、`lxml`、`sqlite-vec` 等二进制/动态依赖 | 需要 Electron ABI rebuild 和 PyInstaller hidden import/binary 收集验证，不能只看编译通过 |
| CI | `.github/workflows/ci.yml` 只在 Ubuntu PR 上 lint、typecheck、test、build | 没有 Windows 冻结、安装、签名、制品上传或发布 job |
| 发布/更新 | 仓库内没有 GitHub Release workflow、更新 feed 或 `autoUpdater`/`electron-updater` 代码 | 首版应按“安装包可手工升级”验收，自动更新另做一阶段 |

因此，README 中的“生产构建”当前准确含义是“编译后可从源码 checkout 启动”，还不是“可交付给普通 Windows 用户的独立安装包”。

## 推荐的产物布局

建议将运行时边界固定为：

```text
Shiori Setup x.y.z.exe          # 对外发布的 NSIS 安装器

安装后：
%LOCALAPPDATA%\Programs\Shiori\
  Shiori.exe                    # Electron 应用
  resources\
    app.asar                    # 主进程、preload、renderer
    python-runtime\             # PyInstaller onedir sidecar
      shiori-runtime.exe
      ...Python 动态库和依赖
    assets\                     # 图标和必须在 ASAR 外读取的资源
    config.example.toml         # 只读模板，不含密钥

运行时可写数据：
%APPDATA%\Shiori\config.toml    # 建议统一到 Electron userData
%APPDATA%\Shiori\logs\         # 桌面诊断日志
%USERPROFILE%\.shiori\workspace\
                                # 角色、会话、记忆、素材等现有工作区
```

electron-builder 的 `files` 用于选择应用文件，`extraResources` 会把额外文件复制到应用的 resources 目录，适合放 Python sidecar、模板和外部资源：[Application Contents](https://www.electron.build/docs/contents/)。运行时应通过 Electron 的 `process.resourcesPath` 定位只读资源，而用户配置使用 `app.getPath("userData")`；两者是 Electron 官方定义的运行时路径：[process.resourcesPath](https://www.electronjs.org/docs/latest/api/process#processresourcespath-readonly)、[app.getPath(name)](https://www.electronjs.org/docs/latest/api/app#appgetpathname)。

不要把真实 `config.toml`、工作区、数据库或用户素材放进安装包。安装包只携带无密钥的模板；首次启动时复制到可写目录，后续升级只迁移 schema，不覆盖用户值。

## Python Runtime 打包

### 为什么推荐 one-folder

PyInstaller 支持 one-folder 和 one-file。one-folder 启动时无需先把全部内容解压到临时目录，依赖和缺失文件也更容易检查；one-file 每次启动会先解包到临时目录，官方明确说明它的启动更慢：[How the One-File Program Works](https://pyinstaller.org/en/stable/operating-mode.html#how-the-one-file-program-works)。Shiori 的 Python Runtime 是常驻 sidecar，且包含多个原生依赖，因此首版选择 one-folder 更稳妥，外层仍只有一个 NSIS 安装包，不会增加用户操作复杂度。

### 建议入口和 spec

新增一个专用、尽量薄的冻结入口，例如 `packaging/shiori_runtime.py`，只负责进入现有 `main.py bridge` 对应的装配流程。用 `.spec` 文件显式记录：

- 必须作为数据携带的内置插件、提示词和默认模板；
- 动态导入模块的 hidden imports；
- `sqlite-vec`、`numpy`、`Pillow`、`lxml` 等实际需要的动态库；
- 不应进入产物的测试、缓存、真实配置、日志和用户数据。

PyInstaller 官方说明，spec 文件本身是可执行 Python，`Analysis` 的 `datas`、`binaries`、`hiddenimports` 用于描述这三类输入：[Using Spec Files](https://pyinstaller.org/en/stable/spec-files.html)。对于通过动态导入而无法被静态分析发现的模块，应使用 hook、`--hidden-import`、`--collect-submodules` 或 `--collect-all`，但应按实际失败证据精确收集，而不是无界打包整个仓库：[Understanding PyInstaller Hooks](https://pyinstaller.org/en/stable/hooks.html)。

### Electron 与 sidecar 的新契约

Electron 主进程不再查找 `.venv/Scripts/python.exe`，而是根据运行模式解析两个明确入口：

- 开发环境：继续运行仓库 `.venv/Scripts/python.exe main.py bridge`；
- packaged 环境：运行 `process.resourcesPath/python-runtime/shiori-runtime.exe`，并把配置路径、工作区路径、日志路径作为显式参数或环境变量传入。

应直接持有 spawned child 的 PID 并终止其进程树。当前通过 PowerShell 按 `python.exe` 和 `main.py bridge` 命令行清理的逻辑不适用于冻结后的 `shiori-runtime.exe`，也不应作为新契约的主路径。

## Electron 打包器选择

### 推荐：electron-builder

对 Shiori 这类“Electron 壳 + 大型外部 sidecar 目录”的应用，electron-builder 的 `extraResources`、NSIS target、Windows 签名和 `electron-updater` 路线比较直接。建议配置放在 `desktop/electron-builder.yml`，由根脚本先构建 Python sidecar，再构建 Electron，最后执行 builder。electron-builder 官方配置入口说明了 `appId`、`productName`、`files`、`extraResources`、`asar`、`win.target`、`publish` 等字段：[Common Configuration](https://www.electron.build/docs/configuration/)。NSIS 是 electron-builder 的默认 Windows target，并支持 per-user/per-machine、安装目录选择和升级行为：[NSIS Options](https://www.electron.build/nsis/)。

必须保留 Electron 原生模块重建步骤。Electron 官方说明，原生 Node 模块需要针对 Electron 的 ABI 重新构建，并推荐 Electron Forge 或 `@electron/rebuild`；electron-builder 也会管理依赖重建，但 Windows Release CI 必须通过真实启动 smoke 验证 `uiohook-napi`：[Using Native Node Modules](https://www.electronjs.org/docs/latest/tutorial/using-native-node-modules)。

### 建议的构建命令边界

最终脚本名称可在实现时决定，但 Release job 的职责应类似：

```powershell
# 1. 使用锁定的 Windows Python 环境生成 onedir sidecar
.venv-release\Scripts\python.exe -m PyInstaller --noconfirm packaging\shiori-runtime.spec

# 2. 可重复安装前端依赖并编译 Electron 三个入口
npm ci
npm --prefix desktop ci --no-audit --no-fund
npm run build

# 3. 首先只生成本地待验收的 x64 NSIS 制品
npx --prefix desktop electron-builder --win nsis --x64 --publish never
```

PyInstaller 的 CLI 和 `--onedir`/spec 用法见官方 [Using PyInstaller](https://pyinstaller.org/en/stable/usage.html)；electron-builder v27 起不再依赖隐式 publish 行为，Release job 应显式指定 `--publish never`、`onTag` 或 `always`：[Publish](https://www.electron.build/docs/publish/)。签名接入后，签名和验证位于发布上传之前，任何一步失败都不创建公开 Release。

### 备选：Electron Forge

Electron 官方 packaging 教程推荐 Electron Forge 作为一体化打包和分发工具；Forge 的 Squirrel.Windows maker 可以生成 Windows 安装制品，GitHub publisher 可以创建 GitHub Release 并上传产物：[Packaging Your Application](https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging)、[Squirrel.Windows Maker](https://www.electronforge.io/config/makers/squirrel.windows)、[GitHub Publisher](https://www.electronforge.io/config/publishers/github)。

Forge 也可完成任务，但本项目需要明确携带 Python onedir 和多个外部资源；相较之下，electron-builder 的 `extraResources + NSIS + electron-updater` 文档路径更短。两套工具只能选一套，不建议同时维护两条安装链。

## 签名与 SmartScreen

公开分发的 Windows 安装包应在首个对外版本前签名。Electron 官方说明，Windows 会检查代码签名证书，未签名应用会触发安全警告；分发和自动更新也依赖可信签名：[Electron Code Signing](https://www.electronjs.org/docs/latest/tutorial/code-signing)。

推荐顺序：

1. 在受控 Windows runner 上生成 Python onedir；
2. 对 `shiori-runtime.exe` 及其中需要签名的自有可执行文件签名；
3. 由 electron-builder 打包并签名 Electron 应用；
4. 对最终 NSIS 安装包签名；
5. 使用 SignTool 的 `/pa` 验证 Authenticode 策略和时间戳，失败即停止发布。

微软官方 SignTool 文档要求在签名和时间戳时显式指定摘要算法，推荐 SHA-256，并提供 `sign`、`timestamp`、`verify` 命令：[SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)。Smart App Control 的微软文档要求应用使用受信任提供者签发的 RSA 代码签名证书，并指出每段代码都应签名；ECC 签名目前不受该检查支持：[Code Signing for Smart App Control](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control)。

证书私钥不能进仓库。CI 中应使用 GitHub Environments 限制 release job，并从 secrets 或硬件/云签名服务临时取用凭据。electron-builder 支持 PFX、硬件令牌和 Azure Artifact Signing 等 Windows 签名方式，具体方案应在选定证书供应商后按其官方 [Windows Code Signing](https://www.electron.build/docs/features/code-signing/code-signing-win/) 接入。微软的托管方案 Artifact Signing 提供 HSM 保护的签名服务和 Public Trust 证书配置：[Artifact Signing overview](https://learn.microsoft.com/en-us/azure/trusted-signing/overview)。

签名能证明发布者和文件完整性，但不能承诺 SmartScreen 永不提示。微软说明 Defender SmartScreen 会同时检查数字签名以及文件、URL 和证书的信誉；信誉不足仍可能产生警告：[Microsoft Defender SmartScreen overview](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/)。首版仍应准备干净 Windows VM 安装证据，并在误报时走微软官方 [Submit a file for malware analysis](https://www.microsoft.com/en-us/wdsi/filesubmission) 提交流程。

## GitHub Releases 与自动更新

### 第一阶段：手工升级

建议每个版本发布：

- `Shiori-Setup-x.y.z.exe`；
- `SHA256SUMS.txt`；
- 版本说明和升级注意事项；
- 可选的 unpacked/diagnostic 制品只放 CI artifact，不面向普通用户。

GitHub 官方把 Release 定义为基于 tag 的可部署软件版本，并支持二进制文件和 release notes：[About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。Release workflow 应由版本 tag 触发，在 Windows runner 上重新执行测试、冻结、打包、签名、安装 smoke，再创建 Draft Release；人工核对后转为公开。

### 第二阶段：自动更新

首版不建议把自动更新作为出包阻塞项。先证明以下契约稳定：配置不会被覆盖、工作区不会迁移失败、旧版本能被安装器正确替换、sidecar 能退出、失败后能回滚。

后续可使用 `electron-updater` 对接 GitHub provider。electron-builder 官方文档说明其自动更新模块支持 NSIS 等 target，并会生成更新元数据；应用必须配置 publisher 并在 packaged app 中检查更新：[Auto Update](https://www.electron.build/docs/features/auto-update/)、[Publish](https://www.electron.build/docs/publish/)。更新通道至少要区分 stable 和 prerelease，且不要让未签名或未完成 smoke 的资产进入 stable feed。

Electron 自带的 `autoUpdater` 在 Windows 上依赖 Squirrel.Windows；如果最终采用 NSIS，应使用 electron-builder 的 `electron-updater`，不要混用两套协议：[Electron autoUpdater](https://www.electronjs.org/docs/latest/api/auto-updater)。

## 推荐实施顺序

### 阶段 0：冻结前审计

- 列出 Python 运行时真正需要的模块、数据文件、内置插件和动态库；
- 固化 Release 使用的 Python 与 Node/Electron 版本；
- 明确产品名称、`appId`、安装范围、升级策略、证书主体和 GitHub Release 命名；
- 决定配置最终位于 `%APPDATA%\Shiori` 还是现有 `~/.shiori`，避免同时出现两个不清楚的配置源。

### 阶段 1：可携带目录版

- 先让 PyInstaller onedir 在没有 Python 的干净 Windows VM 中通过 bridge health check；
- Electron packaged app 从 `process.resourcesPath` 启动 sidecar；
- 把配置和日志迁到可写目录；
- 用 unpacked Electron 目录完成首次启动、聊天、图片/素材、语音、桌宠、退出和重启 smoke。

### 阶段 2：安装包

- 接入 electron-builder NSIS；
- 验证安装、覆盖升级、卸载、保留用户数据、桌面/开始菜单入口；
- 验证 tray 常驻时升级或卸载不会遗留 Electron/Python 进程。

### 阶段 3：签名与发布

- 签名所有自有 PE 文件和最终安装器；
- Windows CI 生成哈希并验证签名；
- 上传 Draft GitHub Release，人工验证后发布。

### 阶段 4：自动更新

- 加入 prerelease 通道和内部试用；
- 验证下载、签名校验、退出安装、失败恢复和配置迁移；
- 稳定后再开放 stable 自动更新。

## 最低验收矩阵

| 场景 | 必须证明 |
| --- | --- |
| 干净 Windows 11 x64 | 未安装 Python/Node/uv，仍能安装并启动 |
| 首次启动 | 创建无密钥默认配置；缺少主模型时给出可操作错误，不崩溃 |
| Bridge | sidecar health 成功；异常退出可见；Electron 退出后无残留进程 |
| 核心数据 | 创建角色、聊天、重启后会话和工作区仍存在 |
| 资源 | 头像、立绘、图片、Story CG、桌宠素材和应用图标在 packaged 环境可读取 |
| 原生能力 | `uiohook-napi` 热键、麦克风、托盘、桌宠窗口在 Release build 可用 |
| 升级 | 从上一个公开版本覆盖安装，不覆盖配置、密钥、数据库和素材 |
| 卸载 | 程序文件移除；是否保留用户数据符合明确产品策略 |
| 签名 | sidecar、主程序、安装包的 SignTool verify 全部通过 |
| 安全软件 | Defender/SmartScreen 实机结果记录；误报有可追踪提交记录 |

单元测试和 `npm run build` 不能替代这套矩阵。Electron 官方的打包教程也把 `make` 后对 distributable 的实际测试作为发布前步骤：[Packaging Your Application](https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging#package-and-distribute-your-application)。

## 主要风险与决策点

1. **配置路径是首要阻塞项。** 当前代码会向仓库/应用目录写 `config.toml`；不先迁移，ASAR 或 Program Files 布局下会失败或升级丢配置。
2. **Python 插件与动态依赖可能让“能冻结”不等于“能运行”。** 必须从 bridge health 到真实功能逐项补 PyInstaller hook/spec，避免靠大量 fallback 掩盖缺包。
3. **原生模块必须在 Electron Release ABI 下验证。** `uiohook-napi` 是全局热键和桌宠语音链路的真实风险点。
4. **进程生命周期要改为 sidecar 契约。** 不能继续依赖 `python.exe main.py bridge` 的命令行特征。
5. **签名应在安装链设计时接入。** 等安装包完成后再补签名，容易遗漏 sidecar 或破坏最终文件哈希。
6. **自动更新不是首包必需。** 手工 Release 可以先验证核心安装与数据迁移边界，减少同时调试安装器和更新器的风险。

## 建议拆分的后续 Issue

1. `release: freeze Python bridge runtime with PyInstaller onedir`
2. `release: separate packaged resources from writable config and user data`
3. `release: package Electron and Python sidecar with electron-builder NSIS`
4. `release: add Windows packaged-app and installer smoke tests`
5. `release: sign Windows binaries and publish Draft GitHub Releases`
6. `release: add prerelease auto-update after installer stabilization`

每个实现 PR 都应关联对应 Issue，并写明实际在干净 Windows 环境完成的验证；在安装/升级 smoke 和签名验证通过前保持 Draft。

## 官方资料索引

- Electron Packaging：<https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging>
- Electron Code Signing：<https://www.electronjs.org/docs/latest/tutorial/code-signing>
- Electron Native Node Modules：<https://www.electronjs.org/docs/latest/tutorial/using-native-node-modules>
- Electron `process.resourcesPath`：<https://www.electronjs.org/docs/latest/api/process#processresourcespath-readonly>
- Electron `app.getPath`：<https://www.electronjs.org/docs/latest/api/app#appgetpathname>
- Electron `autoUpdater`：<https://www.electronjs.org/docs/latest/api/auto-updater>
- electron-builder Configuration：<https://www.electron.build/docs/configuration/>
- electron-builder Application Contents：<https://www.electron.build/docs/contents/>
- electron-builder NSIS：<https://www.electron.build/nsis/>
- electron-builder Windows Code Signing：<https://www.electron.build/docs/features/code-signing/code-signing-win/>
- electron-builder Auto Update：<https://www.electron.build/docs/features/auto-update/>
- electron-builder Publish：<https://www.electron.build/docs/publish/>
- Electron Forge Squirrel.Windows Maker：<https://www.electronforge.io/config/makers/squirrel.windows>
- Electron Forge GitHub Publisher：<https://www.electronforge.io/config/publishers/github>
- PyInstaller Operating Mode：<https://pyinstaller.org/en/stable/operating-mode.html>
- PyInstaller Spec Files：<https://pyinstaller.org/en/stable/spec-files.html>
- PyInstaller Usage：<https://pyinstaller.org/en/stable/usage.html>
- PyInstaller Hooks：<https://pyinstaller.org/en/stable/hooks.html>
- Microsoft SignTool：<https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool>
- Microsoft Smart App Control Code Signing：<https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control>
- Microsoft Artifact Signing：<https://learn.microsoft.com/en-us/azure/trusted-signing/overview>
- Microsoft Defender SmartScreen：<https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/>
- Microsoft Security Intelligence file submission：<https://www.microsoft.com/en-us/wdsi/filesubmission>
- GitHub Releases：<https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases>
