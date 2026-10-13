#!/usr/bin/env python3
"""Convert hbr-tool.com SP/OD simulator .sav to HBRF.

Usage:
 python sav_to_hbrf.py sim_data.sav --js hbr_site_main.js --data-dir assets/char-data -o converted.hbrf
"""
import argparse
import base64
import json
import re
import unicodedata
import zlib
from pathlib import Path


def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value))).replace('・', '·').casefold()


def decode_sav(path):
    return json.loads(zlib.decompress(base64.b64decode(Path(path).read_bytes())).decode('utf-8'))


def site_catalog(js_path):
    text = Path(js_path).read_text(encoding='utf-8')
    styles, skills = {}, {}
    # Extract minified JS's plain data records, not UI markup.
    for m in re.finditer(r'\{style_id:(\d+),chara_id:\d+,[^{}]*?\}', text):
        t = re.search(r'style_name:"((?:\\.|[^"\\])*)"', m.group())
        if t:
            styles[int(m.group(1))] = json.loads('"' + t.group(1) + '"')
    for m in re.finditer(r'\{skill_id:(\d+),skill_name:"((?:\\.|[^"\\])*)"[^{}]*?\}', text):
        skills[int(m.group(1))] = json.loads('"' + m.group(2) + '"')
    return styles, skills


def local_catalog(folder):
    styles = {}
    if not Path(folder).exists():
        return styles
    for file in sorted(Path(folder).glob('*.json')):
        if file.stem == 'common_skills':
            continue
        content = json.loads(file.read_text(encoding='utf-8'))
        for role_key, role in content.items():
            if not isinstance(role, dict) or 'style' not in role:
                continue
            for style_key, style in role['style'].items():
                if not isinstance(style, dict):
                    continue
                record = {'team':file.stem, 'role':role_key, 'english':role.get('english name',''),
                          'style':style_key, 'id':style.get('id'), 'role_data':role}
                for name in (style_key, *style.get('names', {}).values(), style.get('value', '')):
                    if name:
                        styles.setdefault(norm(name), record)
    return styles


def skill_aliases(entry):
    return [norm(x) for x in [entry.get('value',''), *entry.get('names',{}).values()] if x]


def resolve_skill(name, role):
    pools = role['skill']
    candidates = list(pools.get('common', {}).values())
    for k, items in pools.items():
        if k == 'common' or not isinstance(items, dict):
            continue
        candidates += [v for v in items.values() if isinstance(v, dict) and ('sp' in v)]
    for v in candidates:
        if norm(name) in skill_aliases(v):
            return v.get('value') or v.get('names',{}).get('jp') or name
    return None


