"""
HBRTool desktop GUI. Put this file in the project root beside fight.py and hbrf/.
Requires: pip install PySide6. Game automation dependencies are only imported when running a fight.
"""
from __future__ import annotations
import json
import re
import subprocess
import signal
import os
import sys
import ctypes
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QSpinBox, QLineEdit, QScrollArea,
    QFileDialog, QMessageBox, QDialog, QCheckBox, QGroupBox,
    QTabWidget, QTabBar, QTextEdit, QFormLayout, QInputDialog, QSizePolicy)
from config import settings

from paths import ROOT_DIR, SCRIPTS_DIR
ROOT = ROOT_DIR
SCRIPTS = SCRIPTS_DIR
DATA = ROOT / 'assets' / 'char-data'
IMAGES = ROOT / 'assets' / 'char-images'
ICONS = ROOT / 'assets' / 'icons'

# Database layout: each team JSON maps character names to character records.
# Each character has style, skill.common, and skill[style_name].
# 优先采用国服命名
def display_name(record, fallback=''):
    names = record.get('names', {})
    return names.get('zh-CN-CN') or names.get('zh-CN') or record.get('value', fallback)

# 获得主动技能列表
def active_skill_names(group):
    # Nested "passive skill" and "command action" are not normal skill buttons.
    if not isinstance(group, dict):
        return []
    return [skill.get('value', name) for name, skill in group.items()
            if isinstance(skill, dict) and 'sp' in skill and name not in ('passive skill', 'command action')]


@dataclass
class Style:
    name: str                   # canonical character name (HBRF identifier)
    english: str
    sid: str
    title: str                  # canonical style title
    team: str
    tier: str
    elements: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # 风格特有技能
    image: Path | None = None
    label: str = ''             # 保存国服角色名
    localized_title: str = ''   # 保存国服风格名


class Catalog:
    def __init__(self):
        self.styles: list[Style] = []
        self.common_global: list[str] = []  # 光球等通用技能的value
        self.common_by_name: dict[str, list[str]] = {}  # 角色特有的技能value
        self.skill_data = {}  # 技能value查找技能名称、sp等数据
        self.command_styles = set()  # 保存是ADM的角色名和风格名
        self.switch_pairs = {}  # [角色名，技能名] = 切换后技能名
        self.special_styles = {}  # 保存所有'exclude'中字典
        special_file = DATA / 'special_skills.json'
        if special_file.exists():
            special = json.loads(special_file.read_text(encoding='utf-8'))
            self.special_styles = special.get('exclude', {})
            for character, groups in special.get('switchable', {}).items():
                for style_name, entries in groups.items():
                    for name, entry in entries.items():
                        self.switch_pairs[(character, entry["value"])] = entry['link']
        if not DATA.exists():
            return
        for path in sorted(DATA.glob('*.json')):
            raw = json.loads(path.read_text(encoding='utf-8'))
            if path.stem == 'common_skills':
                self.common_global = [x['value'] for x in raw.get('defaultSkills', [])
                                      if isinstance(x, dict) and 'value' in x]
                for x in raw.get('defaultSkills', []):
                    if isinstance(x, dict) and 'value' in x: self.skill_data[x['value']] = x
            elif path.stem != 'special_skills':
                self._load_team(raw, path.stem)

    def _load_team(self, raw, team):
        # 对每个角色
        for character_key, ch in raw.items():
            if not isinstance(ch, dict):
                continue
            name = ch.get('value', character_key)
            english = ch.get('english name', '')
            # 存储角色通用的技能
            groups = ch.get('skill', {})
            common = active_skill_names(groups.get('common', {}))
            self.common_by_name[name] = list(dict.fromkeys(common))
            for group in groups.values():
                if isinstance(group, dict):
                    for key, entry in group.items():
                        if isinstance(entry, dict) and 'sp' in entry:
                            self.skill_data[entry.get('value', key)] = entry
            # 存储风格特有的技能
            for style_key, entry in ch.get('style', {}).items():
                sid_value = entry.get('id', '')
                ids = sid_value if isinstance(sid_value, list) else [sid_value]
                title = entry.get('value', style_key)
                skills = active_skill_names(groups.get(style_key, {}))
                # 司令的鬼神化和waki的魔界骑兵忽略
                if title == "希望的晨曦" and "鬼神化" in skills:
                    skills.remove("鬼神化")
                if title == "高傲魔王的凱旋歸來" and "魔界騎兵起動！" in skills:
                    skills.remove("魔界騎兵起動！")
                command_group = groups.get(style_key, {}).get('command action', {})
                if isinstance(command_group, dict) and command_group:
                    self.command_styles.add((name, title))
                    for key, entry_command in command_group.items():
                        # 会多次加入指挥行动进skill_data，但会覆盖没影响
                        if isinstance(entry_command, dict) and 'sp' in entry_command:
                            skills.insert(0, entry_command.get('value', key))
                            self.skill_data[entry_command.get('value', key)] = entry_command
                # 生成风格Style类
                for sid in ids:
                    # 可怜只保留009-1
                    if title == "CODE:Virtual Killer" and sid == "009-2":
                        continue
                    sid = str(sid)
                    image_path = IMAGES / team / english / f'{sid}.webp'
                    self.styles.append(Style(
                        name=name, english=english, sid=sid, title=title,
                        team=team, tier=str(entry.get('tier', '')),
                        elements=list(entry.get('ele', [])), skills=skills,
                        image=image_path if image_path.is_file() else None,
                        label=display_name(ch, name),
                        localized_title=display_name(entry, title)))

    # 风格可以使用的技能列表
    def skills_for(self, style):
        if style is None:
            return []
        return list(dict.fromkeys(style.skills +
                                  self.common_by_name.get(style.name, []) +
                                  self.common_global))

    # 确保ADM的默认是指挥行动   
    def default_action(self, style):
        if style is None: return '普通攻击'
        # Styles containing the command action cannot use an ordinary attack.
        return '指揮行動' if (style.name, style.title) in self.command_styles else '普通攻击'

    # 确认目标风格是否是有特殊前排技能的风格，并返回特殊技能名称
    def special_for(self, style):
        return self.special_styles.get(style.name, {}).get(style.title) if style else None

    # 给出选择技能下拉栏里的技能名称（有sp显示）
    def skill_label(self, name):
        if name == '普通攻击': return '普通攻击'
        if name == '指揮行動': return '指挥行动'
        if name in ('切换姿态', '鬼神化'): return f'{name}（特殊行动）'
        data = self.skill_data.get(name, {})
        localized = display_name(data, name)
        return f'{localized}（{data.get("sp", "?")} SP）'
    
    # 给出技能的国服简称
    def skill_zh(self, name):
        return display_name(self.skill_data.get(name, {}), name)

    # 确认目标风格的技能是否是可切换的
    def linked(self, style, skill):
        return self.switch_pairs.get((style.name, skill)) if style else None

    # 根据筛选条件找到目标风格，返回Style类
    def find_style(self, team, english, sid):
        return next((s for s in self.styles if s.team == team and
                     s.english == english and s.sid == str(sid)), None)

def round_pixmap(path, size=76):
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    if path and Path(path).exists():
        src = QPixmap(str(path))
        if not src.isNull():
            src = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
            p = QPainter(out)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            mask = QPainterPath()
            mask.addEllipse(0, 0, size, size)
            p.setClipPath(mask)
            p.drawPixmap(0, 0, src)
            p.end()
    return out

TEAM_ORDER = ['31A', '31B', '31C', '31D', '31E', '31F',
              '31X', '30G', '19A', 'Command', '31AB', 'P5R']


class NoWheelComboBox(QComboBox):
    """Keep mouse-wheel scrolling from accidentally changing turn actions."""
    def wheelEvent(self, event):
        event.ignore()

ELEMENT = {"Fire": "火", "Ice": "冰", "Thunder": "雷", "Dark": "暗", "Light": "光", "Void": "虚"}
def element_zh(element):
    return ELEMENT.get(element, "无")

