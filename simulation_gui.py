
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

# 调整面板默认值
def initial_adjustments():
    return {'od': 0.0, 'members': [{'sp': 0, 'token': 0} for _ in range(6)]}


def ensure_state(source):
    """兼容先前测试快照，保持基准值与手动增减完全分离。"""
    data = copy.deepcopy(source)
    if 'base' not in data:
        data['base'] = {
            'od': float(data.pop('od', 0)),
            'members': copy.deepcopy(data.pop('members', [])),
        }
    base = data['base']
    base.setdefault('od', 0.0)
    base.setdefault('members', [])
    while len(base['members']) < 6:
        base['members'].append({'sp': 0, 'token': 0, 'dp': 100.0, 'statuses': []})
    for member in base['members']:
        member.setdefault('sp', 0); member.setdefault('token', 0)
        member.pop('ep', None); member.setdefault('dp', 100.0)
        member.setdefault('statuses', [])
    adjust = data.setdefault('adjustments', initial_adjustments())
    adjust.setdefault('od', 0.0)
    adjust.setdefault('members', [])
    while len(adjust['members']) < 6:
        adjust['members'].append({'sp': 0, 'token': 0})
    for delta in adjust['members']:
        delta.pop('ep', None)
    data.setdefault('field', None)
    if 'enemy_weaknesses' not in data:
        data['enemy_weaknesses'] = list((data.get('enemies') or [{}])[0].get('weakness') or [])
    data.setdefault('enemies', [{'weakness': [], 'damage_rate': 100.0, 'down_turns': 0}])
    for enemy in data['enemies']:
        enemy.pop('weakness', None)
        enemy.setdefault('damage_rate', 100.0)
        enemy.setdefault('down', bool(enemy.pop('down_turns', 0)))
        enemy.pop('broken', None)
    data.setdefault('order', list(range(6)))
    data.setdefault('actions', ['normal_attack'] * 3 + ['none'] * 3)
    data.setdefault('od_timing', None); data.setdefault('od_level', 0)
    data.setdefault('predicted_od', None)  # Simulation 将计算后的绝对 OD 写入此字段
    data.setdefault('bonus', 0); data.setdefault('additional_turn', False)
    return data


def effective_state(data):
    """只读计算：显示值 = simulation 基准 + 当前调整值，重复调用不会累加。"""
    base = data['base']; adjustments = data['adjustments']
    members = []
    for index, member in enumerate(base['members']):
        result = copy.deepcopy(member)
        delta = adjustments['members'][index]
        for key in ('sp', 'token'):
            result[key] = member.get(key, 0) + delta.get(key, 0)
        members.append(result)
    return {
        'od': base['od'] + adjustments['od'],
        'members': members,
        'enemies': copy.deepcopy(data['enemies']),
        'enemy_weaknesses': list(data['enemy_weaknesses']),
        'predicted_od': data['predicted_od'],
        'field': data['field'],
        'order': list(data['order']),
        'actions': list(data['actions']),
        'od_timing': data['od_timing'], 'od_level': data['od_level'],
        'bonus': data['bonus'], 'additional_turn': data['additional_turn'],
    }

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
        active = [(name, catalog.skill_data.get(name, {})) for name in catalog.skills_for(style)]
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
            for name, entry in dict(entries).items():
                label = (catalog.skill_label(name) if category != 'passive' else
                         entry.get('names', {}).get('zh-CN-CN') or
                         entry.get('names', {}).get('zh-CN') or name)
                check = QCheckBox(label); check.setChecked(name in selection.get(category, []))
                vertical.addWidget(check); group.append(check)
                self.checks[category, name] = check
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
        return list(result.items())

    def selection(self):
        answer = {'active': [], 'passive': [], 'orb': []}
        for (category, name), check in self.checks.items():
            if check.isChecked(): answer[category].append(name)
        return answer


