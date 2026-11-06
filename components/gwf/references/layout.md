# 纯 Worktree 布局细则

## 目标结构

```text
my-project/
├── .git/            # 完整 Git 数据库（bare 状态，根目录即仓库本体）
├── .gwf.json        # 项目事实配置（本地生成，不入库）
├── main/            # 主干工作树（分支 main/master）
├── feat-login/      # 需求工作树 1
└── feat-pay/        # 需求工作树 2
```

根目录可包含 `.git/`、`.gwf.json`、`AGENTS.md`、Git 登记的工作树，以及 `.gwf.json` 的 `protected_dirs` 登记的受保护普通目录。工作树由 Git 登记确认，不以目录名判断。

## 受保护目录与资源工作树

在 `.gwf.json` 中按实际情况配置相对容器根的路径：

```json
{
  "protected_dirs": ["runtime"],
  "resource_worktrees": ["data"]
}
```

`protected_dirs` 是普通目录；`resource_worktrees` 必须对应 Git 已登记的工作树，不参与源码同步、归档或碰撞统计。无共同祖先的工作树也不会参与源码统计。配置须合并到已有配置，保留主干和远端设置。`gwf status`、`gwf scan`、`gwf doctor` 和 `gwf config` 仅读取；缺少配置时在内存探测，`gwf config init` 显式写配置，`gwf doctor --repair` 显式设置全局忽略与 rerere。

扫描统计特性工作树的已提交差异、暂存、未暂存及未跟踪路径，并将主工作树的未提交路径纳入碰撞；忽略路径单独计数，不假定未跟踪文件是产物。归档时将根目录的 `worktree.md` 按 SHA-256 保存到 Git 公共管理区的私密 `gwf-archive/`，校验后清理；其他未跟踪文件必须先保全并清理。其他忽略文件默认也会阻止归档，`--force` 可在确认后移除它们和已跟踪改动。

## 为什么根目录保持 bare

两个方案的区别：

| 做法 | 结果 |
| --- | --- |
| `git clone --bare` 后 `git config core.bare false` | 根目录本身被当成工作区（分支 main 已在此检出），`git worktree add main` 会报 `'main' is already used by worktree`；且根目录里的文件会被视为"全部删除" |
| `git clone --bare` 后**保持 bare**，用 `git --git-dir=.git worktree add` | 根目录不是工作区，只有各分支目录；`git worktree list` 第一行是 `(bare)` 条目 |

因此初始化时**不要**设 `core.bare false`。

## 初始化（等价原生命令）

```bash
mkdir my-project && cd my-project
git clone --bare <upstream-url> .git
git --git-dir=.git remote rename origin upstream
git --git-dir=.git config remote.upstream.fetch '+refs/heads/*:refs/remotes/upstream/*'
git --git-dir=.git fetch --no-tags upstream
git --git-dir=.git worktree add main main          # 目录名 = 分支名
# 需要推自己的改动：
git --git-dir=.git remote add origin <fork-url>
git --git-dir=.git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
```

远端约定：`upstream` = 官方，`origin` = 个人 fork。

## 旧仓迁移（已有普通 clone）

首选一键整改（工作区干净时直接跑，`--force` 可带未提交改动，冲突副本会归档）：

```bash
cd existing-project
gwf migrate
```

它等价于下面这套原生命令：

```bash
cd existing-project
git status --porcelain              # 必须干净
git config core.bare true           # 根目录退化为仓库本体，不再是工作区
git worktree add <主分支> <主分支>   # 重建工作区到 ./<主分支>/
# 3) 把根目录剩余的未跟踪/被忽略内容搬进 ./<主分支>/，保留 .git/、.gwf.json、各工作树及已登记的受保护目录
```

迁移前务必确认：未提交改动已提交或 stash；`.gitignore` 未把源码忽略掉。
`core.bare true` 与 `worktree add` 必须成对执行：漏掉后者会让仓库卡在"没有工作树"的状态。

## 从任意子目录定位项目根

```bash
git rev-parse --path-format=absolute --git-common-dir   # → <root>/.git
```

其父目录即项目根。`gwf` 内部用同一条命令，因此在 `main/`、`feat-x/` 或根目录执行结果一致。

## 跨平台差异

| 事项 | macOS / Linux | Windows |
| --- | --- | --- |
| 全局忽略文件 | `~/.gitignore_global` | `%USERPROFILE%\.gitignore_global` |
| 路径分隔符 | `/` | `\`（Python `pathlib` 已处理） |
| 软链 skill | `ln -snf` | `New-Item -ItemType SymbolicLink`（需开发者模式或管理员） |
| 脚本入口 | `gwf`（bash 包装） | `gwf.cmd`（或 `python gwf.py`） |
| 需要 `comm`/`<(...)` 的命令 | 可用 | **不可用**，改用 `gwf scan`（纯 Python 集合运算） |

## 常见问题

**Q：`git worktree add` 报 "already checked out"**
A：该分支已被某个工作树检出。`git worktree list` 查位置，或换分支名。

**Q：根目录 `git status` 报一堆删除**
A：说明被设成了 `core.bare false`。改回 `git --git-dir=.git config core.bare true`，并把根目录的散落文件移进 `main/`。

**Q：`worktree.md` 或 `.notes/` 出现在 `git status` 里**
A：全局忽略没生效。`gwf doctor` 检查，或手动：
```bash
git config --global core.excludesfile ~/.gitignore_global
echo -e "worktree.md\n.notes/" >> ~/.gitignore_global
```

**Q：磁盘占太多**
A：每个工作树都是完整文件树。需求完成后及时 `gwf archive`；不要为同一需求开多个工作树。
