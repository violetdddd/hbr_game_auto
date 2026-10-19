from pathlib import Path
import sys

# 打包后资源在 PyInstaller 内部目录；源码运行时在项目根目录
ROOT_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
ASSETS_DIR = ROOT_DIR / 'assets'
TEMPLATE_DIR = ASSETS_DIR / 'templates'
# scripts 供用户保存和选择脚本，放在 exe 所在目录而不是只读资源目录
SCRIPTS_DIR = (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
               else ROOT_DIR) / 'scripts'
