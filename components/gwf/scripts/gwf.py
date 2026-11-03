#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gwf - Git Worktree Flow CLI

跨平台（Windows / macOS / Linux）零第三方依赖的纯 Worktree 工作流引擎。

目录形态：
    my-project/
    ├── .git/        # 完整 Git 数据库
    ├── main/        # 主干工作树
    └── feat-xxx/    # 特性工作树（每个带 worktree.md）

命令：
    gwf init <url> [dir] [--fork URL]   初始化纯 worktree 拓扑仓库
    gwf new <name> [desc]               开新需求：建 worktree + 生成 worktree.md
    gwf status                          所有工作树状态总览
    gwf scan                            并行分支冲突/重叠预警
    gwf sync [目标...] [--all]          一键同步上游官方代码（含审计与裁决提示）
    gwf archive <folder> [--merge]      合入主干并归档清理
    gwf config [init]                   查看/自动探测项目配置 (.gwf.json)
    gwf doctor                          环境体检（多机器接入时先跑这个）
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG_FILE = ".gwf.json"
DOC_FILE = "worktree.md"
VERSION = "2.2.0"


# ---------------------------------------------------------------- 基础工具

def say(msg=""):
    print(f"[gwf] {msg}")


def warn(msg):
    print(f"[gwf] 警告: {msg}")


def die(msg, code=1):
    print(f"[gwf] 错误: {msg}", file=sys.stderr)
    sys.exit(code)


