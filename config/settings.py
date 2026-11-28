import ctypes
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from ctypes import wintypes
from paths import ROOT_DIR

TIPS_STYLE = ('QPushButton{background:#FF3F55;color:white;}'
              'QPushButton:hover{background:#D92439;color:white;}')

CONFIG_PATH = ROOT_DIR / 'config' / 'configs.json'
MIN_CLICK_INTERVAL = 0.5
MAX_CLICK_INTERVAL = 5.0
DEFAULT_CONFIG = {
    'window_title': 'HeavenBurnsRed',
    'auto_restart_admin': False,
    'click_interval': 0.8,
    'tips_seen': {'editor': False, 'simulation': False},
}

def read_config():
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}

    config = {**DEFAULT_CONFIG, **saved}
    title = config['window_title']
    config['window_title'] = title.strip() if isinstance(title, str) and title.strip() else DEFAULT_CONFIG['window_title']
    if type(config['auto_restart_admin']) is not bool:
        config['auto_restart_admin'] = DEFAULT_CONFIG['auto_restart_admin']
    interval = config['click_interval']
    if type(interval) not in (int, float) or interval != interval:
        config['click_interval'] = DEFAULT_CONFIG['click_interval']
    else:
        config['click_interval'] = round(min(MAX_CLICK_INTERVAL, max(MIN_CLICK_INTERVAL, interval)), 2)
    seen = config['tips_seen']
    if not isinstance(seen, dict):
        seen = {}
    config['tips_seen'] = {**seen, **{page: seen.get(page) is True for page in DEFAULT_CONFIG['tips_seen']}}
    return config

def write_config(config, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file = NamedTemporaryFile(dir=path.parent, encoding='utf-8', mode='w', delete=False)
    temporary = Path(file.name)
    try:
        with file:
            json.dump(config, file, ensure_ascii=False, indent=2)
            file.write('\n')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

def update_config(**changes):
    if 'click_interval' in changes:
        changes['click_interval'] = round(min(MAX_CLICK_INTERVAL, max(MIN_CLICK_INTERVAL, changes['click_interval'])), 2)
    config = read_config()
    config.update(changes)
    write_config(config, CONFIG_PATH)

def tips_seen(page):
    return read_config()['tips_seen'][page]

def mark_tips_seen(page):
    config = read_config()
    config['tips_seen'][page] = True
    write_config(config, CONFIG_PATH)

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
