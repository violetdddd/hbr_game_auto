#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract hbr-tool.com webpack database and map it to local team/common JSON files.

Requirements: Python >= 3.9 and Node.js (no third-party packages).
Examples:
  python make_js_mapping.py axis_website.js ./database -o mapping.json
  python make_js_mapping.py axis_website.js . -o mapping.json
  python make_js_mapping.py axis_website.js 31A.json 31B.json common_skills.json -o mapping.json

Only *.json in supplied directories (recursively) is read. Non-character JSON
files are ignored; common_skills*.json is recognized by its structure.
Website arrays are detected by field signatures, regardless of minified variable names.
"""
import argparse
import collections
import json
import pathlib
import re
import subprocess
import unicodedata

LANGS = ('jp', 'value', 'zh-CN', 'zh-CN-CN')
CHAR_LANGS = ('jp', 'en', 'value', 'zh-CN', 'zh-CN-CN')
SKIP_PARTIAL_SKILL_IDS = {2, 3, 4, 5}
SKIP_SKILL_IDS = {9999}

# These aliases are only used when the original website Japanese name fails to match.
# Output jp always stays the original website string.
STYLE_JP_ALIASES = {
    "Have no fear! Im a hero!": "Have no fear! I'm a hero!",
    "不抜の研鑽": "アオゾラ全力応援歌",
    "前進ネバーギブアップ": "前進ネバーギブアップ！",
    "ピースフルフレーバー": "穏やかな風情",
    "スイート・メロウタイム": "甘い悠々時光",
    "よそかぜ": "そよかぜ",
    "蒼落の忍び": "碧落の忍び",
}
SKILL_JP_ALIASES = {
    "痛気持ちいぃ～！": "痛気持ちいぃ〜！",
    "BeatDown();": "BeatDown()",
    "至高のポーノ": "至福のボーノ",
}
NODE_EXTRACTOR = r'''
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
function extract(field) {
  // New bundles use changing minified variable names, e.g. dl/ul/ml.
  // Match array contents by first record rather than the variable name.
  const re = new RegExp('(?:const|let|var|,)\\s*[A-Za-z_$][\\w$]*\\s*=\\s*\\[\\{'+field+':');
  const match = re.exec(src);
  if (!match) throw Error('Missing website database array: '+field);
  const begin = src.indexOf('[', match.index);
  let level=0, quote=null, escaped=false;
  for (let i=begin;i<src.length;i++) {
    const c=src[i];
    if (quote !== null) {
      if (escaped) escaped=false;
      else if (c==='\\') escaped=true;
      else if (c===quote) quote=null;
    } else if (c==='"' || c==="'" || c==='`') quote=c;
    else if (c==='[') level++;
    else if (c===']') {
      level--;
      if (level===0) return vm.runInNewContext(src.slice(begin,i+1),Object.create(null),{timeout:10000});
    }
  }
  throw Error('Unclosed array '+field);
}
const out={
  characters:extract('chara_id'),
  styles:extract('style_id'),
  skills:extract('skill_id')
};
process.stdout.write(JSON.stringify(out));
'''


def website_db(js_path):
    try:
        done = subprocess.run(['node', '-e', NODE_EXTRACTOR, str(js_path)],
                              check=True, capture_output=True, text=True, encoding='utf-8')
    except FileNotFoundError as exc:
        raise RuntimeError('请安装 Node.js 并确认 node 在 PATH 中') from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('JS 数据表提取失败，网站打包格式可能已更新: '+exc.stderr) from exc
    data = json.loads(done.stdout)
    for k in ('characters', 'styles', 'skills'):
        if not isinstance(data.get(k), list) or not data[k]:
            raise ValueError('网站数据库为空: '+k)
    return data


def norm_safe(text):
    if text is None:
        return ''
    s = unicodedata.normalize('NFKC', str(text)).casefold()
    return re.sub(r'[\s\u3000・･·‧．.「」『』【】()（）_\-]', '', s)


def all_names(rec, key=None):
    result = []
    if key: result.append(key)
    if isinstance(rec, dict):
        result.append(rec.get('value'))
        names = rec.get('names') or {}
        result.extend(names.values() if isinstance(names, dict) else [])
    return [v for v in result if isinstance(v, str) and v.strip()]


def pick_langs(rec, character=False):
    names = rec.get('names') if isinstance(rec, dict) else None
    names = names if isinstance(names, dict) else {}
    result = {'jp': names.get('jp'), 'value': rec.get('value') if isinstance(rec, dict) else None,
              'zh-CN': names.get('zh-CN'), 'zh-CN-CN': names.get('zh-CN-CN')}
    if character:
        result['en'] = rec.get('english name') or names.get('en')
    return result


def files_from(paths, output):
    found = set()
    for raw in paths:
        p = pathlib.Path(raw)
        if not p.exists():
            raise FileNotFoundError(p)
        if p.is_dir():
            found.update(x.resolve() for x in p.rglob('*.json'))
        else:
            found.add(p.resolve())
    found.discard(output.resolve())
    return sorted(found)


def read_local(paths):
    chars, commons = [], []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            print('[skip] invalid JSON:', path, exc)
            continue
        if not isinstance(data, dict):
            continue
        # Common file: defaultSkills/defaultCommandSkill/defaultPassiveSkill.
        if any(k in data for k in ('defaultSkills','defaultCommandSkill','defaultPassiveSkill')):
            for section, arr in data.items():
                if isinstance(arr, list):
                    for rec in arr:
                        if isinstance(rec, dict) and isinstance(rec.get('names'), dict):
                            commons.append({'record':rec,'section':section,'source':path.name})
            continue
        # Team file: top-level character name -> {names, style, skill}.
        if not any(isinstance(v, dict) and 'style' in v and 'names' in v for v in data.values()):
            continue
        team = re.sub(r'\(\d+\)$', '', path.stem)
        for char_name, rec in data.items():
            if isinstance(rec, dict) and isinstance(rec.get('style'), dict):
                chars.append({'name':char_name,'record':rec,'team':team,'source':path.name})
    return chars, commons


def skill_records(character):
    """Find leaf skills under skill/common, skill/<style>, including nested command/passive groups."""
    root = character['record'].get('skill', {})
    def walk(node, trail):
        if not isinstance(node, dict):
            return
        for label, item in node.items():
            if not isinstance(item, dict):
                continue
            if isinstance(item.get('names'), dict):
                yield {'record':item,'name':label,'section':'/'.join(trail),
                       'character':character}
            else:
                yield from walk(item, trail+[label])
    return list(walk(root, []))



def passive_records(character):
    """Traverse top-level passive skill, accepting dicts, lists and nested groups."""
    root = character['record'].get('passive skill', {})

    def walk(node, label=None):
        if isinstance(node, list):
            for item in node:
                yield from walk(item)
        elif isinstance(node, dict):
            if isinstance(node.get('names'), dict):
                yield {'record': node,
                       'name': label or node['names'].get('jp') or '',
                       'section': 'passive skill', 'character': character}
            else:
                for key, value in node.items():
                    yield from walk(value, key)

    return list(walk(root))


def choose(matches):
    """Require unambiguous result; de-duplicate equivalent copies of same team."""
    distinct={}
    for m in matches:
        key=(str(m.get('team')),str(m.get('character_jp')),str(m.get('style_id')),
             str(m.get('name_jp')),str(m.get('section')))
        distinct[key]=m
    return next(iter(distinct.values())) if len(distinct)==1 else None, len(distinct)


def build(js_data, local_chars, commons):
    char_web = {x['chara_id']:x for x in js_data['characters']}
    cindex=collections.defaultdict(list)
    for c in local_chars:
        for alias in all_names(c['record'],c['name']):
            cindex[norm_safe(alias)].append(c)

    def character_candidates(chara_id):
        ch=char_web.get(chara_id, {})
        return {id(c):c for c in cindex.get(norm_safe(ch.get('chara_name')),[])}.values()

    style_map={}
    for web in js_data['styles']:
        web_char=char_web.get(web['chara_id'],{})
        def find_styles(search_jp):
            results = []
            for ch in character_candidates(web['chara_id']):
                for local_style_name, style in ch['record'].get('style', {}).items():
                    if not isinstance(style, dict):
                        continue
                    jp = style.get('names', {}).get('jp')
                    if norm_safe(search_jp) != norm_safe(jp):
                        continue
                    results.append({'team': ch['team'],
                                    'character_jp': ch['record'].get('names', {}).get('jp'),
                                    'style_id': style.get('id'), 'name_jp': jp,
                                    'section': None, 'character': ch, 'style': style})
            return results

        hits = find_styles(web['style_name'])
        # Only fall back to a hand-supplied alias when the original name finds nothing.
        if not hits and web['style_name'] in STYLE_JP_ALIASES:
            hits = find_styles(STYLE_JP_ALIASES[web['style_name']])
        selected,count=choose(hits)
        character=selected['character'] if selected else None
        style=selected['style'] if selected else None
        style_langs = pick_langs(style) if style else {lang: None for lang in LANGS}
        # Always preserve website Japanese title; override is only a lookup alias.
        style_langs['jp'] = web['style_name']
        character_langs = pick_langs(character['record'], character=True) if character else {
            lang: None for lang in CHAR_LANGS
        }
        style_map[str(web['style_id'])] = {
            **style_langs,
            'character': character_langs,
            'team': character['team'] if character else None,
            'style_id': str(style['id']) if style and style.get('id') is not None else None,
            'website_character_id': web['chara_id'],
            'website_character_jp': web_char.get('chara_name'),
            'status': 'matched' if selected else ('ambiguous' if count else 'unmatched'),
        }


    skill_map={}
    common_index=collections.defaultdict(list)
    for item in commons:
        jp=item['record'].get('names',{}).get('jp')
        if jp: common_index[norm_safe(jp)].append(item)
    skill_index={}
    for ch in local_chars:
        skills=skill_records(ch)
        # Top-level passive skills may be stored as a dict or a list.
        skills.extend(passive_records(ch))
        idx=collections.defaultdict(list)
        for s in skills:
            jp=s['record'].get('names',{}).get('jp')
            if jp:idx[norm_safe(jp)].append(s)
        skill_index[id(ch)]=idx

    # Each website style id maps to exactly one local style only if style matching succeeded.
    local_style_for_website = {}
    for ws in js_data['styles']:
        row = style_map[str(ws['style_id'])]
        if row['status'] == 'matched':
            local_style_for_website[ws['style_id']] = (
                ws['chara_id'], row['team'], row['style_id']
            )

    def skill_hit(item, ch=None):
        rec = item['record']
        return {'team': ch['team'] if ch else None,
                'character_jp': ch['record'].get('names', {}).get('jp') if ch else None,
                'style_id': None, 'name_jp': rec.get('names', {}).get('jp'),
                'section': item['section'], 'record': rec,
                'scope': 'character' if ch else 'global'}

    def sp_equals(rec, website_skill):
        local_sp = rec.get('sp')
        website_sp = website_skill.get('use_cost')
        return (isinstance(local_sp, (int, float)) and not isinstance(local_sp, bool)
                and isinstance(website_sp, (int, float)) and not isinstance(website_sp, bool)
                and local_sp == website_sp and website_skill.get('cost_type') == 'SP')

    def character_fallback_skills(ch, website_skill):
        style_id = website_skill.get('style_id') or 0
        if style_id != 0:
            mapping = local_style_for_website.get(style_id)
            if not mapping or mapping[0] != website_skill['chara_id'] or mapping[1] != ch['team']:
                return []
            # The top-level section of skill/<style-name> must belong to THIS style.
            wanted = mapping[2]
            allowed_names = {
                name for name, style in ch['record'].get('style', {}).items()
                if isinstance(style, dict) and str(style.get('id')) == wanted
            }
            return [r for r in skill_records(ch)
                    if r['section'].split('/')[0] in allowed_names]
        # style_id=0: character common + passive skill (including top-level passives).
        candidates = [r for r in skill_records(ch)
                      if r['section'].split('/')[0] in ('common', 'passive skill')]
        candidates.extend(passive_records(ch))
        return candidates

    for web in js_data['skills']:
        hits = []
        name = norm_safe(web['skill_name'])
        if web['skill_id'] in SKIP_SKILL_IDS:
            selected, count, partial = None, 0, False
        else:
            def find_skill_names(search_name):
                found = []
                if web['chara_id'] == 0:
                    for item in common_index.get(search_name, []):
                        found.append(skill_hit(item))
                else:
                    for ch in character_candidates(web['chara_id']):
                        for item in skill_index[id(ch)].get(search_name, []):
                            found.append(skill_hit(item, ch))
                return found

            hits = find_skill_names(name)
            # Alias matching counts as a genuine name match, not an SP-based partial match.
            alias = SKILL_JP_ALIASES.get(web['skill_name'])
            if not hits and alias:
                hits = find_skill_names(norm_safe(alias))
            selected, count = choose(hits)
            partial = False
            # Partial matching ONLY if direct/alias name match is absent (not ambiguous).
            if not selected and count == 0 and web['skill_id'] not in SKIP_PARTIAL_SKILL_IDS:
                fallbacks = []
                search_names = {name}
                if alias:
                    search_names.add(norm_safe(alias))
                if web['chara_id'] == 0:
                    # Global skill: prefer a matching name, then SP.
                    by_name = [item for item in commons
                               if norm_safe(item['record'].get('names', {}).get('jp')) in search_names]
                    by_sp = [item for item in commons if sp_equals(item['record'], web)]
                    for item in (by_name if by_name else by_sp):
                        fallbacks.append(skill_hit(item))
                else:
                    for ch in character_candidates(web['chara_id']):
                        allowed = character_fallback_skills(ch, web)
                        by_name = [r for r in allowed
                                   if norm_safe(r['record'].get('names', {}).get('jp')) in search_names]
                        by_sp = [r for r in allowed if sp_equals(r['record'], web)]
                        for item in (by_name if by_name else by_sp):
                            fallbacks.append(skill_hit(item, ch))
                if fallbacks:
                    selected = fallbacks[0]
                    partial = norm_safe(selected['record'].get('names', {}).get('jp')) not in search_names
        skill = selected['record'] if selected else None
        langs = pick_langs(skill) if skill else {lang: None for lang in LANGS}
        langs['jp'] = web['skill_name']
        skill_map[str(web['skill_id'])] = {
            **langs,
            'team': selected['team'] if selected else None,
            'character_jp': selected['character_jp'] if selected else None,
            'section': selected['section'] if selected else None,
            'website_character_id': web['chara_id'],
            'website_style_id': web.get('style_id'),
            'status': 'partial matched' if partial else
                      ('matched' if selected else ('ambiguous' if count else 'unmatched')),
        }
    return {'style':style_map,'skill':skill_map}


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('js',type=pathlib.Path,help='minified axis_website.js')
    parser.add_argument('local',nargs='+',help='local JSON files and/or directories')
    parser.add_argument('-o','--output',type=pathlib.Path,default=pathlib.Path('js_mapping.json'))
    args=parser.parse_args()
    files=files_from(args.local,args.output)
    chars,commons=read_local(files)
    if not chars: raise RuntimeError('没有找到角色数据库 JSON，请确认目录和文件结构')
    site=website_db(args.js)
    result=build(site,chars,commons)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for key in ('style','skill'):
        counts=collections.Counter(x['status'] for x in result[key].values())
        print(f'{key}: {len(result[key])} | '+', '.join(f'{k}={v}' for k,v in sorted(counts.items())))
    print(f'本地读取：角色 {len(chars)}，通用技能 {len(commons)}；输出：{args.output}')

if __name__=='__main__':
    main()
