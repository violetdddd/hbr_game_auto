"""
HBR Simulation 的数据模型（暂不包含战斗结算）。

数据库来源：skills(20261106-033348).json、styles(6).json。
数据库 ID 是唯一查找标识；名称只用于展示。
Python >= 3.9。
"""
from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Union


JsonDict = Dict[str, Any]
SkillId = int

IGNORED_PASSIVE_EFFECT_TYPES = [
    "all_status_up_value",
    "attack_up_per_token",
    "border_ref_p_down_by_admiral",
    "break_guard",
    "critical_rate_up",
    "damage_rate_up",
    "damage_rate_up_per_token",
    "debuff_guard",
    "defense_up",
    "defense_up_per_token",
    "give_defense_debuff_up",
    "give_heal_up",
    "heal_dp_rate",
    "invincible",
    "makeup",
    "power_up_value",
    "revive_dp_rate",
    "stun_random",
    "toughness_up_value",
    "toughness_up_value_per_revenge_level",
    "remove_special_status",
    "skill_limit_count_up",
    "break_down_turn_up"
]

from paths import ROOT_DIR
SIMULATION_DIR = ROOT_DIR / 'assets' / 'simulation'

def _record_kwargs(cls, record: JsonDict) -> JsonDict:
    """保留数据库已有字段；不修改传入 JSON 对象。"""
    valid = {item.name for item in fields(cls) if item.init}
    return {key: deepcopy(value) for key, value in record.items() if key in valid}

def _filter_passive_effects(effects):
    """过滤无需模拟的被动效果，保留其余效果及条件分支。"""

    if isinstance(effects, list):
        return [
            deepcopy(effect)
            for effect in effects
            if effect.get('type') not in IGNORED_PASSIVE_EFFECT_TYPES
        ]

    if isinstance(effects, dict):
        result = deepcopy(effects)
        # 是cases的情况
        if 'cases' in result:
            result['cases'] = [
                {
                    **case,
                    'effects': _filter_passive_effects(case.get('effects', []))
                }
                for case in result['cases']
            ]
            return result if any(case['effects'] for case in result['cases']) else {}
        # conditions的情况
        for key in ('yes', 'no'):
            if key in result:
                result[key] = _filter_passive_effects(result[key])

        return result if any(result.get(k) for k in ('yes', 'no')) else {}

    return []

def _filter_passive_record(record):
    """返回过滤后的记录；没有有效效果则返回 None。"""
    data = deepcopy(record)
    data['effects'] = _filter_passive_effects(data.get('effects', []))

    if not data['effects']:
        return None

    return data

def _index_by_id(records: Dict[str, JsonDict]) -> Dict[int, JsonDict]:
    """将 JSON 顶层记录按内部 id 建立索引，拒绝重复 id。"""
    if not isinstance(records, dict):
        raise ValueError('数据库顶层必须是字典')
    indexed = {}
    for value in records.values():
        if not isinstance(value, dict) or 'id' not in value:
            raise ValueError('数据库记录缺少 id')
        key = int(value['id'])
        if key in indexed:
            raise ValueError(f'数据库存在重复 ID: {key}')
        indexed[key] = value
    return indexed


@dataclass
class Skill:
    """skills.json 内 kind=active/system 的完整已知字段。"""
    id: int
    names: JsonDict
    kind: str
    cost: JsonDict = field(default_factory=dict)
    cost_type: str = 'sp'
    default_cost: int = 0
    now_cost: int = 0
    used: int = 0
    target: Optional[str] = None
    effects: Union[List[JsonDict], JsonDict] = field(default_factory=list)
    elements: List[str] = field(default_factory=list)
    attack_type: Optional[str] = None
    cases: Any = None
    conditions: JsonDict = field(default_factory=dict)
    ex_skill: Optional[bool] = None
    hit_count: Any = None
    interval_turn: Any = None
    link: Any = None
    on_break: Any = None
    parent_id: Optional[int] = None
    user_select: Any = None

    @classmethod
    def from_record(cls, record: JsonDict) -> 'Skill':
        if record.get('kind') not in ('active', 'system'):
            raise ValueError(f"Skill 只能读取 active/system，收到 {record.get('kind')!r}")
        data = _record_kwargs(cls, record)
        cost = data.get('cost') or {}
        if 'yes' in cost and 'no' in cost:
            data['cost_type'] = 'sp'
            data['default_cost'] = max(
                cost['yes'].get('sp', 0), cost['no'].get('sp', 0)
            )
        else:
            data['cost_type'] = ('sp' if 'sp' in cost else cost.get('resource', 'sp'))
            data['default_cost'] = cost.get(data['cost_type'], 0)  # 只有cost_type为sp时有意义
        data['now_cost'] = data['default_cost']
        data['used'] = 0
        return cls(**data)