def run(args, cwd=None, check=False):
    """执行 git 命令，返回 {code, out, err}。不抛异常，便于按返回码裁决。"""
    try:
        p = subprocess.Popen(
            ["git"] + args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = p.communicate()
        res = {
            "code": p.returncode,
            "out": out.decode("utf-8", "replace").strip(),
            "err": err.decode("utf-8", "replace").strip(),
        }
    except FileNotFoundError:
        die("系统中未找到 git，请先安装 Git 并确保其在 PATH 中")
    if check and res["code"] != 0:
        die("命令失败: git %s\n%s" % (" ".join(args), res["err"] or res["out"]))
    return res


def git_ok(args, cwd=None):
    return run(args, cwd=cwd)["code"] == 0


def shortstat(stat_line):
    """解析 '3 files changed, 12 insertions(+), 4 deletions(-)' 为 (files, lines)。"""
    if not stat_line:
        return (0, 0)
    files = 0
    lines = 0
    m = re.search(r"(\d+) files? changed", stat_line)
    if m:
        files = int(m.group(1))
    for m in re.finditer(r"(\d+) (?:insertions?|deletions?)", stat_line):
        lines += int(m.group(1))
    return (files, lines)


def diff_size(cwd, base, ref="HEAD"):
    res = run(["diff", "--shortstat", "%s..%s" % (base, ref)], cwd=cwd)
    return shortstat(res["out"])


def split_status(cwd):
    """把工作树状态拆成 (已跟踪改动, 未跟踪文件)。构建产物等未跟踪文件不应阻塞流程。"""
    lines = [l for l in run(["status", "--porcelain"], cwd=cwd).get("out", "").splitlines() if l.strip()]
    tracked = [l for l in lines if not l.startswith("??")]
    untracked = [l for l in lines if l.startswith("??")]
    return tracked, untracked


# ---------------------------------------------------------------- 仓库与配置

def git_common_dir():
    res = run(["rev-parse", "--path-format=absolute", "--git-common-dir"])
    if res["code"] == 0 and res["out"]:
        return Path(res["out"]).resolve()
    res = run(["rev-parse", "--git-common-dir"])
    if res["code"] != 0:
        die("当前目录不在任何 Git 仓库内")
    p = Path(res["out"])
    return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()


def project_root():
    """纯 worktree 架构下的容器根目录（.git 的父目录）。"""
    common = git_common_dir()
    return common.parent if common.name == ".git" else common


def list_worktrees(cwd=None):
    res = run(["worktree", "list", "--porcelain"], cwd=cwd)
    if res["code"] != 0:
        die("无法读取 worktree 列表（确认当前目录在 Git 仓库内）")
    blocks = []
    cur = {}
    for line in res["out"].splitlines():
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = {}
            continue
        key, _, val = line.partition(" ")
        cur[key] = val if val else True
    if cur:
        blocks.append(cur)
    items = []
    for b in blocks:
        if b.get("bare"):
            continue
        ref = b.get("branch", "")
        items.append({
            "path": Path(b.get("worktree")).resolve(),
            "branch": ref.replace("refs/heads/", "") if ref else "",
            "head": b.get("HEAD", ""),
            "detached": bool(b.get("detached")),
        })
    return items


def load_config(root):
    p = Path(root) / CONFIG_FILE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        warn("%s 解析失败(%s)，将重新探测" % (p, e))
        return None


def save_config(root, cfg):
    p = Path(root) / CONFIG_FILE
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 让 .gwf.json 永远不进 git（扁平布局下它就在工作区里，必须本地忽略）
    common = run(["rev-parse", "--git-common-dir"], cwd=root).get("out", "")
    if common:
        gitdir = Path(root) / common if not Path(common).is_absolute() else Path(common)
        exclude = Path(gitdir) / "info" / "exclude"
        try:
            content = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
            if CONFIG_FILE not in content.splitlines():
                exclude.parent.mkdir(parents=True, exist_ok=True)
                with open(exclude, "a", encoding="utf-8") as f:
                    if content and not content.endswith("\n"):
                        f.write("\n")
                    f.write("\n# gwf 项目事实配置（本地）\n" + CONFIG_FILE + "\n")
        except OSError:
            pass
    return p


ECOSYSTEM_RULES = [
    ("rust", ["Cargo.toml"], ["Cargo.lock"],
     "cargo check", "cargo test", "cargo clippy -- -D warnings", "cargo build"),
    ("go", ["go.mod"], ["go.sum"],
     "go vet ./...", "go test ./...", "gofmt -l .", "go build ./..."),
    ("maven", ["pom.xml"], [],
     "mvn -q -DskipTests compile", "mvn -q test", "", "mvn -q -DskipTests package"),
    ("gradle", ["build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"],
     ["gradle.lockfile"],
     "./gradlew check", "./gradlew test", "", "./gradlew build"),
    ("cmake", ["CMakeLists.txt"], ["conan.lock", "vcpkg.json", "CMakePresets.json"],
     "cmake --build build", "ctest --test-dir build --output-on-failure", "",
     "cmake -S . -B build && cmake --build build"),
    ("python", ["pyproject.toml", "setup.py", "requirements.txt"],
     ["poetry.lock", "uv.lock", "Pipfile.lock"],
     "python -m compileall -q .", "pytest -q", "ruff check .", ""),
    ("node", ["package.json"],
     ["pnpm-lock.yaml", "yarn.lock", "package-lock.json", "bun.lockb"],
     "", "", "", ""),
    ("swift", ["Package.swift"], ["Package.resolved"],
     "swift build", "swift test", "", "swift build"),
]


def ecosystem_for(main_path):
    """按主干工作树根目录的标记文件探测语言生态与验证命令。"""
    try:
        names = set(os.listdir(str(main_path)))
    except OSError:
        return None
    for eco, markers, locks, check, test, lint, build in ECOSYSTEM_RULES:
        if not any(m in names for m in markers):
            continue
        if eco == "node":
            if "pnpm-lock.yaml" in names:
                pm = "pnpm"
                check = "pnpm install --frozen-lockfile"
            elif "yarn.lock" in names:
                pm = "yarn"
                check = "yarn install --frozen-lockfile"
            elif "bun.lockb" in names:
                pm = "bun"
                check = "bun install --frozen-lockfile"
            else:
                pm = "npm"
                check = "npm ci"
            test = "%s test" % pm
            lint = "%s run lint" % pm
            build = "%s run build" % pm
        return {
            "ecosystem": eco,
            "check": check,
            "test": test,
            "lint": lint,
            "build": build,
            "lockfiles": list(locks),
        }
    return None


def pick_main_worktree(root, wts, cfg):
    if cfg and cfg.get("main_branch"):
        for w in wts:
            if w["branch"] == cfg["main_branch"]:
                return w
    for w in wts:
        if w["path"] == (Path(root) / "main").resolve():
            return w
    for w in wts:
        if w["branch"] in ("main", "master"):
            return w
    return wts[0] if wts else None


def detect_config(root, wts=None):
    wts = wts if wts is not None else list_worktrees(cwd=root)
    main = pick_main_worktree(root, wts, None)
    remotes = [r for r in run(["remote"], cwd=root).get("out", "").splitlines() if r.strip()]

    if "upstream" in remotes:
        upstream = "upstream"
        origin = "origin" if "origin" in remotes else ""
    elif len(remotes) >= 2:
        upstream = "origin"
        origin = [r for r in remotes if r != "origin"][0]
    elif remotes:
        upstream = remotes[0]
        origin = ""
    else:
        upstream = ""
        origin = ""

    main_branch = main["branch"] if main and main["branch"] else "main"
    eco = ecosystem_for(main["path"]) if main else None

    return {
        "_doc": "由 `gwf config init` 自动生成；改这里即可，无需每次向 Agent 复述项目事实。",
        "main_branch": main_branch,
        "main_worktree": main["path"].name if main else "main",
        "upstream_remote": upstream,
        "origin_remote": origin,
        "upstream_ref": ("%s/%s" % (upstream, main_branch)) if upstream else main_branch,
        "patch_tags": ["[fork]", "[me]", "[custom]"],
        "verify": {
            "check": eco["check"] if eco else "",
            "test": eco["test"] if eco else "",
            "lint": eco["lint"] if eco else "",
            "build": eco["build"] if eco else "",
        },
        "ecosystem": eco["ecosystem"] if eco else "unknown",
        "lockfiles": eco["lockfiles"] if eco else [],
    }


def get_config(root, auto_write=True):
    cfg = load_config(root)
    if cfg:
        return cfg
    cfg = detect_config(root)
    if auto_write:
        p = save_config(root, cfg)
        say("已自动探测并生成项目配置: %s" % p)
    return cfg


def ensure_global_ignore(write=True):
    """确保 worktree.md 被全局 gitignore 排除，并开启 rerere。"""
    info = {"excludesfile": "", "created": False, "appended": False, "rerere": False}
    res = run(["config", "--global", "core.excludesfile"])
    path = res["out"] if res["code"] == 0 and res["out"] else ""
    if not path:
        path = str(Path.home() / ".gitignore_global")
        if write:
            run(["config", "--global", "core.excludesfile", path])
            info["created"] = True
    info["excludesfile"] = path

    p = Path(os.path.expanduser(path))
    needed = ["worktree.md", "worktree-*.md"]
    content = ""
    if p.exists():
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
    missing = [n for n in needed if n not in content]
    if missing and write:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write("\n# gwf: 工作树本地需求文档，不入库\n")
                for n in missing:
                    f.write(n + "\n")
            info["appended"] = True
        except OSError as e:
            warn("无法写入全局忽略文件 %s: %s" % (p, e))
    if write:
        run(["config", "--global", "rerere.enabled", "true"])
        run(["config", "--global", "rerere.autoupdate", "true"])
    info["rerere"] = run(["config", "--global", "rerere.enabled"]).get("out") == "true"
    return info


def slugify(text):
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "-", str(text).strip()).strip("-").lower()
    return s or "task"


