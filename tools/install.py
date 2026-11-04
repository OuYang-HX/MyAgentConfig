#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用组件安装器（与具体组件无关）。

仓库约定：
    components/<组件名>/manifest.json    组件声明
    config/gitignore-global             仓库级全局忽略片段（可选）

用法：
    ./install.sh                  # macOS / Linux：安装全部组件
    .\\install.ps1                 # Windows：安装全部组件
    install.sh --list             # 列出组件，不安装
    install.sh --only gwf         # 只装某个组件
    install.sh --dry-run          # 只打印计划
    install.sh --uninstall        # 移除本仓库装过的链接
    install.sh --no-git-config    # 不动 ~/.gitconfig

设计目标：新增技能组 / MCP / 工具时，只加一个 components/<name>/manifest.json，
不需要改安装器本身。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
REPO = Path(__file__).resolve().parent.parent
COMPONENTS = REPO / "components"
REPO_GITIGNORE = REPO / "config" / "gitignore-global"


# ------------------------------------------------------------------ 输出

def say(msg=""):
    print(msg)


def info(msg):
    print("  " + msg)


def ok(msg):
    print("  [ok] " + msg)


def warn(msg):
    print("  [warn] " + msg)


def err(msg):
    print("  [fail] " + msg, file=sys.stderr)


def head(title):
    print()
    print("== " + title + " ==")


# ------------------------------------------------------------------ 工具

def run(args, cwd=None):
    try:
        p = subprocess.run(args, cwd=str(cwd) if cwd else None,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip(), p.stderr.decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return 127, "", "command not found: " + args[0]


def which(cmd):
    return shutil.which(cmd) is not None


def default_skills_dir():
    return Path(os.environ.get("AGENTS_SKILLS_DIR") or (Path.home() / ".agents" / "skills"))


def default_bin_dir():
    if IS_WINDOWS:
        return Path(os.environ.get("AGENTS_BIN_DIR") or (Path.home() / ".gwf" / "bin"))
    return Path(os.environ.get("AGENTS_BIN_DIR") or (Path.home() / ".local" / "bin"))


def is_linkish(dst):
    """判断 dst 是否为类链接（symlink 或 Windows junction）。

    Windows 下 junction 在 Python 3.12 之前 dst.is_symlink() 返回 False。
    本函数统一判定，并带 lexists 守卫杜绝不存在路径崩溃。
    """
    if not isinstance(dst, Path):
        dst = Path(dst)
    if dst.is_symlink():
        return True
    if IS_WINDOWS:
        if hasattr(os.path, "isjunction") and os.path.isjunction(str(dst)):
            return True
        # 跨版本兜底：通过 reparse point 判定（lexists 守卫防止不存在路径崩溃）
        try:
            sd = str(dst)
            if os.path.lexists(sd) and os.path.realpath(sd) != os.path.abspath(sd):
                return True
        except OSError:
            pass
    return False


def ensure_user_path(bin_dst, dry):
    """Windows 用户 PATH 写入（通过 winreg 读写 HKCU\\Environment\\Path）。

    保留原注册表类型（REG_EXPAND_SZ / REG_SZ），并做路径归一化幂等检查。
    """
    if not IS_WINDOWS:
        return
    try:
        import winreg
    except ImportError:
        warn("无法导入 winreg，跳过写入用户 PATH")
        return

    target_norm = os.path.normpath(str(bin_dst)).lower()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except OSError as e:
        warn("打开 HKCU\\Environment 失败: %s" % e)
        return

    try:
        val, vtype = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        val = ""
        vtype = winreg.REG_EXPAND_SZ
    except OSError as e:
        warn("读取 HKCU\\Environment\\Path 失败: %s" % e)
        winreg.CloseKey(key)
        return

    parts = [p.strip() for p in val.split(";") if p.strip()]
    for p in parts:
        if os.path.normpath(p).lower() == target_norm:
            info("用户 PATH 已包含 %s" % bin_dst)
            winreg.CloseKey(key)
            return

    new_val = (val + ";" + str(bin_dst)) if val else str(bin_dst)
    if dry:
        info("设置用户 PATH: += %s" % bin_dst)
        winreg.CloseKey(key)
        return

    try:
        winreg.SetValueEx(key, "Path", 0, vtype, new_val)
        ok("已将 %s 加入 Windows 用户 PATH" % bin_dst)
    except OSError as e:
        warn("写入 HKCU\\Environment\\Path 失败: %s" % e)
    finally:
        winreg.CloseKey(key)


# ------------------------------------------------------------------ 组件

def discover():
    """返回 [(name, dir, manifest)]；manifest 解析失败也返回，附带 error。"""
    found = []
    if not COMPONENTS.is_dir():
        return found
    for d in sorted(COMPONENTS.iterdir()):
        if not d.is_dir():
            continue
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            found.append((d.name, d, {"name": d.name, "_error": str(e)}))
            continue
        manifest.setdefault("name", d.name)
        manifest.setdefault("display", manifest["name"])
        found.append((manifest["name"], d, manifest))
    return found


def check_requires(manifest):
    missing = []
    for req in manifest.get("requires", []):
        cmd = req.get("cmd")
        if not cmd:
            continue
        alt = req.get("windows") if IS_WINDOWS else None
        if which(cmd) or (alt and which(alt)):
            continue
        missing.append((req.get("cmd"), req.get("reason", "")))
    return missing


# ------------------------------------------------------------------ 动作

def link_dir(src, dst, dry):
    """把 src 目录【链接】到 dst。

    安装一律是链接，绝不复制：复制会导致本机改动与仓库脱钩，
    多机器同步只能靠手工拷贝。已存在的符号链接会被替换；
    真实目录不会被覆盖（提示用户自行清理后再装）。
    """
    if is_linkish(dst) or dst.is_file():
        if not dry:
            dst.unlink()
    elif dst.exists():
        warn("%s 已存在且是真实目录（可能是早期复制安装）" % dst)
        warn("未覆盖。请先删除它再重装，否则本机改动不会随仓库更新：")
        warn("    rm -rf \"%s\"" % dst)
        return False
    if dry:
        info("link %s -> %s" % (dst, src))
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(src), str(dst), target_is_directory=True)
    except OSError as e:
        if IS_WINDOWS:
            # 符号链接需要开发者模式；退化为目录联接（junction）——它同样是链接，不是复制
            rc, _, errtxt = run(["cmd", "/c", "mklink", "/J", str(dst), str(src)])
            if rc == 0:
                info("%s: 符号链接不可用，已退化为目录联接（仍是链接，改动可随仓库同步）" % dst.name)
                return True
            err("Windows 建链接失败: %s" % (errtxt or e))
            err("请在「设置 → 开发者模式」开启后重试，或以管理员身份运行")
            return False
        warn("创建链接失败 %s: %s（安装必须是链接，不会复制）" % (dst, e))
        return False
    return True


