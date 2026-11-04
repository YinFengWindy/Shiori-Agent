# MCP

外部插件。连接用户配置的 MCP server，把它们的工具登记成 `mcp_<server>__<tool>`。stdio 进程仍由宿主拉起和回收。

## 启用

新装默认关闭。服务器登记保存在 `<workspace>/plugin-data/mcp/mcp_servers.json`。冷启动先迁入旧工作区根目录的 `mcp_servers.json`；已有新目标优先，旧文件核对后归档，详见[存储决策](../../docs/decisions/2026-11-04-plugin-storage-paths.md)。

新位置里已有服务器，并且 `config.toml` 的 `[plugins.mcp]` 没有显式写 `enabled` 时，启动会一次性写入 `enabled = true`，原有工具照常可用。显式写过 `enabled`（不论真假）的不改。proactive 的 MCP 客户端也读取此登记文件。

## 工具

| 工具 | 作用 |
|---|---|
| `mcp_add` | 连接一个 server 并保存到 `mcp_servers.json` |
| `mcp_remove` | 断开并移除一个 server |
| `mcp_list` | 列出已连接的 server 及其工具 |

启用后在后台重连 `mcp_servers.json` 里的全部服务器，单个失败只记录日志。文件格式不变：

```json
{"servers": {"fs": {"command": ["fs-server"], "env": {}, "cwd": null}}}
```

## 插件关闭时

没有 `mcp_*` 工具，也没有管理工具；`mcp_servers.json` 保留。