def now_str():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def stamp_str():
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def repo_cwd(root):
    """能执行分支类命令的工作目录：优先主干工作树，扁平仓库用根目录。"""
    try:
        wts = list_worktrees(cwd=root)
    except SystemExit:
        return root
    cfg = load_config(root) or {}
    base = cfg.get("main_branch", "")
    for w in wts:
        if w["branch"] == base:
            return w["path"]
    return wts[0]["path"] if wts else root


def make_backup(path, cfg, args):
    """同步前把当前 HEAD 备份成 backup/<branch>-<时间戳> 分支。"""
    if getattr(args, "no_backup", False):
        say("--no-backup：跳过备份分支")
        return ""
    branch = run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path).get("out", "")
    if not branch or branch == "HEAD":
        warn("detached HEAD，跳过备份")
        return ""
    name = "backup/%s-%s" % (branch.replace("/", "-"), stamp_str())
    res = run(["branch", name, "HEAD"], cwd=path)
    if res["code"] != 0:
        warn("创建备份分支失败: %s" % (res["err"] or res["out"])[:160])
        return ""
    sha = run(["rev-parse", "--short", "HEAD"], cwd=path).get("out", "")
    say("已备份 %s (%s) -> 分支 %s" % (branch, sha, name))
    if getattr(args, "backup_push", False) or cfg.get("backup_push"):
        remote = cfg.get("origin_remote") or "origin"
        rc = run(["push", "-q", remote, "%s:refs/heads/%s" % (name, name)], cwd=path)
        if rc["code"] == 0:
            say("备份分支已推送 %s" % remote)
        else:
            warn("备份分支推送失败（本地备份仍在）: %s" % (rc["err"] or rc["out"])[:120])
    return name


def rebase_in_progress(root):
    """返回处于 rebase 中的工作树名；没有则返回空串。"""
    try:
        wts = list_worktrees(cwd=root)
    except SystemExit:
        return ""
    for w in wts:
        gd = run(["rev-parse", "--git-dir"], cwd=w["path"]).get("out", "")
        if not gd:
            continue
        gdp = Path(gd) if Path(gd).is_absolute() else Path(w["path"]) / gd
        for sub in ("rebase-merge", "rebase-apply"):
            if (gdp / sub).exists():
                return w["path"].name
    return ""


def list_backup_branches(cwd):
    res = run(["for-each-ref", "--format=%(refname:short)|%(objectname:short)|%(committerdate:short)",
               "refs/heads/backup/"], cwd=cwd)
    rows = []
    for line in res.get("out", "").splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            rows.append({"name": parts[0], "sha": parts[1], "date": parts[2]})
    return rows


# ---------------------------------------------------------------- init

def cmd_init(args):
    url = args.url
    target = args.dir
    if not target:
        base = re.split(r"[\\/]", url.rstrip("/"))[-1]
        target = base[:-4] if base.endswith(".git") else base
    root = Path(target).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / ".git").exists():
        die("%s 下已存在 .git，请换目录或先手动处理" % root)

    ensure_global_ignore()
    say("克隆裸库到 %s" % (root / ".git"))
    res = run(["clone", "--bare", url, ".git"], cwd=root)
    if res["code"] != 0:
        die("克隆失败:\n%s" % (res["err"] or res["out"]))

    # 根目录保持 bare 状态：.git 即仓库本体，根下不会有幽灵工作区
    gdir = ["--git-dir", str(root / ".git")]

    def groot(sub, **kw):
        return run(gdir + sub, cwd=root, **kw)

    # 官方远端统一命名 upstream，并补 fetch refspec（bare clone 默认没有）
    groot(["remote", "rename", "origin", "upstream"])
    groot(["config", "remote.upstream.fetch", "+refs/heads/*:refs/remotes/upstream/*"])
    if args.fork:
        groot(["remote", "add", "origin", args.fork])
        groot(["config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"])
    say("拉取远端引用...")
    groot(["fetch", "--no-tags", "upstream"])

    head = groot(["symbolic-ref", "--short", "HEAD"]).get("out", "") or "main"
    branch = head if groot(["show-ref", "--verify", "--quiet", "refs/heads/%s" % head])["code"] == 0 else ""
    if not branch:
        for cand in ("main", "master"):
            if groot(["show-ref", "--verify", "--quiet", "refs/heads/%s" % cand])["code"] == 0:
                branch = cand
                break
    if not branch:
        die("未能确定主干分支，请手动执行 git worktree add")

    say("检出主干 %s -> ./%s" % (branch, branch))
    res = groot(["worktree", "add", branch, branch])
    if res["code"] != 0:
        die("主干工作树创建失败:\n%s" % (res["err"] or res["out"]))

    cfg = detect_config(root)
    cfg["main_branch"] = branch
    save_config(root, cfg)
    say("初始化完成：%s" % root)
    for child in sorted(Path(root).iterdir()):
        if child.is_dir() and child.name.startswith(".") and child.name != ".git":
            continue
        say("  %s" % (child.name + "/" if child.is_dir() else child.name))
    say('下一步: cd "%s" && gwf new <需求名> "<一句话目标>"' % root)


# ---------------------------------------------------------------- new

