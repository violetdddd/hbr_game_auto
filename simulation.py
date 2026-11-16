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
import dataclasses
from typing import Any, Dict, List, Optional, Union


JsonDict = Dict[str, Any]

ELEMENTS = ('fire','ice','thunder','light','dark')

PASSIVE_EFFECT_TYPES_NEEDED = {
    # 资源
    "resource",
    "token",
    "token_up_per_attack_enemy",
    "over_drive_rate_up",
    "reduce_consume_overdrive",
    # SP / EP
    "overwrite_sp",
    "sp_limit_overwrite",
    "ep_limit_overwrite",
    "sp_modify",
    # 行动
    "additional_turn",
    "double_action_extra_skill",
    "double_attack_skill",
    "sprightly",
    # 影响后续条件判断的状态和场地
    "element_mark",
    "motivation",
    "zone",
    "mocktail",
    "talisman",
    "inscription",
    "rice_field_zone",
    "morale",
    "funnel",
    "buff_charge",
    "give_debuff_turn_up",
    "shadow_clone",
    "negative_mind",
    "infantilized",
    "high_boost",
    "arrow_cherry_blossoms",
    "dodge",
    "disaster",
    "provoke",
    "misfortune",
    "cover",
    "revenge"
}

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
            if effect.get('type') in PASSIVE_EFFECT_TYPES_NEEDED
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


def json_records_to_dict(path: Path, has_id=True) -> Dict[int, JsonDict]:
    """将 JSON 顶层记录按内部 id 建立索引，拒绝重复 id。"""
    with path.open('r', encoding='utf-8') as handle:
        records = json.load(handle)
        if not isinstance(records, dict):
            raise ValueError('数据库顶层必须是字典')
        if has_id:
            indexed = {}
            for value in records.values():
                if not isinstance(value, dict) or 'id' not in value:
                    raise ValueError('数据库记录缺少 id')
                key = int(value['id'])
                if key in indexed:
                    raise ValueError(f'数据库存在重复 ID: {key}')
                indexed[key] = value
            return indexed
        else:
            indexed = {}
            for key, value in records.items():
                indexed[int(key)] = value
            return indexed