class StyleDialog(QDialog):
    # Only dropdown filters persist between dialog instances; keyword searches do not.
    last_filters = ('SS/SSR', None, None)
    CELL = 100

    def __init__(self, catalog, occupied, parent=None):
        super().__init__(parent)
        self.catalog, self.chosen, self.occupied = catalog, None, occupied
        self.setWindowTitle('选择风格')
        self.resize(900, 650)
        # box行堆积排列控件，只负责管理位置，不负责显示widget
        layout = QVBoxLayout(self)  # 传self的顶层垂直布局
        filters = QHBoxLayout()  # 上端的筛选相关控件，水平布局
        # 搜索框建立与加入布局
        self.search = QLineEdit(); self.search.setPlaceholderText('搜索角色 / 风格')
        filters.addWidget(self.search, 3)
        self.tier = QComboBox(); self.element = QComboBox(); self.team = QComboBox()
        self.tier.addItem('稀有度：SS/SSR', 'SS/SSR')  # item有text和data和index三个属性
        self.tier.addItem('稀有度：全部', None)
        for tier in sorted({x.tier for x in catalog.styles if x.tier}):
            self.tier.addItem(f'稀有度：{tier}', tier)
        self.element.addItem('属性：全部', None)
        self.element.addItem('属性：无', 'None')
        for element in sorted({e for x in catalog.styles for e in x.elements if e}):
            self.element.addItem(f'属性：{element_zh(element)}', element)
        self.team.addItem('队伍：全部', None)
        for team in sorted({x.team for x in catalog.styles if x.team},
                           key=lambda x: (TEAM_ORDER.index(x) if x in TEAM_ORDER else len(TEAM_ORDER), x)):
            self.team.addItem(f'队伍：{team}', team)
        for combo, value in zip((self.tier, self.element, self.team), self.last_filters):
            ix = combo.findData(value)
            if ix >= 0: combo.setCurrentIndex(ix)
            filters.addWidget(combo)
        layout.addLayout(filters)
        # 下侧的风格显示，QScrollArea → content(QWidget) → QGridLayout
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.content = QWidget(); self.grid = QGridLayout(self.content)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grid.setSpacing(5)
        self.scroll.setWidget(self.content); layout.addWidget(self.scroll)
        self.buttons = []  # 存储风格图片
        self.columns = 0
        self.search.textChanged.connect(self.refresh)
        for c in (self.tier, self.element, self.team):
            c.currentIndexChanged.connect(self._filter_changed)
        self.refresh()
        # Initial viewport geometry is not valid until Qt has shown the dialog.
        QTimer.singleShot(0, self._reflow)
        self.scroll.viewport().installEventFilter(self)

    # 刚显示出时自动调用
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow)

    # 监视滚动区域viewport面积变化
    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._reflow)
        return super().eventFilter(watched, event)

    def _filter_changed(self):
        StyleDialog.last_filters = (self.tier.currentData(), self.element.currentData(), self.team.currentData())
        self.refresh()

    def refresh(self):
        # 清除旧布局
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        tier, element, team = self.tier.currentData(), self.element.currentData(), self.team.currentData()
        items = [s for s in self.catalog.styles if s.name not in self.occupied
                 and (tier is None or (s.tier in ('SS', 'SSR') if tier == 'SS/SSR' else s.tier == tier))
                 and (element is None or (not s.elements if element == 'None' else element in s.elements))
                 and (team is None or s.team == team)
                 and self.search.text().lower() in f'{s.name} {s.label} {s.title} {s.localized_title} {s.sid} {s.english}'.lower()]
        self.buttons = []
        if not items:
            self.grid.addWidget(QLabel('没有匹配的风格；请检查数据库字段或筛选条件。'), 0, 0)
        else:
            # Keep character/style order within each team; never order by filter results.
            items.sort(key=lambda s: TEAM_ORDER.index(s.team) if s.team in TEAM_ORDER else len(TEAM_ORDER))
            for style in items:
                b = QPushButton()
                b.setFixedSize(94, 94)
                b.setIcon(QIcon(round_pixmap(style.image, 80)))
                b.setIconSize(QSize(80, 80))
                b.setToolTip(f'{style.label} · {style.localized_title}\n{style.team} / {style.tier} / {style.sid}')
                b.clicked.connect(lambda _=False, selected=style: self.select(selected))
                self.buttons.append(b)
            self._reflow()

    # 面积变化时重新自适应调整布局
    def _reflow(self):
        if not self.buttons: return
        width = self.scroll.viewport().width()
        margins = self.grid.contentsMargins()
        available = max(1, width - margins.left() - margins.right())
        columns = max(1, (available + self.grid.horizontalSpacing()) // (94 + self.grid.horizontalSpacing()))
        # 面积变化但较小，不改变布局
        if columns == self.columns and self.grid.count() == len(self.buttons): return
        self.columns = columns
        while self.grid.count(): self.grid.takeAt(0)
        for i, button in enumerate(self.buttons):
            self.grid.addWidget(button, i // columns, i % columns)

    # 整个对话框尺寸变化时调用
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    # 绑定在风格图片上，被点击时结束窗口返回accept并保存被选中的style
    def select(self, style):
        self.chosen = style
        self.accept()

class TurnRow(QGroupBox):
    # 一般回合内行动控件，能够向主界面emit删除、复制和自己的信号
    remove_requested = Signal(object)
    copy_requested = Signal(object)
    move_requested = Signal(object, int)
    def __init__(self, parent_editor, state=None):
        super().__init__('回合')
        self.setObjectName('turnRow')  # 用于单独改变背景颜色
        self.editor = parent_editor
        outer = QVBoxLayout(self)
        # head包括turn，od，bonus，追加，发动od和定制label，以及信号控件
        head = QHBoxLayout()
        self.turn_no = NoWheelComboBox(); self.turn_no.addItems([f'T{i}' for i in range(1, 21)])
        self.extra = NoWheelComboBox(); self.extra.addItems(['普通回合', '追加回合'])
        self.bonus = NoWheelComboBox(); self.bonus.setMinimumWidth(155); self.bonus.addItem('无 Bonus')
        self.bonus.currentIndexChanged.connect(self.update_background)
        # 需要把index的0到6映射为-3到3
        self.od = NoWheelComboBox(); self.od.addItems(['无 OD', '前置 OD1', '前置 OD2', '前置 OD3', '后置 OD1', '后置 OD2', '后置 OD3'])
        # od变化要影响bonus选择
        self.od.currentIndexChanged.connect(self.refresh_bonus)
        self.od.currentIndexChanged.connect(self.refresh_check_od)
        # OD发动设置和凹追击
        self.activate_od = QCheckBox('发动')
        self.activate_od.toggled.connect(self.refresh_check_od)
        self.check_od = QCheckBox('须凹追击')
        self.check_od.setEnabled(False)
        
        self.custom_label = QLineEdit(); self.custom_label.setPlaceholderText('自定义 label（非空时优先使用）')
        for w in (self.turn_no, self.extra, self.bonus, self.od, self.activate_od, self.check_od):
            head.addWidget(w)
        head.addWidget(self.custom_label, 2)
        for label, callback in [('↑',lambda: self.move_requested.emit(self,-1)),('↓',lambda: self.move_requested.emit(self,1)),
                                ('复制',lambda: self.copy_requested.emit(self)),('删除',lambda: self.remove_requested.emit(self))]:
            b = QPushButton(label); b.clicked.connect(callback); head.addWidget(b)
        # 右上角标index
        self.index_label = QLabel(); self.index_label.setStyleSheet('color: #7A8494; font-size: 9pt;'); head.addWidget(self.index_label)
        outer.addLayout(head)
        # body部分是role，skill和target
        body = QHBoxLayout()
        self._syncing = False
        self._front_swap_source = None  # 存储第一次点击的source
        self.position_buttons = []
        self.roles, self.skills, self.targets = [], [], []
        for i in range(3):
            col = QVBoxLayout()
            r = NoWheelComboBox(); s = NoWheelComboBox(); t = NoWheelComboBox()
            # 角色变化要影响技能选择
            r.currentIndexChanged.connect(lambda _=0, index=i: self._role_changed(index))
            position_button = QPushButton(f'前排 {i+1}  ⇄')
            position_button.setToolTip('点击一个前排位置，再点击另一个位置以交换')
            position_button.clicked.connect(lambda _=False, index=i: self.select_front_swap(index))
            col.addWidget(position_button)
            self.position_buttons.append(position_button)
            # 技能变化（特殊技能）影响其他人技能选择
            s.currentIndexChanged.connect(lambda _=0, index=i: self._skill_changed(index))
            col.addWidget(r); col.addWidget(s); col.addWidget(t)
            body.addLayout(col)
            self.roles.append(r); self.skills.append(s); self.targets.append(t)
        outer.addLayout(body)
        if state: self.load_state(state)
        else: 
            self.refresh_roles()
            self.refresh_bonus()
            self.refresh_check_od()

    # 点击两个前排标题即可交换完整行动（角色、技能和目标）。
    def select_front_swap(self, index):
        buttons = self.position_buttons
        # 第一次点击，储存在_front_swap_source中并显示选中样式
        if self._front_swap_source is None:
            self._front_swap_source = index
            buttons[index].setStyleSheet('QPushButton { background: #dbeafe; border: 1px solid #2563eb; }')
            return
        # 第二次点击，恢复_front_swap_source为空
        source = self._front_swap_source
        self._front_swap_source = None
        for button in buttons:
            button.setStyleSheet('')
        # 如果第二次和第一次点击相同则不换位
        if source == index:
            return
        # 第一次和第二次点击不同则换位
        moves = self.state()['moves']
        moves[source], moves[index] = moves[index], moves[source]
        self.refresh_roles(moves)

    # 所选角色去重，重复的旧的恢复为“选择角色”默认项，最后更新当前的skill
    def _role_changed(self, index):
        selected = self.roles[index].currentData()
        if selected:
            for j, other in enumerate(self.roles):
                if j != index and other.currentData() == selected:
                    other.blockSignals(True)
                    other.setCurrentIndex(0)
                    other.blockSignals(False)
                    self.update_skills(j)
        self.update_skills(index)

    def refresh_roles(self, saved=None):
        saved = saved or [(r.currentData(), s.currentData(), t.currentData()) for r,s,t in zip(self.roles,self.skills,self.targets)]
        # 更改现在可以选择的角色并还原已经选了的角色和技能
        for i, r in enumerate(self.roles):
            r.blockSignals(True); r.clear()
            r.addItem('选择角色', 0)
            for j, style in enumerate(self.editor.slots, 1):
                if style: r.addItem(f'{j} · {self.editor.nickname(j)}', j)
            ix = r.findData(saved[i][0]); r.setCurrentIndex(ix if ix >= 0 else 0)
            r.blockSignals(False)
            self.update_skills(i, saved[i][1], saved[i][2])
        # 角色去重
        for i, r in enumerate(self.roles):
            if r.currentData():
                for j in range(i):
                    if self.roles[j].currentData() == r.currentData():
                        self.roles[j].blockSignals(True)
                        self.roles[j].setCurrentIndex(0)
                        self.roles[j].blockSignals(False)
                        self.update_skills(j)
        self._sync_special()

    def update_skills(self, i, skill=None, target=None):
        # 获取当前style，skill，target
        r, s, t = self.roles[i], self.skills[i], self.targets[i]
        if skill is None: skill = s.currentData()
        if target is None: target = t.currentData()
        slot = r.currentData() or 0
        style = self.editor.slots[slot - 1] if slot else None
        # 清除原skill并获取默认skill
        default = self.editor.catalog.default_action(style)
        s.blockSignals(True); t.blockSignals(True)
        s.clear()
        s.addItem(self.editor.catalog.skill_label(default), default)
        # 添加特殊行动的skill
        special = self.editor.catalog.special_for(style)
        if special: s.addItem(f'{special}（特殊行动）', f'@special:{special}')
        # 添加其他skill
        for name in self.editor.catalog.skills_for(style):
            if name != default: s.addItem(self.editor.catalog.skill_label(name), name)
        # 如果之前的选中的技能现在角色也有，则恢复技能，没有就默认技能
        ix = s.findData(skill)
        s.setCurrentIndex(ix if ix >= 0 else 0)
        # 目标也按类似处理
        t.clear(); t.addItem('无目标', None)
        for j, selected_style in enumerate(self.editor.slots, 1):
            if selected_style: t.addItem(self.editor.nickname(j), j)
        t.addItem('双体左 / 三体中', 8)
        t.addItem('双体右 / 三体右', 9)
        t.addItem('三体左', 7)
        ix = t.findData(target); t.setCurrentIndex(max(0, ix))
        s.blockSignals(False); t.blockSignals(False)
        self._skill_changed(i)

    # 负责禁止指挥行动和特殊技能选择目标
    def _skill_changed(self, i):
        skill = self.skills[i].currentData()
        no_target = skill == '指揮行動' or (isinstance(skill,str) and skill.startswith('@special:'))
        if no_target: self.targets[i].setCurrentIndex(0)
        self.targets[i].setEnabled(not no_target)
        self._sync_special(i)

    def _sync_special(self, source=None):
        # 防止_sync_special→indexchange→_sync_special递归调用
        if self._syncing: return
        self._syncing = True
        try:
            # 先确定special技能的位置
            special_indices = [i for i, s in enumerate(self.skills) if str(s.currentData() or '').startswith('@special:')]
            if len(special_indices) > 1 and source in special_indices:
                special_indices = [source]
            # 有特殊技能时其他角色只能默认技能无目标，不允许其他选项
            if special_indices:
                active = special_indices[0]
                for i, s in enumerate(self.skills):
                    if i != active:
                        slot = self.roles[i].currentData() or 0
                        style = self.editor.slots[slot-1] if slot else None
                        default = self.editor.catalog.default_action(style)
                        ix = s.findData(default)
                        if ix >= 0: s.setCurrentIndex(ix)
                        self.targets[i].setCurrentIndex(0)
                        s.setEnabled(False); self.targets[i].setEnabled(False)
                    else: s.setEnabled(True)
            # 无特殊技能了就允许重新打开选项，指挥行动仍然默认无目标
            else:
                for i, s in enumerate(self.skills):
                    s.setEnabled(True)
                    skill = s.currentData()
                    self.targets[i].setEnabled(skill != '指揮行動')
        finally:
            self._syncing = False

    # 更改od数时触发，用于更改bonus选项
    def refresh_bonus(self):
        previous = self.bonus.currentText()
        od = abs(self.od_value())
        self.bonus.blockSignals(True)
        self.bonus.clear()
        # 不处于od中
        if od == 0:
            self.bonus.addItem('无 Bonus')
            self.bonus.setEnabled(False)
        # 处于od中
        else:
            # 后置od多一个od前的选项
            if self.od_value() > 0:
                self.bonus.addItem(f'OD前')
            self.bonus.setEnabled(True)
            for j in range(1, od + 1):
                self.bonus.addItem(f'OD{od}-bonus{j}')

        selected = self.bonus.findText(previous)
        self.bonus.setCurrentIndex(selected if selected >= 0 else 0)
        self.bonus.blockSignals(False)
        self.update_background()

    # 根据head里的选项生成label
    def label_text(self):
        if self.custom_label.text().strip(): return self.custom_label.text().strip()
        chunks = [self.turn_no.currentText()]
        
        if self.od_value() != 0: 
            prefix = "前置" if self.od_value() < 0 else "后置"
            bonus = self.bonus.currentText()
            chunks.append(prefix + (f'OD{abs(self.od_value())}-OD前' if bonus == 'OD前' else bonus))
        if self.extra.currentIndex(): chunks.append('追加')
        return '-'.join(chunks)

    # 传入实际写入hbrf的内容，匹配为head中相应选项或写为custom label
    @staticmethod
    def parse_label(label, execution_od=0):
        match = re.fullmatch(
            r'T(20|1\d|[1-9])(?:-(前置|后置)(OD([123])-bonus([123])|OD([123])-OD前))?(-追加)?',
            label
        )
        if not match:
            return dict(label=label)

        turn, direction, bonus_text, level, bonus, post_level, extra = match.groups()
        level = int(level or post_level or 0)

        # bonus超出od范围
        if bonus and int(bonus) > level:
            return dict(label=label)

        # 前置od出现“OD”前选项
        if direction == '前置' and post_level:
            return dict(label=label)

        # 把level还原为0-6的od
        if execution_od:
            if not direction or level != abs(execution_od) or (execution_od < 0) != (direction == '前置'):
                return dict(label=label)
            od = -execution_od if execution_od < 0 else execution_od + 3
        else:
            od = (level if direction == '前置' else level + 3) if direction else 0

        return dict(
            turn=int(turn)-1,
            extra=int(bool(extra)),
            od=od,
            bonus_text='OD前' if post_level else (bonus_text or '无 Bonus'),
            label=''
        )

    # index 0到6 转换为hbrf的 -3到3
    def od_value(self):
        ix = self.od.currentIndex()
        return 0 if ix == 0 else -ix if ix <= 3 else ix - 3

    # 若check了发动选框则返回hbrf中的-3到3指令，否则不发动od
    def execution_od(self):
        return self.od_value() if self.activate_od.isChecked() else 0

    # 凹追击需要在execution_od情况下才允许勾选
    def refresh_check_od(self):
        def set_checkbox_color(checkbox, enabled):
            if enabled:
                checkbox.setStyleSheet("QCheckBox { color: black; }")
            else:
                checkbox.setStyleSheet("""
                    QCheckBox {
                        color: gray;
                    }
                    QCheckBox::indicator:disabled {
                        background-color: #E0E0E0;
                        border: 1px solid #999999;
                        border-radius: 3px;
                    }
                """)
        # 无 OD 时禁止勾选发动
        has_od = self.od.currentIndex() != 0

        if not has_od:
            self.activate_od.setChecked(False)

        self.activate_od.setEnabled(has_od)

        # 只有勾选发动后才能勾选凹追击
        enabled = has_od and self.activate_od.isChecked()

        if not enabled:
            self.check_od.setChecked(False)

        self.check_od.setEnabled(enabled)

        set_checkbox_color(self.activate_od, has_od)
        set_checkbox_color(self.check_od, enabled)

    # 改变背景颜色的函数，被bonus更改（和od更改）触发
    def update_background(self):
        colors = {
            1: '#F8DFEA',  # OD1 粉
            2: '#DDF5F1',  # OD2 青
            3: '#FAEFC6',  # OD3 黄
        }

        bonus = self.bonus.currentText()
        match = re.search(r'^OD([123])', bonus)
        color = colors[int(match.group(1))] if match else 'white'

        self.setStyleSheet(
            f'QGroupBox#turnRow {{background-color: {color};}}'
        )

    # 保存状态
    def state(self):
        return dict(turn=self.turn_no.currentIndex(), extra=self.extra.currentIndex(), bonus=self.bonus.currentIndex(), bonus_text=self.bonus.currentText(),
        od=self.od.currentIndex(), activate_od=self.activate_od.isChecked(), check_od=self.check_od.isChecked(), label=self.custom_label.text(),
        moves=[(r.currentData(),s.currentData(),t.currentData()) for r,s,t in zip(self.roles,self.skills,self.targets)])

    # 重新load已经存在的状态
    def load_state(self, state):
        self.turn_no.setCurrentIndex(state.get('turn',0))
        self.extra.setCurrentIndex(state.get('extra',0))
        self.od.setCurrentIndex(state.get('od',0))
        self.activate_od.setChecked(state.get('activate_od', False))
        self.refresh_check_od()
        self.check_od.setChecked(state.get('check_od', False) and self.check_od.isEnabled())
        self.refresh_bonus()
        bonus = state.get('bonus_text', '')
        index = self.bonus.findText(bonus) if bonus else state.get('bonus', 0)
        self.bonus.setCurrentIndex(index if 0 <= index < self.bonus.count() else 0)
        self.custom_label.setText(state.get('label',''))
        self.refresh_roles(state.get('moves',[(0,'普通攻击',None)]*3))

class EventRow(QGroupBox):
    remove_requested = Signal(object)
    copy_requested = Signal(object)
    move_requested = Signal(object, int)

    def __init__(self, kind, state=None, available=None):
        super().__init__('异时层行动' if kind == 'yishi' else '特殊回合行动')
        self.kind = kind
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel('行动'))
        self.action = NoWheelComboBox()
        # 异时层行动
        if kind == 'yishi':
            self.action.addItem('跳过剧情', 'skip')
            self.action.addItem('切换队伍', 'change')
        # 特殊回合行动
        else:
            self.refresh_choices(available or [])
        layout.addWidget(self.action, 1)
        for label, callback in [('↑',lambda: self.move_requested.emit(self,-1)),
                                ('↓',lambda: self.move_requested.emit(self,1)),
                                ('复制',lambda: self.copy_requested.emit(self)),
                                ('删除',lambda: self.remove_requested.emit(self))]:
            b=QPushButton(label); b.clicked.connect(callback); layout.addWidget(b)
        # 右上角index编号
        self.index_label = QLabel(); self.index_label.setStyleSheet('color: #7A8494; background: white; font-size: 9pt;'); layout.addWidget(self.index_label)
        if state:
            ix=self.action.findData(state['action'])
            if ix>=0: self.action.setCurrentIndex(ix)

    # 新建和slot选角变化时调用，available传入mainwindow中检测可行的小按钮
    def refresh_choices(self, available):
        from config import templates as tpl
        current = self.action.currentData()
        labels = {'waki': '魔界骑兵', 'attack': '总攻击'}
        self.action.blockSignals(True)
        self.action.clear()
        for command in tpl.GLOBAL_BUTTON_CONFIG:
            if command in available:
                self.action.addItem(labels.get(command, command), command)
        # 有current就恢复，没有就清空/选择其他合法小按钮
        index = self.action.findData(current)
        if index >= 0: self.action.setCurrentIndex(index)
        # 此时没有可选择的action就不能展开选框
        have_choice = self.action.count() > 0
        self.action.setEnabled(have_choice)
        self.action.blockSignals(False)
        # 用于弹窗提示，返回true则无弹窗，即有行动/一直没有行动，只有原来有现在没有才弹窗
        return current is None or have_choice

    def state(self):
        return {'action': self.action.currentData(), 'kind': self.kind}

def setup_worker_output():
    """EXE 子进程使用 UTF-8 向 GUI 的 PIPE 输出日志。"""
    import io
    import msvcrt
    import os
    import ctypes

    handle = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    if handle in (0, ctypes.c_void_p(-1).value):
        raise OSError('子进程标准输出管道不可用')

    fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
    binary = os.fdopen(fd, 'wb', buffering=0)
    sys.stdout = io.TextIOWrapper(
        binary,
        encoding='utf-8',
        errors='replace',
        write_through=True
    )
    sys.stderr = sys.stdout

# 被Qt调用的线程，这里实际开启了一个新进程，运行run_battle.py，并把报错等传回日志框中。等待添加logger
class Worker(QThread):
    log_text = Signal(str)
    finished_text = Signal(str)

    def __init__(self, path, repeated, count, ticket, auto_close, title, mode='battle'):
        super().__init__()
        self.mode = mode  # battle 对应普通战斗，card 对应技术模拟战
        self.args = ([str(count), title] if mode == 'card' else
                     [str(path), str(int(repeated)), str(count), ticket,
                      str(int(auto_close)), title])
        self.process = None
        self.stopping = False

    def run(self):
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        # 两种运行入口分别启动独立子进程，避免中断时直接终止 GUI 线程
        entry = 'run_card_game.py' if self.mode == 'card' else 'run_battle.py'
        # 打包后用同一个 EXE 的子命令进入工作模式，不再执行独立的 py 文件
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, '--hbr-worker', self.mode, *self.args]
        else:
            cmd = [sys.executable, '-X', 'utf8', '-u', str(ROOT / entry), *self.args]
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, creationflags=flags,
                start_new_session=sys.platform != 'win32'
            )
            # 将子进程的 print、logging 和异常信息转发到当前 Tab 的日志窗口
            for line in self.process.stdout:
                self.log_text.emit(line.rstrip('\r\n'))
            code = self.process.wait()
            if self.stopping:
                self.finished_text.emit('打牌已终止' if self.mode == 'card' else '战斗已终止')
            elif code == 0:
                self.finished_text.emit('执行完成')
            else:
                self.finished_text.emit(f'执行失败，退出码：{code}')
        except Exception:
            self.finished_text.emit(traceback.format_exc())
        finally:
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait()

    # 终止进程函数
    def stop(self):
        # 第二次进入强制kill
        if self.stopping:
            if self.process and self.process.poll() is None:
                self.process.kill()
            return

        # 首次先使用类Ctrl+C的终止信号
        self.stopping = True
        if not self.process or self.process.poll() is not None: return
        try:
            if sys.platform == 'win32':
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(self.process.pid, signal.SIGINT)
        except (OSError, ValueError):
            self.process.terminate()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('HBRTool')
        self.resize(1120, 800)
        self.catalog = Catalog()
        self.slots = [None] * 6  # list[Style]
        self.nicknames = [''] * 6
        self.rows = []
        self.other_actions = [] # Legacy actions not yet supported by the editor
        self.current_path = None
        self.worker = None
        self._build()
        self.add_row()

    def _build(self):
        # 中央控件
        tabs = QTabWidget(); self.setCentralWidget(tabs)
        # 编辑器tab
        edit = QWidget(); tabs.addTab(edit, 'HBRF 编辑器')
        root = QVBoxLayout(edit)
        # 新建、打开、保存工具栏
        toolbar = QHBoxLayout()
        for title, callback in [('新建',self.new),('打开 HBRF',self.open_file),('打开 SAV',self.open_sav),('打开 jpg',self.open_jpg),('保存',self.save),('另存为',lambda: self.save(True))]:
            b = QPushButton(title); b.clicked.connect(callback); toolbar.addWidget(b)
        toolbar.addStretch(); root.addLayout(toolbar)
        # 角色slot
        slots_box = QGroupBox('队伍 · Slot 1–6（点击设置风格；右键清空；点击交换角色以调整位置）')
        slots_layout = QHBoxLayout(slots_box)
        self.slot_buttons = []
        self.slot_swap_source = None  # 储存第一次点击的角色
        self.slot_swap_mode = QPushButton('交换角色：关闭')
        self.slot_swap_mode.setCheckable(True)
        self.slot_swap_mode.toggled.connect(self.set_slot_swap_mode)
        toolbar.addWidget(self.slot_swap_mode)
        for i in range(6):
            col = QVBoxLayout()
            b = QPushButton('＋'); b.setFixedSize(92,92)
            # 普通模式点击选风格；交换模式点击两个槽位来交换
            b.clicked.connect(lambda _=False, ix=i: self.handle_slot_click(ix))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _=None, ix=i: self.clear_style(ix))
            # 昵称
            label = QLineEdit(); label.setPlaceholderText(f'Slot {i+1} · 昵称（可选）')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.editingFinished.connect(lambda ix=i, w=label: self.change_nickname(ix, w.text()))
            col.addWidget(b, alignment=Qt.AlignmentFlag.AlignCenter); col.addWidget(label)
            slots_layout.addLayout(col); self.slot_buttons.append((b,label))
        root.addWidget(slots_box)
        # 创建可滚动的row编辑区
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.rows_holder = QWidget(); self.rows_layout = QVBoxLayout(self.rows_holder)
        self.rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.rows_holder); root.addWidget(self.scroll)
        # 添加底部行动按钮：左侧追加一个行动，右侧按指定序号批量插入
        add_actions = QHBoxLayout()
        for title, kind in [('异时层行动', 'yishi'), ('添加回合', 'turn'), ('特殊回合行动', 'special')]:
            button_pair = QHBoxLayout()
            button_pair.setSpacing(0)  # 两个按钮紧贴
            b = QPushButton('＋ ' + title)
            b.setObjectName('normalAddButton')
            b.clicked.connect(lambda _=False, k=kind: self.add_row(kind=k))
            batch = QPushButton('批量添加')
            batch.setObjectName('batchAddButton')
            batch.clicked.connect(lambda _=False, k=kind: self.batch_add_rows(k))
            button_pair.addWidget(b, 7)
            button_pair.addWidget(batch, 3)
            add_actions.addLayout(button_pair, 1 if kind != 'turn' else 2)
        root.addLayout(add_actions)
        root.addWidget(QLabel('提示：HBRF 限制每回合恰好 3 个不同角色行动，且每名角色最多记录 6 个技能。'))
        # 普通战斗 tab，先设置窗口权限与脚本，再选择单次或重复战斗
        runner = QWidget(); tabs.addTab(runner, '普通战斗')
        form = QFormLayout(runner)
        self.window_title = QLineEdit('HeavenBurnsRed')
        form.addRow('游戏窗口标题', self.window_title)
        self.admin_status = QLabel('管理员：' + ('是' if self.is_admin() else '否'))
        form.addRow('当前权限', self.admin_status)
        admin = QPushButton('以管理员身份重启 GUI（Windows）')
        admin.clicked.connect(self.restart_admin)
        form.addRow(admin)
        # 在正式运行前检测窗口，同时确定游戏分辨率
        test = QPushButton('寻找并激活窗口')
        test.clicked.connect(lambda: self.test_window())
        form.addRow(test)
        self.run_path = QLineEdit()
        self.run_path.setPlaceholderText('未指定则使用当前编辑器脚本')
        self.run_path.editingFinished.connect(self.preview_run_file)
        select = QPushButton('选择脚本')
        select.clicked.connect(self.select_run_file)
        pathrow = QHBoxLayout(); pathrow.addWidget(self.run_path); pathrow.addWidget(select)
        form.addRow('HBRF 路径', pathrow)
        # 勾选后先关闭自动战斗；空行动脚本可以配合游戏内自动战斗使用
        self.auto_close = QCheckBox(
            '战斗前关闭自动战斗（需要自动战斗则不勾选，并上传无任何行动的空 HBRF 文件）'
        )
        self.auto_close.setChecked(True)
        auto_close_row = QHBoxLayout()
        auto_close_row.addStretch(); auto_close_row.addWidget(self.auto_close); auto_close_row.addStretch()
        form.addRow(auto_close_row)

        # 等宽等高的两栏；高度只取右侧表单的建议高度，不占满页面
        battle_modes = QHBoxLayout()
        single_box = QGroupBox('执行单次战斗')
        single_layout = QVBoxLayout(single_box)
        # 提示用户分辨率支持
        resolution_note = QLabel(                         
            '目前支持的分辨率为：\n'
            '(1680, 1050)、(1920, 1200)、(2560, 1600)、\n'
            '(2048, 1152)、(2160, 1215)、(2560, 1440)。\n'
            '如果关闭自动战斗等功能失效，可以换个分辨率再尝试'
        )
        resolution_note.setWordWrap(True)
        resolution_note.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # 单次战斗按钮
        play = QPushButton('执行单次战斗')
        play.clicked.connect(lambda: self.start_run(False))
        # 尾部注意note
        single_note = QLabel('注意：请进入战斗后执行单次战斗')
        single_note.setWordWrap(True)
        # 按顺序加入layout
        single_layout.addWidget(resolution_note)
        single_layout.addStretch(1)
        single_layout.addWidget(play)
        single_layout.addWidget(single_note)

        repeat_box = QGroupBox('光球重复刷取')
        repeat_layout = QVBoxLayout(repeat_box)
        # 选择战斗次数和道具表单
        repeat_form = QFormLayout()
        self.run_count = QSpinBox()
        self.run_count.setRange(1, 9999); self.run_count.setValue(1)
        # 下拉栏显示中文，itemData 仍传给 repetition.py 的英文参数
        self.ticket = QComboBox()
        self.ticket.addItem('体力石', 'stone')
        self.ticket.addItem('门票', 'ticket')
        self.ticket.addItem('备用体力石', 'spare')
        repeat_form.addRow('重复次数', self.run_count)
        repeat_form.addRow('体力类型', self.ticket)
        # 执行重复战斗按钮
        repeat = QPushButton('执行重复战斗')
        repeat.clicked.connect(lambda: self.start_run(True))
        # 尾部的note
        repeat_note = QLabel('注意：进入选择要使用的道具界面后执行重复战斗')
        repeat_note.setWordWrap(True)
        # 按顺序加入layout
        repeat_layout.addLayout(repeat_form)
        repeat_layout.addStretch(1)
        repeat_layout.addWidget(repeat)
        repeat_layout.addWidget(repeat_note)

        for group in (single_box, repeat_box):
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        battle_modes.addWidget(single_box, 1)
        battle_modes.addWidget(repeat_box, 1)
        form.addRow(battle_modes)

        # 子进程执行期间允许中断，结束后自动恢复按钮状态
        self.stop_button = QPushButton('终止当前战斗')
        self.stop_button.clicked.connect(self.stop_run)
        self.stop_button.setEnabled(False)
        form.addRow(self.stop_button)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        form.addRow('状态', self.log)

        # 技术模拟战 tab：与普通战斗使用同一 Worker/中断机制，不需要 HBRF
        card_runner = QWidget(); tabs.addTab(card_runner, '技术模拟战')
        card_form = QFormLayout(card_runner)
        # 技术模拟战单独保留窗口标题和日志，但与普通战斗共用一个 Worker
        self.card_window_title = QLineEdit('HeavenBurnsRed')
        card_form.addRow('游戏窗口标题', self.card_window_title)
        self.card_admin_status = QLabel('管理员：' + ('是' if self.is_admin() else '否'))
        card_form.addRow('当前权限', self.card_admin_status)
        card_admin = QPushButton('以管理员身份重启 GUI（Windows）')
        card_admin.clicked.connect(self.restart_admin)
        card_form.addRow(card_admin)
        card_test = QPushButton('寻找并激活窗口')
        card_test.clicked.connect(lambda: self.test_window(self.card_window_title, self.card_log))
        card_form.addRow(card_test)
        # 重复次数传给 repetition.card_game，不需要加载 HBRF
        self.card_count = QSpinBox()
        self.card_count.setRange(1, 9999); self.card_count.setValue(1)
        card_form.addRow('重复次数', self.card_count)
        card_start = QPushButton('执行重复打牌')
        card_start.clicked.connect(self.start_card_game)
        card_form.addRow(card_start)
        # 说明技术模拟战的启动界面要求
        note = QLabel('注意：当前重复进行[31C]普通战斗，请保证屏幕中完整出现该战斗选项后执行重复打牌')
        note.setWordWrap(True)
        card_form.addRow(note)
        self.card_stop_button = QPushButton('终止重复打牌')
        self.card_stop_button.setEnabled(False)
        self.card_stop_button.clicked.connect(self.stop_run)
        card_form.addRow(self.card_stop_button)
        self.card_log = QTextEdit(); self.card_log.setReadOnly(True)
        card_form.addRow('状态', self.card_log)
        # 样式表设置在主窗口上，会影响它的子控件
        self.setStyleSheet('''QMainWindow{background: #f7f8fa;} QWidget{color: #242933;font-size: 10pt;}
            QGroupBox{border:1px solid #dce2eb;border-radius:12px;margin-top:12px;padding:14px;background:white}
            QGroupBox::title{subcontrol-origin:margin;left:14px;padding:0 5px}
            QPushButton{background:white;border:1px solid #d6deea;border-radius:9px;padding:7px}
            QPushButton:hover{background:#eaf0fc}
            QPushButton#normalAddButton {
                border-top-left-radius: 9px;
                border-bottom-left-radius: 9px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QPushButton#batchAddButton {
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 9px;
                border-bottom-right-radius: 9px;
                border-left: 0px;
            }
            QLineEdit,QComboBox,QSpinBox,QTextEdit{
            background:white;border:1px solid #d6deea;border-radius:7px;padding:6px}
            QTabWidget::pane{border:0} QTabBar::tab {
                background: #f1f4f9;
                border: 1px solid #dce2eb;
                border-bottom: 0;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                padding: 10px 18px;
                margin-right: 3px;
            }
            QTabBar::tab:selected {
                background: #dbeafe;
                color: #1d4ed8;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #eaf0fc;
            }''')
        # 左侧没有重复次数和体力类型，按右侧实际内容高度补齐
        single_box.setMinimumHeight(repeat_box.sizeHint().height())

    # 设置mod为swap，全部重置为可以交换角色的样式
    def set_slot_swap_mode(self, enabled):
        self.slot_swap_source = None
        self.slot_swap_mode.setText('交换角色：开启' if enabled else '交换角色：关闭')
        for button, _ in self.slot_buttons:  # 交换角色样式
            button.setStyleSheet('QPushButton { border: 2px solid #2563eb; }' if enabled else '')

    # 需要分mod处理slot点击事件
    def handle_slot_click(self, index):
        # 不是swap mod则展开style选择面板
        if not self.slot_swap_mode.isChecked():
            self.choose_style(index)
            return
        # swap mod内第一次点击角色，储存并更改样式
        if self.slot_swap_source is None:
            self.slot_swap_source = index
            self.slot_buttons[index][0].setStyleSheet('QPushButton { border: 3px solid #16a34a; background: #dcfce7; }')
            return
        # 第二次点击角色，若重复则重置样式，不重复则交换slot
        source = self.slot_swap_source
        self.slot_swap_source = None
        if source == index:
            self.set_slot_swap_mode(True)
            return
        self.swap_team_slots(source, index)

    # 交换slot
    def swap_team_slots(self, first, second):
        if not (0 <= first < 6 and 0 <= second < 6):
            return
        if first == second:
            return
        # 先交换队伍数据，再同步重映射行动，确保技能按交换后的角色校验。
        a, b = first + 1, second + 1
        self.slots[first], self.slots[second] = self.slots[second], self.slots[first]
        self.nicknames[first], self.nicknames[second] = self.nicknames[second], self.nicknames[first]
        for row in self.rows:
            if isinstance(row, TurnRow):
                moves = row.state()['moves']
                remapped = []
                for role, skill, target in moves:
                    if role == a: role = b
                    elif role == b: role = a
                    if target == a: target = b
                    elif target == b: target = a
                    remapped.append((role, skill, target))
                row.refresh_roles(remapped)

        self.refresh_slots()
        if self.slot_swap_mode.isChecked():
            self.set_slot_swap_mode(True)

    # 选择风格、清除风格和新建的时候调用
    def refresh_slots(self):
        for i,(b,label) in enumerate(self.slot_buttons):
            # 有风格则存储风格图片
            style = self.slots[i]
            if style:
                b.setText(''); b.setIcon(QIcon(round_pixmap(style.image, 80)))
                b.setIconSize(QSize(80,80))
                label.setPlaceholderText(f'{style.label}（可改昵称）')
                if label.text() != self.nicknames[i]: label.setText(self.nicknames[i])
            # 没有风格就清空
            else:
                b.setIcon(QIcon()); b.setText('＋'); label.setPlaceholderText(f'Slot {i+1}')
                label.clear(); self.nicknames[i] = ''
        # 更新下面选技能的角色部分/重新判断特殊行动是否可用，不可用则弹出提示框删除
        available = self.available_global_buttons()
        for row in list(self.rows):
            if isinstance(row, TurnRow): 
                row.refresh_roles()
            elif isinstance(row, EventRow) and row.kind == "special": 
                valid = row.refresh_choices(available)
                if not valid:
                    box = QMessageBox(self)
                    box.setWindowTitle('特殊行动不可用')
                    box.setText(f'当前队伍不再支持任何特殊行动（魔界骑兵启动或总攻击）。')
                    box.setInformativeText('是否删除该行动块？')
                    delete = box.addButton('删除行动块', QMessageBox.ButtonRole.DestructiveRole)
                    box.addButton('保留空行动块', QMessageBox.ButtonRole.RejectRole)
                    box.exec()
                    if box.clickedButton() == delete:
                        self.remove_row(row)

    # 检测可用的global button
    def available_global_buttons(self):
        from config import templates as tpl
        styles = [s for s in self.slots if s]
        allowed = set()
        if any(s.title == "高傲魔王的凱旋歸來" for s in styles):
            allowed.add('waki')
        if any(s.team == 'P5R' for s in styles):
            allowed.add('attack')
        return allowed.intersection(tpl.GLOBAL_BUTTON_CONFIG)

    # 获取目标slot的nickname，没有nickname就返回国服角色名
    def nickname(self, slot):
        style = self.slots[slot-1]
        return self.nicknames[slot-1] or (style.label if style else f'空位{slot}')

    # 更新目标index的nickname，更新后把所有TurnRow的选项都更新了
    def change_nickname(self, index, name):
        if not self.slots[index]: return
        self.nicknames[index] = name.strip().replace(' ','').replace('　','')
        for row in self.rows:
            if isinstance(row, TurnRow): row.refresh_roles()

    # 点击6个槽位之一进入风格选择界面
    def choose_style(self, index):
        # 用角色名集合防止角色重复
        taken = {s.name for i,s in enumerate(self.slots) if s and i != index}
        dialog = StyleDialog(self.catalog, taken, self)
        # 选择了角色会accepted进而更改slots
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.slots[index] = dialog.chosen
            self.nicknames[index] = ''
            self.refresh_slots()

    # 右键槽位清除风格
    def clear_style(self, index):
        self.slots[index] = None; self.nicknames[index] = ''; self.refresh_slots()

    # 新增一行，默认turn，连接删除复制移动行的功能，有index则可以在目标位置插入行
    def add_row(self, state=None, index=None, kind='turn', scroll=True):
        available = self.available_global_buttons() if kind == 'special' else None
        if kind == 'special' and not available and state is None:
            QMessageBox.information(self, '无法添加特殊回合行动', '队伍中需要魔王山胁才能使用魔界骑兵，或需要 P5R 角色才能使用总攻击。')
            return None
        row = TurnRow(self, state) if kind == 'turn' else EventRow(kind, state, available)
        row.remove_requested.connect(self.remove_row)
        row.copy_requested.connect(self.copy_row)
        row.move_requested.connect(self.move_row)
        if index is None: index = len(self.rows)
        self.rows.insert(index,row)
        self.rows_layout.insertWidget(index,row)
        # 如果在最后一行插入，则滚动到最下方
        if scroll and index == len(self.rows)-1:
            QTimer.singleShot(10, lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ))
        # 刷新index
        self.refresh_row_indices()
        return row

    # 按原有行动序号批量插入：1 表示原第 1 行之前，超过原行数则追加到末尾
    def batch_add_rows(self, kind):
        # 特殊回合行动需要队伍支持；先检查，避免弹窗输入后只插入一部分
        if kind == 'special' and not self.available_global_buttons():
            QMessageBox.information(
                self, '无法添加特殊回合行动',
                '队伍中需要魔王山胁才能使用魔界骑兵，或需要 P5R 角色才能使用总攻击。'
            )
            return

        text, ok = QInputDialog.getText(
            self, '批量添加行动',
            '将在输入的位置前插入（从 1 开始，使用英文逗号分隔，例如 1,2,7）：'
        )
        if not ok:
            return
        parts = [part.strip() for part in text.split(',')]
        if not all(part.isascii() and part.isdecimal() and int(part) > 0 for part in parts):
            QMessageBox.warning(self, '输入错误', '请输入用英文逗号分隔的正整数，例如 1,2,7。')
            return

        # 所有位置都相对于插入前的行动列表；重复序号允许插入多个行动。
        original_count = len(self.rows)
        for position in sorted(map(int, parts), reverse=True):
            index = min(position - 1, original_count)
            self.add_row(index=index, kind=kind, scroll=False)

    # 删除row
    def remove_row(self, row):
        self.rows.remove(row); row.setParent(None); row.deleteLater()
        self.refresh_row_indices()

    # 复制row，位置是被复制的行下方
    def copy_row(self, row): self.add_row(row.state(), self.rows.index(row)+1, 'turn' if isinstance(row, TurnRow) else row.kind)

    # 移动row
    def move_row(self, row, shift):
        i = self.rows.index(row); j = i + shift
        if not 0 <= j < len(self.rows): return
        self.rows.pop(i); self.rows.insert(j,row)
        self.rows_layout.removeWidget(row); self.rows_layout.insertWidget(j,row)
        self.refresh_row_indices()

    # 新建页面，全部清除后加一行空turn row
    def new(self):
        self.current_path = None; self.slots = [None]*6; self.nicknames=['']*6; self.other_actions=[]
        for row in list(self.rows): self.remove_row(row)
        self.refresh_slots(); self.add_row()

    # 刷新所有块右上角index编号
    def refresh_row_indices(self):
        for i, row in enumerate(self.rows, 1):
            row.index_label.setText(f'#{i}')

    # 匹配注释中的风格元数据，group(0)是整个匹配字符串，(1)是slot，(2)是字典
    @staticmethod
    def _style_notes(path):
        # Format: # HBRTOOL_STYLE 1 {"team":"31A","english":"...","id":"001"}
        result = {}
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*#\s*HBRTOOL_STYLE\s+([1-6])\s+(\{.*\})\s*$', line)
            if match:
                result[int(match.group(1))] = json.loads(match.group(2))
        return result

    # 打开从 hbr-tool.com 保存的 SAV，转换后复用现有 HBRF 编辑器导入逻辑
    def open_sav(self):
        QMessageBox.information(
            self, 'SAV 文件来源',
            '仅支持从 https://www.hbr-tool.com/ 网站保存的 .sav 文件。\n'
            '转换结果不包含部分特殊行动等信息，导入后请检查并重新保存。'
        )
        sav_path, _ = QFileDialog.getOpenFileName(
            self, '选择 SAV 文件', str(SCRIPTS), 'SAV (*.sav);;All files (*)'
        )
        if not sav_path: return
        # 转换结果先保存为 HBRF 文件，再交给原有编辑器载入
        output_path, _ = QFileDialog.getSaveFileName(
            self, '保存转换后的 HBRF',
            str(SCRIPTS / (Path(sav_path).stem + '.hbrf')),
            'HBRF (*.hbrf)'
        )
        if not output_path: return
        try:
            # 直接调用转换模块，保留未匹配技能/风格的警告
            from hbrf.axisWebsite.sav_to_hbrf import main as convert_sav
            converted, warnings = convert_sav(sav_path, output_path=output_path)
            self.open_file(str(converted))  # 复用 HBRF 导入和风格匹配逻辑
            if warnings:
                unique = list(dict.fromkeys(warnings))
                details = '\n'.join(unique[:12])
                if len(unique) > 12:
                    details += f'\n……另有 {len(unique)-12} 条警告'
                QMessageBox.warning(self, 'SAV 转换提示', details)
        except Exception as e:
            QMessageBox.critical(self, 'SAV 转换失败', str(e))

    # 打开从 hbr-axletool.pages.dev 保存的 jpg，转换后复用现有 HBRF 编辑器导入逻辑
    def open_jpg(self):
        QMessageBox.information(
            self, 'jpg 文件来源',
            '仅支持从 https://hbr-axletool.pages.dev/ 网站保存的 .jpg 文件。\n'
            '转换结果不包含部分特殊行动等信息，导入后请检查并重新保存。'
        )
        jpg_path, _ = QFileDialog.getOpenFileName(
            self, '选择 jpg 文件', str(SCRIPTS), 'JPG (*.jpg);;All files (*)'
        )
        if not jpg_path: return
        # 转换结果先保存为 HBRF 文件，再交给原有编辑器载入
        output_path, _ = QFileDialog.getSaveFileName(
            self, '保存转换后的 HBRF',
            str(SCRIPTS / (Path(jpg_path).stem + '.hbrf')),
            'HBRF (*.hbrf)'
        )
        if not output_path: return
        try:
            # 直接调用转换模块，保留未匹配技能/风格的警告
            from hbrf.axletool.axle_jpg_to_hbrf import main as convert_jpg
            converted, warnings = convert_jpg(jpg_path, output_path=output_path)
            self.open_file(str(converted))  # 复用 HBRF 导入和风格匹配逻辑
            if warnings:
                unique = list(dict.fromkeys(warnings))
                details = '\n'.join(unique[:12])
                if len(unique) > 12:
                    details += f'\n……另有 {len(unique)-12} 条警告'
                QMessageBox.warning(self, 'jpg 转换提示', details)
        except Exception as e:
            QMessageBox.critical(self, 'jpg 转换失败', str(e))

    # 打开 HBRF；指定 path 时复用原来的解析流程，不再弹出文件选择框
    def open_file(self, path=None):
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getOpenFileName(
                self, '打开 HBRF', str(SCRIPTS), 'HBRF (*.hbrf);;All files (*)'
            )
        # 用户取消选择时path为空
        if not path: return
        try:
            from hbrf import model as m
            script = m.load_hbrf(path)  # 调用model的load_hbrf生成BattleScript类
            notes = self._style_notes(path)  # 获得注释中的风格元数据
            chosen = [None] * 6  # list[Style]
            loaded_nicknames = [''] * 6
            occupied = set()
            # script.roles强制6名角色，有可能脚本保存成了空位
            for i, role in enumerate(script.roles):
                # 空位忽略即可
                if role.name.startswith(('空位', '__EMPTY_SLOT_')) and not role.skills:
                    continue
                note = notes.get(i+1)
                style = None
                if note is not None:
                    # 通过元数据找回风格
                    style = self.catalog.find_style(note.get('team'), note.get('english'), note.get('id'))
                # 没有元数据/出错风格寻找失败
                if style is None:
                    question = QMessageBox(self)
                    question.setWindowTitle('角色 / 风格未匹配')
                    question.setText(f'Slot {i+1}: {role.name}\n无法确定数据库中的对应风格。')
                    question.setInformativeText('舍弃：保留空位（相关回合需手动修复）；选择风格：手动指定；取消：中止打开文件。')
                    discard = question.addButton('舍弃角色', QMessageBox.ButtonRole.DestructiveRole)
                    choose = question.addButton('选择风格', QMessageBox.ButtonRole.AcceptRole)
                    cancel = question.addButton('取消导入', QMessageBox.ButtonRole.RejectRole)
                    question.setDefaultButton(choose)
                    question.exec()
                    clicked = question.clickedButton()
                    if clicked == cancel: return
                    if clicked == choose:
                        dialog = StyleDialog(self.catalog, occupied, self)
                        if dialog.exec() != QDialog.DialogCode.Accepted: return
                        style = dialog.chosen
                if style and style.name in occupied:
                    raise ValueError(f'同一角色重复上场：{style.name}')
                chosen[i] = style
                # 成功恢复style则添加occupied并储存可能的nickname
                if style:
                    occupied.add(style.name)
                    canonical = style.label.replace(' ', '').replace('　','')
                    loaded_nicknames[i] = role.name if role.name != canonical else ''

            # 新建并从0开始恢复每一行行动
            self.new()
            self.current_path = Path(path)
            self.slots = chosen
            self.nicknames = loaded_nicknames
            self.refresh_slots()
            for row in list(self.rows): self.remove_row(row)
            # active代表可切换技能目前启用的那一个
            active = {}
            for role in script.roles:
                for index, item in enumerate(role.skills, 1):
                    if '/' in item:
                        active[(role.slot, index)] = item.split('/', 1)[0]
            # 还原每一行行动
            check_next_turn = False  # CheckOD 对应下一条 BattleTurn
            for a in script.actions:
                # 需要check下一个BattleTurn
                if isinstance(a, m.CheckOD):
                    check_next_turn = True
                    continue
                # 有switch的技能要交换active
                if isinstance(a, m.SkillSwitch):
                    pair = script.roles[a.role-1].skills[a.skill-1].split('/')
                    if len(pair) == 2:
                        old = active.get((a.role,a.skill),pair[0])
                        active[(a.role,a.skill)] = pair[1] if old == pair[0] else pair[0]
                    continue
                if isinstance(a, m.SpecialRoleButton):
                    name = {'kelian': '切换姿态', 'siling': '鬼神化'}.get(a.button)
                    if not name or not chosen[a.role-1]:
                        self.other_actions.append((len(self.rows), a))
                        continue

                    # HBRF 的 SpecialRoleButton 只保存操作角色和前排位置。
                    moves = [(0, '普通攻击', None) for _ in range(3)]
                    moves[a.position] = (a.role, '@special:' + name, None)

                    # 尽量沿用之前回合的另外两名角色。
                    previous = next((r for r in reversed(self.rows) if isinstance(r, TurnRow)), None)
                    candidates = [slot for slot, _, _ in previous.state()['moves']] if previous else []
                    candidates += [i for i, style in enumerate(chosen, 1) if style]

                    for i in range(3):
                        if i == a.position: continue
                        slot = next((s for s in candidates if s and s != a.role
                                    and s not in [v[0] for v in moves]), 0)
                        if slot:
                            moves[i] = (slot, self.catalog.default_action(chosen[slot-1]), None)

                    self.add_row({'moves': moves}, scroll=False)
                    continue
                if isinstance(a, (m.SkipEvent,m.ChangeTeamEvent)):
                    self.add_row({'action':'skip' if isinstance(a,m.SkipEvent) else 'change'},kind='yishi'); continue
                if isinstance(a, m.SpecialGlobalButton):
                    self.add_row({'action':a.button},kind='special'); continue
                # 什么都不是的行动扔到垃圾桶里
                if not isinstance(a, m.BattleTurn):
                    self.other_actions.append((len(self.rows), a)); continue
                # 是BattleTurn
                moves=[]
                for mv in a.actions:
                    old_role=script.roles[mv.role-1]
                    if mv.skill==0: text=self.catalog.default_action(chosen[mv.role-1])
                    else:
                        value=old_role.skills[mv.skill-1]
                        text=active.get((mv.role,mv.skill),value.split('/',1)[0])
                    moves.append((mv.role if chosen[mv.role-1] else 0,text,
                                  mv.target if mv.target in (7,8,9) or (mv.target is not None and chosen[mv.target-1]) else None))
                state = TurnRow.parse_label(a.label, a.od)
                # 当od这个值不存在时添加默认值
                state.setdefault('od', -a.od if a.od < 0 else (a.od + 3 if a.od > 0 else 0))
                state.update(activate_od=a.od != 0, check_od=check_next_turn,moves=moves)
                self.add_row(state, scroll=False)
                check_next_turn = False
            self.run_path.setText(str(path))
            self.statusBar().showMessage(f'已打开：{path}')
        except Exception as e:
            QMessageBox.critical(self,'读取失败',str(e))

    def build_script(self):
        from hbrf import model as m
        # 把index映射为slot，同时处理中间角色空位问题
        present = [i for i, style in enumerate(self.slots) if style is not None]
        order = present + [i for i in range(6) if i not in present]  # 先排有的再排空位
        slot_map = {old+1: new+1 for new, old in enumerate(order)}
        compact_styles = [self.slots[i] for i in order]  # list[Style | None]
        # 加入昵称/国服名/空位，技能初始化为空
        roles = [m.Role(i+1, (self.nicknames[old] or self.slots[old].label).replace(' ','').replace('　','') if self.slots[old] else f'空位{i+1}', [])
                 for i, old in enumerate(order)]
        if len({r.name for r in roles}) != 6: raise ValueError('角色昵称不能重复')
        # 异常判断和使用的技能收集
        used = [[] for _ in range(6)]  # 记录使用过的技能，方便hbrf技能部分写入
        used_pairs = {}  # (compact slot, unordered pair) -> (selected names)  # 记录用过的可切换技能，方便提示框显示
        for row in self.rows:
            if not isinstance(row, TurnRow): continue
            seen = set()
            moves = row.state()['moves']
            special = [i for i, (_,sk,_) in enumerate(moves) if str(sk or '').startswith('@special:')]
            if len(special)>1: raise ValueError(f'{row.label_text()}：只能选择一个特殊前排行动')
            for position,(slot,skill,target) in enumerate(moves):
                if not slot or not self.slots[slot-1]: raise ValueError(f'{row.label_text()}：有未选择的角色')
                if slot in seen: raise ValueError(f'{row.label_text()}：角色重复')
                seen.add(slot)
                style=self.slots[slot-1]
                if skill == "指揮行動" or str(skill).startswith('@special:'):
                    if target is not None: raise ValueError(f'{row.label_text()}：指挥/特殊行动不能指定目标')
                elif skill == '普通攻击':
                    pass
                else:
                    if skill not in self.catalog.skills_for(style): raise ValueError(f'{self.nickname(slot)} 无法使用 {skill}')
                    # 如果是可切换技能，和切换后的技能名放一起作为元组存储，键是(角色slot, 技能pair的set)
                    link=self.catalog.linked(style,skill)
                    if link:
                        key=(slot_map[slot], frozenset((skill,link)))
                        used_pairs.setdefault(key, (skill,link))
                        item=key[1]
                    else: item=skill
                    if item not in used[slot_map[slot]-1]: used[slot_map[slot]-1].append(item)
            if special:
                for i,(slot,skill,target) in enumerate(moves):
                    if i != special[0] and skill != self.catalog.default_action(self.slots[slot-1]):
                        raise ValueError(f'{row.label_text()}：特殊前排行动时其他角色必须使用默认行动')
        for index, items in enumerate(used):
            if len(items)>6: raise ValueError(f'{roles[index].name}：使用技能超过6个，目前暂不支持')
        # 收集switchable pair初始默认选择
        defaults = {}  # (角色slot, 技能pair的set) → 初始选择
        for (slot,pair),(a,b) in used_pairs.items():
            options=[self.catalog.skill_label(a),self.catalog.skill_label(b)]
            selection,ok=QInputDialog.getItem(self, '选择初始切换技能',
                f'{roles[slot-1].name}：请选择初始默认技能', options, 0, False)
            if not ok: raise ValueError('已取消技能初始状态选择')
            defaults[(slot,pair)] = a if selection == options[0] else b
        # hbrf技能部分写入
        for index, items in enumerate(used):
            names=[]
            for item in items:
                if isinstance(item,frozenset):
                    first=defaults[(index+1,item)]; second=next(x for x in item if x!=first)
                    names.append(first+'/'+second)
                else: names.append(item)
            roles[index].skills=names
        # 开始遍历所有rows来构建BattleScript
        current = dict(defaults)
        actions=[]
        for row in self.rows:
            # EventRow存储为action
            if isinstance(row, EventRow):
                action=row.action.currentData()
                if row.kind == 'special' and action not in self.available_global_buttons():
                    raise ValueError('特殊回合行动与当前队伍不匹配，请重新选择角色或删除该行动')
                if action == 'skip': actions.append(m.SkipEvent())
                elif action == 'change': actions.append(m.ChangeTeamEvent())
                else: actions.append(m.SpecialGlobalButton(action))
                continue
            # TurnRow存储为action之前的处理
            moves=[]; special_action=None
            for position,(slot,skill,target) in enumerate(row.state()['moves']):
                new_slot=slot_map[slot]; style=self.slots[slot-1]
                default=self.catalog.default_action(style)
                # 特殊行动，不存在技能列表中，skill_id设为0
                if str(skill or '').startswith('@special:'):
                    special_action=(new_slot,position,skill.partition(':')[2]); skill_id=0
                # 默认技能，不存在技能列表中，skill_id设为0
                elif skill in (default,'普通攻击'):
                    skill_id=0
                # 其他需要使用的技能
                else:
                    link=self.catalog.linked(style,skill)
                    # 如果是可切换技能，判断其确实切换了，则切换skill的指向并加入SkillSwitch
                    if link:
                        pair=frozenset((skill,link)); key=(new_slot,pair)
                        skill_id=used[new_slot-1].index(pair)+1
                        if current[key]!=skill:
                            actions.append(m.SkillSwitch(new_slot, skill_id, position))
                            current[key]=skill
                    # 不是可切换的普通技能
                    else: skill_id=used[new_slot-1].index(skill)+1
                moves.append(m.SkillAction(new_slot,skill_id,
                            slot_map[target] if target and target <= 6 else target))
            # 是特殊行动则加入SpecialRoleButton进action
            if special_action:
                if row.execution_od():
                    raise ValueError('特殊前排行动不能同时发动 OD')
                role,position,name=special_action
                button={'切换姿态':'kelian','鬼神化':'siling'}.get(name)
                if not button: raise ValueError(f'未知特殊行动：{name}')
                actions.append(m.SpecialRoleButton(role,position,button))
                continue
            # 不是特殊行动先看是否需要凹追击check od
            if row.check_od.isChecked():
                if row.execution_od() == 0:
                    raise ValueError(
                        f'{row.label_text()}：凹追击要求本回合发动 OD'
                    )
                actions.append(m.CheckOD())
            # 不是特殊行动则加入BattleTurn进action
            actions.append(m.BattleTurn(row.label_text(),row.execution_od(),moves))
        # 垃圾桶里真有东西
        if self.other_actions:
            raise ValueError('有无法表示的原始 Action，已拒绝保存以免丢失信息')
        # 调用m.BattleScript将action储存为BattleScript
        script=m.BattleScript(roles,actions)
        m.validate_hbrf(script)
        return script,compact_styles

    # 保存文件
    def save(self, save_as=False):
        try: script, compact_styles=self.build_script()
        except Exception as e:
            QMessageBox.warning(self,'无法保存',str(e)); return False
        path = self.current_path
        if save_as or not path:
            filename,_ = QFileDialog.getSaveFileName(self,'保存 HBRF',str(path or SCRIPTS / 'new.hbrf'),'HBRF (*.hbrf)')
            if not filename: return False
            path=Path(filename)
        try:
            from hbrf import model as m
            m.save_hbrf(script,path)
            # 在文件尾部 Include style metadata as comments to retain compatibility with model.load_hbrf.
            with Path(path).open('a', encoding='utf-8') as f:
                f.write('\n# HBRTool style metadata\n')
                for slot, style in enumerate(compact_styles, 1):
                    if style:
                        meta = dict(team=style.team, english=style.english, id=style.sid)
                        f.write(f'# HBRTOOL_STYLE {slot} {json.dumps(meta, ensure_ascii=False)}\n')
            # Keep the GUI view's slots and actions untouched on save.
            self.current_path=path
            self.statusBar().showMessage(f'已保存：{path}')
            return True
        except Exception as e:
            QMessageBox.critical(self,'保存失败',str(e)); return False

    # 在手动输入好hbrf文件路径后触发输出角色和技能顺序要求
    def preview_run_file(self):
        path = self.run_path.text().strip()
        if not path: return
        try:
            self.show_run_roles(path)
        except Exception as e:
            QMessageBox.warning(self, '读取脚本失败', str(e))

    # 输出角色和技能顺序要求
    def show_run_roles(self, path):
        from hbrf import model as m
        script = m.load_hbrf(path)
        self.log.append(f'\n脚本：{Path(path).name}')
        for role in script.roles:
            if role.name.startswith(('空位', '__EMPTY_SLOT_')):
                self.log.append(f'位置{role.slot}：空位')
                continue
            skills = ['/'.join(self.catalog.skill_zh(s) for s in skill.split('/'))
                    for skill in role.skills]
            self.log.append(f'位置{role.slot}：{role.name}：{"、".join(skills) if skills else "无"}')
        self.log.append(f'[注意] 使用的技能可以少于3个，但每名角色都必须装备至少3个主动技能，防止技能所在位置变化')

    # 选择战斗脚本，选好后触发输出角色和技能顺序要求
    def select_run_file(self):
        p, _ = QFileDialog.getOpenFileName(self, '选择战斗脚本', str(SCRIPTS), 'HBRF (*.hbrf)')
        if not p: return
        self.run_path.setText(p)
        try:
            self.show_run_roles(p)
        except Exception as e:
            QMessageBox.warning(self, '读取脚本失败', str(e))

    # 判断是否有管理员权限
    @staticmethod
    def is_admin():
        if sys.platform!='win32': return False
        try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception: return False

    # 重启以获得管理员权限
    def restart_admin(self):
        if sys.platform!='win32':
            QMessageBox.information(self,'提示','管理员提权仅适用于 Windows'); return
        if self.is_admin():
            QMessageBox.information(self,'提示','当前已经以管理员身份运行'); return
        if QMessageBox.question(self,'重启确认','未保存的 GUI 编辑内容将丢失，确定以管理员权限重启？') != QMessageBox.StandardButton.Yes: return
        args = ' '.join('"'+x.replace('"','\\"')+'"' for x in sys.argv)
        result=ctypes.windll.shell32.ShellExecuteW(None,'runas',sys.executable,args,str(ROOT),1)
        if result>32: QApplication.quit()
        else: QMessageBox.warning(self,'提权失败',f'ShellExecuteW 返回 {result}')

    # 尝试寻找游戏界面
    def test_window(self, title_widget=None, log_widget=None):
        title_widget = title_widget or self.window_title
        log_widget = log_widget or self.log
        try:
            from window_operation import find_window
            game = find_window(title_widget.text().strip())
            resolution = settings.detect_resolution(game)
            log_widget.append(f'已找到：{game.title}，坐标=({game.left},{game.top})，分辨率={resolution[0]}×{resolution[1]}')
            settings.set_resolution(resolution=resolution)
        except Exception as e: QMessageBox.warning(self,'窗口检测失败，请检查游戏窗口名称是否正确',str(e))

    # 通过参数判断单次/repeat战斗，启动worker进行战斗
    def start_run(self, repeated):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self,'运行中','已有任务正在运行'); return
        # 未取得管理员权限则不允许启动战斗
        if not self.is_admin():
            QMessageBox.warning(
                self,
                '操作游戏需要管理员权限',
                '请先点击“以管理员身份重启 GUI（Windows）”，'
                '获得管理员权限后再执行战斗。'
            )
            return

        path=self.run_path.text().strip()
        # 没有输入hbrf文件path则用编辑器刚刚保存的current_path
        if not path:
            if not self.save(): return
            path=str(self.current_path)
        # 编辑器和脚本位置一致，询问是否保存再用新保存的script
        else:
            if self.current_path and Path(path).resolve()==self.current_path.resolve():
                if QMessageBox.question(self,'文件确认','将按磁盘上已保存的 HBRF 运行。是否先保存编辑器内容？') == QMessageBox.StandardButton.Yes:
                    if not self.save(): return  # 保存失败不进行战斗
        try:
            from hbrf import model as m
            script=m.load_hbrf(path)
            if any(r.name.startswith(('__EMPTY_SLOT_', '空位')) for r in script.roles):
                raise ValueError('当前存在空队伍位置；运行前必须补全 6 个角色（老板位可以随便选）')
        except Exception as e:
            QMessageBox.warning(self,'脚本无效',str(e)); return
        self.log.append('开始执行：'+('重复战斗' if repeated else '单次战斗'))
        self.worker=Worker(path,repeated,self.run_count.value(),self.ticket.currentData(),
                           self.auto_close.isChecked(),self.window_title.text().strip())
        self.worker.finished_text.connect(self.log.append)
        self.worker.log_text.connect(self.log.append)
        self.worker.finished.connect(self.run_finished)
        self.card_stop_button.setEnabled(False)
        self.stop_button.setText('终止当前战斗')
        self.stop_button.setEnabled(True)
        self.worker.start()

    def start_card_game(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, '运行中', '已有任务正在运行'); return
        # 未取得管理员权限则不允许启动打牌
        if not self.is_admin():
            QMessageBox.warning(
                self,
                '操作游戏需要管理员权限',
                '请先点击“以管理员身份重启 GUI（Windows）”，'
                '获得管理员权限后再执行重复打牌。'
            )
            return
        
        self.card_log.append('开始执行：技术模拟战重复打牌')
        # mode='card' 时 Worker 运行 run_card_game.py，而不是 run_battle.py
        self.worker = Worker(None, False, self.card_count.value(), 'stone', False,
                             self.card_window_title.text().strip(), mode='card')
        self.worker.log_text.connect(self.card_log.append)
        self.worker.finished_text.connect(self.card_log.append)
        self.worker.finished.connect(self.run_finished)
        self.stop_button.setEnabled(False)
        self.card_stop_button.setText('终止重复打牌')
        self.card_stop_button.setEnabled(True)
        self.worker.start()

    def stop_run(self):
        if not self.worker or not self.worker.isRunning(): return
        force = self.worker.stopping
        # 根据当前运行模式选择正确的终止按钮和日志区
        button = self.card_stop_button if self.worker.mode == 'card' else self.stop_button
        log = self.card_log if self.worker.mode == 'card' else self.log
        button.setText('强制结束' if not force else ('终止重复打牌' if self.worker.mode == 'card' else '终止当前战斗'))
        log.append('正在强制结束子进程' if force else '已发送中断请求')
        self.worker.stop()

    # 两种子进程结束时都恢复按钮文字并禁用终止操作
    def run_finished(self):
        for button in (self.stop_button, self.card_stop_button):
            if button == self.stop_button:
                button.setText('终止当前战斗')
            elif button == self.card_stop_button:
                button.setText('终止重复打牌')
            button.setEnabled(False)

if __name__=='__main__':
    # EXE 子进程通过指定参数直接运行战斗函数，不创建 Qt 窗口
    if len(sys.argv) >= 3 and sys.argv[1] == '--hbr-worker':
        # 打包后的子进程先恢复 UTF-8 标准输出
        if getattr(sys, 'frozen', False):
            setup_worker_output()

        mode = sys.argv[2]
        sys.argv = [sys.argv[0], *sys.argv[3:]]
        if mode == 'battle':
            from run_battle import main
        elif mode == 'card':
            from run_card_game import main
        else:
            raise ValueError(f'未知的工作模式：{mode}')
        try:
            main()
        except KeyboardInterrupt:
            print('用户中断任务', flush=True)
            sys.exit(130)
    else:
        app=QApplication(sys.argv)

        # 统一设置所有 Qt 窗口的图标
        app.setWindowIcon(QIcon(str(ROOT / 'logo.ico')))

        window=MainWindow()
        window.show()
        sys.exit(app.exec())