def cmd_new(args):
    root = project_root()
    wts = list_worktrees()
    cfg = get_config(root)
    main = pick_main_worktree(root, wts, cfg)
    if not main:
        die("找不到主干工作树")

    name = args.name.strip()
    folder = name if re.match(r"^(feat|fix|chore|refactor|perf)-", name) else "feat-" + slugify(name)
    branch = folder.replace("-", "/", 1) if re.match(r"^(feat|fix|chore|refactor|perf)-", folder) else folder
    dest = Path(root) / folder
    if dest.exists():
        die("目录 %s 已存在" % dest)

    base = cfg.get("main_branch", "main")
    ensure_global_ignore(write=False)

    up = cfg.get("upstream_ref", "")
    if up and git_ok(["rev-parse", "--verify", "--quiet", up], cwd=main["path"]):
        say("同步主干基线 %s -> %s ..." % (base, up))
        res = run(["merge", "--ff-only", up], cwd=main["path"])
        if res["code"] != 0:
            warn("主干无法快进到 %s（可能有下游提交），本次基于现有主干创建" % up)

    say("创建 worktree %s（分支 %s，基线 %s）" % (folder, branch, base))
    res = run(["worktree", "add", "-b", branch, str(dest), base], cwd=main["path"])
    if res["code"] != 0:
        die("创建失败:\n%s" % (res["err"] or res["out"]))

    sha = run(["rev-parse", "--short", "HEAD"], cwd=dest).get("out", "")
    verify = cfg.get("verify", {}) or {}
    verify_lines = "\n".join("- `%s`" % v for v in verify.values() if v) or "- 按项目实际命令补充"

    doc = """# 需求台账：{name}

- **分支**: {branch}
- **工作树**: {folder}/
- **基线**: {base} ({sha})
- **技术栈**: {eco}
- **状态**: 进行中
- **创建**: {date}

## 1. 目标（一句话）
{desc}

## 2. 改动范围
- 主要模块/文件：
- 明确不改动的部分：

## 3. 上游追踪与覆盖判据（DEP-3）
| 本需求的增量入口 | 判定上游是否已覆盖（可执行判据） | 处置 |
| --- | --- | --- |
| 例：新配置项 `foo.bar` | `git grep -n "foo.bar" {upref} -- <路径>` | 上游已有 → 删本增量 |

## 4. 验证方式（在本工作树内执行）
{verify_lines}

## 5. 冲突记录
- 与并行工作树重叠文件：暂无（用 `gwf scan` 复核）
""".format(
        name=name, branch=branch, folder=folder, base=base, sha=sha,
        eco=cfg.get("ecosystem", "unknown"), desc=args.desc or "（一句话目标待补充）",
        upref=cfg.get("upstream_ref", base), verify_lines=verify_lines, date=now_str(),
    )
    (dest / DOC_FILE).write_text(doc, encoding="utf-8")

    say("完成：%s（分支 %s）" % (dest, branch))
    say("%s 已生成（全局 gitignore 已排除，不会入库）" % (dest / DOC_FILE))
    print("")
    print('  接下来: cd "%s"' % folder)


# ---------------------------------------------------------------- status / scan

def feature_rows(root, wts, cfg):
    base = cfg.get("main_branch", "main")
    rows = []
    for w in wts:
        ahead = run(["rev-list", "--count", "%s..HEAD" % base], cwd=w["path"]).get("out", "?")
        behind = run(["rev-list", "--count", "HEAD..%s" % base], cwd=w["path"]).get("out", "?")
        tracked, untracked = split_status(w["path"])
        dirty = len(tracked)
        files = len([l for l in run(["diff", "--name-only", "%s..HEAD" % base], cwd=w["path"]).get("out", "").splitlines() if l.strip()])
        sha = run(["rev-parse", "--short", "HEAD"], cwd=w["path"]).get("out", "")
        subj = run(["log", "-1", "--pretty=%s"], cwd=w["path"]).get("out", "")
        rows.append({
            "folder": w["path"].name, "branch": w["branch"], "ahead": ahead,
            "behind": behind, "dirty": dirty, "untracked": len(untracked), "files": files, "sha": sha,
            "subject": subj, "doc": (w["path"] / DOC_FILE).exists(),
        })
    return rows


def cmd_status(args):
    root = project_root()
    cfg = get_config(root)
    rows = feature_rows(root, list_worktrees(), cfg)
    upstream = cfg.get("upstream_ref", "")

    print("")
    print("项目根: %s" % root)
    print("主干: %s    官方基线: %s    生态: %s" % (
        cfg.get("main_branch"), upstream or "(未配置)", cfg.get("ecosystem")))
    print("")
    header = "%-18s %-16s %6s %7s %6s %8s %8s  %s" % (
        "工作树", "分支", "ahead", "behind", "dirty", "改动文件", "HEAD", "最近提交")
    print(header)
    print("-" * 96)
    for r in rows:
        tag = " [main]" if r["folder"] == cfg.get("main_worktree") else ""
        print("%-18s %-16s %6s %7s %6s %8s %8s  %s%s" % (
            r["folder"], r["branch"], r["ahead"], r["behind"], r["dirty"],
            r["files"], r["sha"], (r["subject"] or "")[:36], tag))
    print("")
    extra = [r for r in rows if r.get("untracked")]
    if extra:
        say("未跟踪文件（多为构建产物，不影响同步/归档）: "
            + ", ".join("%s(+%d)" % (r["folder"], r["untracked"]) for r in extra))
    stale = [r["folder"] for r in rows
             if r["behind"] not in ("0", "?", None) and r["folder"] != cfg.get("main_worktree")]
    if stale:
        say("落后主干，需要同步: %s" % ", ".join(stale))
        say("一键执行: gwf sync %s" % " ".join(stale))
    else:
        say("所有工作树均已对齐主干")


