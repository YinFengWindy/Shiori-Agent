# P7 单 frontend 入口

范围：#964、#965，接续四层重构 #908。通用音频边界遵循同日已确认的 [D12 修订](2026-11-02-p7-scope-and-audio-boundary.md)。

插件源码只有 `frontend.entry`，该模块显式具名导出 `ui`、`background`、`surface` 中需要的贡献。现有组件和控制器可以直接 re-export；模块求值不启动任务或申请资源。主 UI、常驻后台和 surface 保持各自的执行环境与清理责任。

内置构建读取 manifest 生成一份模块清单，三个环境选择对应导出。外部包编译成一个 ESM，构建器根据真实导出表与 CSS 输出生成 `frontend.exports` 和 `frontend.css`。宿主按包授予一份资源快照和 `frontend_grant`，不再发送三份平行入口描述。

源码的 npm 对等依赖由 `package.json.peerDependencies` 声明；构建器将 React、React DOM 与 Shiori SDK 的范围写入 `frontend.peers`。这项元数据随受信包内容固定，Python 在执行插件代码、提示信任之前校验宿主版本。React 与 SDK 继续 external，实际模块通过宿主 import map 共享。删除顶层 `peer_dependencies` 不等于删除共享依赖检查。

旧 `renderer` 声明、默认导出适配、按目录查找 kind 的构建流程和三套传输字段全部移除。具名贡献自身的不同类型、窗口隔离、激活回执、失败回滚与业务判别联合保留。旧 API 不新增兼容层，4.0 发布前统一完成迁移。
