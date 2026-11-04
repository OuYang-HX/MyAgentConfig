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
│   ├── gwf/                     # 组件 1：Git WorkTree Flow
│   │   ├── manifest.json        # 声明：技能目录 / 命令 / gitignore / git config / 依赖
│   │   ├── README.md
│   │   ├── references/          # 细则库
│   │   ├── scripts/             # gwf 引擎
│   │   └── skills/              # 本组技能（每个子目录含 SKILL.md）
│   │       ├── git-worktree-flow/
│   │       └── gwf-init/ gwf-new/ gwf-scan/ gwf-sync/ gwf-archive/ gwf-release/
│   └── commit-reorg/            # 组件 2：Git Commit Reorg
│       ├── manifest.json
│       ├── README.md
│       └── skills/
│           └── git-commit-reorg/
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

## 安装：**建链接，不复制**

克隆之后**只做一件事**：把这些组件**软链接**到本机的 `~/.agents/skills/`（家目录下的 `.agents/skills`）。
安装器**永不复制文件**——复制会让本机改动与仓库脱钩，之后想同步只能手工比对拷贝。

```bash
git clone git@github.com:OuYang-HX/MyAgentConfig.git ~/github/MyAgentConfig
cd ~/github/MyAgentConfig
./install.sh                 # macOS / Linux：链接全部组件
```

```powershell
git clone git@github.com:OuYang-HX/MyAgentConfig.git $env:USERPROFILE\github\MyAgentConfig
cd $env:USERPROFILE\github\MyAgentConfig
powershell -ExecutionPolicy Bypass -File .\install.ps1      # Windows
```

安装后的实际形态（`~/.agents/skills/` 里**全是链接**）：

```text
~/.agents/skills/
├── git-worktree-flow -> ~/github/MyAgentConfig/components/gwf/skills/git-worktree-flow
├── gwf-init          -> ~/github/MyAgentConfig/components/gwf/skills/gwf-init
├── gwf-sync          -> ~/github/MyAgentConfig/components/gwf/skills/gwf-sync
└── ...
~/.local/bin/gwf      -> ~/github/MyAgentConfig/components/gwf/scripts/gwf
```

### 常用命令

```bash
./install.sh --list          # 看有哪些组件
./install.sh --only gwf      # 只装/重装某个组件
./install.sh --status        # 检查：是否都是链接？有没有被复制过？
./install.sh --dry-run       # 只打印计划，不落盘
./install.sh --uninstall     # 移除本仓库装过的链接（不动全局 git 配置）
```

### 安装器做的事（全部由 manifest 驱动）

1. 扫描 `components/*/manifest.json`，检查依赖命令；
2. 把**每个技能目录链接**到 `~/.agents/skills/`（Windows 符号链接不可用时退化为**目录联接 junction**，仍是链接，不是复制）；
3. **链接**命令入口到 `~/.local/bin`（Windows 在 `~/.gwf/bin` 生成指向仓库路径的 `gwf.cmd` 并加入用户 PATH）；
4. 合并 `gitignore` 规则到全局 `core.excludesfile`、设置 `git_config`；
5. 跑组件 `hook`（如有）、执行 `check` 自检、输出汇总。

### 日常同步工作流（这就是要链接而不是复制的原因）

| 场景 | 做法 |
| --- | --- |
| 在任意机器上改技能 | **直接改仓库里的文件**（`components/**`）；`~/.agents/skills/` 里看到的就是同一份文件（链接），改完立即可用 |
| 让其它机器生效 | 本机 `git commit && git push`；其它机器 `git pull` 即生效，**不用重装** |
| 新增组件/技能目录 | 其它机器 `git pull` 后跑一次 `./install.sh`（新增目录需要新建链接） |
| 换新机器 | `git clone` + `./install.sh` 一次搞定 |

> 也可以直接编辑 `~/.agents/skills/gwf-sync/SKILL.md`：它解析后就是仓库里的文件，改完在仓库里提交即可。但**不要**在这些路径下用"另存/复制"的方式替换文件。

### 排查

```bash
./install.sh --status       # 逐项报告：链接正常 / 未安装 / 是真实目录（复制安装）
```

- **提示"真实目录（复制安装）"**：说明之前是复制安装。删掉目标目录再重装即可：
  ```bash
  rm -rf ~/.agents/skills/gwf-sync      # 只删这一个
  cd ~/github/MyAgentConfig && ./install.sh
  ```
- **Windows 建链接失败**：打开「设置 → 开发者模式」（或管理员运行 PowerShell）后重跑；安装器会优先用符号链接，失败自动退化为目录联接。
- **路径换了**（仓库搬家）：重新跑 `./install.sh` 重建全部链接。

## 现有组件

| 组件 | 说明 |
| --- | --- |
| [`gwf`](components/gwf/README.md) | **GWF = Git WorkTree Flow**：纯 worktree 多需求并行开发 + fork 上游同步治理 + 定制产物发版交付。7 个一句话技能 + `gwf` 命令 |
| [`commit-reorg`](components/commit-reorg/README.md) | **Git Commit Reorg**：提交历史重排方法论与执行技能（plan-first 门禁、双备份+物理归档、行数预算、树等价验证）。1 个技能 |

### gwf 一句话速查

| 你要做的事 | 对 Agent 说 | 命令 |
| --- | --- | --- |
| 整理成 worktree 布局 | "把这个仓库初始化成 worktree 布局" | `gwf init <url> <dir> --fork <fork>` |
| 开新需求 | "开个需求：登录改造，只改 auth 模块" | `gwf new login "只改 auth 模块"` |
| 看状态 / 查冲突 | "看下各分支会不会撞车" | `gwf status` / `gwf scan` |
| 同步官方代码 | "同步官方" | `gwf sync --all` |
| 合入并清理 | "这个需求做完了，合入并清理" | `gwf archive feat-login --merge` |
| 发版交付 | "打一版交付" | 按 `gwf-release`：版本→打包→产物+sha256→交付→装机→`--force-with-lease` |

用户不需要补充"更新条件/更新要求"——审计顺序、裁决矩阵、清理清单、验证阶梯、单调递减验收都在技能正文里。

## 设计参考

- 技能组织方式：[mattpocock/skills](https://github.com/mattpocock/skills)——每个能力一个短技能、技能名即命令、正文自带方法论（`grill-me` / `grill-with-docs` 那套），而不是写一个什么都管的巨型技能。
- 补丁管理方法：Debian DEP-3 补丁标记规范与 RPM patch 栈实践——补丁分类（forwarded / backport / local-only / pending-drop）、官方优先、改动量单调递减。

## 兼容性

- 平台：macOS / Linux / Windows（安装器与 gwf 引擎均为纯 Python 3 标准库，无第三方依赖）
- 语言：与项目语言无关（Rust / Go / Java / Kotlin / C++ / Python / Node / Swift，验证命令自动探测，可手改 `.gwf.json`）
- Git：需要 `git worktree`（2.5+，推荐 2.30+）