def install_skills(comp_dir, manifest, skills_dst, dry):
    spec = manifest.get("skills") or {}
    rel = spec.get("dir")
    if not rel:
        return 0
    src_dir = comp_dir / rel
    if not src_dir.is_dir():
        warn("技能目录不存在: %s" % src_dir)
        return 0
    n = 0
    for skill in sorted(src_dir.iterdir()):
        if not skill.is_dir() or not (skill / "SKILL.md").exists():
            continue
        if link_dir(skill, skills_dst / skill.name, dry):
            n += 1
            info("技能 %s" % skill.name)
    return n


def install_bin(comp_dir, manifest, bin_dst, dry):
    n = 0
    for entry in manifest.get("bin", []):
        name = entry.get("name")
        rel = entry.get("windows") if IS_WINDOWS and entry.get("windows") else entry.get("posix")
        if not name or not rel:
            continue
        src = comp_dir / rel
        if not src.exists():
            warn("可执行入口不存在: %s" % src)
            continue
        target = bin_dst / (name + (".cmd" if IS_WINDOWS else ""))
        if dry:
            info("bin %s -> %s" % (target, src))
            n += 1
            continue
        bin_dst.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.is_file():
            target.unlink()
        if IS_WINDOWS:
            py = comp_dir / (entry.get("python") or "scripts/gwf.py")
            script = '@echo off\r\npython "{}" %*\r\n'.format(py if py.exists() else src)
            target.write_text(script, encoding="ascii", errors="ignore")
        else:
            os.symlink(str(src), str(target))
            try:
                os.chmod(str(src), 0o755)
            except OSError:
                pass
        info("命令 %s" % target.name)
        n += 1
    return n


def git_global_config(key, value, dry):
    rc, cur, _ = run(["git", "config", "--global", key])
    if rc == 0 and cur == value:
        return False
    if dry:
        info("git config --global %s %s" % (key, value))
        return True
    run(["git", "config", "--global", key, value])
    return True


def global_excludesfile(dry):
    rc, cur, _ = run(["git", "config", "--global", "core.excludesfile"])
    if rc == 0 and cur:
        return Path(os.path.expanduser(cur))
    path = Path.home() / ".gitignore_global"
    if not dry:
        run(["git", "config", "--global", "core.excludesfile", str(path)])
    return path


def merge_gitignore(patterns, dry):
    if not patterns:
        return 0
    path = global_excludesfile(dry)
    existing = []
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            existing = []
    added = [p for p in patterns if p not in existing]
    if not added:
        return 0
    if dry:
        info("gitignore += %s" % ", ".join(added))
        return len(added)
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = "# MyAgentConfig"
    with open(path, "a", encoding="utf-8") as f:
        if existing and existing[-1].strip():
            f.write("\n")
        if marker not in existing:
            f.write("\n" + marker + "\n")
        for p in added:
            f.write(p + "\n")
    return len(added)


