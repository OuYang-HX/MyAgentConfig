---
name: gwf-scan
description: 一键查看所有 worktree 状态并预警并行分支冲突：哪个分支落后主干、哪些文件被多个需求同时修改、应该先合入谁。用户说"现在什么状态/落后多少/会不会冲突/先合谁/检查一下并行分支"时使用。
---

# gwf-scan · 一键体检：状态 + 冲突预警

## 一句话触发
> "看下现在各分支状态" / "这几个需求会不会撞车"

## 一键命令

```bash
gwf status      # 总览：每个工作树的 ahead/behind/dirty/改动文件数/最近提交
gwf scan        # 交叉比对：哪些文件被多个分支同时修改 + 谁落后主干
```

## 输出长什么样

`gwf status`：

```text
工作树             分支             ahead  behind  dirty  改动文件     HEAD  最近提交
feat-login         feat/login           1       0      0        2   4d76119  [fork] feat: wechat login
feat-pay           feat/pay             1       3      0        1   9c0775d  [fork] feat: pay channel
main               main                 0       0      0        0   f87c1b4  upstream: refactor main entry [main]
```

`gwf scan`（重叠时）：

```text
[冲突预警] 2 个文件被多个并行分支同时修改：
  - src/auth/handler.c   <- feat-login, feat-pay
  - CMakeLists.txt       <- feat-login, feat-pay
建议：先合入改动更基础的分支，再对另一个执行 gwf sync <folder>
```

## 判读规则（技能替你做的判断）

| 现象 | 含义 | 下一步 |
| --- | --- | --- |
| `behind > 0` | 主干已有新提交（可能是其它需求合入或官方更新） | 合入前先 `gwf sync <该工作树>` |
| `dirty > 0` | 有未提交改动 | 先提交/暂存，再同步（同步会拒绝脏工作树） |
| 有重叠文件 | 两个需求改同一处 | 先合"更基础"的那个；另一个随后 `gwf sync` 解决 |
| 重叠在构建/配置文件（`CMakeLists.txt`、`pom.xml`、`Cargo.toml`、`package.json`） | 多半是"两边各加一行" | 合并时两边都保留，别互相覆盖 |
| 改动文件数持续增长 | 可能在上游已有能力上造轮子 | 去 `worktree.md` 第 3 节核对判据 |

## 没有 CLI 时

```bash
git worktree list
git diff --name-only main..feat-a > /tmp/a.txt
git diff --name-only main..feat-b > /tmp/b.txt
# Windows PowerShell:
#   Compare-Object (Get-Content a.txt) (Get-Content b.txt) -IncludeEqual -ExcludeDifferent
comm -12 <(sort /tmp/a.txt) <(sort /tmp/b.txt)     # 仅 bash/zsh
git rev-list --count HEAD..main                    # 在每个工作树内查落后数
```

## 验收清单
- [ ] 每个工作树都给出了 ahead/behind/dirty
- [ ] 有重叠文件时，明确给出"先合谁"的建议
- [ ] 落后 > 0 的工作树，明确提示先 `gwf sync`
