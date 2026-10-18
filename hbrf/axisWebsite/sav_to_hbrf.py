#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert HBR Tool SAV JSON to HBRF using make_js_mapping output.

Usage:
    python sav_to_hbrf.py input.sav mapping.json -o output.hbrf
    from sav_to_hbrf import main
    path, warnings = main("input.sav", "mapping.json")

Special actions are intentionally not converted. Inspect the generated HBRF.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
import zlib
import base64

DEFAULT_SKILLS = {1, 2, 3, 4, 5, 8001, 8002, 8003, 8004, 9999}
POST_OD = {4: 1, 5: 2, 6: 3}
INTRO = '# 此hbrf文件为解析https://www.hbr-tool.com/网站保存的sav文件生成，不包含特殊行动，需要手动检查调整并重新保存'
TEAM_HEADER = '# 配队和技能（用于初始化角色编号为1-6，目前支持技能数最多6个，角色最少需要装备3个技能）'
TURN_HEADER = '# 回合 = OD; 角色: 技能,目标（od后置1或2或3，前置为负，0为不开od）'


def decode_sav(path):
    return json.loads(zlib.decompress(base64.b64decode(Path(path).read_bytes())).decode('utf-8'))

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def text_field(obj, key):
    value = obj.get(key)
    return str(value).strip() if value is not None else ''


def format_name(name, *, strip_spaces=False):
    name = str(name).replace('\r', ' ').replace('\n', ' ').replace(':', '：').replace(';', '；').replace(',', '，')
    if strip_spaces:
        name = re.sub(r'\s+', '', name)
    return name.strip()


