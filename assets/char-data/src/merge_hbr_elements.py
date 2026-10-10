#!/usr/bin/env python3
"""Merge SeraphDB card ele into 12 existing team JSON files. Standard library only."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

TEAMS = ('31A', '31B', '31C', '30G', '31D', '31E', '31F', '31X', 'Command', 'P5R', '31AB', '19A')
SOURCE_TEAMS = {'Command': '司令部', 'P5R': 'PERSONA5R', '31AB': 'Angel Beats'}
ELEMENTS = {'Fire': '火', 'Light': '光', 'Thunder': '雷', 'Ice': '冰', 'Dark': '暗', 'Void': '虚'}

def read_json(path):
    with path.open(encoding='utf-8-sig') as f:
        return json.load(f)

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')

def build_index(characters):
    index = defaultdict(list)
    for character in characters:
        team = character.get('team')
        for card in character.get('cards', []):
            key = (team, card.get('name'))
            if not isinstance(card.get('ele'), list):
                continue
            index[key].append({'ele': card['ele'], 'card_id': card.get('id'), 'character': character.get('label')})
    return index

def merge_team(data, team, index, bilingual=False):
    stats = {'matched': 0, 'missing': [], 'ambiguous': [], 'invalid': []}
    source_team = SOURCE_TEAMS.get(team, team)
    for character_name, character in data.items():
        if not isinstance(character, dict):
            continue
        for style_name, style in character.get('style', {}).items():
            jp = style.get('names', {}).get('jp') or style.get('value')
            matches = index.get((source_team, jp), [])
            info = {'character': character_name, 'style': style_name, 'jp': jp}
            if len(matches) == 0:
                stats['missing'].append(info)
                continue
            if len(matches) > 1:
                stats['ambiguous'].append({**info, 'candidates': matches})
                continue
            ele = matches[0]['ele']
            if any(x not in ELEMENTS for x in ele):
                stats['invalid'].append({**info, 'ele': ele})
                continue
            style['ele'] = ele.copy()
            if bilingual:
                style['element'] = [{'zh': ELEMENTS[x], 'en': x.lower()} for x in ele]
            stats['matched'] += 1
    return stats

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('characters.json'))
    p.add_argument('--input-dir', type=Path, default=Path('.'))
    p.add_argument('--output-dir', type=Path, default=Path('with_elements'))
    p.add_argument('--bilingual', action='store_true', help='Also write element as a bilingual list')
    args = p.parse_args()
    index = build_index(read_json(args.source))
    report = {}
    for team in TEAMS:
        source_path = args.input_dir / (team + '.json')
        if not source_path.is_file():
            report[team] = {'status': 'file_not_found', 'path': str(source_path)}
            print(f'{team}: file not found ({source_path})')
            continue
        data = read_json(source_path)
        stats = merge_team(data, team, index, args.bilingual)
        output_path = args.output_dir / source_path.name
        write_json(output_path, data)
        report[team] = {'status': 'processed', 'output': str(output_path), **stats}
        print(f'{team}: {stats["matched"]} matched, {len(stats["missing"])} missing, '
              f'{len(stats["ambiguous"])} ambiguous, {len(stats["invalid"])} invalid -> {output_path}')
    write_json(args.output_dir / 'merge_report.json', report)
    print(f'Report: {args.output_dir / "merge_report.json"}')

if __name__ == '__main__':
    main()
