#!/usr/bin/env python3
"""Import course materials, rebuild the catalog, and publish Marginalia."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 100 * 1024 * 1024
EXTENSIONS = {'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv',
              '.txt', '.md', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.zip', '.7z', '.rar'}
DEFAULT_CATEGORIES = [
    ('handouts', '讲义', 'Handouts'), ('slides', '课件', 'Lecture slides'),
    ('exams', '试题与解析', 'Exams & solutions'),
    ('references', '教材与参考', 'Textbooks & references'),
    ('review', '复习总结', 'Review notes'), ('assignments', '实验与作业', 'Labs & assignments'),
]


class LibraryError(Exception):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def folder_name(value):
    if (not value or value in {'.', '..'} or value != value.strip() or value.endswith('.')
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?', value, re.I)):
        raise LibraryError(f'不能用作文件夹名称：{value!r}')
    return value


def safe_path(root, relative):
    """Only accept regular paths inside this checkout, never linked directories."""
    rel = PurePosixPath(relative)
    if rel.is_absolute() or not rel.parts or any(p in {'.', '..'} for p in rel.parts):
        raise LibraryError(f'目录必须是仓库内的相对路径：{relative}')
    target = Path(root)
    for part in rel.parts:
        folder_name(part)
        target = target / part
        if target.is_symlink() or (hasattr(target, 'is_junction') and target.is_junction()):
            raise LibraryError(f'不导入符号链接或目录联接：{target}')
    if not target.resolve().is_relative_to(Path(root).resolve()):
        raise LibraryError(f'路径超出仓库：{relative}')
    return target


def slug(english, chinese, prefix):
    value = re.sub(r'[^a-z0-9]+', '-', english.lower()).strip('-')
    return value or prefix + '-' + hashlib.sha256(chinese.encode()).hexdigest()[:10]


def validate_config(config, root):
    ids, directories = set(), set()
    for course in config['courses']:
        if course['id'] in ids or course['directory'].casefold() in directories:
            raise LibraryError('课程 ID 或课程目录重复，请检查 library.json。')
        ids.add(course['id']); directories.add(course['directory'].casefold())
        if PurePosixPath(course['directory']).parts[:1] != ('courses',):
            raise LibraryError('课程目录必须位于 courses/ 下。')
        safe_path(root, course['directory'])
        category_ids, category_dirs = set(), set()
        for category in course['categories']:
            folder_name(category['directory'])
            if category['id'] in category_ids or category['directory'].casefold() in category_dirs:
                raise LibraryError(f"分类 ID 或分类目录重复：{course['name']['zh']}")
            category_ids.add(category['id']); category_dirs.add(category['directory'].casefold())


def find_item(items, value):
    return next((x for x in items if value.casefold() in
                 {x['id'].casefold(), x['name']['zh'].casefold(), x['name']['en'].casefold()}), None)


def select_metadata(config, course_name, english_name, category_name, category_english):
    config = copy.deepcopy(config)
    course = find_item(config['courses'], course_name)
    if course is None:
        folder_name(course_name)
        course = {'id': slug(english_name or '', course_name, 'course'),
                  'name': {'en': english_name or course_name, 'zh': course_name},
                  'description': {'en': 'Course materials, references, and review notes.',
                                  'zh': '课程讲义、参考资料与复习笔记。'},
                  'directory': 'courses/' + course_name, 'categories': []}
        config['courses'].append(course)
    category = find_item(course['categories'], category_name)
    if category is None:
        default = next((x for x in DEFAULT_CATEGORIES if category_name in x), None)
        if default:
            cid, zh, en = default
            existing = find_item(course['categories'], cid)
            if existing:
                return config, course, existing
        else:
            zh, en = folder_name(category_name), category_english or category_name
            cid = slug(category_english or '', zh, 'category')
        category = {'id': cid, 'name': {'en': en, 'zh': zh}, 'directory': zh}
        course['categories'].append(category)
    return config, course, category


def metadata(source, relative, category, cached=None):
    source = Path(source)
    size = source.stat().st_size
    if size > MAX_BYTES:
        raise LibraryError(f'文件超过 100 MiB，普通 Git 上传不支持：{source.name}')
    sha = digest(source)
    pages = None
    if source.suffix.lower() == '.pdf':
        if cached and cached.get('sha256') == sha and cached.get('pages') is not None:
            pages = cached['pages']
        else:
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise LibraryError('缺少 pypdf。请使用“更新资料库.cmd”启动，或安装 scripts/requirements.txt。') from exc
            try:
                reader = PdfReader(source)
                if reader.is_encrypted and not reader.decrypt(''):
                    raise LibraryError(f'PDF 需要密码，请先提供可直接打开的副本：{source.name}')
                pages = len(reader.pages)
                if not pages:
                    raise ValueError('PDF 没有页面')
            except LibraryError:
                raise
            except Exception as exc:
                raise LibraryError(f'PDF 无法读取：{source.name}（{exc}）') from exc
    # Keep the existing PDF schema, adding only what other file formats require.
    result = {'name': Path(relative).name, 'path': relative, 'category': category,
              'bytes': size, 'pages': pages, 'sha256': sha}
    if source.suffix.lower() != '.pdf':
        result['format'] = source.suffix[1:].upper()
    return result


def previous_files(root):
    path = Path(root) / 'catalog.json'
    return {f['path']: f for c in read_json(path)['courses'] for f in c['files']} if path.exists() else {}


def enumerate_sources(sources):
    result, ignored = [], 0
    for source in sources:
        path = Path(source).expanduser().absolute()
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise LibraryError(f'请选择原始文件或文件夹：{path}')
        if path.is_file():
            if path.suffix.lower() not in EXTENSIONS:
                raise LibraryError(f'暂不支持此格式：{path.name}')
            result.append((path, path.name))
        elif path.is_dir():
            for base, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not d.startswith('_')
                                 and not (Path(base) / d).is_symlink()
                                 and not (hasattr(Path(base) / d, 'is_junction') and (Path(base) / d).is_junction()))
                for name in sorted(files):
                    item = Path(base) / name
                    if name.startswith(('.', '~$')) or item.suffix.lower() not in EXTENSIONS:
                        ignored += 1
                        continue
                    if item.is_symlink():
                        raise LibraryError(f'不导入文件链接：{item}')
                    result.append((item, item.relative_to(path).as_posix()))
        else:
            raise LibraryError(f'找不到文件或文件夹：{path}')
    if not result:
        raise LibraryError('没有找到支持的资料文件。')
    return result, ignored


def plan_import(root, config, course, category, sources, replace=False):
    previous, plan, seen = previous_files(root), [], {}
    candidates, ignored = enumerate_sources(sources)
    for source, tail in candidates:
        relative = '/'.join((course['directory'], category['directory'], tail))
        target = safe_path(root, relative)
        record = metadata(source, relative, category['id'], previous.get(relative))
        key = relative.casefold()
        if key in seen:
            if seen[key]['path'] != relative or seen[key]['sha256'] != record['sha256']:
                raise LibraryError(f'本次选择的文件存在重名冲突：{relative}')
            continue
        seen[key] = record
        if target.exists() and not target.is_file():
            raise LibraryError(f'目标是文件夹，不能覆盖：{relative}')
        action = 'add'
        if target.exists():
            action = 'same' if digest(target) == record['sha256'] else 'replace'
            if action == 'replace' and not replace:
                raise LibraryError(f'同名文件内容不同：{relative}\n原文件尚未改动。如需替换，请选择“允许替换”或添加 --replace。')
        plan.append({'source': source, 'path': relative, 'action': action, 'record': record})
    return plan, ignored


def build_catalog(root, config, overrides=(), allow_removals=False):
    validate_config(config, root)
    previous = previous_files(root)
    incoming = {x['path']: x for x in overrides}
    catalog = {k: copy.deepcopy(v) for k, v in config.items() if k not in {'schema_version', 'branch', 'courses'}}
    catalog['courses'] = []
    all_paths, folded = set(), set()
    for c in config['courses']:
        course = {k: copy.deepcopy(v) for k, v in c.items() if k != 'categories'}
        course['categories'] = [{k: v for k, v in cat.items() if k != 'directory'} for cat in c['categories']]
        course['files'] = []
        for category in c['categories']:
            prefix = c['directory'] + '/' + category['directory'] + '/'
            directory = safe_path(root, prefix.rstrip('/'))
            records = {}
            if directory.exists():
                for base, dirs, files in os.walk(directory, followlinks=False):
                    dirs[:] = sorted(d for d in dirs if not d.startswith(('.', '_')))
                    for name in dirs:
                        safe_path(root, (Path(base) / name).relative_to(root).as_posix())
                    for name in sorted(files):
                        if name.startswith(('.', '~$')) or Path(name).suffix.lower() not in EXTENSIONS:
                            continue
                        path = Path(base) / name
                        relative = path.relative_to(root).as_posix()
                        safe_path(root, relative)
                        records[relative] = incoming.get(relative) or metadata(path, relative, category['id'], previous.get(relative))
            records.update({p: f for p, f in incoming.items() if p.startswith(prefix)})
            # Preserve existing ordering, then append new files in filename order.
            ordered = [records[p] for p in previous if p in records]
            ordered.extend(records[p] for p in sorted(records) if p not in previous)
            for f in ordered:
                if f['path'].casefold() in folded:
                    raise LibraryError(f"文件路径重复（忽略大小写）：{f['path']}")
                all_paths.add(f['path']); folded.add(f['path'].casefold())
            course['files'].extend(ordered)
        catalog['courses'].append(course)
    missing = set(previous) - all_paths
    if missing and not allow_removals:
        raise LibraryError('以下已收录文件缺失；未改动目录。若已主动删除或重命名，请运行 sync --allow-removals：\n' + '\n'.join(sorted(missing)))
    return catalog


def md(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('[', '&#91;').replace(']', '&#93;').replace('\n', ' ')


def generated_documents(catalog):
    website = catalog['website']
    rows, docs = [], {}
    total = sum(len(c['files']) for c in catalog['courses'])
    for course in catalog['courses']:
        files = course['files']
        amount = sum(f['bytes'] for f in files) / 1024 ** 2
        link = quote(course['directory'] + '/README.md', safe='/')
        contents = '; '.join(f"{cat['name']['en']}: {sum(f['category'] == cat['id'] for f in files)}" for cat in course['categories'])
        rows.append(f"| [{md(course['name']['en'])} · {md(course['name']['zh'])}]({link}) | {len(files)} files · {amount:.1f} MiB | {md(contents)} |")
        lines = [f"# {course['name']['en']} · {course['name']['zh']}", '',
                 f'[Library home](../../README.md) · [Browse on the website]({website})', '',
                 f'{len(files)} files · {amount:.1f} MiB. Original filenames and contents are preserved.', '',
                 f'共 {len(files)} 份资料，保留原有中文文件名与文件内容。', '']
        for cat in course['categories']:
            lines += [f"## {cat['name']['en']} · {cat['name']['zh']}", '',
                      '| File / 文件 | Pages / 页数 | Size / 大小 |', '| --- | ---: | ---: |']
            for f in files:
                if f['category'] == cat['id']:
                    relative = f['path'][len(course['directory']) + 1:]
                    lines.append(f"| [{md(f['name'])}]({quote(relative, safe='/')}) | {f['pages'] if f['pages'] is not None else '—'} | {f['bytes'] / 1024 ** 2:.2f} MiB |")
            lines.append('')
        docs[course['directory'] + '/README.md'] = '\n'.join(lines)
    docs['README.md'] = f"""# {catalog['title']} · {catalog['title_zh']}

