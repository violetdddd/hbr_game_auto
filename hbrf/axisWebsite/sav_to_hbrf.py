#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HBR Tool .sav -> HBRF.  main(sav_path, mapping_path=None, output_path=None).
Requires the project's ``hbrf.model`` when converting (not at import time).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import zlib
from collections import OrderedDict
from pathlib import Path
from paths import ROOT_DIR

DATA_DIR = ROOT_DIR / "assets" / "char-data"

DEFAULT_SKILLS = {0, 1, 2, 3, 4, 5, 8001, 8002, 8003, 8004, 9999}
POST_OD = {4: 1, 5: 2, 6: 3}
KAREN_STYLES = {176: 1, 177: 2}  # 176=009-1(形态001), 177=009-2(形态002)
INTRO = '# 此hbrf文件为解析https://www.hbr-tool.com/网站保存的sav文件生成，不包含特殊行动，需要手动检查调整并重新保存'


def decode_sav(path):
    return json.loads(zlib.decompress(base64.b64decode(Path(path).read_bytes())).decode('utf-8'))

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def clean_name(value, strip_spaces=False):
    value = str(value).replace('\r', ' ').replace('\n', ' ').replace(':', '：').replace(';', '；').replace(',', '，').strip()
    return re.sub(r'\s+', '', value) if strip_spaces else value

