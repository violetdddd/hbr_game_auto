"""战斗模拟 Tab。仅负责界面、状态快照与手动修正；实际结算由 engine.advance 提供。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QTabWidget, QScrollArea,
    QGroupBox, QStackedWidget, QMessageBox, QFileDialog, QSizePolicy, QFrame,
    QComboBox,
)

from paths import ROOT_DIR
SIMULATION_DIR = ROOT_DIR / 'assets' / 'simulation'

ELEMENTS = [('无', None), ('火', 'fire'), ('冰', 'ice'), ('雷', 'thunder'), ('光', 'light'), ('暗', 'dark')]
FIELD_OPTIONS = [('无', None), ('稻场', 'rice_field'), ('火场', 'fire'), ('冰场', 'ice'),
                 ('雷场', 'thunder'), ('光场', 'light'), ('暗场', 'dark')]
ELEMENT_NAMES = dict((value, label) for label, value in ELEMENTS)
FIELD_NAMES = dict((value, label) for label, value in FIELD_OPTIONS)
BLUE_BUTTON = ('QPushButton{background:#2563eb;color:white;border:1px solid #1d4ed8;'
               'border-radius:7px;padding:3px 9px;font-weight:600}'
               'QPushButton:hover{background:#1d4ed8}'
               'QPushButton:disabled{background:#cbd5e1;border-color:#cbd5e1}')
WHITE_BUTTON = ('QPushButton{padding:2px 5px;min-height:0px;}')
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
def icon_label(path, size=23, fallback=''):
    label = QLabel(); label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        label.setPixmap(pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
    else:
        label.setText(fallback)
        label.setToolTip(f'图片不存在：{path}')
    return label

# 清理一整个layout
def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())

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

    @staticmethod
    def catalog_data_path(style):
        return ROOT_DIR / 'assets' / 'char-data' / (style.team + '.json')

    def _get_passives(self, style):
        path = self.catalog_data_path(style)
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
                style = owner.setup.styles[slot]
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

class BattleSetup(QGroupBox):
    """固定高度，敌人初始数据、六名上场风格及独立的共鸣风格。"""
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__('战斗设置', parent)
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
        self.enemy_count = combo([(str(n), n) for n in range(1, 4)])
        enemy_col.addWidget(self.enemy_count)

        enemy_col.addWidget(QLabel('敌人弱点'))
        self.enemy_weaknesses = []
        weakness_button = QPushButton('设置弱点')
        weakness_button.setStyleSheet(BLUE_BUTTON)
        weakness_button.clicked.connect(self.choose_weaknesses)
        self.weakness_button = weakness_button
        enemy_col.addWidget(weakness_button)

        od_rate_line = QHBoxLayout()
        od_rate_line.addWidget(QLabel('OD率 '))
        self.global_od_rate = dspin(0, 999, 100); self.global_od_rate.setMaximumWidth(90)
        self.global_od_rate.setSuffix('%')
        od_rate_line.addWidget(self.global_od_rate, 1)
        enemy_col.addLayout(od_rate_line)

        initial_od_line = QHBoxLayout()
        initial_od_line.addWidget(QLabel('开局OD'))
        self.initial_od = dspin(0, 300, 0); self.initial_od.setMaximumWidth(90)
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
        self.breaks, self.earrings, self.necklaces, self.skill_buttons, self.resonance_breaks = [], [], [], [], []
        for i in range(6):
            avatars = QWidget(); av = QHBoxLayout(avatars)
            av.setContentsMargins(0, 0, 0, 0); av.setSpacing(3)
            av.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            avatar = QPushButton('＋'); avatar.setFixedSize(61, 61)
            avatar.clicked.connect(lambda _=False, index=i: self.choose_style(index))
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
            self.enemy_weaknesses = dialog.values()
            names = '、'.join(ELEMENT_NAMES[x] for x in self.enemy_weaknesses) or '无'
            self.weakness_button.setText('弱点：' + names)
            self.weakness_button.setToolTip(names)

    @staticmethod
    def _set_level(box, style):
        maximum = {'A': 20, 'S': 10, 'SS': 4, 'SSR': 4}.get(style.tier, 4) if style else 4
        box.clear()
        for n in range(maximum + 1):
            box.addItem(str(n), n)
        box.setCurrentIndex(maximum if style and style.tier in ('A', 'S') else min(2, maximum))

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
            'passive': [],
            'orb': []
        }
        self._set_avatar(index)
        self._set_level(self.breaks[index], selected)

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

    def reset(self):
        self.styles = [None]*6; self.resonances = [None]*6
        self.skill_selections = [{'active': [], 'passive': [], 'orb': []} for _ in range(6)]
        self.enemy_count.setCurrentIndex(0); self.initial_od.setValue(0); self.global_od_rate.setValue(100)
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
            'enemy_weaknesses': list(self.enemy_weaknesses),
            'initial_od': float(self.initial_od.value()),
            'global_od_rate': float(self.global_od_rate.value()),
        }

    @staticmethod
    def _style_id(style):
        if style is None: return None
        path = SkillSelectionDialog.catalog_data_path(style)
        if not path.exists(): raise FileNotFoundError(f'找不到风格数据库：{path}')
        data = json.loads(path.read_text(encoding='utf-8'))
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
        self.sp = 0
        self.size = size

    def configure(self, path, round_pixmap, sp):
        self.picture = round_pixmap(path, self.size) if path else QPixmap()
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

class TargetBadge(QWidget):
    """头像右下角的技能目标标记。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(25, 25)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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
        self.select_first = None
        self.setObjectName('simulationTurn')
        self.setFixedHeight(self.HEIGHT)
        outer = QVBoxLayout(self); outer.setContentsMargins(4, 3, 4, 3)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self._make_combat_page(); self._make_adjust_page()
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
        el = QVBoxLayout(enemy); el.setContentsMargins(4, 1, 4, 1); el.setSpacing(0)
        self.title = QLabel(); self.title.setStyleSheet('font-weight:700;')
        el.addWidget(self.title)
        self.enemy_icons_row = QVBoxLayout(); self.enemy_icons_row.setSpacing(0)
        el.addLayout(self.enemy_icons_row)
        self.field_display = QHBoxLayout(); self.field_display.setSpacing(1)
        el.addLayout(self.field_display)
        el.addStretch()
        root.addWidget(enemy, 20)
        root.addWidget(self._separator())

        team = QWidget()
        tl = QHBoxLayout(team); tl.setContentsMargins(3, 1, 3, 1); tl.setSpacing(3)
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
                badge.move(31, 29)
                avatar.clicked.connect(lambda _=False, pos=position: self.swap_position(pos))
                # 顺序为：信念、头像、ep
                body.addWidget(token)
                body.addWidget(avatar)
                body.addWidget(ep)
                col.addLayout(body)
                # 三者下方的statuses
                statuses = QHBoxLayout()
                statuses.setSpacing(1)
                statuses.setAlignment(Qt.AlignmentFlag.AlignLeft)
                col.addLayout(statuses)
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
        od_values.addWidget(self.od_label)
        od_values.addWidget(self.predicted_od_label)
        top.addLayout(od_values); top.addStretch()
        ol.addLayout(top)
        # od发动选择区
        self.before_od = combo([('不发动', 0)])
        self.after_od = combo([('不发动', 0)])
        for title, box in (('前置', self.before_od), ('后置', self.after_od)):
            row = QHBoxLayout()
            row.setSpacing(2)
            caption = QLabel(title)
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
        self.next_button.clicked.connect(lambda: self.owner.next_turn(self))
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
        for position, title in enumerate(('三体左', '单体中', '双体右')):
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

    def update_state_from_simulation(self):
        """
        GUI传给engine可操作的base相关内容，engine内部增量更新，然后传回来完整的base state
        gui_add_state = {
            'order': [int] * 6,
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int}] * 6,
            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool, "statuses": [
            {"id": int, "duration_type": str, "remaining": int, "level": int, "element": str}, ...
            ]} for _ in range(3)],
            'field': str or None,
            'od_timing': str or None,
            'od_level': int
        }
        """
        base = self.state_data["base"]
        gui_add_state = {
            'order': base["order"],
            'actions': base["actions"],
            'enemies': base["enemies"],
            'field': base["field"],
            'od_timing': base["od_timing"],
            'od_level': base["od_level"]
        }
        simulation_state = copy.deepcopy(self.owner.engine.recalculate(copy.deepcopy(gui_add_state)))
        for need_update in ("members", "od", "predicted_od", "bonus"):
            base[need_update] = simulation_state[need_update]

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
        target_type = skill.get('target_type', 'ignore')
        old_action = base['actions'][slot]
        target_slot = None
        user_selected = None
        target_selected = False
        # 单体敌人或ignore的情况，不要弹出选择框
        if target_type == "ignore":
            target_selected = True
        elif target_type == 'enemy':
            enemies = [i for i, enemy in enumerate(base['enemies']) if enemy['exist']]
            if len(enemies) == 1:
                target_slot = enemies[0]
                target_selected = True
        # 敌人多体和我方角色，弹出选择框
        if not target_selected:
            dialog = TargetSelectionDialog(
                self.owner, target_type, slot, base, self
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                target_slot = dialog.selected_slot
            else:
                self.restore_action(position, old_action)
                return
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
            'target': {
                'type': target_type,
                'slot': target_slot
            },
            'user_selected': user_selected
        }

        # self.update_state_from_simulation()
        # 刷新显示
        self.refresh()

    # 用户取消选择时调用，用于恢复上一个选择的技能
    def restore_action(self, position, old_action):
        box = self.action_boxes[position]

        box.blockSignals(True)
        box.setCurrentIndex(box.findData(old_action['id']))
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

        # self.update_state_from_simulation()
        self.refresh()

    def swap_position(self, position):
        if self.select_first is None:
            self.select_first = position
            self.portraits[position][0].setStyleSheet(
                'QPushButton{border:2px solid #2563eb;background:#dbeafe}')  # 选中样式
            return
        first, second, self.select_first = self.select_first, position, None
        self.portraits[first][0].setStyleSheet(
            'QPushButton{background:transparent;border:0;padding:0}')  # 还原普通样式
        if first == second or (first >= 3 and second >= 3):  # 后排交换不允许
            return
        base = self.state_data['base']
        # 队伍state顺序交换
        base['order'][first], base['order'][second] = base['order'][second], base['order'][first]
        # 前后排交换技能重新安排
        if (first < 3) != (second < 3):
            for position in (first, second):
                slot = base['order'][position]
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
                    'user_selected': None
                }

        # self.update_state_from_simulation()
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
            style = self.owner.setup.styles[slot]
            picture = self.member_portraits[position]
            if style:
                picture.setPixmap(self.owner.setup.round_pixmap(style.image, 25))
                picture.setToolTip(style.localized_title)
            else:
                picture.clear()
                picture.setText('＋')

    # 负责从调整页读取值到 state_data，也就是说退出调整面板才总体存储一次adjustment
    def save_adjust(self):
        base = self.state_data['base']
        adjust = self.state_data['adjustments']
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

        # 判断目标是否改变，如改变则给出提示框
        checks = self.enemy_presence_checks
        re_target_actions = []
        new_target = next(i for i, check in enumerate(checks) if check.isChecked())
        for action in self.state_data["base"]["actions"]:
            target = action["target"]
            if target["type"] == "enemy" and not checks[target["slot"]].isChecked():  # 如果有目标type，那么不应该出现slot为None的情况
                target["slot"] = new_target
                re_target_actions.append(action["name"])
        if re_target_actions:
            warning = "、".join(re_target_actions)
            QMessageBox.warning(self,"技能目标调整",f"敌人配置发生变化，以下技能已自动调整目标：{warning}")

    def toggle_mode(self):
        if self.stack.currentIndex() == 0:
            self.load_adjust()
            self.stack.setCurrentIndex(1)
            self.refresh_enemy_setting()
        else:
            self.save_adjust()
            self.stack.setCurrentIndex(0)
            # self.update_state_from_simulation()
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
        else:
            return None
        entry = self._status_db.get(str(status_id))
        if entry is None:
            return None
        category, not_display = entry.get('category'), entry.get('not_display', False)
        if category == "rule" or not_display:
            return None
        file_name = (entry.get('icon') or entry.get('icons').get(element))
        path = ROOT_DIR / 'assets' / 'icons' / 'status' / file_name

        return path

    # 敌人弱点和场地的信息显示
    def refresh_enemy_info(self, effective):
        clear_layout(self.enemy_icons_row)
        # 弱点
        weak = QHBoxLayout()
        weak.setSpacing(1)
        weak.addWidget(QLabel('敌人弱点：'))
        for element in effective.get('enemy_weaknesses', []):
            path = ROOT_DIR / 'assets' / 'icons' / 'element' / f'{element}.webp'
            weak.addWidget(icon_label(path, 15, ELEMENT_NAMES.get(element, '?')))
        if len(effective.get('enemy_weaknesses', [])) == 0:
            weak.addWidget(QLabel('无'))
        weak.addStretch()
        # 敌人具体status信息
        self.enemy_icons_row.addLayout(weak)
        enemies = effective['enemies']
        for position, label in enumerate(('左侧敌人：', '中间敌人：', '右侧敌人：')):
            if enemies[position].get('exist') is not True:
                continue
            line = QHBoxLayout()
            line.setSpacing(1)
            line.addWidget(QLabel(label))
            for status in enemies[position].get('statuses', []):
                path = self._status_icon(status)
                if path:
                    line.addWidget(icon_label(path, 15))
            line.addStretch()
            self.enemy_icons_row.addLayout(line)
        # 场地信息
        clear_layout(self.field_display)
        self.field_display.addWidget(QLabel('场地：'))
        field = effective.get('field')
        if field is None:
            self.field_display.addWidget(QLabel('无'))
        else:
            icon = 'RiceFieldZone.webp' if field == 'rice_field' else f'{field.capitalize()}Zone.webp'
            self.field_display.addWidget(icon_label(
                ROOT_DIR / 'assets' / 'icons' / 'status' / icon, 15, FIELD_NAMES.get(field, '场')))
        self.field_display.addStretch()

    def effective_state(self):
        """只读输出；base 中 members 恒按 slot 0–5 排列。"""
        effective = copy.deepcopy(self.state_data['base'])
        adjustments = self.state_data['adjustments']
        effective['od'] = effective.get('od', 0.0) + adjustments.get('od', 0.0)
        for slot, member in enumerate(effective['members']):
            delta = adjustments['members'][slot]
            for key in ('sp', 'token'):
                member[key] = int(member.get(key, 0)) + int(delta.get(key, 0))
        return effective

    def refresh(self):
        effective = self.effective_state()
        now_timing = effective.get('od_timing')
        now_od = effective.get('od_level') if now_timing == "before" else 0
        # label，bonus由simulation决定
        self.title.setText(f'T{effective.get("turn")}' + 
                           (f"-OD{now_od}" if now_od != 0 else '') +
                           (f"-bonus{effective.get('bonus')}" if effective.get('bonus') != 0 else '') +
                           ('-追加回合' if effective.get('additional_turn') else ''))
        # od
        od = effective.get('od')
        self.od_label.setText(f'{od:.2f}%')
        estimate = effective.get('predicted_od')
        self.predicted_od_label.setText(f'→ {estimate:.2f}%')
        self.od_label.setStyleSheet(f"font-weight:700;color:{'#dc2626' if od < 0 else '#242933'}")
        self.predicted_od_label.setStyleSheet(
            f"font-weight:700;color:{'#dc2626' if estimate < 0 else '#242933'}")
        level = max(0, min(3, int(od // 100)))
        pix = QPixmap(str(ROOT_DIR / 'assets' / 'icons' / 'od' / f'od{level}.webp'))
        if pix.isNull():
            self.od_icon.setText(f'OD{level}')
        else:
            self.od_icon.setPixmap(pix.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
        # od发动选择框
        available = level if now_od == 0 or now_timing == "before" else 0
        for timing, box in (('before', self.before_od), ('after', self.after_od)):
            box.blockSignals(True)
            box.clear()
            box.addItem('不发动', 0)
            for n in range(1, available + 1):
                box.addItem(f'OD{n}', n)
            box.setCurrentIndex(max(0, box.findData(
                effective.get('od_level', 0) if now_timing == timing else 0)))
            box.blockSignals(False)
        # 敌人
        self.refresh_enemy_info(effective)
        # 队伍
        for position in range(6):
            slot = effective['order'][position]
            member = effective['members'][slot]
            style = self.owner.setup.styles[slot]
            # 按slot修改portrait
            button, portrait = self.portraits[position]
            portrait.configure(style.image if style else None,
                               self.owner.setup.round_pixmap, int(member.get('sp', 0)))
            target = effective['actions'][slot]['target']
            self.target_badges[position].configure(target, self.owner.setup.styles, self.owner.setup.round_pixmap)
            button.setToolTip((style.localized_title if style else f'角色{slot+1}') +
                              '（点击两名角色头像交换位置）')
            # 按slot修改token和ep
            faith, ep = self.member_resources[position]
            faith.setText(f"信念\n{member['token']}" if position < 3 and member.get('token', 0) > 0 else '')
            ep.setText(f"EP\n{member['ep']}" if position < 3 and member.get('ep', 0) > 0 else '')
            # 按slot修改状态图标
            clear_layout(self.status_rows[position])
            for status in member.get('statuses', []):
                path = self._status_icon(status)
                if path:
                    self.status_rows[position].addWidget(icon_label(path, 15))
            # 按slot修改可行的所有技能选择
            action = self.action_boxes[position]
            skiills = member.get('skills', [])
            action.blockSignals(True)
            action.clear()
            if len(skiills) == 0:
                action.setVisible(False)
            else: 
                action.setVisible(True)
                if position < 3:
                    for i, skill in enumerate(member.get('skills', [])):
                        if i not in (1, 2):
                            action.addItem(f"{skill.get('name')}（{skill.get('cost')} {skill.get('cost_type')}）", skill.get('id'))
                else:
                    for skill in member.get('skills')[1:3]:
                        action.addItem(f"{skill.get('name')}", skill.get('id'))
                # 按当前技能选择安排动作
                original = effective['actions'][slot]
                idx = action.findData(original["id"])
                action.setCurrentIndex(idx if idx >= 0 else 0)
            action.blockSignals(False)
        if self in self.owner.turns:
            self.refresh_turn_controls()

    def state(self):
        """导出用于 JSON 恢复的完整状态；不合并 adjustments。"""
        if self.stack.currentIndex() == 1:
            self.save_adjust()

        return copy.deepcopy(self.state_data)


class SimulationTab(QWidget):
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setup = BattleSetup(catalog, style_dialog_class, round_pixmap)
        self.status_db = json.loads((SIMULATION_DIR / 'statuses.json').read_text(encoding='utf-8'))
        self.styles_db = json.loads((SIMULATION_DIR / 'styles.json').read_text(encoding='utf-8'))
        self.turns = []; self.session = None
        from simulation import Simulation
        self.engine = Simulation()
        outer = QVBoxLayout(self); outer.setContentsMargins(7, 7, 7, 5)
        outer.setSpacing(5)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.container = QWidget(); self.turn_layout = QVBoxLayout(self.container)
        self.turn_layout.setContentsMargins(3, 3, 3, 3)
        self.turn_layout.setSpacing(5)
        self.turn_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 设置面板与回合面板属于同一个滚动容器，不会固定悬浮在顶部。
        self.turn_layout.addWidget(self.setup)
        toolbar = QHBoxLayout()
        start = QPushButton('开始战斗'); start.setStyleSheet(BLUE_BUTTON)
        start.clicked.connect(self.start)
        export = QPushButton('导出模拟数据')
        export.clicked.connect(self.export_state)
        toolbar.addStretch(); toolbar.addWidget(start); toolbar.addWidget(export)
        self.turn_layout.addLayout(toolbar)
        self.scroll.setWidget(self.container); outer.addWidget(self.scroll)
        self.setStyleSheet(COMPACT +
                        'QGroupBox#simulationTurn{background:white;border:1px solid #dce2eb;'
            'border-radius:9px;margin-top:0;padding:1px}')

    def start(self):
        if any(style is None for style in self.setup.styles):
            QMessageBox.warning(self, '无法开始战斗', '请先选齐六个风格。'); return
        setup_state = self.setup.state()
        if sum(1 for style in setup_state["styles"] if self.styles_db.get(str(style["style_id"]))["role"] == "admiral") > 1:
            QMessageBox.warning(self, '无法开始战斗', '一个队伍只能有一名舰长。'); return
        self.session = {'setup': setup_state}  # 用于存储战斗设置和turn的总体情况
        # 清除旧回合
        for turn in self.turns:
            self.turn_layout.removeWidget(turn); turn.deleteLater()
        self.turns.clear()
        # 初始化战斗
        initialized_turn = self.engine.first_turn(
            copy.deepcopy(setup_state)
        )
        self.add_turn_from_simulation(initialized_turn)

    # simulation_state 是 simulation.advance() 或 first_turn() 的返回值。
    # 直接使用 simulation_state 构造 BattleTurn，避免重复计算。
    def add_turn_from_simulation(self, simulation_state):
        """
        simulation_state = {
            'members': [{
            'sp': int, 'token': int, "ep": int, 'dp': float,
            'statuses': [{
                "id": int, "duration_type": str, "remaining": int, "level": int, "element": str
            }, ... ],
            "skills": [{"name": str, "cost_type": str, "cost": int, "id": int, "target_type": str, "user_select": None | [str]}, ... ] 
            } for _ in range(6)],
            'order': [int] * 6,
            'actions': [{"name": str, "id": int, "target": {"type": str, "slot": int | None}, "user_selected": None | int}] * 6,

            'enemies': [{"exist": bool, "damage_rate": int, 'down': bool, "statuses": [
            {"id": int, "duration_type": str, "remaining": int, "level": int, "element": str}, ...
            ]} for _ in range(3)],
            'enemy_weaknesses': [str],

            'field': str or None,
            "turn": int,
            'od': float,
            'predicted_od': float,
            'od_timing': str or None,
            'od_level': int,
            'bonus': int,
            'additional_turn': bool
        }
        """
        turn_config = {"base": simulation_state, "adjustments": {"od": 0.0, "members": [{"sp": 0, "token": 0} for _ in range(6)]}}
        turn = BattleTurn(self, len(self.turns) + 1, turn_config)
        self.turns.append(turn); self.turn_layout.addWidget(turn)
        for item in self.turns: item.refresh_turn_controls()
        return turn

    # 用于从json文件重构战斗状态，直接使用 state 构造 BattleTurn。
    def add_turn_from_state(self, state):
        """
        {"base": simulation_state, 
        "adjustments": {"od": float, "members": [{"sp": int, "token": int} for _ in range(6)]} }
        """
        turn = BattleTurn(self, len(self.turns) + 1, state)
        self.turns.append(turn); self.turn_layout.addWidget(turn)
        for item in self.turns: item.refresh_turn_controls()
        return turn

    def truncate_after(self, turn):
        if turn not in self.turns: return
        target = self.turns.index(turn) + 1
        for later in self.turns[target:]:
            self.turn_layout.removeWidget(later)
            later.setParent(None); later.deleteLater()
        del self.turns[target:]
        for item in self.turns: item.refresh_turn_controls()

    def next_turn(self, turn):
        last_state = copy.deepcopy(turn.effective_state())
        simulation_state = self.engine.advance(last_state)
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
