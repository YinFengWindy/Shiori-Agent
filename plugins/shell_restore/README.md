# shell_restore 插件

`rm` 命令安全改写。拦截 `shell` 工具调用，把 `rm` 命令改写为 `mv` 命令，将目标文件移入还原目录而非直接删除，防止 LLM 误操作导致不可逆数据丢失。

---

## 接入点

| 接入方式 | 阶段 |
|---|---|
| `@on_tool_pre(tool_name="shell")` | shell 工具执行前——改写命令参数 |

---

## 运作逻辑

### 1. 拦截 shell 工具

每次 LLM 调用 `shell` 工具时，钩子接收 `PreToolCtx`，取出 `arguments["command"]` 字符串。

### 2. 解析命令（_rewrite_command）

用 `shlex.split` 做 POSIX 拆词，逐 token 扫描：

1. 跳过前缀词（`sudo`、`env`、`VAR=val` 形式的环境变量赋值）。
2. 定位到 `rm`（按文件名匹配，支持完整路径如 `/bin/rm`）。
3. 跳过 `rm` 的所有 option 标志（以 `-` 开头的 token，`--` 后视为路径）。
4. 收集剩余 token 作为删除目标列表。

若命令中没有 `rm`，或解析不出目标路径，返回 `None`，插件不做修改。

### 3. 改写为 mv

把解析出的目标路径重新组装为：

```
[prefix...] mv -- <target1> <target2> ... <restore_dir>
```

`restore_dir` 默认使用当前工作区的绝对路径 `recovery/shell_restore/`，仅在实际改写命令时创建。该目录保存用户原文件，独立于可清空的 `plugin-data/`；停用、卸载或勾选删除插件数据均保留它。不同工作区各自隔离。

显式环境变量 `AKASIC_RESTORE_DIR` 继续优先，按原值使用；空值报错。历史 `~/restore` 不自动迁移、分配给某个工作区或删除，用户应单独备份和管理其内容。完整恢复备份须包含当前恢复目录，若设置了自定义路径则另行备份该路径。

改写后的命令字典替换原 `arguments` 并继续执行，LLM 感知不到任何变化。