def cmd_scan(args):
    root = project_root()
    cfg = get_config(root)
    base = cfg.get("main_branch", "main")
    wts = [w for w in list_worktrees() if w["branch"] != base]
    if not wts:
        say("没有特性工作树可扫描")
        return

    changed = {}
    for w in wts:
        res = run(["diff", "--name-only", "%s..HEAD" % base], cwd=w["path"])
        changed[w["path"].name] = set(l for l in res["out"].splitlines() if l.strip())

    print("")
    say("扫描 %d 个特性工作树（基线 %s）" % (len(wts), base))

    hot = {}
    for name, files in changed.items():
        for f in files:
            hot.setdefault(f, []).append(name)
    overlaps = {f: v for f, v in hot.items() if len(v) > 1}

    empty = [n for n, v in changed.items() if not v]
    if empty:
        warn("尚无改动的工作树: %s" % ", ".join(sorted(empty)))

    if not overlaps:
        say("无文件重叠：并行分支互不影响")
    else:
        print("")
        print("[冲突预警] %d 个文件被多个并行分支同时修改：" % len(overlaps))
        for f, names in sorted(overlaps.items()):
            print("  - %-52s <- %s" % (f, ", ".join(sorted(names))))
        print("")
        say("建议：先合入改动更基础的分支，再对另一个执行 gwf sync <folder>")

    behind = []
    for w in wts:
        n = run(["rev-list", "--count", "HEAD..%s" % base], cwd=w["path"]).get("out", "0")
        if n not in ("0", ""):
            behind.append((w["path"].name, n))
    if behind:
        print("")
        say("落后主干（合入前必须先同步）：")
        for name, n in behind:
            print("  - %-18s 落后 %s 个提交" % (name, n))


# ---------------------------------------------------------------- sync

def sync_one(root, cfg, target, args, base):
    path = Path(target).resolve()
    if not path.exists():
        die("目标不存在: %s" % path)

    tracked, untracked = split_status(path)
    if tracked:
        die("%s 有未提交的已跟踪改动，先提交或 stash 再同步：\n%s"
            % (path.name, "\n".join(tracked[:10])))
    if untracked:
        warn("%s 有 %d 个未跟踪文件（多为构建产物），本次忽略" % (path.name, len(untracked)))

    mb = run(["merge-base", base, "HEAD"], cwd=path).get("out", "")
    if not mb:
        die("%s 与 %s 无共同祖先，无法 rebase" % (path.name, base))

    our_files = [l for l in run(["diff", "--name-only", "%s..HEAD" % mb], cwd=path).get("out", "").splitlines() if l.strip()]
    our_commits = [l for l in run(["log", "--oneline", "%s..HEAD" % mb], cwd=path).get("out", "").splitlines() if l.strip()]
    upstream_commits = [l for l in run(["log", "--oneline", "%s..%s" % (mb, base)], cwd=path).get("out", "").splitlines() if l.strip()]
    touched = []
    if our_files and len(our_files) <= 200:
        touched = [l for l in run(["log", "--oneline", "%s..%s" % (mb, base), "--"] + our_files,
                                  cwd=path).get("out", "").splitlines() if l.strip()]

    before = diff_size(path, base)
    branch = run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path).get("out", "")
    print("")
    print("=" * 68)
    print("工作树 %s（分支 %s）" % (path.name, branch))
    print("=" * 68)
    print("  我们的提交        : %d 个" % len(our_commits))
    tags = cfg.get("patch_tags") or []
    if tags:
        counts = []
        untagged = 0
        for line in our_commits:
            subject = line.split(" ", 1)[1] if " " in line else line
            hit = next((t for t in tags if subject.startswith(t)), None)
            if hit:
                counts.append(hit)
            else:
                untagged += 1
        detail = ", ".join("%s %d" % (t, counts.count(t)) for t in tags)
        print("  自定义前缀分布    : %s, 未标记 %d" % (detail, untagged))
    print("  我们的改动文件    : %d 个" % len(our_files))
    print("  上游新增提交      : %d 个" % len(upstream_commits))
    print("  上游动过我们的文件: %d 个提交   <-- 冲突高发区" % len(touched))
    for line in touched[:10]:
        print("      %s" % line)
    print("  同步前增量        : %d 文件 / %d 行   (单调递减基线)" % (before[0], before[1]))

    if args.dry_run:
        say("--dry-run：仅审计，未执行 rebase")
        return "dry"

    backup = make_backup(path, cfg, args)
    if backup:
        args.backups = getattr(args, "backups", []) + ["%s:%s" % (backup, path.name)]

    say("rebase 到 %s ..." % base)
    res = run(["rebase", "--empty=drop", base], cwd=path)
    if res["code"] != 0:
        conflicted = [l for l in run(["diff", "--name-only", "--diff-filter=U"], cwd=path).get("out", "").splitlines() if l.strip()]
        print("")
        warn("rebase 停在冲突处（未自动 abort，交给裁决）")
        if conflicted:
            print("  冲突文件：")
            for f in conflicted:
                print("    - %s" % f)
        print("")
        print("  裁决顺序（官方优先）：")
        print("   1) 上游已实现同等功能 -> 取上游版本，删我方实现")
        print("   2) 上游改了结构未实现功能 -> 按上游新结构重写")
        print("   3) 无关新增 -> 两边都保留")
        print("   4) 锁文件(%s) -> git checkout --theirs <lock> 后由项目工具重新生成"
              % (", ".join(cfg.get("lockfiles") or []) or "按项目"))
        print("  解决后: git add -A && git rebase --continue  /  放弃: git rebase --abort")
        if backup:
            print("  回滚到同步前: git reset --hard %s" % backup)
        return "conflict"

    dropped = [l for l in (res["out"] + "\n" + res["err"]).splitlines()
               if "dropping" in l or "already upstream" in l]
    # git 版本不同消息可能缺失：用 subject 对比兜底
    try:
        before_subjects = [l.split(" ", 1)[1].strip() for l in our_commits if " " in l]
        after_commits = [l for l in run(["log", "--oneline", "%s..HEAD" % base], cwd=path).get("out", "").splitlines() if l.strip()]
        after_subjects = set(l.split(" ", 1)[1].strip() for l in after_commits if " " in l)
        for subj in before_subjects:
            if subj not in after_subjects and not any(subj in d for d in dropped):
                dropped.append("dropped: " + subj)
    except Exception:
        pass
    after = diff_size(path, base)
    print("")
    say("rebase 完成")
    if dropped:
        print("  变空被丢弃的提交（上游多半已实现，需逐条确认）：")
        for d in dropped:
            print("    %s" % d)
    print("  同步后增量: %d 文件 / %d 行" % (after[0], after[1]))
    if after[0] > before[0] or after[1] > before[1]:
        warn("增量变大，违反单调递减：检查是否重复实现了上游已有能力")
    else:
        say("单调递减通过 (%d->%d 文件, %d->%d 行)" % (before[0], after[0], before[1], after[1]))

    if backup:
        print("")
        say("备份分支: %s" % backup)
        print("  核对功能是否丢失: gwf backup show %s" % backup)
        print("  确认无误后删除:   gwf backup clean %s" % backup)
        print("  发现问题回滚:     git reset --hard %s" % backup)

    if args.verify:
        verify = cfg.get("verify", {}) or {}
        for key in ("check", "test"):
            cmd = verify.get(key)
            if not cmd:
                continue
            say("验证 %s: %s" % (key, cmd))
            try:
                rc = subprocess.call(cmd, cwd=str(path), shell=True)
            except (FileNotFoundError, OSError):
                warn("命令不可用: %s" % cmd)
                continue
            if rc != 0:
                warn("验证失败(%s)：按仓库规则改代码，不要改门禁" % cmd)
                return "verify-failed"
    return "ok"


