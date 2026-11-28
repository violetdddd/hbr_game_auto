"""战斗模拟 Tab。仅负责界面、状态快照与手动修正；实际结算由 engine.advance 提供。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QTabWidget, QScrollArea,
    QGroupBox, QStackedWidget, QMessageBox, QFileDialog, QSizePolicy, QFrame,
    QComboBox, QAbstractButton, QInputDialog,
)

from paths import ROOT_DIR, SCRIPTS_DIR
from config import settings
from simulation import DEFAULT_ENEMY_SLOTS
SIMULATION_DIR = ROOT_DIR / 'assets' / 'simulation'
ICON_DIR = ROOT_DIR / 'assets' / 'icons'
KELIAN_DIR = ROOT_DIR / "assets" / "char-images" / "31A" / "Karen_Asakura"


ELEMENTS = [('无', None), ('火', 'fire'), ('冰', 'ice'), ('雷', 'thunder'), ('光', 'light'), ('暗', 'dark')]
FIELD_OPTIONS = [('无', None), ('火场', 'fire'), ('冰场', 'ice'),
                 ('雷场', 'thunder'), ('光场', 'light'), ('暗场', 'dark'), ('稻场', 'rice_field'), ("其他", "others")]
ELEMENT_NAMES = dict((value, label) for label, value in ELEMENTS)
FIELD_NAMES = dict((value, label) for label, value in FIELD_OPTIONS)
TERRITORY_NAMES = {204: "晚夏", 157: "再生"}
BLUE_BUTTON = ('QPushButton{background:#2563eb;color:white;border:1px solid #1d4ed8;'
               'border-radius:7px;padding:3px 9px;font-weight:600}'
               'QPushButton:hover{background:#1d4ed8}'
               'QPushButton:disabled{background:#cbd5e1;border-color:#cbd5e1}')
WHITE_BUTTON = ('QPushButton{padding:2px 5px;min-height:0px;}')
OD_COLORS = {1: '#F8DFEA', 2: '#DDF5F1', 3: '#FAEFC6'}  # 与HBRF编辑器一致
COMPACT = """
QComboBox {
    padding: 2px 4px;
    min-height: 17px;
    border: 1px solid #d6deea;
    border-radius: 5px;
    background: white;
}

QSpinBox, QDoubleSpinBox {
    padding: 1px 1px;
    min-height: 17px;
    border: 1px solid #d6deea;
    border-radius: 5px;
    background: white;
}

/* 扩大上下箭头所在区域 */
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button  {
    width: 15px;
}