def convert(axis: dict, mapping: dict):
    units = axis['unitDataList']
    ops = axis['userOperationList']
    if len(units) != 6:
        raise ValueError('HBRF 队伍必须恰好有六名角色')

    styles = mapping.get('style', {})
    skills = mapping.get('skill', {})
    style_ids = [int(row['style_id']) for row in units]
    if len(set(style_ids)) != 6:
        raise ValueError('队伍风格 ID 重复，无法生成唯一的角色顺序')

    name_by_style = {}
    style_info = {}
    char_slot = {}
    warnings = []
    for slot, style_id in enumerate(style_ids, 1):
        info = styles.get(str(style_id), {})
        style_info[style_id] = info
        character = info.get('character') or {}
        name = format_name(character.get('zh-CN-CN') or f'未匹配角色{style_id}', strip_spaces=True)
        name_by_style[style_id] = name
        char_id = info.get('website_character_id')
        if char_id is not None:
            char_slot[int(char_id)] = slot
        if info.get('status') != 'matched':
            warnings.append(f'队伍槽位 {slot}: 风格 {style_id} 未完全匹配')
    if len(set(name_by_style.values())) != 6:
        raise ValueError('队伍中出现相同的角色名称，无法按 HBRF 格式区分')

    # First appearance in front-row operations determines the 1-based skill slot.
    equipped = {style_id: OrderedDict() for style_id in style_ids}
    for op_no, op in enumerate(ops, 1):
        place = op.get('placeStyle') or []
        selected = op.get('selectSkill') or []
        if len(place) < 3 or len(selected) < 3:
            raise ValueError(f'操作 {op_no}: 前排位置或技能不足 3 个')
        for style_id, action in zip(place[:3], selected[:3]):
            style_id = int(style_id)
            if style_id not in equipped:
                raise ValueError(f'操作 {op_no}: 风格 {style_id} 未在队伍中')
            skill_id = int(action.get('skill_id') or 0)
            if skill_id in DEFAULT_SKILLS or skill_id == 0:
                continue
            if skill_id not in equipped[style_id]:
                mapped = skills.get(str(skill_id), {})
                label = format_name(mapped.get('value') or f'未匹配技能{skill_id}')
                if mapped.get('value') is None or mapped.get('status') in ('unmatched', 'ambiguous'):
                    warnings.append(f'操作 {op_no}: 技能 {skill_id} 未完全匹配')
                if label in equipped[style_id].values():
                    warnings.append(f'角色 {name_by_style[style_id]}: 不同技能 ID 具有同一繁体名称 {label!r}')
                equipped[style_id][skill_id] = label
                if len(equipped[style_id]) > 6:
                    raise ValueError(f'角色 {name_by_style[style_id]} 使用了超过6种非默认技能，无法全部存入HBRF')

    skill_slots = {sid: {skill_id: i for i, skill_id in enumerate(records, 1)}
                   for sid, records in equipped.items()}

    result = [INTRO, "", TEAM_HEADER]
    for style_id in style_ids:
        labels = list(equipped[style_id].values())
        result.append(f'{name_by_style[style_id]}: ' + ', '.join(labels))
    result.extend(["", TURN_HEADER])

    # Track the last OD trigger type/level for bonus labels.
    # Note: phase persists for OD bonus rows, but a normal bonus=0 row does not belong to it.
    phase = None   # ('前置'|'后置', level)
    for op_no, op in enumerate(ops, 1):
        trigger = bool(op.get('triggerOverDrive'))
        kb = int(op.get('kbAction') or 0)
        if trigger:
            level = int(op.get('overDriveLevel') or 0)
            if level not in (1, 2, 3):
                raise ValueError(f'操作 {op_no}: 前置OD等级无效 {level}')
            phase = ('前置', level)
            od_value = -level
        elif kb in POST_OD:
            level = POST_OD[kb]
            phase = ('后置', level)
            od_value = level
        else:
            od_value = 0

        turn = int(op.get('turnNumber') or 0)
        bonus = int(op.get('overDriveNumber') or 0)
        additional = int(op.get('additionalCount') or 0)
        label = f'T{turn}'
        if phase is not None and (trigger or kb in POST_OD or bonus > 0):
            kind, level = phase
            label += f'-{kind}OD{level}'
            if kind == '前置':
                # Trigger row has bonus=0 but represents the first pre-OD action.
                label += f'-bonus{max(1, bonus)}'
            elif bonus == 0:
                label += '-OD前'
            else:
                label += f'-bonus{bonus}'
        if additional:
            label += '-追加'

        actions = []
        for style_id, action in zip(op['placeStyle'][:3], op['selectSkill'][:3]):
            style_id = int(style_id)
            skill_id = int(action.get('skill_id') or 0)
            num = skill_slots[style_id].get(skill_id, 0)
            target_id = action.get('buffTargetCharaId')
            target = 0
            if num != 0 and target_id is not None:
                try:
                    target = char_slot.get(int(target_id), 0)
                    if not target:
                        warnings.append(f'操作 {op_no}: 目标角色ID {target_id} 不在队伍中，改为0')
                except (TypeError, ValueError):
                    warnings.append(f'操作 {op_no}: 非法目标角色ID {target_id!r}，改为0')
            actions.append(f'{name_by_style[style_id]}: {num},{target}')
        result.append(f'{label} = {od_value}; ' + '; '.join(actions))

    result.extend(['', '# HBRTool style metadata'])
    for slot, style_id in enumerate(style_ids, 1):
        info = style_info[style_id]
        character = info.get('character') or {}
        meta = {'team': info.get('team'), 'english': character.get('en'), 'id': info.get('style_id')}
        result.append(f'# HBRTOOL_STYLE {slot} ' + json.dumps(meta, ensure_ascii=False))
    return '\n'.join(result) + '\n', warnings


def main(sav_path, mapping_path=None, output_path=None):
    """将 HBR Tool 的 .sav 转为 .hbrf，可从其他 Python 文件直接调用。

    Args:
        sav_path: SAV 文件路径。
        mapping_path: 映射 JSON 路径；默认与本脚本同目录的 mapping.json。
        output_path: 输出路径；默认替换 SAV 后缀为 .hbrf。

    Returns:
        (output_path: pathlib.Path, warnings: list[str])
    """
    sav_path = Path(sav_path)
    mapping_path = (Path(mapping_path) if mapping_path is not None
                    else Path(__file__).resolve().with_name('mapping.json'))
    output_path = Path(output_path) if output_path is not None else sav_path.with_suffix('.hbrf')

    axis = decode_sav(sav_path)
    content, warnings = convert(axis, read_json(mapping_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return output_path, warnings


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sav', type=Path, help='网站导出的 SAV 路径')
    parser.add_argument('mapping', nargs='?', type=Path, help='mapping.json 路径（默认脚本目录）')
    parser.add_argument('-o', '--output', type=Path, help='输出 HBRF 路径')
    args = parser.parse_args()
    output, warnings = main(args.sav, args.mapping, args.output)
    print(f'输出: {output} | 警告: {len(warnings)}')
    for w in dict.fromkeys(warnings):
        print('[警告]', w)


if __name__ == '__main__':
    cli()
