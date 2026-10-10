#!/usr/bin/env python3
"""Download and inventory HBR AxleTool data and images; export JSON/CSV candidates.
Requires Python 3.9+. Only standard library.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

REPO = 'https://github.com/FuseFairy/HBR-AxleTool-vue'
ARCHIVES = [
    'https://codeload.github.com/FuseFairy/HBR-AxleTool-vue/zip/refs/heads/main',
    'https://codeload.github.com/FuseFairy/HBR-AxleTool-vue/zip/refs/heads/master',
]
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif'}
NAME_FIELDS = ('name', 'title', 'label', 'displayName', 'display_name', 'characterName', 'styleName', 'skillName')
ID_FIELDS = ('id', 'ID', 'characterId', 'styleId', 'skillId', 'character_id', 'style_id', 'skill_id')
IMAGE_FIELDS = ('image', 'img', 'icon', 'avatar', 'portrait', 'imageUrl', 'image_url', 'iconUrl', 'icon_url', 'thumbnail')
SKILL_WORDS = ('skill', 'ability', '技能', 'スキル')
STYLE_WORDS = ('style', '战型', '戰型', '风格', 'スタイル')
CHAR_WORDS = ('character', 'chara', 'member', '角色', 'キャラ')
TEAM_WORDS = ('team', 'squad', 'unit', '队伍', '部队', '部隊')


def get_archive():
    error = None
    for url in ARCHIVES:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'HBR-asset-sync/1.0'})
            with urllib.request.urlopen(req, timeout=90) as response:
                data = response.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if zf.testzip() is not None:
                    raise ValueError('Archive CRC check failed')
            return data, url
        except Exception as e:
            error = e
    raise RuntimeError(f'Unable to download GitHub source archive: {error}')


def unpack(data, root):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for item in zf.infolist():
            parts = Path(item.filename).parts
            if len(parts) < 2 or item.is_dir():
                continue
            rel = Path(*parts[1:])
            if '..' in rel.parts:
                continue
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(item) as src, target.open('wb') as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)


def category(s):
    s = s.lower()
    for cat, words in [('skill', SKILL_WORDS), ('style', STYLE_WORDS), ('character', CHAR_WORDS), ('team', TEAM_WORDS)]:
        if any(w.lower() in s for w in words):
            return cat
    return None


def walk_json(obj, source, path='$', depth=0):
    if depth > 16:
        return
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from walk_json(item, source, f'{path}[{i}]', depth + 1)
    elif isinstance(obj, dict):
        if any(k in obj for k in NAME_FIELDS):
            name = next((obj[k] for k in NAME_FIELDS if isinstance(obj.get(k), (str, int))), None)
            if name is not None:
                identifier = next((obj[k] for k in ID_FIELDS if isinstance(obj.get(k), (str, int))), None)
                images = {k: obj[k] for k in IMAGE_FIELDS if isinstance(obj.get(k), str)}
                # Do not guess relation fields: retain original fields for later verified joins.
                hint = category(source + ' ' + path)
                yield {'category_hint': hint or 'unknown', 'source': source, 'json_path': path,
                       'id': identifier, 'name': str(name), 'image_refs': images, 'raw': obj}
        for key, val in obj.items():
            if isinstance(val, (list, dict)):
                yield from walk_json(val, source, f'{path}.{key}', depth + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='hbr_data', help='Destination directory')
    args = parser.parse_args()
    out = Path(args.out)
    raw = out / 'source'
    export = out / 'export'
    export.mkdir(parents=True, exist_ok=True)
    print('Downloading GitHub source archive...')
    data, archive_url = get_archive()
    unpack(data, raw)

    files = [p for p in raw.rglob('*') if p.is_file()]
    imgs = [p for p in files if p.suffix.lower() in IMAGE_EXT]
    json_files = [p for p in files if p.suffix.lower() == '.json' and 'node_modules' not in p.parts]
    candidates, broken = [], []
    for p in json_files:
        rel = p.relative_to(raw).as_posix()
        try:
            obj = json.loads(p.read_text(encoding='utf-8-sig'))
            candidates.extend(walk_json(obj, rel))
        except (ValueError, UnicodeError) as e:
            broken.append({'path': rel, 'error': str(e)})

    # All images remain in source/ in their original directories, preserving references.
    image_index = []
    for p in imgs:
        rel = p.relative_to(raw).as_posix()
        image_index.append({'path': rel, 'file': p.name, 'stem': p.stem,
                            'kind_hint': category(rel) or 'unknown', 'bytes': p.stat().st_size,
                            'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})

    # Exact matching only; filenames that happen to resemble names are not considered verified.
    image_paths = {x['path']: x['path'] for x in image_index}
    for row in candidates:
        matched = []
        for ref in row['image_refs'].values():
            cleaned = ref.split('?', 1)[0].lstrip('/')
            for alternative in (cleaned, 'public/' + cleaned, 'src/' + cleaned):
                if alternative in image_paths:
                    matched.append(alternative)
        row['matched_images'] = sorted(set(matched))

    (export / 'records_candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding='utf-8')
    (export / 'images.json').write_text(json.dumps(image_index, ensure_ascii=False, indent=2), encoding='utf-8')
    (export / 'json_parse_errors.json').write_text(json.dumps(broken, ensure_ascii=False, indent=2), encoding='utf-8')
    with (export / 'records_candidates.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['category_hint', 'id', 'name', 'source', 'json_path', 'matched_images'])
        writer.writeheader()
        for row in candidates:
            writer.writerow({k: ', '.join(row[k]) if k == 'matched_images' else row[k] for k in writer.fieldnames})
    with (export / 'images.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['path', 'file', 'stem', 'kind_hint', 'bytes', 'sha256'])
        writer.writeheader()
        writer.writerows(image_index)

    # Find likely dynamic data URLs and import locations for the manual second pass.
    references = []
    pattern = re.compile(r'''(?:(?:https?://)[^\s'"`<>]+|[\w@./-]+\.(?:json|png|jpg|jpeg|webp|svg))''', re.I)
    for p in files:
        if p.suffix.lower() not in ('.js', '.ts', '.vue', '.jsx', '.tsx') or p.stat().st_size > 2_000_000:
            continue
        rel = p.relative_to(raw).as_posix()
        contents = p.read_text(encoding='utf-8', errors='replace')
        if any(word in contents.lower() for word in ['skill', 'style', 'character', '角色', '技能']):
            found = sorted(set(pattern.findall(contents)))
            if found:
                references.append({'source': rel, 'references': found[:300]})
    (export / 'code_asset_references.json').write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = Counter(row['category_hint'] for row in candidates)
    report = [f'Upstream: {REPO}', f'Archive: {archive_url}', f'Files: {len(files)}',
              f'Images: {len(imgs)}', f'JSON files: {len(json_files)}',
              f'Named JSON objects (not deduplicated): {len(candidates)}',
              f'Category hints: {dict(counts)}', f'JSON parse errors: {len(broken)}',
              '', 'IMPORTANT: Categories and records are candidates, NOT a verified game database.',
              'If data is embedded in JS or fetched at runtime, inspect code_asset_references.json',
              'and the original source files. Images under source/ retain original paths.',
              'No SP costs, ownership, unlock rules, or role-style-skill links are inferred.']
    (export / 'REPORT.txt').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('\n'.join(report))
    print('Output:', out.resolve())


if __name__ == '__main__':
    main()