/* 鼠标悬停时突出显示 */
QSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {
    background: #dbeafe;
}
"""

class NoWheelComboBox(QComboBox):
    """与原 GUI 一致：滚轮只用于页面滚动，不改变下拉框选项。"""
    def wheelEvent(self, event):
        event.ignore()

# 生成内容为options的下拉框
def combo(options, width=None):
    box = NoWheelComboBox()
    for label, value in options:
        box.addItem(label, value)
    if width is not None:
        box.setFixedWidth(width)
    box.setFixedHeight(22)
    return box

# 可填整数数值，有上下箭头的编辑栏
def spin(low=0, high=99999, value=0, width=None):
    box = QSpinBox(); box.setRange(low, high); box.setValue(value)
    box.setFixedHeight(22)
    if width: box.setFixedWidth(width)
    return box

# 可填小数数值，有上下箭头的编辑栏
def dspin(low=0, high=9999.99, value=0, width=None):
    box = QDoubleSpinBox(); box.setRange(low, high); box.setDecimals(2)
    box.setSingleStep(1); box.setValue(value); box.setFixedHeight(22)
    if width: box.setFixedWidth(width)
    return box

class FullPopupCombo(NoWheelComboBox):
    """技能下拉框本体保持紧凑，但弹出菜单保证完整显示所有技能名。"""
    def showPopup(self):
        view = self.view()
        width = max(self.width(), *(self.fontMetrics().horizontalAdvance(self.itemText(i)) + 40
                                    for i in range(self.count())))
        view.setMinimumWidth(min(width, 650))
        super().showPopup()

# 一般的图标显示
def icon_label(path, size=23, fallback='', reference_size=None):
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    pixmap = QPixmap(str(path))
    width = height = size
    if not pixmap.isNull():
        ratio = label.devicePixelRatioF()
        if reference_size is not None:
            width = round(pixmap.width() * size / reference_size)
            height = round(pixmap.height() * size / reference_size)

        pixmap = pixmap.scaled(
            round(width * ratio), round(height * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        pixmap.setDevicePixelRatio(ratio)

        label.setPixmap(pixmap)
        label.setScaledContents(False)
    else:
        label.setText(fallback)
        label.setToolTip(f'图片不存在：{path}')

    label.setFixedSize(width, height)
    return label

# 清理一整个layout
def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())

class StatusRow(QScrollArea):
    ICON_SIZE = 21
    REFERENCE_SIZE = 59

    def __init__(self):
        super().__init__()
        self.items = []
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(self.ICON_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalScrollBar().setSingleStep(self.ICON_SIZE)
        self.viewport().setStyleSheet('background:white;')
        self.icons = QWidget()
        self.icons.setFixedSize(0, self.ICON_SIZE)
        self.icons.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.row = QHBoxLayout(self.icons)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(0)
        self.setWidget(self.icons)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    def set_statuses(self, items):
        if items == self.items:
            return
        self.items = items
        scroll = self.horizontalScrollBar()
        offset = scroll.value()
        while self.row.count():
            widget = self.row.takeAt(0).widget()
            widget.hide(); widget.deleteLater()
        width, height = 0, self.ICON_SIZE
        for path, _, _ in items:
            icon = self.status_icon(path)
            self.row.addWidget(icon)
            width += icon.width()
            height = max(height, icon.height())
        self.icons.setFixedSize(width, height)
        self.setFixedHeight(height)
        scroll.setValue(offset)

    def status_icon(self, path):
        return icon_label(path, self.ICON_SIZE, '?', self.REFERENCE_SIZE)

    def wheelEvent(self, event):
        # 普通纵向滚轮交给外层页面，横向滚轮或Shift滚轮移动状态栏
        delta = event.pixelDelta().x() or event.angleDelta().x()
        if not delta and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = event.pixelDelta().y() or event.angleDelta().y()
        scroll = self.horizontalScrollBar()
        if delta and scroll.maximum():
            scroll.setValue(scroll.value() - delta)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_details()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def show_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('状态详情')
        dialog.resize(340, 280)
        layout = QVBoxLayout(dialog)
        area = QScrollArea(); area.setWidgetResizable(True)
        content = QWidget()
        details = QGridLayout(content)
        details.setContentsMargins(4, 4, 4, 4)
        details.setHorizontalSpacing(3); details.setVerticalSpacing(0)
        details.setAlignment(Qt.AlignmentFlag.AlignTop)
        details.setColumnStretch(1, 1)
        for i, (path, name, status) in enumerate(self.items):
            duration = status.get('duration_type')
            remaining = status.get('remaining')
            element = status.get('element')
            level = status.get('level')
            if status.get('data') and "mode" in status.get('data'):
                name += f"×{status.get('data').get('mode').get('number')}"
            if element:
                name = ELEMENT_NAMES[element] + name
            if level:
                name += f" Level {level} "
            if duration == 'permanent':
                name += '（永久）'
            elif duration == "during_down":
                name += "（倒下状态）"
            elif duration != 'use_immersion_ex':
                label = {'ally_turn': '我方回合', 'enemy_turn': '敌方回合'}.get(duration, '剩余次数')
                name += f'（{label}：{remaining if remaining is not None else "bug"}）'
            title = QLabel(name)
            title.setTextFormat(Qt.TextFormat.PlainText)
            details.addWidget(self.status_icon(path), i * 2, 0, Qt.AlignmentFlag.AlignCenter)
            details.addWidget(title, i * 2, 1)
            if status.get('source') not in (None, ''):
                source = QLabel(f'来源：{status["source"]}')
                source.setTextFormat(Qt.TextFormat.PlainText)
                source.setWordWrap(True)
                details.addWidget(source, i * 2 + 1, 1)
        if not self.items:
            details.addWidget(QLabel('当前没有状态'), 0, 0, 1, 2)
        area.setWidget(content); layout.addWidget(area)
        close = QPushButton('关闭')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()
        dialog.deleteLater()


class WeaknessDialog(QDialog):
    """所有敌人共享弱点，使用类似技能设置的复选弹窗。"""
    def __init__(self, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle('敌人弱点设置')
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        self.checks = {}
        for label, value in ELEMENTS[1:]:
            check = QCheckBox(label)
            check.setChecked(value in selected)
            self.checks[value] = check
            layout.addWidget(check)
        controls = QHBoxLayout()
        for title, checked in (('全选', True), ('全不选', False)):
            button = QPushButton(title)
            button.clicked.connect(lambda _=False, value=checked:
                                   [c.setChecked(value) for c in self.checks.values()])
            controls.addWidget(button)
        layout.addLayout(controls)
        save = QPushButton('确定')
        save.setStyleSheet(BLUE_BUTTON)
        save.clicked.connect(self.accept)
        layout.addWidget(save)

    def values(self):
        return [key for key, check in self.checks.items() if check.isChecked()]

# 技能选择面板
class SkillSelectionDialog(QDialog):
    def __init__(self, catalog, style, selection, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'技能设置 · {style.localized_title}')
        self.resize(550, 520)
        self.checks = {}
        self.catalog = catalog
        root = QVBoxLayout(self)
        tabs = QTabWidget(); root.addWidget(tabs)
        active = [(name, catalog.skill_data.get(name, {})) for name in catalog.skills_for(style) if name != "指揮行動"]
        passive = self._get_passives(style)
        orb = [(name, catalog.skill_data.get(name, {})) for name in catalog.common_global]
        orb_names = {name for name, _ in orb}
        active = [(name, entry) for name, entry in active if name not in orb_names]
        for category, title, entries in [('active', '主动技能', active),
                                         ('passive', '被动技能', passive),
                                         ('orb', '光球技能', orb)]:
            page = QWidget(); layout = QVBoxLayout(page)
            buttons = QHBoxLayout()
            select_all = QPushButton('全选'); deselect_all = QPushButton('全不选')
            buttons.addWidget(select_all); buttons.addWidget(deselect_all)
            buttons.addStretch(); layout.addLayout(buttons)
            area = QScrollArea(); area.setWidgetResizable(True)
            holder = QWidget(); vertical = QVBoxLayout(holder)
            vertical.setAlignment(Qt.AlignmentFlag.AlignTop)
            group = []
            # 显示技能名（主动技能还有sp消耗），但内部存储simulation_id
            for name, entry in dict(entries).items():
                simulation_id = int(entry['simulation_id'])
                label = (catalog.skill_label(name) if category != 'passive' else
                         entry.get('names', {}).get('zh-CN-CN') or
                         entry.get('names', {}).get('zh-CN') or name)
                check = QCheckBox(label); check.setChecked(simulation_id in selection.get(category, []))
                vertical.addWidget(check); group.append(check)
                self.checks[category, simulation_id] = check
            area.setWidget(holder); layout.addWidget(area)
            select_all.clicked.connect(lambda _=False, checks=group:
                                       [item.setChecked(True) for item in checks])
            deselect_all.clicked.connect(lambda _=False, checks=group:
                                         [item.setChecked(False) for item in checks])
            tabs.addTab(page, title)
        save = QPushButton('保存技能设置'); save.setStyleSheet(BLUE_BUTTON)
        save.clicked.connect(self.accept); root.addWidget(save)

        if catalog.is_dark_simei(style):
            active = self.checks['active', 737]
            passive = self.checks['passive', 728]
            active.setChecked(active.isChecked() or passive.isChecked())
            passive.setChecked(active.isChecked())
            active.toggled.connect(passive.setChecked)
            passive.toggled.connect(active.setChecked)

    @staticmethod
    def catalog_data_path(style):
        return ROOT_DIR / 'assets' / 'char-data' / (style.team + '.json')

    @staticmethod
    def _get_passives(style):
        path = SkillSelectionDialog.catalog_data_path(style)
        if not path.is_file(): return []
        data = json.loads(path.read_text(encoding='utf-8'))
        person = next((item for item in data.values()
                       if isinstance(item, dict) and item.get('english name') == style.english), {})
        groups = person.get('skill', {})
        result = {}
        for source in (person.get('passive skill', {}),
                       groups.get(style.title, {}).get('passive skill', {})):
            if isinstance(source, dict):
                for key, item in source.items():
                    if isinstance(item, dict): result[item.get('value', key)] = item
        return list(result.items())  # items取的是json中某技能名key，和value（是包含value，simulation_id等key的字典）

    def selection(self):
        answer = {'active': [], 'passive': [], 'orb': []}
        for (category, simulation_id), check in self.checks.items():
            if check.isChecked():
                answer[category].append(simulation_id)
        return answer

class TargetSelectionDialog(QDialog):
    """选择一个技能目标；我方返回角色 slot，敌方返回敌人 position。"""
    def __init__(self, owner, target_type, source_slot, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择技能目标')
        self.setModal(True)
        self.selected_slot = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('请选择一个目标：'))

        targets = QHBoxLayout()
        targets.setSpacing(8)
        layout.addLayout(targets)
        # 我方角色为目标
        if target_type in ('ally_single', 'ally_single_without_self', "ally_single_front_without_self"):
            for position, slot in enumerate(state['order']):
                if target_type == 'ally_single_without_self' and slot == source_slot:
                    continue
                if target_type == 'ally_single_front_without_self' and (position >= 3 or slot == source_slot):
                    continue
                style = owner.styles[slot]
                button = QPushButton()
                button.setFixedSize(65, 65)
                button.setIcon(QIcon(owner.setup.round_pixmap(style.image, 58)))
                button.setIconSize(QSize(58, 58))
                button.setToolTip(style.localized_title)
                button.clicked.connect(lambda _=False, s=slot: self.choose(s))
                targets.addWidget(button)
        # 敌人单体为目标
        elif target_type == 'enemy':
            names = ('左侧敌人', '中间敌人', '右侧敌人')
            for position, enemy in enumerate(state['enemies']):
                if not enemy['exist']:
                    continue

                button = QPushButton(names[position])
                button.setMinimumSize(105, 40)
                button.clicked.connect(lambda _=False, p=position: self.choose(p))
                targets.addWidget(button)

    def choose(self, slot):
        self.selected_slot = slot
        self.accept()

class UserSelectionDialog(QDialog):
    """选择技能的一个 user_select 分支。返回从 1 开始的选项编号。"""
    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择技能效果')
        self.selected = None
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel('请选择技能效果：'))
        for i, description in enumerate(options, 1):
            button = QPushButton(description)
            button.setMinimumSize(105, 40)
            button.clicked.connect(lambda _=False, index=i: self.choose(index))
            layout.addWidget(button)

    def choose(self, index):
        self.selected = index
        self.accept()

class SpecialActionDialog(QDialog):
    """设置角色是否击破敌人，以及特殊技能发动次数。"""
    SPECIAL_NAMES = {
        'demonic_rage': '鬼神化',
        'all_out_attack': '总攻击',
        'demon_cavalry': '魔界骑兵启动',
        "kelian_form_change": "可怜形态"  # 0为可怜，1为可镰
    }
    def __init__(self, on_break, be_attacked_times, special_trigger, special_count=None, parent=None):
        super().__init__(parent)
        if special_count == None:
            special_count = [0,0]
        self.setWindowTitle('特殊行动设置')
        self.setMinimumWidth(240)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 是否击破敌人
        self.break_check = QCheckBox('是否击破敌人')
        self.break_check.setChecked(bool(on_break))
        layout.addWidget(self.break_check)

        # 是否受敌人攻击
        attacked_line = QHBoxLayout()
        attacked_line.addWidget(QLabel('受敌人攻击次数 '))
        self.attacked_num = spin(low=0, high=10, value=0)
        self.attacked_num.setValue(be_attacked_times)
        attacked_line.addWidget(self.attacked_num)
        layout.addLayout(attacked_line)

        # 特殊技能发动次数 before/after
        self.special_combos = []
        if special_trigger in self.SPECIAL_NAMES:
            if special_trigger == "kelian_form_change":
                row = QHBoxLayout()
                name = self.SPECIAL_NAMES.get("kelian_form_change")
                row.addWidget(QLabel(name))
                kelian_combo = combo([("杀戮如游戏", 0), ("杀戮如呼吸", 1)])
                self.special_combos.append(kelian_combo)
                kelian_combo.setCurrentIndex(
                    max(0, self.special_combos[0].findData(special_count[0]))
                )
                row.addWidget(kelian_combo)
                layout.addLayout(row)
            else:
                for i, timing in enumerate(["（前置OD前发动）", "（前置OD后发动）"]):
                    row = QHBoxLayout()
                    name = self.SPECIAL_NAMES.get(special_trigger)
                    row.addWidget(QLabel(name+timing))
                    maximum = 3 if special_trigger == 'demon_cavalry' else 1
                    special_combo = combo([("不发动" if i == 0 else f"发动{i}次", i) for i in range(maximum + 1)])
                    self.special_combos.append(special_combo)
                    special_combo.setCurrentIndex(
                        max(0, self.special_combos[i].findData(special_count[i]))
                    )
                    row.addWidget(special_combo)
                    layout.addLayout(row)

        # 确定
        confirm = QPushButton('确定')
        confirm.setStyleSheet(BLUE_BUTTON)
        confirm.clicked.connect(self.accept)
        layout.addWidget(confirm)

    def values(self):
        special_count = []
        for combo in self.special_combos:
            special_count.append(combo.currentData())
        return {
            'on_break': self.break_check.isChecked(),
            'be_attacked_times': self.attacked_num.value(),
            'special_count': special_count  # 空列表/长度为1的列表（可镰）/长度为2的列表（waki/总攻击/司令）
        }

class BattleSetup(QGroupBox):
    """固定高度，敌人初始数据、六名上场风格及独立的共鸣风格。"""
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__('战斗设置（左键选择，右键交换）', parent)
        self.setFixedHeight(230)
        self.catalog = catalog
        self.style_dialog_class = style_dialog_class
        self.round_pixmap = round_pixmap
        self.styles = [None] * 6  # 主GUI的Style类
        self.resonances = [None] * 6  # 主GUI的Style类
        self.skill_selections = [{'active': [], 'passive': [], 'orb': []} for _ in range(6)]
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(5)

        enemy_panel = QWidget(); enemy_panel.setFixedWidth(140)
        enemy_col = QVBoxLayout(enemy_panel)
        enemy_col.setContentsMargins(0, 0, 0, 4); enemy_col.setSpacing(2)

        enemy_col.addWidget(QLabel('敌人数量'))
        enemy_line = QHBoxLayout()
        self.enemy_count = combo([(str(n), n) for n in range(1, 4)])
        self.enemy_count.currentIndexChanged.connect(self.change_enemy_count)
        enemy_line.addWidget(self.enemy_count, 1)
        self.enemy_positions = QPushButton()
        self.enemy_positions.clicked.connect(self.change_enemy_count)
        enemy_line.addWidget(self.enemy_positions)
        enemy_col.addLayout(enemy_line)
        self.set_enemy_slots(DEFAULT_ENEMY_SLOTS[1])

        enemy_col.addWidget(QLabel('敌人弱点'))
        self.enemy_weaknesses = []
        weakness_button = QPushButton('设置弱点')
        weakness_button.setStyleSheet(BLUE_BUTTON)
        weakness_button.clicked.connect(self.choose_weaknesses)
        self.weakness_button = weakness_button
        enemy_col.addWidget(weakness_button)

        od_rate_line = QHBoxLayout()
        od_rate_line.addWidget(QLabel('OD率 '))
        self.global_od_rate = spin(0, 999, 100); self.global_od_rate.setMaximumWidth(90)
        self.global_od_rate.setSuffix('%')
        od_rate_line.addWidget(self.global_od_rate, 1)
        enemy_col.addLayout(od_rate_line)

        initial_od_line = QHBoxLayout()
        initial_od_line.addWidget(QLabel('开局OD'))
        self.initial_od = dspin(-300, 300, 0); self.initial_od.setMaximumWidth(90)
        self.initial_od.setSuffix('%')
        initial_od_line.addWidget(self.initial_od, 1)
        enemy_col.addLayout(initial_od_line)
        enemy_col.addStretch()

        reset = QPushButton('重置战斗设置')
        reset.setStyleSheet(WHITE_BUTTON)
        reset.clicked.connect(self.reset)
        enemy_col.addWidget(reset)
        root.addWidget(enemy_panel)
        divider = QFrame(); divider.setFrameShape(QFrame.Shape.VLine); divider.setStyleSheet('color:#91bdff;')
        root.addWidget(divider)

        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(1)
        for row, label in enumerate(('风格与共鸣', '突破', 'OD耳环', '项链', '技能', '共鸣突破')):
            caption = QLabel(label); caption.setFixedWidth(69)
            grid.addWidget(caption, row, 0)
        self.avatar_buttons, self.resonance_buttons = [], []
        self.swap_source = None
        self.breaks, self.earrings, self.necklaces, self.skill_buttons, self.resonance_breaks = [], [], [], [], []
        for i in range(6):
            avatars = QWidget(); av = QHBoxLayout(avatars)
            av.setContentsMargins(0, 0, 0, 0); av.setSpacing(3)
            av.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            avatar = QPushButton('＋'); avatar.setFixedSize(61, 61)
            avatar.clicked.connect(lambda _=False, index=i: self.choose_style(index))
            avatar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            avatar.customContextMenuRequested.connect(lambda _=None, index=i: self.swap_setup_slots(index))
            resonance = QPushButton('＋'); resonance.setFixedSize(35, 35)
            resonance.setToolTip('选择共鸣风格（右键清空）')
            resonance.clicked.connect(lambda _=False, index=i: self.choose_resonance(index))
            resonance.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            resonance.customContextMenuRequested.connect(lambda _=None, index=i: self.clear_resonance(index))
            av.addWidget(avatar); av.addWidget(resonance)
            grid.addWidget(avatars, 0, i+1)
            self.avatar_buttons.append(avatar); self.resonance_buttons.append(resonance)
            level = combo([(str(n), n) for n in range(5)])
            ear = combo([('无', 0), ('10%', 10), ('12%', 12), ('15%', 15)])
            necklace = combo([(f'SP+{n}', n) for n in range(4)])
            self.breaks.append(level); self.earrings.append(ear)
            self.necklaces.append(necklace)
            ear.setCurrentIndex(3); necklace.setCurrentIndex(3)
            for row, widget in enumerate((level, ear, necklace), 1):
                widget.setMinimumWidth(77)
                grid.addWidget(widget, row, i+1)
            button = QPushButton('设置技能'); button.setStyleSheet(BLUE_BUTTON)
            button.setFixedHeight(22)
            button.clicked.connect(lambda _=False, index=i: self.choose_skills(index))
            grid.addWidget(button, 4, i+1)
            resonance_level = combo([(str(n), n) for n in range(5)])
            resonance_level.setCurrentIndex(2)
            resonance_level.setMinimumWidth(77)
            grid.addWidget(resonance_level, 5, i+1)
            self.resonance_breaks.append(resonance_level)
            self.skill_buttons.append(button)
        for col in range(1, 7): grid.setColumnStretch(col, 1)
        root.addLayout(grid, 1)
        self.weakness_button.setToolTip('无弱点')

    @staticmethod
    def identity(style):
        return (style.team, style.english, style.sid) if style else None

    def choose_weaknesses(self):
        dialog = WeaknessDialog(self.enemy_weaknesses, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_weaknesses(dialog.values())

    def set_weaknesses(self, weaknesses):
        self.enemy_weaknesses = list(weaknesses)
        names = '、'.join(ELEMENT_NAMES[x] for x in self.enemy_weaknesses) or '无'
        self.weakness_button.setText('弱点：' + names)
        self.weakness_button.setToolTip(names)

    @staticmethod
    def _max_level(style):
        return {'A': 20, 'S': 10, 'SS': 4, 'SSR': 4}.get(style.tier, 4) if style else 4

    @staticmethod
    def _default_level(style):
        return BattleSetup._max_level(style) if style and style.tier in ('A', 'S') else 2

    @staticmethod
    def _set_level(box, style):
        maximum = BattleSetup._max_level(style)
        box.clear()
        for n in range(maximum + 1):
            box.addItem(str(n), n)
        box.setCurrentIndex(BattleSetup._default_level(style))

    def _set_avatar(self, index, resonance=False):
        style = self.resonances[index] if resonance else self.styles[index]
        button = self.resonance_buttons[index] if resonance else self.avatar_buttons[index]
        size = 32 if resonance else 58
        button.setText('' if style else '＋')
        button.setIcon(QIcon(self.round_pixmap(style.image, size)) if style else QIcon())
        button.setIconSize(QSize(size, size))
        button.setToolTip((('共鸣：' if resonance else '上场：') +
                           style.label + ' · ' + style.localized_title) if style else
                          ('选择共鸣风格（右键清空）' if resonance else '选择上场风格'))

    def choose_style(self, index):
        self.clear_setup_swap()
        occupied = {style.name for i, style in enumerate(self.styles)
                    if style is not None and i != index}
        # 不允许与已经使用的共鸣风格相同：在选择弹窗内直接隐藏。
        forbidden = {self.identity(style) for style in self.resonances if style}
        dialog = self._filtered_dialog(occupied, forbidden)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        selected = dialog.chosen
        if any(self.identity(selected) == self.identity(x) for x in self.resonances if x):
            QMessageBox.warning(self, '风格冲突', '这个风格已经作为共鸣风格选中，请先取消共鸣。')
            return
        self.styles[index] = selected
        orb_names = set(self.catalog.common_global)
        self.skill_selections[index] = {
            'active': [
                int(self.catalog.skill_data[name]['simulation_id'])
                for name in self.catalog.skills_for(selected)
                if name not in orb_names and name != "指揮行動"
            ],
            'passive': [
                int(entry["simulation_id"])
                for _, entry in SkillSelectionDialog._get_passives(selected)
            ],
            'orb': [
                int(self.catalog.skill_data[name]["simulation_id"])
                for name in self.catalog.common_global
            ]
        }
        self._set_avatar(index)
        self._set_level(self.breaks[index], selected)

    def clear_setup_swap(self):
        if self.swap_source is not None:
            self.avatar_buttons[self.swap_source].setStyleSheet('')
            self.swap_source = None

    def swap_setup_slots(self, index):
        if self.swap_source is None:
            self.swap_source = index
            self.avatar_buttons[index].setStyleSheet('QPushButton{border:2px solid #2563eb;background:#dbeafe;}')
            return
        first = self.swap_source
        self.clear_setup_swap()
        if first == index:
            return
        # 风格、共鸣、技能与饰品配置一起换位
        for entries in (self.styles, self.resonances, self.skill_selections):
            entries[first], entries[index] = entries[index], entries[first]
        for boxes, styles in ((self.breaks, self.styles), (self.resonance_breaks, self.resonances),
                              (self.earrings, None), (self.necklaces, None)):
            first_value, second_value = boxes[first].currentData(), boxes[index].currentData()
            for slot, value in ((first, second_value), (index, first_value)):
                if styles is not None:
                    self._set_level(boxes[slot], styles[slot])
                boxes[slot].setCurrentIndex(boxes[slot].findData(value))
        for slot in (first, index):
            self._set_avatar(slot)
            self._set_avatar(slot, resonance=True)
            count = sum(len(group) for group in self.skill_selections[slot].values())
            self.skill_buttons[slot].setToolTip(f'已选 {count} 项技能' if self.styles[slot] else '')

    def _filtered_dialog(self, occupied, forbidden):
        # StyleDialog 的过滤按角色名进行；通过轻量代理追加风格级精确排除，
        # 不修改原 Catalog，不影响其余 GUI。
        class CatalogView:
            def __init__(self, catalog, blocked):
                self._catalog = catalog
                self.styles = [style for style in catalog.styles
                               if BattleSetup.identity(style) not in blocked]
            def __getattr__(self, name):
                return getattr(self._catalog, name)
        return self.style_dialog_class(CatalogView(self.catalog, forbidden), occupied, self)

    def choose_resonance(self, index):
        self.clear_setup_swap()
        forbidden = {self.identity(style) for style in self.styles if style}
        forbidden.update(self.identity(style) for i, style in enumerate(self.resonances)
                         if i != index and style)
        dialog = self._filtered_dialog(set(), forbidden)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        self.resonances[index] = dialog.chosen
        self._set_level(self.resonance_breaks[index], dialog.chosen)
        self._set_avatar(index, resonance=True)

    def clear_resonance(self, index):
        self.resonances[index] = None
        self._set_level(self.resonance_breaks[index], None)
        self._set_avatar(index, resonance=True)

    def choose_skills(self, index):
        style = self.styles[index]
        if style is None:
            QMessageBox.information(self, '未选择风格', '请先选择该位置的风格。'); return
        dialog = SkillSelectionDialog(self.catalog, style, self.skill_selections[index], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.skill_selections[index] = dialog.selection()
            count = sum(len(group) for group in self.skill_selections[index].values())
            self.skill_buttons[index].setToolTip(f'已选 {count} 项技能')

    def set_enemy_slots(self, slots):
        self.enemy_slots = tuple(sorted(slots))
        blocked = self.enemy_count.blockSignals(True)
        self.enemy_count.setCurrentIndex(self.enemy_count.findData(len(slots)))
        self.enemy_count.blockSignals(blocked)
        self.enemy_positions.setVisible(len(slots) == 2)
        self.enemy_positions.setText('、'.join('左中右'[slot] for slot in self.enemy_slots))
        self.enemy_positions.setToolTip('重新选择双体敌人的位置')

    def change_enemy_count(self):
        count = self.enemy_count.currentData()
        if count != 2:
            self.set_enemy_slots(DEFAULT_ENEMY_SLOTS[count])
            return
        positions = [(0, 1), (0, 2), (1, 2)]
        labels = ['左侧和中间', '左侧和右侧', '中间和右侧']
        current = positions.index(self.enemy_slots) if self.enemy_slots in positions else 0
        selected, ok = QInputDialog.getItem(
            self, '选择双体敌人位置', '请根据实际战斗界面选择两个敌人的位置。',
            labels, current, False
        )
        self.set_enemy_slots(positions[labels.index(selected)] if ok else self.enemy_slots)

    def reset(self):
        self.clear_setup_swap()
        self.styles = [None]*6; self.resonances = [None]*6
        self.skill_selections = [{'active': [], 'passive': [], 'orb': []} for _ in range(6)]
        self.set_enemy_slots(DEFAULT_ENEMY_SLOTS[1])
        self.initial_od.setValue(0); self.global_od_rate.setValue(100)
        self.enemy_weaknesses = []
        self.weakness_button.setText('设置弱点')
        self.weakness_button.setToolTip('无弱点')
        for i in range(6):
            self._set_avatar(i); self._set_avatar(i, resonance=True)
            level = self.breaks[i]; level.clear()
            for n in range(5): level.addItem(str(n), n)
            level.setCurrentIndex(2)
            self.earrings[i].setCurrentIndex(3)
            self.necklaces[i].setCurrentIndex(3)
            self.skill_buttons[i].setToolTip('')
            self._set_level(self.resonance_breaks[i], None)

    def state(self):
        """构造 simulation.initialize() 所需的纯 ID 配置。"""
        # 风格和共鸣
        styles = []
        resonances = []
        for i, style in enumerate(self.styles):
            active_ids = list(self.skill_selections[i]['active'])        # 主动技能
            passive_ids = list(self.skill_selections[i]['passive'])        # 被动技能
            orb_ids = list(self.skill_selections[i]['orb'])        # 光球技能
            styles.append({
                'style_id': self._style_id(style),
                'break_level': int(self.breaks[i].currentData()),
                'od_earring': int(self.earrings[i].currentData()),
                'necklace_sp': int(self.necklaces[i].currentData()),
                'active_skill_ids': active_ids,
                'passive_skill_ids': passive_ids,
                'orb_skill_ids': orb_ids,
            })

            # 共鸣风格
            resonance = self.resonances[i]

            if resonance is None:
                resonances.append(None)
            else:
                resonances.append({
                    'style_id': self._style_id(resonance),
                    'break_level': int(self.resonance_breaks[i].currentData()),
                })

        return {
            'styles': styles,
            'resonances': resonances,
            'enemy_count': int(self.enemy_count.currentData() or 1),
            'enemy_slots': list(self.enemy_slots),
            'enemy_weaknesses': list(self.enemy_weaknesses),
            'initial_od': float(self.initial_od.value()),
            'global_od_rate': float(self.global_od_rate.value()),
        }

    def resolve_styles(self, setup):
        # 导出文件只保存simulation_id，导入时还原GUI使用的风格对象
        entries = setup['styles'] + setup['resonances']
        wanted = {entry['style_id'] for entry in entries if entry is not None}
        styles = {}
        team_data = {}
        for style in self.catalog.styles:
            try:
                style_id = self._style_id(style, team_data)
            except ValueError:
                continue
            if style_id in wanted:
                styles[style_id] = style
                if wanted == styles.keys():
                    break
        missing = wanted - styles.keys()
        if missing:
            raise ValueError(f'界面数据库找不到风格 ID：{sorted(missing)}')
        return [styles[entry['style_id']] if entry is not None else None for entry in entries]

    def restore_state(self, setup, styles):
        self.clear_setup_swap()
        self.styles, self.resonances = styles[:6], styles[6:]
        for i, (entry, resonance) in enumerate(zip(setup['styles'], setup['resonances'])):
            self.skill_selections[i] = {
                'active': list(entry['active_skill_ids']),
                'passive': list(entry['passive_skill_ids']),
                'orb': list(entry['orb_skill_ids']),
            }
            count = sum(len(group) for group in self.skill_selections[i].values())
            self.skill_buttons[i].setToolTip(f'已选 {count} 项技能')
            self._set_avatar(i)
            self._set_avatar(i, resonance=True)
            self._set_level(self.breaks[i], self.styles[i])
            self._set_level(self.resonance_breaks[i], self.resonances[i])
            self.breaks[i].setCurrentIndex(self.breaks[i].findData(entry['break_level']))
            self.earrings[i].setCurrentIndex(self.earrings[i].findData(entry['od_earring']))
            self.necklaces[i].setCurrentIndex(self.necklaces[i].findData(entry['necklace_sp']))
            if resonance is not None:
                box = self.resonance_breaks[i]
                box.setCurrentIndex(box.findData(resonance['break_level']))
        self.set_enemy_slots(setup.get('enemy_slots', DEFAULT_ENEMY_SLOTS[setup['enemy_count']]))
        self.initial_od.setValue(setup['initial_od'])
        self.global_od_rate.setValue(setup['global_od_rate'])
        self.set_weaknesses(setup['enemy_weaknesses'])

    def check_saved_setup(self, setup, styles):
        # 写入控件前检查范围，避免Qt静默截断存档里的设定
        for i, entry in enumerate(setup['styles']):
            if entry['break_level'] not in range(self._max_level(styles[i]) + 1) or \
               self.earrings[i].findData(entry['od_earring']) < 0 or \
               self.necklaces[i].findData(entry['necklace_sp']) < 0:
                raise ValueError(f'第 {i + 1} 个上场风格的突破或饰品设定无效。')
            for key in ('active_skill_ids', 'passive_skill_ids', 'orb_skill_ids'):
                if not isinstance(entry[key], list):
                    raise ValueError(f'第 {i + 1} 个上场风格的技能设定无效。')
        for i, entry in enumerate(setup['resonances']):
            if entry is not None and entry['break_level'] not in range(self._max_level(styles[i + 6]) + 1):
                raise ValueError(f'第 {i + 1} 个共鸣风格的突破设定无效。')
        for box, value in ((self.initial_od, setup['initial_od']), (self.global_od_rate, setup['global_od_rate'])):
            if not box.minimum() <= value <= box.maximum():
                raise ValueError('开局OD或OD倍率超出设定范围。')
        if any(element not in ELEMENT_NAMES for element in setup['enemy_weaknesses']):
            raise ValueError('敌人弱点包含未知属性。')

    @staticmethod
    def _style_id(style, team_data=None):
        if style is None: return None
        path = SkillSelectionDialog.catalog_data_path(style)
        if team_data is None:
            team_data = {}
        if path not in team_data:
            if not path.exists(): raise FileNotFoundError(f'找不到风格数据库：{path}')
            team_data[path] = json.loads(path.read_text(encoding='utf-8'))
        data = team_data[path]
        person = next((v for v in data.values() if isinstance(v, dict) and
                       v.get('english name') == style.english), {})
        entry = next((v for v in person.get('style', {}).values()
                      if v.get('value') == style.title), {})
        value = entry.get('simulation_id')
        if value is None:
            raise ValueError(
                f'风格 {style.localized_title} 缺少 simulation_id'
            )
        return value


class PortraitWithSP(QWidget):
    """SP 叠加于头像右上角，白色粗体、黑色描边。"""
    def __init__(self, size=52, parent=None):
        super().__init__(parent)
        self.setFixedSize(size + 7, size + 5)
        self.picture = QPixmap()
        self.image_path = None
        self.image_ratio = None
        self.sp = 0
        self.size = size

    def configure(self, path, round_pixmap, sp):
        ratio = self.devicePixelRatioF()
        image_changed = path != self.image_path or ratio != self.image_ratio
        if image_changed:
            self.image_path, self.image_ratio = path, ratio
            self.picture = round_pixmap(path, self.size) if path else QPixmap()
        if image_changed or self.sp != sp:
            self.sp = sp
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.picture.isNull():
            painter.drawPixmap(1, 3, self.picture)
        else:
            painter.setPen(QPen(QColor('#94a3b8')))
            painter.drawEllipse(2, 4, self.size - 2, self.size - 2)
        font = QFont(); font.setBold(True); font.setPointSize(13)
        painter.setFont(font)
        text = str(self.sp)
        rect = self.rect().adjusted(0, -2, -1, 0)
        # 先绘制八方向黑色描边，再绘制白色文字。
        painter.setPen(QPen(QColor('#dc2626' if self.sp < 0 else '#111827'), 2 if self.sp < 0 else 1))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (1, 1), (-1, 1), (1, -1)):
            painter.drawText(rect.translated(dx, dy),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, text)
        painter.setPen(QPen(QColor('white')))
        painter.drawText(rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, text)
        painter.end()

class TargetBadge(QAbstractButton):
    """头像右下角的技能目标标记。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(25, 25)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip('左键重新选择技能目标')
        self.pixmap = QPixmap()
        self.text = ''
        self.hide()

    def configure(self, target, styles, round_pixmap):
        self.pixmap = QPixmap()
        self.text = ''
        kind = target.get('type')
        slot = target.get('slot')
        if slot is None:
            self.hide()
            return
        if kind in ('ally_single', 'ally_single_without_self', 'ally_single_front_without_self'):
            style = styles[slot]
            self.pixmap = round_pixmap(style.image, 22)
        elif kind == 'enemy':
            self.text = ('左', '中', '右')[slot]
        else:
            self.hide()
            return
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.pixmap.isNull():
            painter.drawPixmap(1, 1, self.pixmap)
            painter.setPen(QPen(QColor('#2563eb'), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(1, 1, 22, 22)
        elif self.text:
            painter.setPen(QPen(QColor('#2563eb'), 1))
            painter.setBrush(QColor('white'))
            painter.drawEllipse(1, 1, 22, 22)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(11)
            painter.setFont(font)
            painter.setPen(QColor('#2563eb'))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self.text
            )
        painter.end()

class BattleTurn(QGroupBox):
    """
    单回合 GUI：base 保存确定状态，adjustments 保存手动偏移。成员始终按 slot 排列。
    update表示更改state_data，refresh表示刷新界面显示。
    目前combat界面的更改会直接修改state_data，adjust修改则仅在退出时应用到state_data，进入时从state_data来load。
    """
    HEIGHT = 105
    def __init__(self, owner, number, state):
        super().__init__('')
        self.owner, self.number = owner, number
        self.state_data = copy.deepcopy(state)
        self._status_db = self.owner.status_db
        self._combo_options = {}
        self._shown_statuses = {}
        self._shown_targets = {}
        self._shown_weaknesses = None
        self._shown_field = None
        self._shown_od_icon = None
        self.select_first = None
        self.setObjectName('simulationTurn')
        self.setFixedHeight(self.HEIGHT)
        outer = QVBoxLayout(self); outer.setContentsMargins(4, 3, 4, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.height_timer = QTimer(self)
        self.height_timer.setSingleShot(True)
        self.height_timer.timeout.connect(self.update_turn_height)
        self._make_combat_page()
        self.refresh()

    @staticmethod
    def _separator():
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet('color:#91bdff;')
        divider.setFixedWidth(2)
        return divider

    def _make_combat_page(self):
        page = QWidget()
        root = QHBoxLayout(page); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(3)
        enemy = QWidget()
        el = QVBoxLayout(enemy); el.setContentsMargins(1, 0, 1, 0); el.setSpacing(0)
        self.title = QLabel(); self.title.setStyleSheet('font-weight:700;')
        el.addWidget(self.title)
        self.enemy_weakness_row = QHBoxLayout(); self.enemy_weakness_row.setSpacing(1)
        el.addLayout(self.enemy_weakness_row)
        self.enemy_status_rows = []
        for label in ('左侧敌人：', '中间敌人：', '右侧敌人：'):
            line = QWidget()
            row = QHBoxLayout(line)
            row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)
            row.addWidget(QLabel(label))
            statuses = StatusRow()
            row.addWidget(statuses, 1)
            el.addWidget(line)
            self.enemy_status_rows.append((line, statuses))
        self.field_display = QHBoxLayout(); self.field_display.setSpacing(1)
        el.addLayout(self.field_display)
        el.addStretch()
        root.addWidget(enemy, 20)
        root.addWidget(self._separator())

        team = QWidget()
        tl = QHBoxLayout(team); tl.setContentsMargins(1, 0, 1, 0); tl.setSpacing(3)
        self.portraits, self.target_badges, self.action_boxes = [], [], []
        self.status_rows, self.member_resources = [], []
        for first, last, stretch in ((0, 3, 65), (3, 6, 35)):
            group = QHBoxLayout(); group.setSpacing(2)
            for position in range(first, last):
                col = QVBoxLayout(); col.setSpacing(1)
                # 行动框
                action = FullPopupCombo()
                action.setFixedHeight(22)
                action.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                action.setMinimumContentsLength(1)
                action.setMinimumWidth(0)
                action.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                policy = action.sizePolicy()
                policy.setRetainSizeWhenHidden(True)
                action.setSizePolicy(policy)
                action.currentIndexChanged.connect(lambda _=0, pos=position: self.update_action(pos))
                col.addWidget(action)
                # 框下主体部分
                body = QHBoxLayout()
                body.setSpacing(0)
                # 信念
                token = QLabel()
                token.setMaximumWidth(27)
                token.setAlignment(Qt.AlignmentFlag.AlignCenter)
                token.setStyleSheet('font-size:10px;font-weight:600;')
                # ep
                ep = QLabel()
                ep.setMaximumWidth(27)
                ep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ep.setStyleSheet('font-size:10px;font-weight:600;')
                # 头像
                avatar = QPushButton()
                avatar.setFixedSize(55, 54)
                avatar.setStyleSheet('QPushButton{background:transparent;border:0;padding:0}')
                portrait = PortraitWithSP(45, avatar)
                portrait.move(2, 1)
                badge = TargetBadge(avatar)
                badge.move(30, 29)
                badge.clicked.connect(lambda _=False, pos=position: self.change_action_target(pos))
                avatar.clicked.connect(lambda _=False, pos=position: self.swap_position(pos))
                # 头像右键展开特殊状态编辑
                avatar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                avatar.customContextMenuRequested.connect(
                    lambda _=None, pos=position: self.handle_special_click(pos)
                )
                # 顺序为：信念、头像、ep
                body.addWidget(token)
                body.addWidget(avatar)
                body.addWidget(ep)
                col.addLayout(body)
                # 三者下方的statuses
                statuses = StatusRow() if position < 3 else None
                if statuses is not None:
                    col.addWidget(statuses)
                col.addStretch()
                group.addLayout(col, 1)
                self.portraits.append((avatar, portrait))
                self.target_badges.append(badge)
                self.action_boxes.append(action)
                self.status_rows.append(statuses)
                self.member_resources.append((token, ep))
            tl.addLayout(group, stretch)
        root.addWidget(team, 70)
        root.addWidget(self._separator())

        od = QWidget()
        ol = QVBoxLayout(od); ol.setContentsMargins(4, 2, 4, 2); ol.setSpacing(1)
        top = QHBoxLayout(); top.setSpacing(2)
        # od显示区
        self.od_icon = QLabel(); self.od_icon.setFixedSize(35, 35)
        top.addWidget(self.od_icon)
        od_values = QVBoxLayout(); od_values.setSpacing(0)
        self.od_label = QLabel(); self.od_label.setStyleSheet('font-weight:700;')
        self.predicted_od_label = QLabel(); self.predicted_od_label.setStyleSheet('font-weight:700;')
        # 为箭头、负号和五位数字预留宽度，OD变化时不挤动其他区域
        od_font = QFont(self.owner.font())
        od_font.setBold(True)
        self.predicted_od_label.setMinimumWidth(QFontMetrics(od_font).horizontalAdvance('→ -100.00%'))
        od_values.addWidget(self.od_label)
        od_values.addWidget(self.predicted_od_label)
        top.addLayout(od_values); top.addStretch()
        ol.addLayout(top)
        # od发动选择区
        self.before_od = combo([('不发动', 0)])
        self.after_od = combo([('不发动', 0)])
        self.before_od_caption = QLabel('前置')
        self.after_od_caption = QLabel('后置')
        for caption, box in ((self.before_od_caption, self.before_od), (self.after_od_caption, self.after_od)):
            row = QHBoxLayout()
            row.setSpacing(2)
            caption.setFixedWidth(27)
            row.addWidget(caption)
            row.addWidget(box, 1)
            ol.addLayout(row)
        self.before_od.currentIndexChanged.connect(lambda: self.update_and_refresh_od('before'))
        self.after_od.currentIndexChanged.connect(lambda: self.update_and_refresh_od('after'))
        ol.addStretch()
        root.addWidget(od, 10)
        root.addWidget(self._separator())

        # 操作栏：OD 区域只负责显示及发动设置，不再放置按钮。
        operations = QWidget()
        op = QVBoxLayout(operations)
        op.setContentsMargins(2, 2, 2, 2); op.setSpacing(2)
        self.switch_button = QPushButton('调整')
        self.switch_button.setStyleSheet(BLUE_BUTTON)
        self.switch_button.setFixedHeight(26)
        self.switch_button.clicked.connect(self.toggle_mode)
        self.next_button = QPushButton('下一回合')
        self.next_button.setStyleSheet(BLUE_BUTTON)
        self.next_button.setFixedHeight(26)
        self.next_button.clicked.connect(lambda: self.owner.next_turn())
        self.back_button = QPushButton('回到本回合')
        self.back_button.setFixedHeight(27)
        self.back_button.setStyleSheet(WHITE_BUTTON)
        self.back_button.clicked.connect(lambda: self.owner.truncate_after(self))
        op.addWidget(self.switch_button)
        op.addWidget(self.next_button)
        op.addWidget(self.back_button)
        op.addStretch()
        root.addWidget(operations, 6)
        self.stack.addWidget(page)

    def _make_adjust_page(self):
        page = QWidget()
        root = QHBoxLayout(page); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(3)
        enemy = QWidget()
        grid = QGridLayout(enemy); grid.setContentsMargins(3, 2, 3, 2); grid.setSpacing(2)
        grid.addWidget(QLabel('敌人'), 0, 0)
        grid.addWidget(QLabel('倒下'), 1, 0)
        grid.addWidget(QLabel('破坏率'), 2, 0)
        self.enemy_presence_checks, self.enemy_edits = [], []
        for position, title in enumerate(('敌人左', '敌人中', '敌人右')):
            # 选择敌人
            header = QHBoxLayout(); header.setSpacing(1)
            header.addWidget(QLabel(title))
            present = QCheckBox()
            present.setToolTip('勾选表示此位置存在敌人')
            present.toggled.connect(self.refresh_enemy_setting)
            header.addWidget(present)
            grid.addLayout(header, 0, position + 1)
            # 敌人倒下和破坏率编辑
            down, rate = QCheckBox(), spin(0, 999, 100)
            down.setToolTip('是否处于倒下回合')
            grid.addWidget(down, 1, position + 1, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(rate, 2, position + 1)
            self.enemy_presence_checks.append(present)
            self.enemy_edits.append((down, rate))
        root.addWidget(enemy, 25)
        root.addWidget(self._separator())

        # 角色：DP 与头像横向并列，占据第一行；下面只有 SP 和信念。
        team = QWidget()
        grid = QGridLayout(team); grid.setContentsMargins(3, 2, 3, 2); grid.setSpacing(2)
        for row, name in enumerate(('DP', 'SP', '信念')):
            caption = QLabel(name); caption.setFixedWidth(28)
            grid.addWidget(caption, row, 0)
        self.member_edits, self.member_portraits = [], []
        for position in range(6):
            top = QHBoxLayout(); top.setSpacing(1)
            picture = QLabel(); picture.setFixedSize(25, 25); picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top.addWidget(picture)
            dp = dspin(0, 150, 100)
            dp.setSuffix('%'); dp.setFixedHeight(22); dp.setMinimumWidth(46)
            dp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            top.addWidget(dp, 1)
            grid.addLayout(top, 0, position + 1)
            controls = {'dp': dp}
            for row, key in ((1, 'sp'), (2, 'token')):
                widget = spin(-99, 99, 0); widget.setMinimumWidth(58)
                grid.addWidget(widget, row, position + 1)
                controls[key] = widget
            self.member_edits.append(controls)
            self.member_portraits.append(picture)
        root.addWidget(team, 65)
        root.addWidget(self._separator())

        # 调整区：OD±、场地、返回按钮
        misc = QWidget()
        layout = QVBoxLayout(misc); layout.setContentsMargins(3, 2, 3, 2); layout.setSpacing(3)
        od_line = QHBoxLayout(); od_line.setSpacing(2)
        od_line.addWidget(QLabel('OD'))
        self.adjust_od = dspin(-500, 500, 0)
        od_line.addWidget(self.adjust_od, 1)
        layout.addLayout(od_line)
        field_line = QHBoxLayout(); field_line.setSpacing(2)
        field_line.addWidget(QLabel('场地'))
        self.adjust_field = combo(FIELD_OPTIONS)
        field_line.addWidget(self.adjust_field, 1)
        layout.addLayout(field_line)
        back = QPushButton('返回')
        back.setStyleSheet(BLUE_BUTTON)
        back.clicked.connect(self.toggle_mode)
        layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        root.addWidget(misc, 7)
        self.stack.addWidget(page)

    @staticmethod
    def simulation_input(state_data):
        """GUI传给engine可操作的base相关内容，engine内部增量更新"""
        base = state_data["base"]
        return {
            "member_dp": [m["dp"] for m in base["members"]],
            "order": base["order"],
            "actions": base["actions"],
            "enemies": [{key: enemy[key] for key in ("exist", "damage_rate", "down")}
                        for enemy in base["enemies"]],
            "field": base["field"],
            "od_timing": base["od_timing"],
            "od_level": base["od_level"],
            "special_actions": base["special_actions"],
            "adjustments": state_data["adjustments"]
        }

    def update_state_from_simulation(self):
        """
        调用simulationTab的相关函数，GUI传给engine可操作的base相关内容，engine内部增量更新，然后传回来完整的base state
        """
        self.owner.sync_from_turn(self)

    def edit_special_action(self, position):
        base = self.state_data['base']
        slot = base['order'][position]
        action = base['actions'][slot]
        special_trigger = base['members'][slot].get('special_trigger')
        special_actions = base.get('special_actions')
        # 创建对话框，读取当前状态
        if action != None:
            special_count = None if special_trigger == None else [special_actions.get(special_trigger, 0), special_actions.get(special_trigger+"_after", 0)]
            dialog = SpecialActionDialog(
                on_break=action.get('on_break', False),
                be_attacked_times=action.get('be_attacked_times') or 0,
                special_trigger=special_trigger,
                special_count=special_count,
                parent=self
            )
            # 取消则不更改任何内容
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            # 保存角色的 on_break
            action['on_break'] = values['on_break']
            action['be_attacked_times'] = values['be_attacked_times']
            # 保存特殊技能发动次数
            if special_trigger in SpecialActionDialog.SPECIAL_NAMES:
                special_actions[special_trigger] = values['special_count'][0]
                if len(values['special_count']) == 2:
                    special_actions[special_trigger+"_after"] = values['special_count'][1]
            self.update_state_from_simulation()
        self.refresh()

    def refresh_enemy_setting(self, *_):
        checks = self.enemy_presence_checks
        # 至少保留一个敌人
        for check in checks:
            check.setEnabled(
                not check.isChecked()
                or sum(c.isChecked() for c in checks) > 1
            )
        # 更改样式
        for present, (down, rate) in zip(checks, self.enemy_edits):
            active = present.isChecked()
            down.setEnabled(active)
            down.setStyleSheet('' if active else
                               'QCheckBox::indicator:disabled{background:#cbd5e1;'
                               'border:1px solid #94a3b8;border-radius:3px;}')
            rate.setEnabled(active)
            rate.setStyleSheet('' if active else
                               'QSpinBox:disabled{background:#e5e7eb;color:#6b7280;'
                               'border:1px solid #cbd5e1;}')

    # 进行target和user_selected的选择
    def update_action(self, position):
        base = self.state_data['base']
        slot = base['order'][position]
        skill_id = self.action_boxes[position].currentData()
        skill = next((s for s in base['members'][slot]['skills'] if s['id'] == skill_id), None)
        if skill is None:
            return
        old_action = base['actions'][slot]
        target = self.select_action_target(skill['target_type'], slot, base)
        if target is None:
            self.restore_action(position, old_action)
            return
        user_selected = None
        # 选择 user_select 分支
        options = skill.get('user_select')
        if options:
            dialog = UserSelectionDialog(options, self)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.restore_action(position, old_action)
                return

            user_selected = dialog.selected
        # 更新action
        base['actions'][slot] = {
            'id': skill['id'],
            'name': skill['name'],
            'target': target,
            'user_selected': user_selected,
            'on_break': False,
            "be_attacked_times": 0
        }

        self.update_state_from_simulation()
        # 刷新显示
        self.refresh()

    def select_action_target(self, target_type, slot, base):
        # 单体敌人和无需指定目标的技能直接返回
        if target_type == 'ignore':
            return {'type': target_type, 'slot': None}
        if target_type == 'enemy':
            enemies = [i for i, enemy in enumerate(base['enemies']) if enemy['exist']]
            if len(enemies) == 1:
                return {'type': target_type, 'slot': enemies[0]}
        dialog = TargetSelectionDialog(self.owner, target_type, slot, base, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return {'type': target_type, 'slot': dialog.selected_slot}

    def change_action_target(self, position):
        base = self.state_data['base']
        slot = base['order'][position]
        action = base['actions'][slot]
        if not action:
            return
        skill = next((skill for skill in base['members'][slot]['skills'] if skill['id'] == action['id']), None)
        if skill is None or skill['target_type'] == 'ignore':
            return
        target = self.select_action_target(skill['target_type'], slot, base)
        if target is not None and target != action['target']:
            action['target'] = target
            self.update_state_from_simulation()
            self.refresh()

    # 用户取消选择时调用，用于恢复上一个选择的技能
    def restore_action(self, position, old_action):
        box = self.action_boxes[position]

        box.blockSignals(True)
        box.setCurrentIndex(box.findData(old_action['id']) if old_action else -1)
        box.blockSignals(False)

    # 更新od值同时调用refresh
    def update_and_refresh_od(self, timing):
        base = self.state_data['base']
        selected = self.before_od if timing == 'before' else self.after_od
        other = self.after_od if timing == 'before' else self.before_od
        # 前置和后置od互斥
        if selected.currentData():
            other.blockSignals(True)
            other.setCurrentIndex(0)
            other.blockSignals(False)
        # 更新state
        base['od_timing'] = timing if selected.currentData() else None
        base['od_level'] = selected.currentData() or 0

        self.update_state_from_simulation()
        self.refresh()

    def clear_swap_selection(self):
        if self.select_first is not None:
            self.portraits[self.select_first][0].setStyleSheet(
                'QPushButton{background:transparent;border:0;padding:0}')
            self.select_first = None

    def handle_special_click(self, position):
        self.clear_swap_selection()
        self.edit_special_action(position)

    def swap_position(self, position):
        if self.select_first is None:
            self.select_first = position
            self.portraits[position][0].setStyleSheet(
                'QPushButton{border:2px solid #2563eb;background:#dbeafe}')  # 选中样式
            return
        first, second = self.select_first, position
        self.clear_swap_selection()
        if first == second or (first >= 3 and second >= 3):  # 后排交换不允许
            return
        base = self.state_data['base']

        # 追加回合
        if base["additional_turn"]:
            first_slot = base["order"][first]
            second_slot = base["order"][second]
            # 只有本次追加回合允许行动的角色可以互换
            available_slots = {
                slot
                for slot in base["order"][:3]
                if any(status.get("id") == 20 for status in base["members"][slot]["statuses"])
            }
            if (first_slot not in available_slots or second_slot not in available_slots):
                return

        # 队伍state顺序交换
        base['order'][first], base['order'][second] = base['order'][second], base['order'][first]
        # 前后排交换技能重新安排
        if (first < 3) != (second < 3):
            for position in (first, second):
                slot = base['order'][position]
                # 可以行动
                if base['members'][slot]['skills']:
                    skill = base['members'][slot]['skills'][
                        0 if position < 3 else 1  # 0为前排默认技能，1为后排默认技能
                    ]

                    base['actions'][slot] = {
                        'id': skill['id'],
                        'name': skill['name'],
                        'target': {
                            'type': skill.get('target_type'),
                            'slot': None
                        },
                        'user_selected': None,
                        'on_break': False,
                        "be_attacked_times": 0
                    }
                # 当前没有可用技能时交给模拟重新判断
                else:
                    base['actions'][slot] = None

        self.update_state_from_simulation()
        self.refresh()

    # 负责从 state_data 读取值到调整页
    def load_adjust(self):
        base = self.state_data['base']
        adjust = self.state_data['adjustments']
        # od和场地
        self.adjust_od.setValue(adjust['od'])
        self.adjust_field.setCurrentIndex(max(0, self.adjust_field.findData(base.get('field'))))
        # 敌人
        enemies = base.get('enemies')
        for position, (down, rate) in enumerate(self.enemy_edits):
            enemy = enemies[position]
            exists = enemy["exist"]
            present = self.enemy_presence_checks[position]
            present.blockSignals(True)
            present.setChecked(exists)
            present.blockSignals(False)
            down.setChecked(enemy['down'] if exists else False)
            rate.setValue(enemy['damage_rate'] if exists else 100)
        # 队伍
        for position, controls in enumerate(self.member_edits):
            slot = base['order'][position]
            member = base['members'][slot]
            delta = adjust['members'][slot]
            for key in ('sp', 'token'):
                controls[key].setValue(delta.get(key, 0))
            controls['dp'].setValue(member.get('dp', 100.0))
            style = self.owner.styles[slot]
            picture = self.member_portraits[position]
            if style:
                picture.setPixmap(self.owner.setup.round_pixmap(style.image, 25))
                picture.setToolTip(style.localized_title)
            else:
                picture.clear()
                picture.setText('＋')

    # 负责从调整页读取值到 state_data，也就是说退出调整面板才总体存储一次adjustment
    def save_adjust(self, state_data=None):
        if state_data is None:
            state_data = self.state_data
        base = state_data['base']
        adjust = state_data['adjustments']
        adjust['od'] = self.adjust_od.value()
        base['field'] = self.adjust_field.currentData()
        for position, (down, rate) in enumerate(self.enemy_edits):
            if not self.enemy_presence_checks[position].isChecked():
                base['enemies'][position]["exist"] = False
                continue
            base['enemies'][position]["exist"] = True
            base['enemies'][position].update(down=down.isChecked(), damage_rate=rate.value())
            base['enemies'][position].setdefault('statuses', [])
        for position, controls in enumerate(self.member_edits):
            slot = base['order'][position]
            adjust['members'][slot]['sp'] = controls['sp'].value()
            adjust['members'][slot]['token'] = controls['token'].value()
            base['members'][slot]['dp'] = controls['dp'].value()

    def toggle_mode(self):
        if self.stack.currentIndex() == 0:
            if self.stack.count() == 1:
                self._make_adjust_page()
            self.load_adjust()
            self.stack.setCurrentIndex(1)
            self.refresh_enemy_setting()
        else:
            self.save_adjust()
            self.stack.setCurrentIndex(0)
            self.update_state_from_simulation()
            self.refresh()

    # 根据是否是当前最后一回合来显示回到本回合或者下一回合
    def refresh_turn_controls(self):
        latest = bool(self.owner.turns and self.owner.turns[-1] is self)
        self.next_button.setVisible(latest)
        self.back_button.setVisible(not latest)

    # 从dict找状态图标路径
    def _status_icon(self, status):
        if isinstance(status, dict):
            status_id, element = status.get('id'), status.get('element', "none")
            if element == None:
                element = "none"
        else:
            return None
        entry = self._status_db.get(str(status_id))
        if entry is None:
            return None
        category, not_display = entry.get('category'), entry.get('not_display', False)
        if category == "rule" or not_display:
            return None
        file_name = entry.get('icon') or entry.get('icons', {}).get(element)
        if file_name:
            return ICON_DIR / 'status' / file_name

    def refresh_status_row(self, row, statuses):
        if self._shown_statuses.get(row) == statuses:
            return
        self._shown_statuses[row] = statuses
        items = []
        for status in statuses:
            path = self._status_icon(status)
            if path:
                entry = self._status_db[str(status['id'])]
                name = entry.get('zh_cn') or status.get('name') or entry['name']
                items.append((path, name, status))
        row.set_statuses(items)

    # 敌人弱点和场地的信息显示
    def refresh_enemy_info(self, effective):
        # 弱点
        weaknesses = tuple(effective.get('enemy_weaknesses', []))
        if weaknesses != self._shown_weaknesses:
            self._shown_weaknesses = weaknesses
            weak = self.enemy_weakness_row
            clear_layout(weak)
            weak.addWidget(QLabel('敌人弱点：'))
            for element in weaknesses:
                path = ICON_DIR / 'element' / f'{element}.webp'
                weak.addWidget(icon_label(path, 18, ELEMENT_NAMES.get(element, '?')))
            if not weaknesses:
                weak.addWidget(QLabel('无'))
            weak.addStretch()
        # 敌人具体status信息
        enemies = effective['enemies']
        for enemy, (line, statuses) in zip(enemies, self.enemy_status_rows):
            if line.isHidden() == enemy['exist']:
                line.setVisible(enemy['exist'])
            self.refresh_status_row(statuses, enemy['statuses'])
        # 场地行的信息：场地、域、量表
        field = effective.get('field')
        super_scale = effective['super_scale']
        territory = effective.get("territory")
        field_key = (field, territory, super_scale['element'], super_scale['value'])
        if field_key == self._shown_field:
            return
        self._shown_field = field_key
        clear_layout(self.field_display)
        # 场地信息
        self.field_display.addWidget(QLabel('场：'))
        if field is None:
            self.field_display.addWidget(QLabel('无'))
        elif field == "others": 
            self.field_display.addWidget(QLabel('其他'))
        else:
            icon = 'RiceFieldZone.webp' if field == 'rice_field' else f'{field.capitalize()}Zone.webp'
            self.field_display.addWidget(icon_label(
                ICON_DIR / 'status' / icon, 18, FIELD_NAMES.get(field, '场')))
        self.field_display.addStretch()
        # 域信息和场地放在一起
        if isinstance(territory, int):
            self.field_display.addWidget(QLabel("域：" + TERRITORY_NAMES[territory]))
        self.field_display.addStretch()
        # 超越量表信息和场地放在一起
        if super_scale["element"]:
            element = super_scale["element"]
            path = ICON_DIR / 'element' / f'{element}.webp'
            self.field_display.addWidget(icon_label(path, 18, ELEMENT_NAMES.get(element, '?')))
            self.field_display.addWidget(QLabel('量表：'))
            self.field_display.addWidget(QLabel(f'{super_scale["value"]}'))

    @staticmethod
    def refresh_stylesheet(widget, style):
        if widget.styleSheet() != style:
            widget.setStyleSheet(style)

    def refresh_combo(self, box, options, selected):
        options = tuple(options)
        if box.isHidden() == bool(options):
            box.setVisible(bool(options))
        if not options:
            return
        options_changed = self._combo_options.get(box) != options
        if not options_changed and box.currentData() == selected:
            return
        was_blocked = box.blockSignals(True)
        if options_changed:
            box.clear()
            for label, value in options:
                box.addItem(label, value)
            self._combo_options[box] = options
        box.setCurrentIndex(max(0, box.findData(selected)))
        box.blockSignals(was_blocked)

    def update_turn_height(self):
        # 等敌人行显隐和状态图标的尺寸更新后，再读取布局所需高度
        page = self.stack.widget(0)
        page.layout().activate()
        page_height = page.minimumSizeHint().height()
        border_extra = 2 if self.state_data['base']['additional_turn'] else 0
        height = max(self.HEIGHT, page_height + 8 + border_extra)
        if self.minimumHeight() != height:
            self.setFixedHeight(height)

    def refresh(self):
        # 仅用于显示，直接读取已提交的base
        effective = self.state_data['base']
        additional_turn = effective.get("additional_turn")
        now_timing = effective.get('od_timing')
        bonus = effective.get('bonus')
        # 只有后置od的bonus0时now_od不是od_level而是0
        now_od = 0 if now_timing == "after" and bonus == 0 else effective.get("od_level")
        self.refresh_stylesheet(self, 'QGroupBox#simulationTurn{border:2px solid #dc2626;}' if additional_turn else '')
        od_color = OD_COLORS.get(effective.get('od_level'), 'white') if now_timing and bonus != 0 else 'white'
        self.refresh_stylesheet(self.title, f'font-weight:700;background-color:{od_color};')
        od = effective.get('od'); estimate = effective.get('predicted_od')
        level = max(0, min(3, int(od // 100)))
        # od发动选择框
        # 前置od发动条件是当前刚刚开启前置od，或者当前处于od外的非附加回合中
        available_before = 3 if (now_timing == "before" and bonus == 1 and not additional_turn) or (now_od == 0 and not additional_turn) else 0
        # 后置od发动条件是当前刚刚开启前置od，或者当前处于od外
        available_after = 3 if (now_timing == "before" and bonus == 1 and not additional_turn) or now_od == 0 else 0
        for timing, caption, box, available in (('before', self.before_od_caption, self.before_od, available_before), ('after', self.after_od_caption, self.after_od, available_after)):
            if caption.isHidden() == bool(available):
                caption.setVisible(bool(available))
            # 不做任何检查，只要可以发动od就允许发动任意等级的od
            options = [('不发动', 0)] + [(f'OD{n}', n) for n in range(1, available + 1)] if available else []
            selected_level = effective.get('od_level', 0) if now_timing == timing else 0
            self.refresh_combo(box, options, selected_level)
        # label，bonus由simulation决定
        self.title.setText(f'T{effective.get("turn")}' + 
                           (f"-OD{now_od}" if now_od != 0 else '') +
                           (f"-bonus{bonus}" if bonus != 0 else '') +
                           ('-追加回合' if additional_turn else ''))
        # od
        self.od_label.setText(f'{od:.2f}%')
        self.predicted_od_label.setText(f'→ {estimate:.2f}%')
        self.refresh_stylesheet(self.od_label, f"font-weight:700;color:{'#dc2626' if od < 0 else '#242933'}")
        self.refresh_stylesheet(self.predicted_od_label,
            f"font-weight:700;color:{'#dc2626' if estimate < 0 else '#242933'}")
        if level != self._shown_od_icon:
            self._shown_od_icon = level
            pix = QPixmap(str(ICON_DIR / 'od' / f'od{level}.webp'))
            if pix.isNull():
                self.od_icon.setText(f'OD{level}')
            else:
                self.od_icon.setPixmap(pix.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
        # 敌人
        self.refresh_enemy_info(effective)
        # 队伍
        for position in range(6):
            slot = effective['order'][position]
            member = effective['members'][slot]
            style = self.owner.styles[slot]
            # 按slot修改portrait
            button, portrait = self.portraits[position]
            if not style:
                style_image = None
            elif style.title == "CODE:Virtual Killer":
                style_image = style.image if effective["special_actions"]["kelian_form_change"] == 0 else KELIAN_DIR / '009-2.webp'
            else:
                style_image = style.image
            portrait.configure(style_image if style else None,
                               self.owner.setup.round_pixmap, int(member.get('sp', 0)))
            effect_action = effective['actions'][slot]
            target = effect_action['target'] if effect_action else {}
            target_slot = target.get('slot')
            target_style = self.owner.styles[target_slot] if target_slot is not None and target.get('type') != 'enemy' else None
            target_key = (target.get('type'), target_slot, target_style.image if target_style else None,
                          button.devicePixelRatioF())
            if self._shown_targets.get(position) != target_key:
                self._shown_targets[position] = target_key
                self.target_badges[position].configure(target, self.owner.styles, self.owner.setup.round_pixmap)
            button.setToolTip("左键依次选择两名角色交换；右键设置特殊行动")
            # 按slot修改token和ep
            faith, ep = self.member_resources[position]
            faith.setText(f"信念\n{member['token']}" if position < 3 and member.get('token', 0) > 0 else '')
            ep.setText(f"EP\n{member['ep']}" if position < 3 and member.get('ep', 0) > 0 else '')
            # 按slot修改状态图标
            if position < 3:
                self.refresh_status_row(self.status_rows[position], member.get('statuses', []))
            # 按slot修改可行的所有技能选择
            skills = member.get('skills', [])
            if position < 3:
                options = [(skill['name'], skill['id']) for skill in skills[:1]]
                options.extend((f"{skill['name']}（{skill['cost']} {skill['cost_type']}）", skill['id'])
                               for skill in skills[1:] if skill['id'] not in (0, 3, 4))
            else:  # 后排只显示基础行动
                options = [(skill['name'], skill['id']) for skill in skills if skill['id'] in (0, 3, 4)]
            self.refresh_combo(self.action_boxes[position], options, effect_action['id'] if effect_action else None)
        self.height_timer.start(0)
        if self in self.owner.turns:
            self.refresh_turn_controls()

    def state(self):
        """导出已提交的回合状态，保留独立的 adjustments。"""
        return copy.deepcopy(self.state_data)


class SimulationTab(QWidget):
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setup = BattleSetup(catalog, style_dialog_class, round_pixmap)
        self.styles = [None] * 6  # 主GUI的Style类
        self.status_db = json.loads((SIMULATION_DIR / 'statuses.json').read_text(encoding='utf-8'))
        self.styles_db = json.loads((SIMULATION_DIR / 'styles.json').read_text(encoding='utf-8'))
        self.turns: list[BattleTurn] = []
        self.session = None
        from simulation import Simulation
        self.engine = Simulation()
        outer = QVBoxLayout(self); outer.setContentsMargins(7, 7, 7, 5)
        outer.setSpacing(5)
        toolbar = QHBoxLayout(); toolbar.setSpacing(4)
        for label, handler in (
            ('导入完整模拟数据', self.import_state),
            ('导出完整模拟数据', self.export_state),
            ('从HBRF导入', self.import_hbrf),
            ('导出HBRF', self.export_hbrf),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        self.tips_button = QPushButton('温馨提示')
        self.tips_button.setStyleSheet('' if settings.tips_seen('simulation') else settings.TIPS_STYLE)
        self.tips_button.clicked.connect(self.show_tips)
        toolbar.addStretch(); toolbar.addWidget(self.tips_button)
        outer.addLayout(toolbar)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.container = QWidget(); self.turn_layout = QVBoxLayout(self.container)
        self.turn_layout.setContentsMargins(3, 3, 3, 3)
        self.turn_layout.setSpacing(5)
        self.turn_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 设置面板与回合面板属于同一个滚动容器，不会固定悬浮在顶部。
        self.turn_layout.addWidget(self.setup)
        setup_buttons = QHBoxLayout()
        start = QPushButton('开始战斗'); start.setStyleSheet(BLUE_BUTTON)
        self.apply_setup = QPushButton('应用调整'); self.apply_setup.setStyleSheet(BLUE_BUTTON)
        self.apply_setup.setEnabled(False)

        start.clicked.connect(self.start)
        self.apply_setup.clicked.connect(self.apply_setup_changes)
        setup_buttons.addStretch(); setup_buttons.addWidget(start); setup_buttons.addWidget(self.apply_setup)
        self.turn_layout.addLayout(setup_buttons)
        self.scroll.setWidget(self.container); outer.addWidget(self.scroll)
        self.setStyleSheet(COMPACT +
                        'QGroupBox#simulationTurn{background:white;border:1px solid #dce2eb;'
            'border-radius:9px;margin-top:0;padding:1px}')

    def show_tips(self):
        QMessageBox.information(
            self, '温馨提示',
            '声明\n'
            '为方便排轴，目前不对任何技能和OD使用进行限制（检查OD/SP消耗、技能次数限制、冷却回合等）。\n\n'
            '战斗设定\n'
            '左键选风格，依次右键两个上场角色可交换战斗设定中的位置。再设置技能、突破、饰品、共鸣和敌人信息。'
            '单体默认居中，双体按实际战斗选择位置。'
            '「开始战斗」会创建新战斗，「应用调整」会从首回合重算现有排轴。\n\n'
            '编辑回合\n'
            '从下拉框选择技能和OD发动情况。依次左键两个头像可交换站位，右键点击头像可设置破盾及角色专属特殊行动。'
            '左键点击头像右下角的目标徽章可以重新选择目标。'
            '点击「调整」可修改本回合的资源、DP、敌人和场地，用于一些特殊被动的触发和技能费用计算等。\n\n'
            '查看与推进\n'
            '点击状态栏查看该单位的状态详情。状态较多时，可用横向滚轮或 Shift 加滚轮查看后续状态。'
            '点击「下一回合」结算行动，「回到本回合」会移除之后的回合。\n\n'
            '保存与恢复\n'
            '用「导出模拟数据」保存设定和排轴，再用「导入模拟数据」可以恢复并继续编辑。'
            '「从HBRF导入」会以默认战斗设定重放单队排轴，导入后请检查并调整。\n\n'
            '目前暂未支持\n'
            '我方DP、敌方破坏率、倒地和技能破盾等需要手动填写。受击被动按手动设置的受击次数触发。\n'
            '实际伤害、回复DP等与排轴无关的效果尚未结算。\n'
            '敌方行动、敌方施加的增益和异常状态等尚未自动模拟。部分概率效果默认触发。'
            
        )
        settings.mark_tips_seen('simulation')
        self.tips_button.setStyleSheet('')

    def read_setup(self, warning_title):
        if any(style is None for style in self.setup.styles):
            QMessageBox.warning(self, warning_title, '请先选齐六个风格。'); return
        setup_state = self.setup.state()
        if sum(1 for style in setup_state["styles"] if self.styles_db.get(str(style["style_id"]))["role"] == "admiral") > 1:
            QMessageBox.warning(self, warning_title, '一个队伍只能有一名舰长。'); return
        return setup_state

    def start(self):
        setup_state = self.read_setup('无法开始战斗')
        if setup_state is None:
            return
        engine = type(self.engine)()
        try:
            initialized_turn = engine.first_turn(setup_state)
        except Exception as error:
            QMessageBox.warning(self, '无法开始战斗', str(error)); return
        self.engine = engine
        self.session = {'setup': setup_state}  # 用于存储战斗设置和turn的总体情况
        self.styles = copy.deepcopy(self.setup.styles)
        self.clear_turns()
        self.add_turn_from_simulation(initialized_turn)
        self.apply_setup.setEnabled(True)

    def clear_turns(self):
        for turn in self.turns:
            self.turn_layout.removeWidget(turn)
            turn.hide(); turn.deleteLater()
        self.turns.clear()

    def apply_setup_changes(self):
        if self.session is None:
            return
        setup_state = self.read_setup('无法应用设定修改')
        if setup_state is None:
            return

        # 从新设定的开场快照开始，按原有回合顺序重算
        engine = type(self.engine)()
        states = []
        try:
            engine.first_turn(setup_state)
            special_triggers = {style.special_trigger for style in engine.turns[0].team}
            for turn in self.turns:
                state = copy.deepcopy(turn.state_data)
                if turn.stack.currentIndex() == 1:
                    turn.save_adjust(state)
                gui_add_state = turn.simulation_input(state)

                # 敌人出场位置随新设定继承，保留回合内手动更改的出场配置
                previous = self.engine.turns[turn.number - 1].battle.monsters
                enemies = gui_add_state["enemies"]
                if all(enemy["exist"] == monster.exist for enemy, monster in zip(enemies, previous)):
                    for enemy, monster in zip(enemies, engine.turns[turn.number - 1].battle.monsters):
                        enemy["exist"] = monster.exist

                # 换队后清除已经没有对应角色的专属行动
                for trigger in gui_add_state["special_actions"]:
                    if trigger.removesuffix("_after") not in special_triggers:
                        gui_add_state["special_actions"][trigger] = 0

                state["base"] = engine.recalculate(gui_add_state, turn.number)
                states.append(state)
        except Exception as error:
            QMessageBox.warning(self, '无法应用设定修改', str(error)); return

        # 整条轴都重算成功后再替换已生效的设定和回合数据
        self.engine = engine
        self.session['setup'] = setup_state
        self.styles = copy.deepcopy(self.setup.styles)
        for turn, state in zip(self.turns, states):
            turn.state_data = state
            if turn.stack.currentIndex() == 1:
                turn.load_adjust()
                turn.refresh_enemy_setting()
            turn.refresh()

    # simulation_state 是 simulation.advance() 或 first_turn() 的返回值。
    # 直接使用 simulation_state 构造 BattleTurn，避免重复计算。
    def add_turn_from_simulation(self, simulation_state):
        """
        simulation_state = {
            'members': [{
            'sp': int, 'token': int, "ep": int, 'dp': float, "special_trigger": str | None,
            'statuses': [{
                "id": int, "name": str, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None
            }, ... ],
            "skills": [{"name": str, "cost_type": str, "cost": int, "id": int, "target_type": str, "user_select": None | [str]}, ... ] 
            } for _ in range(6)],
            'order': [int] * 6,
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int, "on_break": False} | None] * 6,
            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool, "statuses": [
            {"id": int, "duration_type": str, "remaining": int, "level": int, "element": str, "source": str | None}, ...
            ]} for _ in range(3)],
            'enemy_weaknesses': [str],
            "super_scale": {"element": None, "value": 0},
            'field': str or None,
            "turn": int,
            'od': float,
            'predicted_od': float,
            'od_timing': str or None,
            'od_level': int,
            'bonus': int,
            'additional_turn': bool,
            "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0} before/after
        }
        """
        turn_config = {"base": simulation_state, "adjustments": {"od": 0.0, "members": [{"sp": 0, "token": 0} for _ in range(6)]}}
        return self.add_turn_from_state(turn_config)

    # 用于从json文件重构战斗状态，直接使用 state 构造 BattleTurn。
    def add_turn_from_state(self, state):
        """
        {"base": simulation_state, 
        "adjustments": {"od": float, "members": [{"sp": int, "token": int} for _ in range(6)]} }
        """
        previous = self.turns[-1] if self.turns else None
        turn = BattleTurn(self, len(self.turns) + 1, state)
        self.turns.append(turn); self.turn_layout.addWidget(turn)
        if previous is not None:
            previous.refresh_turn_controls()
        turn.refresh_turn_controls()
        return turn

    def truncate_after(self, turn):
        if turn not in self.turns: return
        target = self.turns.index(turn) + 1
        for later in self.turns[target:]:
            self.turn_layout.removeWidget(later)
            later.setParent(None); later.deleteLater()
        del self.turns[target:]
        for item in self.turns: item.refresh_turn_controls()
        self.engine.truncate_after(target)

    def sync_from_turn(self, start_turn):
        """
        某一个turn出现调整的时候调用本函数进行后续所有turn的刷新和同步
        gui_add_state = {
            "member_dp": [m["dp"] for m in base["members"]],
            'order': [int] * 6,
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int, "on_break": False}] * 6,
            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool}] * 3,
            'field': str or None,
            'od_timing': str or None,
            'od_level': int,
            "special_actions": {"demonic_rage": 0, "all_out_attack": 0, "demon_cavalry": 0, "kelian_form_change": 0}, before/after
            "adjustments": {xxx},
        }
        """
        start_index = self.turns.index(start_turn)
        # 从某个turn开始调用recalculate
        for i in range(start_index, len(self.turns)):
            turn = self.turns[i]
            result = self.engine.recalculate(
                turn.simulation_input(turn.state_data),
                turn.number
            )
            turn.state_data["base"] = result
        # 全部更新state_data完毕之后刷新显示
        for turn in self.turns[start_index:]:
            turn.refresh()

    def next_turn(self):
        simulation_state = self.engine.advance()
        result = self.add_turn_from_simulation(simulation_state)
        # 不自动滚动到最末，以免跳过需要检查的动作。
        return result

    def state(self):
        if self.session is None: return None
        return {'setup': copy.deepcopy(self.session['setup']),
                'turns': [turn.state() for turn in self.turns]}

    def export_state(self):
        state = self.state()
        if state is None:
            QMessageBox.information(self, '未开始战斗', '请先开始战斗。'); return
        filename, _ = QFileDialog.getSaveFileName(self, '保存模拟状态',
                                                   'simulation_state.json', 'JSON (*.json)')
        if filename:
            Path(filename).write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                      encoding='utf-8')

    def build_hbrf(self):
        from hbrf import model as m

        if not self.turns:
            raise ValueError('请先开始战斗。')
        roles = [m.Role(slot + 1, (style.label or style.name).replace(' ', '').replace('　', ''))
                 for slot, style in enumerate(self.styles)]
        if len({role.name for role in roles}) != 6:
            raise ValueError('HBRF要求六名角色的名称各不相同。')

        # 先收集每名角色用到的技能，同一对切换技能共用一个位置
        skill_names = [
            {self.catalog.skill_data[name]['simulation_id']: name
             for name in self.catalog.skills_for(style)
             if 'simulation_id' in self.catalog.skill_data.get(name, {})}
            for style in self.styles
        ]
        used = [{} for _ in roles]
        pursuit_enabled = [
            self.catalog.is_dark_simei(style) and 728 in entry.get('passive_skill_ids', [])
            for style, entry in zip(self.styles, self.session['setup']['styles'])
        ]
        pursuit = frozenset((m.SIMEI_PURSUIT_SKILL,))
        rows = []
        for turn in self.turns:
            base = turn.state_data['base']
            enemy_count = sum(enemy['exist'] for enemy in base['enemies'])
            moves = []
            for slot in base['order'][:3]:
                action = base['actions'][slot]
                skill_id = action['id'] if action else 0
                skill = None
                target = None
                if skill_id not in (0, 1, 2, 4520001):
                    skill = skill_names[slot].get(skill_id)
                    if skill is None:
                        raise ValueError(f'第{turn.number}张回合卡：{roles[slot].name}的技能 {action["name"]} 无法对应HBRF技能。')
                    linked = self.catalog.linked(self.styles[slot], skill)
                    pair = frozenset((skill, linked)) if linked else frozenset((skill,))
                    if pair not in used[slot]:
                        role = roles[slot]
                        if not (pursuit_enabled[slot] and pair == pursuit):
                            role.skills.append(f'{skill}/{linked}' if linked else skill)
                        used[slot][pair] = (len(role.skills), skill)
                    choice = action['target']
                    if choice['type'] == 'enemy':
                        if enemy_count > 1:
                            target = choice['slot'] + 7
                    elif choice['slot'] is not None:
                        target = choice['slot'] + 1
                    moves.append((slot, skill, pair, target))
                elif skill_id == 1 and enemy_count > 1:
                    target_slot = action['target']['slot']
                    moves.append((slot, None, None, target_slot + 7 if target_slot is not None else None))
                else:
                    moves.append((slot, None, None, None))
            # 使用HBRF编辑器支持的标签，显示标题不参与导出
            if not 1 <= base['turn'] <= 20:
                raise ValueError(f'第{turn.number}张回合卡超出HBRF编辑器支持的T1–T20。')
            label = f"T{base['turn']}"
            timing, level, bonus = base['od_timing'], base['od_level'], base['bonus']
            if timing and level:
                direction = '前置' if timing == 'before' else '后置'
                phase = f'bonus{bonus}' if bonus else 'OD前'
                label += f'-{direction}OD{level}-{phase}'
            if base['additional_turn']:
                label += '-追加'
            rows.append((label, base, moves))

        for slot, role in enumerate(roles):
            if pursuit_enabled[slot]:
                role.skills.append(m.SIMEI_PURSUIT_SKILL)
                used[slot][pursuit] = (len(role.skills), m.SIMEI_PURSUIT_SKILL)

        actions = []
        form = 0
        previous = None
        for label, base, moves in rows:
            special = base['special_actions']
            # 可怜形态在模拟中先切换，其余按钮按结算顺序分别导出前后两段
            for after_pre_od in (False, True):
                suffix = '_after' if after_pre_od else ''
                for trigger, button in (('kelian_form_change', 'kelian'), ('demonic_rage', 'siling')):
                    if trigger == 'kelian_form_change':
                        if after_pre_od:
                            continue
                        count = int(special[trigger] != form)
                        form = special[trigger]
                    else:
                        count = special[trigger + suffix]
                    if count:
                        slot = next((i for i, member in enumerate(base['members'])
                                     if member['special_trigger'] == trigger), None)
                        if slot is None:
                            raise ValueError(f'{label}缺少发动{button}的角色。')
                        position = base['order'].index(slot)
                        actions.extend(m.SpecialRoleButton(slot + 1, position if position < 3 else 0, button, after_pre_od)
                                       for _ in range(count))
                for trigger, button in (('all_out_attack', 'attack'), ('demon_cavalry', 'waki')):
                    actions.extend(m.SpecialGlobalButton(button, after_pre_od)
                                   for _ in range(special[trigger + suffix]))

            turn_moves = []
            for position, (slot, skill, pair, target) in enumerate(moves):
                number = 0
                if pair is not None:
                    number, current = used[slot][pair]
                    if current != skill:
                        actions.append(m.SkillSwitch(slot + 1, number, position))
                        used[slot][pair] = (number, skill)
                turn_moves.append(m.SkillAction(slot + 1, number, target))

            # 只有发动OD的回合写入档位，后续Bonus继续按普通行动执行
            od = 0
            if base['od_timing'] == 'before' and base['bonus'] == 1 and not base['additional_turn']:
                od = -base['od_level']
            elif base['od_timing'] == 'after' and base['bonus'] == 0:
                if not base['additional_turn'] or previous is None or previous['od_timing'] != 'after':
                    od = base['od_level']
            actions.append(m.BattleTurn(label, od, turn_moves))
            previous = base

        script = m.BattleScript(roles, actions)
        m.validate_hbrf(script)
        return script

    def export_hbrf(self):
        from hbrf import model as m

        try:
            script = self.build_hbrf()
            filename, _ = QFileDialog.getSaveFileName(self, '导出 HBRF', 'simulation.hbrf', 'HBRF (*.hbrf)')
            if not filename:
                return
            path = Path(filename)
            if path.suffix.lower() != '.hbrf':
                path = path.with_name(path.name + '.hbrf')
            metadata = [dict(team=style.team, english=style.english, id=style.sid) for style in self.styles]
            m.save_hbrf(script, path, metadata)
        except Exception as error:
            QMessageBox.warning(self, '无法导出 HBRF', str(error))

    def import_hbrf(self):
        from hbrf import model as m

        answer = QMessageBox.question(
            self, '从HBRF导入',
            'HBRF只记录游戏操作，导入时可能丢失共鸣、资源调整、随机分支和破盾等信息。'
            '回合和状态会按模拟规则重算，请在导入后手动检查和调整。\n\n是否继续？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        filename, _ = QFileDialog.getOpenFileName(self, '从HBRF导入', str(SCRIPTS_DIR), 'HBRF (*.hbrf)')
        if not filename:
            return
        try:
            script = m.load_hbrf(filename)
            if len(script.roles) != 6:
                raise ValueError('战斗模拟只支持单队HBRF。')
            styles = self.hbrf_styles(script.roles, m.load_style_metadata(filename))
            if styles is not None:
                self.import_state(self.hbrf_to_state(script, styles), inherit_battle=True)
        except Exception as error:
            QMessageBox.warning(self, '无法从HBRF导入', str(error))

    def hbrf_styles(self, roles, metadata):
        styles = []
        occupied = set()
        for role in roles:
            note = metadata.get(role.slot, {})
            style = self.catalog.find_style(note.get('team'), note.get('english'), note.get('id'))
            if style is None:
                names = {name for entry in role.skills for name in entry.split('/')}
                candidates = [style for style in self.catalog.styles
                              if style.name not in occupied
                              and role.name in (style.name, style.label.replace(' ', '').replace('　', ''))
                              and names.issubset(self.catalog.skills_for(style))]
                if len(candidates) == 1:
                    style = candidates[0]
                else:
                    dialog = self.setup.style_dialog_class(self.catalog, occupied, self)
                    dialog.setWindowTitle(f'为HBRF角色「{role.name}」选择风格')
                    if dialog.exec() != QDialog.DialogCode.Accepted:
                        return None
                    style = dialog.chosen
            if style.name in occupied:
                raise ValueError(f'同一角色重复上场：{style.name}')
            occupied.add(style.name)
            styles.append(style)
        return styles

    def hbrf_to_state(self, script, styles):
        from hbrf import model as m
        from simulation import Skill, json_records_to_dict

        # 从显式指定的敌人位置还原出场配置，没有指定时默认单体居中
        enemy_slots = sorted({move.target - 7 for turn in script.actions if isinstance(turn, m.BattleTurn)
                              for move in turn.actions if move.target in (7, 8, 9)}) or list(DEFAULT_ENEMY_SLOTS[1])
        setup = {
            'styles': [], 'resonances': [None] * 6,
            'enemy_count': len(enemy_slots), 'enemy_slots': enemy_slots,
            'enemy_weaknesses': [value for _, value in ELEMENTS[1:]],
            'initial_od': 0.0, 'global_od_rate': 100,
        }
        records = json_records_to_dict(self.engine.skills_path)
        role_skills = []
        for role, style in zip(script.roles, styles):
            style_id = self.setup._style_id(style)
            entries = []
            active_ids, orb_ids = [], []
            for entry in role.skills:
                variants = []
                for name in entry.split('/'):
                    skill_id = self.catalog.skill_data.get(name, {}).get('simulation_id')
                    if skill_id is None or name not in self.catalog.skills_for(style):
                        raise ValueError(f'{role.name}的技能「{name}」无法匹配所选风格。')
                    skill_id = int(skill_id)
                    variants.append(Skill.from_record(records[skill_id]))
                    (orb_ids if name in self.catalog.common_global else active_ids).append(skill_id)
                entries.append(variants)
            # 暗四妹的技能栏含打靶时，还原配套的追击被动
            passive_ids = [int(entry['simulation_id']) for _, entry in SkillSelectionDialog._get_passives(style)]
            if style_id == 266 and 737 not in active_ids:
                passive_ids = [skill_id for skill_id in passive_ids if skill_id != 728]
            role_skills.append(entries)
            setup['styles'].append({
                'style_id': style_id,
                'break_level': self.setup._default_level(style),
                'od_earring': 15, 'necklace_sp': 3,
                'active_skill_ids': list(dict.fromkeys(active_ids)),
                'orb_skill_ids': list(dict.fromkeys(orb_ids)),
                'passive_skill_ids': passive_ids,
            })

        # 按执行器的交换顺序更新站位，切换技能从文件头的第一项开始
        order = list(range(6))
        selected = [[0] * len(entries) for entries in role_skills]
        special = {key: 0 for key in SpecialActionDialog.SPECIAL_NAMES}
        special.update({key + '_after': 0 for key in SpecialActionDialog.SPECIAL_NAMES
                        if key != 'kelian_form_change'})
        states = []
        positions_after_od = []
        for entry in script.actions:
            if isinstance(entry, (m.SkillSwitch, m.SpecialRoleButton)):
                slot = entry.role - 1
                if isinstance(entry, m.SpecialRoleButton) and entry.after_pre_od:
                    positions_after_od.append((slot, entry.position))
                else:
                    index = order.index(slot)
                    order[index], order[entry.position] = order[entry.position], order[index]
                if isinstance(entry, m.SkillSwitch):
                    index = entry.skill - 1
                    if len(role_skills[slot][index]) < 2:
                        raise ValueError(f'{script.roles[slot].name}的第{entry.skill}个技能没有切换版本。')
                    selected[slot][index] ^= 1
                elif entry.button == 'kelian':
                    special['kelian_form_change'] ^= 1
                elif entry.button == 'siling':
                    special['demonic_rage_after' if entry.after_pre_od else 'demonic_rage'] += 1
            elif isinstance(entry, m.SpecialGlobalButton):
                trigger = {'waki': 'demon_cavalry', 'attack': 'all_out_attack'}[entry.button]
                special[trigger + ('_after' if entry.after_pre_od else '')] += 1
            elif isinstance(entry, m.BattleTurn):
                for slot, position in positions_after_od:
                    index = order.index(slot)
                    order[index], order[position] = order[position], order[index]
                positions_after_od.clear()
                actions = [None] * 6  # 后排及技能编号0交给引擎补默认行动
                for position, move in enumerate(entry.actions):
                    slot = move.role - 1
                    index = order.index(slot)
                    order[index], order[position] = order[position], order[index]
                for move in entry.actions:
                    slot = move.role - 1
                    if not move.skill:
                        if move.target in (7, 8, 9):
                            actions[slot] = {'id': 1, 'name': '普通攻击', 'user_selected': None,
                                             'target': {'type': 'enemy', 'slot': move.target - 7},
                                             'on_break': False, 'be_attacked_times': 0}
                        continue
                    skill = role_skills[slot][move.skill - 1][selected[slot][move.skill - 1]]
                    if setup['styles'][slot]['style_id'] == 266 and skill.id == 737:
                        continue  # 该技能只通过后排自动追击发动
                    actions[slot] = self.hbrf_skill_action(skill, move.target, slot, order, enemy_slots)
                states.append({
                    'base': {
                        'order': order.copy(), 'actions': actions,
                        'od_timing': 'before' if entry.od < 0 else 'after' if entry.od > 0 else None,
                        'od_level': abs(entry.od), 'special_actions': special.copy(),
                    },
                    'adjustments': {'od': 0, 'members': [{'sp': 0, 'token': 0} for _ in range(6)]},
                })
                # 每个战斗回合用完后清零按钮次数，可怜形态继续继承
                for key in special:
                    if key != 'kelian_form_change':
                        special[key] = 0
        return {'setup': setup, 'turns': states}

    @staticmethod
    def hbrf_skill_action(skill, target, slot, order, enemy_slots):
        kind = skill.selection_target_type()
        target_slot = None
        if kind == 'enemy':
            target_slot = target - 7 if target in (7, 8, 9) else enemy_slots[0]
        elif kind != 'ignore':
            candidates = order[:3] if kind == 'ally_single_front_without_self' else order
            if kind != 'ally_single':
                candidates = [candidate for candidate in candidates if candidate != slot]
            target_slot = target - 1 if target in range(1, 7) and target - 1 in candidates else candidates[0]
        # HBRF不记录随机分支和破盾结果，分支取数据库中的第一项
        return {
            'id': skill.id, 'name': skill.names['zh_cn'], 'on_break': False,
            'target': {'type': kind, 'slot': target_slot},
            'user_selected': int(next(iter(skill.user_select))) if skill.user_select else None,
        }

    def import_state(self, data=None, *, inherit_battle=False):
        # QPushButton.clicked传入的布尔值不代表存档
        if not isinstance(data, dict):
            filename, _ = QFileDialog.getOpenFileName(self, '导入模拟数据', '', 'JSON (*.json)')
            if not filename:
                return
            try:
                data = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
            except Exception as error:
                QMessageBox.warning(self, '无法导入模拟数据', str(error)); return
        try:
            self.restore_state(data, inherit_battle=inherit_battle)
        except Exception as error:
            title = '无法从HBRF导入' if inherit_battle else '无法导入模拟数据'
            QMessageBox.warning(self, title, str(error))

    def restore_state(self, data, *, inherit_battle=False):
        setup = data['setup']
        states = data['turns']
        if not isinstance(states, list) or not states:
            raise ValueError('模拟数据至少需要一个回合。')

        # 重建引擎的开场快照，再逐回合应用存档里的行动和手动调整
        engine = type(self.engine)()
        initial = engine.first_turn(setup)
        styles = self.setup.resolve_styles(setup)
        self.setup.check_saved_setup(setup, styles)
        restored = []
        for number, state in enumerate(states, 1):
            try:
                if inherit_battle:
                    state = {'base': {**initial, **state['base']}, 'adjustments': state['adjustments']}
                gui_add_state = BattleTurn.simulation_input(state)
                order = gui_add_state['order']
                if any(type(slot) is not int for slot in order) or sorted(order) != list(range(6)):
                    raise ValueError('站位必须包含六个不同的队伍位置。')
                if len(gui_add_state['actions']) != 6 or len(gui_add_state['member_dp']) != 6 or \
                   len(gui_add_state['enemies']) != 3 or len(gui_add_state['adjustments']['members']) != 6:
                    raise ValueError('角色、行动或敌人数量无效。')
                if not any(enemy['exist'] for enemy in gui_add_state['enemies']):
                    raise ValueError('每个回合至少需要一名敌人存在。')
                for action in gui_add_state['actions']:
                    if action is None:
                        continue
                    target = action['target']
                    slot = target['slot']
                    kind = target['type']
                    if kind == 'ignore' and slot is None:
                        continue
                    if kind not in ('enemy', 'ally_single', 'ally_single_without_self', 'ally_single_front_without_self') or \
                       type(slot) is not int or slot not in range(3 if kind == 'enemy' else 6):
                        raise ValueError('行动目标格式无效。')
                base = engine.recalculate(copy.deepcopy(gui_add_state), number, inherit_battle=inherit_battle)
                restored.append({'base': base, 'adjustments': state['adjustments']})
            except Exception as error:
                raise ValueError(f'第 {number} 个回合无法恢复：{error}') from error

        # 全部回合重放成功后再替换当前战斗
        self.setup.restore_state(setup, styles)
        self.engine = engine
        self.session = {'setup': copy.deepcopy(setup)}
        self.styles = copy.deepcopy(self.setup.styles)
        self.clear_turns()
        for state in restored:
            self.add_turn_from_state(state)
        self.apply_setup.setEnabled(True)
