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
import math
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
    "makeup",
    "shadow_clone",
    "invincible",
    "negative_mind",
    "infantilized",
    "high_boost",
    "arrow_cherry_blossoms",
    "dodge",
    "disaster",
    "provoke",
    "misfortune",
    "cover",
    "revenge",
    "zone_up_eternal_plus_15",
    "b_i_yamawaki_servant",
    # 特殊替换，需要存入被动，但trigger名同effect需要手动触发
    "replace_normal_skill",
    "replace_pursuit"
}

ACTIVE_EFFECT_TYPES_NEEDED = {
    # 资源
    "resource",
    "token",
    "heal_sp_by_token",
    "specify_sp",
    # rule
    "additional_turn",
    "zone",
    "summers_end_territory",
    "remove_summers_end_territory",
    "revive_territory",
    # 特殊技能效果
    "remove_buff",
    "remove_debuff",
    "immersion",
    # 特殊状态
    "provoke",
    "cover",
    "dodge",
    "invincible",
    "sprightly",
    "shadow_clone",
    "revenge",
    "double_action_extra_skill",
    "shredding",
    "recoil",
    "b_i_yamawaki_servant",
    "curry",
    "dim_sum",
    "gelato",
    "shchi",
    "steak",
    "tea",
    "diva",
    "mocktail",
    "super_break_down",
    # buff
    "attack_up",
    "attack_up_by_token",
    "attack_up_include_normal",
    "attack_up_range_by_all_damage_rate",
    "critical_damage_up",
    "mind_eye",
    "give_attack_buff_up",
    "give_debuff_up",
    "funnel",
    "buff_charge",
    "morale",
    "motivation",
    "fighting_spirit",
    "eternal_oath",
    "arrow_cherry_blossoms",
    # debuff
    "fragile",
    "defense_down",
    "resist_down",
    "resist_down_overwrite",
    "misfortune",
    "undermine",
    "venom",
    "disaster",
    "infantilized",
    "hacking",
}

ATTACK_UP_GROUP = {
    "attack_up",
    "attack_up_by_token",
    "attack_up_include_normal",
    "attack_up_range_by_all_damage_rate",
}

DEBUFF_UP_GROUP = {
    "defense_down",
    "fragile",
    "resist_down",
}

DP_HEAL_GROUP = {
    "heal_dp",
    "heal_dp_rate",
    "revive_dp",
}

ON_ATTACKED_GROUP = {
    "shadow_clone",
    "invincible",
    "dodge",
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
        # conditions的情况，目前其实并不存在
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

    def selection_target_type(self):
        # GUI只区分需要手动选择的目标
        if self.target in ("ally_single", "ally_single_without_self", "ally_single_front_without_self"):
            return self.target
        if self.target == "single":
            return "enemy"
        return "ignore"

    @classmethod
    def from_record(cls, record: JsonDict) -> 'Skill':
        if record.get('kind') not in ('active', 'system', 'accessory'):
            raise ValueError(f"Skill 只能读取 active/system，收到 {record.get('kind')!r}")
        data = _record_kwargs(cls, record)
        # 设置cost相关
        cost = data.get('cost') or {}
        if 'yes' in cost and 'no' in cost:  # 目前只有sp类型
            data['cost_type'] = 'sp'
            data['default_cost'] = max(
                cost['yes'].get('sp', 0), cost['no'].get('sp', 0)
            )
        elif "cases" in cost:  # 目前只有od类型
            data['cost_type'] = cost.get('resource', 'od')
            data['default_cost'] = max(item.get(data['cost_type']) for item in cost.get("cases"))
        else:  # sp，ep，token，ct，od
            data['cost_type'] = ('sp' if 'sp' in cost else cost.get('resource', 'sp'))
            data['default_cost'] = cost.get(data['cost_type'], 0)
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
    trash: bool = False
    data: dict = field(default_factory=dict)  # 通用字段，储存特殊的status

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
    hit: int = 0

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
    od_rate_extra: int = 0  # 光月歌共鸣和鱼大师被动，在battle_start()中储存, 例如鱼为5
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
    skills: List[Skill] = field(default_factory=list)  # 当回合计算出来的，除default技能外的可以用的skills

    @staticmethod
    def generate_default_skills_from_skill(skill: Skill) -> dict:
        return {"name": skill.names["zh_cn"], "id": skill.id, "cost": 0, "cost_type": "sp",
                "target_type": "ignore", "user_select": None}

    def style_has_passive_id(self, skill_id: int) -> bool:
        if not self.skill_passive:
            return
        return any(passive.id == skill_id for passive in self.skill_passive)

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
        data = {k: deepcopy(record[k]) for k in ('id', 'names', 'character_names', 'team', 'tier', 'elements', 'role', 'attack_type', "hit")}
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
        simei_auto = False
        for skill_id in active_skill_ids or []:
            if skill_id == 737:
                simei_auto = True
                continue
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
                        if isinstance(effect.get('od'), list):
                            effect['od'] = effect['od'][resonance_break_level]
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
        basic_ids = [2 if instance.role == 'admiral' else 1, 0, 3]
        # 两个追击/普攻替换技能
        if "replace_pursuit" in instance.passive_triggers and simei_auto:  # 暗四妹是普攻+自动追击+无
            basic_ids[2] = 0
            basic_ids[1] = 4
            raw = skill_records[int(7280001)]
            instance.active_skills.append(Skill.from_record(raw))
        elif "replace_normal_skill" in instance.passive_triggers:
            basic_ids[0] = 4520001
            raw = skill_records[int(4520001)]
            instance.active_skills.append(Skill.from_record(raw))
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
    default_hit: float = 2.5
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
    od_timing: Optional[str] = None  # None, before, after 记录此时处于的od状态，after可以bonus0
    od_level: int = 0
    additional_turn: bool = False
    bonus: int = 0
    order: List[int] = field(default_factory=lambda: list(range(6)))
    special_actions: dict = dataclasses.field(default_factory=lambda: {
        "demonic_rage": 0, "demonic_rage_after": 0, "all_out_attack": 0, "all_out_attack_after": 0, 
        "demon_cavalry": 0, "demon_cavalry_after": 0, "kelian_form_change": 0
    })

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
        return matches_element(ctx.subject, need_element)

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
        action = ctx.turn.actions[slot]
        return find_skill_by_id(ctx.subject, action.get("id")).now_cost if action else 0

    @staticmethod
    def normal_attack(ctx: Context):
        slot = ctx.subject.slot
        action = ctx.turn.actions[slot]
        return action.get("id") == 1 if action else False

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
def resolve_targets(turn: Turn, owner: Style, target_type: str, effect=None) -> list[Style | Monster]:
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
        "single": lambda: [
            effect.get("effect_target")
        ],
        "ally_single": lambda: [
            effect.get("effect_target")
        ],
        "ally_single_without_self": lambda: [
            effect.get("effect_target")
        ],
        "ally_single_front_without_self": lambda: [
            effect.get("effect_target")
        ]
    }
    if target_type not in groups:
        raise ValueError(f"未知角色目标: {target_type}")
    return groups[target_type]()

def calculate_funnel(style: Style, consume=False):
    """计算连击珠应用哪个，单独发动的都是回合消耗，叠层发动的都是use消耗，被动都是permanent"""
    funnels = [status for status in style.statuses if status.id == 13 and not status.trash]
    if not funnels:
        return 0
    # 计算连击珠的实际伤害
    def damage(status):
        mode = status.data["mode"]
        return mode["value"] * mode["number"]
    # 为连击珠排序，取前2，切片操作少于2个不会报错
    use_funnels = sorted(
        (s for s in funnels if s.duration_type == "use" and not s.trash),
        key=damage,
        reverse=True
    )[:2]
    use_damage = sum(damage(s) for s in use_funnels)
    # 回合连击珠
    turn_funnels = [
        s for s in funnels
        if s.duration_type == "ally_turn"
    ]
    turn_best = max(turn_funnels, key=damage, default=None)
    turn_damage = damage(turn_best) if turn_best else 0
    # 被动连击珠
    passive_funnels = [
        s for s in funnels
        if s.duration_type == "permanent"
    ]
    passive_best = max(passive_funnels, key=damage, default=None)
    # 根据伤害选择连击珠
    chosen = (
        [turn_best]
        if turn_damage >= use_damage
        else use_funnels
    )
    # 如果需要则进行连击珠消耗
    if consume and chosen is use_funnels:
        for status in use_funnels:
            status.trash = True
    # 返回连击珠个数
    return sum(
        s.data["mode"]["number"]
        for s in chosen + ([passive_best] if passive_best else [])
        if s is not None
    )

# 根据行动的参数计算od增加数值
def calculate_od(hit, funnel, enemy, direct, earring: int, extra_rate: float, default_hit: float) -> float:
    if earring != 0:  # 10,12,15
        if hit != 0:
            od_rate_100 = 105 + (earring-5) / 9 * min(hit - 1, 9) + extra_rate
        else:
            od_rate_100 = 105 + extra_rate
    else:
        od_rate_100 = 100 + extra_rate
    per_hit_od = math.floor(od_rate_100 * default_hit) / 100  # 2位小数
    direct_od = math.floor(od_rate_100 * direct) / 100  # 2位小数
    return direct_od if hit == 0 else per_hit_od * (hit + funnel) * enemy + direct_od 

# sp回复
def add_sp(target: Style, effect: dict):
    limit = effect.get("limit", target.sp_limit)
    target.sp = max(min(target.sp + effect["sp"], limit), target.sp)

