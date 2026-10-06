import cv2
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
TEMPLATE_DIR = ASSETS_DIR / "templates"

# 配置参数
resolution = (1920, 1260)
skip = (1700, 220)
change = (100, 120)
ok = (1200, 950)
member = [(160, 1070), (450, 1070), (740, 1070), (1010, 1070), (1250, 1070), (1500, 1070)]
next_turn = (1760, 1070)
skill_123 = [0, (1200, 380), (1200, 560), (1200, 750)]
skill_4_drug = [(1100, 800), (1100, 200)]
OD = (1770, 150) 
switch_skills = [(1800, 380), (1770, 560), (1740, 740)]
repeat_combat = {"activity":(1770,1020), "gem":(1520,920), "orb":(1300,1030), 
                 "five":(1300,750), "stone":(1350,1050), "ticket":(730,560),
                 "confirm":(1200,980), "ok":(960, 950), "fight":(960,1111), 
                 "detail":(1515, 915), "team19":(1570,195)}
wash_well_config = {"reget":(700,980), "first":(1375,395), "confirm":(1200,980), 
                    "dx":110, "dy":140}
no_where = (1850, 1200)

# 图片匹配模板
start_action_fig = cv2.imread(".//templates//start_action.png", cv2.IMREAD_COLOR)
skip_fig = cv2.imread(".//templates//skip.png", cv2.IMREAD_COLOR)
od_fig_1 = cv2.imread(".//templates//od_1.png", cv2.IMREAD_COLOR)
od_fig_2 = cv2.imread(".//templates//od_2.png", cv2.IMREAD_COLOR)
od_fig_3 = cv2.imread(".//templates//od_3.png", cv2.IMREAD_COLOR)
od_fig_1_big = cv2.imread(".//templates//od_1_big.png", cv2.IMREAD_COLOR)
od_fig_2_big = cv2.imread(".//templates//od_2_big.png", cv2.IMREAD_COLOR)
od_fig_3_big = cv2.imread(".//templates//od_3_big.png", cv2.IMREAD_COLOR)
od_figs = [od_fig_1, od_fig_2, od_fig_3]
od_figs_big = [od_fig_1_big, od_fig_2_big, od_fig_3_big]
stone_fig = cv2.imread(".//templates//stone.png", cv2.IMREAD_COLOR)
OK_fig = cv2.imread(".//templates//OK.png", cv2.IMREAD_COLOR)
again_fig = cv2.imread(".//templates//again.png", cv2.IMREAD_COLOR)

zhihui = cv2.imread(".//templates//zhihui.png", cv2.IMREAD_COLOR)
liliang = cv2.imread(".//templates//liliang.png", cv2.IMREAD_COLOR)
lingqiao = cv2.imread(".//templates//lingqiao.png", cv2.IMREAD_COLOR)
tili = cv2.imread(".//templates//tili.png", cv2.IMREAD_COLOR)
yunqi = cv2.imread(".//templates//yunqi.png", cv2.IMREAD_COLOR)
plus_3 = cv2.imread(".//templates//3.png", cv2.IMREAD_COLOR)
properties = {"+3":plus_3, "智慧":zhihui, "力量":liliang, "灵巧":lingqiao, "运气":yunqi, "体力":tili,}

end_cardgame_fig = cv2.imread(".//templates//end_cardgame.png", cv2.IMREAD_COLOR)
eazy_31C_fig = cv2.imread(".//templates//eazy_31C.png", cv2.IMREAD_COLOR)
home_cardgame_fig = cv2.imread(".//templates//home_cardgame.png", cv2.IMREAD_COLOR)
start_cardgame_position = (1250,1000)

hbr_home_fight = cv2.imread(".//templates//hrb_fight.png", cv2.IMREAD_COLOR)
hbr_save_electric = cv2.imread(".//templates//end_electric.png", cv2.IMREAD_COLOR)
diamond_lens_button = cv2.imread(".//templates//diamond_lens.png", cv2.IMREAD_COLOR)
back_to_home_fig = cv2.imread(".//templates//back_to_home.png", cv2.IMREAD_COLOR)
stop_repeat_fight_fig = cv2.imread(".//templates//stop_repeat_fight.png", cv2.IMREAD_COLOR)
team_blue_fig = cv2.imread(".//templates//team_blue.png", cv2.IMREAD_COLOR)
menu_fig = cv2.imread(".//templates//menu.png", cv2.IMREAD_COLOR)
end_hbr_game_fig = cv2.imread(".//templates//end_hbr_game.png", cv2.IMREAD_COLOR)
auto_on_fig = cv2.imread(".//templates//auto_on.png", cv2.IMREAD_COLOR)
auto_off_fig = cv2.imread(".//templates//auto_off.png", cv2.IMREAD_COLOR)
mission_fig = cv2.imread(".//templates//mission.png", cv2.IMREAD_COLOR)
daily_mission_fig = cv2.imread(".//templates//daily_mission.png", cv2.IMREAD_COLOR)
get_rewards_fig = cv2.imread(".//templates//get_rewards.png", cv2.IMREAD_COLOR)
time_exercise_fig = cv2.imread(".//templates//time_exercise.png", cv2.IMREAD_COLOR)
save_electric_fig = cv2.imread(".//templates//save_electric.png", cv2.IMREAD_COLOR)
OK_electric_fig = cv2.imread(".//templates//electric_ok.png", cv2.IMREAD_COLOR)
stone_spare_fig = cv2.imread(".//templates//stone_spare.png", cv2.IMREAD_COLOR)
stone_tili_fig = cv2.imread(".//templates//stone_tili.png", cv2.IMREAD_COLOR)
ticket_orb_fig = cv2.imread(".//templates//ticket_orb.png", cv2.IMREAD_COLOR)
use_most_fig = cv2.imread(".//templates//use_most.png", cv2.IMREAD_COLOR)

kelian_change_fig = cv2.imread(".//templates//kelian_change.png", cv2.IMREAD_COLOR)

kaishi_fig = cv2.imread(".//templates//kaishi.png", cv2.IMREAD_COLOR)
tiaozhan_fig = cv2.imread(".//templates//tiaozhan.png", cv2.IMREAD_COLOR)

back_fig = cv2.imread(".//templates//back.png", cv2.IMREAD_COLOR)
retry_fig = cv2.imread(".//templates//retry.png", cv2.IMREAD_COLOR)

Siling_GuiShenHua_fig = cv2.imread(".//templates//GuiShenHua.png", cv2.IMREAD_COLOR)