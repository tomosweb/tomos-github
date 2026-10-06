#!/usr/bin/env python3
"""Supply missing publication metadata in the Pages build checkout from Git history."""
import argparse
import datetime as dt
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

FRONT = re.compile(r'\A---\r?\n(.*?)\r?\n---(?=\r?\n|$)', re.S)


def scalar(source, key):
    front = FRONT.match(source)
    if not front:
        return ''
    match = re.search(r'^' + re.escape(key) + r'[ \t]*:[ \t]*(.*)$', front[1], re.M)
    if not match:
        return ''
    value = match[1].strip()
    if value.startswith('"'):
        import json
        try:
            return json.JSONDecoder().raw_decode(value)[0]
        except (ValueError, TypeError):
            return ''
    if value.startswith("'"):
        match = re.match(r"'((?:''|[^'])*)'", value)
        return match[1].replace("''", "'") if match else ''
    return re.sub(r'\s+#.*$', '', value).strip()


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def valid_published(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})', value):
        return False
    try:
        dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False


def set_scalar(source, key, value):
    front = FRONT.match(source)
    nl = '\r\n' if '\r\n' in source else '\n'
    if not front:
        return f'---{nl}{key}: {value}{nl}---{nl}' + source
    pattern = re.compile(r'^' + re.escape(key) + r'[ \t]*:[^\r\n]*', re.M)
    block = pattern.sub(lambda _: f'{key}: {value}', front[1]) if pattern.search(front[1]) else front[1] + (nl if front[1] else '') + f'{key}: {value}'
    return f'---{nl}{block}{nl}---' + source[front.end():]


def prepare(root, timezone):
    repo = Path(subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip())
    if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--is-shallow-repository'], text=True).strip() == 'true':
        raise RuntimeError('Publication metadata requires complete Git history (fetch-depth: 0).')
    paths = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z', '--', str(root.resolve().relative_to(repo))], text=True).split('\0')
    count = 0
    for relative in paths:
        if not relative or Path(relative).suffix.lower() not in ('.md', '.markdown'):
            continue
        path = repo / relative
        with path.open(encoding='utf-8', newline='') as handle:
            source = handle.read()
        if scalar(source, 'draft') == 'true':
            continue
        date = scalar(source, 'date')
        published = scalar(source, 'published')
        if valid_date(date) and valid_published(published):
            continue
        # --follow preserves initial publication across a detected rename.
        history = subprocess.check_output(['git', '-C', str(repo), 'log', '--follow', '--format=%aI', '--diff-filter=A', '--', relative], text=True).splitlines()
        if not history:
            raise RuntimeError(f'No initial publication commit found: {relative}')
        initial = dt.datetime.fromisoformat(history[-1])
        updated = source
        if not valid_published(published):
            published = initial.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
            updated = set_scalar(updated, 'published', published)
        if not valid_date(date):
            # Explicit initial publication time, if present, is authoritative.
            local = dt.datetime.fromisoformat(published.replace('Z', '+00:00')).astimezone(timezone)
            updated = set_scalar(updated, 'date', local.date().isoformat())
        with path.open('w', encoding='utf-8', newline='') as handle:
            handle.write(updated)
        count += 1
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content-root', default='content')
    parser.add_argument('--timezone', default='Asia/Tokyo')
    args = parser.parse_args()
    print(f'Publication metadata prepared: {prepare(Path(args.content_root), ZoneInfo(args.timezone))} article(s).')
