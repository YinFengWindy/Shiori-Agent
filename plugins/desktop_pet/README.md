# desktop_pet

桌宠插件拥有角色绑定、形象选择、显示与位置策略、气泡、语音交互和 Bilibili 直播陪伴。模型格式由独立形象插件提供；当前 `pet_codex_sprite` 支持 Codex 精灵图，依赖 `desktop_pet`。

## 状态与素材

`roles/roles.json` 的 `plugin_data.desktop_pet.<role_id>` 只保存 `selected_model`（提供者服务引用和模型 ID）与 `desktop_pet_enabled`。角色能力开关仍随角色页「保存」提交，单启用角色校验仍在同一角色事务中完成。模型提供者暂不可用不会删除选择。

精灵包 metadata 归 `plugin_data.pet_codex_sprite.<role_id>`，文件归 `plugin-data/pet_codex_sprite/pets-<role_id>/<package_id>/`。旧桌宠素材由精灵插件复制并核对，先提交自身 metadata，再改写桌宠选择，最后清理旧包目录；中断后可重试。备份应同时包含角色清单和各形象插件素材目录。

窗口可见状态与按角色/显示器保存的位置仍归桌宠设备偏好 `userData/plugin-data/desktop_pet.json`。语音偏好仍在 `plugin-data/desktop_pet/voice-preferences.json`；直播设置和登录凭据也继续归桌宠。

## 选择与导入

桌宠素材入口聚合当前可用提供者的模型和导入策略。原生 picker 使用该提供者声明的暂存命名空间、过滤条件与大小上限；后端由提供者再次验证文件和格式。`pets.import/remove/select` 使用角色、提供者引用及素材路径/模型 ID，桌宠不解析图集。

实际切换通过桌宠 background 的 `select` 执行：活动角色先准备候选模型，成功后交接并保存；准备或保存失败恢复原展示。未启用角色的选择只持久化，不激活窗口。

## 呈现与语音

桌宠通过 `shiori.pet-models.v1` 服务向选中提供者提交短呈现请求。提供者发自身事件给 background，加载完成后通过桌宠依赖回报实例就绪。接受请求不代表已显示；每次请求和呈现实例有独立身份，超时与迟到回报不能恢复旧窗口。

形象插件拥有实际 surface，通用气泡视图、指针手势和菜单来自 `@yinfengwindy/shiori-pet` 构建时共享模块。语音手势和显示落点回报桌宠；语音输入、TTS 队列和直播输出仍只有一套。真实录音、解码与播放由宿主通用原语提供，ASR/TTS 模型由可选择的 provider 提供。

SDK 4.0.1 的隐藏创建与 `surface.lifecycle` 事件支持模型准备和窗口失效处理。拖动、惯性和移动仍走原有通用 surface 原语；没有跨插件 React 挂载或新的插件层。

## 验证

插件测试仅使用 `shiori-sdk[testing]`；包安装见 `TESTING.md`。共享前端、桌宠和精灵插件的定向测试覆盖选择、交接、按来源取消和清理；真实宿主装配、独立打包与 Electron 语音组合另行验收。设计见 `docs/decisions/2026-11-09-desktop-pet-2d-providers.md`。
