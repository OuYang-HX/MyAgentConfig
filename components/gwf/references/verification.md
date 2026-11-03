# 跨语言验证阶梯

同步 / 合入后按顺序跑，**记录 exit code 与关键数字**，不要"看起来对"。

## 通用顺序

1. 编译/类型检查（最快发现结构错位）
2. 单元测试
3. 静态检查 / lint
4. 构建产物
5. 与本次改动相关的集成/回归测试

## 各生态默认命令

命令优先取 `.gwf.json` 的 `verify` 字段（`gwf config init` 已按标记文件自动探测），下面是探测来源与手工兜底：

| 生态 | 标记文件 | check | test | lint |
| --- | --- | --- | --- | --- |
| Rust | `Cargo.toml` | `cargo check` | `cargo test` | `cargo clippy -- -D warnings` |
| Go | `go.mod` | `go vet ./...` | `go test ./...` | `gofmt -l .` |
| Java/Maven | `pom.xml` | `mvn -q -DskipTests compile` | `mvn -q test` | 按项目（checkstyle/spotbugs） |
| Java/Kotlin/Gradle | `build.gradle*`、`settings.gradle*` | `./gradlew check` | `./gradlew test` | `./gradlew lint`（Android） |
| C/C++ | `CMakeLists.txt` | `cmake --build build` | `ctest --test-dir build --output-on-failure` | clang-tidy（按项目） |
| Python | `pyproject.toml`/`requirements.txt` | `python -m compileall -q .` | `pytest -q` | `ruff check .` |
| Node | `package.json` | `npm ci` / `pnpm i --frozen-lockfile` | `npm test` / `pnpm test` | `npm run lint` |
| Swift | `Package.swift` | `swift build` | `swift test` | — |

多模块项目（Maven/Gradle/CMake 子工程）先跑受影响子模块，再跑全量。

## 门禁纪律

- 类型错误、lint、政策测试按仓库规则**改代码**；不加 `// @ts-ignore`、`# noqa`、`@SuppressWarnings`，不调阈值，不改 CI 条件。
- 工具链版本取仓库声明：`rust-toolchain.toml` / `go.mod` 的 go 版本 / `.nvmrc` / `gradle/wrapper` / `engines` / `packageManager`。本机不匹配就装对应版本，别改仓库去迁就本机。
- 依赖解析类改动（lock 文件、`pom` 依赖区）必须显式验证：`cargo build` / `go mod verify` / `mvn -o` 之类能证明"没有偷偷升级"。
- 生成型工程（codegen/prebuild）用干净重建（`--clean`），并复核生成物确实包含预期内容。

## 记录格式

```text
check : cargo check            exit 0
test  : cargo test             412 passed, 0 failed, 3 ignored
lint  : cargo clippy            exit 0
build : cargo build --release  exit 0
```

数字写进 `worktree.md` 或同步报告，方便下一轮对比（测试数骤降说明用例被误删）。
