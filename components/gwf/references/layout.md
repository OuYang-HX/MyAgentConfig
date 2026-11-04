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

根目录**只允许**出现 `.git/`、`.gwf.json` 和各分支目录。任何源码文件出现在根目录都算布局被污染。

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

```bash
cd existing-project
git status --porcelain          # 必须干净
# 1) 把当前分支检出到一个子目录
git worktree add ./main <当前分支>
# 2) 确认 ./main 内容正确后，删除根目录的散落文件（它们已在 main/ 中）
# 3) 根目录只留 .git/、main/、其它 worktree
```

迁移前务必确认：未提交改动已提交或 stash；`.gitignore` 未把源码忽略掉。

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
