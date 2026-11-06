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
FIELD_OPTIONS = [('无场地', None), ('稻田', 'rice_field'), ('火场地', 'fire'), ('冰场地', 'ice'),
                 ('雷场地', 'thunder'), ('光场地', 'light'), ('暗场地', 'dark')]
ELEMENT_NAMES = dict((value, label) for label, value in ELEMENTS)
FIELD_NAMES = dict((value, label) for label, value in FIELD_OPTIONS)
BLUE_BUTTON = ('QPushButton{background:#2563eb;color:white;border:1px solid #1d4ed8;'
               'border-radius:7px;padding:3px 9px;font-weight:600}'
               'QPushButton:hover{background:#1d4ed8}'
               'QPushButton:disabled{background:#cbd5e1;border-color:#cbd5e1}')
COMPACT = ('QComboBox,QSpinBox,QDoubleSpinBox{padding:2px 4px;min-height:17px;'
           'border:1px solid #d6deea;border-radius:5px;background:white}')


class NoWheelComboBox(QComboBox):
    """与原 GUI 一致：滚轮只用于页面滚动，不改变下拉框选项。"""
    def wheelEvent(self, event):
        event.ignore()


def combo(options, width=None):
    box = NoWheelComboBox()
    for label, value in options:
        box.addItem(label, value)
    if width is not None:
        box.setFixedWidth(width)
    box.setFixedHeight(25)
    return box


def spin(low=0, high=99999, value=0, width=None):
    box = QSpinBox(); box.setRange(low, high); box.setValue(value)
    box.setFixedHeight(25)
    if width: box.setFixedWidth(width)
    return box


def dspin(low=0, high=999.99, value=0, width=None):
    box = QDoubleSpinBox(); box.setRange(low, high); box.setDecimals(2)
    box.setSingleStep(1); box.setValue(value); box.setFixedHeight(25)
    if width: box.setFixedWidth(width)
    return box


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


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def initial_adjustments():
    return {'od': 0.0, 'members': [{'sp': 0, 'token': 0, 'ep': 0} for _ in range(6)]}


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
        base['members'].append({'sp': 0, 'token': 0, 'ep': 0, 'dp': 100.0, 'statuses': []})
    for member in base['members']:
        member.setdefault('sp', 0); member.setdefault('token', 0)
        member.setdefault('ep', 0); member.setdefault('dp', 100.0)
        member.setdefault('statuses', [])
    adjust = data.setdefault('adjustments', initial_adjustments())
    adjust.setdefault('od', 0.0)
    adjust.setdefault('members', [])
    while len(adjust['members']) < 6:
        adjust['members'].append({'sp': 0, 'token': 0, 'ep': 0})
    data.setdefault('field', None)
    data.setdefault('enemies', [{'weakness': None, 'damage_rate': 100.0, 'down_turns': 0}])
    for enemy in data['enemies']:
        enemy.setdefault('weakness', None)
        enemy.setdefault('damage_rate', 100.0)
        enemy.setdefault('down_turns', 0)
        enemy.pop('broken', None)
    data.setdefault('order', list(range(6)))
    data.setdefault('actions', ['normal_attack'] * 3 + ['none'] * 3)
    data.setdefault('od_timing', None); data.setdefault('od_level', 0)
    data.setdefault('bonus', 0); data.setdefault('additional_turn', False)
    return data


