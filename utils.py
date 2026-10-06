import time
import cv2
import numpy as np
from config.config import no_where
from window_operation import click_in_game, drag_in_game, find_window, capture_window

# 需要特殊处理image通道时可以调用这个，不需特殊处理则直接使用detect_button即可
def match_template(template, image, offset:tuple=(0,0), threshold=0.8):
    """
    返回template在截图image中的匹配结果，未找到返回None，找到返回中点的相对坐标
    """
    # 检查图片大小
    if template.shape[0] > image.shape[0] or template.shape[1] > image.shape[1]:
        raise ValueError("template is larger than screenshot region")
    
    # 模板匹配
    res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)

    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    # 未匹配成功
    if max_val < threshold:
        return None

    # 匹配成功
    # 计算模板宽高
    h, w = template.shape[:2]

    # 返回模板中心点相对坐标
    center_x = offset[0] + max_loc[0] + w // 2
    center_y = offset[1] + max_loc[1] + h // 2

    return (center_x, center_y)  # 返回游戏内匹配图像中点的相对坐标

def detect_button(game, template, region:tuple=(0,0,0,0), threshold=0.8):
    """
    先截屏再匹配template在游戏中的位置，未找到返回None，找到返回中点的相对坐标
    """
    # 不单独传入特异通道比对，需要进行截屏
    screenshot = capture_window(game, region=region)

    offset = region[:2]

    return match_template(template, screenshot, offset, threshold)

def wait_until(condition, timeout=60, interval=0.2, warning="", raise_error=True):
    """
    反复调用 condition()，直到返回 truthy 值。
    成功时返回 condition() 的返回值；超时返回 None 或抛异常。
    """
    start_time = time.monotonic()

    while True:
        result = condition()

        if result:
            return result

        if time.monotonic() - start_time > timeout:
            if raise_error:
                raise TimeoutError(f"{timeout}s内等待失败: {warning}")
            return None

        time.sleep(interval)

def wait_and_click(game, template, timeout=5*60, interval=0.2,
                   region=(0,0,0,0), threshold=0.8,
                   warning="", raise_error=True,
                   click_blank=False, click_wait_time=0):
    """ 
    检测目标图片并点击该按钮
    可设置超时检测时常、报错语句、等待是是否点击空白处、检测间隔时间、检测区域
    """
    def condition():
        pos = detect_button(
            game,
            template,
            region=region,
            threshold=threshold
        )

        if pos:
            time.sleep(click_wait_time)
            click_in_game(game, pos)
            return pos

        if click_blank:
            click_in_game(game, no_where)

        return None

    return wait_until(
        condition,
        timeout=timeout,
        interval=interval,
        warning=warning,
        raise_error=raise_error
    )

def wait_until_any_template(game, templates:dict, timeout=5*60, interval=0.2,
                            region=(0,0,0,0), threshold=0.8,
                            warning="", raise_error=True):

    offset = region[:2]

    def condition():
        screenshot = capture_window(game, region)

        for name, template in templates.items():
            pos = match_template(
                template,
                screenshot,
                offset=offset,
                threshold=threshold
            )

            if pos:
                return name, pos

        return None

    return wait_until(
        condition,
        timeout=timeout,
        interval=interval,
        warning=warning,
        raise_error=raise_error
    )