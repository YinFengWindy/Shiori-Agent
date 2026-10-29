# 插件运行时契约

这份长文已经退役。现行说明是：

- [插件指南](plugin-guide.md)：manifest 字段与版本比较语法、setup 上下文、服务 Key、事件顺序、版本策略和测试。
- [生命周期与准入](plugin-lifecycle.md)：规划、只登记、预执行闸门、重载、启停、诊断与信任。
- [前端契约](plugin-frontend.md)：renderer 入口、对等依赖、注入的 `client` 与 `host`、后台模块和 surface。
- [API 参考](plugin-api.md)：由 `python -m scripts.gen_plugin_api` 从内核和 `shiori_sdk.core` 生成。
- [插件变更](plugin-changelog.md)：4.0.0 起的定版记录。没有 Unreleased 批次。

旧的章节锚点不再维护。找方法签名时以生成的 API 参考和源码 docstring 为准。
