# 上游覆盖裁决细则（DEP-3 思路）

一句话：**官方实现了 → 删我们的；官方没实现 → 按官方新结构重写；两边无关 → 都留。**

## 补丁分类（借鉴 Debian DEP-3）

给每个自定义提交或 `worktree.md` 台账行标一个状态，同步时按状态处理：

| 标签 | 含义 | 上游出现后的处置 |
| --- | --- | --- |
| `forwarded:<PR>` | 已向上游提 PR | PR 合并 → 整条删除 |
| `backport:<sha>` | 借用的上游修复 | 上游版本已含该 sha → 删除 |
| `not-needed` / `local-only` | 私有定制，上游永不接受 | 永久保留，但必须做成可插拔（独立目录/入口注入） |
| `pending-drop` | 临时兜底（等上游实现） | 上游实现后 → 删除并清理资产 |
| `origin` | 从上游摘的补丁 | 上游已有 → 删除 |

建议提交前缀：`[fork] feat: ...`、`[fork][backport] fix: ...`、`[fork][temp] ...`。

## 覆盖判定必须"成对"

只看名字出现不等于覆盖。判定要看：

1. **实现**：等价函数/类/接口/配置项是否真的存在（`git grep` 特征符号）；
2. **配套资产**：字体、图标、模板、生成物、构建钩子是否随实现一起提供；
3. **门控与接线**：是否真的被调用/被注册/被开关控制，而不是只有声明。

只有"实现 + 资产/门控"齐全，才判"完全覆盖"。

## 审计命令（同步前必跑）

```bash
mb=$(git merge-base main HEAD)

# 1) 我们的文件：哪些上游提交动过
git log --oneline $mb..main -- $(git diff --name-only $mb..HEAD)

# 2) 我们的提交（数量与主题）
git log --oneline $mb..HEAD

# 3) 上游是否已有等价符号（按台账判据替换符号）
git grep -n "<特征符号>" main -- <路径>

# 4) 上游该提交带了哪些资产
git show --stat <覆盖候选提交> | head -30

# 5) 同步前后增量（单调递减）
git diff --shortstat main..HEAD
```

## 冲突裁决矩阵

| 场景 | 动作 |
| --- | --- |
| 完全覆盖 | `git rebase --skip` 或 `drop` 该提交；随后删配套资产 |
| 部分覆盖 | 保留官方实现，只补差异；提交信息写清差异点 |
| 上游结构变了但没实现功能 | 以上游新文件/新类为基底重写，不留死路径 |
| 双方各自新增 | 合并保留（依赖表、路由表、import 各加一行） |
| 同一模块多条 import | 合并成一条，别留两条同源 import |
| 锁文件冲突 | `git checkout --theirs <lock>` 取上游，变基后项目工具重新生成 |
| 上游政策测试拦我们的实现 | 按上游口径改实现，不改测试、不加 disable |
| 上一代机械提交（锁文件、版本号、过期文档） | 丢弃，本代末尾统一生成一条 |

## 锁文件纪律

| 生态 | 锁文件 | 处置 |
| --- | --- | --- |
| Rust | `Cargo.lock` | 取上游版本；必要时 `cargo update -p <crate>` 局部更新 |
| Go | `go.sum`、`vendor/` | 取上游；`go mod tidy` 重算 |
| Java/Maven | 无锁文件，`pom.xml` 依赖区 | 冲突多为"两边各加依赖"，都保留 |
| Java/Gradle | `gradle.lockfile`、`gradle/libs.versions.toml` | 取上游后 `./gradlew dependencies --write-locks` |
| C/C++ | `CMakeLists.txt`、`conan.lock`、`vcpkg.json` | CMakeLists 冲突按"两边各加一行"合并；lock 取上游 |
| Python | `uv.lock`、`poetry.lock`、`Pipfile.lock` | 取上游后 `uv lock` / `poetry lock --no-update` |
| Node | `pnpm-lock.yaml`、`yarn.lock`、`package-lock.json` | **绝不手解**；取上游后按原包管理器重装生成 |

**绝不**用 `--lockfile-only` 重解：它按 semver 把上游钉死的版本升到更新小版本，等于偷改依赖。

## 删除配套资产清单

- 二进制/字体/图标/图片/模板/示例数据
- 内嵌 base64 模块、生成物（`*.generated.*`）
- 构建钩子：CMake 脚本、Gradle/Maven 插件、Cargo feature、Vite/Babel 插件、prebuild 脚本、bundle 校验
- CSP/权限白名单、类型声明、导出符号、默认配置、环境变量
- i18n 条目、帮助文本、README 章节
- 测试夹具、mock 数据

验收：

```bash
git grep -n "<旧符号|旧文件名>" -- <源码目录> <脚本目录>   # 空
git diff --stat main..HEAD -- <曾改过的文件>              # 空 = 完全采用上游
```

`git rm` 删除"本提交刚新增且已暂存"的文件需要 `-f`。

## 单调递减

每轮同步后：

```bash
git diff --stat upstream/main..HEAD    # 或 main..HEAD
```

文件数、行数不得比上一代更大。变大通常意味着：
- 上游已实现同类能力，我们还在维护自己的版本；
- 用拼贴方式解冲突，把两套逻辑都留下了；
- 把上游的删除操作"还原"回来了。

## 反模式

- 只看上游"提到"某个名字就判覆盖（必须核对实现 + 资产 + 门控）。
- 删了提交，留下资产、引用、构建钩子、白名单。
- 冲突时整体 `--ours` 保留我方，或关掉测试/类型门禁。
- 两套实现并存"反正能跑"。