def effective_state(data):
    """只读计算：显示值 = simulation 基准 + 当前调整值，重复调用不会累加。"""
    base = data['base']; adjustments = data['adjustments']
    members = []
    for index, member in enumerate(base['members']):
        result = copy.deepcopy(member)
        delta = adjustments['members'][index]
        for key in ('sp', 'token', 'ep'):
            result[key] = member.get(key, 0) + delta.get(key, 0)
        members.append(result)
    return {
        'od': max(0.0, base['od'] + adjustments['od']),
        'members': members,
        'enemies': copy.deepcopy(data['enemies']),
        'field': data['field'],
        'order': list(data['order']),
        'actions': list(data['actions']),
        'od_timing': data['od_timing'], 'od_level': data['od_level'],
        'bonus': data['bonus'], 'additional_turn': data['additional_turn'],
    }


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
    def __init__(self, catalog, style_dialog_class, round_pixmap, parent=None):
        super().__init__('战斗设置', parent)
        self.catalog = catalog
        self.style_dialog_class = style_dialog_class
        self.round_pixmap = round_pixmap
        self.styles = [None] * 6
        self.skill_selections = [{'active': [], 'passive': [], 'orb': []} for _ in range(6)]
        root = QHBoxLayout(self); root.setContentsMargins(9, 12, 9, 8); root.setSpacing(8)
        enemy_panel = QWidget(); enemy_panel.setFixedWidth(133)
        enemy_col = QVBoxLayout(enemy_panel); enemy_col.setContentsMargins(0, 0, 0, 0)
        enemy_col.setSpacing(3)
        enemy_col.addWidget(QLabel('敌人数量'))
        self.enemy_count = combo([(f'{n} 个', n) for n in range(1, 4)])
        enemy_col.addWidget(self.enemy_count)
        enemy_col.addWidget(QLabel('敌人弱点'))
        self.enemy_weaknesses = []
        for i in range(3):
            line = QHBoxLayout(); line.setContentsMargins(0, 0, 0, 0)
            label = QLabel(f'{i+1}'); label.setFixedWidth(13); line.addWidget(label)
            weakness = combo(ELEMENTS)
            line.addWidget(weakness, 1)
            enemy_col.addLayout(line); self.enemy_weaknesses.append(weakness)
        enemy_col.addStretch()
        self.enemy_count.currentIndexChanged.connect(self._refresh_enemy_controls)
        root.addWidget(enemy_panel)
        divider = QFrame(); divider.setFrameShape(QFrame.Shape.VLine); root.addWidget(divider)

        team_panel = QWidget(); team_layout = QVBoxLayout(team_panel)
        team_layout.setContentsMargins(0, 0, 0, 0); team_layout.setSpacing(2)
        header = QHBoxLayout(); header.addWidget(QLabel('六人队伍'))
        reset = QPushButton('重置'); reset.clicked.connect(self.reset)
        header.addWidget(reset); header.addStretch(); team_layout.addLayout(header)
        grid = QGridLayout(); grid.setHorizontalSpacing(5); grid.setVerticalSpacing(2)
        labels = ['风格', '突破', 'OD耳环', '普攻属性', '项链', '技能']
        for row, name in enumerate(labels):
            caption = QLabel(name); caption.setFixedWidth(58)
            grid.addWidget(caption, row, 0)
        self.avatar_buttons = []; self.breaks = []; self.earrings = []
        self.elements = []; self.necklaces = []; self.skill_buttons = []
        for idx in range(6):
            avatar = QPushButton('＋'); avatar.setFixedSize(56, 56)
            avatar.clicked.connect(lambda _=False, i=idx: self.choose_style(i))
            grid.addWidget(avatar, 0, idx+1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.avatar_buttons.append(avatar)
            level = combo([(str(n), n) for n in range(5)])
            ear = combo([('无', 0), ('10%', 10), ('12%', 12), ('15%', 15)])
            elem = combo(ELEMENTS)
            necklace = combo([(f'SP+{n}', n) for n in range(4)])
            self.breaks.append(level); self.earrings.append(ear)
            self.elements.append(elem); self.necklaces.append(necklace)
            ear.setCurrentIndex(3); necklace.setCurrentIndex(3)
            for row, widget in enumerate((level, ear, elem, necklace), 1):
                widget.setMinimumWidth(67)
                grid.addWidget(widget, row, idx+1)
            setting = QPushButton('设置'); setting.setStyleSheet(BLUE_BUTTON)
            setting.setFixedHeight(25)
            setting.clicked.connect(lambda _=False, i=idx: self.choose_skills(i))
            grid.addWidget(setting, 5, idx+1); self.skill_buttons.append(setting)
        for column in range(1, 7): grid.setColumnStretch(column, 1)
        team_layout.addLayout(grid)
        root.addWidget(team_panel, 1)
        self._refresh_enemy_controls()

    def _refresh_enemy_controls(self):
        count = self.enemy_count.currentData() or 1
        for i, box in enumerate(self.enemy_weaknesses): box.setEnabled(i < count)

    def choose_style(self, index):
        occupied = {style.name for i, style in enumerate(self.styles)
                    if style is not None and i != index}
        dialog = self.style_dialog_class(self.catalog, occupied, self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        style = dialog.chosen
        self.styles[index] = style
        self.skill_selections[index] = {'active': list(self.catalog.skills_for(style)),
                                        'passive': [], 'orb': []}
        button = self.avatar_buttons[index]; button.setText('')
        button.setIcon(QIcon(self.round_pixmap(style.image, 51)))
        button.setIconSize(QSize(51, 51))
        button.setToolTip(f'{style.label} · {style.localized_title}')
        maximum = {'A': 20, 'S': 10, 'SS': 4, 'SSR': 4}.get(style.tier, 4)
        level = self.breaks[index]; level.clear()
        for n in range(maximum + 1): level.addItem(str(n), n)
        level.setCurrentIndex(maximum if style.tier in ('A', 'S') else min(2, maximum))

    def choose_skills(self, index):
        style = self.styles[index]
        if style is None:
            QMessageBox.information(self, '未选择风格', '请先选择该位置的风格。'); return
        dialog = SkillSelectionDialog(self.catalog, style, self.skill_selections[index], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.skill_selections[index] = dialog.selection()
            amount = sum(len(group) for group in self.skill_selections[index].values())
            self.skill_buttons[index].setToolTip(f'已选 {amount} 项技能')

    def reset(self):
        self.styles = [None] * 6
        self.skill_selections = [{'active': [], 'passive': [], 'orb': []} for _ in range(6)]
        self.enemy_count.setCurrentIndex(0)
        for box in self.enemy_weaknesses: box.setCurrentIndex(0)
        for index, button in enumerate(self.avatar_buttons):
            button.setText('＋'); button.setIcon(QIcon())
            level = self.breaks[index]; level.clear()
            for n in range(5): level.addItem(str(n), n)
            level.setCurrentIndex(2)
            self.earrings[index].setCurrentIndex(3)
            self.elements[index].setCurrentIndex(0)
            self.necklaces[index].setCurrentIndex(3)

    def state(self):
        return {
            'enemies': [{'weakness': self.enemy_weaknesses[i].currentData(),
                         'damage_rate': 100.0, 'down_turns': 0}
                        for i in range(self.enemy_count.currentData() or 1)],
            'members': [{
                'position': i+1, 'style_id': self._style_id(i),
                'team': style.team if style else None,
                'character': style.name if style else None,
                'style': style.title if style else None,
                'break_level': self.breaks[i].currentData(),
                'od_earring': self.earrings[i].currentData(),
                'normal_attack_element': self.elements[i].currentData(),
                'necklace_sp': self.necklaces[i].currentData(),
                'enabled_skills': copy.deepcopy(self.skill_selections[i]),
            } for i, style in enumerate(self.styles)],
        }

    def _style_id(self, index):
        style = self.styles[index]
        if style is None: return None
        path = SkillSelectionDialog.catalog_data_path(style)
        if not path.exists(): return None
        data = json.loads(path.read_text(encoding='utf-8'))
        person = next((item for item in data.values() if isinstance(item, dict) and
                       item.get('english name') == style.english), {})
        entry = next((item for item in person.get('style', {}).values()
                      if item.get('value') == style.title and
                      style.sid in [str(v) for v in
                                    (item.get('id') if isinstance(item.get('id'), list) else [item.get('id')])]), {})
        result = entry.get('simulation_id')
        return result[0] if isinstance(result, list) and result else result


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
        font = QFont(); font.setBold(True); font.setPointSize(11)
        painter.setFont(font)
        text = str(self.sp)
        rect = self.rect().adjusted(0, -2, -1, 0)
        # 先绘制八方向黑色描边，再绘制白色文字。
        painter.setPen(QPen(QColor('#111827')))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (1, 1), (-1, 1), (1, -1)):
            painter.drawText(rect.translated(dx, dy),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, text)
        painter.setPen(QPen(QColor('white')))
        painter.drawText(rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, text)
        painter.end()


class BattleTurn(QGroupBox):
    def __init__(self, owner, number, state):
        super().__init__('')
        self.owner = owner
        self.number = number
        self.state_data = ensure_state(state)
        self.select_first = None
        self.setObjectName('simulationTurn')
        outer = QVBoxLayout(self); outer.setContentsMargins(8, 8, 8, 7)
        outer.setSpacing(2)
        header = QHBoxLayout(); header.setSpacing(5)
        self.title = QLabel(); self.title.setStyleSheet('font-weight:600;')
        header.addWidget(self.title)
        header.addStretch(1)
        outer.addLayout(header)
        self.stack = QStackedWidget(); outer.addWidget(self.stack)
        self._make_combat_page()
        self._make_adjust_page()
        footer = QHBoxLayout(); footer.setSpacing(4); footer.addStretch()
        self.switch_button = QPushButton('调整'); self.switch_button.setStyleSheet(BLUE_BUTTON)
        self.switch_button.setFixedHeight(24)
        self.switch_button.clicked.connect(self.toggle_mode)
        self.next_button = QPushButton('下一回合')
        self.next_button.setStyleSheet(BLUE_BUTTON); self.next_button.setFixedHeight(24)
        self.next_button.clicked.connect(lambda: self.owner.next_turn(self))
        self.back_button = QPushButton('回到本回合'); self.back_button.setFixedHeight(24)
        self.back_button.clicked.connect(lambda: self.owner.truncate_after(self))
        footer.addWidget(self.switch_button)
        footer.addWidget(self.next_button)
        footer.addWidget(self.back_button)
        outer.addLayout(footer)
        self.refresh()

    def _make_combat_page(self):
        page = QWidget(); root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(7)
        # 仅展示敌人数量、弱点、场地，无编辑控件。
        enemy = QFrame(); enemy.setObjectName('simulationSegment')
        el = QVBoxLayout(enemy); el.setContentsMargins(6, 3, 6, 3); el.setSpacing(2)
        el.addWidget(QLabel('敌人与场地'))
        self.enemy_count_label = QLabel()
        el.addWidget(self.enemy_count_label)
        self.enemy_icons_row = QHBoxLayout(); self.enemy_icons_row.setSpacing(3)
        el.addLayout(self.enemy_icons_row)
        self.field_display = QHBoxLayout(); self.field_display.setSpacing(3)
        el.addLayout(self.field_display); el.addStretch(1)
        root.addWidget(enemy, 2)
        od = QFrame(); od.setObjectName('simulationSegment')
        ol = QVBoxLayout(od); ol.setContentsMargins(6, 3, 6, 3); ol.setSpacing(3)
        ol.addWidget(QLabel('OD 发动'))
        icon_row = QHBoxLayout(); icon_row.setSpacing(3)
        self.od_icon = QLabel(); self.od_icon.setFixedSize(36, 36)
        icon_row.addWidget(self.od_icon)
        self.od_label = QLabel(); self.od_label.setStyleSheet('font-weight:600;')
        icon_row.addWidget(self.od_label); icon_row.addStretch()
        ol.addLayout(icon_row)
        before_row = QHBoxLayout(); before_row.setSpacing(3)
        before_row.addWidget(QLabel('前置'))
        self.before_od = combo([('不发动', 0)])
        before_row.addWidget(self.before_od, 1)
        ol.addLayout(before_row)
        after_row = QHBoxLayout(); after_row.setSpacing(3)
        after_row.addWidget(QLabel('后置'))
        self.after_od = combo([('不发动', 0)])
        after_row.addWidget(self.after_od, 1)
        ol.addLayout(after_row)
        self.before_od.currentIndexChanged.connect(lambda: self.update_od('before'))
        self.after_od.currentIndexChanged.connect(lambda: self.update_od('after'))
        ol.addStretch(1)
        root.addWidget(od, 2)

        team = QFrame(); team.setObjectName('simulationSegment')
        tl = QVBoxLayout(team); tl.setContentsMargins(5, 3, 5, 3); tl.setSpacing(2)
        tl.addWidget(QLabel('我方行动（依次点击两名角色头像可交换位置）'))
        members_row = QHBoxLayout(); members_row.setSpacing(3)
        self.portraits = []; self.action_boxes = []; self.status_rows = []
        for pos in range(6):
            column = QVBoxLayout(); column.setSpacing(1)
            action = combo([('普通攻击', 'normal_attack')] if pos < 3 else
                           [('无', 'none'), ('追击', 'pursuit')])
            action.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            action.currentIndexChanged.connect(lambda _=0, i=pos: self.update_action(i))
            column.addWidget(action)
            body = QHBoxLayout(); body.setSpacing(1)
            avatar_button = QPushButton(); avatar_button.setFixedSize(67, 61)
            avatar_button.setStyleSheet('QPushButton{background:transparent;border:0;padding:0}')
            portrait = PortraitWithSP(50, avatar_button)
            portrait.move(3, 2)
            avatar_button.clicked.connect(lambda _=False, i=pos: self.swap_position(i))
            body.addWidget(avatar_button)
            statuses = QHBoxLayout(); statuses.setSpacing(1)
            body.addLayout(statuses)
            column.addLayout(body)
            members_row.addLayout(column, 1)
            self.portraits.append((avatar_button, portrait))
            self.action_boxes.append(action); self.status_rows.append(statuses)
            if pos == 2:
                separator = QFrame(); separator.setFrameShape(QFrame.Shape.VLine)
                members_row.addWidget(separator)
        tl.addLayout(members_row)
        root.addWidget(team, 9)
        self.stack.addWidget(page)

    def _make_adjust_page(self):
        page = QWidget(); root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(7)
        # 全局、敌人、角色三个独立列，整个页面取代普通显示页面。
        global_box = QGroupBox('全局调整'); gl = QGridLayout(global_box)
        gl.setContentsMargins(6, 8, 6, 5); gl.setSpacing(3)
        self.adjust_od = dspin(-999, 999, 0, 79)
        self.adjust_field = combo(FIELD_OPTIONS, 93)
        gl.addWidget(QLabel('OD 增减'), 0, 0); gl.addWidget(self.adjust_od, 0, 1)
        gl.addWidget(QLabel('场地'), 1, 0); gl.addWidget(self.adjust_field, 1, 1)
        self.adjust_enemies = combo([(f'{i} 个', i) for i in range(1, 4)], 93)
        gl.addWidget(QLabel('敌人数'), 2, 0); gl.addWidget(self.adjust_enemies, 2, 1)
        root.addWidget(global_box, 2)

        enemy_box = QGroupBox('各敌人状态'); eg = QGridLayout(enemy_box)
        eg.setContentsMargins(5, 8, 5, 5); eg.setSpacing(3)
        eg.addWidget(QLabel(''), 0, 0)
        for i in range(3):
            eg.addWidget(QLabel(f'敌人{i+1}'), 0, i+1,
                         alignment=Qt.AlignmentFlag.AlignCenter)
        self.enemy_edits = []
        for i in range(3):
            down = spin(0, 99, 0, 65)
            rate = dspin(0, 999.99, 100, 75)
            weakness = combo(ELEMENTS, 75)
            eg.addWidget(down, 1, i+1)
            eg.addWidget(rate, 2, i+1)
            eg.addWidget(weakness, 3, i+1)
            self.enemy_edits.append((down, rate, weakness))
        for row, name in [(1, '倒下回合'), (2, '破坏率'), (3, '弱点')]:
            eg.addWidget(QLabel(name), row, 0)
        root.addWidget(enemy_box, 3)

        team_box = QGroupBox('角色资源调整（增减量）')
        mg = QGridLayout(team_box)
        mg.setContentsMargins(5, 8, 5, 5); mg.setSpacing(2)
        self.member_edits = []; self.member_portraits = []
        for i in range(6):
            pic = QLabel(); pic.setFixedSize(34, 34)
            pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mg.addWidget(pic, 0, i+1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.member_portraits.append(pic)
            fields = {}
            for row, key in enumerate(('sp', 'token', 'ep'), 1):
                box = spin(-999, 999, 0, 57)
                mg.addWidget(box, row, i+1)
                fields[key] = box
            dp = dspin(0, 150, 100, 61); dp.setSuffix('%')
            mg.addWidget(dp, 4, i+1); fields['dp'] = dp
            self.member_edits.append(fields)
        for row, label in enumerate(('SP', 'Token', 'EP', 'DP'), 1):
            mg.addWidget(QLabel(label), row, 0)
        root.addWidget(team_box, 6)
        self.stack.addWidget(page)
        self.adjust_enemies.currentIndexChanged.connect(self.update_enemy_edit_visibility)

    def update_enemy_edit_visibility(self):
        count = self.adjust_enemies.currentData() or 1
        for i, controls in enumerate(self.enemy_edits):
            for widget in controls: widget.setEnabled(i < count)

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
        data = self.state_data
        adjust = data['adjustments']
        self.adjust_od.setValue(adjust['od'])
        self.adjust_field.setCurrentIndex(max(0, self.adjust_field.findData(data['field'])))
        self.adjust_enemies.setCurrentIndex(max(0, len(data['enemies']) - 1))
        for i, (down, rate, weak) in enumerate(self.enemy_edits):
            enemy = data['enemies'][i] if i < len(data['enemies']) else {
                'damage_rate': 100.0, 'down_turns': 0, 'weakness': None}
            down.setValue(enemy.get('down_turns', 0))
            rate.setValue(enemy.get('damage_rate', 100.0))
            weak.setCurrentIndex(max(0, weak.findData(enemy.get('weakness'))))
        for index, controls in enumerate(self.member_edits):
            member = data['base']['members'][index]
            delta = adjust['members'][index]
            for key in ('sp', 'token', 'ep'): controls[key].setValue(delta.get(key, 0))
            controls['dp'].setValue(member.get('dp', 100.0))
            style = self.owner.setup.styles[index]
            avatar = self.member_portraits[index]
            if style:
                avatar.setPixmap(self.owner.setup.round_pixmap(style.image, 33))
                avatar.setToolTip(style.localized_title)
            else:
                avatar.setText('＋')
        self.update_enemy_edit_visibility()

    def save_adjust(self):
        data = self.state_data; adjust = data['adjustments']
        # 绝不累加到 base，也不归零：这里保存的是完整、持久的调整量。
        adjust['od'] = self.adjust_od.value()
        data['field'] = self.adjust_field.currentData()
        count = self.adjust_enemies.currentData() or 1
        data['enemies'] = [{'down_turns': down.value(), 'damage_rate': rate.value(),
                            'weakness': weak.currentData()}
                           for down, rate, weak in self.enemy_edits[:count]]
        for i, controls in enumerate(self.member_edits):
            for key in ('sp', 'token', 'ep'):
                adjust['members'][i][key] = controls[key].value()
            data['base']['members'][i]['dp'] = controls['dp'].value()

    def toggle_mode(self):
        if self.stack.currentIndex() == 0:
            self.save_combat_state(); self.load_adjust()
            self.stack.setCurrentIndex(1)
            self.switch_button.setText('返回')
            self.next_button.hide(); self.back_button.hide()
        else:
            self.save_adjust(); self.stack.setCurrentIndex(0)
            self.switch_button.setText('调整')
            self.next_button.show(); self.back_button.show()
            self.refresh()

    def refresh_enemy_info(self):
        data = self.state_data
        self.enemy_count_label.setText(f"{len(data['enemies'])} 个敌人")
        clear_layout(self.enemy_icons_row)
        for i, enemy in enumerate(data['enemies']):
            item = QVBoxLayout(); item.setSpacing(0)
            label = QLabel(str(i+1)); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item.addWidget(label)
            elem = enemy.get('weakness')
            path = ROOT_DIR / 'assets' / 'icons' / 'element' / f'{elem}.webp'
            item.addWidget(icon_label(path, 23, '—' if elem is None else ELEMENT_NAMES.get(elem, '?')),
                           alignment=Qt.AlignmentFlag.AlignCenter)
            self.enemy_icons_row.addLayout(item)
        self.enemy_icons_row.addStretch()
        clear_layout(self.field_display)
        field = data.get('field')
        if field is None:
            self.field_display.addWidget(QLabel('无场地'))
        elif field == 'rice_field':
            path = ROOT_DIR / 'assets' / 'icons' / 'status' / 'RiceFieldZone.webp'
            self.field_display.addWidget(icon_label(path, 23, '稻'))
        else:
            path = ROOT_DIR / 'assets' / 'icons' / 'status' / f'{field.capitalize()}Zone.webp'
            self.field_display.addWidget(icon_label(path, 23, FIELD_NAMES.get(field, '场')))
        self.field_display.addStretch()

    def refresh(self):
        data = self.state_data
        result = effective_state(data)
        self.title.setText(f'T{self.number}' +
                           (f"-bonus{data['bonus']}" if data.get('bonus') else '') +
                           ('-追加回合' if data.get('additional_turn') else ''))
        od_value = result['od']
        self.od_label.setText(f'{od_value:.2f}%')
        level = min(3, int(od_value // 100))
        image_path = ROOT_DIR / 'assets' / 'icons' / 'od' / f'od{level}.webp'
        pix = QPixmap(str(image_path))
        if pix.isNull(): self.od_icon.setText(f'OD{level}')
        else:
            self.od_icon.setPixmap(pix.scaled(35, 35,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
        self.refresh_enemy_info()
        available = min(3, int(od_value // 100))
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
                # 状态图标只根据本地 statuses 文件显示，缺少映射时保留空白。
                path = self.owner.status_icon(status)
                if path:
                    self.status_rows[position].addWidget(icon_label(path, 20))
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

    def state(self):
        if self.stack.currentIndex() == 1:
            self.save_adjust()
        else:
            self.save_combat_state()
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
            'QFrame#simulationSegment{border:1px solid #dce2eb;border-radius:8px;background:white}' +
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
        members = [{'sp': 0, 'token': 0, 'ep': 0, 'dp': 100.0, 'statuses': []}
                   for _ in range(6)]
        initial = {
            'base': {'od': 0.0, 'members': members},
            'adjustments': initial_adjustments(),
            'field': None,
            'enemies': copy.deepcopy(self.session['setup']['enemies']),
            'order': list(range(6)),
            'actions': ['normal_attack']*3 + ['none']*3,
            'od_timing': None, 'od_level': 0,
            'bonus': 0, 'additional_turn': False,
        }
        self.add_turn(initial)

    def add_turn(self, state):
        turn = BattleTurn(self, len(self.turns) + 1, state)
        self.turns.append(turn); self.turn_layout.addWidget(turn)
        return turn

    def truncate_after(self, turn):
        if turn not in self.turns: return
        target = self.turns.index(turn) + 1
        for later in self.turns[target:]:
            self.turn_layout.removeWidget(later)
            later.setParent(None); later.deleteLater()
        del self.turns[target:]

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
