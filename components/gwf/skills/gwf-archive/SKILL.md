---
name: gwf-archive
description: 一键收尾：把已完成的需求合入主干、推送、移除对应 worktree、删除分支并清理元数据，未合入时默认拒绝以免丢工作。用户说"合入主干/这个需求做完了/收尾/清理工作树/归档/删掉这个分支"时使用。
---

# gwf-archive · 一键合入 + 归档

## 一句话触发
> "这个需求做完了，合入并清理"

## 一键命令

```bash
gwf archive feat-login              # 已合入时才允许；未合入直接拒绝
gwf archive feat-login --merge      # 未合入时先快进合入 main，再移除
gwf archive feat-login --merge --no-push   # 合入但不推送
gwf archive feat-login --keep-branch       # 只删工作树，保留分支
```

## 它替你决定的事（安全默认）

1. **先保全需求台账**：根目录 `worktree.md` 按 SHA-256 保存到 Git 公共管理区的私密归档，再清理工作树。其他未跟踪文件始终拒绝归档；其他忽略文件和已跟踪改动默认拒绝，确认保全后可用 `--force` 删除。
2. **未合入默认拒绝**：避免"目录删了、工作没了"。
3. `--merge` 只做 **`--ff-only`**：主干已分叉时不会悄悄生成一个 merge commit，而是报错让你先 rebase。
4. **合入后二次校验** `merge-base --is-ancestor`，校验不过就不删任何东西。
5. 删完执行 `git worktree prune`，清掉失效元数据。
6. 推送失败只警告不中断（可能没网/没权限，稍后手动推）。

## 执行顺序（CLI 内部行为，便于人工复核）

```bash
# 1) 工作树干净？
cd <根>/feat-login && git status --porcelain
# 2) 是否已合入？
cd <根>/main && git merge-base --is-ancestor feat/login main
# 3) 未合入：快进合入
git merge --ff-only feat/login
# 4) 推送（有 origin 远端时）
git push origin main
# 5) 移除工作树 + 删分支 + 剪枝
cd <根>
git worktree remove ./feat-login
git branch -d feat/login
git worktree prune
```

## 归档前自检（Agent 要替用户确认）

- [ ] `gwf status` 中该工作树已跟踪与未跟踪内容均已保全且可清理
- [ ] 该工作树已 `gwf sync` 过（`behind = 0`），避免把落后代码合并进主干
- [ ] 验证命令通过（`.gwf.json` 的 `verify`）
- [ ] `worktree.md` 第 1 节目标已达成、第 3 节判据结论已记录（归档前把它整理成一行结论，别丢知识）
- [ ] 若该需求被官方吸收，确认自定义增量已删除（`git diff --stat main..HEAD` 里已看不到它）

## 归档后

- 根目录保留 Git 登记的工作树和配置登记的受保护普通目录
- `gwf status` 应只剩主干（或其它未完成需求）
- 分支删除用 `-d`（安全）；只有确知要丢时才 `-D`

## 反模式
- 未合入就 `git worktree remove --force`：工作目录被删，未合并的提交只能靠 reflog 捞。
- 用 `git merge` 制造 merge commit 覆盖主干历史（会污染后续 rebase 与单调递减统计）。
- 归档前不跑 `gwf sync`，把落后主干的分支硬合进去。
