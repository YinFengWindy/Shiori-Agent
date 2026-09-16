# desktop_pet

桌宠包模型、校验、导入服务、角色选择与单点启用状态由 `backend/` 拥有。
角色能力页中的开关由 `ui/roleSettings.tsx` 贡献，修改草稿后仍通过角色页的「保存」提交；选择/删除桌宠包后的投影刷新保留其他角色字段的未保存修改。

## 持久化边界

状态存于工作区 `roles/roles.json` 顶层 `plugin_data.desktop_pet.<role_id>`，不在 `RoleRecord`、角色序列化字段或 `runtime_config` 中。宿主的 `RoleExtensions` 只处理不透明命名空间和插件注册的草稿校验/投影。物理上与角色清单同文件是为了让角色修改、启用目标角色和禁用其他角色共享一次原子替换；没有两个 RPC 或两个文件之间的部分成功窗口。所有访问该规范化路径的 repository 实例共享进程内重入锁。

角色清单 v2/v3 → v4 迁移在读取/重写边界执行，早于 `RoleRecord` 投影；无需启用插件。旧 pet 字段的捕获和移除发生在同一次原子替换，失败保留旧清单，重试幂等。已存在的插件命名空间优先于残留旧字段，其他命名空间保持不变。

插件启用时和收到 `RoleDeleted` 时对照现存角色清理状态与孤儿 `pets` 资产；因此停用期间删除的角色会在重新启用时清理。删除角色时保留的非 pet 资产不受此清理影响。未完成导入/删除留下的孤儿目录在下次启用时清理。

## 原生文件选择与导入

`ui/petPackagePicker.ts` 通过注入的 `PluginHostServices.pickFiles` 选择 ZIP，插件声明过滤条件、32MB 限制与 `desktop_pet-pets` 暂存命名空间。宿主只提供通用的原生选择及受限复制，返回 `private_runtime/imports/<namespace>/UUID-原文件名`，不对 ZIP 签发媒体 URL。选择取消返回空列表；复制失败清理此次实际创建的文件。

`pets.import` 保持 `{role_id, source}` 契约，RPC 边界只接受该插件暂存目录内的普通 ZIP，拒绝外部路径、路径穿越、链接逃逸和超限文件；包结构与图片校验仍由插件服务负责。

## 仍待后续交付

- 动作通过 `ctx.rpc.emit("action", ...)` 下发；UI/surface 通过注入 client 的 `background.call("sync", ...)` 通知后台，宿主不持有桌宠通信特例。
- #220 / #221：观察与语音对桌宠表面的兼容耦合不在本次范围内。
