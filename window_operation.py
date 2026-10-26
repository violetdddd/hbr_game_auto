import pygetwindow as gw
import pyautogui
import time
import cv2
import numpy as np
from anti import human_position, human_time

def find_window(title = "HeavenBurnsRed"):
    # 1. 找到游戏窗口
    game_title = title
    windows = gw.getWindowsWithTitle(game_title)

    if not windows:
        raise Exception(f"找不到窗口: {game_title}")
    
    # 激活窗口
    windows[0].activate()
    time.sleep(0.5)  # 等窗口置顶

    return windows[0]  # 取第一个匹配窗口

# 2. 定义函数：点击窗口内某个坐标（相对左上角）
def click_in_game(game, position, jitter = 10, sleep=True):
    x, y = position

    # 获取窗口左上角位置
    win_left, win_top = game.left, game.top

    # 转换成全局坐标
    abs_x, abs_y = win_left + x, win_top + y
    abs_x, abs_y = human_position(abs_x, abs_y, jitter)

    # 先经过一定延迟再点击
    if sleep:
        time.sleep(human_time())
    pyautogui.click(abs_x, abs_y)

def drag_in_game(game, trajectory, duration=0.3):
    x1, y1 = trajectory[0]
    x2, y2 = trajectory[1]
    win_left, win_top = game.left, game.top

    abs_x1, abs_y1 = human_position(win_left + x1, win_top + y1)
    abs_x2, abs_y2 = human_position(win_left + x2, win_top + y2)

    time.sleep(human_time())

    pyautogui.moveTo(abs_x1, abs_y1)
    pyautogui.dragTo(abs_x2, abs_y2, duration=human_time(duration, 0.1))

    time.sleep(human_time(1))

def position_monitor():
    print("请移动鼠标到目标位置，按 Ctrl+C 结束...")
    try:
        while True:
            x, y = pyautogui.position()
            print(f"当前坐标: ({x}, {y})", end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n坐标记录结束！")

def capture_window(game, region:tuple=(0,0,0,0)):  # 要求传相对左上角的坐标（包括标题栏边框等）x,y,w,h

    win_x, win_y, win_w, win_h = game.left, game.top, game.width, game.height

    region_x, region_y, region_w, region_h = region

    # 默认的0，0，0，0是截游戏全屏
    if region == (0,0,0,0):
        region_w, region_h = win_w, win_h

    # 截图region的绝对坐标
    region = (win_x+region_x, win_y+region_y, region_w, region_h)

    screenshot = pyautogui.screenshot(region=region)
    screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    return screenshot