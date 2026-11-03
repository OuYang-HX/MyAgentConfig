# 模板与配置

## 1. `worktree.md`（每个工作树一份，不入库）

由 `gwf new` 生成，开发中持续更新。

```markdown
# 需求台账：<名字>

- **分支**: feat/<name>
- **工作树**: feat-<name>/
- **基线**: main (<sha>)
- **技术栈**: rust / go / maven / gradle / cmake / python / node
- **状态**: 进行中 | 已对齐 | 待合入 | 已归档
- **创建**: YYYY-MM-DD HH:mm

## 1. 目标（一句话）

## 2. 改动范围
- 主要模块/文件：
- 明确不改动的部分：

## 3. 上游追踪与覆盖判据（DEP-3）
| 本需求的增量入口 | 判定上游是否已覆盖（可执行判据） | 处置 |
| --- | --- | --- |
| 新配置项 `foo.bar` | `git grep -n "foo.bar" upstream/main -- conf/` | 上游已有 → 删本增量 |

## 4. 验证方式（在本工作树内执行）
- `<check 命令>`
- `<test 命令>`

## 5. 冲突记录
- 与并行工作树重叠文件：
- 每轮同步结论（日期 / 上游 SHA / 删了哪条 / 增量变化）：
```

**判据列必须可执行**：一条能直接复制运行的 `git grep` / `git log`，而不是"看情况"。

## 2. `.gwf.json`（项目根，本地生成，不入库）

```json
{
  "_doc": "由 gwf config init 自动生成；改这里即可，无需每次向 Agent 复述项目事实。",
  "main_branch": "main",
  "main_worktree": "main",
  "upstream_remote": "upstream",
  "origin_remote": "origin",
  "upstream_ref": "upstream/main",
  "patch_tags": ["[fork]", "[me]", "[custom]"],
  "verify": {
    "check": "cargo check",
    "test": "cargo test",
    "lint": "cargo clippy -- -D warnings",
    "build": "cargo build"
  },
  "ecosystem": "rust",
  "lockfiles": ["Cargo.lock"],
  "release": {
    "version_source": "package.json#version",
    "build_number_source": "app.json#android.versionCode",
    "build_label": "me",
    "package": "pnpm build",
    "artifact_glob": "dist/*.zip",
    "install": "",
    "deliver_dir": "~/Desktop"
  }
}
```

| 字段 | 作用 | 什么时候手改 |
| --- | --- | --- |
| `main_branch` | 主干分支名 | 主干不叫 main/master |
| `main_worktree` | 主干所在目录名 | 目录名与分支名不一致 |
| `upstream_remote` / `origin_remote` | 官方 / 个人 fork 的远端名 | 远端命名不同（如 `official`） |
| `upstream_ref` | 官方基线引用 | 官方分支不叫 main |
| `verify` | 验证命令 | 探测不准（多模块、用 make 包装、需要容器） |
| `lockfiles` | 锁文件清单 | 用了 conan/vcpkg/uv 等非默认方案 |
| `backup_push` | `true` 时同步前备份分支同时推个人远端 | 需要跨机器留档时 |
| `patch_tags` | 自定义提交前缀，`gwf sync` 审计时按前缀统计（`[fork] 3 / 未标记 1`） | 有自己的提交规范 |
| `release` | 发版打包/交付信息 | 需要定制产物交付时（见 `release.md`） |

放在项目根（`.git/` 同级），**不在任何工作树内**，所以不会被 git 跟踪，也不会污染 `git diff upstream/main..HEAD` 的单调递减统计。

## 3. 同步报告模板

```markdown
## 同步 <日期>：upstream <old-sha>..<new-sha>（+N 提交）

| 工作树 | 我们的提交 | 上游动过的文件 | 处置 | 增量变化 |
| --- | --- | --- | --- | --- |
| feat-login | 2 | src/auth/handler.c | 上游已实现鉴权 → 删 1 提交 + 清理配置项 | 3文件/40行 → 2文件/25行 |

验证：check exit 0；test 128 passed。
遗留：feat-pay 因 <原因> 暂停在冲突，待裁决。
```

## 4. 提交信息前缀建议

```text
[fork] feat: ...            私有新功能
[fork][backport] fix: ...   借用上游修复（上游版本包含后可删）
[fork][temp] ...            等上游实现的临时兜底（上游实现后删）
[fork][local-only] ...      永不上游，长期保留（应做成可插拔）
```

`patch_tags` 与这些前缀对应，`gwf sync` 与 Agent 据此识别哪些提交该删。
