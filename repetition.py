from window_operation import click_in_game, find_window
from config.settings import resolution
from config import positions as pos
from config import templates as tpl
from vision.images import load_template
from fight import fight
from utils import wait_and_click, detect_button, wait_until
import time

# 定义一局最多等待20min
MAX_TIME = 20*60

# 用于反复多次刷体力
def repeat_fight(game, fight_config, times, ticket="stone"):
    if times < 1:
        raise ValueError("times必须至少为1")
    if ticket not in ("stone", "ticket", "spare"):
        raise Exception("入场券格式不正确，请填写stone, ticket或spare")
    """从使用体力位置开始循环"""
    def repeat_one_time():
        nonlocal counter
        time.sleep(1)
        if ticket == "ticket":  # 后续其他票要更新支持
            wait_and_click(game, load_template(tpl.ticket_orb_fig))
        elif ticket == "stone":
            wait_and_click(game, load_template(tpl.stone_tili_fig))
        elif ticket == "spare":
            wait_and_click(game, load_template(tpl.stone_spare_fig))
        wait_and_click(game, load_template(tpl.OK_fig))
        wait_and_click(game, load_template(tpl.use_most_fig))
        wait_and_click(game, load_template(tpl.OK_fig))

        print(f"Time: {counter}")
        counter += 1

    counter = 1
    repeat_one_time()
    time.sleep(0.5)
    click_in_game(game, pos.repeat_combat["fight"])
    if fight_config is not None:
        fight(game, fight_config, auto_close=True)

    for i in range(times-1):
        wait_and_click(game, load_template(tpl.again_fig), 
                       click_blank=True, timeout=MAX_TIME, 
                       warning="重复战斗中未匹配到重新开始按钮")

        repeat_one_time()
        if fight_config is not None:
            fight(game, fight_config, auto_close=True)

# 改版后游戏内已经支持自动洗孔，本函数可暂时弃用
def wash_well(game, target_property, wash_rows=(1,2,3,4,6)):
    
    def detect_property():
        region = (resolution[0]//3, resolution[1]//3, resolution[0]//3, resolution[1]//3)

        proper = detect_button(game, load_template(tpl.properties[target_property]), region=region)
        if proper and detect_button(game, load_template(tpl.properties["+3"]), region=region):
            return True
        else:
            return False
        
    def wash_one_well():  # 此函数直接调用需要手动点进去再点出来
        repeat_count = 1
        while True:
            if detect_property():
                break
            else:
                click_in_game(game, pos.wash_well_config["reget"])
                time.sleep(0.5)
                repeat_count += 1
        print(f"wash {repeat_count} times")

    if not wash_rows:  # 空列表可以只洗一个孔
        wash_one_well()
    else:  # 指定洗哪些排
        position_x, position_y = pos.wash_well_config["first"]
        for y in wash_rows:
            dy = y-1
            for dx in range(3):
                time.sleep(1)
                click_in_game(game, (position_x+dx*pos.wash_well_config["dx"], position_y+dy*pos.wash_well_config["dy"]))
                time.sleep(1)
                if detect_property():
                    print("wash 0 times")
                    click_in_game(game, pos.wash_well_config["reget"])  # 和取消同一个位置
                else:
                    click_in_game(game, pos.wash_well_config["confirm"])
                    time.sleep(0.5)
                    wash_one_well()
                    click_in_game(game, pos.wash_well_config["confirm"])

def card_game(game, times):
    def home_condition():
        pt = detect_button(game, load_template(tpl.home_cardgame_fig))
        if pt:
            return pt

        click_in_game(game, pos.no_where)
        return None
    
    if times < 1:
        raise ValueError("times必须至少为1")
    for i in range(times):
        start_time = time.time()
        # 游戏每次会回到上次进入战斗的界面，认为一定能找到31C战斗
        wait_and_click(
            game,
            load_template(tpl.eazy_31C_fig),
            warning="未检测到31C战斗入口"
        )
        time.sleep(1)
        # 点击开始挑战
        click_in_game(game, pos.start_cardgame_position)
        # 随便等一会自动打牌
        print(f"time: {i+1} start, waiting for auto")
        time.sleep(120)

        # 检测是否结束战斗，超20min没结束则报错退出
        wait_until(lambda: detect_button(game, load_template(tpl.end_cardgame_fig)),
                   timeout=MAX_TIME,
                   interval=5,
                   warning="没成功结束31C战斗")
        print(f"time: {i+1} end game")

        # 等待奖励领取完毕并检测是否回到主页面
        wait_until(home_condition,
                   timeout=MAX_TIME,
                   interval=1,
                   warning="战斗结束后没回到主界面")
        print(f"time: {i+1} end, use about {(time.time() - start_time)//60} min")

# 已经刷完徽章，暂时不需要这个函数
def high_score_emblem(game, fight_config):
    fight(game, fight_config)
    time.sleep(5)
    wait_and_click(game, load_template(tpl.kaishi_fig), warning="no detection of button 开始.", click_blank=True)
    wait_and_click(game, load_template(tpl.OK_fig))
    wait_and_click(game, load_template(tpl.tiaozhan_fig), warning="no detection of button 挑战.")

# 刷开局追击使用
def start_follow_up(game, fight_config_withoutOD, targetOD, max_time=50):
    def OD_condition():
        pt = detect_button(game, load_template(tpl.od_figs_big[0]))
        if pt:
            return pt
        else:
            click_in_game(game, pos.OD, sleep=False)

    try_time = 0
    for i in range(max_time):
        try_time += 1
        print(f"trying time {try_time}")
        # 非后置OD战斗部分结束
        fight(game, fight_config_withoutOD)
        time.sleep(0.5)
        # 开OD
        wait_until(OD_condition,
                   interval=0.1, 
                   warning="未检测到OD按钮")
        time.sleep(0.1)
        # 点到目标OD结束凹追击，没有目标OD则开1OD返回重开
        if not wait_and_click(game, load_template(tpl.od_figs_big[targetOD-1]), timeout=2, interval=0.25, raise_error=False):
            time.sleep(0.5)
            wait_and_click(game, load_template(tpl.od_figs_big[0]))
            time.sleep(0.5)
            wait_and_click(game, load_template(tpl.back_fig))
            time.sleep(0.5)
            wait_and_click(game, load_template(tpl.retry_fig))
            time.sleep(0.5)
            wait_and_click(game, load_template(tpl.OK_fig))
            continue
        else:
            return try_time

if __name__ == "__main__":
    # position_monitor()

    game = find_window()
    # fight_config = parse_hbrf_file('scripts/OD3.hbrf')
    # print(start_follow_up(game, fight_config, 3), "times total")
    repeat_fight(game, fight_config=None, times=6, ticket="ticket")  # stone, spare, ticket

    # wash_well(game, "灵巧", wash_rows=(2))

    # card_game(game, 1)

    # high_score_emblem(game, fight_config)
