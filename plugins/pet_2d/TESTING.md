# 独立测试

Python 测试使用合成小包，守住 ZIP 路径与资源上限、清单与图片完整性、跨文件引用、原子发布、失败重试、角色隔离及服务生命周期。依赖 `shiori-sdk[testing]>=4.1.2,<4.2.0`、`shiori-plugin-desktop-pet>=0.1.5` 与 Pillow；不依赖宿主 fixture。

在包含 SDK 与桌宠 wheel 的隔离环境安装 `.[test]` 后运行：

```sh
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

前端定向验证涵盖模型引用与网格数据、取消加载及资源销毁。嘴部、眼睑和头发的兼容性通过同版本参考播放器与原始样包比对；个人素材及参考脚本不提交。

真实 Electron 验收覆盖导入、透明绘制、切换精灵、气泡、实际音频口型、停止、直播回复及卸载。音频协议可用本地 HTTP 替身验证，不能据此宣称真实麦克风、模型音质或 Bilibili 登录已经验收。
