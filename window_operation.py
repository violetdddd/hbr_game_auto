import pygetwindow as gw
import pyautogui
import time
import cv2
import numpy as np
from anti import human_position, human_time
from config import positions as pos
from config import settings

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
def click_in_game(game, position, jitter = 10, sleep=True, sleep_time=0.5):
    x, y = position

    # 先经过一定延迟再点击
    if sleep:
        time.sleep(human_time(sleep_time))

    while True:
        if game.isActive:
            # 等窗口重新激活后再读取坐标，避免使用切回前的位置
            abs_x, abs_y = human_position(game.left + x, game.top + y, jitter)
            if game.isActive:
                pyautogui.click(abs_x, abs_y)
                return
        time.sleep(0.2)

def click_circle_in_game(game, position, sleep_time=0.3):
    center_x, center_y = position
    x_shift = (0, 0.7, 1, 0.7, 0, -0.7, -1, -0.7)
    y_shift = (-1, -0.7, 0, 0.7, 1, 0.7, 0, -0.7)
    click_in_game(game, (center_x, center_y), sleep_time=sleep_time)
    for i in range(8):
        x, y = center_x + int(x_shift[i] * pos.radius), center_y + int(y_shift[i] * pos.radius)
        click_in_game(game, (x, y), sleep_time=sleep_time)

def smooth_drag_to(abs_x1, abs_y1, abs_x2, abs_y2, duration, sample_freq=120):
    move_duration = human_time(duration, 0.05)
    steps = max(10, round(move_duration * sample_freq))
    started = time.perf_counter()

    for step in range(1, steps + 1):
        progress = step / steps
        deadline = started + move_duration * progress
        time.sleep(max(0, deadline - time.perf_counter()))
        x = round(abs_x1 + (abs_x2 - abs_x1) * progress)
        y = round(abs_y1 + (abs_y2 - abs_y1) * progress)
        pyautogui.moveTo(x, y, _pause=False)

def drag_in_game(game, trajectory, duration=0.4):
    x1, y1 = trajectory[0]
    x2, y2 = trajectory[1]
    time.sleep(human_time())

    while True:
        if game.isActive:
            win_left, win_top = game.left, game.top
            abs_x1, abs_y1 = human_position(win_left + x1, win_top + y1, only_x=True)
            abs_x2, abs_y2 = human_position(win_left + x2, win_top + y2, only_x=True)
            # 对16:9的y轴进行微调修正
            resolution = settings.current_resolution
            if resolution not in ((1680, 1050), (1920, 1200), (2560, 1600)):
                abs_y1 *= 1.08
                abs_y2 *= 1.04
            if game.isActive:
                pyautogui.moveTo(abs_x1, abs_y1)
                if game.isActive:
                    pyautogui.mouseDown(button="left")
                    time.sleep(0.1)
                    try:
                        smooth_drag_to(abs_x1, abs_y1, abs_x2, abs_y2, duration)
                        time.sleep(1)
                    finally:
                        pyautogui.mouseUp(button="left")
                        time.sleep(0.5)
                    return
        time.sleep(0.2)

def fast_drag_in_game(game, trajectory, duration=0.15):
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
                    pyautogui.mouseDown(button="left")
                    time.sleep(0.1)
                    if game.isActive:
                        smooth_drag_to(abs_x1, abs_y1, abs_x2, abs_y2, duration)
                        pyautogui.mouseUp(button="left")
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