# 判断style是否有某status
def has_status_id(owner: Style | Monster, status_id: int, allow_trash: bool = False) -> bool:
    if allow_trash:
        return any(status.id == status_id for status in owner.statuses)
    else:
        return any(status.id == status_id and not status.trash for status in owner.statuses)

# 判断某技能是否是攻击技能
def is_attack_skill(skill: Skill) -> bool:
    return bool(skill.attack_type)

# 通过skill_id寻找某风格的非默认技能
def find_skill_by_id(style: Style, skill_id: int) -> Skill:
    if skill_id == 4:
        skill_id = 7280001
    return next(skill for skill in style.active_skills if skill.id == skill_id)

# 计算敌人数量
def monster_num(turn: Turn) -> int:
    return sum(monster.exist for monster in turn.battle.monsters)

# 计算敌人是否有buff
def monster_has_buff(turn: Turn, position=None):
    def one_monster_has_buff(monster: Monster):
        return any(status.category == "buff" and not status.trash for status in monster.statuses)
    if position is not None:
        if position not in (0,1,2):
            return False
        else:
            return one_monster_has_buff(turn.battle.monsters[position])
    else:
        for monster in turn.battle.monsters:
            if monster.exist and one_monster_has_buff(monster):
                return True
        return False

# 获取所有use消耗的buff
def get_use_buff(style: Style, status_id: int, duration_type: str):
    return [status for status in style.statuses if status.id == status_id and status.duration_type == duration_type]

# 不使用技能时恢复轻快buff
def fresh_sprightly(style: Style):
    for status in style.statuses:
        if status.id == 194 and status.trash:
            status.trash = False
            break

# 增加虚属性判定
def matches_element(style: Style, element: str) -> bool:
    return (
        element in style.elements
        or ("void" in style.elements and element in ELEMENTS)
    )