def is_flat_layout(root, wts):
    """扁平仓库：根目录本身就是唯一工作区（还没转成纯 worktree 布局）。"""
    return len(wts) == 1 and wts[0]["path"] == root


def cmd_sync(args):
    root = project_root()
    cfg = get_config(root)
    wts = list_worktrees()
    flat = is_flat_layout(root, wts)
    main = pick_main_worktree(root, wts, cfg)
    if not main:
        die("找不到主干工作树")
    base = cfg.get("main_branch", "main")
    up = cfg.get("upstream_ref", "")
    # 扁平仓库或显式 --upstream：目标分支直接变基到官方引用，不经 main 中转
    onto_upstream = bool(up) and (flat or args.upstream)

    ensure_global_ignore(write=False)

    if not args.skip_fetch and up and cfg.get("upstream_remote"):
        say("拉取官方 %s ..." % up)
        res = run(["fetch", "--no-tags", cfg["upstream_remote"],
                   "+refs/heads/%s:refs/remotes/%s" % (base, up)])
        if res["code"] != 0:
            warn("fetch 失败（无网络或无该远端）: %s" % (res["err"] or res["out"])[:160])
        elif not onto_upstream:
            say("主干 %s 快进到 %s ..." % (base, up))
            res = run(["merge", "--ff-only", up], cwd=main["path"])
            if res["code"] != 0:
                warn("主干无法快进到官方（存在下游提交）")
                if args.rebase_main:
                    say("按 --rebase-main 变基主干 ...")
                    run(["rebase", up], cwd=main["path"])
                else:
                    say("保持现有主干继续；需要把主干也变基到官方时加 --rebase-main")

    if flat:
        say("直接同步到官方 %s（不经主干中转）" % up)
        targets = [root]
    elif args.all and not onto_upstream:
        targets = [w["path"] for w in wts if w["branch"] != base]
    elif args.targets:
        targets = []
        for t in args.targets:
            cand = Path(root) / t
            if cand.exists():
                targets.append(cand)
            elif Path(t).resolve().exists():
                targets.append(Path(t).resolve())
            else:
                die("找不到工作树: %s" % t)
    else:
        if onto_upstream and not args.targets:
            say("直接同步到官方 %s（不经主干中转）" % up)
        targets = [Path.cwd()]

    results = {}
    for t in targets:
        if not onto_upstream and Path(t).resolve() == main["path"].resolve():
            say("跳过主干 %s" % Path(t).name)
            continue
        results[Path(t).name] = sync_one(root, cfg, t, args, up if onto_upstream else base)

    if results:
        print("")
        say("同步结果：")
        label = {"ok": "完成", "conflict": "有冲突待裁决", "dry": "仅审计",
                 "verify-failed": "验证失败"}
        for name, status in results.items():
            print("  - %-20s %s" % (name, label.get(status, status)))
    if any(v == "conflict" for v in results.values()):
        print("")
        say("有工作树停在冲突中：解决后 git rebase --continue，或 git rebase --abort 回滚")
        sys.exit(2)


# ---------------------------------------------------------------- archive

