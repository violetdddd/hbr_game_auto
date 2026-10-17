import sys
from hbrf import model as m
from window_operation import find_window
from config import settings
import logging


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout,
        force=True
    )

    path, repeated, count, ticket, auto_close, title = sys.argv[1:]
    script = m.load_hbrf(path)
    game = find_window(title)
    settings.set_resolution(settings.detect_resolution(game))

    if repeated == '1':
        from repetition import repeat_fight
        repeat_fight(game, script, int(count), ticket=ticket, auto_close=(auto_close == '1'))
    else:
        from fight import fight
        fight(game, script, auto_close=(auto_close == '1'))

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n用户中断战斗', flush=True)
        sys.exit(130)