def repo_gitignore_patterns():
    if not REPO_GITIGNORE.exists():
        return []
    out = []
    for line in REPO_GITIGNORE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def run_hook(comp_dir, manifest, dry):
    hook = manifest.get("hook")
    if not hook:
        return True
    script = comp_dir / hook
    if not script.exists():
        warn("manifest 声明了 hook 但文件不存在: %s" % script)
        return False
    if dry:
        info("hook %s" % script)
        return True
    if script.suffix == ".ps1" and IS_WINDOWS:
        rc, _, e = run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)])
    elif script.suffix == ".sh" and not IS_WINDOWS:
        rc, _, e = run(["bash", str(script)])
    else:
        rc, _, e = run(["python3", str(script)])
    if rc != 0:
        warn("hook 执行失败(%s): %s" % (hook, e[:200]))
        return False
    return True


def verify(manifest, bin_dst):
    chk = manifest.get("check")
    if not chk:
        return
    name = chk.get("bin")
    args = chk.get("args", [])
    exe = bin_dst / (name + (".cmd" if IS_WINDOWS else ""))
    if IS_WINDOWS and exe.exists():
        rc, out, _ = run([str(exe)] + args)
    elif exe.exists() or which(name):
        rc, out, _ = run([str(exe)] + args if exe.exists() else [name] + args)
    else:
        warn("校验命令不存在: %s" % name)
        return
    if rc == 0:
        ok("%s" % (out.splitlines()[0] if out else (name + " 正常")))
    else:
        warn("%s 校验失败" % name)


def link_state(dst, repo):
    """返回 (状态, 说明)。状态: ok / missing / copy / other。"""
    if is_linkish(dst):
        try:
            target = os.path.realpath(str(dst))
        except OSError:
            return "other", "链接无法解析"
        if target.startswith(os.path.realpath(repo)):
            return "ok", target
        return "other", "链接指向仓库外: %s" % target
    if dst.exists():
        return "copy", "真实目录/文件（不是链接，改动不会随仓库同步）"
    return "missing", "未安装"

def print_status(comps, skills_dst, bin_dst):
    problems = 0
    print()
    print("== 安装状态（应为链接，不应该是复制）==")
    for name, comp_dir, manifest in comps:
        if manifest.get("_error"):
            print("%s: manifest 解析失败" % name)
            problems += 1
            continue
        print()
        print("组件 %s (%s)" % (name, manifest.get("display", "")))
        rel = (manifest.get("skills") or {}).get("dir")
        if rel:
            src_dir = comp_dir / rel
            entries = sorted([d for d in src_dir.iterdir()
                              if d.is_dir() and (d / "SKILL.md").exists()]) if src_dir.is_dir() else []
            for skill in entries:
                state, note = link_state(skills_dst / skill.name, REPO)
                if state == "ok":
                    ok("技能 %-22s 链接正常" % skill.name)
                elif state == "missing":
                    problems += 1
                    warn("技能 %-22s %s" % (skill.name, note))
                else:
                    problems += 1
                    err("技能 %-22s %s" % (skill.name, note))
            if not entries:
                warn("组件下没有找到技能")
        for entry in manifest.get("bin", []):
            bname = entry.get("name")
            target = bin_dst / (bname + (".cmd" if IS_WINDOWS else ""))
            if IS_WINDOWS and target.is_file() and not is_linkish(target):
                try:
                    content = target.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    content = ""
                if str(REPO) in content or os.path.realpath(str(REPO)) in content:
                    ok("命令 %-22s 包装器正常（指向仓库）" % bname)
                    continue
            state, note = link_state(target, REPO)
            if state == "ok":
                ok("命令 %-22s 链接正常" % bname)
            elif state == "missing":
                warn("命令 %-22s 未安装（%s）" % (bname, target))
            else:
                problems += 1
                err("命令 %-22s %s" % (bname, note))
    if problems:
        print("待处理 %d 项：重新执行 ./install.sh 即可修复（如遇复制安装，先按提示删掉目标目录）" % problems)
    else:
        print("全部为链接，改动会随仓库同步 ✔")
    return 1 if problems else 0


def uninstall(skills_dst, bin_dst, dry):
    removed = 0
    repo = str(REPO)
    repo_real = os.path.realpath(repo)
    for dst in (skills_dst, bin_dst):
        if not dst.is_dir():
            continue
        for item in dst.iterdir():
            target = None
            if is_linkish(item):
                try:
                    target = os.path.realpath(str(item))
                except OSError:
                    continue
                if target.startswith(repo_real) or os.path.abspath(target).startswith(repo):
                    if dry:
                        info("unlink %s" % item)
                    else:
                        item.unlink()
                    removed += 1
            elif IS_WINDOWS and item.is_file() and item.suffix.lower() == ".cmd":
                try:
                    content = item.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    content = ""
                if repo in content or repo_real in content:
                    if dry:
                        info("unlink wrapper %s" % item)
                    else:
                        item.unlink()
                    removed += 1
    say("已移除 %d 个链接（全局 git 配置未改动）" % removed)