class BattleSetup(QGroupBox):
    """固定高度，敌人初始数据、六名上场风格及独立的共鸣风格。"""
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__('战斗设置', parent)
        self.setFixedHeight(230)
        self.catalog = catalog
        self.style_dialog_class = style_dialog_class
        self.round_pixmap = round_pixmap
        self.styles = [None] * 6
        self.resonances = [None] * 6
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
        enemy_col.addStretch(1)

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
                name
                for name in self.catalog.skills_for(selected)
                if name not in orb_names
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
        self.enemy_count.setCurrentIndex(0); self.initial_od.setValue(0)
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
        return {
            'initial_od': self.initial_od.value(),
            'enemy_weaknesses': list(self.enemy_weaknesses),
            'enemies': [{'damage_rate': 100, 'down': False}
                        for _ in range(self.enemy_count.currentData() or 1)],
            'members': [{
                'position': i+1, 'style_id': self._style_id(self.styles[i]),
                'team': style.team if style else None,
                'character': style.name if style else None,
                'style': style.title if style else None,
                'break_level': self.breaks[i].currentData(),
                'od_earring': self.earrings[i].currentData(),
                'necklace_sp': self.necklaces[i].currentData(),
                'enabled_skills': copy.deepcopy(self.skill_selections[i]),
            } for i, style in enumerate(self.styles)],
            'resonance_style_ids': [self._style_id(s) for s in self.resonances],
            'resonance_break_levels': [self.resonance_breaks[i].currentData() if s else None
                                       for i, s in enumerate(self.resonances)],
        }

    @staticmethod
    def _style_id(style):
        if style is None: return None
        path = SkillSelectionDialog.catalog_data_path(style)
        if not path.exists(): return None
        data = json.loads(path.read_text(encoding='utf-8'))
        person = next((v for v in data.values() if isinstance(v, dict) and
                       v.get('english name') == style.english), {})
        entry = next((v for v in person.get('style', {}).values()
                      if v.get('value') == style.title and
                      style.sid in [str(k) for k in
                                    (v.get('id') if isinstance(v.get('id'), list) else [v.get('id')])]), {})
        value = entry.get('simulation_id')
        return value[0] if isinstance(value, list) and value else value


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


