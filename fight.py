import time
import cv2
# import numpy as np
from config import settings
from config import positions as pos
from config import templates as tpl
from vision.images import load_template
from window_operation import click_in_game, drag_in_game, find_window, capture_window
from utils import match_template, detect_button, wait_and_click, wait_until, wait_until_any_template
from hbrf import model as mod
from paths import SCRIPTS_DIR
import logging
from dataclasses import replace

log = logging.getLogger('hbr.fight')

def close_auto_fight(game):
    resolution = settings.current_resolution
    region = (0,0,resolution[0]//4,resolution[1]//8)
    templates = {"off": load_template(tpl.auto_off_fig), "on":load_template(tpl.auto_on_fig)}

    # 未找到会抛出异常
    name, pt = wait_until_any_template(game, templates, region=region, interval=0.1, warning="未匹配到自动战斗按钮")

    if name == "on":
        click_in_game(game, pt)

    return name

def detect_start_button(game, is_gray=False):
    resolution = settings.current_resolution
    if is_gray:
        t = tpl.start_action_gray_fig
    else:
        t = tpl.start_action_fig
    # 用r通道减g通道获得粉色信息
    template = cv2.subtract(load_template(t)[:, :, 2], load_template(t)[:, :, 1])
    region = (resolution[0]*3//4,resolution[1]//2,resolution[0]//4,resolution[1]//2)

    # 截取窗口区域
    screenshot = capture_window(game, region=region)

    channel = cv2.subtract(screenshot[:, :, 2], screenshot[:, :, 1])

    offset = region[:2]

    return match_template(template, channel, offset)

def detect_skip_button(game):
    resolution = settings.current_resolution
    region=(resolution[0]*2//3, 0, resolution[0]//3, resolution[1]//4)
    return detect_button(game, load_template(tpl.skip_fig), region=region)

def detect_od_button(game, od_mode, is_small=False):
    resolution = settings.current_resolution
    if is_small:  # 右上角小图标有od_0
        region=(resolution[0]*3//4, 0, resolution[0]//4, resolution[1]//4)
        template = load_template(tpl.od_figs[od_mode])
    else:  # 中间大图标没有od_0
        region=(0, resolution[1]//4, resolution[0], resolution[1]//2)
        template = load_template(tpl.od_figs_big[od_mode-1])
    return detect_button(game, template, region=region, threshold=0.85)

def detect_current_od(game):
    for level in range(4):
        if detect_od_button(game, level, is_small=True):
            return level

    raise RuntimeError("凹追击检测时未能识别当前 OD 等级")

def ensure_front(game, old_member_position, role, position):
    if position >2 :
        raise ValueError("特殊技能发动要求角色处于前排，请检查hbrf文件")
    
    i = old_member_position.index(role)
    # 角色已经在正确位置
    if i == position:
        return

    # 角色在后排先换到前排正确位置
    click_in_game(game, pos.member[i])
    click_in_game(game, pos.member[position])
    old_member_position[i], old_member_position[position] = old_member_position[position], old_member_position[i]
    return 

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

def operate_one_turn(game, old_member_position, role_skill_num: dict, action: mod.BattleTurn, need_od_check=False):
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

                # 选择技能目标我方角色
                if target_position in {1,2,3,4,5,6}:
                    click_in_game(game, pos.member[member_position_output.index(target_position)])

                # 区分指向星癌体
                elif target_position in {7,8,9}:
                    # 不知道为啥一定点两次才起作用
                    click_in_game(game, pos.monster[target_position-7])
                    click_in_game(game, pos.monster[target_position-7])

            elif target_position in {7,8,9}:
                # 点击2次角色
                click_in_game(game, pos.member[i])
                time.sleep(1.5)
                click_in_game(game, pos.member[i])
                time.sleep(1)
                # 不知道为啥一定点两次才起作用
                click_in_game(game, pos.monster[target_position-7])
                click_in_game(game, pos.monster[target_position-7])

    def OD_condition(OD_mode):
        pt = detect_button(game, load_template(tpl.od_figs_big[0]))
        if pt:
            time.sleep(0.1)
            wait_and_click(game, load_template(tpl.od_figs_big[OD_mode-1]), 
                           timeout=60,
                           warning=f"未匹配到目标OD{OD_mode}按钮", threshold=0.85)
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
        wait_and_click(game, load_template(tpl.od_figs_big[od_index]), warning=f"未匹配到OD{od_index+1}按钮", threshold=0.85)
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
        time.sleep(0.05)
        click_in_game(game, pos.OD, sleep=False)

        # 不需要凹追击检测od
        if not need_od_check:
            # 每次循环匹配OD1按钮，匹配到则点击所需OD，未匹配到继续点右上角OD按钮
            wait_until(lambda: OD_condition(OD_mode),
                    timeout=5*60,
                    interval=0.1,
                    warning=f"未匹配到OD{OD_mode}按钮")

            # 等到回合结束按钮重新出现
            wait_until(lambda: detect_start_button(game), 
                    warning="开OD后未匹配到回合结束按钮")
        # 需要检测od
        else:
            def detect_od_window():

                # 已进入下一回合，说明错过OD发动窗口
                if detect_start_button(game):
                    return "no"
                
                # OD选择窗口已经出现
                if detect_od_button(game, 1):
                    return "yes"

                # 尝试重新点击OD按钮，目前有概率在下一回合开始OD充足也会返回yes
                click_in_game(game, pos.OD, sleep=False)
                return None

            name = wait_until(
                detect_od_window,
                timeout=5 * 60,
                interval=0.5,
                warning="凹追击检测OD时未检测到OD选择界面或回合开始按钮"
            )
            pass_od_check = False
            pre_od = False
            current_od = 0
            time.sleep(0.5)
            if name == "yes":  # 进入了od界面，至少有od1
                for i in range(3):  # 检查od等级
                    if detect_od_button(game, 3-i):
                        current_od = 3-i
                        break
                if current_od >= OD_mode:
                    pass_od_check = True
                time.sleep(0.5)
                if detect_start_button(game, is_gray=True):  # 是前置od
                    pre_od = True
                    pass_od_check = False
                # 没检测到对应od/进入前置就要点od1，并等待回合开始，然后再退出
                if not pass_od_check:  
                    wait_and_click(game, load_template(tpl.od_figs_big[0]), 
                            timeout=60,
                            warning=f"未匹配到目标OD1按钮")
                    # 等到回合结束按钮重新出现
                    wait_until(lambda: detect_start_button(game), 
                                warning="开OD后未匹配到回合结束按钮")
            if not pass_od_check:  # 此时要么在bonus1里要么在下一回合，可以退出
                if pre_od:
                    msg = f"需要 后置OD{OD_mode} ，当前进入 前置OD{current_od}"
                else:
                    msg = f"需要 OD{OD_mode} ，当前为 OD{current_od}"
                raise mod.ODRetryRequired(msg)
            else:  # 凹追击成功
                log.info("%s 回合凹 OD%d 成功，继续战斗", action.label, OD_mode)
                wait_and_click(game, load_template(tpl.od_figs_big[OD_mode-1]), 
                               timeout=60,
                               warning=f"未匹配到目标OD{OD_mode}按钮", threshold=0.85)
                # 等到回合结束按钮重新出现
                wait_until(lambda: detect_start_button(game), 
                           warning="开OD后未匹配到回合结束按钮")

    return member_position_output

def fight(game, script: mod.BattleScript, auto_close=False):
    def local_role(role):  # 用于将7-12映射回1-6
        return role - (current_team - 1) * 6
    
    # 每支队伍独立维护站位，编号均为1-6
    team_positions = {
        team: [1, 2, 3, 4, 5, 6]
        for team in range(1, len(script.roles) // 6 + 1)
    }
    # 每支队伍独立维护技能数量，key也是局部编号1-6
    team_skill_nums = {
        team: {
            role.slot - (team - 1) * 6: len(role.skills)
            for role in script.roles[(team - 1) * 6:team * 6]
        }
        for team in team_positions
    }
    # 初始默认team为1
    current_team = 1

    # 设置关闭自动战斗flag
    has_turn_off_auto = False
    # 设置检查od凹追击flag，理论上只有CheckOD紧接BattleTurn才会触发检查
    need_od_check = False

    for action in script.actions:
        # 需要auto close并且遇到第一个不是mod.SkipEvent的行动
        if auto_close and not has_turn_off_auto and not isinstance(action, mod.SkipEvent):
            log.info("正在关闭自动战斗")
            close_auto_fight(game)
            has_turn_off_auto = True

        if isinstance(action, mod.CheckOD):  # check_od只负责修改flag
            need_od_check = True
            log.info("本回合需要凹追击")
            continue

        elif isinstance(action, mod.SkipEvent):  # 表示需要点击skip按钮
            log.info("正在跳过剧情")
            pt = wait_until(lambda: detect_skip_button(game),
                       timeout=5*60,
                       warning="未检测到跳过剧情按钮")
            if pt:
                time.sleep(1)
                click_in_game(game, pt)
                time.sleep(3)

        elif isinstance(action, mod.TeamEvent):  # 更改current_team
            current_team = action.team
            log.info("当前战斗队伍为：队伍%d", current_team)

        elif isinstance(action, mod.ChangeTeamEvent):  # 表示需要切换队伍
            log.info("正在切换队伍")
            wait_and_click(game, load_template(tpl.change_fig),
                           warning="未检测到切换队伍按钮")
            wait_and_click(game, load_template(tpl.OK_electric_fig),
                           warning="未检测到切换队伍后的OK按钮")

        elif isinstance(action, mod.ResetPositions):
            log.info("正在重新设定角色位置")
            # old_member_position = action.positions.copy()

        elif isinstance(action, mod.SpecialRoleButton):
            log.info("正在启动 %s 按钮", action.button)
            wait_until(lambda: detect_start_button(game),
                       timeout=5*60,
                       warning="未检测到回合结束按钮")

            ensure_front(game, team_positions[current_team], local_role(action.role), action.position)
            operate_role_button(game, action.button, action.position)

        elif isinstance(action, mod.SkillSwitch):
            log.info("正在切换角色技能")
            wait_until(lambda: detect_start_button(game),
                        timeout=5*60,
                        warning="未检测到回合结束按钮")
            local_slot = local_role(action.role)
            ensure_front(game, team_positions[current_team], local_slot, action.position)
            # 如果角色本来就在前排
            operate_skill_switch(game, action.position, local_slot, action.skill, team_skill_nums[current_team])

        elif isinstance(action, mod.SpecialGlobalButton):
            log.info("正在使用 %s 小按钮", action.button)
            wait_until(lambda: detect_start_button(game),
                        timeout=5*60,
                        warning="未检测到回合结束按钮")
            wait_and_click(game, load_template(tpl.GLOBAL_BUTTON_CONFIG[action.button]), warning=f"未检测到{action.button}按钮")
            
        elif isinstance(action, mod.BattleTurn):  # 表示正常进行行动回合
            Turn = action.label
            log.info("正在进行 %s 回合行动", Turn)
            # 把action的role编号都替换为1-6
            local_action = replace(
                action,
                actions=[
                    replace(move, role=local_role(move.role))
                    for move in action.actions
                ]
            )
            # 到下一个回合了
            wait_until(lambda: detect_start_button(game),
                       timeout=5*60,
                       warning="未检测到回合结束按钮")

            # 前置od需要凹追击时
            if need_od_check and action.od < 0:
                od_check = abs(action.od)
                time.sleep(0.5)
                current_od = detect_current_od(game)
                # 没有成功则给出重新开始战斗信号，成功则继续运行
                if current_od < od_check:
                    raise mod.ODRetryRequired(
                        f"需要 OD{od_check} ，当前为 OD{current_od}"
                    )
                else:
                    log.info("%s 回合凹 OD%d 成功，当前为 OD%d，继续战斗", action.label, od_check, current_od)

            team_positions[current_team] = operate_one_turn(
                game=game, 
                old_member_position=team_positions[current_team].copy(), 
                role_skill_num=team_skill_nums[current_team],
                action=local_action,
                need_od_check=need_od_check)
            # 防止重复点击，可等待一段时间
            time.sleep(3)

        need_od_check = False  # 还原need_od_check为false

def restart_battle(game, attempt, e):
    log.info(
        "第 %d 次凹追击失败：%s",
        attempt, e
    )
    wait_and_click(game, load_template(tpl.back_fig), warning="未检测到返回按钮")
    wait_and_click(game, load_template(tpl.retry_fig), warning="未检测到重试按钮")
    wait_and_click(game, load_template(tpl.OK_fig), warning="未检测到确定按钮")
    time.sleep(2)  # 等待战斗重试加载

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
    fight_script = mod.load_hbrf(SCRIPTS_DIR / "test111.hbrf")
    # """异时层由于有很多剧情，暂时不能自动关闭auto战斗"""
    fight(game, fight_script, auto_close=False)
    # fight(game, fight_config, auto_close=True)

