from mouse_simulation import click_in_game, find_window, position_monitor, drag_in_game
from config import repeat_combat, OK_fig, again_fig, stone_fig, resolution, properties, wash_well_config, eazy_31C_fig, end_cardgame_fig, home_cardgame_fig, start_cardgame_position, skill_4_drug, no_where, stone_spare_fig, stone_tili_fig, ticket_orb_fig, use_most_fig, kaishi_fig, tiaozhan_fig, OD, od_figs_big, back_fig, retry_fig
from fight import fight, parse_hbrf_file, detect_start_button, operate_one_turn
from utils import detect_and_click_button, detect_button
import time

# 定义一局最多等待20min
MAX_TIME = 20*60

# 用于反复多次刷体力
def repeat_fight(game, fight_config, times, ticket="stone"):
    if ticket not in ("stone", "ticket", "spare"):
        raise Exception("入场券格式不正确，请填写stone, ticket或spare")
    """从使用体力位置开始循环"""
    def repeat_one_time():
        nonlocal counter
        time.sleep(1)
        if ticket == "ticket":  # 后续其他票要更新支持
            detect_and_click_button(game, ticket_orb_fig)
        elif ticket == "stone":
            detect_and_click_button(game, stone_tili_fig)
        elif ticket == "spare":
            detect_and_click_button(game, stone_spare_fig)
        detect_and_click_button(game, OK_fig)
        detect_and_click_button(game, use_most_fig)
        detect_and_click_button(game, OK_fig)
        # click_in_game(game, repeat_combat["five"])  # 确保使用满5个体力
        # click_in_game(game, repeat_combat["confirm"])
        # time.sleep(2)
        # if ticket == "stone":
        #     pos = detect_button(game, stone_fig)
        # elif ticket == "spare":
        #     pos = detect_button(game, stone_spare_fig)
        # else:
        #     pos = None
        # if pos:
        #     click_in_game(game, pos)
        #     while True:
        #         ok = detect_button(game, OK_fig)
        #         if ok:
        #             click_in_game(game, ok)
        #             break
        #         else:
        #             time.sleep(0.5)
        #     time.sleep(1)
        #     click_in_game(game, repeat_combat["confirm"])
        print(f"Time: {counter}")
        counter += 1
    counter = 1
    repeat_one_time()
    time.sleep(0.5)
    click_in_game(game, repeat_combat["fight"])
    if fight_config is not None:
        fight(game, fight_config, auto_close=True)

    for i in range(times-1):
        while True:
            again = detect_button(game, again_fig)
            if again:
                click_in_game(game, again)
                break
            else:
                click_in_game(game, no_where)  # 屏幕右下角，保证不点到again就行

        repeat_one_time()
        if fight_config is not None:
            fight(game, fight_config, auto_close=True)

def wash_well(game, target_property, wash_rows=[1,2,3,4,6]):
    
    def detect_property():
        region = (resolution[0]//3, resolution[1]//3, resolution[0]//3, resolution[1]//3)

        proper = detect_button(game, properties[target_property], region=region)
        if proper and detect_button(game, properties["+3"], region=region):
            return True
        else:
            return False
        
    def wash_one_well():  # 需要手动点进去再点出来
        repeat_count = 1
        while True:
            if detect_property():
                break
            else:
                click_in_game(game, wash_well_config["reget"])
                time.sleep(0.5)
                repeat_count += 1
        print(f"wash {repeat_count} times")

    if not wash_rows:  # 空列表可以只洗一个孔
        wash_one_well()
    else:  # 指定洗哪些排
        position_x, position_y = wash_well_config["first"]
        for y in wash_rows:
            dy = y-1
            for dx in range(3):
                time.sleep(1)
                click_in_game(game, (position_x+dx*wash_well_config["dx"], position_y+dy*wash_well_config["dy"]))
                time.sleep(1)
                if detect_property():
                    print("wash 0 times")
                    click_in_game(game, wash_well_config["reget"])  # 和取消同一个位置
                else:
                    click_in_game(game, wash_well_config["confirm"])
                    time.sleep(0.5)
                    wash_one_well()
                    click_in_game(game, wash_well_config["confirm"])

def card_game(game, times):
    for i in range(times):
        start_time = time.time()
        # 游戏每次会回到上次进入战斗的界面，认为一定能找到31C战斗
        eazy_31C_position =  detect_button(game, eazy_31C_fig)
        click_in_game(game, eazy_31C_position)
        time.sleep(1)
        # 点击开始挑战
        click_in_game(game, start_cardgame_position)
        # 随便等一会自动打牌
        print(f"time: {i+1} start, waiting for auto")
        time.sleep(120)
        # 检测是否结束战斗，结束则跳出
        while not detect_button(game, end_cardgame_fig):
            time.sleep(5)
            if time.time() - start_time > MAX_TIME:
                print("20min内没结束31C战斗，自动退出")
                return
        print(f"time: {i+1} end game")
        # 检测是否回到主页面
        while not detect_button(game, home_cardgame_fig):
            click_in_game(game, no_where)  # 屏幕右下角，保证不点到战斗就行
            time.sleep(1)
            if time.time() - start_time > MAX_TIME:
                print("20min内没回到主界面，自动退出")
                return
        print(f"time: {i+1} end, use about {(time.time() - start_time)//60} min")
        
def HighScoreEmblem(game, fight_config):
    fight(game, fight_config, need_switch=True)
    time.sleep(5)
    detect_and_click_button(game, kaishi_fig, warning="no detection of button 开始.", click_blank=True)
    detect_and_click_button(game, OK_fig)
    detect_and_click_button(game, tiaozhan_fig, warning="no detection of button 挑战.")

def StartFollowUp(game, fight_config_withoutOD, targetOD, max_time=50):
    try_time = 0
    for i in range(max_time):
        try_time += 1
        print(f"trying time {try_time}")
        # 非后置OD战斗部分结束
        fight(game, fight_config_withoutOD)
        time.sleep(0.5)
        # 开OD
        while True:
            pos = detect_button(game, od_figs_big[0])
            if pos:
                time.sleep(0.1)
                # 点到目标OD结束凹追击，没有目标OD则开1OD返回重开
                if not detect_and_click_button(game, od_figs_big[targetOD-1], max_time=2, warning="", click_blank=False, delta_time=0.25, region=None, raise_error=False):
                    time.sleep(0.5)
                    detect_and_click_button(game, od_figs_big[0])
                    time.sleep(0.5)
                    detect_and_click_button(game, back_fig)
                    time.sleep(0.5)
                    detect_and_click_button(game, retry_fig)
                    time.sleep(0.5)
                    detect_and_click_button(game, OK_fig)
                    break
                else:
                    return try_time
            else:
                time.sleep(0.1)
                click_in_game(game, OD)

if __name__ == "__main__":
    # position_monitor()

    game = find_window()
    # fight_config = parse_hbrf_file('hbrf/OD3.hbrf')
    # print(StartFollowUp(game, fight_config, 3), "times total")
    repeat_fight(game, fight_config=None, times=16, ticket="stone")  # stone, spare, ticket

    # wash_well(game, "灵巧", wash_rows=[2])

    # card_game(game, 1)

    # HighScoreEmblem(game, fight_config)