@dataclass
class Skill:
    """skills.json 内 kind=active/system 的完整已知字段。"""
    id: int
    names: JsonDict
    kind: str
    cost: JsonDict = field(default_factory=dict)  # 记录原生cost字段
    cost_type: str = 'sp'
    default_cost: int = 0  # 记录没改动过的默认最高cost，非sp cost不用管，不会进行检查
    now_cost: int = 0  # 记录当前触发各种效果后的cost
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
        # 设置cost相关
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
    cases: Any = None
    cost: JsonDict = field(default_factory=dict)
    effects: Union[List[JsonDict], JsonDict] = field(default_factory=list)
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
    trigger_times: int = 0
    trigger_limit: Optional[int] = None
    skill_id: Optional[int] = None
    status_id: Optional[List[int]] = None

    @classmethod
    def from_record(cls, record: JsonDict) -> Optional['LimitBreak']:
        record = _filter_passive_record(record)
        if record is None:
            return None

        data = _record_kwargs(cls, record)
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
    element: Optional[str] = None
    duration_type: Optional[str] = None
    remaining: Optional[int] = None
    level: Optional[int] = None
    source: Optional[int] = None
    data: dict = field(default_factory=dict)  # 通用字段，储存特殊的status

    def to_dict(self):
        return {"id": self.id, "name": self.name, "duration_type": self.duration_type, "remaining": self.remaining, "level": self.level, "element": self.element, "source": self.source}

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
    # 提前计算默认的技能，普攻/指挥，无，追击
    basic_skills: List[dict] = field(default_factory=list)

    # 角色的动态资源与修正，不在这里执行计算。
    special_trigger: str = None  # 是否需要检测破盾以及专属技能（鬼神化、小按钮、总攻击）或机制（超越量表、切换形态）
    od_rate_extra: float = 0.0  # 光月歌共鸣和鱼大师被动，在battle_start()中储存, 例如鱼为0.05
    od_earring: int = 15
    slot: int = 0
    # 每次攻击前根据各种状态动态计算
    sp_modify: int = 0 
    # 每回合的状态
    sp: int = 0
    sp_limit: int = 20
    ep: int = 0
    ep_limit: int = 10
    token: int = 0
    dp: float = 100.0  # 范围是0-150
    statuses: List[Status] = field(default_factory=list)

    @staticmethod
    def generate_default_skills_from_skill(skill: Skill) -> dict:
        return {"name": skill.names["zh_cn"], "id": skill.id, "cost": 0, "cost_type": "sp",
                "target_type": "ignore", "user_select": None}

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
    ) -> Style:
        """装配已选择技能/解锁突破；不会推断 SP/EP/状态的战斗规则。"""
        data = {k: deepcopy(record[k]) for k in ('id', 'names', 'character_names', 'team', 'tier', 'elements', 'role', 'attack_type')}
        instance = cls(**data, od_earring=od_earring)
        # 检测char独特的技能/机制
        special = record.get("special")
        if special:
            instance.special_trigger = special.get("type")
        # 读入当前突破下解锁的突破被动，跳过已经升级的小被动
        for level, entries in record.get('limit_break', {}).items():
            level = int(level)
            if level > break_level:
                continue
            for entry in entries:
                discard_level = entry.get('discard_limit_level')
                if (discard_level is not None and break_level >= int(discard_level)):
                    continue
                # from_record会过滤掉那些ignore的effect
                passive = LimitBreak.from_record(entry)
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
            # 共鸣被动只装备给 SSR 上场风格。
            support = resonance_record.get('support_skill')
            if instance.tier == 'SSR' and support:
                passive = SupportSkill.from_record(support)
                if passive is not None:
                    if resonance_break_level is None or not 0 <= resonance_break_level <= 4:
                        raise ValueError(f"无效的共鸣突破等级: {resonance_break_level}")
                    for effect in passive.effects:
                        if isinstance(effect.get('value'), list):
                            effect['value'] = effect['value'][resonance_break_level]
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
        # 舰长的行动为指挥+无+追击，其他为普攻+无+追击
        basic_ids = (2 if instance.role == 'admiral' else 1, 0, 3)
        instance.basic_skills = [
            cls.generate_default_skills_from_skill(
                Skill.from_record(skill_records[skill_id])
            ) for skill_id in basic_ids
        ]
        # 根据项链更改初始sp
        instance.sp = necklace_sp
        return instance


@dataclass
class Monster:
    exist: bool
    position: int  # 0 起始；敌人位置不随回合交换
    statuses: List[Status] = field(default_factory=list)
    down: bool = False
    damage_rate: int = 100


@dataclass
class Battle:
    enemy_weaknesses: List[str] = dataclasses.field(default_factory=list)
    monsters: List[Monster] = dataclasses.field(default_factory=list)
    field: dict = dataclasses.field(default_factory=lambda: {"value": None, "left_turn": -1})  # 无、元素、稻场、其他
    territory: Optional[int] = None
    global_od_rate: float = 100.0
    super_scale: dict = dataclasses.field(default_factory=lambda: {"element": None, "value": 0})  # 超越量表
    od_consume: int = 100

@dataclass
class Turn:
    """GUI 与 Simulation 交换的战斗快照；结算应另在 Simulation 引擎实现。"""
    battle: Battle
    team: List[Style] = field(default_factory=list)  # 永远按照slot顺序0-5排布
    turn_num: int = 1  # 记录当前第几回合
    actions: List[Dict] = field(default_factory=list)  # 记录当前回合的行动
    od: float = 0.0  # 百分比下保留2位小数
    predicted_od: float = 0.0  # 百分比下保留2位小数，用于真正返回预测od值
    stage_tmp_od: float = 0.0  # 百分比下保留2位小数，用于给apply_effect暂存
    od_timing: Optional[str] = None  # None, before, after
    od_level: int = 0
    additional_turn: bool = False
    bonus: int = 0
    order: List[int] = field(default_factory=lambda: list(range(6)))

