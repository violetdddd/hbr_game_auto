import time
import cv2
import numpy as np
from config.config import resolution, skip, skill_123, member, next_turn, OD, start_action_fig, skip_fig, change, ok, skill_4_drug, od_figs, od_figs_big, switch_skills, no_where, auto_on_fig, auto_off_fig, kelian_change_fig, Siling_GuiShenHua_fig
from window_operation import click_in_game, drag_in_game, find_window, capture_window
from utils import match_template, detect_button, wait_and_click, wait_until, wait_until_any_template
# from window_operation import position_monitor

def parse_hbrf_file(filepath):  
    """返回一个列表，每个元素为一个回合的行动列表，包括OD状态、前排角色位置和技能"""
    with open(filepath, encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    # 1. 解析角色定义
    role_dict = {}
    role_skill_num = []
    lines_without_comments = [line for line in lines if not line.startswith('#')]
    role_lines = lines_without_comments[:6]
    for idx, line in enumerate(role_lines, start=1):
        name = line.split(':')[0].strip()
        role_skill_num.append(line.count(",")+1)  # 统计多少逗号来确定技能数
        role_dict[name] = idx

    # 2. 解析行动部分
    actions = []
    actions.append(role_skill_num)  # actions里第一个元素是角色用到的技能数量

    for line in lines_without_comments[6:]:
        if line.startswith('skip'):
            actions.append(0)  # 0表示需要点skip
        elif line.startswith('change'):
            actions.append(1)  # 0表示需要切换队伍
        elif line.startswith('前置OD'):  # 在V4改版后弃用此条
            actions.append(2)  # 2表示开启前置od
        elif line.startswith('reset'):
            turn, rest = line.split('=')
            reset_positions = list(map(int, rest.split(',')))
            actions.append(reset_positions)  # 2表示开启前置od

        else:
            turn, rest = line.split('=')
            rest_parts = [p.strip() for p in rest.split(';')]

            od = int(rest_parts[0])  # 取 OD
            moves = rest_parts[1:]   # 角色动作

            curr_pos = []
            skills = []

            for i, move in enumerate(moves, start=1):

                parts = move.split(':')
                name = parts[0].strip()
                skill_tuple = tuple(map(int, parts[1].split(',')))
                skills.append(skill_tuple)
                curr_pos.append(role_dict[name])
                    
            actions.append([turn.strip(), od, curr_pos.copy(), skills])

    return actions

def close_auto_fight(game):
    region = (0,0,resolution[0]//4,resolution[1]//8)
    templates = {"off": auto_off_fig, "on":auto_on_fig}

    # 未找到会抛出异常
    name, pos = wait_until_any_template(game, templates, region=region, interval=0.1, warning="未匹配到自动战斗按钮")

    if name == "on":
        click_in_game(game, pos)

    return name

def detect_start_button(game):
    # 用r通道减g通道获得粉色信息
    template = cv2.subtract(start_action_fig[:, :, 2], start_action_fig[:, :, 1])
    region = (resolution[0]*3//4,resolution[1]//2,resolution[0]//4,resolution[1]//2)

    # 截取窗口区域
    screenshot = capture_window(game, region=region)

    channel = cv2.subtract(screenshot[:, :, 2], screenshot[:, :, 1])

    offset = region[:2]

    return match_template(template, channel, offset)

def detect_skip_button(game):
    region=(resolution[0]*2//3, 0, resolution[0]//3, resolution[1]//4)
    return detect_button(game, skip_fig, region=region)

def detect_od_button(game, od_mode):
    region=(resolution[0]*3//4, 0, resolution[0]//4, resolution[1]//4)
    template = od_figs[od_mode-1]

    return detect_button(game, template, region=region)

def switch_skill(game, member_index, skill_index):
    click_in_game(game, member[member_index-1])
    click_in_game(game, switch_skills[skill_index-1])
    click_in_game(game, member[member_index-1])

def operate_one_turn(game, old_member_position, OD_mode, new_member_position, skills_setting, role_skill_num):
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
            click_in_game(game, member[step[0]])
            click_in_game(game, member[step[1]])

    def arrange_skills(member_position_output, skills_setting: list):  # 元素为元组，（技能，指向角色）
        for i in range(3):  # 前排的3名角色
            skill_position = skills_setting[i][0]
            target_position = skills_setting[i][1]
            if skill_position != 0:  # 不是普通攻击
                # 点击角色
                click_in_game(game, member[i])

                # 选择技能
                if skill_position <= 3:  # 不需要滑动
                    click_in_game(game, skill_123[skill_position])
                else:  # 只支持最多6个技能，先滑动再点击3个技能的位置
                    drag_in_game(game, skill_4_drug)
                    # 角色编号到指标的映射要-1
                    role_skill_max = role_skill_num[member_position_output[i]-1]
                    # 可以兼容技能数4-6
                    click_in_game(game, skill_123[3+skill_position-role_skill_max])

                # 选择技能目标
                if target_position != 0:  # 有指向角色
                    click_in_game(game, member[member_position_output.index(target_position)]) 

    def OD_condition():
        pos = detect_button(game, od_figs_big[0])
        if pos:
            time.sleep(0.1)
            wait_and_click(game, od_figs_big[OD_mode-1], warning=f"未匹配到目标OD{OD_mode}按钮")
            return pos
        else:
            # time.sleep(0.1)
            click_in_game(game, OD, sleep=False)

    # 稍微等待防止点击过快
    time.sleep(0.3)

    # V4改版后的前置OD
    if OD_mode < 0:
        click_in_game(game, OD)
        time.sleep(0.2)
        od_index = abs(OD_mode)-1
        wait_and_click(game, od_figs_big[od_index], warning=f"未匹配到OD{od_index+1}按钮")
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
    click_in_game(game, next_turn)

    # 后置OD
    if OD_mode > 0:
        # 防止动画过短点不到，先快速点一次OD
        time.sleep(0.02)
        click_in_game(game, OD, sleep=False)

        # 每次循环匹配OD1按钮，匹配到则点击所需OD，未匹配到继续点右上角OD按钮
        wait_until(OD_condition,
                   interval=0.1,
                   warning=f"未匹配到OD{OD_mode}按钮")

        # 等到回合结束按钮重新出现
        wait_until(lambda: detect_start_button(game), 
                   warning="开OD后未匹配到回合结束按钮")

    return member_position_output

def fight(game, fight_config, auto_close=False, need_switch=False):
    if auto_close:
        close_auto_fight(game)

    old_member_position = [1,2,3,4,5,6]  # 初始位置

    role_skill_num = fight_config[0]  # 各角色所用技能数量

    for turn_idx in range(1,len(fight_config)):
        turn_action = fight_config[turn_idx]

        if turn_action == 0:  # 表示需要点击skip按钮
            print("now skipping the dialog.")
            pos = wait_until(lambda: detect_skip_button(game),
                       timeout=5*60,
                       warning="未检测到跳过剧情按钮")
            if pos:
                time.sleep(1)
                click_in_game(game, pos)
                time.sleep(3)

        elif turn_action == 1:  # 表示需要切换队伍
            print(f"now switching team.")
            click_in_game(game, change)
            time.sleep(0.2)
            click_in_game(game, ok)
            
        else:  # 表示正常进行行动回合
            pos = wait_until(lambda: detect_start_button(game),
                       timeout=5*60,
                       warning="未检测到回合结束按钮")
            if pos:  # 到下一个回合了
                # 为了异时层一二队重新设置角色位置，其他时候并不需要
                if isinstance(turn_action, list) and len(turn_action) == 6:
                    print(f"now resetting team positions.")
                    old_member_position = turn_action
                else:
                    Turn = turn_action[0]
                    print(f"now fighting turn {Turn}.")
                    """技能/状态切换"""
                    if need_switch:
                        # if Turn == "1":
                        #     switch_skill(game, 3,2)
                        if Turn in ("5","6-od1","7-od2/2-追加"): # (1,5,6,9,10,14)
                            time.sleep(1)
                            if Turn == "1":
                                click_in_game(game, member[2])
                            else:
                                click_in_game(game, member[2])
                            # wait_and_click(game, kelian_change_fig, warning="未匹配到可怜切换按钮")
                            wait_and_click(game, Siling_GuiShenHua_fig, warning="未匹配到司令鬼神化按钮")
                            time.sleep(3)
                    """技能/状态切换"""
                    old_member_position = operate_one_turn(game, old_member_position.copy(), *turn_action[1:], role_skill_num)
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
    fight_config = parse_hbrf_file('hbrf/Encounter4.hbrf')
    """异时层由于有很多剧情，暂时不能自动关闭auto战斗"""
    fight(game, fight_config, auto_close=False, need_switch=True)
    # fight(game, fight_config, auto_close=True)