def convert(source, js, data_dir, output):
    raw = decode_sav(source)
    site_styles, site_skills = site_catalog(js)
    local = local_catalog(data_dir)
    warnings = []
    slot_of_style = {}
    roles = []
    meta = []
    for slot, unit in enumerate(raw['unitDataList'], start=1):
        style_id = unit['style_id']
        site_name = site_styles.get(style_id)
        if style_id in slot_of_style:
            warnings.append(f'重复使用网站风格ID {style_id}: 无法区分重复队员')
        slot_of_style[style_id] = slot
        record = local.get(norm(site_name)) if site_name else None
        if record is None:
            warnings.append(f'Slot {slot}: 无法在本地数据库匹配风格 {site_name!r} (site id={style_id})；请在GUI中手动选风格')
        roles.append({'name':re.sub(r'\s+', '', record['role']) if record else f'未匹配角色{slot}',
                      'record':record,'skills':[],'site_name':site_name})
        if record:
            meta.append((slot, {'team':record['team'],'english':record['english'], 'id':record['id']}))

    outputs = []
    first_positions = [unit['style_id'] for unit in raw['unitDataList']]
    previous = first_positions[:]
    for turn in raw['userOperationList']:
        if not turn.get('used', True):
            warnings.append('忽略 used=false 的网站回合')
            continue
        position = turn['placeStyle']
        if sorted(position) != sorted(first_positions):
            warnings.append(f"T{turn['turnNumber']}: 队伍组成改变，无法直接转换")
            continue
        if turn.get('triggerOverDrive') or turn.get('overDriveNumber'):
            warnings.append(f"T{turn['turnNumber']}: 包含OD相关状态，当前无法保证其触发时点；请手动检查")
        if turn.get('kbAction', 1) != 1:
            warnings.append(f"T{turn['turnNumber']}: 未支持 kbAction={turn['kbAction']}")
        if turn.get('selectedPlaceNo', -1) != -1:
            warnings.append(f"T{turn['turnNumber']}: 未支持 selectedPlaceNo={turn['selectedPlaceNo']}")
        if turn.get('remark'):
            warnings.append(f"T{turn['turnNumber']}: 网站备注未转换: {turn['remark']}")
        if position != previous:
            warnings.append(f"T{turn['turnNumber']}: 站位变化已记录到本回合前排；请核对换位语义")
        previous = position[:]
        fields = [f"T{turn['turnNumber']}" + (f"-additional{turn['additionalCount']}" if turn.get('additionalCount') else '') + ' = 0']
        for i in range(3):
            style = position[i]
            if style not in slot_of_style:
                raise ValueError(f'回合包含未定义的风格ID: {style}')
            slot = slot_of_style[style]
            role = roles[slot-1]
            selected = turn['selectSkill'][i]
            skill_id = selected['skill_id']
            target = selected.get('buffTargetCharaId')
            if skill_id == 1:
                skill_number = 0
            else:
                name = site_skills.get(skill_id)
                if not name:
                    raise ValueError(f'网站JS中不存在技能 {skill_id}')
                resolved = resolve_skill(name, role['record']['role_data']) if role['record'] else None
                if resolved is None and skill_id >= 9000:
                    common_path = Path(data_dir) / 'common_skills.json'
                    if common_path.exists():
                        global_skills = json.loads(common_path.read_text(encoding='utf-8')).get('defaultSkills', [])
                        for entry in global_skills:
                            if norm(name) in skill_aliases(entry):
                                resolved = entry.get('value') or name
                                break
                if resolved is None:
                    resolved = name
                    warnings.append(f"T{turn['turnNumber']} Slot {slot}: 未能通过本地技能库匹配 {name!r} (id={skill_id})，保留网站技能名")
                if resolved not in role['skills']:
                    role['skills'].append(resolved)
                skill_number = role['skills'].index(resolved) + 1
            if target is not None:
                warnings.append(f"T{turn['turnNumber']} Slot {slot}: 网站指定目标 {target!r} 未转换，需手工处理")
            fields.append(f"{role['name']}: {skill_number},0")
        outputs.append('; '.join(fields))
    for i, role in enumerate(roles,1):
        if len(role['skills']) > 6:
            raise ValueError(f"Slot {i} {role['name']} 使用了{len(role['skills'])}个技能，超过HBRF上限6")
    if len({r['name'] for r in roles}) != 6:
        warnings.append('生成的角色名存在重复；请检查角色昵称或不同风格重复上场情况')
    lines = ['# Converted from hbr-tool.com simulator (.sav)']
    lines += [r['name'] + ': ' + ', '.join(r['skills']) for r in roles]
    lines += ['']
    lines += ['# HBRTool style metadata']
    lines += ['# HBRTOOL_STYLE ' + str(slot) + ' ' + json.dumps(info,ensure_ascii=False,separators=(',',':')) for slot, info in meta]
    lines += ['', '# Round actions', *outputs, '']
    Path(output).write_text('\n'.join(lines), encoding='utf-8')
    return roles, outputs, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sav', type=Path)
    parser.add_argument('--js', type=Path, required=True, help='Site main.*.js saved alongside HTML')
    parser.add_argument('--data-dir', type=Path, default=Path('assets/char-data'))
    parser.add_argument('-o','--output', type=Path, default=Path('converted.hbrf'))
    args = parser.parse_args()
    roles, turns, warnings = convert(args.sav,args.js,args.data_dir,args.output)
    print(f'Wrote {args.output}: {len(roles)} roles, {len(turns)} turns')
    for item in warnings:
        print('WARNING:',item)


if __name__ == '__main__':
    main()
