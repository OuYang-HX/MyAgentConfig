---
name: git-worktree-flow
description: Git 纯 Worktree 多需求并行开发与 fork 上游同步的"技能集合"入口。当用户提到 worktree 布局、开新需求、建分支、看工作树状态、并行分支冲突、同步官方代码/更新 upstream、合入归档、初始化代码仓时，先用本技能路由到对应的原子技能（gwf-init / gwf-new / gwf-scan / gwf-sync / gwf-archive），每个原子技能都自带一键命令，用户不需要复述任何流程细节。
---

# git-worktree-flow · 技能集合

一个**可一键触发**的 Git 工作流技能集合。设计目标：**用户只说一句话，流程细节全部写在技能里。**

## 三层信息，各归其位（用户为什么不用描述需求）

| 层 | 存在哪里 | 解决什么 | 谁来维护 |
| --- | --- | --- | --- |
| **方法** | 各原子技能的 SKILL.md | 怎么同步、怎么裁决、怎么清理 | 本仓库维护，一次写好 |
| **项目事实** | 仓库根 `.gwf.json` | 哪个远端是官方、主分支名、验证命令、锁文件 | `gwf config init` 自动探测 |
| **任务状态** | 各 worktree 的 `worktree.md` | 需求目标、改动范围、上游判据 | `gwf new` 自动生成，随开发更新 |

→ 所以用户只需说"同步官方"或"开个需求叫 xxx"，不用再附加任何条件句。

## 路由表（说一句话就够）

| 用户的话 | 加载技能 | 一句话命令 |
| --- | --- | --- |
| "初始化/第一次拉这个仓库/改成 worktree 布局" | `gwf-init` | `gwf init <url> [dir]`（已有扁平仓用 `gwf migrate`） |
| "开个需求/做功能/建个分支/我要改 xxx" | `gwf-new` | `gwf new <名> "<一句话目标>"` |
| "现在什么状态/落后多少/会不会冲突/先合谁" | `gwf-scan` | `gwf status` / `gwf scan` |
| "同步官方/更新 upstream/拉上游最新/官方发版了/rebase 到最新/更新官方代码到我的 fork 分支" | `gwf-sync` | `gwf sync --all`（扁平仓库直接 `gwf sync`） |
| "合入主干/收尾/清理 worktree/这个需求做完了" | `gwf-archive` | `gwf archive <目录> --merge` |
| "回滚/恢复/删备份分支/我当时改了什么" | `gwf-sync`（备份子命令） | `gwf backup list/show/clean` |
| "打包/发版/出包/构建号/交付/装机/推到远端" | `gwf-release` | 按 `gwf-release` 流程（版本→打包→产物→交付→装机→推送） |

## 共用铁律（每个原子技能都遵守，此处只列，细则见 references）

1. **官方优先**：上游实现了同一功能 → 删掉自定义实现，两套并存是最大技术债。
2. **单调递减**：每次同步后 `git diff --stat <main>..HEAD` 的文件数/行数不得变大。
3. **先备份、后核对、再清理**：任何可能丢提交的操作（同步/变基）前自动建 `backup/*` 分支；
   确认原有功能没丢之后再删，绝不凭记忆判断。
4. **重写而非拼贴**：上游结构变了，就以新结构为基底重写，不留死路径。
5. **`worktree.md`、`.gwf.json` 与 `.notes/` 不进 git**：过程记录与草稿放工作树根目录 `.notes/`，任务状态写 `worktree.md`，均靠全局 `core.excludesfile` 排除。
6. **容器根布局**：保留 `.git/`、`.gwf.json`、`AGENTS.md`、Git 登记的工作树，以及 `.gwf.json` 中 `protected_dirs` 登记的受保护普通目录。
7. **不擅自动门禁**：类型错误/lint/测试按仓库规则改代码，不加 disable、不改阈值。
8. **脏工作树先问**：有未提交改动时先提交或 stash，绝不 reset 丢弃。

## references（细则，按需读取）

路径相对本技能目录；安装后技能是软链接，`../../references/` 指向组件根的细则库。

- `../../references/layout.md` — 纯 worktree 布局、初始化、旧仓迁移、跨平台差异
- `../../references/arbitration.md` — 上游覆盖裁决矩阵、死资产清理、锁文件纪律、DEP-3 标签
- `../../references/verification.md` — 跨语言验证阶梯（C++/Java/Rust/Go/Python/Node）与门禁纪律
- `../../references/release.md` — 版本策略、构建号、产物命名、latest 清单、装机与推送纪律
- `../../references/templates.md` — `worktree.md` 模板、`.gwf.json` 字段说明（含 `release` 段）

## 没有 CLI 时

所有原子技能都附了等价的原生 git 命令，逻辑与 CLI 一致，可直接照做。