def cmd_archive(args):
    root = project_root()
    cfg = get_config(root)
    base = cfg.get("main_branch", "main")
    wts = list_worktrees()
    main = pick_main_worktree(root, wts, cfg)

    target = (Path(root) / args.folder).resolve()
    if not target.exists():
        die("工作树不存在: %s" % args.folder)
    if main and target == main["path"].resolve():
        die("不能归档主干工作树")

    tracked, untracked = split_status(target)
    if tracked and not args.force:
        die("%s 有未提交的已跟踪改动，先提交/清理（或加 --force 丢弃）：\n%s"
            % (args.folder, "\n".join(tracked[:10])))
    if untracked:
        warn("%s 有 %d 个未跟踪文件（构建产物等），归档时一并删除" % (args.folder, len(untracked)))

    branch = run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).get("out", "")
    if not branch:
        die("无法确定 %s 的分支名（可能处于 detached HEAD）" % args.folder)

    def is_merged():
        return run(["merge-base", "--is-ancestor", branch, base], cwd=main["path"])["code"] == 0

    if not is_merged():
        if not args.merge:
            die("分支 %s 尚未合入 %s。加 --merge 尝试快进合入，或先手动合并" % (branch, base))
        say("合入 %s -> %s（仅允许快进）" % (branch, base))
        res = run(["merge", "--ff-only", branch], cwd=main["path"])
        if res["code"] != 0:
            die("无法快进合入（主干已分叉），请先在 %s 内 rebase 后重试" % args.folder)
        if not is_merged():
            die("合入后校验失败，未做任何删除操作")
        say("合入完成")
        if not args.no_push and cfg.get("origin_remote"):
            res = run(["push", cfg["origin_remote"], base], cwd=main["path"])
            if res["code"] != 0:
                warn("推送失败（可稍后手动推）: %s" % (res["err"] or res["out"])[:160])

    # 最后一道保险：未合入且未强制时绝不移除，避免丢工作
    if not is_merged() and not args.force:
        die("分支 %s 仍未合入 %s，已中止（确需丢弃请加 --force）" % (branch, base))

    say("移除工作树 %s" % target)
    need_force = args.force or bool(untracked)
    res = run(["worktree", "remove", str(target)] + (["--force"] if need_force else []), cwd=main["path"])
    if res["code"] != 0:
        die("移除失败: %s" % (res["err"] or res["out"]))
    if not args.keep_branch:
        run(["branch", "-D" if args.force else "-d", branch], cwd=main["path"])
    run(["worktree", "prune"], cwd=main["path"])
    say("归档完成，目录已清理")


# ---------------------------------------------------------------- config / doctor

def cmd_backup(args):
    root = project_root()
    cfg = get_config(root)
    cwd = repo_cwd(root)
    action = args.action or "list"

    if action == "list":
        rows = list_backup_branches(cwd)
        print("")
        if not rows:
            say("没有备份分支")
            return
        say("备份分支（同步前自动创建）:")
        for r in rows:
            ahead = run(["rev-list", "--count", "HEAD..%s" % r["name"]], cwd=cwd).get("out", "?")
            print("  %-46s %-10s %-12s 相对当前多出 %s 个提交" % (r["name"], r["sha"], r["date"], ahead))
        print("")
        say("核对: gwf backup show <分支名>    删除: gwf backup clean <分支名> | --all")
        return

    if action == "show":
        if not args.names:
            die("用法: gwf backup show <备份分支名>")
        name = args.names[0]
        if not name.startswith("backup/"):
            name = "backup/" + name
        if not git_ok(["rev-parse", "--verify", "--quiet", "refs/heads/%s" % name], cwd=cwd):
            die("备份分支不存在: %s" % name)
        print("")
        say("备份 %s 相对当前 HEAD 的差异（HEAD..备份 = 被丢弃/被改写的提交）" % name)
        commits = run(["log", "--oneline", "HEAD..%s" % name], cwd=cwd).get("out", "")
        print(commits if commits else "  (无提交差异：当前分支已包含备份内容)")
        diff = run(["diff", "--stat", "HEAD..%s" % name], cwd=cwd).get("out", "")
        if diff:
            print("")
            print("  文件差异：")
            for line in diff.splitlines():
                print("    " + line)
        print("")
        say("确认功能未丢失后：gwf backup clean %s" % name)
        say("发现问题回滚：  git reset --hard %s" % name)
        return

    if action == "clean":
        busy = rebase_in_progress(root)
        if busy:
            die("工作树 %s 仍处于 rebase 中：先解决冲突（git rebase --continue）或回滚（git rebase --abort），再清理备份" % busy)
        names = list(args.names)
        if args.all:
            names = [r["name"] for r in list_backup_branches(cwd)]
        if not names:
            die("用法: gwf backup clean <备份分支...> | --all")
        for n in names:
            if not n.startswith("backup/"):
                die("只允许删除 backup/ 前缀的分支: %s" % n)
            if not git_ok(["rev-parse", "--verify", "--quiet", "refs/heads/%s" % n], cwd=cwd):
                warn("不存在，跳过: %s" % n)
                continue
            ahead = run(["rev-list", "--count", "HEAD..%s" % n], cwd=cwd).get("out", "0")
            if ahead not in ("0", ""):
                warn("%s 相对当前多出 %s 个提交（确认这些提交确实不需要了）" % (n, ahead))
            res = run(["branch", "-D", n], cwd=cwd)
            if res["code"] != 0:
                warn("删除失败: %s" % (res["err"] or res["out"]).strip())
                continue
            if args.remote and cfg.get("origin_remote"):
                rc = run(["push", cfg["origin_remote"], "--delete", n], cwd=cwd)
                if rc["code"] != 0:
                    warn("远端删除失败: %s" % (rc["err"] or rc["out"])[:120])
            say("已删除备份分支 %s" % n)
        return

    die("未知动作: %s（可选 list / show / clean）" % action)


