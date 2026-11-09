# 独立测试

插件依赖 `shiori-sdk>=4.1.1,<4.2.0`、`shiori-plugin-desktop-pet>=0.1.5` 和 Pillow；测试仅使用 SDK testing。独立 wheelhouse 必须同时包含匹配的 SDK 与桌宠插件 wheel，不依赖宿主或根 conftest。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

现有包校验、ZIP 与原生暂存边界测试随素材所有权迁入本插件。迁移回归覆盖复制后的两次命名空间提交失败、清理失败后重试、目标冲突和禁用意图保留；呈现回归覆盖未就绪拒绝、准备数据由 provider 校验、失联撤销就绪；setup 验证依赖与服务释放。

模型服务接收命令不代表模型已经显示。真正 ready/failed/closed/hidden 回报、surface 切换与 GPU/动画释放由前端测试及真实 Electron 验收确认。样包不加入自动测试。
