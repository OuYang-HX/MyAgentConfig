# gwf · Git WorkTree Flow

> **GWF = Git WorkTree Flow**。`gwf` 是这条工作流的命令行引擎。

一个**技能集合**组件：把"纯 worktree 多需求并行开发"和"fork 上游同步治理"拆成 6 个可一句话触发的技能 + 1 个跨平台引擎。

## 组件内结构

```text
components/gwf/
├── manifest.json          # 安装声明（技能目录、命令、gitignore、git config、依赖）
├── README.md              # 本文件
├── references/            # 细则库（布局 / 裁决 / 验证 / 模板）
├── scripts/               # gwf 引擎（纯 Python3 标准库）
│   ├── gwf.py
│   ├── gwf                # macOS / Linux 入口
│   └── gwf.cmd            # Windows 入口
└── skills/                # 本组技能（安装器把每个子目录链到 ~/.agents/skills/）
    ├── git-worktree-flow/ # 集合入口 + 路由表 + 铁律
    ├── gwf-init/          # 建仓 / 迁移 / 体检
    ├── gwf-new/           # 开需求 + 台账
    ├── gwf-scan/          # 状态 + 冲突预警
    ├── gwf-sync/          # 同步官方 + 裁决（旗舰）
    └── gwf-archive/       # 合入 + 归档
```

## 三层分工（用户不用复述需求的原因）

| 层 | 位置 | 内容 |
| --- | --- | --- |
| 方法 | `skills/*/SKILL.md` | 审计顺序、裁决矩阵、清理清单、验收标准 |
| 项目事实 | 仓库根 `.gwf.json` | 官方远端、主干分支、验证命令、锁文件 |
| 任务状态 | 各工作树 `worktree.md` | 需求目标、改动范围、上游判据、同步记录 |

## 一键命令

| 场景 | 技能 | 命令 |
| --- | --- | --- |
| 建仓 / 迁移 / 换机器体检 | `gwf-init` | `gwf init` / `gwf doctor` |
| 开需求 | `gwf-new` | `gwf new` |
| 看状态 / 查冲突 | `gwf-scan` | `gwf status` / `gwf scan` |
| 同步官方代码 | `gwf-sync` | `gwf sync --all` |
| 合入归档 | `gwf-archive` | `gwf archive <dir> --merge` |

## 安装（链接，不复制）

由仓库根安装器统一处理，组件本身不需要单独安装脚本：

```bash
./install.sh --only gwf        # 只装这一个组件
./install.sh --list            # 看仓库里有哪些组件
./install.sh --status          # 检查是否都是链接（不是复制）
```

安装后 `~/.agents/skills/gwf-*` 与 `~/.local/bin/gwf` 都是**指向本仓库的链接**：
改仓库文件立即生效，`git pull` 后各机器自动同步，无需重装。

## 设计参考

- 技能组织方式：[mattpocock/skills](https://github.com/mattpocock/skills)（每个能力一个短技能、技能名即命令、正文自带方法论）
- 补丁管理方法：Debian DEP-3 补丁标记、RPM patch 栈、官方优先与改动量单调递减
