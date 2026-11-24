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

    # 先经过一定延迟再点击
    if sleep:
        time.sleep(human_time())

    while True:
        if game.isActive:
            # 等窗口重新激活后再读取坐标，避免使用切回前的位置
            abs_x, abs_y = human_position(game.left + x, game.top + y, jitter)
            if game.isActive:
                pyautogui.click(abs_x, abs_y)
                return
        time.sleep(0.2)

def drag_in_game(game, trajectory, duration=0.3):
    x1, y1 = trajectory[0]
    x2, y2 = trajectory[1]
    time.sleep(human_time())

    while True:
        if game.isActive:
            win_left, win_top = game.left, game.top
            abs_x1, abs_y1 = human_position(win_left + x1, win_top + y1)
            abs_x2, abs_y2 = human_position(win_left + x2, win_top + y2)
            if game.isActive:
                pyautogui.moveTo(abs_x1, abs_y1)
                if game.isActive:
                    pyautogui.dragTo(abs_x2, abs_y2, duration=human_time(duration, 0.1))
                    time.sleep(human_time(1))
                    return
        time.sleep(0.2)

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
    region_x, region_y, region_w, region_h = region
    while True:
        if game.isActive:
            win_x, win_y = game.left, game.top
            # 默认的0，0，0，0是截游戏全屏
            width, height = (game.width, game.height) if region == (0,0,0,0) else (region_w, region_h)
            absolute_region = (win_x + region_x, win_y + region_y, width, height)
            if game.isActive:
                screenshot = pyautogui.screenshot(region=absolute_region)
                # 截图过程中失焦时丢弃这一帧，避免后续误匹配
                if game.isActive:
                    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        time.sleep(0.2)