class Simulation:
    """持有静态数据库与初始化后的 Turn。进行实际的模拟并实现与gui的dict state传递接口"""
    def __init__(self):
        self.skills_path = SIMULATION_DIR / 'skills.json'
        self.styles_path = SIMULATION_DIR / 'styles.json'
        self.statuses_path = SIMULATION_DIR / 'statuses.json'
        self.skill_records: Dict[int, JsonDict] = {}
        self.style_records: Dict[int, JsonDict] = {}
        self.status_records: Dict[int, JsonDict] = {}
        self.turns: List[Turn] = []  # 存储每一个turn运行到on action start并预测出od的位置
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
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int, "on_break": False, "be_attacked_times": False}] * 6,
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
            "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0} before/after
        其中，技能的第0个为默认主动技能，第1个为默认被动技能（无），第2个为追击，普通攻击默认无目标
        """
        # 先解析members
        members = []
        for style in turn.team:
            # 把style的skills转换为字典
            if not style.skills:  # 如果当回合没有可以使用的skills则返回空的列表
                skills = []
            else:  # 当回合有可以使用的技能
                skills = deepcopy(style.basic_skills)  # 3个，默认的顺序为：前排默认技能，无，追击
                for skill in style.skills:
                    # 处理target type，GUI仅需要知道是敌人还是友方（是否可选自己）
                    target_type = skill.selection_target_type()
                    # 处理user_select
                    if skill.user_select == None:
                        user_select = None
                    else:
                        user_select = [u["description"] for u in skill.user_select.values()]
                    # 转换为字典并加入skills dict中
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
                'statuses': [asdict(status) for status in style.statuses],
                'skills': skills,
                "special_trigger": style.special_trigger
            })

        # 解析enemies
        enemies = []
        for monster in turn.battle.monsters:
            enemies.append({
                'exist': monster.exist,
                'damage_rate': monster.damage_rate,
                'down': monster.down,
                'statuses': [asdict(status) for status in monster.statuses],
            })

        return deepcopy({
        'members': members,
        'order': turn.order,
        'actions': turn.actions,
        'enemies': enemies,
        'enemy_weaknesses': turn.battle.enemy_weaknesses,
        "super_scale": turn.battle.super_scale,
        'field': turn.battle.field["value"],
        "territory": turn.battle.territory,
        'turn': turn.turn_num,
        'od': turn.od,
        'predicted_od': turn.predicted_od,
        'od_timing': turn.od_timing,
        'od_level': turn.od_level,
        'bonus': turn.bonus,
        'additional_turn': turn.additional_turn,
        "special_actions": turn.special_actions
        })

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
                if record.get('kind') not in ('active', 'system', "accessory"):
                    raise ValueError(f'技能 {skill_id} 不是 active/system/accessory')
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
            default_hit=math.floor(2.5 * global_od_rate) / 100  # 2位小数
        )
        turn = Turn(
            battle=battle,
            team=result_styles,
            od=initial_od,
            predicted_od=initial_od
        )
        # 只在全部构造成功后提交，避免部分初始化失败污染旧战斗。
        self.skill_records = skill_records
        self.style_records = style_records
        self.status_records = status_records
        self.initial_config = config
        self.turns = []
        return turn

    # 判断一个技能是否有某个effect，直接统计effect可能会出现target condition不满足的情况
    def skill_has_effect_with(self, skill: Skill, action: dict, ctx: Context, *, effect_key: str=None, effect_type: str=None):
        effects = self.resolve_active_effects(skill, action, ctx)
        if effect_key:
            return any(effect.get(effect_key) for effect in effects)
        if effect_type:
            return any(effect.get("type") == effect_type for effect in effects)

    def trigger_passives(self, turn: Turn, trigger: str):
        """触发某个时间节点str的全队伍被动"""
        order = deepcopy(turn.order)
        order[0], order[1] = order[1], order[0]  # 触发顺序是position的1，0，2，3，4，5
        for slot in order:
            style = turn.team[slot]
            self.trigger_style_passives(turn, style, trigger)

    def trigger_style_passives(self, turn: Turn, style: Style, trigger: str, *, only_od=False, without_od=False):
        """触发一个角色的全部被动"""
        if trigger in style.passive_triggers:
            for passive in iter_passives(style):
                if style.id == 49 and isinstance(passive, LimitBreak):
                    if turn.special_actions["kelian_form_change"] == 0 and passive.id in (490002, 490005):
                        continue
                    elif turn.special_actions["kelian_form_change"] == 1 and passive.id in (490001, 490004, 490006):
                        continue
                # 判断trigger时机
                if passive.trigger != trigger:
                    continue
                self.trigger_one_passive(passive, turn, style, only_od=only_od, without_od=without_od)

    def trigger_one_passive(self, passive: LimitBreak | Passive | SupportSkill, turn: Turn, style: Style, *, only_od=False, without_od=False):
        """触发一个传入的被动"""
        # 判断trigger condition是否满足
        ctx = Context(turn=turn, subject=style)
        if (passive.trigger_condition and not check(passive.trigger_condition, ctx)):
            return
        # 检查触发次数
        if isinstance(passive, LimitBreak) and passive.trigger_limit is not None:
            if passive.trigger_times >= passive.trigger_limit:
                return
            else:
                if not only_od:  # 不是shortcut才要增加trigger_times
                    passive.trigger_times += 1
        # 解析是否有case等结构，返回实际生效的effect列表
        effects = self.resolve_passive_effects(passive, ctx)
        # 对每个effect判断和应用效果
        for effect in effects:
            if only_od and effect.get("target") != "od":
                continue
            if without_od and effect.get("target") == "od":
                continue
            self.apply_effect(turn, style, effect)

    def trigger_active_actions(self, style: Style, skill: Skill, action: dict, ctx: Context, second=False):
        """实际应用的主动技能触发函数，过滤掉od相关的内容，在shortcut里做"""
        # 解析是否有case等结构，过滤不模拟的effect，返回实际生效的effect列表
        turn = ctx.turn
        effects = self.resolve_active_effects(skill, action, ctx)
        effects = [effect for effect in effects if effect.get("target") != "od"]
        # 应用效果
        for effect in effects:
            if second and effect.get("need_break"):  # 双动不触发破盾相关buff
                continue
            self.apply_effect(turn, style, effect, source=skill.names.get("zh_cn"))
        # 增加使用次数
        skill.used += 1

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

    def resolve_active_effects(self, skill: Skill, action: dict, ctx: Context):
        # 破盾的技能
        if skill.on_break:
            if action.get("on_break"):
                before_filter = skill.on_break.get("yes").get("effects")
            else:
                before_filter = skill.on_break.get("no").get("effects")
        # 用户选择的技能
        elif skill.user_select:
            selected = str(action.get("user_selected"))
            before_filter = skill.user_select.get(selected).get("effects")
            # 小螃蟹的原皮大招hit count在此处变化，因此od shortcut需要调用本函数进行动态hit count赋值
            if skill.user_select.get(selected).get("hit_count"):
                skill.hit_count = skill.user_select.get(selected).get("hit_count")
        # conditions技能
        elif skill.conditions and skill.conditions.get("effects"):
            if check(skill.conditions.get("effects"), ctx):
                before_filter = skill.effects.get("yes")
            else:
                before_filter = skill.effects.get("no")
        # cases技能
        elif skill.cases and "effects" in skill.cases:
            before_filter = []
            for case in skill.effects["cases"]:
                if check(case["when"], ctx):
                    before_filter = case["effects"]
                    break
        elif isinstance(skill.effects, list):
            before_filter = skill.effects
        # 未知结构
        else:
            raise ValueError(f"未知主动技能效果结构: {skill.effects}")
        # 理莎的返婴被动，在filter之前确认是否有dp恢复相关效果，并添加返婴1层
        tmp_effect = None
        if ctx.subject.style_has_passive_id(556) and before_filter and any(effect.get("type") in DP_HEAL_GROUP for effect in before_filter):
            tmp_effect = {"type": "infantilized", "target": "all", "status_id": 214, "duration": {"type": "permanent"}, "level": 1, "target_condition": "target.has(214)"}
        after_filter = [deepcopy(effect) for effect in before_filter if effect.get("type") in ACTIVE_EFFECT_TYPES_NEEDED]
        if tmp_effect:
            after_filter.append(tmp_effect)
        # 对每个effect确定单体的target
        turn = ctx.turn
        for effect in after_filter:
            effect_target = None
            target_dict = action.get("target")
            if target_dict.get("type") == "enemy":
                effect_target = turn.battle.monsters[target_dict.get("slot")]
            elif target_dict.get("type") != "ignore":  # 我方单体角色
                effect_target = turn.team[target_dict.get("slot")]
            effect["effect_target"] = effect_target
            # 特殊技能额外信息加入effect
            if effect.get("type") == "heal_sp_by_token":
                effect["sp"] = effect.get("sp") * skill.now_cost
        return after_filter
        
    # 实际解析并应用effect的函数
    def apply_effect(self, turn: Turn, owner: Style, effect: dict, source=None):
        effect_type = effect["type"]
        target_type = effect.get("target", "self")

        # 全局目标单独处理；其余统一解析为 Style / Monster 列表
        if target_type in ("od", "field", "territory"):
            targets = []
        else:
            targets = resolve_targets(turn, owner, target_type, effect)
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
            # 应用debuff回合延长，暂时默认1回合延长
            if has_status_id(owner, 135) and duration_type == "enemy_turn" and self.status_records.get(status_id).get("category") == "debuff":
                remaining += 1
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
                    (s for s in target.statuses if s.id == status_id and not s.trash),
                    None
                )
                # 不重复添加
                if unique and old is not None:
                    if effect_type in ON_ATTACKED_GROUP:
                        old.remaining += remaining
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
                data=deepcopy({key: value for key, value in effect.items() if key != "effect_target"}),
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
                            add_sp(target, effect)

                        if "ep" in effect:
                            target.ep = max(0, min(target.ep + effect["ep"], target.ep_limit))
            case "token":
                for target in targets:
                    target.token = max(0, min(target.token + effect.get("level", 0), 10))
            case "token_up_per_attack_enemy":
                # 根据攻击命中的敌人数增加 Token
                for target in targets:  # 其实就是self
                    action = turn.actions[target.slot]
                    # 无行动或追击等
                    if not action or action["id"] in (0, 2, 3, 4):
                        token_added = 0
                    # 普通攻击
                    elif action["id"] == 1:
                        token_added = 1
                    # 其他一般技能
                    else:
                        skill = find_skill_by_id(target, action.get("id"))
                        # 检测是否是攻击技能
                        if is_attack_skill(skill):
                            target_type = skill.target
                            if target_type == "single":  # 单体技能
                                token_added = 1
                            elif target_type == "all":  # 群体技能
                                token_added = sum(1 for monster in turn.battle.monsters if monster.exist)
                        else:  # 非攻击技能
                            token_added = 0
                    target.token = max(0, min(target.token + token_added * effect.get("value", 1), 10))
            case "over_drive_rate_up":
                for target in targets:
                    target.od_rate_extra += effect["value"]
            case "reduce_consume_overdrive":
                turn.battle.od_consume = max(0, turn.battle.od_consume - effect["value"])

            # ==================== SP / EP 修正 ====================
            case "overwrite_sp":
                # 记录技能费用覆盖规则，不立即修改 now_cost
                for target in targets:
                    add_status(target)
            case "sp_limit_overwrite":
                value = effect.get("value", 20)
                for target in targets:
                    target.sp_limit = value
                    # 暂时没有向下调整的和非永久的sp_limit，SP 已有值不强制降低
            case "ep_limit_overwrite":
                for target in targets:
                    target.ep_limit = effect["value"]
                    add_status(target)
            case "sp_modify":
                for target in targets:
                    add_status(target)  # advance中根据这些status决定style的sp_modify数值

            # ==================== 特殊状态 ====================
            case "additional_turn":
                # 在下一阶段检查追加回合状态并安排额外行动
                for target in targets:
                    add_status(target)
            case "double_action_extra_skill":
                # EX 技能双动，在执行 EX 技能时消费
                # TODO: 在行动结算时处理
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
                # 注册修正状态，在 Debuff 实际施加时：duration += 所有生效的 give_debuff_turn_up.value
                for target in targets:
                    add_status(target)
            case "zone_up_eternal_plus_15":
                # 注册修正状态，施加 zone 时变为永久
                for target in targets:
                    add_status(target)
            case "element_mark":
                # 对应属性的队员人数决定层数，最大6层
                element = (effect.get("elements") or [None])[0]
                level = sum(matches_element(style, element) for style in turn.team)
                for target in targets:
                    add_status(target, level=level, max_level=6)
            case "zone":
                element = (effect.get("elements") or [None])[0]
                duration = effect.get("duration", {})
                turn.battle.field["value"] = element
                # 没有value则为permanent，填-1认为永久
                turn.battle.field["left_turn"] = (
                    -1 if has_status_id(owner, 126) else duration.get("value", -1) 
                )
                self.trigger_passives(turn, "on_active_zone")
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
            case "makeup":
                for target in targets:
                    add_status(target, unique=True)
            case "talisman":
                for target in targets:
                    add_status(target, level=effect.get("level", 0), max_level=10)
            case "inscription":
                for target in targets:
                    add_status(target, level=effect.get("level", 0), max_level=15)
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
            case "dodge":
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

            # ==================== 主动技能区 ====================
            # 资源
            case "heal_sp_by_token":
                for target in targets:
                    add_sp(target, effect)
                
            case "specify_sp":
                for target in targets:
                    add_status(target)
            # rule
            case "summers_end_territory":
                turn.battle.territory = 204
                
            case "remove_summers_end_territory":
                turn.battle.territory = None
                
            case "revive_territory":
                turn.battle.territory = 157

            # 特殊技能效果
            case "remove_buff":
                for target in targets:
                    removes = 0
                    for status in target.statuses:
                        if status.category == "buff" and not status.trash:
                            status.trash = True
                            removes += 1
                        if removes >= effect.get("number", 1):
                            break
                
            case "remove_debuff":
                for target in targets:
                    removes = 0
                    limit = effect.get("number", 1) if effect.get("number", 1) > 0 else None
                    for status in target.statuses:
                        if status.category == "debuff" and not status.trash:
                            status.trash = True
                            removes += 1
                        if limit and removes >= limit:
                            break
                
            case "immersion":
                for target in targets:
                    add_status(target, unique=True)

            case "fear_for_demon":
                for target in targets:
                    add_status(target, unique=True)

            case "gui_shen":
                for target in targets:
                    add_status(target, unique=True)

            # 特殊状态
            case "shredding" | "diva" :
                for target in targets:
                    add_status(target)

            case "super_break_down":
                for target in targets:
                    if target.down:
                        add_status(target)

            case "invincible":
                for target in targets:
                    add_status(target, unique=True)
                
            case "recoil" | "b_i_yamawaki_servant" | "curry" | "dim_sum" | "gelato" | "shchi" | "steak" | "tea":
                for target in targets:
                    add_status(target, unique=True)
                
            # buff
            case "attack_up" | "attack_up_include_normal" | "critical_damage_up" | \
                 "mind_eye" | "give_attack_buff_up" | "give_debuff_up":
                for target in targets:
                    add_status(target)
                
            case "eternal_oath" | "attack_up_by_token" | "attack_up_range_by_all_damage_rate" | "fighting_spirit":
                for target in targets:
                    add_status(target, unique=True)

            # debuff
            case "resist_down_overwrite":
                element = effect.get("elements")[0]
                if element not in turn.battle.enemy_weaknesses:
                    turn.battle.enemy_weaknesses.append(element)
                    
            case "fragile" | "defense_down" | "undermine" | "hacking":
                for target in targets:
                    add_status(target)

            case "resist_down":
                if effect.get("elements")[0] in turn.battle.enemy_weaknesses:
                    for target in targets:
                        add_status(target)

            case "venom":
                for target in targets:
                    add_status(target, level=effect.get("level", 1), max_level=10)

            # ==================== 未知类型 ====================
            case _:
                raise NotImplementedError(
                    f"未实现的被动效果类型: {effect_type}"
                )

    def resolve_tmp_od(self, turn: Turn, direct=True):
        """将apply effect后的stage_tmp_od加回正式od，回合开始的效果还需加到od上，否则仅加预测od"""
        if direct:
            turn.od = min(turn.stage_tmp_od + turn.od, 300)
            turn.predicted_od  = min(turn.stage_tmp_od + turn.predicted_od, 300)
        else:
            turn.predicted_od += turn.stage_tmp_od
        turn.stage_tmp_od = 0

    def consume_enemy_turn(self, turn: Turn):
        """把所有己方和敌方的enemy_turn进行消耗，包括灵符状态重置等级"""
        for enemy in turn.battle.monsters:
            for status in enemy.statuses:
                if status.duration_type == "enemy_turn":
                    status.remaining -= 1
                    if status.remaining <= 0:
                        status.trash = True
                if status.id == 177 and not enemy.down:
                    status.level = 0
        for style in turn.team:
            for status in style.statuses:
                if status.duration_type == "enemy_turn":
                    status.remaining -= 1
                    if status.remaining <= 0:
                        status.trash = True
        # 清除掉所有标记为trash的status
        for style in turn.team:
            for status in style.statuses[::-1]:
                if status.trash and status.duration_type == "enemy_turn":
                    style.statuses.remove(status)
        for enemy in turn.battle.monsters:
            for status in enemy.statuses[::-1]:
                if status.trash and status.duration_type == "enemy_turn":
                    enemy.statuses.remove(status)

    def consume_od_end(self, turn: Turn):
        """od结束的时候调用，清除相关buff"""
        for style in turn.team:
            for status in style.statuses:
                if status.duration_type == "od_end":
                    status.trash = True
        # 清除掉所有标记为trash的status
        for style in turn.team:
            for status in style.statuses[::-1]:
                if status.trash and status.duration_type == "od_end":
                    style.statuses.remove(status)

    def consume_buff_by_use(self, skill: Skill, style: Style, ctx: Context, action):
        """apply actions的时候调用，将发动的叠层buff进行trash"""
        def consume_use_turn_buff(statuses: list[Status], element=None):
            # 非元素一定都要消耗
            consumed_normal = 0
            for status in statuses:
                if status.element == None and not status.trash:
                    status.trash = True
                    consumed_normal += 1
                    if consumed_normal == 2:
                        break
            if not element:
                return
            # 有元素的技能则消耗对应元素属性的buff
            consumed_element = 0
            for status in statuses:
                if status.element == element and not status.trash:
                    status.trash = True
                    consumed_element += 1
                    if consumed_element == 2:
                        break

        # ex技能连续发动和沉浸状态去除
        if skill.ex_skill:
            for status in style.statuses:
                if status.duration_type in ("use_ex", "use_immersion_ex"):
                    status.trash = True
                    # 沉浸状态接触时把所有skills的elements都还原(为None)
                    if status.duration_type == "use_immersion_ex":
                        for none_skill in style.skills:
                            if is_attack_skill(none_skill):
                                elements = self.skill_records[none_skill.id].get("elements")
                                if elements == None:
                                    elements = []
                                none_skill.elements = elements
        # 加攻加深去除
        effects = self.resolve_active_effects(skill, action, ctx)
        buff_num = sum(effect.get("type") in ATTACK_UP_GROUP for effect in effects)
        if buff_num:
            remove_buff = 0
            for status in style.statuses:
                if status.id == 54 and not status.trash:
                    remove_buff += 1
                    status.trash = True
                if remove_buff == buff_num:
                    break
        # debuff加深去除
        debuff_num = sum(effect.get("type") in DEBUFF_UP_GROUP for effect in effects)
        if debuff_num:
            remove_debuff = 0  # 减益加深
            for status in style.statuses:
                if status.id == 118 and not status.trash:
                    remove_debuff += 1
                    status.trash = True
                if remove_debuff == debuff_num:
                    break
            remove_debuff = 0  # 樱花箭
            for status in style.statuses:
                if status.id == 120 and not status.trash:
                    remove_debuff += 1
                    status.trash = True
                if remove_debuff == debuff_num:
                    break
        # 去除攻击技能相关
        attack_skill = is_attack_skill(skill)
        if attack_skill:
            # 消耗充能
            for status in style.statuses:
                if status.id == 25 and not status.trash:
                    status.trash = True
                    break
            # 消耗连击珠
            calculate_funnel(style, consume=True)
            # 以下3种buff如果有ally_turn的就是单独发动，默认不消耗use的层数
            # 消耗心眼
            if not any(status.id == 78 and status.duration_type == "ally_turn" for status in style.statuses):
                mind_eyes = get_use_buff(style, 78, "on_attack_weak")
                consume_use_turn_buff(mind_eyes)
            # 消耗加攻
            if not any(status.id == 1 and status.duration_type == "ally_turn" for status in style.statuses):
                attack_ups = get_use_buff(style, 1, "use")
                consume_use_turn_buff(attack_ups, skill.elements[0] if skill.elements else None)
            # 消耗爆伤
            if not any(status.id == 7 and status.duration_type == "ally_turn" for status in style.statuses):
                critical_damage_ups = get_use_buff(style, 7, "use")
                consume_use_turn_buff(critical_damage_ups, skill.elements[0] if skill.elements else None)

    def using_demon_cavalry(self, turn: Turn, times: int, before_od=True):
        od_added = monster_num(turn) * 6 * turn.battle.default_hit * times
        if before_od:
            turn.od = min(turn.od + od_added, 300)
        turn.predicted_od = min(turn.predicted_od + od_added, 300)
        waki = next(style for style in turn.team if style.id == 113)
        effect = {"type": "fear_for_demon", "target": "all", "duration": {"type": "enemy_turn", "value": 1}, "status_id": 230}
        self.apply_effect(turn, waki, effect, source="魔界骑兵启动！")

    def using_demonic_rage(self, turn: Turn, before_od=True):
        if before_od:
            turn.od = min(turn.od + 15, 300)
        turn.predicted_od = min(turn.predicted_od + 15, 300)
        effects = [
            {"type": "gui_shen", "duration": {"type": "ally_turn", "value": 3}, "status_id": 229, "target": "self"}, 
            {"type": "remove_debuff", "target": "self", "number": -1}, 
            {"type": "funnel", "target": "self", "mode": {"number": 3, "value": 25}, "solo": True, "status_id": 13, "duration": {"type": "ally_turn", "value": 3}}, 
            {"type": "mind_eye", "target": "self", "value": 120, "duration": {"type": "ally_turn", "value": 3}, "solo": True, "status_id": 78}
        ]
        siling = next(style for style in turn.team if style.id == 365)
        for effect in effects:
            self.apply_effect(turn, siling, effect, source="鬼神化")

    def od_up_through_action(self, turn: Turn, tmp_turn: Turn, tmp_style: Style, effects, skill: Skill, attack_skill, hit, enemy_count, second=False):
        direct = 0
        for effect in effects:
            # 临时应用连击珠效果
            if effect.get("type") == "funnel":
                self.apply_effect(tmp_turn, tmp_style, effect)
            # 解析od相关，存储直充od数值
            elif effect.get("type") == "resource" and effect.get("target") == "od":
                direct = 0 if second and effect.get("need_break") else effect.get("od")  # 需要破盾的第二次不发动
            # 目前有唯一一个消耗全部token获得od的技能，暂时按照可以吃od加深算
            elif effect.get("type") == "over_drive_point_up_by_token":
                direct = effect.get("value") * skill.now_cost
        funnel = calculate_funnel(tmp_style, consume=True) if attack_skill else 0
        turn.stage_tmp_od += calculate_od(hit, funnel, enemy_count, direct, tmp_style.od_earring, tmp_style.od_rate_extra, turn.battle.default_hit)

    def resolve_simei_pursuit(self, simei_style: Style, turn: Turn, simei_ex: bool, attack_skill: bool, skill: Skill, only_od=True):
        """完成四妹的自动追击的od计算或buff计算，目前认为不会触发任何其他被动"""
        if simei_style and attack_skill and skill.now_cost <= 8 and skill.cost_type == "sp":
            simei_skill = find_skill_by_id(simei_style, 4)
            if simei_ex or simei_style.sp < simei_skill.now_cost:  # 本回合已经发动过或者sp不够发动不出来大招
                if only_od:  # 计算od
                    turn.stage_tmp_od += calculate_od(simei_style.hit, 0, 1, 0, 0, simei_style.od_rate_extra, turn.battle.default_hit)
                # 仅追击则不给任何buff，仅触发被动
                else:
                    self.trigger_style_passives(turn, simei_style, "on_pursuit", without_od=True)
                return simei_ex
            else:
                if only_od:  # 计算od
                    hit = simei_skill.hit_count
                    funnel = calculate_funnel(simei_style)
                    # 四妹大招吃连击珠但是不吃od耳环
                    turn.stage_tmp_od += calculate_od(hit, funnel, 1, 0, 0, simei_style.od_rate_extra, turn.battle.default_hit)
                else:  # 计算buff
                    effects = [deepcopy(effect) for effect in simei_skill.effects if effect.get("type") in ACTIVE_EFFECT_TYPES_NEEDED]
                    for effect in effects:
                        self.apply_effect(turn, simei_style, effect, source="猫咪喷射打靶")
                    # 增加使用次数
                    simei_skill.used += 1
                    # 触发被动
                    self.trigger_style_passives(turn, simei_style, "on_pursuit", without_od=True)
                return True
        return simei_ex

    def resolve_sp_up_effect_passive(self, effect, turn, style, ctx, *, only_od):
        """对一个具体的effect判断是否恢复sp，根据target condition判断恢复几次sp，并最终触发被动"""
        if effect.get("sp"):  # 对于恢复sp的主动技能
            target_condition = effect.get("target_condition")
            targets = resolve_targets(turn, style, effect.get("target"), effect)
            for target in targets:
                ctx_target = replace(ctx, subject=target)
                # 每一个非自身target触发被动
                if target != style and (target_condition == None or check(target_condition, ctx_target)):
                    if only_od:
                        self.trigger_style_passives(turn, target, "on_sp_up_by_nonself_active_skill", only_od=True)
                    else:
                        self.trigger_style_passives(turn, target, "on_sp_up_by_nonself_active_skill", without_od=True)

    def resolve_talisman(self, monster: Monster):
        """把tama灵符的等级对某一怪物提升1级"""
        for status in monster.statuses:
            if status.id == 177:
                status.level = min(status.level+1, 10)
                break

    def action_legalization(self, turn: Turn):
        """合法化turn.actions，允许recalculate的action和初始化的[None]*6"""
        # actions按slot存放，前后排按本回合的order判断
        for position, slot in enumerate(turn.order):
            style = turn.team[slot]
            front = position < 3
            if has_status_id(style, 33) or \
            turn.additional_turn and front and not has_status_id(style, 20, True):
                turn.actions[slot] = None
                continue

            action = turn.actions[slot]
            skill_id = action.get("id") if action else None
            # 基础技能已经包含指挥、曙光普攻和暗四妹自动追击的替换，这里根据基础技能和站位选择默认技能
            basic_skills = style.basic_skills[:1] if front else style.basic_skills[1:3]
            basic_skill = next((skill for skill in basic_skills if skill["id"] == skill_id), None)
            # 当前选择的action就是基础技能
            if basic_skill is not None:
                action["name"] = basic_skill["name"]
                action["target"] = {"type": "ignore", "slot": None}
                action["user_selected"] = None
                continue

            # 使用本回合已选择的技能，例如可怜/可镰形态变化后旧技能可能失效
            if front and action:
                skill = next((skill for skill in style.skills if skill.id == skill_id), None)
                if skill is not None:
                    target_type = skill.selection_target_type()
                    target = action.get("target") or {}
                    target_slot = target.get("slot")
                    target_valid = target_type in ("ignore", "ally_single", "ally_single_without_self")
                    if target_type == "enemy":
                        target_valid = type(target_slot) is int and target_slot in range(len(turn.battle.monsters)) and \
                            turn.battle.monsters[target_slot].exist
                    elif target_type == "ally_single_front_without_self":
                        target_valid = type(target_slot) is int and target_slot in turn.order[:3] and target_slot != slot
                    selected = action.get("user_selected")
                    if target_valid and (not skill.user_select or str(selected) in skill.user_select):
                        continue

            # 无法保留旧行动时，恢复当前站位的默认行动
            default_skill = basic_skills[0]
            turn.actions[slot] = {
                "name": default_skill["name"],
                "id": default_skill["id"],
                "target": {"type": "ignore", "slot": None},
                "user_selected": None,
                "on_break": False,
                "be_attacked_times": 0
            }

    def od_legalization(self, turn: Turn, gui_add_state):
        """检查od是否合法并清除不合法的od设置"""
        natural_od_timing = turn.od_timing
        natural_od_level = turn.od_level
        natural_od_bonus = turn.bonus
        # od 相关发动没有变化，和natural一致则直接返回
        if natural_od_timing == gui_add_state["od_timing"] and natural_od_level == gui_add_state["od_level"]:
            return

        # 前置od发动条件是当前刚刚开启前置od，或者当前处于od外的非附加回合中
        available_before = True if (natural_od_timing == "before" and natural_od_bonus == 1) or (natural_od_level == 0 and not turn.additional_turn) else False
        # 后置od发动条件是当前刚刚开启前置od，或者当前处于od外
        available_after = True if (natural_od_timing == "before" and natural_od_bonus == 1) or natural_od_level == 0 else False

        # 检查od设置是否合法
        legal = True
        # 新发动前置od不合法
        if gui_add_state["od_timing"] == "before" and natural_od_timing == None and not available_before:
            legal = False
        # 新发动后置od不合法
        if gui_add_state["od_timing"] == "after" and natural_od_timing == None and not available_after:
            legal = False
        # 延续之前的od设置与新设置冲突不合法
        if natural_od_timing != None and (gui_add_state["od_timing"] != natural_od_timing or gui_add_state["od_level"] != natural_od_level):
            legal = False
        # 合法可以应用新设置
        if legal:
            turn.od_timing = gui_add_state["od_timing"]
            turn.od_level = gui_add_state["od_level"]
            
    def battle_start(self, turn: Turn):
        """
        战斗开场要处理的被动等，刚进场时slot和position一致
        on battle start, on first battle start
        补齐超越量表和默认的action
        """
        super_element = None
        super_scale = 0
        # 战斗开始每个人+1sp
        for style in turn.team:
            add_sp(style, {"sp": 1})
        # 检测超越量表
        for style in turn.team:
            special_trigger = style.special_trigger
            if special_trigger == "elemental_admiral":
                super_element = style.elements[0]
        # 超越量表开局数值计算
        if super_element:
            for style in turn.team:
                if matches_element(style, super_element):
                    super_scale += 15
        turn.battle.super_scale["element"] = super_element
        turn.battle.super_scale["value"] = super_scale
        # 先结算on_battle_start
        self.trigger_passives(turn, "on_battle_start")
        self.resolve_tmp_od(turn)
        # 再结算on_first_battle_start
        self.trigger_passives(turn, "on_first_battle_start")
        self.resolve_tmp_od(turn)

    def turn_start(self, turn: Turn, new_turn: bool) -> Turn:
        """
        输入刚开始的新回合(调用位置在前置od之前)，解析当前回合状态，应用对应回合的被动，初始化行动
        on_new_turn_start
        on_additional_turn_start
        on_overdrive_start  后置od
        ally_dp_broken
        """
        # new_turn_start
        if new_turn:
            # 回合开始先加2sp
            for style in turn.team:
                add_sp(style, {"sp": 2})
            # 再结算on_new_turn_start的被动
            self.trigger_passives(turn, "on_new_turn_start")
            self.resolve_tmp_od(turn)
            # 冰雷惠的回sp
            if any(style.dp <= 0 for style in turn.team):
                self.trigger_passives(turn, "ally_dp_broken")
            # 特殊属性印记状态，为前排角色提供额外1sp
            for slot in turn.order[:3]:
                style = turn.team[slot]
                for status in style.statuses:
                    if status.id == 166 and status.level == 6:
                        add_sp(style, {"sp": 1})
                        break
            # 晚夏之阵特殊状态，全体sp+1
            if turn.battle.territory == 204:
                for style in turn.team:
                    add_sp(style, {"sp": 1})
            # 猛毒触发
            venom_od = sum(enemy.exist and has_status_id(enemy, 218) for enemy in turn.battle.monsters) * 3 * turn.battle.default_hit
            turn.od = min(turn.od + venom_od, 300)
            turn.predicted_od = min(turn.predicted_od + venom_od, 300)
        # 附加回合
        elif turn.additional_turn:
            self.trigger_passives(turn, "on_additional_turn_start")
            self.resolve_tmp_od(turn)
        # 不处于附加回合的od状态，而且是第一个bonus，且此时不会出现前置od一定是后置od的起始
        elif turn.od_level != 0 and turn.bonus == 1:
            sp_added_dict = {1: 5, 2: 12, 3: 20}
            sp_added = sp_added_dict[turn.od_level]
            for style in turn.team:
                add_sp(style, {"sp": sp_added, "limit": 99})
            turn.od -= turn.battle.od_consume * turn.od_level
            turn.predicted_od -= turn.battle.od_consume * turn.od_level
            self.trigger_passives(turn, "on_overdrive_start")

        # 我方所有回合都要触发的被动
        self.trigger_passives(turn, "on_ally_turn_start")

        # 回合开始按站位补齐默认行动
        turn.actions = [None] * 6
        self.action_legalization(turn)

    def calculate_member_skills(self, turn: Turn):
        """给出所有队员可以使用的非默认技能以及使用的cost，存储在style.skills中，不修改其余数据"""
        for style in turn.team:
            # 疲劳状态没有任何skills
            if has_status_id(style, 33):
                style.skills = []
            # 处于附加回合但是前排没有附加回合状态没有skills
            elif turn.additional_turn and not has_status_id(style, 20, True) and style.slot in turn.order[:3]:
                style.skills = []
            # 能够正常使用skills的角色
            else:
                style.skills = []
                # initialize() 已经装入全部被选择的主动/光球技能
                for skill in style.active_skills:
                    # 普攻技能替换
                    if skill.id == 4520001:
                        continue
                    # 可镰不同形态的技能安排
                    if style.id == 49:
                        if turn.special_actions["kelian_form_change"] == 0 and skill.id == 319:
                            continue
                        elif turn.special_actions["kelian_form_change"] == 1 and skill.id == 326:
                            continue
                    # 处理cost，先刷新cost数值，每次调用完全重新计算
                    skill.now_cost = skill.default_cost
                    # 对所有cost_type先检查condition，目前cost里面不应该检查"target."
                    cost_condition = skill.conditions.get("cost")
                    if cost_condition:
                        if check(cost_condition, Context(turn, style)):
                            skill.now_cost = skill.cost.get("yes").get(skill.cost_type)
                        else:
                            skill.now_cost = skill.cost.get("no").get(skill.cost_type)
                    # 消耗sp的技能，消耗全部sp的不参与判断
                    if skill.cost_type == "sp" and skill.now_cost >= 0:
                        # 检查 overwrite_sp
                        for status in style.statuses:
                            if status.id == 175 and status.data.get("skill_id") == skill.id:
                                condition = status.data.get("condition")
                                if not condition or check(condition, Context(turn, style)):
                                    skill.now_cost = status.data.get("sp")
                        # 检查沉浸和鬼神化
                        if has_status_id(style, 228) or has_status_id(style, 229):
                            skill.now_cost = 0
                        # 检查轻快状态
                        spri = [status for status in style.statuses if status.id == 194]
                        if spri:
                            value_max = max(status.data.get("value") for status in spri)
                            if skill.id != 366 and skill.now_cost == skill.default_cost:
                                skill.now_cost = math.ceil(skill.default_cost * (1-value_max))
                                for status in spri:  # 把用过的轻快status标记为trash，回合末清除
                                    if status.data.get("value") == value_max:
                                        status.trash = True
                                        break
                        # 最后检查sp_modify
                        sp_modify_list = [status for status in style.statuses if status.id == 6]
                        if sp_modify_list:
                            sp_add = sp_minus = 0
                            for sp_modify in sp_modify_list:
                                condition = sp_modify.data.get("condition")
                                if not condition or check(condition, Context(turn, style)):
                                    modify = sp_modify.data.get("value")
                                    if modify > 0:
                                        sp_add = max(sp_add, modify)
                                    elif modify < 0:
                                        sp_minus = min(sp_minus, modify)
                            skill.now_cost = max(skill.now_cost + sp_add + sp_minus, 0)
                    # 消耗od的技能有一个是cases
                    elif skill.cost_type == "od":
                        if skill.cases and "cost" in skill.cases:
                            for case in skill.cost["cases"]:
                                if check(case["when"], Context(turn, style)):
                                    skill.now_cost = case["od"]
                                    break
                    # 消耗全部资源的技能
                    elif skill.now_cost < 0:
                        if skill.cost_type == "sp":
                            skill.now_cost = style.sp
                        elif skill.cost_type == "token":
                            skill.now_cost = style.token

                    # 沉浸状态的攻击技能属性赋予
                    if has_status_id(style, 228) and is_attack_skill(skill):
                        status = next(status for status in style.statuses if status.id == 228)
                        skill.elements = [status.element]

                    # 追击替换不实际加入到可以选择的skill列表当中
                    if skill.id == 7280001:
                        continue
                    style.skills.append(skill)

    def apply_actions_od_shortcut(self, turn: Turn):
        """
        在recalculate中调用，位于action start之后，只结算actions的消耗、od增长（predict）
        临时应用effect中的连击珠效果
        after_ex_use
        on_sp_up_by_nonself_active_skill
        on_relieve_enemy_buff
        on_break_enemy
        """
        # 预测只给队友临时增加连击珠，并标记已消费的珠子
        tmp_turn = replace(turn, team=[
            replace(style, statuses=[replace(status) if status.id == 13 else status
                                    for status in style.statuses])
            for style in turn.team
        ])
        turn.stage_tmp_od = 0
        # 判断超越量表
        super_scale_element = turn.battle.super_scale.get("element")
        super_scale_value = turn.battle.super_scale.get("value")
        if super_scale_element and super_scale_value < 100:
            scale_add = 0
            for slot in turn.order[:3]:
                style = turn.team[slot]
                if matches_element(style, super_scale_element) and turn.actions[style.slot]:
                    scale_add += 4
            if super_scale_value + scale_add >= 100:
                turn.stage_tmp_od += 100  # 不改变超越量表数值
        # 应用每个角色的技能，消耗对应资源，增加连击珠，并计算技能的od增量
        skill_ids = [action.get("id") if action is not None else None for action in turn.actions]
        # 判断技能应用顺序，同时记录是否有四妹自动追击存在
        action_type = []  # 1为非攻击技能/无行动，2为攻击技能，3为后排
        simei_style = None
        simei_ex = False
        for i, slot in enumerate(turn.order):
            skill_id, style, action = skill_ids[slot], turn.team[slot], turn.actions[slot]
            if not skill_id:
                action_type.append(1)
            elif i > 2:
                action_type.append(3)
                if skill_id == 4:
                    simei_style = tmp_turn.team[slot]
            else:
                if skill_id == 1:  # 普通行动
                    action_type.append(2)
                elif skill_id == 2:  # 指挥行动
                    action_type.append(1)
                else:  # 一般的skill
                    skill = find_skill_by_id(style, skill_id)
                    if is_attack_skill(skill):
                        action_type.append(2)
                    else:
                        action_type.append(1)
        # 应用每个角色的技能，消耗对应资源，增加连击珠，并计算技能的od增量
        for _, slot in sorted(zip(action_type, turn.order), key=lambda item: item[0]):
            skill_id, style, action = skill_ids[slot], turn.team[slot], turn.actions[slot]
            if not skill_id or skill_id in (0,2,4):  # 没有行动或指挥行动或四妹自动追击
                continue
            elif skill_id == 1:  # 普通攻击
                turn.stage_tmp_od += calculate_od(3, 0, 1, 0, 0, style.od_rate_extra, turn.battle.default_hit)
            elif skill_id == 3:  # 追击
                turn.stage_tmp_od += calculate_od(style.hit, 0, 1, 0, 0, style.od_rate_extra, turn.battle.default_hit)
            else:  # 一般的skill
                skill = find_skill_by_id(style, skill_id)
                # 先消耗资源
                match skill.cost_type:
                    case "sp":
                        style.sp -= skill.now_cost
                    case "token":
                        style.token -= skill.now_cost
                    case "ep":
                        style.ep -= skill.now_cost
                    case "od":
                        turn.stage_tmp_od -= skill.now_cost
                    case "ct":
                        pass
                    case _:
                        raise NotImplementedError(
                            f"不存在的技能消耗资源类型: {skill.cost_type}"
                        )
                # 进行技能effect相关od计算，使用tmp turn和style
                tmp_style = tmp_turn.team[slot]  # 和style的status是完全一致的
                ctx = Context(tmp_turn, tmp_style)
                if skill.conditions and skill.conditions.get("effects"):  # 这里有可能是target.作为起始
                    expr = skill.conditions.get("effects")
                    if expr.startswith("target."):
                        ctx = Context(tmp_turn, tmp_turn.battle.monsters[action.get("target").get("slot")])
                effects = self.resolve_active_effects(skill, action, ctx)
                hit = enemy_count = 0
                # 先判断是否是攻击性技能并存储hit数
                attack_skill = is_attack_skill(skill)
                if attack_skill:
                    hit = skill.hit_count
                    if skill.target == "single":
                        enemy_count = 1
                    elif skill.target == "all":
                        enemy_count = monster_num(turn)
                # 再判断具体效果
                self.od_up_through_action(turn, tmp_turn, tmp_style, effects, skill, attack_skill, hit, enemy_count)
                simei_ex = self.resolve_simei_pursuit(simei_style, turn, simei_ex, attack_skill, skill, True)  # 四妹追击
                # 白虎的攻击双动，不会和技能双动同时存在
                if has_status_id(style, 227) and attack_skill:
                    self.od_up_through_action(turn, tmp_turn, tmp_style, effects, skill, attack_skill, hit, enemy_count, second=True)
                    simei_ex = self.resolve_simei_pursuit(simei_style, turn, simei_ex, attack_skill, skill, True)  # 四妹追击
                # ex技能双动
                elif has_status_id(style, 125) and skill.ex_skill:
                    self.od_up_through_action(turn, tmp_turn, tmp_style, effects, skill, attack_skill, hit, enemy_count, second=True)
                    simei_ex = self.resolve_simei_pursuit(simei_style, turn, simei_ex, attack_skill, skill, True)  # 四妹追击

                # 结算和od相关的被动效果，白虎的ex双动不会引发od相关被动因此暂不考虑
                if skill.ex_skill:
                    self.trigger_style_passives(turn, style, "after_ex_use", only_od=True)
                    if has_status_id(style, 125):  
                        self.trigger_style_passives(turn, style, "after_ex_use", only_od=True)
                # 破盾被动认为只发动一次
                if action.get("on_break"):
                    self.trigger_style_passives(turn, style, "on_break_enemy", only_od=True)
                # 清除buff被动认为只发动一次
                if self.skill_has_effect_with(skill, action, ctx, effect_type="remove_buff") and monster_has_buff(turn, action["target"]["slot"]):
                    self.trigger_style_passives(turn, style, "on_relieve_enemy_buff", only_od=True)
                # 有恢复sp的主动技能
                if self.skill_has_effect_with(skill, action, ctx, effect_key="sp"):
                    effects = self.resolve_active_effects(skill, action, ctx)
                    for effect in effects:
                        self.resolve_sp_up_effect_passive(effect, turn, style, ctx, only_od=True)
                        # 对于非破盾时恢复sp的ex双动技能
                        if has_status_id(style, 125) and skill.ex_skill and not effect.get("need_break"):
                            self.resolve_sp_up_effect_passive(effect, turn, style, ctx, only_od=True)

        self.resolve_tmp_od(turn, direct=False)

    def apply_member_actions(self, turn: Turn):
        """
        结算当前actions的所有效果，为消耗了的status进行标记
        after_ex_use
        on_use_specific_skill
        on_sp_up_by_nonself_active_skill
        on_attack_weak
        on_relieve_enemy_buff(_attack)
        on_use_specific_status_skill
        on_pursuit  # 暗四妹
        on_use_od_cost_skill
        after_action
        """
        # 修改超越量表
        super_scale_element = turn.battle.super_scale.get("element")
        super_scale_value = turn.battle.super_scale.get("value")
        if super_scale_element and super_scale_value < 100:
            scale_add = 0
            for slot in turn.order[:3]:
                style = turn.team[slot]
                if matches_element(style, super_scale_element) and turn.actions[style.slot]:
                    scale_add += 4
            turn.battle.super_scale["value"] = min(super_scale_value + scale_add, 100)
        # 应用每个角色的技能effect
        skill_ids = [action.get("id") if action is not None else None for action in turn.actions]
        # 判断技能应用顺序和四妹是否自动追击
        simei_style = simei_action = None
        simei_ex = False
        action_type = []  # 1为非攻击技能/无行动，2为攻击技能，3为后排
        for i, slot in enumerate(turn.order):
            skill_id, style, action = skill_ids[slot], turn.team[slot], turn.actions[slot]
            if not skill_id:
                action_type.append(1)
            elif i > 2:
                action_type.append(3)
                if skill_id == 4:
                    simei_style = style
                    simei_action = action
            else:
                if skill_id == 1:  # 普通行动
                    action_type.append(2)
                elif skill_id == 2:  # 指挥行动
                    action_type.append(1)
                else:  # 一般的skill
                    skill = find_skill_by_id(style, skill_id)
                    if is_attack_skill(skill):
                        action_type.append(2)
                    else:
                        action_type.append(1)
        # 应用每个角色的技能
        for _, slot in sorted(zip(action_type, turn.order), key=lambda item: item[0]):
            skill_id, style, action = skill_ids[slot], turn.team[slot], turn.actions[slot]
            if not skill_id or skill_id in (1, 3):  # 没有行动、普攻、追击
                fresh_sprightly(style)
                continue
            elif skill_id == 4:  # 四妹自动追击，在最后未使用ex时fresh_sprightly
                continue
            elif skill_id == 2:  # 指挥行动
                effect = {"type": "attack_up_include_normal", "target": "ally_front", "status_id": 211, "duration": {"type": "ally_turn", "value": 1}}
                self.apply_effect(turn, style, effect, "指挥行动")
                fresh_sprightly(style)
            else:  # 一般的skill
                skill = find_skill_by_id(style, skill_id)
                attack_skill = is_attack_skill(skill)
                # 攻击技能需要把灵符等级增加1
                if attack_skill:
                    if skill.target == "all":
                        for monster in turn.battle.monsters:
                            if monster.exist:
                                self.resolve_talisman(monster)
                    elif skill.target == "single":
                        monster = turn.battle.monsters[action["target"]["slot"]]
                        self.resolve_talisman(monster)
                # 恢复轻快
                if skill.cost_type != "sp":
                    fresh_sprightly(style)
                # 进行技能effect相关结算准备
                ctx = Context(turn, style)
                if skill.conditions and skill.conditions.get("effects"):  # 这里有可能是target.作为起始
                    if skill.conditions.get("effects").startswith("target."):
                        ctx = Context(turn, turn.battle.monsters[action.get("target").get("slot")])
                # 结算effect前先判断是否有buff
                relieve_buff = monster_has_buff(turn, action["target"]["slot"])
                # 正式结算effects
                self.trigger_active_actions(style, skill, action, ctx)
                # 刻蚀的解除
                if skill.id == 741:
                    enemy = turn.battle.monsters[action["target"]["slot"]]
                    for status in enemy.statuses[::-1]:
                        if status.id == 223:
                            status.trash = True
                # 确定buff的消耗
                self.consume_buff_by_use(skill, style, ctx, action)
                simei_ex = self.resolve_simei_pursuit(simei_style, turn, simei_ex, attack_skill, skill, False)  # 四妹追击
                # 白虎的攻击双动，不会和ex技能双动同时存在
                if has_status_id(style, 227) and attack_skill:
                    # 正式结算effects
                    self.trigger_active_actions(style, skill, action, ctx, second=True)
                    # 确定buff的消耗
                    self.consume_buff_by_use(skill, style, ctx, action)
                    simei_ex = self.resolve_simei_pursuit(simei_style, turn, simei_ex, attack_skill, skill, False)  # 四妹追击
                # ex技能双动
                elif has_status_id(style, 125, allow_trash=True) and skill.ex_skill and skill.id != 741:  # 排除可怜的刻蚀大招
                    # 正式结算effects
                    self.trigger_active_actions(style, skill, action, ctx, second=True)
                    # 确定buff的消耗
                    self.consume_buff_by_use(skill, style, ctx, action)
                    simei_ex = self.resolve_simei_pursuit(simei_style, turn, simei_ex, attack_skill, skill, False)  # 四妹追击

                # 结算非od的被动效果
                if skill.cost_type == "od":
                    self.trigger_style_passives(turn, style, "on_use_od_cost_skill", without_od=True) 
                if skill.ex_skill:
                    self.trigger_style_passives(turn, style, "after_ex_use", without_od=True)
                if "on_use_specific_skill" in style.passive_triggers:
                    for passive in style.limit_break_passive:  # 目前只有突破被动有on_use_specific_skill
                        if passive.trigger == "on_use_specific_skill" and passive.skill_id == skill.id:
                            self.trigger_one_passive(passive, turn, style, without_od=True)
                if "on_use_specific_status_skill" in style.passive_triggers:
                    for passive in style.limit_break_passive:  # 目前只有突破被动有on_use_specific_status_skill
                        if passive.trigger == "on_use_specific_status_skill":
                            effect_types = [self.status_records.get(st_id).get("name") for st_id in passive.status_id]
                            if any(self.skill_has_effect_with(skill, action, ctx, effect_type=effect_type) for effect_type in effect_types):
                                self.trigger_one_passive(passive, turn, style, without_od=True)
                if attack_skill and skill.elements and skill.elements[0] in turn.battle.enemy_weaknesses:
                    self.trigger_style_passives(turn, style, "on_attack_weak", without_od=True)
                if action.get("on_break"):
                    self.trigger_style_passives(turn, style, "on_break_enemy", without_od=True)
                if self.skill_has_effect_with(skill, action, ctx, effect_type="remove_buff") and relieve_buff:
                    self.trigger_style_passives(turn, style, "on_relieve_enemy_buff", without_od=True)
                    if attack_skill:
                        self.trigger_style_passives(turn, style, "on_relieve_enemy_buff_attack", without_od=True)
                """on_active_zone在apply effect中进行，因为被动技能的场地展开也算"""
                # 有恢复sp的主动技能
                if self.skill_has_effect_with(skill, action, ctx, effect_key="sp"):
                    effects = self.resolve_active_effects(skill, action, ctx)
                    for effect in effects:
                        self.resolve_sp_up_effect_passive(effect, turn, style, ctx, only_od=False)

                # ex技能双动可能触发2次after_ex_use和on_sp_up_by_nonself_active_skill
                if has_status_id(style, 125, allow_trash=True) and skill.ex_skill:
                    self.trigger_style_passives(turn, style, "after_ex_use", without_od=True)
                    # 有恢复sp的主动技能（resource和heal_sp_by_token）
                    if self.skill_has_effect_with(skill, action, ctx, effect_key="sp"):
                        effects = self.resolve_active_effects(skill, action, ctx)
                        for effect in effects:
                            if not effect.get("need_break"):  # 对于不需要break的技能
                                self.resolve_sp_up_effect_passive(effect, turn, style, ctx, only_od=False)
                # 白虎攻击技能双动可能触发2次after_ex_use
                elif has_status_id(style, 227) and attack_skill and skill.ex_skill:
                    self.trigger_style_passives(turn, style, "after_ex_use", without_od=True)

        # token增加
        self.trigger_passives(turn, "after_action")
        # 四妹的buff清除和sp消耗
        if simei_style:
            if not simei_ex:  # 实际没有使用ex技能
                fresh_sprightly(simei_style)
            else:  # 实际使用了ex技能，则扣费和buff消耗
                simei_skill = find_skill_by_id(simei_style, 4)
                ctx = Context(turn, simei_style)
                simei_style.sp -= simei_skill.now_cost
                self.consume_buff_by_use(simei_skill, simei_style, ctx, simei_action)


    def resolve_turn_end_status(self, turn: Turn):
        """
        在应用完actions之后调用，把该清除掉的status进行清除
        同时把predict od存到od中
        """
        # 消耗status我方回合数
        for style in turn.team:
            # 附加回合不在行动中的不消耗
            if turn.additional_turn and not has_status_id(style, 20, True):
                continue
            for status in style.statuses:
                if status.duration_type == "ally_turn":
                    status.remaining -= 1
                    if status.remaining <= 0:
                        status.trash = True
            for status in style.statuses:
                if status.id == 229 and status.trash:
                    self.apply_effect(turn, style, {"type": "recoil", "status_id": 33, "target": "self", "duration": {"type": "ally_turn", "value": 1}}, "鬼神化副作用")
                    break
        # 消耗场地我方回合数
        if turn.battle.field["left_turn"] != -1:
            turn.battle.field["left_turn"] -= 1
            if turn.battle.field["left_turn"] == 0:
                turn.battle.field["left_turn"] = -1
                turn.battle.field["value"] = None

        # 受击与dp还原
        for slot, style in enumerate(turn.team):
            style.dp = 100
            be_attacked_times = (turn.actions[slot] or {}).get("be_attacked_times") or 0
            if be_attacked_times > 0:
                for i in range(be_attacked_times):
                    self.trigger_style_passives(turn, style, "on_attacked")
                for status in style.statuses:
                    if status.duration_type == "on_attacked":
                        status.remaining -= be_attacked_times
                        if status.remaining <= 0:
                            status.trash = True

        # 清除掉所有标记为trash的status
        for style in turn.team:
            for status in style.statuses[::-1]:
                if status.trash:
                    style.statuses.remove(status)
        for monster in turn.battle.monsters:
            for status in monster.statuses[::-1]:
                if status.trash:
                    monster.statuses.remove(status)

        # 把predict od存到od中，保持两者一致
        turn.od = min(turn.predicted_od, 300)
        turn.predicted_od = min(turn.predicted_od, 300)

        # 特殊actions还原
        for special in turn.special_actions:
            if special == "kelian_form_change":
                continue
            turn.special_actions[special] = 0


    def new_turn_label_refresh(self, turn: Turn):
        """
        根据上一回合的GUI给的label得到本回合的label，调用位于GUI的任何改动之前，返回当前是否为新回合
        消耗duration为敌方回合数的buff
        additional_turn
        od_timing
        od_level
        bonus
        turn_num
        """
        new_turn = False
        # 追加回合
        if any(has_status_id(style, 20) for style in turn.team):
            turn.additional_turn = True
            for style in turn.team:
                for status in style.statuses:
                    if status.id == 20 and not status.trash:
                        status.trash = True
        else:
            turn.additional_turn = False
        # 如果当前是追加回合，那么所有回合相关label都不应该变化
        if turn.additional_turn:
            pass
        # 非追加回合需要结算
        else:
            # od到新的一轮需要增加bonus
            if turn.od_timing:
                turn.bonus += 1
                # 如果超过说明od结束
                if turn.bonus > turn.od_level:
                    turn.bonus = 0
                    turn.od_level = 0
                    self.consume_od_end(turn)
                    # 后置od为new turn start
                    if turn.od_timing == "after":
                        turn.turn_num += 1
                        new_turn = True
                        self.consume_enemy_turn(turn)
                    turn.od_timing = None
            # 上回合不在od内
            else:
                turn.turn_num += 1
                new_turn = True
                self.consume_enemy_turn(turn)
        return new_turn

    def first_turn(self, state: dict) -> dict:
        """初始化战斗并生成 GUI 所需的首回合状态。"""
        turn = self.initialize(state)
        self.battle_start(turn)

        # 在这里添加用于recalculate的第0个turn和自身
        place_holder = deepcopy(turn)
        place_holder.turn_num = 0
        place_holder.actions = [None] * 6
        self.turns.extend([place_holder, turn])

        # 第一回合不需要resolve上一回合的行动effect以及状态消耗等，直接回合开始
        self.turn_start(turn, True)
        
        # 计算skills并生成gui所需members字典
        self.calculate_member_skills(turn)

        # 结算on_action_start被动
        self.trigger_passives(turn, "on_action_start")

        # 应用turn_start(turn)产生的默认行动
        self.apply_actions_od_shortcut(turn)

        return self.turn_to_dict(turn)

    def recalculate(self, gui_add_state, turn_number: int, *, inherit_battle=False) -> dict:
        """
        接受gui传入的state并直接覆盖当前的Turn类对应值：
        gui_add_state = {
            "member_dp": [float] * 6,
            'order': [int] * 6,  # 在recalculate中处理
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int, "on_break": False, "be_attacked_times": False}] * 6,
            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool}] * 3,
            'field': str or None,  # 回合开始前处理
            'od_timing': str or None,
            'od_level': int,
            "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0}, before/after
            "adjustments": {"od": 0.0, "members": [{"sp": 0, "token": 0} for _ in range(6)]}
        }
        重新计算从上回合开始计算后返回新state给GUI
        on_overdrive_start  前置OD
        after_ex_use
        on_use_specific_skill
        on_sp_up_by_nonself_active_skill
        user_select
        on_attack_weak
        on_relieve_enemy_buff(_attack)
        on_use_specific_status_skill
        on_active_zone
        on_pursuit
        on_use_od_cost_skill
        """
        # 如果recalculate的不是最后一个turn，那gui就应该递归进行下一个turn的recalculate
        # turn number从1开始，根据其新增内容和上一Turn的内容重新计算
        turn = deepcopy(self.turns[turn_number-1])

        if turn_number == 1:
            # 第0个turn是开场快照，首回合没有上一回合的行动或状态消耗
            turn.turn_num = 1
            new_turn = True
        else:
            # 结算上一回合的行动、状态，再更新回合label
            self.apply_member_actions(turn)
            self.resolve_turn_end_status(turn)
            new_turn = self.new_turn_label_refresh(turn)

        # HBRF没有这些手动调整，重放时直接沿用引擎计算出的状态
        if not inherit_battle:
            for position, monster in enumerate(turn.battle.monsters):
                replace_monster = gui_add_state["enemies"][position]
                monster.exist = replace_monster["exist"]
                monster.damage_rate = replace_monster["damage_rate"]
                monster.down = replace_monster["down"]
                for status in monster.statuses:
                    if status.id == 170 and not monster.down:
                        monster.statuses.remove(status)
                        break
            if turn.battle.field["value"] != gui_add_state["field"]:
                turn.battle.field["value"] = gui_add_state["field"]
                turn.battle.field["left_turn"] = -1

            for slot, style in enumerate(turn.team):
                style.dp = gui_add_state["member_dp"][slot]

        # 新回合开始的被动和机制触发
        self.turn_start(turn, new_turn)

        # 此处更新adjustments
        for slot, style in enumerate(turn.team):
            style.sp += gui_add_state["adjustments"]["members"][slot]["sp"]
            style.token += gui_add_state["adjustments"]["members"][slot]["token"]
        turn.od = min(gui_add_state["adjustments"]["od"] + turn.od, 300)
        turn.predicted_od = min(gui_add_state["adjustments"]["od"] + turn.predicted_od, 300)

        # 此处应用special_actions的可镰
        turn.special_actions["kelian_form_change"] = gui_add_state["special_actions"]["kelian_form_change"]

        # 此处应用special_actions的前置od前
        for special_trigger in ("demonic_rage", "all_out_attack", "demon_cavalry"):
            turn.special_actions[special_trigger] = gui_add_state["special_actions"][special_trigger]
            times = turn.special_actions[special_trigger]
            if times:
                match special_trigger:
                    case "demonic_rage":
                        self.using_demonic_rage(turn, before_od=True)
                    case "all_out_attack":
                        od_added = monster_num(turn) * 7 * turn.battle.default_hit
                        turn.od = min(turn.od + od_added, 300)
                        turn.predicted_od = min(turn.predicted_od + od_added, 300)
                    case "demon_cavalry":
                        self.using_demon_cavalry(turn, times, before_od=True)

        # 此处应用od设置
        pre_od_timing = turn.od_timing
        self.od_legalization(turn, gui_add_state)
        # 开前置od效果
        if turn.od_timing == "before" and pre_od_timing == None:
            sp_added_dict = {1: 5, 2: 12, 3: 20}
            sp_added = sp_added_dict[turn.od_level]
            turn.bonus = 1
            for style in turn.team:
                add_sp(style, {"sp": sp_added, "limit": 99})
            turn.od -= turn.battle.od_consume * turn.od_level
            turn.predicted_od -= turn.battle.od_consume * turn.od_level
            self.trigger_passives(turn, "on_overdrive_start")  # 暂时没有跟od相关的效果

        # 此处应用special_actions的前置od后
        for special_trigger in ("demonic_rage_after", "all_out_attack_after", "demon_cavalry_after"):
            turn.special_actions[special_trigger] = gui_add_state["special_actions"][special_trigger]
            times = turn.special_actions[special_trigger]
            if times:
                match special_trigger:
                    case "demonic_rage_after":
                        self.using_demonic_rage(turn, before_od=False)
                    case "all_out_attack_after":
                        od_added = monster_num(turn) * 7 * turn.battle.default_hit
                        turn.predicted_od = min(turn.predicted_od + od_added, 300)
                    case "demon_cavalry_after":
                        self.using_demon_cavalry(turn, times, before_od=False)

        # 追加回合只能在原前排中交换有行动资格的角色
        order = gui_add_state["order"]
        if not turn.additional_turn or (
            sorted(order[:3]) == sorted(turn.order[:3]) and order[3:] == turn.order[3:] and
            all(old == new or has_status_id(turn.team[old], 20, True)
                for old, new in zip(turn.order[:3], order[:3]))
        ):
            turn.order = order.copy()
        # 按当前站位计算技能，再检查GUI传入的行动
        self.calculate_member_skills(turn)
        turn.actions = gui_add_state["actions"]
        # 检查actions是否合法，不合法则转换为对应的默认action
        self.action_legalization(turn)

        # 结算on_action_start被动
        self.trigger_passives(turn, "on_action_start")

        self.apply_actions_od_shortcut(turn)

        # 转换为GUI的字典
        result = self.turn_to_dict(turn)

        # 只有整个计算成功，才提交
        if turn_number == len(self.turns):
            self.turns.append(turn)
        else:
            self.turns[turn_number] = turn

        # 返回给GUI
        return result

    def advance(self) -> dict:
        """
        完全仅由GUI触发，计算下一回合的开始的默认状态，并把Turn表示成state进行返回
        取上一回合的状态copy为新的回合，并存入turns中
        实际完成actions的effect
        运行到回合结束结算各种status以及od等回合的判断
        运行到新回合开始并使用默认的行动
        on_action_start
        将turn转换为dict传给GUI
        """
        last_turn = self.turns[-1]
        turn = deepcopy(last_turn)

        # 结算上一个turn的实际actions
        self.apply_member_actions(turn)

        # 此处结算回合结束清除状态
        self.resolve_turn_end_status(turn)

        # resolve新的回合label
        new_turn = self.new_turn_label_refresh(turn)

        # 新回合开始的被动和机制触发
        self.turn_start(turn, new_turn)
        
        # member数据计算后存储在Turn中
        self.calculate_member_skills(turn)

        # 结算on_action_start被动，暂时没有和od相关的效果
        self.trigger_passives(turn, "on_action_start")

        # 运行turn_start给出的default行动，更新od等资源
        self.apply_actions_od_shortcut(turn)

        # 转换为GUI的字典
        result = self.turn_to_dict(turn)

        # 只有整个计算成功，才提交
        self.turns.append(turn)

        # 返回给GUI
        return result
    
    def truncate_after(self, turn_index):
        del self.turns[turn_index+1:]

__all__ = ['Simulation', 'Skill', 'Passive', 'LimitBreak', 'SupportSkill', 'Style', 'Monster', 'Battle', 'Turn', 'Status']
