from dataclasses import dataclass, field
from pathlib import Path
from config import templates as tpl
import re

"""
未来可以增加的内容：平A、选择怪物目标、技能切换、小按钮
"""
# 角色
@dataclass
class Role:
    slot: int
    name: str
    skills: list[str] = field(default_factory=list)

# 使用技能的move
@dataclass
class SkillAction:
    role: int
    skill: int = 0
    target: int | None = None

# 战斗中行动一回合
@dataclass
class BattleTurn:
    label: str
    od: int
    actions: list[SkillAction]

# 跳过剧情
@dataclass
class SkipEvent:
    pass

# 切换队伍
@dataclass
class ChangeTeamEvent:
    pass

# waki/总攻击的全局小按钮
@dataclass
class SpecialGlobalButton:
    button: str

# 切换技能属性
@dataclass
class SkillSwitch:
    role: int
    skill: int
    position: int  # 这里直接0，1，2但写在脚本里+1变成更易读的1，2，3

# 可怜/司令的前排技能按钮
@dataclass
class SpecialRoleButton:
    role: int
    position: int  # 这里直接0，1，2但写在脚本里+1变成更易读的1，2，3
    button: str

# 凹追击检测od行动
@dataclass
class CheckOD:
    pass

class ODRetryRequired(Exception):
    pass

# 切换队伍信号，不点击换队按钮
@dataclass
class TeamEvent:
    team: int  # 1 或 2

# 整个战斗脚本
BattleAction = BattleTurn | SkipEvent | ChangeTeamEvent | SpecialGlobalButton | SkillSwitch | SpecialRoleButton | CheckOD | TeamEvent
@dataclass
class BattleScript:
    roles: list[Role]
    actions: list[BattleAction]


def validate_hbrf(script: BattleScript):
    if len(script.roles) not in (6, 12):
        raise ValueError("每支队伍必须有6名角色")

    role_ids = {role.slot for role in script.roles}
    role_by_id = {role.slot: role for role in script.roles}
    moster_ids = {7, 8, 9}

    if role_ids != set(range(1, len(script.roles) + 1)):
        raise ValueError("一队角色编号为1-6，二队编号为7-12")

    for role in script.roles:
        if len(role.skills) > 6:
            raise ValueError("角色暂不支持超过6个技能")

    # 区分2个team和1个team
    current_team = 1
    team_count = len(script.roles) // 6

    for i, action in enumerate(script.actions):

        if isinstance(action, TeamEvent):
            if team_count != 2:
                raise ValueError(f"单队伍不应出现队伍切换信号")
            if not 1 <= action.team <= 2:
                raise ValueError(f"非法队伍编号: {action.team}")
            current_team = action.team
            continue

        active_role_ids = set(range(
            (current_team - 1) * 6 + 1,
            current_team * 6 + 1
        ))

        if isinstance(action, CheckOD):
            # od检测不能位于最后一个
            if i+1 >= len(script.actions):
                raise ValueError(
                    f"OD检测后面没有战斗行动"
                )
            next_action = script.actions[i+1]
            if not isinstance(next_action, BattleTurn) or next_action.od == 0:
                raise ValueError(
                    f"OD检测后面不是战斗行动或战斗行动不发动OD"
                )

        elif isinstance(action, SpecialRoleButton):
            if action.button not in tpl.ROLE_BUTTON_CONFIG:
                raise ValueError(
                    f"非法前排角色特殊按钮: {action.button}"
                )
            if action.role not in active_role_ids:
                raise ValueError(
                    f"{action.button}的对应角色: {action.role}不属于队伍{current_team}"
                )
            if action.position not in (0,1,2):
                raise ValueError(
                    f"{action.button}的对应角色必须站在前排"
                )
            
        elif isinstance(action, SkillSwitch):
            if action.role not in active_role_ids:
                raise ValueError(
                    f"切换技能的角色不属于队伍{current_team}: {action.role}"
                )
            if not 1 <= action.skill <= len(role_by_id[action.role].skills):
                raise ValueError(
                    f"切换非法技能编号: {action.skill}"
                )
            if action.position not in (0,1,2):
                raise ValueError(
                    f"切换技能的对应角色必须站在前排"
                )

        elif isinstance(action, SpecialGlobalButton):
            if action.button not in tpl.GLOBAL_BUTTON_CONFIG:
                raise ValueError(
                    f"非法全局按钮: {action.button}"
                )

        elif isinstance(action, BattleTurn):

            if not -3 <= action.od <= 3:
                raise ValueError(
                    f"非法OD值: {action.od}"
                )

            if len(action.actions) != 3:
                raise ValueError(
                    f"{action.label}: 前排必须有3人"
                )

            front_roles = [
                x.role
                for x in action.actions
            ]

            if len(set(front_roles)) != 3:
                raise ValueError(
                    f"{action.label}: 前排角色重复"
                )

            for move in action.actions:

                if move.role not in active_role_ids:
                    raise ValueError(
                        f"{action.label}: 角色{move.role}不属于队伍{current_team}"
                    )

                if move.target is not None and move.target not in range(1, 10):
                    raise ValueError(
                        f"非法技能目标: {move.target}"
                    )

                role = role_by_id[move.role]

                if move.skill < 0:
                    raise ValueError("技能编号不能小于0")

                if move.skill > len(role.skills):
                    raise ValueError(
                        f"{role.name}不存在技能{move.skill}"
                    )

