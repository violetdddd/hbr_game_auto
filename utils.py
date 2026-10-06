import time
import cv2
import numpy as np
from config import no_where
from mouse_simulation import click_in_game, drag_in_game, find_window, capture_window
# from win_api_post import click_in_game, drag_in_game, find_window, capture_window

def detect_button(game, template, channel=None, region=None):

    # 不单独传入特异通道比对，则需要进行截屏
    if channel is None:
        screenshot = capture_window(game, region=region)

    # 单独传入特异通道比对，则截屏设置为channel
    else:
        screenshot = channel  # 不需要region参数

    # 模板匹配
    res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)

    loc = np.where(res >= 0.8)  # 阈值 0.8

    # 如果检测到至少一个匹配点，返回第一个位置
    if len(loc[0]) > 0:
        pt = (loc[1][0], loc[0][0])  # (x, y)

        # 计算模板宽高
        h, w = template.shape[:2]

        # 返回模板中心点坐标
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2

        return (center_x, center_y)  # 返回游戏内匹配图像中点的相对坐标
    
    return None

def detect_and_click_button(game, template, max_time=5*60, warning="", click_blank=False, delta_time=1, region=None, raise_error=True):
    """ 
    检测目标图片并点击该按钮
    可设置超时检测时常、报错语句、等待是是否点击空白处、检测间隔时间、检测区域
    """
    start_time = time.time()
    while True:
        template_position = detect_button(game, template, region=region)
        if template_position:
            click_in_game(game, template_position)
            return True
        else:
            if time.time() - start_time > max_time:
                if raise_error:
                    raise Exception(f"{max_time}s内未匹配到目标图片："+warning)
                else:
                    return False
            if click_blank:
                click_in_game(game, no_where)
            time.sleep(delta_time)