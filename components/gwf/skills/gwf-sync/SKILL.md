---
name: gwf-sync
description: 一键把上游官方代码同步进各 worktree：自动 fetch 官方、快进主干、审计上游是否已实现我们的自定义功能、按"官方优先"裁决删减或按新结构重写、连带清理死资产、核验自定义增量单调递减并跑验证。用户说"同步官方/更新 upstream/拉取上游最新/官方发版了/把 feat-x rebase 到最新/和官方对齐"时使用，不需要再补充任何更新条件。
---

# gwf-sync · 一键同步官方代码

## 一句话触发
> "同步官方" / "官方发版了，对齐一下"

## 一键命令

```bash
gwf sync --all                # 所有特性工作树依次同步（先审计，再 rebase）
gwf sync feat-login          # 只同步一个
gwf sync --all --dry-run     # 只看审计报告，不动手（有风险时先跑这个）
gwf sync --all --verify      # 同步后顺带跑 .gwf.json 里的 check/test
gwf sync --all --rebase-main # 主干也有下游提交时，把主干一起变基到官方
```

退出码：`0` 全部完成；`2` 有工作树停在冲突中待裁决。

## 它替你做的决定（所以不用你说条件）

1. **只取命名引用**：`git fetch --no-tags upstream +refs/heads/<main>:refs/remotes/upstream/<main>`（不用 `fetch --all`，避免个人分支混进官方命名空间）。
2. **主干优先快进**：`merge --ff-only upstream/main`；主干有下游提交无法快进时**只警告不擅自变基**（要不要动主干是另一件事，得显式 `--rebase-main`）。
3. **同步前审计**（这是关键，冲突不是随机出现的）：
   - 我们有几个提交、改了几个文件；
   - 上游这段时间新增多少提交；
   - **上游动过我们哪些文件**（`git log <base>..main -- <我们的文件>`）——这里才是冲突高发区。
4. **rebace 用 `--empty=drop`**：上游已实现导致补丁变空的提交自动丢弃，并打印 "dropping …" 证据。
5. **单调递减核验**：同步前后各算一次 `git diff --shortstat main..HEAD`，变大就警告"可能在重复实现上游能力"。
6. **冲突不自动 abort**：停止并列出冲突文件 + 裁决顺序，把决定权留给人/Agent。

## 审计输出（示例）

```text
工作树 feat-login（分支 feat/login）
  我们的提交        : 1 个
  我们的改动文件    : 2 个
  上游新增提交      : 1 个
  上游动过我们的文件: 1 个提交   <-- 冲突高发区
      f87c1b4 upstream: refactor main entry + docs
  同步前增量        : 3 文件 / 4 行   (单调递减基线)
```

## 裁决矩阵（冲突时按这个顺序判）

| 上游情况 | 判断依据 | 动作 |
| --- | --- | --- |
| **完全覆盖**（已原生实现同功能） | `worktree.md` 判据命中；上游提交说明/PR 对应 | 丢弃我方提交（`drop` / `rebase --skip`），并清理配套资产 |
| **部分覆盖** | 上游有了框架，但缺我们的定制行为 | 保留官方代码，只补差异部分，单独提交说明 |
| **未覆盖但结构变了**（文件搬家、类/接口重构） | 冲突集中在上游重构过的块 | **以上游新结构为基底重写**，不留死路径、不改名硬塞 |
| **两侧各自新增** | 不同位置（依赖表、路由表、import） | 两边都保留，合并成一条 |
| **锁文件冲突** | `Cargo.lock` / `go.sum` / `pom.xml` / `CMakeLists.txt` / `pnpm-lock.yaml` 等 | `git checkout --theirs <lock>` 取上游版本，**变基完成后**用项目工具重新生成；绝不手工逐行解 |
| **上游政策/门禁测试拦我们的实现** | CI/测试规则变了 | 按上游认可口径改写实现，不改测试、不加 disable |

## 删除功能后的连带清理（最容易漏）

删 commit ≠ 删实现。逐项核对：

- [ ] 配套资源：自定义字体/图标/图片/模板/示例数据
- [ ] 构建钩子：CMake 脚本、Maven/Gradle 插件、Cargo feature 开关、Vite/Babel 插件、构建脚本片段
- [ ] 配置与声明：默认配置项、环境变量、类型定义（`.d.ts` / `.pyi` / header）、导出符号
- [ ] 文档与 i18n：README 章节、翻译条目、帮助文本
- [ ] 测试夹具：只服务于该功能的测试数据、mock

判据（两条都要满足）：

```bash
git grep -n "<旧符号|旧文件名>" -- <源码目录> <脚本目录>   # 为空
git diff --stat <main>..HEAD -- <曾改过的文件>            # 为空 = 完全采用上游
```

## 冲突后的操作（rebase 停在中间时）

```bash
git status                     # 看冲突文件
# 按裁决矩阵编辑/取版本
git add -A
git rebase --continue          # 继续；补丁变空会自动丢弃
git rebase --abort             # 完全放弃本次同步，回到同步前
```

不要用 `--skip` 赌运气：跳过前先确认该提交对应的功能上游确实有了。

## 验收清单（每次同步都要给证据）

- [ ] `gwf status`：所有工作树 `behind = 0`
- [ ] `git diff --stat <main>..HEAD`：文件数 / 行数 **≤ 同步前**
- [ ] 变空被丢弃的提交已逐条确认"上游确实实现了"
- [ ] 连带清理判据命令输出为空
- [ ] 验证命令 exit 0（`gwf sync --verify` 或手动跑 `.gwf.json` 的 `verify`）
- [ ] `worktree.md` 第 3 节补一行：本轮哪条增量被官方覆盖、何时删除
- [ ] 台账更新：上游基线 SHA、本轮删了哪些补丁、剩余增量多少

## 报告模板

```markdown
## 同步 <date>：upstream <old-sha>..<new-sha>（+N 提交）
| 工作树 | 我们的提交 | 上游动过的文件 | 处置 | 增量变化 |
| --- | --- | --- | --- | --- |
| feat-login | 2 | src/auth/handler.c | 上游已实现鉴权 → 删 1 条提交 + 清理配置 | 3文件/40行 → 2文件/25行 |
验证：check exit 0，test 128 passed。
```

## 没有 CLI 时（等价原生步骤）

```bash
cd <根>/main
git fetch --no-tags upstream +refs/heads/main:refs/remotes/upstream/main
git merge --ff-only upstream/main
cd ../feat-login
mb=$(git merge-base main HEAD)
git log --oneline $mb..main -- $(git diff --name-only $mb..HEAD)   # 审计：上游动过我们的文件
git diff --shortstat main..HEAD                                    # 同步前增量
git rebase --empty=drop main
git diff --shortstat main..HEAD                                    # 同步后增量，必须不变大
```

## 反模式

- 冲突时"两边都留一份"图省事 → 两套实现并存，下一轮同步继续冲突。
- 为了让 rebase 通过而 `git checkout --ours` 整体保留我方、或关掉门禁。
- 锁文件手工逐行合并、或用 `--lockfile-only` 重解（偷改依赖版本）。
- 同步期间在脏工作树上强行操作。
- 只删 commit 不清理资产，留下死代码和构建钩子。
- 没有审计报告就开始 rebase（不知道上游动过哪些文件，等于盲改）。