def load_hbrf(filepath) -> BattleScript:
    filepath = Path(filepath)

    # ---------- 预处理文本文件 ----------
    with filepath.open(encoding="utf-8") as f:
        lines = [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]

    if len(lines) < 6:
        raise ValueError("HBRF至少需要定义6名角色")

    # ---------- Roles ----------
    role_lines = []

    for line in lines:
        if ":" not in line or "=" in line:
            break
        role_lines.append(line)

    if len(role_lines) not in (6, 12):
        raise ValueError("HBRF必须定义6名或12名角色")

    roles = []

    # 前6行或12行是角色定义区
    for slot, line in enumerate(role_lines, start=1):
        if ":" not in line:
            raise ValueError(f"角色定义格式错误: {line}")

        name, skill_text = line.split(":", 1)

        name = name.strip()

        skills = [
            skill.strip()
            for skill in skill_text.split(",")
            if skill.strip()
        ]

        if not name:
            raise ValueError(f"第{slot}名角色没有名称")

        if len(skills) > 6:
            raise ValueError("角色暂不支持超过6个技能")

        roles.append(
            Role(
                slot=slot,
                name=name,
                skills=skills
            )
        )

    role_by_name = {
        role.name: role
        for role in roles
    }

    if len(role_by_name) != len(roles):
        raise ValueError("角色名称不能重复")

    # ---------- Actions ----------
    actions = []

    for line in lines[len(roles):]:

        if line == "skip":
            actions.append(SkipEvent())
            continue

        if line == "change":
            actions.append(ChangeTeamEvent())
            continue

        if re.fullmatch(r"Team\s*=\s*[12]", line):
            actions.append(TeamEvent(int(line.split("=", 1)[1].strip())))
            continue

        if line in tpl.GLOBAL_BUTTON_CONFIG:
            actions.append(SpecialGlobalButton(line))
            continue

        # 可怜/司令这种前排点击技能按钮或切换技能的行动：code | name | 技能/无 | 位置
        if "|" in line:
            parts = [x.strip() for x in line.split("|")]
            command = parts[0]

            # 可怜/司令这种前排点击技能按钮的行动
            if command in tpl.ROLE_BUTTON_CONFIG and len(parts) == 3:
                name, need_pos = parts[1], int(parts[2])
                if name not in role_by_name:
                    raise ValueError(
                        f"{command}指示的角色名: {name}不存在"
                    )
                if need_pos not in (1,2,3):
                    raise ValueError(
                        f"{command}的对应角色必须站在前排"
                    )

                actions.append(
                    SpecialRoleButton(
                        role=role_by_name[name].slot,
                        button=command,
                        position=need_pos-1
                    )
                )
                continue

            # 切换某角色的技能属性
            elif command == "skill" and len(parts) == 4:
                switch_role_name, switch_skill, need_pos = parts[1], int(parts[2]), int(parts[3])
                if switch_role_name not in role_by_name:
                    raise ValueError(
                        f"未知角色: {switch_role_name}"
                    )
                if need_pos not in (1,2,3):
                    raise ValueError(
                        f"{command}的对应角色必须站在前排"
                    )
                # 技能编号的大小问题将在validate中验证
                actions.append(
                    SkillSwitch(
                        role=role_by_name[switch_role_name].slot,
                        skill=switch_skill,
                        position=need_pos-1
                    )
                )
                continue

            # 包含“|”字符但不是skill开头或可怜司令等的是无效指令
            else: 
                raise ValueError(f"无效指令: {line}")

        #增加check_od，为fight提供凹追击的信号
        if line == "check_od":
            actions.append(CheckOD())
            continue

        # ---------- Normal battle turn ----------
        if "=" not in line:
            raise ValueError(f"无法识别HBRF语句: {line}")

        label, value = line.split("=", 1)

        parts = [
            x.strip()
            for x in value.split(";")
        ]

        # od+3个角色的行动
        if len(parts) < 4:
            raise ValueError(f"回合格式错误: {line}")

        od = int(parts[0])

        turn_actions = []

        for move in parts[1:]:

            if ":" not in move:
                raise ValueError(
                    f"角色行动格式错误: {label.strip()} 中 {move}"
                )

            role_name, skill_info = move.split(":", 1)

            role_name = role_name.strip()

            if role_name not in role_by_name:
                raise ValueError(
                    f"未知角色: {role_name}"
                )

            values = [
                int(x.strip())
                for x in skill_info.split(",")
            ]

            if len(values) != 2:
                raise ValueError(
                    f"无法解析: {label.strip()} 中 {move}，技能格式必须是 skill,target"
                )

            skill, target = values

            turn_actions.append(
                SkillAction(
                    role=role_by_name[role_name].slot,
                    skill=skill,
                    target=None if target == 0 else target
                )
            )

        if len(turn_actions) != 3:
            raise ValueError(
                f"每个正常回合应定义3名前排角色: {line}"
            )

        actions.append(
            BattleTurn(
                label=label.strip(),
                od=od,
                actions=turn_actions
            )
        )

    script = BattleScript(
        roles=roles,
        actions=actions
    )

    validate_hbrf(script)

    return script

