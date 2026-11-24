from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

@lru_cache(maxsize=None)
def load_template(path):
    # 由Python读取路径，避免Windows下OpenCV无法打开含中文的文件名
    data = Path(path).read_bytes()
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None:
        raise ValueError(f"无法解码模板: {path}")

    return image