def cmd_config(args):
    root = project_root()
    cfg = load_config(root)
    if args.action == "init" or not cfg:
        cfg = detect_config(root)
        p = save_config(root, cfg)
        say("已生成配置: %s" % p)
    else:
        say("当前配置: %s" % (Path(root) / CONFIG_FILE))
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def cmd_doctor(args):
    root = project_root()
    wts = list_worktrees()
    cfg = get_config(root)
    print("")
    print("== gwf doctor ==")
    print("gwf 版本      : %s" % VERSION)
    print("python        : %s" % sys.version.split()[0])
    print("git           : %s" % (run(["--version"]).get("out") or "未知"))
    print("项目根        : %s" % root)
    print("工作树数量    : %d" % len(wts))
    for w in wts:
        print("   - %-20s %s" % (w["path"].name, w["branch"]))
    flat = is_flat_layout(root, wts)
    print("布局          : %s" % ("扁平仓库（根目录即工作区）" if flat else "纯 worktree 拓扑"))
    if flat:
        say("  扁平布局可直接同步官方: gwf sync（自动直连 %s）" % (cfg.get("upstream_ref") or "upstream"))
        say("  想获得多需求隔离（每需求一个目录）再迁移：")
        say("    1) 确认工作区干净: git status --porcelain")
        say("    2) cd .. && mkdir <新目录> && mv <旧目录>/.git <新目录>/.git")
        say("    3) cd <新目录> && git --git-dir=.git worktree add <分支名> <分支名>")
        say("    4) 核对 <分支名>/ 内容后删除旧工作区")
    print("配置文件      : %s" % ("已就绪" if (Path(root) / CONFIG_FILE).exists() else "缺失"))
    info = ensure_global_ignore()
    print("全局忽略文件  : %s%s" % (info["excludesfile"],
                                "  (本次已写入规则)" if info["appended"] else ""))
    print("rerere        : %s" % ("已开启" if info["rerere"] else "未开启"))
    main = pick_main_worktree(root, wts, cfg)
    if main:
        ignored = run(["check-ignore", "-q", DOC_FILE], cwd=main["path"])["code"] == 0
        print("worktree.md   : %s" % ("已被忽略 OK" if ignored else "未被忽略（会进 git 历史！）"))
        if not ignored:
            warn("请在全局忽略文件里加入 worktree.md")
    print("")


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(
        prog="gwf",
        description="Git Worktree Flow：纯 worktree 布局 + 多需求并行 + 上游同步一键引擎",
    )
    p.add_argument("--version", action="version", version="gwf " + VERSION)
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="初始化纯 worktree 拓扑（克隆裸库到 .git）")
    sp.add_argument("url", help="官方仓库地址")
    sp.add_argument("dir", nargs="?", help="目标目录名")
    sp.add_argument("--fork", default="", help="个人 fork 地址（写入 origin 远端）")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("new", help="开新需求：建 worktree + 生成 worktree.md")
    sp.add_argument("name", help="需求名（如 login 或 feat-login）")
    sp.add_argument("desc", nargs="?", default="", help="一句话目标")
    sp.set_defaults(func=cmd_new)

    sub.add_parser("status", help="工作树状态总览").set_defaults(func=cmd_status)
    sub.add_parser("scan", help="并行分支冲突/重叠预警").set_defaults(func=cmd_scan)

    sp = sub.add_parser("sync", help="同步上游官方代码（含审计与裁决提示）")
    sp.add_argument("targets", nargs="*", help="目标工作树目录（默认当前目录）")
    sp.add_argument("--all", action="store_true", help="同步所有特性工作树")
    sp.add_argument("--dry-run", action="store_true", help="只审计不动手")
    sp.add_argument("--verify", action="store_true", help="同步后执行 .gwf.json 里的验证命令")
    sp.add_argument("--rebase-main", action="store_true", help="主干无法快进时把主干也变基到官方")
    sp.add_argument("--skip-fetch", action="store_true", help="不联网，只用已有引用")
    sp.add_argument("--no-backup", action="store_true", help="同步前不创建备份分支（不推荐）")
    sp.add_argument("--backup-push", action="store_true", help="把备份分支推到个人远端")
    sp.add_argument("--upstream", action="store_true",
                    help="目标分支直接变基到官方引用（扁平仓库/单分支 fork 用；扁平布局默认启用）")
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("archive", help="合入主干并归档清理工作树")
    sp.add_argument("folder", help="工作树目录名")
    sp.add_argument("--merge", action="store_true", help="未合入时尝试快进合入主干")
    sp.add_argument("--no-push", action="store_true", help="合入后不推送")
    sp.add_argument("--keep-branch", action="store_true", help="保留分支")
    sp.add_argument("--force", action="store_true", help="忽略未提交改动/强制删除")
    sp.set_defaults(func=cmd_archive)

    sp = sub.add_parser("backup", help="查看/核对/清理同步前自动创建的备份分支")
    sp.add_argument("action", nargs="?", default="list", choices=["list", "show", "clean"])
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true", help="clean 时删除全部 backup/* 分支")
    sp.add_argument("--remote", action="store_true", help="clean 时同时删除远端备份分支")
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser("config", help="查看/生成项目配置 .gwf.json")
    sp.add_argument("action", nargs="?", default="show", choices=["show", "init"])
    sp.set_defaults(func=cmd_config)

    sub.add_parser("doctor", help="环境体检（多机器接入先跑这个）").set_defaults(func=cmd_doctor)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