A personal collection of learning materials, organized by course. A place for the pages worth keeping.

[Browse the library]({website}) · [Update guide / 更新指南](docs/UPDATING.md) · [中文说明](#中文说明)

The website opens in English and includes a Chinese language switch. Original Chinese filenames are preserved.

## Courses

| Course | Materials | Contents |
| --- | ---: | --- |
{chr(10).join(rows)}

## Browse and download

- Use the [website]({website}) to select a course, filter by category, and search filenames.
- Open supported documents in your browser or download the original files.
- Browse [`courses/`](courses/), or use **Code → Download ZIP** to download the repository.

## Add materials

On Windows, double-click **更新资料库.cmd** in your local clone. Choose or create a course, select a category and files, then choose **上传并更新网站**. The updater copies the files, rebuilds the website catalog and course indexes, commits, and pushes the update.

PDFs, Office documents, images, text files, and archives are supported. See the [update guide](docs/UPDATING.md) for setup, command-line examples, and replacing files. Course settings live in `library.json`; `catalog.json` and the course indexes are generated automatically.

## 中文说明

**书页之间**是按课程整理的个人学习资料库，现有 **{len(catalog['courses'])} 门课程、{total} 份资料**。网页默认英文，可切换中文，保留原有中文文件名和文件内容。

添加资料时，在本地仓库双击 **更新资料库.cmd**，依次选择课程、分类和文件，再选择“上传并更新网站”。脚本会自动更新网站目录和各课程索引，无需手工修改 JSON。详细操作见[更新指南](docs/UPDATING.md#中文操作指南)。
"""
    return docs


def transaction(root, texts, imports=()):
    """Stage everything first; restore originals if any local replacement fails."""
    root = Path(root)
    work = root / '.marginalia-work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='import-', dir=work) as temporary:
        temporary = Path(temporary)
        staged, backups, applied = {}, {}, []
        for item in imports:
            if item['action'] == 'same':
                continue
            stage = temporary / 'new' / item['path']
            stage.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item['source'], stage)
            if digest(stage) != item['record']['sha256']:
                raise LibraryError(f"复制时源文件发生变化，请重新导入：{item['source'].name}")
            staged[item['path']] = stage
        for relative, text in texts.items():
            target = safe_path(root, relative)
            raw = text.encode('utf-8')
            if target.exists() and target.read_bytes().replace(b'\r\n', b'\n') == raw:
                continue
            stage = temporary / 'new' / relative
            stage.parent.mkdir(parents=True, exist_ok=True)
            stage.write_bytes(raw)
            staged[relative] = stage
        for relative in staged:
            target = safe_path(root, relative)
            if target.exists():
                backup = temporary / 'backup' / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                backups[relative] = backup
        try:
            for relative, stage in staged.items():
                target = safe_path(root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, target)
                applied.append(relative)
        except BaseException:
            for relative in reversed(applied):
                target = safe_path(root, relative)
                if relative in backups:
                    os.replace(backups[relative], target)
                else:
                    target.unlink()
            raise
    return list(staged)


def save_library(root, config, catalog, imports=()):
    texts = generated_documents(catalog)
    texts['library.json'] = json_text(config)
    texts['catalog.json'] = json_text(catalog)
    return transaction(root, texts, imports)


def run(command, root, timeout=90, check=True):
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
    except FileNotFoundError as exc:
        raise LibraryError(f'未找到 {command[0]}，请按更新指南安装。') from exc
    except subprocess.TimeoutExpired as exc:
        raise LibraryError(f'{command[0]} 执行超时。已保存的资料仍在本地，可稍后重试。') from exc
    if check and result.returncode:
        raise LibraryError((result.stderr or result.stdout).strip())
    return result


def git(root, *args, check=True):
    return run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
                *args], root, check=check)


def repository_name(config):
    parsed = urlparse(config['repository'])
    if parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com' or len(parsed.path.strip('/').split('/')) != 2:
        raise LibraryError('library.json 中 repository 应是 https://github.com/用户名/仓库名。')
    return parsed.path.strip('/').removesuffix('.git')


def check_checkout(root, config):
    actual = Path(git(root, 'rev-parse', '--show-toplevel').stdout.strip()).resolve()
    if actual != Path(root).resolve():
        raise LibraryError('请在 git clone 得到的仓库中运行；下载 ZIP 后不能直接发布。')
    expected = repository_name(config).lower()
    remote = git(root, 'remote', 'get-url', 'origin').stdout.strip().removesuffix('.git')
    if remote.lower() not in {'https://github.com/' + expected, 'git@github.com:' + expected}:
        raise LibraryError(f'origin 与 library.json 不一致，未上传。实际地址：{remote}')
    branch = config.get('branch', 'main')
    if git(root, 'branch', '--show-current').stdout.strip() != branch:
        raise LibraryError(f'请切换到 {branch} 分支后发布。')
    if git(root, 'diff', '--cached', '--name-only').stdout.strip():
        raise LibraryError('Git 暂存区已有其他改动，请先完成或取消该次暂存，再使用更新脚本。')


def refresh(root, config):
    check_checkout(root, config)
    run(['gh', 'auth', 'status'], root)
    branch = config.get('branch', 'main')
    git(root, 'fetch', 'origin', branch)
    ahead, behind = map(int, git(root, 'rev-list', '--left-right', '--count', f'HEAD...origin/{branch}').stdout.split())
    if behind:
        if ahead or git(root, 'status', '--porcelain').stdout.strip():
            raise LibraryError('远端有更新，且本地已有改动。资料已保留；请先处理 Git 同步，脚本不会强制覆盖或自动解决冲突。')
        git(root, 'merge', '--ff-only', f'origin/{branch}')
        return True
    return False


def wait_for_website(config, catalog, timeout=180):
    expected = catalog
    base = config['website'].rstrip('/') + '/'
    deadline = time.monotonic() + timeout
    print('已推送，等待网站目录发布（通常约 1 分钟）…', flush=True)
    while time.monotonic() < deadline:
        try:
            req = Request(base + 'catalog.json?update=' + str(time.time_ns()), headers={'Cache-Control': 'no-cache'})
            with urlopen(req, timeout=15) as response:
                current = json.load(response)
            if current == expected:
                print('网站目录已更新：' + base)
                return True
        except (OSError, ValueError):
            pass
        time.sleep(5)
    print('GitHub 已接收上传，网站目录尚未核验到新版本。可稍后重新打开网站，或查看仓库 Actions。')
    print(config['repository'] + '/actions')
    return False


def managed_changes(root, config, catalog):
    allowed = {'library.json', 'catalog.json', 'README.md'}
    allowed.update(c['directory'] + '/README.md' for c in config['courses'])
    allowed.update(f['path'] for c in catalog['courses'] for f in c['files'])
    allowed.update(previous_files_from_head(root))
    changed = git(root, 'diff', '--name-only', '-z', 'HEAD').stdout.split('\0')
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').stdout.split('\0')
    changes = sorted({p for p in changed + untracked if p in allowed})
    unrelated = [p for p in changed + untracked if p and p not in allowed]
    if unrelated:
        raise LibraryError('发现本次资料更新之外的改动，未提交。请先处理这些文件：\n' + '\n'.join(unrelated))
    return changes


def previous_files_from_head(root):
    result = git(root, 'show', 'HEAD:catalog.json', check=False)
    if result.returncode:
        return set()
    return {f['path'] for c in json.loads(result.stdout)['courses'] for f in c['files']}


def publish(root, config, catalog, wait=True):
    refreshed = refresh(root, config)
    if refreshed:
        raise LibraryError('已取得远端最新版本。请重新运行更新脚本，以最新课程目录发布。')
    # A prior interrupted push may have left local commits. Never push unrelated ones.
    branch = config.get('branch', 'main')
    local_commits = git(root, 'log', '--format=%s', f'origin/{branch}..HEAD').stdout.splitlines()
    if any(not title.startswith('Update learning materials') for title in local_commits):
        raise LibraryError('存在尚未推送的其他提交，请先处理后再使用资料发布脚本。')
    changes = managed_changes(root, config, catalog)
    if changes:
        # --literal-pathspecs preserves filenames containing brackets and wildcard characters.
        try:
            for start in range(0, len(changes), 40):
                git(root, '--literal-pathspecs', 'add', '--', *changes[start:start + 40])
            git(root, 'commit', '-m', 'Update learning materials')
        except LibraryError:
            # The index was empty on entry; unstage only this updater's paths.
            for start in range(0, len(changes), 40):
                git(root, '--literal-pathspecs', 'reset', '--quiet', 'HEAD', '--', *changes[start:start + 40], check=False)
            raise
    if changes or local_commits:
        git(root, 'push', 'origin', branch)
        print('上传成功：' + config['repository'])
    else:
        print('没有需要上传的新改动。')
    if wait:
        return wait_for_website(config, catalog)
    print('网站地址：' + config['website'])
    return True


def print_plan(plan, ignored=0):
    labels = {'add': '新增', 'replace': '替换', 'same': '相同，跳过复制'}
    for item in plan:
        print(f"  [{labels[item['action']]}] {item['path']}")
    if ignored:
        print(f'跳过 {ignored} 个隐藏、临时或不支持格式的文件。')


def choose(title, options):
    print('\n' + title)
    for i, label in enumerate(options, 1):
        print(f'  {i}. {label}')
    while True:
        value = input('输入序号：').strip()
        if value.isdigit() and 1 <= int(value) <= len(options):
            return int(value) - 1
        print('请输入上面的有效序号。')


def prompt_name(message, optional=False):
    while True:
        value = input(message).strip()
        if value or optional:
            return value


def pick_sources(root):
    mode = choose('选择资料来源', ['弹窗多选文件', '弹窗选择整个文件夹（包含子文件夹）', '手动粘贴文件或文件夹路径'])
    if mode < 2 and os.name == 'nt':
        result = run(['powershell.exe', '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File',
                      str(Path(root) / 'scripts' / 'select-files.ps1'), '-Mode', 'Files' if mode == 0 else 'Folder'], root, timeout=3600)
        return json.loads(result.stdout.strip() or '[]')
    return [prompt_name('粘贴完整路径（可带双引号）：').strip('"')]


def wizard(root):
    config = read_json(Path(root) / 'library.json')
    print('\nMarginalia · 学习资料库更新工具\n' + str(root))
    action = choose('本次操作', ['添加资料（选择或新建课程）', '扫描课程文件夹，更新目录', '上传之前已保存的更新', '退出'])
    if action == 3:
        return 0
    try:
        print('检查远端更新…', flush=True)
        refresh(root, config)
        config = read_json(Path(root) / 'library.json')
    except LibraryError as exc:
        print('暂未同步远端：' + str(exc))
        if action == 2:
            raise
        print('仍可先整理并保存到本地，发布时会再次检查。')
    if action == 0:
        options = [c['name']['zh'] for c in config['courses']] + ['新建课程']
        choice = choose('选择课程', options)
        if choice == len(options) - 1:
            name = prompt_name('课程中文名称：')
            english = prompt_name('课程英文名称（可留空）：', optional=True)
            cats = [{'id': cid, 'name': {'zh': zh, 'en': en}} for cid, zh, en in DEFAULT_CATEGORIES]
        else:
            name, english = options[choice], None
            cats = config['courses'][choice]['categories']
        category_choice = choose('选择分类', [c['name']['zh'] for c in cats] + ['新建分类'])
        if category_choice == len(cats):
            category_name = prompt_name('分类中文名称：')
            category_en = prompt_name('分类英文名称（可留空）：', optional=True)
        else:
            category_name, category_en = cats[category_choice]['name']['zh'], cats[category_choice]['name']['en']
        config, course, category = select_metadata(config, name, english, category_name, category_en)
        sources = pick_sources(root)
        if not sources:
            print('已取消选择，未改动资料。')
            return 0
        # Calculate the full plan before offering replacement of any different namesakes.
        plan, ignored = plan_import(root, config, course, category, sources, replace=True)
        print_plan(plan, ignored)
        if any(x['action'] == 'replace' for x in plan):
            answer = choose('有同名但内容不同的文件', ['跳过这些文件，保留原件', '允许替换这些文件', '取消本次导入'])
            if answer == 2:
                return 0
            if answer == 0:
                plan = [x for x in plan if x['action'] != 'replace']
        if not plan:
            print('没有需要导入的文件。')
            return 0
        catalog = build_catalog(root, config, [x['record'] for x in plan])
        choice = choose('完成方式', ['上传并更新网站', '仅保存到本地，稍后上传', '取消'])
        if choice == 2:
            return 0
        save_library(root, config, catalog, plan)
        print('资料和目录已保存。')
    else:
        catalog = build_catalog(root, config)
        choice = 0 if action == 2 else choose('目录扫描完成', ['上传并更新网站', '仅保存到本地', '取消'])
        if choice == 2:
            return 0
        save_library(root, config, catalog)
    if choice == 0:
        return 0 if publish(root, config, catalog) else 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='仓库目录（默认脚本所在仓库）')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('list', help='列出课程和分类')
    add = sub.add_parser('add', help='导入文件或文件夹；默认仅保存本地')
    add.add_argument('--course', required=True)
    add.add_argument('--english-name')
    add.add_argument('--category', required=True)
    add.add_argument('--category-english')
    add.add_argument('--replace', action='store_true')
    add.add_argument('--dry-run', action='store_true')
    add.add_argument('sources', nargs='+', type=Path)
    sync = sub.add_parser('sync', help='扫描资料并更新目录')
    sync.add_argument('--allow-removals', action='store_true')
    sync.add_argument('--check', action='store_true', help='检查生成文件是否最新，不写文件')
    push = sub.add_parser('publish', help='同步目录并发布本地更新')
    for command in (add, sync):
        command.add_argument('--publish', action='store_true')
    for command in (add, sync, push):
        command.add_argument('--no-wait', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command is None:
            return wizard(root)
        config = read_json(root / 'library.json')
        if args.command == 'list':
            for course in config['courses']:
                print(f"{course['name']['zh']} / {course['name']['en']} ({course['id']})")
                print('  ' + '、'.join(c['name']['zh'] for c in course['categories']))
            return 0
        dry_run = getattr(args, 'dry_run', False)
        checking = getattr(args, 'check', False)
        publishing = args.command == 'publish' or getattr(args, 'publish', False)
        if checking and publishing:
            raise LibraryError('--check 和 --publish 不能同时使用。')
        if publishing and not dry_run:
            refresh(root, config)
            config = read_json(root / 'library.json')
        plan = []
        if args.command == 'add':
            config, course, category = select_metadata(config, args.course, args.english_name, args.category, args.category_english)
            plan, ignored = plan_import(root, config, course, category, args.sources, args.replace)
            print_plan(plan, ignored)
        catalog = build_catalog(root, config, [x['record'] for x in plan], getattr(args, 'allow_removals', False))
        if dry_run:
            print('预览完成，未修改文件，也未上传。')
            return 0
        if checking:
            texts = generated_documents(catalog)
            texts['catalog.json'] = json_text(catalog)
            stale = [p for p, text in texts.items() if not (root / p).exists() or (root / p).read_text(encoding='utf-8-sig') != text]
            if stale:
                raise LibraryError('目录需要更新，请运行 sync：\n' + '\n'.join(stale))
            print('目录、文件大小、页数与 SHA-256 检查通过。')
            return 0
        changed = save_library(root, config, catalog, plan)
        print(f'本地已更新 {len(changed)} 个文件；共 {sum(len(c["files"]) for c in catalog["courses"])} 份资料。')
        if publishing:
            return 0 if publish(root, config, catalog, not args.no_wait) else 2
        print('需要上线时，运行 publish 或双击更新入口选择“上传之前已保存的更新”。')
        return 0
    except (LibraryError, OSError, ValueError, KeyError) as exc:
        print('\n未完成：' + str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\n已取消。')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