@dataclass
class Context:
    turn: Turn
    subject: Style | Monster | None

class Conditions:
    @staticmethod
    def front(ctx: Context):
        return ctx.subject.slot in ctx.turn.order[:3]

    @staticmethod
    def has(ctx: Context, status_id: int):
        return any(status.id == status_id for status in ctx.subject.statuses)

    @staticmethod
    def dp_rate(ctx: Context):
        return ctx.subject.dp / 100

    @staticmethod
    def element(ctx: Context, need_element: str):
        return need_element in ctx.subject.elements

    @staticmethod
    def used(ctx: Context, skill_id: int):
        for skill in ctx.subject.active_skills:
            if skill.id == skill_id:
                return skill.used
        return 0

    @staticmethod
    def level(ctx: Context, status_id: int):
        for status in ctx.subject.statuses:
            if status.id == status_id:
                return status.level
        return 0

    @staticmethod
    def weak(ctx: Context, need_element: str):
        return need_element in ctx.turn.battle.enemy_weaknesses
    
    @staticmethod
    def sp(ctx: Context):
        return ctx.subject.sp

    @staticmethod
    def zone(ctx: Context, need_element_s: str):
        if need_element_s == "elements":
            return ctx.turn.battle.field["value"] in ELEMENTS
        elif need_element_s == "none":
            return not ctx.turn.battle.field["value"]
        elif need_element_s in ELEMENTS:
            return ctx.turn.battle.field["value"] == need_element_s

    @staticmethod
    def during_down_turn(ctx: Context):
        return ctx.subject.down

    @staticmethod
    def token(ctx: Context):
        return ctx.subject.token

    @staticmethod
    def character(ctx: Context, need_eng_name: str):
        return ctx.subject.character_names.get("en") == need_eng_name
    
    @staticmethod
    def in_od(ctx: Context):
        return ctx.turn.od_level != 0
    
    @staticmethod
    def turn(ctx: Context):
        return ctx.turn.turn_num
    
    @staticmethod
    def skill_sp(ctx: Context):
        slot = ctx.subject.slot
        action_skill_id = ctx.turn.actions[slot].get("id")
        for skill in ctx.subject.active_skills:
            if skill.id == action_skill_id:
                return skill.now_cost
        raise ValueError("程序不应该运行到这里，请检查数据库字段")

    @staticmethod
    def normal_attack(ctx: Context):
        slot = ctx.subject.slot
        action_skill_id = ctx.turn.actions[slot].get("id")
        return action_skill_id == 1

    @staticmethod
    def is_team(ctx: Context, need_team: str):
        return ctx.subject.team == need_team

    @staticmethod
    def damage_rate(ctx: Context):
        return ctx.subject.damage_rate

    @staticmethod
    def mark_level(ctx: Context, need_element: str):
        for style in ctx.turn.team:
            for status in style.statuses:
                if status.id == 166 and status.element == need_element:
                    return status.level
        return 0

    @staticmethod
    def od(ctx: Context):
        return ctx.turn.od

    @staticmethod
    def role(ctx: Context, need_role: str):
        return ctx.subject.role == need_role

    @staticmethod
    def ep(ctx: Context):
        return ctx.subject.ep

    # 温泉通行木牌，特殊情况在后续函数中解析 
    # @staticmethod
    # def has_skill(ctx: Context, skill_id: int):

    @staticmethod
    def territory_is(ctx: Context, territory_id: int):
        return ctx.turn.battle.territory == territory_id

