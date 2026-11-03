# 发版与交付细则

## 1. 版本策略

| 概念 | 取值 | 说明 |
| --- | --- | --- |
| 源码版本 | **已纳入源码的官方版本** | 不是"最新发布标签"。官方源码可能已领先发布标签，也可能落后 |
| 自定义标签 | 递增显示用（`oyhx.7`、`me.3`） | 只影响显示，不参与比较 |
| 构建号 | `versionCode` / `buildNumber` | 单调递增，且**大于设备已装包和官方包** |
| 官方基线 | upstream 提交 SHA 或源码版本 | 写进产物清单与 `worktree.md`，用于追溯 |

### 版本号比对型提醒的通病

源码版本高于最新已发布版本时（源码 `0.0.58`、已发布 `0.0.52`），上游随后以同号发布就不会触发"有新版本"提醒。两种收尾任选其一：

1. 把"已纳入源码的上游基线"（提交 SHA 或源码版本）另存进产物与清单，用它参与比较；
2. 明确接受这次漏提醒，并在提醒文案与台账里写明。

不要把它写成无条件的正确做法。

## 2. 产物命名与校验

```text
<name>-<version>-<label>-code<build>-<YYYYMMDD>-<arch>.<ext>
<name>-<version>-<label>-code<build>-<YYYYMMDD>-<arch>.<ext>.sha256
```

```bash
shasum -a 256 <artifact>     # macOS
sha256sum <artifact>         # Linux
```

体积与上一代对比：异常增大/缩小都要能解释（例如官方删除了不可达模块，体积下降属正常）。

## 3. 共享盘 / NAS 的 latest 约定

目录里**只保留一个**当前包，固定命名：

```text
<name>-latest.<ext>
<name>-latest.<ext>.sha256
<name>-latest.txt
```

`txt` 内容：版本、构建号、架构、日期、源码提交 SHA、验证结论。

更新顺序（防半成品）：

1. 写临时文件；
2. 核对摘要；
3. 原子替换 latest；
4. 清理旧包与旧校验文件（按包名核对，别误删其他应用）。

## 4. 装机核对

```bash
<installer> -r <artifact>        # 保留数据
# 包管理器核对版本 / 构建号 / 签名
# 进程 PID 安装前后一致；崩溃日志看时间戳
```

Android 例：`adb install -r`；`adb shell dumpsys package <pkg> | grep version`；`adb logcat -d | grep -E "FATAL|AndroidRuntime"`。

## 5. 推送纪律

```bash
git push --force-with-lease=<ref>:<旧SHA>
```

- 旧 SHA 在动手前就记下来；
- 不用 `--force`、不用 `--admin`、不关分支保护；
- 历史已被外部引用（发布说明、交付清单里的 SHA）时，不要重写那一段。

## 6. 同分支多工作树

同一分支被多个工作树检出时，采用"临时迁移分支 + 原子更新 ref"：

```bash
# 当前目录
git switch -c tmp/port-<date>
# ... 完成改动与验证 ...
git update-ref refs/heads/<target> <new-sha> <old-sha>   # 旧值不匹配就失败，安全
# 其它工作树：确认干净后
git reset --hard <target>
```

避免在 A 工作树里直接改 B 工作树的文件（会留下假 diff / 半更新）。

## 7. 生成型工程

prebuild / codegen / 资源生成类工程：

- 用**干净重建**（`--clean`），不要增量；
- 重建后复核注入标记：
  ```bash
  grep -c "<注入标记>" <生成文件>     # 必须 > 0
  ```
- 生成的版本号要正确（读产物而不是读配置）；
- 生成物若被 gitignore，注意它不会随 `git pull` 更新，需本机重建。

## 8. 记账模板

```markdown
## 发版 <version> (<label>) / code <build> — <YYYY-MM-DD>
- 官方基线: <upstream-sha>（已纳入源码的版本 <ver>）
- 产物: <name>-<version>-<label>-code<build>-<date>-<arch>.<ext>
- sha256: <hash>（上一代 <hash>）
- 验证: <check> exit 0；<test> N passed
- 装机: 设备 <型号>，install -r Success，版本/构建号核对一致，数据保留
- 推送: <ref> <old-sha> -> <new-sha>（--force-with-lease）
```
