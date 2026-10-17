# from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent
# ASSETS_DIR = BASE_DIR / "assets"
# TEMPLATE_DIR = ASSETS_DIR / "templates"
from config import settings


def scale_position(position):

    sx, sy = settings.template_scale()

    if isinstance(position, tuple) and len(position) == 2:
        return (round(position[0] * sx), round(position[1] * sy))

    if isinstance(position, list):
        return [scale_position(p) for p in position]

    return position

# 以resolution = (1920, 1200)为标准的相对位置坐标
_member = [(160, 1070), (450, 1070), (740, 1070), (1010, 1070), (1250, 1070), (1500, 1070)]
# 三个星癌体的左中右，两个星癌体是中右
_monster = [(1070, 550), (1314, 590), (1650, 600)]
_next_turn = (1760, 1070)
# 此处可以放平A的坐标
_skill_123 = [(250, 760), (1200, 380), (1200, 560), (1200, 750)]
_skill_4_drug = [(1100, 800), (1100, 200)]
_OD = (1770, 150) 
_switch_skills = [(1840, 410), (1810, 600), (1770, 790)]

_no_where = (1850, 1200)

_start_cardgame_position = (1250,1000)

_positions = {
    "member": _member,
    "monster": _monster,
    "next_turn": _next_turn,
    "skill_123": _skill_123,
    "skill_4_drug": _skill_4_drug,
    "OD": _OD,
    "switch_skills": _switch_skills,
    "no_where": _no_where,
    "start_cardgame_position": _start_cardgame_position
}

# pos.something 引用的时候会调用这个方法
def __getattr__(name):
    if name in _positions:
        return scale_position(_positions[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")