# AST语法树解析
import ast
import operator
from dataclasses import replace
OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
def check(expr, ctx):
    """检测数据库语句函数是否为真"""
    def run(node, ctx):
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.BoolOp):
            values = (run(x, ctx) for x in node.values)
            return all(values) if isinstance(node.op, ast.And) else any(values)

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not run(node.operand, ctx)

        if isinstance(node, ast.Compare):
            left = run(node.left, ctx)
            for op, right_node in zip(node.ops, node.comparators):
                right = run(right_node, ctx)
                if not OPS[type(op)](left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)

            if name in ('team.count', 'enemy.count'):
                group = ctx.turn.team if name == 'team.count' else ctx.turn.battle.monsters
                group = [x for x in group if getattr(x, 'exist', True)]

                if not node.args:
                    return len(group)

                return sum(
                    bool(run(node.args[0], replace(ctx, subject=x)))
                    for x in group
                )

            func = getattr(Conditions, name.replace('target.', ''))
            return func(ctx, *(run(arg, ctx) for arg in node.args))

        raise ValueError(f'不支持的条件语法：{ast.dump(node)}')

    return bool(run(ast.parse(expr, mode='eval').body, ctx))

# 按顺序遍历风格被动
def iter_passives(style: Style):
    yield from style.limit_break_passive
    yield from style.skill_passive
    if style.support_skill_passive is not None:
        yield style.support_skill_passive

# 获得target的列表
def resolve_targets(turn: Turn, owner: Style, target_type: str):
    front = [turn.team[i] for i in turn.order[:3]]
    sub = [turn.team[i] for i in turn.order[3:]]
    groups = {  # 采用lambda表达式，这样仅在实际选择了该lambda分支才运行
        "self": lambda: [owner],
        "ally_all": lambda: turn.team,
        "ally_front": lambda: front,
        "ally_sub": lambda: sub,
        "ally_all_without_self": lambda: [
            x for x in turn.team if x is not owner
        ],
        "ally_front_without_self": lambda: [
            x for x in front if x is not owner
        ],
        "all": lambda: [
            x for x in turn.battle.monsters if x.exist
        ],
    }
    if target_type not in groups:
        raise ValueError(f"未知角色目标: {target_type}")
    return groups[target_type]()