@dataclass
class Passive:
    """skills.json 内 kind=passive 的完整已知字段。"""
    id: int
    names: JsonDict
    kind: str = 'passive'
    attack_type: Optional[str] = None
    cases: Any = None
    cost: JsonDict = field(default_factory=dict)
    effects: Union[List[JsonDict], JsonDict] = field(default_factory=list)
    elements: List[str] = field(default_factory=list)
    trigger: Optional[str] = None
    trigger_condition: Optional[str] = None
    variants: Any = None

    @classmethod
    def from_record(cls, record: JsonDict) -> Optional['Passive']:
        if record.get('kind') != 'passive':
            raise ValueError(f"Passive 只能读取 passive，收到 {record.get('kind')!r}")

        record = _filter_passive_record(record)
        if record is None:
            return None

        data = _record_kwargs(cls, record)
        return cls(**data)

@dataclass
class LimitBreak:
    """一条 styles.json 中的 limit_break[突破等级] 被动。"""
    id: int
    name: str
    trigger: str
    trigger_condition: Optional[str] = None
    effects: List[JsonDict] = field(default_factory=list)
    unlock_level: int = 0

    discard_limit_level: Optional[int] = None
    trigger_limit: Optional[int] = None
    skill_id: Optional[int] = None
    status_id: Optional[List[int]] = None

    @classmethod
    def from_record(cls, record: JsonDict, unlock_level: int) -> Optional['LimitBreak']:
        record = _filter_passive_record(record)
        if record is None:
            return None

        data = _record_kwargs(cls, record)
        data['unlock_level'] = int(unlock_level)
        return cls(**data)


@dataclass
class SupportSkill:
    """一条 styles.json 中的 support_skill；effects 保留数据库原始 value 数组。"""
    name: str
    kind: str = 'support'
    trigger: Optional[str] = None
    trigger_condition: Optional[str] = None
    effects: List[JsonDict] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: JsonDict) -> Optional['SupportSkill']:
        record = _filter_passive_record(record)
        if record is None:
            return None

        data = _record_kwargs(cls, record)
        return cls(**data)

@dataclass
class Status:
    id: int
    category: str
    name: str
    duration_type: Optional[str] = None
    remaining: Optional[int] = None
    level: int = 0

