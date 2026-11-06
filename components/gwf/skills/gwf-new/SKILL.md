---
name: gwf-new
description: 一键开新需求：从最新主干建独立 worktree，并自动生成需求台账 worktree.md（含目标、改动范围、上游覆盖判据、验证方式）。用户说"开个需求/做新功能/建个分支/我要改 xxx/新建一个工作区/加一个特性"时使用，不需要再补充任何流程条件。
---

# gwf-new · 一键开需求

## 一句话触发
> "开个需求：<名字>，目标是 <一句话>"

## 一键命令

```bash
gwf new <需求名> "<一句话目标>"
# 例：
gwf new login "支持企业微信扫码登录，只改 auth 模块"
gwf feat-pay "支付通道对接"
```

产物：
- 目录 `./feat-login/`（分支 `feat/login`），基线 = 最新主干
- `./feat-login/worktree.md`（自动生成，全局 gitignore 已排除，不会入库）

## 它替你决定的事（不用你说）

1. 先更新主干：有 `upstream_ref` 且可快进时 `merge --ff-only`；主干有下游提交则警告并按现有主干创建。
2. 命名规范化：`login` → 目录 `feat-login`、分支 `feat/login`；已有 `fix-`/`chore-` 前缀则保留。
3. 需求台账四段结构：目标 / 改动范围 / **上游覆盖判据**（DEP-3 风格，可执行判据）/ 验证方式（来自 `.gwf.json` 的 `verify`）。
4. 不污染其它工作树：每个需求独立目录，依赖、构建产物互不干扰。

## 扁平仓库提示
若执行报错提示`当前是扁平仓库（根目录即工作区）`，说明仓库尚未整改为 worktree 拓扑。
先在仓库根目录执行就地秒级迁移：
```bash
gwf migrate
```
迁移完成后重新执行 `gwf new` 即可。

## 生成的 worktree.md 模板

```markdown
# 需求台账：<名字>
- 分支: feat/<name> | 工作树: feat-<name>/ | 基线: main (<sha>) | 技术栈: <eco>
## 1. 目标（一句话）
<用户给的目标>
## 2. 改动范围
## 3. 上游追踪与覆盖判据（DEP-3）
| 本需求的增量入口 | 判定上游是否已覆盖 | 处置 |
## 4. 验证方式
## 5. 冲突记录
```

后续开发中**始终更新这个文件**：改动范围变化要改，新增"判据"要加行，同步上游后要记一行结论（哪条增量被官方覆盖、已删除）。

## 没有 CLI 时

```bash
cd <项目根>
cd main && git merge --ff-only <upstream_ref> && cd ..
git worktree add -b feat/<name> ./feat-<name> main
# 然后手写 ./feat-<name>/worktree.md（内容同上面的模板）
```

## 验收清单
- [ ] 容器根含 `.git/`、`.gwf.json`、可选 `AGENTS.md`、Git 登记的工作树及配置登记的受保护普通目录
- [ ] `gwf status` 中能看到新工作树，`behind = 0`
- [ ] 新目录内 `git status --porcelain` 为空（说明 `worktree.md` 确实被全局忽略）
- [ ] `worktree.md` 第 3 节至少有一行可执行的覆盖判据（否则后续同步时无法判断该不该删）

## 反模式
- 不要在主工作树里直接 `git checkout -b`（会打断其它需求的工作区）。
- 不要在根目录创建任何源码文件。
- 细节见 `../../references/templates.md`。