# ------------------------------------------------------------------ 主流程

def main():
    ap = argparse.ArgumentParser(description="MyAgentConfig 通用组件安装器")
    ap.add_argument("--list", action="store_true", help="列出组件")
    ap.add_argument("--status", action="store_true", help="检查安装状态（链接是否正常/是否被复制）")
    ap.add_argument("--only", default="", help="只安装指定组件（逗号分隔）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划")
    ap.add_argument("--uninstall", action="store_true", help="移除本仓库安装的链接")
    ap.add_argument("--no-git-config", action="store_true", help="不动全局 git 配置")
    ap.add_argument("--skills-dir", default="", help="覆盖技能安装目录")
    ap.add_argument("--bin-dir", default="", help="覆盖命令安装目录")
    args = ap.parse_args()

    skills_dst = Path(args.skills_dir) if args.skills_dir else default_skills_dir()
    bin_dst = Path(args.bin_dir) if args.bin_dir else default_bin_dir()

    comps = discover()
    if not comps:
        say("components/ 下没有可安装组件")
        return 0

    if args.list:
        say("")
        for name, d, m in comps:
            say("%-14s %-28s kind=%-8s v%s" % (
                name, m.get("display", ""), m.get("kind", "?"), m.get("version", "-")))
            if m.get("description"):
                say("                %s" % m["description"])
        say("")
        return 0

    if args.status:
        return print_status(comps, skills_dst, bin_dst)

    if args.uninstall:
        head("卸载")
        uninstall(skills_dst, bin_dst, args.dry_run)
        return 0

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    if only:
        comps = [c for c in comps if c[0] in only]
        if not comps:
            say("未找到指定组件: %s" % ", ".join(only))
            return 1

    head("MyAgentConfig 安装")
    say("仓库: %s" % REPO)
    say("技能目录: %s" % skills_dst)
    say("命令目录: %s" % bin_dst)
    if args.dry_run:
        say("模式: dry-run（不落盘）")

    failures = 0
    total_skills = 0
    total_bin = 0

    for name, comp_dir, manifest in comps:
        if manifest.get("_error"):
            err("%s manifest.json 解析失败: %s" % (name, manifest["_error"]))
            failures += 1
            continue

        head("%s  %s" % (name, manifest.get("display", "")))
        kind = manifest.get("kind", "skills")

        missing = check_requires(manifest)
        if missing:
            for cmd, reason in missing:
                err("缺少依赖 %s（%s）" % (cmd, reason))
            failures += 1
            say("  -> 跳过该组件")
            continue

        if kind != "skills":
            # 非技能类组件：交给组件自己的 hook（如 MCP 配置、工具安装）
            if manifest.get("hook"):
                if run_hook(comp_dir, manifest, args.dry_run):
                    ok("%s 已通过 hook 安装" % name)
                else:
                    failures += 1
            else:
                warn("kind=%s 的组件需要提供 hook 脚本，已跳过" % kind)
            continue

        n = install_skills(comp_dir, manifest, skills_dst, args.dry_run)
        total_skills += n
        ok("技能 %d 个 -> %s" % (n, skills_dst))

        b = install_bin(comp_dir, manifest, bin_dst, args.dry_run)
        total_bin += b
        if b:
            ok("命令 %d 个 -> %s" % (b, bin_dst))

        if not args.no_git_config:
            patterns = manifest.get("gitignore", [])
            added = merge_gitignore(patterns, args.dry_run)
            if added:
                ok("全局 gitignore 新增 %d 条: %s" % (added, ", ".join(patterns)))
            for key, val in (manifest.get("git_config") or {}).items():
                if git_global_config(key, val, args.dry_run):
                    ok("git config --global %s %s" % (key, val))

        if manifest.get("hook"):
            if not run_hook(comp_dir, manifest, args.dry_run):
                failures += 1

        if not args.dry_run:
            verify(manifest, bin_dst)

    if not args.no_git_config:
        extras = repo_gitignore_patterns()
        if extras:
            merge_gitignore(extras, args.dry_run)

    if IS_WINDOWS and total_bin:
        ensure_user_path(bin_dst, args.dry_run)

    head("汇总")
    say("组件 %d 个，技能 %d 个，命令 %d 个，失败 %d 个" % (len(comps), total_skills, total_bin, failures))
    if failures:
        say("有组件安装失败，见上面的 [fail]")
        return 1
    say("完成。新开终端或 source 你的 shell 配置以加载 PATH 变更。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
