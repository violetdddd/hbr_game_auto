"""HBR Simulation 的数据模型（暂不包含战斗结算）。

数据库来源：skills(20261106-033348).json、styles(6).json。
数据库 ID 是唯一查找标识；名称只用于展示。
Python >= 3.9。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Union


JsonDict = Dict[str, Any]
SkillId = int


def _record_kwargs(cls, record: JsonDict) -> JsonDict:
    """保留数据库已有字段；不修改传入 JSON 对象。"""
    valid = {item.name for item in fields(cls) if item.init}
    return {key: deepcopy(value) for key, value in record.items() if key in valid}


def _index_by_id(records: Dict[str, JsonDict]) -> Dict[int, JsonDict]:
    """允许 JSON 顶层以字符串 ID 为键，内部统一转换成整数 ID。"""
    return {int(value['id']): value for value in records.values()}


@dataclass
class Skill:
    """skills.json 内 kind=active/system 的完整已知字段。"""
    id: int
    names: JsonDict
    kind: str
    cost: JsonDict = field(default_factory=dict)
    cost_type: str
    default_cost: int
    now_cost: int
    used: int = 0
    target: Optional[str] = None
    effects: List[JsonDict] = field(default_factory=list)
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
    extra: JsonDict = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: JsonDict) -> 'Skill':
        if record.get('kind') not in ('active', 'system'):
            raise ValueError(f"Skill 只能读取 active/system，收到 {record.get('kind')!r}")
        data = _record_kwargs(cls, record)
        cost = data.get('cost') or {}
        if 'yes' in cost and 'no' in cost:
            data['default_cost'] = max(cost['yes'].get('sp', 0), cost['no'].get('sp', 0))
        else:
            data['default_cost'] = cost.get('sp', 0)
        data['cost_type'] = 'sp' if cost.get('sp') else cost.get('resource')
        data['extra'] = {k: deepcopy(v) for k, v in record.items() if k not in data}
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
    effects: List[JsonDict] = field(default_factory=list)
    elements: List[str] = field(default_factory=list)
    trigger: Optional[str] = None
    trigger_condition: Optional[str] = None
    variants: Any = None
    extra: JsonDict = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: JsonDict) -> 'Passive':
        if record.get('kind') != 'passive':
            raise ValueError(f"Passive 只能读取 passive，收到 {record.get('kind')!r}")
        data = _record_kwargs(cls, record)
        data['extra'] = {k: deepcopy(v) for k, v in record.items() if k not in data}
        return cls(**data)


@dataclass
class LimitBreak:
    """一条 styles.json 中的 limit_break[突破等级] 被动。"""
    id: Optional[int] = None
    name: str = ''
    trigger: Optional[str] = None
    trigger_condition: Optional[str] = None
    effects: List[JsonDict] = field(default_factory=list)
    unlock_level: int = 0
    extra: JsonDict = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: JsonDict, unlock_level: int) -> 'LimitBreak':
        data = _record_kwargs(cls, record)
        data['unlock_level'] = int(unlock_level)
        data['extra'] = {k: deepcopy(v) for k, v in record.items() if k not in data}
        return cls(**data)


@dataclass
class SupportSkill:
    """一条 styles.json 中的 support_skill；effects 保留数据库原始 value 数组。"""
    name: str
    kind: str = 'support'
    trigger: Optional[str] = None
    trigger_condition: Optional[str] = None
    effects: List[JsonDict] = field(default_factory=list)
    extra: JsonDict = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: JsonDict) -> 'SupportSkill':
        data = _record_kwargs(cls, record)
        data['extra'] = {k: deepcopy(v) for k, v in record.items() if k not in data}
        return cls(**data)


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

    # 角色的动态资源与修正，不在这里执行计算。
    od_rate: float = 1.0
    sp_modify: int = 0
    sp: float = 0.0
    ep: float = 0.0
    token: float = 0.0
    dp: float = 100.0
    statuses: List[int] = field(default_factory=list)

    break_level: int = 0
    resonance_style_id: Optional[int] = None
    resonance_break_level: Optional[int] = None

    @classmethod
    def from_record(
        cls,
        record: JsonDict,
        *,
        break_level: int = 0,
        active_skill_ids: Optional[List[int]] = None,
        passive_skill_ids: Optional[List[int]] = None,
        skill_records: Optional[Dict[int, JsonDict]] = None,
        resonance_record: Optional[JsonDict] = None,
        resonance_break_level: Optional[int] = None,
    ) -> 'Style':
        """装配已选择技能/解锁突破；不会推断 SP/EP/状态的战斗规则。"""
        data = {k: deepcopy(record[k]) for k in
                ('id', 'names', 'character_names', 'team', 'tier')}
        for key in ('elements', 'role', 'attack_type'):
            if key in record:
                data[key] = deepcopy(record[key])
        instance = cls(**data, break_level=int(break_level))
        for level, entries in record.get('limit_break', {}).items():
            if int(level) <= instance.break_level:
                for entry in entries:
                    instance.limit_break_passive.append(LimitBreak.from_record(entry, int(level)))

        skill_records = skill_records or {}
        for skill_id in active_skill_ids or []:
            raw = skill_records[int(skill_id)]
            instance.active_skills.append(Skill.from_record(raw))
        for skill_id in passive_skill_ids or []:
            raw = skill_records[int(skill_id)]
            instance.skill_passive.append(Passive.from_record(raw))

        if resonance_record is not None:
            instance.resonance_style_id = int(resonance_record['id'])
            instance.resonance_break_level = resonance_break_level
            # 共鸣被动只装备给 SSR 上场风格。
            support = resonance_record.get('support_skill')
            if instance.tier == 'SSR' and support:
                instance.support_skill_passive = SupportSkill.from_record(support)
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
    statuses: List[int] = field(default_factory=list)
    down: bool = False
    damage_rate: int = 100


@dataclass
class Battle:
    enemy_weaknesses: List[str] = field(default_factory=list)
    monsters: List[Monster] = field(default_factory=list)
    field: Optional[str] = None
    domain: Optional[str] = None


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

    def to_dict(self) -> JsonDict:
        """转成可 JSON 序列化的嵌套字典，供 GUI/存档传输。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: JsonDict) -> 'Turn':
        """从 GUI/JSON 快照重新建立数据对象。"""
        raw = deepcopy(data)
        raw['battle'] = Battle(
            **{**raw['battle'], 'monsters': [Monster(**m) for m in raw['battle'].get('monsters', [])]}
        )
        raw['team'] = Team(styles=[
            Style(
                **{**s,
                   'limit_break_passive': [LimitBreak(**v) for v in s.get('limit_break_passive', [])],
                   'skill_passive': [Passive(**v) for v in s.get('skill_passive', [])],
                   'support_skill_passive': (SupportSkill(**s['support_skill_passive'])
                                             if s.get('support_skill_passive') else None),
                   'active_skills': [Skill(**v) for v in s.get('active_skills', [])]}
            ) for s in raw['team'].get('styles', [])
        ])
        return cls(**raw)


__all__ = ['Skill', 'Passive', 'LimitBreak', 'SupportSkill', 'Style',
           'Team', 'Monster', 'Battle', 'Turn']
