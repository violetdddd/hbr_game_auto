import ctypes
from ctypes import wintypes

def detect_resolution(game):
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)

    user32.GetClientRect(game._hWnd, ctypes.byref(rect))
    user32.ClientToScreen(game._hWnd, ctypes.byref(origin))

    return (rect.right - rect.left, rect.bottom - rect.top)

# 配置参数
RESOLUTIONS = {
    (1680, 1050): {'x_scale': 0.875, 'y_scale': 0.875},  # 8:5
    (1920, 1200): {'x_scale': 1.0, 'y_scale': 1.0},  # 8:5
    (2560, 1600): {'x_scale': 1.333, 'y_scale': 1.333},  # 8:5
    (1920, 1080): {'x_scale': 1.0, 'y_scale': 0.9},  # 16:9，关闭自动等可能有问题
    (2048, 1152): {'x_scale': 1.067, 'y_scale': 0.96},  # 16:9
    (2160, 1215): {'x_scale': 1.125, 'y_scale': 1.0},  # 16:9
    (2560, 1440): {'x_scale': 1.333, 'y_scale': 1.2},  # 16:9
}

current_resolution = (1920, 1200)

def set_resolution(resolution):
    global current_resolution
    if resolution == (0,0):
        raise ValueError(f'游戏当前可能处于最小化状态，无法正确识别分辨率')
    elif resolution not in RESOLUTIONS:
        raise ValueError(f'不支持的分辨率：{resolution}')
    current_resolution = resolution

def template_scale():
    return RESOLUTIONS[current_resolution]['x_scale'], RESOLUTIONS[current_resolution]['y_scale']