def save_hbrf(script: BattleScript, filepath):
    validate_hbrf(script)

    filepath = Path(filepath)

    with filepath.open("w", encoding="utf-8") as f:

        f.write("# 配队和技能（用于初始化角色编号为1-6，目前支持技能数最多6个，角色最少需要装备3个技能）\n")

        role_num = len(script.roles)

        for i, role in enumerate(sorted(script.roles, key=lambda r: r.slot),1):
            if role_num == 12 and i == 1:
                f.write("#队伍1\n")
            skills = ", ".join(role.skills)
            f.write(f"{role.name}: {skills}\n")
            if role_num == 12 and i == 6:
                f.write("\n#队伍2\n")

        f.write("\n")
        f.write(
            "# 回合 = OD; 角色: 技能,目标（od后置1或2或3，前置为负，0为不开od）\n"
        )

        role_by_id = {
            role.slot: role
            for role in script.roles
        }

        for action in script.actions:

            if isinstance(action, SkipEvent):
                f.write("skip\n")

            elif isinstance(action, ChangeTeamEvent):
                f.write("change\n")

            elif isinstance(action, TeamEvent):
                f.write(f"Team = {action.team}\n")

            elif isinstance(action, CheckOD):
                f.write("check_od\n")

            elif isinstance(action, SpecialGlobalButton):
                f.write(f"{action.button}\n")

            elif isinstance(action, SpecialRoleButton):
                f.write(f"{action.button} | {role_by_id[action.role].name} | {action.position+1}\n")

            elif isinstance(action, SkillSwitch):
                f.write(f"skill | {role_by_id[action.role].name} | {action.skill} | {action.position+1}\n")

            elif isinstance(action, BattleTurn):

                fields = [
                    f"{action.label} = {action.od}"
                ]

                for move in action.actions:

                    role = role_by_id[move.role]

                    target = (
                        move.target
                        if move.target is not None
                        else 0
                    )

                    fields.append(
                        f"{role.name}: "
                        f"{move.skill},{target}"
                    )

                f.write(
                    "; ".join(fields) + "\n"
                )
            else:
                raise ValueError(
                    f"暂不支持的action class: {type(action)}"
                )