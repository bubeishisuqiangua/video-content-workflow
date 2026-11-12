# 视频内容工作流 Skill

从「想做什么视频」开始，经过构思、脚本、视频制作、成片检查、caption 和封面，再交接定时发布。可用于产品演示、教程、知识分享和故事短片；电影学英文是可选示例。

保留素材哈希校验、去重、版本保护、分平台进度、提交前记录和不确定结果核对。语言、受众、样式、审核要求、账号和时间由自己的项目配置决定。

这是一套给 agent 使用的技能和本地协调脚本。剪辑、生成图片、读取 Drive 和发布使用你连接的工具。仓库没有附带编辑器、模型、平台上传器或云端运行服务。Drive 导入和跨聊天交接提供规范，需要在自己的环境连接并实现相应能力。

## 使用

将仓库放进 agent 的 skills 目录，名称保留 `video-content-workflow`。Codex 通常使用 `~/.codex/skills/`，自定义安装用 `$CODEX_HOME/skills/`。需要时刷新技能发现。

可以直接说：

> 用 $video-content-workflow 帮我做一个产品功能视频，从创意和视频开始，再做文案、封面。先给我审阅，暂时不要发布。

也可从成片开始，或在明确授权后配置每日文件夹检查和自动交接。安装 skill 不代表授权发布、发消息、付费生成或创建定时任务。单个聊天可以完成全流程，多聊天只是可选方式。

项目文件放在 skill 目录之外。脚本需要 Python 3.10+；核验视频和封面需要 PATH 中的 FFmpeg、ffprobe。Windows 缺 IANA 时区数据时可安装 `tzdata`。初始化后先编辑 `workflow.json`，再创建实际任务：

```sh
python scripts/workflow.py --root /path/to/my-project init
```

默认关闭发布且无真实账号。平台线上记录才是排程依据；本地状态不能代替核实。定时运行需要宿主环境可用，不会因为安装 skill 就持续在线。

完整命令见 [操作说明](references/operations.md)，agent 入口见 [SKILL.md](SKILL.md)。MIT 开源；第三方视频、音乐和平台权限需要另行确认。
