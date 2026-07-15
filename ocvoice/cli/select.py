"""CLI for interactive project/session selection.

@contract: Provides interactive terminal UI for browsing projects/sessions
@desc: Discovers OpenCode server, fetches projects from global.dat + SQLite DB,
       displays numbered lists for interactive selection, sends commands to
       daemon via IPC. Supports fuzzy matching via difflib.
@tags: cli, session, project, discovery, ipc
"""

import sys
from .ipc import write_command


def _discover_ide() -> tuple:
    """Find OpenCode server, return (base_url, auth, prefix)."""
    from ..opencode.ide_discovery import IDEDiscovery
    ide = IDEDiscovery()
    if not ide.discover():
        print("❌ OpenCode server not found")
        print("   Make sure OpenCode Desktop is running")
        sys.exit(1)
    return (ide.base_url, ide.auth, ide.prefix)


def _get_client():
    """Return an OpenCodeClient connected to the discovered IDE."""
    from ..opencode.client import OpenCodeClient
    url, auth, prefix = _discover_ide()
    client = OpenCodeClient(base_url=url, auth=auth, prefix=prefix)
    print(f"  🔗 {url} prefix='{prefix}'", flush=True)
    return client


def _send_command(cmd: str, **kwargs):
    """Write command and print confirmation."""
    write_command(cmd, **kwargs)
    print(f"  ✅ Команда отправлена демону OCVoice")


def _project_name(project: dict) -> str:
    """Extract human-readable project name from API response."""
    name = project.get('name', '')
    if name:
        return name
    worktree = project.get('worktree', '')
    if worktree and worktree != '/':
        import os as _os
        return _os.path.basename(worktree.rstrip('/'))
    return project.get('id', 'Desktop')[:20]


def show_status():
    """Print current project and session."""
    client = _get_client()
    try:
        project = client.get_current_project()
        print(f"📁 Проект: {_project_name(project)}")
    except Exception as e:
        print(f"📁 Проект: ошибка — {e}")

    try:
        sessions = client.list_sessions()
        user_sessions = [s for s in sessions
                         if 'OCVoice' not in s.get('title', '')]
        if client.session_id:
            for s in user_sessions:
                if s['id'] == client.session_id:
                    print(f"💬 Сессия: {s.get('title', 'untitled')} ({s['id'][:16]}...)")
                    break
            else:
                print(f"💬 Сессия: {client.session_id[:16]}... (не найдена в списке)")
        else:
            print("💬 Сессия: не выбрана")
        print(f"🔗 Сервер: {client.base_url}")
        print(f"📊 Всего сессий: {len(user_sessions)}")
    except Exception as e:
        print(f"💬 Сессии: ошибка — {e}")
    client.close()


def select_session():
    """List sessions and let user pick one interactively."""
    client = _get_client()
    sessions = client.list_sessions()
    user_sessions = [s for s in sessions
                     if 'OCVoice' not in s.get('title', '')]

    if not user_sessions:
        print("📭 Нет сессий. Создайте новую.")
        try:
            ans = input("  Создать новую сессию? [Y/n] ").strip().lower()
            if ans in ('', 'y', 'yes', 'да'):
                _send_command("new_session")
        except (KeyboardInterrupt, EOFError):
            print()
        return

    print(f"\n{'─'*50}")
    print("  Выберите сессию:\n")
    for i, s in enumerate(user_sessions, 1):
        title = s.get('title', 'untitled')[:55]
        sid = s['id'][:16]
        directory = s.get('directory', '')
        proj = directory.rsplit('/', 1)[-1] if directory else ''
        is_current = s['id'] == client.session_id
        mark = "→" if is_current else " "
        print(f"  {mark} {i:2d}. {title}")
        proj_tag = f"  [{proj}]" if proj else ""
        print(f"       ({sid}...){proj_tag}")

    print(f"\n  0. Отмена")
    print(f"{'─'*50}")

    try:
        choice = input("\n  > ").strip()
        if not choice:
            print("  Отменено")
            return
        idx = int(choice) - 1
        if idx < 0:
            print("  Отменено")
            return
        if 0 <= idx < len(user_sessions):
            selected = user_sessions[idx]
            _send_command("select_session", session_id=selected['id'])
            title = selected.get('title', 'untitled')
            print(f"\n  ✅ Переключаюсь на: {title}")
        else:
            print("  Неверный номер")
    except (ValueError, KeyboardInterrupt, EOFError):
        print("\n  Отменено")
    finally:
        client.close()