def convert(axis: dict, mapping: dict, output_path):
    """Convert already decoded data; save using hbrf.model. Return (Path, warnings)."""
    from hbrf import model as m

    units = axis['unitDataList']
    operations = axis['userOperationList']
    if len(units) != 6:
        raise ValueError('HBRF 队伍必须有六名角色')
    site_styles, site_skills = mapping.get('style', {}), mapping.get('skill', {})
    warnings = []
    roles, metadata = [], []
    style_to_slot = {}
    char_slots = {}
    # 解析角色部分，负责收集开头和结尾注释的信息
    for slot, unit in enumerate(units, 1):
        style_id = int(unit['style_id'])
        info = site_styles.get(str(style_id)) or {}
        char = info.get('character') or {}
        name = clean_name(char.get('zh-CN-CN') or f'未匹配角色{style_id}', strip_spaces=True)
        roles.append(m.Role(slot, name, []))
        # 保存style_to_slot[网站风格id]=slot
        style_to_slot[style_id] = slot
        char_id = info.get('website_character_id')
        # 存储char_slots[网站角色id]=slot
        if char_id is not None:
            char_id = int(char_id)
            if char_id in char_slots:
                raise ValueError(f'队伍有重复角色：网站角色 ID {char_id}')
            char_slots[char_id] = slot
        if info.get('status') != 'matched':
            warnings.append(f'槽位 {slot}：风格 {style_id} 未完整匹配')
        # 找本地数据库风格id
        local_style_id = info.get('style_id')
        # 可怜单独给一个赋值初始id，就是009-1
        if style_id in KAREN_STYLES:
            local_style_id = '009-1'
            style_to_slot[style_id+1] = slot  # 认为可怜的第二个形态是第一形态的id+1
        metadata.append({'team': info.get('team'), 'english': char.get('en'), 'id': local_style_id})

    # 给定技能id获取其技能名称
    def skill_name(skill_id, index):
        info = site_skills.get(str(skill_id)) or {}
        label = info.get('value') or f'未匹配技能{skill_id}'
        if not info.get('value') or info.get('status') in ('unmatched', 'ambiguous'):
            warnings.append(f'操作 {index}：技能 {skill_id} 未完整匹配')
        return label

    def skill_id_of(skill_name_value):
        for skill_id, skill_content in site_skills.items():
            if skill_content.get("value") == skill_name_value:
                return int(skill_id)
        raise ValueError(f'未找到技能 {skill_name_value} 的网站技能ID')

    special_file = DATA_DIR / "special_skills.json"
    special = json.loads(special_file.read_text(encoding="utf-8")) if special_file.exists() else {}
    links = {}
    for name, groups in special.get("switchable", {}).items():
        # group是一个风格及其所对应的技能，这里保存了(skill id): link id
        for group in groups.values():
            links.update({skill_id_of(v["value"]): skill_id_of(v["link"]) for skill, v in group.items()})

    # 第一次遍历：收集用过的skill信息
    used = {slot: OrderedDict() for slot in range(1, 7)}
    initial_selection = {}
    for index, op in enumerate(operations, 1):
        places, selections = op.get('placeStyle') or [], op.get('selectSkill') or []
        if len(places) < 6 or len(selections) < 6:
            raise ValueError(f'第{index}行行动的上场角色不满6人')
        for style_id, selection in zip(places[:3], selections[:3]):
            slot = style_to_slot[style_id]
            sid = int(selection.get('skill_id') or 0)
            if sid in DEFAULT_SKILLS:
                continue
            pair = links.get(sid)  # 不是links则返回None
            key = frozenset((sid, pair)) if pair else sid
            if key not in used[slot]:
                if pair:
                    first_name = skill_name(sid, index)
                    second_name = skill_name(pair, index)
                    label = first_name + '/' + second_name
                    # 保存切换技能里面初始选择的技能
                    initial_selection[(slot, key)] = sid
                else:
                    label = skill_name(sid, index)
                used[slot][key] = label
                if len(used[slot]) > 6:
                    raise ValueError(f'槽位 {slot}：超过 6 个不同的技能槽')
    # 构建一个slot和技能id（pair是frozenset）到技能栏位的映射
    skill_index = {slot: {key: i for i, key in enumerate(skills, 1)} for slot, skills in used.items()}
    # 加入Role技能列表
    for role in roles:
        role.skills = list(used[role.slot].values())

    # 第二次遍历，收集行动、od、label信息
    # 收集od和label信息
    phase = None
    last_phase = None
    actions = []
    active_form = {}  # 用1和2来表示可怜的两个形态，初始为1
    active_skill = dict(initial_selection)
    for index, op in enumerate(operations, 1):
        trigger = bool(op.get('triggerOverDrive'))
        kb = int(op.get('kbAction') or 0)
        turn_no = int(op.get('turnNumber') or 0)
        bonus = int(op.get('overDriveNumber') or 0)
        extra = int(op.get('additionalCount') or 0)
        od = 0
        if trigger:
            level = int(op.get('overDriveLevel') or 0)
            if level not in (1, 2, 3):
                raise ValueError(f'操作 {index}：非法前置 OD {level}')
            phase, od = ('前置', level), -level
            last_phase = phase
        elif kb in POST_OD:
            level = POST_OD[kb]
            phase, od = ('后置', level), level
            last_phase = phase
        elif bonus == 0:
            last_phase = None
        label = f'T{turn_no}'
        if last_phase:
            direction, level = last_phase
            label += f'-{direction}OD{level}'
            if direction == '前置':
                label += f'-bonus{max(1, bonus)}'
            elif bonus == 0:
                label += '-OD前'
            else:
                label += f'-bonus{bonus}'
        if extra:
            label += '-追加'

        # 收集行动信息
        moves, switches = [], []
        places, selections = op['placeStyle'][:3], op['selectSkill'][:3]
        for position, (style_id, selection) in enumerate(zip(places, selections)):
            style_id = int(style_id)
            slot = style_to_slot[style_id]
            # 处理额外的可怜切换action
            if style_id in KAREN_STYLES:
                new_form = KAREN_STYLES[style_id]
                if slot in active_form and active_form[slot] != new_form:
                    switches.append(m.SpecialRoleButton(slot, position, 'kelian'))
                active_form[slot] = new_form
            sid = int(selection.get('skill_id') or 0)
            # 默认行动
            if sid in DEFAULT_SKILLS:
                number = 0
            # 额外处理技能切换
            else:
                pair = links.get(sid)
                key = frozenset((sid, pair)) if pair else sid
                number = skill_index[slot][key]
                if pair and active_skill[(slot, key)] != sid:
                    switches.append(m.SkillSwitch(slot, number, position))
                    active_skill[(slot, key)] = sid
            # 收集一般的技能信息
            target_id = selection.get('buffTargetCharaId')
            target = None
            if number and target_id not in (None, '', 0, '0'):
                try:
                    target = char_slots.get(int(target_id))
                    if target is None:
                        warnings.append(f'操作 {index}：目标角色 {target_id} 不在队伍中，改为无目标')
                except (TypeError, ValueError):
                    warnings.append(f'操作 {index}：非法目标 {target_id!r}，改为无目标')
            moves.append(m.SkillAction(slot, number, target))
        # 将特殊行动和一般战斗行动加入actions列表
        actions.extend(switches)
        actions.append(m.BattleTurn(label, od, moves))

    script = m.BattleScript(roles, actions)
    m.validate_hbrf(script)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    m.save_hbrf(script, output)
    body = output.read_text(encoding='utf-8')
    footer = '\n# HBRTool style metadata\n' + ''.join(
        f'# HBRTOOL_STYLE {slot} {json.dumps(info, ensure_ascii=False)}\n'
        for slot, info in enumerate(metadata, 1)
    )
    output.write_text(INTRO + '\n\n' + body.rstrip('\n') + '\n' + footer, encoding='utf-8')
    return output, warnings


def main(sav_path, mapping_path=None, output_path=None):
    """GUI/other Python: main('xxx.sav') -> (Path, warnings)."""
    source = Path(sav_path)
    mapping_file = Path(mapping_path) if mapping_path is not None else Path(__file__).resolve().with_name('mapping.json')
    output = Path(output_path) if output_path is not None else source.with_suffix('.hbrf')
    return convert(decode_sav(source), read_json(mapping_file), output)


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sav', type=Path)
    parser.add_argument('mapping', nargs='?', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    output, warnings = main(args.sav, args.mapping, args.output)
    print(f'输出：{output}；警告：{len(warnings)}')
    for warning in dict.fromkeys(warnings):
        print('[警告]', warning)


if __name__ == '__main__':
    cli()
