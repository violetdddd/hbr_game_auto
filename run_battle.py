import sys
from hbrf import model as m
from window_operation import find_window
from config import settings
import logging


MAX_RETRY = 100

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
    need_ao = any(isinstance(action, m.CheckOD) for action in script.actions)

    if repeated == '1':
        if need_ao:
            raise ValueError("重复刷取光球不支持凹追击检查")
        from repetition import repeat_fight
        repeat_fight(game, script, int(count), ticket=ticket, auto_close=(auto_close == '1'))
    else:
        from fight import fight
        need_auto_close = auto_close == '1'
        if need_ao:
            from fight import restart_battle
            for attempt in range(1, MAX_RETRY + 1):
                # 成功就return结束即可
                try:
                    fight(game, script, auto_close=(attempt == 1 and need_auto_close))
                    return True
                # 失败则捕捉异常重新开始
                except m.ODRetryRequired as e:
                    if attempt == MAX_RETRY:
                        raise RuntimeError(
                            f"凹追击失败，已达到最大尝试次数 {MAX_RETRY}"
                        ) from e
                    restart_battle(game, attempt, e)
        else:
            fight(game, script, auto_close=need_auto_close)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n用户中断战斗', flush=True)
        sys.exit(130)