class BattleTurn(QGroupBox):
    """固定高度战斗回合。普通与调整模式互相替换，状态数据不重复叠加。"""
    HEIGHT = 105

    def __init__(self, owner, number, state):
        super().__init__('')
        self.owner = owner; self.number = number
        self.state_data = ensure_state(state)
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
        page = QWidget(); root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(3)

        enemy = QWidget()
        el = QVBoxLayout(enemy); el.setContentsMargins(4, 1, 4, 1); el.setSpacing(0)
        self.title = QLabel(); self.title.setStyleSheet('font-weight:700;')
        el.addWidget(self.title)
        self.enemy_icons_row = QVBoxLayout(); self.enemy_icons_row.setSpacing(0)
        el.addLayout(self.enemy_icons_row)
        self.field_display = QHBoxLayout(); self.field_display.setSpacing(2)
        el.addLayout(self.field_display)
        el.addStretch(1)
        root.addWidget(enemy, 20)
        root.addWidget(self._separator())

        team = QWidget()
        tl = QHBoxLayout(team); tl.setContentsMargins(4, 3, 4, 3); tl.setSpacing(4)
        self.portraits, self.action_boxes, self.status_rows = [], [], []
        for first, last, stretch in ((0, 3, 65), (3, 6, 35)):
            group = QHBoxLayout(); group.setSpacing(2)
            for pos in range(first, last):
                column = QVBoxLayout(); column.setSpacing(1)
                action = FullPopupCombo()
                action.setFixedHeight(22)
                action.setSizeAdjustPolicy(
                    QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
                )
                action.setMinimumContentsLength(1)
                action.setMinimumWidth(0)
                action.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                action.currentIndexChanged.connect(lambda _=0, i=pos: self.update_action(i))
                column.addWidget(action)
                body = QHBoxLayout(); body.setSpacing(1)
                avatar_button = QPushButton(); avatar_button.setFixedSize(55, 54)
                avatar_button.setStyleSheet('QPushButton{background:transparent;border:0;padding:0}')
                portrait = PortraitWithSP(45, avatar_button); portrait.move(2, 1)
                avatar_button.clicked.connect(lambda _=False, i=pos: self.swap_position(i))
                body.addWidget(avatar_button)
                statuses = QHBoxLayout(); statuses.setSpacing(1)
                body.addLayout(statuses)
                column.addLayout(body); column.addStretch()
                group.addLayout(column, 1)
                self.portraits.append((avatar_button, portrait))
                self.action_boxes.append(action); self.status_rows.append(statuses)
            tl.addLayout(group, stretch)
        root.addWidget(team, 70)
        root.addWidget(self._separator())

        od = QWidget()
        ol = QVBoxLayout(od); ol.setContentsMargins(4, 3, 4, 2); ol.setSpacing(1)
        top = QHBoxLayout(); top.setSpacing(2)
        self.od_icon = QLabel(); self.od_icon.setFixedSize(35, 35)
        top.addWidget(self.od_icon)
        od_values = QVBoxLayout(); od_values.setSpacing(0)
        self.od_label = QLabel(); self.od_label.setStyleSheet('font-weight:700;')
        self.predicted_od_label = QLabel(); self.predicted_od_label.setStyleSheet('font-weight:700;')
        od_values.addWidget(self.od_label)
        od_values.addWidget(self.predicted_od_label)
        top.addLayout(od_values); top.addStretch()
        ol.addLayout(top)
        self.before_od = combo([('不发动', 0)])
        self.after_od = combo([('不发动', 0)])
        for title, box in (('前置', self.before_od), ('后置', self.after_od)):
            line = QHBoxLayout(); line.setSpacing(2)
            caption = QLabel(title); caption.setFixedWidth(27)
            line.addWidget(caption); line.addWidget(box, 1)
            ol.addLayout(line)
        self.before_od.currentIndexChanged.connect(lambda: self.update_od('before'))
        self.after_od.currentIndexChanged.connect(lambda: self.update_od('after'))
        ol.addStretch(1)
        root.addWidget(od, 10)
        root.addWidget(self._separator())

        # ④ 操作栏：OD 区域只负责显示及发动设置，不再放置按钮。
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
        self.back_button.setStyleSheet('QPushButton{padding:2px 4px;min-height:0px;}')
        self.back_button.clicked.connect(lambda: self.owner.truncate_after(self))
        op.addWidget(self.switch_button)
        op.addWidget(self.next_button)
        op.addWidget(self.back_button)
        op.addStretch(1)
        root.addWidget(operations, 6)
        self.stack.addWidget(page)

    def _make_adjust_page(self):
        page = QWidget(); root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(3)

        # ① 敌人：敌人数和三名敌人在同一行。
        enemy_panel = QWidget(); eg = QGridLayout(enemy_panel)
        eg.setContentsMargins(3, 2, 3, 2); eg.setSpacing(2)
        self.adjust_enemies = combo([(str(i), i) for i in range(1, 4)])
        self.adjust_enemies.setFixedWidth(48)
        eg.addWidget(self.adjust_enemies, 0, 0)
        self.enemy_edits = []; self.enemy_headers = []
        for i in range(3):
            heading = QLabel(f'敌人{i+1}')
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            eg.addWidget(heading, 0, i+1)
            self.enemy_headers.append(heading)
            down = QCheckBox(); down.setToolTip('倒下')
            rate = spin(0, 999, 100)
            eg.addWidget(down, 1, i+1, alignment=Qt.AlignmentFlag.AlignCenter)
            eg.addWidget(rate, 2, i+1)
            self.enemy_edits.append((down, rate))
        eg.addWidget(QLabel('倒下'), 1, 0)
        eg.addWidget(QLabel('破坏率'), 2, 0)
        root.addWidget(enemy_panel, 25)
        root.addWidget(self._separator())

        # ② 角色：DP 与头像横向并列，占据第一行；下面只有 SP 和信念。
        team_panel = QWidget(); mg = QGridLayout(team_panel)
        mg.setContentsMargins(3, 2, 3, 2); mg.setSpacing(2)
        self.member_edits = []; self.member_portraits = []
        for i in range(6):
            first_row = QHBoxLayout(); first_row.setSpacing(1)
            pic = QLabel(); pic.setFixedSize(25, 25)
            pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            first_row.addWidget(pic)
            self.member_portraits.append(pic)
            fields = {}
            dp = dspin(0, 150, 100)
            dp.setSuffix('%'); dp.setFixedHeight(22); dp.setMinimumWidth(46)
            dp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            first_row.addWidget(dp, 1); fields['dp'] = dp
            mg.addLayout(first_row, 0, i+1)
            for row, key in enumerate(('sp', 'token'), 1):
                widget = spin(-999, 999, 0)
                widget.setFixedHeight(21); widget.setMinimumWidth(58)
                mg.addWidget(widget, row, i+1)
                fields[key] = widget
            self.member_edits.append(fields)
        mg.addWidget(QLabel('DP'), 0, 0)
        for row, label in ((1, 'SP'), (2, '信念')):
            caption = QLabel(label); caption.setFixedWidth(28)
            mg.addWidget(caption, row, 0)
        root.addWidget(team_panel, 65)
        root.addWidget(self._separator())

        # ③ OD/全局：三行内放入 OD 增减、场地以及返回按钮。
        od_panel = QWidget(); ol = QVBoxLayout(od_panel)
        ol.setContentsMargins(3, 2, 3, 2); ol.setSpacing(3)
        od_line = QHBoxLayout(); od_line.setSpacing(2)
        od_line.addWidget(QLabel('OD±'))
        self.adjust_od = dspin(-999, 999, 0)
        od_line.addWidget(self.adjust_od, 1)
        ol.addLayout(od_line)
        field_line = QHBoxLayout(); field_line.setSpacing(2)
        field_line.addWidget(QLabel('场地'))
        self.adjust_field = combo(FIELD_OPTIONS)
        field_line.addWidget(self.adjust_field, 1)
        ol.addLayout(field_line)
        self.adjust_return = QPushButton('返回')
        self.adjust_return.setStyleSheet(BLUE_BUTTON)
        self.adjust_return.setFixedHeight(25)
        self.adjust_return.clicked.connect(self.toggle_mode)
        ol.addWidget(self.adjust_return, alignment=Qt.AlignmentFlag.AlignRight)
        ol.addStretch(1)
        root.addWidget(od_panel, 7)
        self.stack.addWidget(page)
        self.adjust_enemies.currentIndexChanged.connect(self.update_enemy_edit_visibility)

    def update_enemy_edit_visibility(self):
        count = self.adjust_enemies.currentData() or 1
        for i, controls in enumerate(self.enemy_edits):
            enabled = i < count
            self.enemy_headers[i].setEnabled(enabled)
            for widget in controls:
                widget.setEnabled(enabled)
                if isinstance(widget, QCheckBox):
                    widget.setStyleSheet('' if enabled else
                        'QCheckBox::indicator:disabled{background:#cbd5e1;'
                        'border:1px solid #94a3b8;border-radius:3px;}')
                else:
                    widget.setStyleSheet('' if enabled else
                        'QSpinBox:disabled{background:#e5e7eb;color:#6b7280;'
                        'border:1px solid #cbd5e1;}')

    def update_action(self, position):
        self.state_data['actions'][position] = self.action_boxes[position].currentData()

    def update_od(self, timing):
        selected = self.before_od if timing == 'before' else self.after_od
        other = self.after_od if timing == 'before' else self.before_od
        if selected.currentData():
            other.blockSignals(True); other.setCurrentIndex(0); other.blockSignals(False)
        self.state_data['od_timing'] = timing if selected.currentData() else None
        self.state_data['od_level'] = selected.currentData() or 0

    def swap_position(self, index):
        if self.select_first is None:
            self.select_first = index
            self.portraits[index][0].setStyleSheet('QPushButton{border:2px solid #2563eb;background:#dbeafe}')
            return
        first = self.select_first; self.select_first = None
        self.portraits[first][0].setStyleSheet('QPushButton{background:transparent;border:0;padding:0}')
        if first == index: return
        self.save_combat_state()
        data = self.state_data
        data['order'][first], data['order'][index] = data['order'][index], data['order'][first]
        data['actions'][first], data['actions'][index] = data['actions'][index], data['actions'][first]
        self.refresh()

    def save_combat_state(self):
        for i, box in enumerate(self.action_boxes):
            self.state_data['actions'][i] = box.currentData()

    def load_adjust(self):
        data = self.state_data; adjust = data['adjustments']
        self.adjust_od.setValue(adjust['od'])
        self.adjust_field.setCurrentIndex(max(0, self.adjust_field.findData(data['field'])))
        self.adjust_enemies.setCurrentIndex(max(0, len(data['enemies'])-1))
        for i, (down, rate) in enumerate(self.enemy_edits):
            enemy = data['enemies'][i] if i < len(data['enemies']) else {
                'damage_rate': 100.0, 'down': False}
            down.setChecked(bool(enemy.get('down', enemy.get('down_turns', 0))))
            rate.setValue(round(enemy.get('damage_rate', 100)))
        for position, controls in enumerate(self.member_edits):
            slot = data['order'][position]
            member = data['base']['members'][slot]
            delta = adjust['members'][slot]
            for key in ('sp', 'token'): controls[key].setValue(delta.get(key, 0))
            controls['dp'].setValue(member.get('dp', 100.0))
            style = self.owner.setup.styles[slot]
            pic = self.member_portraits[position]
            if style:
                pic.setPixmap(self.owner.setup.round_pixmap(style.image, 25))
                pic.setToolTip(style.localized_title)
                pic.setText('')
            else:
                pic.clear(); pic.setText('＋')
        self.update_enemy_edit_visibility()

    def save_adjust(self):
        data = self.state_data; adjust = data['adjustments']
        adjust['od'] = self.adjust_od.value()
        data['field'] = self.adjust_field.currentData()
        count = self.adjust_enemies.currentData() or 1
        old_enemies = data['enemies']
        new_enemies = []
        for i, (down, rate) in enumerate(self.enemy_edits[:count]):
            enemy = copy.deepcopy(old_enemies[i]) if i < len(old_enemies) else {}
            enemy['down'] = down.isChecked()
            enemy['damage_rate'] = rate.value()
            enemy.pop('down_turns', None)
            new_enemies.append(enemy)
        data['enemies'] = new_enemies
        for position, fields in enumerate(self.member_edits):
            slot = data['order'][position]
            for key in ('sp', 'token'):
                adjust['members'][slot][key] = fields[key].value()
            data['base']['members'][slot]['dp'] = fields['dp'].value()

    def toggle_mode(self):
        if self.stack.currentIndex() == 0:
            self.save_combat_state(); self.load_adjust()
            self.stack.setCurrentIndex(1)
        else:
            self.save_adjust(); self.stack.setCurrentIndex(0)
            self.refresh()
            self.refresh_turn_controls()

    def refresh_turn_controls(self):
        latest = self.owner.turns and self.owner.turns[-1] is self
        self.next_button.setVisible(bool(latest))
        self.back_button.setVisible(not bool(latest))

    def refresh_enemy_info(self):
        data = self.state_data
        clear_layout(self.enemy_icons_row)
        weak_line = QHBoxLayout(); weak_line.setSpacing(1)
        weak_line.addWidget(QLabel('敌人弱点：'))
        weaknesses = data['enemy_weaknesses']
        for item in weaknesses:
            path = ROOT_DIR / 'assets' / 'icons' / 'element' / f'{item}.webp'
            weak_line.addWidget(icon_label(path, 18, ELEMENT_NAMES.get(item, '?')))
        if not weaknesses: weak_line.addWidget(QLabel('无'))
        weak_line.addStretch(1)
        self.enemy_icons_row.addLayout(weak_line)
        for i, enemy in enumerate(data['enemies'], 1):
            line = QHBoxLayout(); line.setSpacing(1)
            line.addWidget(QLabel(f'敌人{i}状态：'))
            line.addStretch(1)
            self.enemy_icons_row.addLayout(line)
        clear_layout(self.field_display)
        self.field_display.addWidget(QLabel('场地：'))
        field = data.get('field')
        if field is None:
            self.field_display.addWidget(QLabel('无'))
        elif field == 'rice_field':
            path = ROOT_DIR / 'assets' / 'icons' / 'status' / 'RiceFieldZone.webp'
            self.field_display.addWidget(icon_label(path, 19, '稻'))
        else:
            path = ROOT_DIR / 'assets' / 'icons' / 'status' / f'{field.capitalize()}Zone.webp'
            self.field_display.addWidget(icon_label(path, 19, FIELD_NAMES.get(field, '场')))
        self.field_display.addStretch(1)

    def refresh(self):
        data = self.state_data; result = effective_state(data)
        self.title.setText(f'T{self.number}' +
                           (f"-bonus{data['bonus']}" if data.get('bonus') else '') +
                           ('-追加回合' if data.get('additional_turn') else ''))
        od_value = result['od']
        self.od_label.setText(f'{od_value:.2f}%')
        estimate = data.get('predicted_od')
        self.predicted_od_label.setText('→ —' if estimate is None else f'→ {estimate:.2f}%')
        self.od_label.setStyleSheet('font-weight:700;color:' + ('#dc2626' if od_value < 0 else '#242933') + ';')
        self.predicted_od_label.setStyleSheet('font-weight:700;color:' +
                                            ('#dc2626' if estimate is not None and estimate < 0 else '#242933') + ';')
        level = max(0, min(3, int(od_value // 100)))
        pix = QPixmap(str(ROOT_DIR / 'assets' / 'icons' / 'od' / f'od{level}.webp'))
        if pix.isNull(): self.od_icon.setText(f'OD{level}')
        else: self.od_icon.setPixmap(pix.scaled(29, 29,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation))
        self.refresh_enemy_info()
        available = max(0, min(3, int(od_value // 100)))
        for timing, box in (('before', self.before_od), ('after', self.after_od)):
            box.blockSignals(True); box.clear(); box.addItem('不发动', 0)
            for n in range(1, available+1): box.addItem(f'OD{n}', n)
            if data['od_timing'] == timing:
                box.setCurrentIndex(max(0, box.findData(data['od_level'])))
            box.blockSignals(False)
        if data['od_level'] > available:
            data['od_level'] = 0; data['od_timing'] = None
        for position in range(6):
            slot = data['order'][position]
            style = self.owner.setup.styles[slot]
            button, portrait = self.portraits[position]
            portrait.configure(style.image if style else None,
                               self.owner.setup.round_pixmap,
                               result['members'][slot]['sp'])
            button.setToolTip((style.localized_title if style else f'角色{slot+1}') +
                              '（点击两名角色头像交换位置）')
            clear_layout(self.status_rows[position])
            for status in result['members'][slot].get('statuses', []):
                path = self.owner.status_icon(status)
                if path: self.status_rows[position].addWidget(icon_label(path, 15))
            action = self.action_boxes[position]
            original = data['actions'][position]
            action.blockSignals(True); action.clear()
            if position < 3:
                action.addItem('普通攻击', 'normal_attack')
                if style:
                    selected = self.owner.setup.skill_selections[slot]
                    for name in dict.fromkeys(selected['active'] + selected['orb']):
                        entry = self.owner.catalog.skill_data.get(name, {})
                        action.addItem(self.owner.catalog.skill_label(name),
                                       entry.get('simulation_id', name))
            else:
                action.addItem('无', 'none'); action.addItem('追击', 'pursuit')
            index = action.findData(original)
            action.setCurrentIndex(index if index >= 0 else 0)
            data['actions'][position] = action.currentData()
            action.blockSignals(False)
        if self in self.owner.turns:
            self.refresh_turn_controls()

    def state(self):
        if self.stack.currentIndex() == 1: self.save_adjust()
        else: self.save_combat_state()
        answer = copy.deepcopy(self.state_data)
        answer['effective'] = effective_state(self.state_data)
        return answer


class SimulationTab(QWidget):
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setup = BattleSetup(catalog, style_dialog_class, round_pixmap)
        self.turns = []; self.session = None
        self.engine = None  # engine.advance(effective_snapshot, setup, actions)
        self._status_icons = self._load_status_icons()
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

    @staticmethod
    def _load_status_icons():
        for path in (ROOT_DIR / 'assets' / 'simulation-data' / 'statuses.json',
                     ROOT_DIR / 'assets' / 'char-data' / 'statuses.json'):
            if path.is_file():
                try: return json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError): return {}
        return {}

    def status_icon(self, item):
        if not isinstance(item, (int, str, dict)): return None
        if isinstance(item, dict):
            identifier = item.get('status_id', item.get('id'))
            element = item.get('element') or 'none'
        else:
            identifier = item; element = 'none'
        status = self._status_icons.get(str(identifier), {})
        if status.get('not_display'): return None
        file_name = status.get('icon') or status.get('icons', {}).get(element)
        if not file_name: file_name = status.get('icons', {}).get('none')
        if not file_name: return None
        path = ROOT_DIR / 'assets' / 'icons' / 'status' / file_name
        return path if path.is_file() else None

    def start(self):
        if any(style is None for style in self.setup.styles):
            QMessageBox.warning(self, '无法开始战斗', '请先选齐六个风格。'); return
        self.session = {'setup': self.setup.state()}
        for turn in self.turns:
            self.turn_layout.removeWidget(turn); turn.deleteLater()
        self.turns.clear()
        members = [{'sp': 0, 'token': 0, 'dp': 100.0, 'statuses': []}
                   for _ in range(6)]
        initial = {
            'base': {'od': self.session['setup']['initial_od'], 'members': members},
            'adjustments': initial_adjustments(),
            'field': None,
            'enemies': copy.deepcopy(self.session['setup']['enemies']),
            'enemy_weaknesses': list(self.session['setup']['enemy_weaknesses']),
            'predicted_od': None,
            'order': list(range(6)),
            'actions': ['normal_attack']*3 + ['none']*3,
            'od_timing': None, 'od_level': 0,
            'bonus': 0, 'additional_turn': False,
        }
        self.add_turn(initial)

    def add_turn(self, state):
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
        if not self.turns or turn is not self.turns[-1]:
            QMessageBox.information(self, '回合顺序', '请先点击“回到本回合”清除后续回合。')
            return
        current = turn.state()
        effective = current['effective']
        if self.engine is None:
            # 未连接 Simulation 时仅继承当前可见资源作为下一回合基准值。
            # 这不是 SP/OD 的战斗结算结果。
            next_snapshot = copy.deepcopy(effective)
        else:
            next_snapshot = self.engine.advance(copy.deepcopy(effective),
                                                copy.deepcopy(self.session['setup']),
                                                copy.deepcopy(effective['actions']))
        next_snapshot = ensure_state(next_snapshot)
        # 下一回合重新建立基准，并把所有手动偏移初始化为0；旧回合的偏移保留在旧回合。
        next_snapshot['base'] = {
            'od': next_snapshot.pop('od', next_snapshot['base']['od']),
            'members': next_snapshot.pop('members', next_snapshot['base']['members']),
        }
        next_snapshot['adjustments'] = initial_adjustments()
        next_snapshot['actions'] = ['normal_attack']*3 + ['none']*3
        next_snapshot['od_timing'] = None; next_snapshot['od_level'] = 0
        next_snapshot['bonus'] = 0; next_snapshot['additional_turn'] = False
        next_snapshot['predicted_od'] = None
        result = self.add_turn(next_snapshot)
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
