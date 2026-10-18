"""独立运行技术模拟战（31C）重复打牌，供 GUI Worker 启动。"""
import logging
import sys
from window_operation import find_window
from config import settings
from repetition import card_game


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S', stream=sys.stdout, force=True)
    count, title = sys.argv[1:]
    game = find_window(title)
    settings.set_resolution(settings.detect_resolution(game))
    logging.getLogger('hbr.card').info('开始重复打牌，共 %s 次', count)
    card_game(game, int(count))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('用户中断技术模拟战', flush=True)
        sys.exit(130)