@dataclass
class Style:
    """一名上场风格的静态配置与动态战斗资源。"""
    id: int
    names: JsonDict
    character_names: JsonDict
    team: str
    tier: str
    elements: List[str] = field(default_factory=list)
    role: Optional[str] = None
    attack_type: Optional[str] = None

    # 初始化后装入已达到解锁等级的突破被动、勾选的被动及主动技能。
    limit_break_passive: List[LimitBreak] = field(default_factory=list)
    skill_passive: List[Passive] = field(default_factory=list)
    support_skill_passive: Optional[SupportSkill] = None
    active_skills: List[Skill] = field(default_factory=list)
    # 保存所有可能的triggers，后续advance可以先检查该风格有没有trigger，若有再按顺序遍历limit_break_passive，skill_passive，support_skill_passive
    passive_triggers: List[str] = field(default_factory=list)

    # 角色的动态资源与修正，不在这里执行计算。
    od_rate: float = 1.0
    od_earring: int = 15
    necklace_sp: int = 3
    sp_modify: int = 0
    sp: int = 0
    ep: int = 0
    token: int = 0
    dp: float = 100.0
    statuses: List[Status] = field(default_factory=list)
    turn_action: Skill = None

    break_level: int = 0
    resonance_style_id: Optional[int] = None
    resonance_break_level: Optional[int] = None

    @classmethod
    def from_record(
        cls,
        record: JsonDict,
        *,
        break_level: int = 0,
        od_earring: int = 15,
        necklace_sp: int = 3,
        active_skill_ids: Optional[List[int]] = None,
        passive_skill_ids: Optional[List[int]] = None,
        skill_records: Optional[Dict[int, JsonDict]] = None,
        resonance_record: Optional[JsonDict] = None,
        resonance_break_level: Optional[int] = None,
    ) -> 'Style':
        """装配已选择技能/解锁突破；不会推断 SP/EP/状态的战斗规则。"""
        data = {k: deepcopy(record[k]) for k in
                ('id', 'names', 'character_names', 'team', 'tier', 'elements', 'role', 'attack_type')}
        instance = cls(**data, break_level=int(break_level),
                       od_earring=int(od_earring), necklace_sp=int(necklace_sp))
        # 读入当前突破下解锁的突破被动，跳过已经升级的小被动
        for level, entries in record.get('limit_break', {}).items():
            level = int(level)
            if level > instance.break_level:
                continue
            for entry in entries:
                discard_level = entry.get('discard_limit_level')

                if (discard_level is not None and instance.break_level >= int(discard_level)):
                    continue

                # from_record会过滤掉哪些ignore的effect
                passive = LimitBreak.from_record(entry, level)

                if passive is not None:
                    instance.limit_break_passive.append(passive)
        # 读入主动技能
        skill_records = skill_records or {}
        for skill_id in active_skill_ids or []:
            raw = skill_records[int(skill_id)]
            instance.active_skills.append(Skill.from_record(raw))
        # 由于在from_record中剔除了不需要模拟的ignore的effect，若被动有分支结构，可能导致某个分支的effect = []，后续要注意
        # 读入被动技能
        for skill_id in passive_skill_ids or []:
            raw = skill_records[int(skill_id)]
            passive = Passive.from_record(raw)
            if passive is not None:
                instance.skill_passive.append(passive)
        # 读入共鸣被动
        if resonance_record is not None:
            instance.resonance_style_id = int(resonance_record['id'])
            instance.resonance_break_level = resonance_break_level
            # 共鸣被动只装备给 SSR 上场风格。
            support = resonance_record.get('support_skill')
            if instance.tier == 'SSR' and support:
                passive = SupportSkill.from_record(support)
                if passive is not None:
                    level = instance.resonance_break_level
                    if level is None or not 0 <= level <= 4:
                        raise ValueError(f"无效的共鸣突破等级: {level}")
                    for effect in passive.effects:
                        if isinstance(effect.get('value'), list):
                            effect['value'] = effect['value'][level]
                    instance.support_skill_passive = passive
        instance.passive_triggers = list(dict.fromkeys(
            passive.trigger
            for passive in (
                instance.limit_break_passive
                + instance.skill_passive
                + ([instance.support_skill_passive] if instance.support_skill_passive else [])
            )
            if passive.trigger is not None
        ))
        if instance.role == "admiral":
            instance.turn_action = Skill.from_record(skill_records[int(2)])
        else: 
            instance.turn_action = Skill.from_record(skill_records[int(1)])
        return instance


@dataclass
class Team:
    styles: List[Style] = field(default_factory=list)

    def __post_init__(self):
        if len(self.styles) > 6:
            raise ValueError('Team 最多允许六个上场风格')

    def by_slot(self, slot: int) -> Style:
        """slot 为 0 起始的上场顺序，不是 GUI 当前站位。"""
        return self.styles[slot]


