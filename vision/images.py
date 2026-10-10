import cv2
from functools import lru_cache

@lru_cache(maxsize=None)
def load_template(path):
    path = str(path)

    image = cv2.imread(path, cv2.IMREAD_COLOR)

    if image is None:
        raise FileNotFoundError(f"无法找到模板: {path}")

    return image