def _discover_projects() -> list[tuple]:
    """Read projects from OpenCode Desktop storage.

    Sources: opencode.global.dat (primary), SQLite DB (fallback).
    Returns list of (name, worktree, is_current).
    """
    import os as _os
    import json

    seen = set()
    projects = []

    # 1) opencode.global.dat — all user-added projects
    global_dat_paths = [
        _os.path.expanduser(
            "~/Library/Application Support/ai.opencode.desktop/opencode.global.dat"
        ),
        _os.path.expanduser(
            "~/.config/ai.opencode.desktop/opencode.global.dat"
        ),
    ]
    for gd_path in global_dat_paths:
        if _os.path.isfile(gd_path):
            try:
                with open(gd_path) as f:
                    gd_data = json.load(f)
                raw_server = gd_data.get('server', {})
                if isinstance(raw_server, str):
                    raw_server = json.loads(raw_server)
                for p in raw_server.get('projects', {}).get('local', []):
                    wt = p.get('worktree', '')
                    if wt and wt not in seen:
                        seen.add(wt)
                        projects.append((_os.path.basename(wt.rstrip('/')), wt, False))
            except Exception:
                pass
            break

    # 2) SQLite DB — supplement
    db_path = _os.path.expanduser("~/.local/share/opencode/opencode.db")
    if _os.path.isfile(db_path):
        import sqlite3
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.execute(
                "SELECT worktree, name FROM project "
                "WHERE id != 'global' AND worktree != '/'"
            )
            for wt, pname in cur.fetchall():
                if wt and wt not in seen:
                    seen.add(wt)
                    name = pname or _os.path.basename(wt.rstrip('/'))
                    projects.append((name, wt, False))
            conn.close()
        except Exception:
            pass

    # 3) Fallback: API scan
    if not projects:
        from ..opencode.ide_discovery import IDEDiscovery
        ide = IDEDiscovery()
        if ide.discover():
            from ..opencode.client import OpenCodeClient
            client = OpenCodeClient(base_url=ide.base_url, auth=ide.auth)
            try:
                for p in client.list_projects():
                    pid = p.get('id', '')
                    work = p.get('worktree', '')
                    if pid == 'global' or work == '/' or not work:
                        continue
                    if work not in seen:
                        seen.add(work)
                        name = _os.path.basename(work.rstrip('/'))
                        projects.append((name, work, False))
            except Exception:
                pass
            client.close()

    # Mark current project
    try:
        from ..opencode.ide_discovery import IDEDiscovery
        from ..opencode.client import OpenCodeClient
        ide = IDEDiscovery()
        if ide.discover():
            client = OpenCodeClient(base_url=ide.base_url, auth=ide.auth)
            current_worktree = client.get_current_project().get('worktree', '')
            projects = [
                (n, w, w == current_worktree) if not c else (n, w, c)
                for n, w, c in projects
            ]
            projects.sort(key=lambda x: (not x[2], x[0].lower()))
            client.close()
    except Exception:
        pass

    return projects


def select_project():
    """Discover projects and let user pick one interactively."""
    print("\n  🔍 Загружаю проекты...")
    projects = _discover_projects()

    if not projects:
        print("❌ Проекты не найдены")
        print("   Убедитесь, что OpenCode Desktop запущен")
        return

    print(f"\n{'─'*50}")
    print("  Выберите проект:\n")
    for i, (name, worktree, current) in enumerate(projects, 1):
        mark = "→" if current else " "
        tag = " (текущий)" if current else ""
        short_wt = worktree.rsplit('/', 1)[-1] if worktree else "?"
        print(f"  {mark} {i:2d}. {name}{tag}")
        print(f"       {worktree}")

    print(f"\n  0. Отмена")
    print(f"{'─'*50}")

    try:
        choice = input("\n  > ").strip()
        if not choice:
            print("  Отменено")
            return
        idx = int(choice) - 1
        if idx < 0:
            print("  Отменено")
            return
        if 0 <= idx < len(projects):
            name, worktree, _ = projects[idx]
            _send_command("select_project", worktree=worktree, project_name=name)
            print(f"\n  ✅ Переключаюсь на проект: {name}")
        else:
            print("  Неверный номер")
    except (ValueError, KeyboardInterrupt, EOFError):
        print("\n  Отменено")


def main(args: list[str]):
    """Entry point for 'ocvoice select' or 'ocv select'."""
    if not args:
        show_status()
        return

    sub = args[0]
    if sub in ("session", "sessions", "сессия", "сессии"):
        select_session()
    elif sub in ("project", "projects", "проект", "проекты"):
        select_project()
    elif sub in ("status", "info", "статус"):
        show_status()
    else:
        print(f"Неизвестная команда: {sub}")
        print("Использование: ocvoice select [session|project|status]")
        sys.exit(1)
