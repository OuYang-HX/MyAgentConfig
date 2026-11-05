---
name: gwf-init
description: 一键把一个仓库整理成"纯 Worktree 拓扑"（根目录只有 .git 和各分支目录），或迁移已有的普通仓库。用户说"初始化这个仓库/第一次拉这个 fork/帮我整理成 worktree 布局/加个远端"时使用。自动配置全局忽略 worktree.md、探测技术栈与验证命令、生成 .gwf.json。
---

# gwf-init · 一键建仓 / 迁移 / 环境就绪

## 一句话触发
> "把这个仓库初始化成 worktree 布局" / "第一次拉这个 fork"

## 一键命令

```bash
# 全新克隆（官方仓 + 可选个人 fork）
gwf init <官方仓库URL> [目录名] [--fork <个人fork URL>]

# 已有普通克隆（扁平仓库）一键就地整改为纯 worktree 拓扑（秒级执行）
gwf migrate

# 环境体检（换机器新接入先跑这个）
gwf doctor
```

CLI 不可用时，Agent 按下面的原生步骤执行（等价逻辑，跨平台通用）：

```bash
mkdir my-project && cd my-project
git clone --bare <upstream-url> .git
git --git-dir=.git remote rename origin upstream
git --git-dir=.git config remote.upstream.fetch '+refs/heads/*:refs/remotes/upstream/*'
git --git-dir=.git fetch --no-tags upstream
git --git-dir=.git worktree add <主分支名> <主分支名>
# 若需要推自己的改动：
git --git-dir=.git remote add origin <fork-url>
```

## 它替你决定的事（不用你说）

1. 根目录保持 **bare** 状态（`.git` 是仓库本体），因此根目录下**不会**出现幽灵工作区或一堆被"删除"的文件。
2. 远端命名统一：`upstream` = 官方，`origin` = 个人 fork。
3. 主干检出到 `./<主分支名>/`，目录名与分支名一致（`main/`、`master/`）。
4. 全局 `core.excludesfile` 写入 `worktree.md` / `worktree-*.md` / `.gwf.json`，并开启 `rerere`（记住冲突解法，重复变基不再手工解）。
5. 扫描主干根目录的标记文件（`Cargo.toml` / `go.mod` / `pom.xml` / `build.gradle*` / `CMakeLists.txt` / `pyproject.toml` / `package.json`）自动推断生态与验证命令，写入 `.gwf.json`。

## 目标结构（验收）

```text
my-project/
├── .git/          # 完整 Git 数据库（bare）
├── .gwf.json      # 项目事实配置（本地生成，不入库）
├── main/          # 主干工作树
└── feat-xxx/      # 各需求工作树
```

## 验收清单
- [ ] 根目录只有 `.git/`、`.gwf.json` 和分支目录（无散落源码）
- [ ] `gwf doctor` 显示 `worktree.md` 与 `.gwf.json` `已被忽略 OK`
- [ ] `gwf status` 能列出主干工作树，无报错
- [ ] `.gwf.json` 的 `main_branch` / `upstream_ref` / `verify` 与项目实际一致；不一致就手改（这是唯一需要人工确认的地方）

## 已有仓库（扁平 clone）整改或直接使用

1. **一键就地整改（推荐，秒级完成）**：
   在普通仓库根目录直接运行：
   ```bash
   gwf migrate            # 工作区必须干净
   gwf migrate --force    # 有未提交改动时继续
   ```
   它会自动将 `core.bare` 置为 `true`，把内容归位到主干工作树 `./<主分支>/` 并注册完成，无需重新克隆或建新目录搬迁。
   - 已跟踪且未修改的内容：丢弃根目录副本（内容与检出结果一致）
   - 未跟踪/被忽略的本地内容（`node_modules`、`.venv`、`worktree.md` 等）：整目录搬入主干工作树
   - 与检出内容不一致的副本（`--force` 下的未提交修改等）：归档到 `.gwf-migrate-backup-<时间戳>/`，**不覆盖任何一侧**
   - submodule（index 中 mode 160000）：**不搬移、不递归**（其 `.git` 记录的是相对旧位置的 gitdir，搬了必失效）；干净的直接移除，有本地改动的整目录归档，迁移后在新主干工作树执行 `git submodule update --init --recursive` 复原
   - `git worktree add` 失败会自动回滚 `core.bare`，不会把仓库卡成无工作树的 bare 状态

2. **不整改直接使用**：
   普通 clone 的仓库**也可以直接用**：`gwf sync` 会自动识别扁平布局，把当前分支直接变基到官方。

3. **CLI 不可用时的原生手动步骤**：
```bash
git status --porcelain            # 必须干净
cd ..
mkdir <新目录>
mv <旧目录>/.git <新目录>/.git      # 只搬 Git 数据库
cd <新目录>
git --git-dir=.git worktree add <主分支> <主分支>   # 重建工作区
```

## 注意
- 迁移**已存在的普通仓库**前优先提交或 stash 未提交改动；确实要带改动迁移时用 `--force`，冲突副本会归档而不是覆盖。
- 不要 `git config core.bare false`（会让根目录变成工作区，`worktree add` 会因"分支已被检出"失败）。
- 细节见 `../../references/layout.md`。
