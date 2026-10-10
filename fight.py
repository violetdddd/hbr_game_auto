import time
import cv2
# import numpy as np
from config.settings import resolution
from config import positions as pos
from config import templates as tpl
from vision.images import load_template
from window_operation import click_in_game, drag_in_game, find_window, capture_window
from utils import match_template, detect_button, wait_and_click, wait_until, wait_until_any_template
from hbrf import model as mod
from paths import SCRIPTS_DIR


def close_auto_fight(game):
    region = (0,0,resolution[0]//4,resolution[1]//8)
    templates = {"off": load_template(tpl.auto_off_fig), "on":load_template(tpl.auto_on_fig)}

    # 未找到会抛出异常
    name, pt = wait_until_any_template(game, templates, region=region, interval=0.1, warning="未匹配到自动战斗按钮")

    if name == "on":
        click_in_game(game, pt)

    return name

def detect_start_button(game):
    # 用r通道减g通道获得粉色信息
    template = cv2.subtract(load_template(tpl.start_action_fig)[:, :, 2], load_template(tpl.start_action_fig)[:, :, 1])
    region = (resolution[0]*3//4,resolution[1]//2,resolution[0]//4,resolution[1]//2)

    # 截取窗口区域
    screenshot = capture_window(game, region=region)

    channel = cv2.subtract(screenshot[:, :, 2], screenshot[:, :, 1])

    offset = region[:2]

    return match_template(template, channel, offset)

def detect_skip_button(game):
    region=(resolution[0]*2//3, 0, resolution[0]//3, resolution[1]//4)
    return detect_button(game, load_template(tpl.skip_fig), region=region)

def detect_od_button(game, od_mode):
    region=(resolution[0]*3//4, 0, resolution[0]//4, resolution[1]//4)
    template = load_template(tpl.od_figs[od_mode-1])

    return detect_button(game, template, region=region)

def ensure_front(game, old_member_position, role):
    i = old_member_position.index(role)
    # 角色已经在前排
    if i < 3:
        return i

    # 角色在后排先换到前排第一个
    click_in_game(game, pos.member[i])
    click_in_game(game, pos.member[0])
    old_member_position[i], old_member_position[0] = old_member_position[0], old_member_position[i]
    return 0

def operate_skill_switch(game, member_pos, member_slot, skill_index, role_skill_num: dict):
    """
    已经在前排的角色使用此函数进行技能属性切换
    """
    click_in_game(game, pos.member[member_pos])
    if skill_index in (1,2,3):
        click_in_game(game, pos.switch_skills[skill_index-1])
    # validate过，认为一定不会超过角色技能数，同时技能数不超过6
    else:
        drag_in_game(game, pos.skill_4_drug)
        # 获取该角色最大技能数
        role_skill_max = role_skill_num[member_slot]
        # 可以兼容技能数4-6
        click_in_game(game, pos.switch_skills[2+skill_index-role_skill_max])
    click_in_game(game, pos.member[member_pos])

def operate_role_button(game, button: str, member_position):
    """
    已经在前排的角色使用此函数发动技能小按钮
    """
    click_in_game(game, pos.member[member_position])
    wait_and_click(game, load_template(tpl.ROLE_BUTTON_CONFIG[button]), warning=f"未匹配到{button}按钮")
    time.sleep(3)

def operate_one_turn(game, old_member_position, role_skill_num: dict, action: mod.BattleTurn):
    """
    操作游戏一回合，包含前置OD、调整位置、选择技能、后置OD
    """
    def generate_swaps(old_member_position, new_member_position):
        steps = []  # 存储位置编号为0-5
        for i in range(3):  # 遍历新position（前排），利用swap调整旧的position
            if old_member_position[i] != new_member_position[i]:
                for j in range(i+1, 6):  # 遍历旧的position，选择与新position对应的
                    if old_member_position[j] == new_member_position[i]:
                        steps.append((j,i))
                        old_member_position[i], old_member_position[j] = old_member_position[j], old_member_position[i]
                        break
        return steps, old_member_position
    
    def swap_position(swap_steps):
        for step in swap_steps:
            click_in_game(game, pos.member[step[0]])
            click_in_game(game, pos.member[step[1]])

    def arrange_skills(member_position_output, skills_setting: list):  # 元素为元组，（技能，指向角色）
        for i in range(3):  # 前排的3名角色
            skill_position = skills_setting[i][0]
            target_position = skills_setting[i][1]
            if skill_position != 0:  # 不是普通攻击
                # 点击角色
                click_in_game(game, pos.member[i])

                # 选择技能
                if skill_position <= 3:  # 不需要滑动
                    click_in_game(game, pos.skill_123[skill_position])
                else:  # 只支持最多6个技能，先滑动再点击3个技能的位置
                    drag_in_game(game, pos.skill_4_drug)
                    # 获取该角色最大技能数
                    role_skill_max = role_skill_num[member_position_output[i]]
                    # 可以兼容技能数4-6
                    click_in_game(game, pos.skill_123[3+skill_position-role_skill_max])

                # 选择技能目标
                if target_position is not None:  # 有指向角色
                    click_in_game(game, pos.member[member_position_output.index(target_position)]) 

    def OD_condition(OD_mode):
        pt = detect_button(game, load_template(tpl.od_figs_big[0]))
        if pt:
            time.sleep(0.1)
            wait_and_click(game, load_template(tpl.od_figs_big[OD_mode-1]), 
                           timeout=60,
                           warning=f"未匹配到目标OD{OD_mode}按钮")
            return pt
        else:
            # time.sleep(0.1)
            click_in_game(game, pos.OD, sleep=False)

    # 稍微等待防止点击过快
    time.sleep(0.3)

    # 提取action中数据
    OD_mode = action.od
    new_member_position = [move.role for move in action.actions]
    skills_setting = [(move.skill, move.target) for move in action.actions]

    # V4改版后的前置OD
    if OD_mode < 0:
        click_in_game(game, pos.OD)
        time.sleep(0.2)
        od_index = abs(OD_mode)-1
        wait_and_click(game, load_template(tpl.od_figs_big[od_index]), warning=f"未匹配到OD{od_index+1}按钮")
        wait_until(lambda: detect_start_button(game), 
                   warning="开OD后未匹配到回合结束按钮")
        time.sleep(0.2)

    # 先调整位置
    steps, member_position_output = generate_swaps(old_member_position, new_member_position)
    if len(steps) != 0:
        swap_position(steps)
    
    # 再选择技能
    arrange_skills(member_position_output, skills_setting)

    # 下一回合
    click_in_game(game, pos.next_turn)

    # 后置OD
    if OD_mode > 0:
        # 防止动画过短点不到，先快速点一次OD
        time.sleep(0.02)
        click_in_game(game, pos.OD, sleep=False)

        # 每次循环匹配OD1按钮，匹配到则点击所需OD，未匹配到继续点右上角OD按钮
        wait_until(lambda: OD_condition(OD_mode),
                   timeout=5*60,
                   interval=0.1,
                   warning=f"未匹配到OD{OD_mode}按钮")

        # 等到回合结束按钮重新出现
        wait_until(lambda: detect_start_button(game), 
                   warning="开OD后未匹配到回合结束按钮")

    return member_position_output

def fight(game, script: mod.BattleScript, auto_close=False):
    if auto_close:
        close_auto_fight(game)

    # 初始化位置和角色技能数量
    old_member_position = [1,2,3,4,5,6]  # 初始位置
    # 角色slot到角色技能数量的映射
    role_skill_num = {role.slot: len(role.skills) for role in script.roles}

    for action in script.actions:

        if isinstance(action, mod.SkipEvent):  # 表示需要点击skip按钮
            print("now skipping the dialog.")
            pt = wait_until(lambda: detect_skip_button(game),
                       timeout=5*60,
                       warning="未检测到跳过剧情按钮")
            if pt:
                time.sleep(1)
                click_in_game(game, pt)
                time.sleep(3)

        elif isinstance(action, mod.ChangeTeamEvent):  # 表示需要切换队伍
            print(f"now switching team.")
            click_in_game(game, pos.change)
            time.sleep(0.2)
            click_in_game(game, pos.ok)

        elif isinstance(action, mod.ResetPositions):
            print(f"now resetting team positions.")
            old_member_position = action.positions.copy()

        elif isinstance(action, mod.SpecialRoleButton):
            wait_until(lambda: detect_start_button(game),
                       timeout=5*60,
                       warning="未检测到回合结束按钮")
            print(f"now activating {action.button} button.")

            now_pos = ensure_front(game, old_member_position, action.role)
            operate_role_button(game, action.button, now_pos)

        elif isinstance(action, mod.SkillSwitch):
            wait_until(lambda: detect_start_button(game),
                        timeout=5*60,
                        warning="未检测到回合结束按钮")
            print(f"now switching skill.")
            now_pos = ensure_front(game, old_member_position, action.role)
            # 如果角色本来就在前排
            operate_skill_switch(game, now_pos, action.role, action.skill, role_skill_num)

        elif isinstance(action, mod.SpecialGlobalButton):
            wait_until(lambda: detect_start_button(game),
                        timeout=5*60,
                        warning="未检测到回合结束按钮")
            print(f"now activating {action.button} button.")
            wait_and_click(game, load_template(tpl.GLOBAL_BUTTON_CONFIG[action.button]), warning=f"未检测到{action.button}按钮")
            
        elif isinstance(action, mod.BattleTurn):  # 表示正常进行行动回合
            # 到下一个回合了
            wait_until(lambda: detect_start_button(game),
                       timeout=5*60,
                       warning="未检测到回合结束按钮")
            
            Turn = action.label
            print(f"now fighting turn {Turn}.")

            old_member_position = operate_one_turn(
                game=game, 
                old_member_position=old_member_position.copy(), 
                role_skill_num=role_skill_num,
                action=action)
            # 防止重复点击，可等待一段时间
            time.sleep(3)

import ctypes

def is_admin() -> bool:
    """
    返回当前进程是否具有管理员权限（Windows）。
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
    
if __name__ == "__main__":
    # position_monitor()
    print(is_admin())
    game = find_window()
    fight_script = mod.load_hbrf(SCRIPTS_DIR / "test.hbrf")
    # """异时层由于有很多剧情，暂时不能自动关闭auto战斗"""
    fight(game, fight_script, auto_close=False)
    # fight(game, fight_config, auto_close=True)

