# MyAgentConfig

个人跨设备的 **Agent 配置仓库**：技能组、MCP 配置、工具链，全部按"组件"组织，一台机器一条命令装齐。

## 组件模型

仓库不再是"一堆技能"，而是**可扩展的组件集合**。每个组件自带声明，安装器不认识任何具体组件：

```text
MyAgentConfig/
├── install.sh / install.ps1     # 通用安装器（薄包装，零业务逻辑）
├── tools/install.py             # 安装器实现：组件发现、链接、配置合并、hook
├── config/gitignore-global      # 仓库级全局忽略片段（可选）
├── components/                  # 所有可安装组件，一个目录一个组件
│   └── gwf/                     # 组件 1：Git WorkTree Flow
│       ├── manifest.json        # 声明：技能目录 / 命令 / gitignore / git config / 依赖
│       ├── README.md
│       ├── references/          # 细则库
│       ├── scripts/             # gwf 引擎
│       └── skills/              # 本组技能（每个子目录含 SKILL.md）
│           ├── git-worktree-flow/
│           ├── gwf-init/ gwf-new/ gwf-scan/ gwf-sync/ gwf-archive/
└── README.md
```

新增组件（技能组、MCP、工具）时**只加一个目录 + `manifest.json`**，安装器不用改。

### manifest.json 字段

| 字段 | 说明 |
| --- | --- |
| `name` / `display` / `version` | 组件标识与展示 |
| `kind` | `skills`（安装器原生处理）；其它类型（如 `mcp`）走 `hook` |
| `skills.dir` | 技能所在目录，下面的每个含 `SKILL.md` 的子目录会被链到 `~/.agents/skills/` |
| `bin[]` | 要暴露的命令：`name` + `posix`/`windows` 入口文件 |
| `gitignore[]` | 合并进全局 gitignore 的规则 |
| `git_config{}` | 要设置的全局 git 配置 |
| `requires[]` | 依赖命令，缺失则跳过该组件并报错 |
| `hook` | 组件自定义安装脚本（`.sh` / `.ps1` / `.py`），用于 MCP 配置、工具安装等 |
| `check` | 安装后自检命令 |

### 未来的组件怎么放

```text
components/
├── gwf/                 # 技能组（kind=skills）
├── mcp-xxx/             # MCP 配置（kind=mcp + hook）
└── tools-xxx/           # 命令行工具（kind=tool + hook）
```

例如 MCP 组件：`manifest.json` 写 `"kind": "mcp"` 和 `"hook": "install.sh"`，hook 里调用各客户端 CLI 完成注册；安装器负责发现、依赖检查、失败汇报和 dry-run。

## 安装

```bash
git clone <你的仓库地址> ~/github/MyAgentConfig
cd ~/github/MyAgentConfig
./install.sh                 # macOS / Linux：装全部组件
./install.sh --list          # 看有哪些组件
./install.sh --only gwf      # 只装某个组件
./install.sh --dry-run       # 只打印计划，不落盘
./install.sh --uninstall     # 移除本仓库装过的链接（不动全局 git 配置）
```

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1              # Windows
powershell -ExecutionPolicy Bypass -File .\install.ps1 --only gwf
```

安装器做的事（全部由 manifest 驱动）：

1. 扫描 `components/*/manifest.json`，检查依赖命令；
2. 把每个技能目录链到 `~/.agents/skills/`（Windows 用 junction 兜底）；
3. 链接命令入口到 `~/.local/bin`（Windows 到 `~/.gwf/bin` 并加入用户 PATH）；
4. 合并 `gitignore` 规则到全局 `core.excludesfile`、设置 `git_config`；
5. 跑组件 `hook`（如有）、执行 `check` 自检、输出汇总。

换机器重跑一次；仓库更新后 `git pull` 即可（符号链接指向仓库内容，自动生效）。

## 现有组件

| 组件 | 说明 |
| --- | --- |
| [`gwf`](components/gwf/README.md) | **GWF = Git WorkTree Flow**：纯 worktree 多需求并行开发 + fork 上游同步治理。6 个一句话技能 + `gwf` 命令 |

### gwf 一句话速查

| 你要做的事 | 对 Agent 说 | 命令 |
| --- | --- | --- |
| 整理成 worktree 布局 | "把这个仓库初始化成 worktree 布局" | `gwf init <url> <dir> --fork <fork>` |
| 开新需求 | "开个需求：登录改造，只改 auth 模块" | `gwf new login "只改 auth 模块"` |
| 看状态 / 查冲突 | "看下各分支会不会撞车" | `gwf status` / `gwf scan` |
| 同步官方代码 | "同步官方" | `gwf sync --all` |
| 合入并清理 | "这个需求做完了，合入并清理" | `gwf archive feat-login --merge` |

用户不需要补充"更新条件/更新要求"——审计顺序、裁决矩阵、清理清单、验证阶梯、单调递减验收都在技能正文里。

## 设计参考

- 技能组织方式：[mattpocock/skills](https://github.com/mattpocock/skills)——每个能力一个短技能、技能名即命令、正文自带方法论（`grill-me` / `grill-with-docs` 那套），而不是写一个什么都管的巨型技能。
- 补丁管理方法：Debian DEP-3 补丁标记规范与 RPM patch 栈实践——补丁分类（forwarded / backport / local-only / pending-drop）、官方优先、改动量单调递减。

## 兼容性

- 平台：macOS / Linux / Windows（安装器与 gwf 引擎均为纯 Python 3 标准库，无第三方依赖）
- 语言：与项目语言无关（Rust / Go / Java / Kotlin / C++ / Python / Node / Swift，验证命令自动探测，可手改 `.gwf.json`）
- Git：需要 `git worktree`（2.5+，推荐 2.30+）