class Simulation:
    """持有静态数据库与初始化后的 Turn。"""
    def __init__(self):
        self.skills_path = SIMULATION_DIR / 'skills.json'
        self.styles_path = SIMULATION_DIR / 'styles.json'
        self.statuses_path = SIMULATION_DIR / 'statuses.json'
        self.skill_records: Dict[int, JsonDict] = {}
        self.style_records: Dict[int, JsonDict] = {}
        self.status_records: Dict[int, JsonDict] = {}
        self.turns: List[Turn] = []
        self.initial_config: Optional[JsonDict] = None

    def turn_to_dict(self, turn: Turn) -> dict:
        """
        将 Turn 转换为 GUI 可序列化的字典。
        simulation_state = {
            'members': [{
            'sp': int, 'token': int, "ep": int, 'dp': float, "special_trigger": str | None,
            'statuses': [{
                "id": int, "name": str, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None
            }, ... ],
            "skills": [{"name": str, "cost_type": str, "cost": int, "id": int, "target_type": str, "user_select": None | [str]}, ... ] 
            } for _ in range(6)],
            'order': [int] * 6,
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int, "on_break": False}] * 6,
            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool, "statuses": [
            {"id": int, "name": str, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None}, ...
            ]} for _ in range(3)],
            'enemy_weaknesses': [str],
            "super_scale" = {"element": None, "value": 0},
            'field': str or None,
            "turn" : int,
            'od': float,
            'predicted_od': float,
            'od_timing': str or None,
            'od_level': int,
            'bonus': int,
            'additional_turn': bool,
            "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0}
        其中，技能的第0个为默认主动技能，第1个为默认被动技能（无），第2个为追击，普通攻击默认无目标
        """
        return asdict(turn)

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

        # 加载3个数据库；只使用记录内部的 id 进行索引。
        skill_records = json_records_to_dict(self.skills_path)
        style_records = json_records_to_dict(self.styles_path)
        status_records = json_records_to_dict(self.statuses_path, has_id=False)

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
        if sum(1 for sid in style_ids if style_records.get(sid)["role"] == "admiral") > 1:
            raise ValueError('上场的admiral风格不能多于一个')

        # 解析每一个上场风格的技能和共鸣风格的id，传入Style.from_record进行进一步解析
        result_styles = []
        for slot, entry in enumerate(styles_config):
            sid = style_ids[slot]
            active_ids = entry.get('active_skill_ids', [])
            orb_ids = entry.get('orb_skill_ids', [])
            passive_ids = entry.get('passive_skill_ids', [])
            selected_active = [skill_id for skill_id in dict.fromkeys(active_ids + orb_ids) if skill_id not in (0, 1, 2, 3)]
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
            style = Style.from_record(
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
            )
            style.slot = slot
            result_styles.append(style)

        default_enemy_config = {1: (1,), 2: (1,2), 3: (0,1,2)}
        battle = Battle(
            enemy_weaknesses=list(dict.fromkeys(weaknesses)),
            monsters=[Monster(position=i, exist=i in default_enemy_config[enemy_count]) for i in range(3)],
            global_od_rate=global_od_rate,
        )
        turn = Turn(
            battle=battle,
            team=result_styles,
            od=initial_od,
        )
        # 只在全部构造成功后提交，避免部分初始化失败污染旧战斗。
        self.skill_records = skill_records
        self.style_records = style_records
        self.status_records = status_records
        self.initial_config = config
        self.turns = [turn]
        return turn

    # 实际应用的被动触发函数，给出在某个时间节点的触发str即可
    def trigger_passives(self, turn: Turn, trigger: str):
        order = deepcopy(turn.order)
        order[0], order[1] = order[1], order[0]  # 触发顺序是position的1，0，2，3，4，5
        for slot in order:
            style = turn.team[slot]
            if trigger in style.passive_triggers:
                for passive in iter_passives(style):
                    # 判断trigger时机
                    if passive.trigger != trigger:
                        continue
                    # 判断trigger condition是否满足
                    ctx = Context(turn=turn, subject=style)
                    if (passive.trigger_condition and not check(passive.trigger_condition, ctx)):
                        continue
                    # 检查触发次数
                    if isinstance(passive, LimitBreak) and passive.trigger_limit is not None:
                        if passive.trigger_times >= passive.trigger_limit:
                            continue
                        else:
                            passive.trigger_times += 1
                    # 解析是否有case等结构，返回实际生效的effect列表
                    effects = self.resolve_passive_effects(passive, ctx)
                    # 对每个effect判断和应用效果
                    for effect in effects:
                        self.apply_effect(turn, style, effect)

    # 解析passive的结构，提取实际生效的effect列表
    def resolve_passive_effects(self, passive, ctx):
        effects = passive.effects
        # 普通list结构
        if isinstance(effects, list):
            return effects
        # cases结构
        if "cases" in effects:
            for case in effects["cases"]:
                if check(case["when"], ctx):
                    return case["effects"]
            return []
        # 未知结构
        raise ValueError(f"未知被动效果结构: {effects}")

    def apply_effect(self, turn: Turn, owner: Style, effect: dict, source=None):
        effect_type = effect["type"]
        target_type = effect.get("target", "self")

        # 全局目标单独处理；其余统一解析为 Style / Monster 列表
        if target_type in ("od", "field"):
            targets = []
        else:
            targets = resolve_targets(turn, owner, target_type)
            # 每个目标分别判断 target_condition
            condition = effect.get("target_condition")
            if condition:
                targets = [
                    target for target in targets
                    if check(condition, Context(turn=turn, subject=target))
                ]

        # 创建 / 更新状态
        def add_status(target, *, level=None, max_level=None, unique=False):
            status_id = effect.get("status_id")
            if status_id is None:
                raise ValueError(f"{effect_type} 缺少 status_id")
            status_information = self.status_records.get(status_id)
            duration = effect.get("duration", {})
            duration_type = duration.get("type")
            remaining = duration.get("value")
            # 属性印记相同属性不叠加层数直接跳过，不同属性可以正常添加状态
            if status_id == 166:
                same_element = next(
                    (s for s in target.statuses if s.id == status_id and s.element == (effect.get("elements") or [None])[0]),
                    None
                )
                if same_element: return same_element
            # 叠层或者无法存在多个的statuses，不产生新status直接return
            if unique or (level is not None and status_id != 166):
                old = next(
                    (s for s in target.statuses if s.id == status_id),
                    None
                )
                # 不重复添加
                if unique and old is not None:
                    return old
                # 叠加层数
                elif level is not None and old is not None:
                    level += old.level
                    if max_level is not None:
                        level = min(level, max_level)
                    old.level = level
                    return old
            # 新上的status
            status = Status(
                id=status_id,
                category=status_information.get("category"),
                name=status_information.get("zh_cn"),
                element=(effect.get("elements") or [None])[0],
                duration_type=duration_type,
                remaining=remaining,
                level=level,
                source=source,
                data=deepcopy(effect),
            )
            target.statuses.append(status)
            return status

        match effect_type:
            # ==================== 资源 ====================
            case "resource":
                # random 暂不随机化：默认触发
                if target_type == "od":
                    value = effect.get("od", 0)
                    if isinstance(value, list):
                        raise ValueError("OD 数值尚未按共鸣等级展开")
                    turn.stage_tmp_od += value
                else:
                    for target in targets:
                        if "sp" in effect:
                            limit = effect.get("limit", target.sp_limit)
                            target.sp = min(target.sp + effect["sp"], limit)

                        if "ep" in effect:
                            target.ep = max(0, min(target.ep + effect["ep"], target.ep_limit))
            case "token":
                for target in targets:
                    target.token = max(0, min(target.token + effect.get("level", 0), 10))
            case "token_up_per_attack_enemy":
                # 根据攻击命中的敌人数增加 Token
                for target in targets:
                    action = turn.actions[target.slot]
                    target_type = action["target"]["type"]
                    if target_type == "single" or action["id"] == 1:
                        token_added = 1
                    elif target_type == "all":
                        token_added = sum(1 for monster in turn.battle.monsters if monster.exist)
                    else:
                        token_added = 0
                    target.token = max(0, min(target.token + token_added * effect.get("value", 1), 10))
            case "over_drive_rate_up":
                for target in targets:
                    target.od_rate_extra += effect["value"] / 100
            case "reduce_consume_overdrive":
                turn.battle.od_consume = max(0, turn.battle.od_consume - effect["value"])

            # ==================== SP / EP 修正 ====================
            case "overwrite_sp":
                # 记录技能费用覆盖规则，不立即修改 now_cost
                # TODO: 计算技能费用时判断 condition 并读取 skill_id、sp
                for target in targets:
                    add_status(target)
            case "sp_limit_overwrite":
                value = effect.get("value", 20)
                for target in targets:
                    target.sp_limit = value
                    # 暂时没有向下调整的和非永久的sp_limit，SP 已有值不强制降低
                    # add_status(target)
            case "ep_limit_overwrite":
                for target in targets:
                    target.ep_limit = effect["value"]
                    add_status(target)
            case "sp_modify":
                for target in targets:
                    add_status(target)  # advance中根据这些status决定style的sp_modify数值

            # ==================== 特殊状态 ====================
            case "additional_turn":
                # TODO: 在下一阶段检查追加回合状态并安排额外行动
                for target in targets:
                    add_status(target, unique=True)
            case "double_action_extra_skill":
                # EX 技能双动，在执行 EX 技能时消费
                for target in targets:
                    add_status(target, unique=True)
            case "double_attack_skill":
                # 攻击双动
                # TODO: 在行动结算时处理
                for target in targets:
                    add_status(target, unique=True)
            # 以下三个在替换基础技能时特殊处理
            # case "replace_normal_skill":
            # case "replace_pursuit":
            # case "always_persuit_sp8":
            case "sprightly":
                for target in targets:
                    add_status(target)
            case "give_debuff_turn_up":
                # 不建议直接永久修改 active_skills 内的数据库效果
                # 改为注册修正状态，施加 Debuff 时增加 enemy_turn
                # TODO: 在 Debuff 实际施加时：
                # duration += 所有生效的 give_debuff_turn_up.value
                for target in targets:
                    add_status(target)
            case "element_mark":
                # 对应属性的队员人数决定层数，最大6层
                element = (effect.get("elements") or [None])[0]
                level = sum(element in style.elements for style in turn.team)
                for target in targets:
                    add_status(target, level=level, max_level=6)
            case "zone":
                element = (effect.get("elements") or [None])[0]
                duration = effect.get("duration", {})
                turn.battle.field["value"] = element
                turn.battle.field["left_turn"] = (
                    duration.get("value", -1)  # 没有value则为permanent，填-1认为永久
                )
            case "rice_field_zone":
                turn.battle.field["value"] = "rice_field"
                turn.battle.field["left_turn"] = -1
            case "funnel":
                # mode = {"value": int, "number": int}
                # 原始参数保存在 Status.data 中
                for target in targets:
                    add_status(target)

            # ==================== 普通状态 ====================
            case "motivation":
                for target in targets:
                    add_status(target, level=effect.get("level", 1), max_level=5,)
            case "mocktail":
                for target in targets:
                    add_status(target, unique=True)
            case "talisman":
                for target in targets:
                    add_status(target, level=effect.get("level", 0))
            case "inscription":
                for target in targets:
                    add_status(target, level=effect.get("level", 0))
            case "morale":  # 这里共鸣会写value，但其他时候会写level
                for target in targets:
                    add_status(target, level=effect.get("level", effect.get("value", 1)), max_level=10,)
            case "buff_charge":
                for target in targets:
                    add_status(target, unique=True)
            case "shadow_clone":  # 不追踪该状态，因此暂时认为unique
                for target in targets:
                    add_status(target, unique=True)
            case "negative_mind":
                for target in targets:
                    add_status(target, unique=True)
            case "infantilized":
                for target in targets:
                    add_status(target, level=effect.get("level", 1), max_level=20,)
            case "high_boost":
                for target in targets:
                    add_status(target, unique=True)
            case "arrow_cherry_blossoms":
                for target in targets:
                    add_status(target, unique=True)
            case "dodge":  # 不追踪该状态，因此暂时认为unique
                for target in targets:
                    add_status(target, unique=True)
            case "disaster":
                for target in targets:
                    add_status(target, level=effect.get("level", 1), max_level=10,)
            case "provoke":
                for target in targets:
                    add_status(target)
            case "misfortune":
                for target in targets:
                    add_status(target, unique=True)
            case "cover":
                for target in targets:
                    add_status(target)
            case "revenge":
                for target in targets:
                    add_status(target, level=effect.get("level", 0), max_level=10,)

            # ==================== 未知类型 ====================
            case _:
                raise NotImplementedError(
                    f"未实现的被动效果类型: {effect_type}"
                )

    def battle_start(self, turn: Turn):
        """
        战斗开场要处理的被动等，刚进场时slot和position一致
        on battle start, on first battle start
        补齐超越量表和默认的action
        """
        actions = []
        super_element = None
        super_scale = 0
        # 前三名默认普通攻击，后三名默认无行动
        for style in turn.team:
            # 选取默认行动
            default_skill = style.basic_skills[0 if style.slot < 3 else 1]
            actions.append({
                'name': default_skill['name'],
                'id': default_skill['id'],
                'target': {
                    'type': "ignore",
                    'slot': None,
                },
                'user_selected': None,
                "on_break": False
            })
            # 检测超越量表
            special_trigger = style.special_trigger
            if special_trigger == "elemental_admiral":
                super_element = style.elements[0]
        # 超越量表开局数值计算
        if super_element:
            for style in turn.team:
                if super_element in style.elements:
                    super_scale += 15
        turn.actions = actions
        turn.battle.super_scale["element"] = super_element
        turn.battle.super_scale["value"] = super_scale
        # 先结算on_battle_start
        self.trigger_passives(turn, "on_battle_start")
        # 再结算on_first_battle_start
        self.trigger_passives(turn, "on_first_battle_start")

    def advance(self, last_state) -> dict:
        """根据当前GUI传回的state计算下一回合的开始的state；不修改传入对象。"""
        return deepcopy(last_state)  # TODO: 实现战斗结算逻辑

    def first_turn(self, state: dict) -> dict:
        """测试版：初始化战斗并生成 GUI 所需的首回合状态。"""
        turn = self.initialize(state)
        self.battle_start(turn)

        members = []
        
        # 测试用基础行动
        for slot, style in enumerate(turn.team):
            skills = deepcopy(style.basic_skills)  # 3个，默认的顺序为：前排默认技能，无，追击
            # initialize() 已经装入全部被选择的主动/光球技能
            for skill in style.active_skills:
                # 处理target type，GUI仅需要知道是敌人还是友方（是否可选自己）
                if skill.target in ("ally_single", "ally_single_without_self", "ally_single_front_without_self"):
                    target_type = skill.target
                elif skill.target == "single":
                    target_type = "enemy"
                else:
                    target_type = "ignore"
                # 处理user_select
                if skill.user_select == None:
                    user_select = None
                else:
                    user_select = [u["description"] for u in skill.user_select.values()]

                skills.append({
                    'name': skill.names.get('zh_cn'),
                    'id': skill.id,
                    'cost_type': skill.cost_type,
                    'cost': skill.now_cost,
                    'target_type': target_type,
                    'user_select': user_select,
                })

            members.append({
                'sp': style.sp,
                'ep': style.ep,
                'token': style.token,
                'dp': style.dp,
                'statuses': [status.to_dict() for status in style.statuses],
                'skills': skills,
                "special_trigger": style.special_trigger
            })

        # GUI 中三个敌人位置始终存在，使用 exist 标记实际敌人
        enemies = [{'exist': False, 'damage_rate': 100, 'down': False, 'statuses': [],} for _ in range(3)]

        for monster in turn.battle.monsters:
            position = monster.position
            enemies[position] = {
                'exist': monster.exist,
                'damage_rate': monster.damage_rate,
                'down': monster.down,
                'statuses': deepcopy(monster.statuses),
            }

        return {
        'members': members,
        'order': list(range(6)),
        'actions': turn.actions,
        'enemies': enemies,
        'enemy_weaknesses': deepcopy(turn.battle.enemy_weaknesses),
        "super_scale": deepcopy(turn.battle.super_scale),
        'field': turn.battle.field["value"],
        'turn': turn.turn_num,
        'od': float(turn.od),
        'predicted_od': float(turn.od)+100,
        'od_timing': None,
        'od_level': 0,
        'bonus': 0,
        'additional_turn': False,
        "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0}
    }

    def recalculate(self, gui_add_state, turn_number):
        """
        接受gui传入的state并直接覆盖当前的Turn类对应值：
        gui_add_state = {
            "member_status": [{"id": int, "name": str, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None}] * 6,
            'order': [int] * 6,
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int, "on_break": False}] * 6,
            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool, "statuses": [
            {"id": int, "name": str, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None}, ...
            ]} for _ in range(3)],
            'field': str or None,
            'od_timing': str or None,
            'od_level': int,
            "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0}
        }
        重新计算从turn start开始计算后返回可能改变的值
        simulation_state = {
            'members': [{
            'sp': int, 'token': int, "ep": int, 'dp': float, "special_trigger": str | None,
            'statuses': [{
                "id": int, "name": str, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None
            }, ... ],
            "skills": [{"name": str, "cost_type": str, "cost": int, "id": int, "target_type": str, "user_select": None | [str]}, ... ] 
            } for _ in range(6)],
            'od': float,
            'predicted_od': float,
            'bonus': int
            "super_scale": {"element": None, "value": 0},
        }
        """


__all__ = ['Simulation', 'Skill', 'Passive', 'LimitBreak', 'SupportSkill', 'Style', 'Monster', 'Battle', 'Turn', 'Status']
