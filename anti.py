import random

def human_time(base=0.5, var=0.3):
    """随机延时：base±var"""
    t = base + random.uniform(-var, var)
    return max(0.01, t)  # 避免负值

def human_position(x, y, jitter=10):
    """在目标位置周围±jitter像素范围内点击"""
    offset_x = x + random.randint(-jitter, jitter)
    offset_y = y + random.randint(-jitter, jitter)
    return (offset_x, offset_y)