@dataclass
class Monster:
    position: int  # 0 起始；敌人位置不随回合交换
    statuses: List[Status] = field(default_factory=list)
    down: bool = False
    damage_rate: int = 100


@dataclass
class Battle:
    enemy_weaknesses: List[str] = field(default_factory=list)
    monsters: List[Monster] = field(default_factory=list)
    field: Optional[str] = None
    territory: Optional[str] = None
    global_od_rate: float = 100.0


@dataclass
class Turn:
    """GUI 与 Simulation 交换的战斗快照；结算应另在 Simulation 引擎实现。"""
    battle: Battle
    team: Team
    label: JsonDict = field(default_factory=dict)  # 例如 turn/bonus/od_level/additional_turn
    od: float = 0.0
    od_timing: Optional[str] = None  # None, before, after
    od_level: int = 0
    additional_turn: bool = False
    bonus: int = 0
    order: List[int] = field(default_factory=lambda: list(range(6)))


class Simulation:
    """持有静态数据库与初始化后的 Turn；此阶段不进行战斗结算。"""

    def __init__(self):
        self.skills_path = SIMULATION_DIR / 'skills.json'
        self.styles_path = SIMULATION_DIR / 'styles.json'
        self.skill_records: Dict[int, JsonDict] = {}
        self.style_records: Dict[int, JsonDict] = {}
        self.turn: Optional[Turn] = None
        self.initial_config: Optional[JsonDict] = None

    @staticmethod
    def _read_records(path: Path) -> Dict[int, JsonDict]:
        with path.open('r', encoding='utf-8') as handle:
            return _index_by_id(json.load(handle))

    @staticmethod
    def _ids(values, label: str) -> List[int]:
        if not isinstance(values, list):
            raise ValueError(f'{label} 必须是 ID 列表')
        # 去重且保留顺序；不要用技能名称查找数据库
        result = []
        seen = set()
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f'{label} 必须包含整数 simulation ID，收到 {value!r}')
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    def initialize(self, state: dict) -> Turn:
        """从战斗设置和数据库创建初始 Turn，不执行下一回合结算。

        state = {
            'styles': [{
                'style_id': int, 'break_level': int,
                'od_earring': int, 'necklace_sp': int,
                'active_skill_ids': [int], 'passive_skill_ids': [int],
                'orb_skill_ids': [int]
            }, ... 六项],
            'resonances': [None | {'style_id': int, 'break_level': int}, ... 六项],
            'enemy_count': 1..3,
            'enemy_weaknesses': ['fire', ...],
            'initial_od': float,
            'global_od_rate': float,
        }

        styles/resonances 对应同一 slot，0 起始；名字只用于展示。
        """

        # 先各种检查gui传入的state符合要求
        if not isinstance(state, dict):
            raise TypeError('initialize 的 state 必须是 dict')
        config = deepcopy(state)
        styles_config = config.get('styles')
        resonances_config = config.get('resonances', [None] * 6)
        if not isinstance(styles_config, list) or len(styles_config) != 6:
            raise ValueError('styles 必须正好包含六名上场风格')
        if not isinstance(resonances_config, list) or len(resonances_config) != 6:
            raise ValueError('resonances 必须是长度为 6 的列表（未选择为 None）')

        enemy_count = config.get('enemy_count', 1)
        if type(enemy_count) is not int or not 1 <= enemy_count <= 3:
            raise ValueError('enemy_count 必须为 1、2 或 3')
        weaknesses = config.get('enemy_weaknesses', [])
        if not isinstance(weaknesses, list) or any(not isinstance(e, str) for e in weaknesses):
            raise ValueError('enemy_weaknesses 必须是字符串列表')
        initial_od = float(config.get('initial_od', 0.0))
        global_od_rate = float(config.get('global_od_rate', 100.0))

        # 加载两个数据库；只使用记录内部的 id 进行索引。
        skill_records = self._read_records(self.skills_path)
        style_records = self._read_records(self.styles_path)

        # 此处保存style_ids并检测上场和共鸣风格能够匹配到数据库
        # 先校验选中风格是否重复，不限制共鸣与上场属于同一角色。
        style_ids = []
        resonance_ids = []
        for slot, (entry, resonance) in enumerate(zip(styles_config, resonances_config)):
            if not isinstance(entry, dict) or 'style_id' not in entry:
                raise ValueError(f'styles[{slot}] 缺少 style_id')
            sid = int(entry['style_id'])
            if sid not in style_records:
                raise ValueError(f'styles[{slot}] 无法找到风格 ID {sid}')
            style_ids.append(sid)
            if resonance is not None:
                if not isinstance(resonance, dict) or 'style_id' not in resonance:
                    raise ValueError(f'resonances[{slot}] 格式错误')
                rid = int(resonance['style_id'])
                if rid not in style_records:
                    raise ValueError(f'resonances[{slot}] 无法找到风格 ID {rid}')
                resonance_ids.append(rid)
        if len(set(style_ids)) != 6:
            raise ValueError('上场风格不能重复')
        if len(resonance_ids) != len(set(resonance_ids)):
            raise ValueError('共鸣风格不能重复')
        if set(style_ids).intersection(resonance_ids):
            raise ValueError('共鸣不能与任意上场风格重复')

        # 解析每一个上场风格的技能和共鸣风格的id，传入Style.from_record进行进一步解析
        result_styles = []
        for slot, entry in enumerate(styles_config):
            sid = style_ids[slot]
            active_ids = self._ids(entry.get('active_skill_ids', []), 'active_skill_ids')
            orb_ids = self._ids(entry.get('orb_skill_ids', []), 'orb_skill_ids')
            passive_ids = self._ids(entry.get('passive_skill_ids', []), 'passive_skill_ids')
            selected_active = list(dict.fromkeys(active_ids + orb_ids))
            # 查询主动技能是否存在
            for skill_id in selected_active:
                record = skill_records.get(skill_id)
                if record is None:
                    raise ValueError(f'slot {slot} 的主动技能 ID {skill_id} 不存在')
                if record.get('kind') not in ('active', 'system'):
                    raise ValueError(f'技能 {skill_id} 不是 active/system')
            # 查询被动技能是否存在
            for skill_id in passive_ids:
                record = skill_records.get(skill_id)
                if record is None:
                    raise ValueError(f'slot {slot} 的被动技能 ID {skill_id} 不存在')
                if record.get('kind') != 'passive':
                    raise ValueError(f'技能 {skill_id} 不是 passive')

            # 解析共鸣风格
            resonance = resonances_config[slot]
            resonance_record = (
                style_records[int(resonance['style_id'])]
                if resonance is not None else None
            )
            result_styles.append(Style.from_record(
                style_records[sid],
                break_level=int(entry.get('break_level', 0)),
                od_earring=int(entry.get('od_earring', 15)),
                necklace_sp=int(entry.get('necklace_sp', 3)),
                active_skill_ids=selected_active,
                passive_skill_ids=passive_ids,
                skill_records=skill_records,
                resonance_record=resonance_record,
                resonance_break_level=(
                    int(resonance.get('break_level', 0))
                    if resonance is not None else None
                ),
            ))

        battle = Battle(
            enemy_weaknesses=list(dict.fromkeys(weaknesses)),
            monsters=[Monster(position=i) for i in range(enemy_count)],
            global_od_rate=global_od_rate,
        )
        turn = Turn(
            battle=battle,
            team=Team(styles=result_styles),
            od=initial_od,
            label={'turn': 0, 'bonus': 0, 'od_level': 0, 'additional_turn': False},
        )
        # 只在全部构造成功后提交，避免部分初始化失败污染旧战斗。
        self.skill_records = skill_records
        self.style_records = style_records
        self.initial_config = config
        self.turn = turn
        return turn


__all__ = ['Simulation', 'Skill', 'Passive', 'LimitBreak', 'SupportSkill', 'Style',
           'Team', 'Monster', 'Battle', 'Turn', 'Status']
