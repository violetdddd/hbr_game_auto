"""HBRTool desktop GUI. Put this file in the project root beside fight.py and hbrf/.
Requires: pip install PySide6. Game automation dependencies are only imported when running a fight.
"""
from __future__ import annotations
import json
import re
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
    QTabWidget, QTextEdit, QFormLayout, QInputDialog)

from paths import ROOT_DIR
ROOT = ROOT_DIR
SCRIPTS = ROOT / 'scripts'
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
                        self.switch_pairs[(character, name)] = entry['link']
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
                if style_key == "希望的晨曦" and "鬼神化" in skills:
                    skills.remove("鬼神化")
                if style_key == "高傲魔王的凱旋歸來" and "魔界騎兵起動！" in skills:
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
                    if style_key == "CODE:Virtual Killer" and sid == "009-2":
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
        self.editor = parent_editor
        outer = QVBoxLayout(self)
        # head包括turn，od，bonus，追加，发动od和定制label，以及信号控件
        head = QHBoxLayout()
        self.turn_no = NoWheelComboBox(); self.turn_no.addItems([f'T{i}' for i in range(1, 21)])
        self.extra = NoWheelComboBox(); self.extra.addItems(['普通回合', '追加回合'])
        self.bonus = NoWheelComboBox(); self.bonus.setMinimumWidth(155); self.bonus.addItem('无 Bonus')
        # 需要把index的0到6映射为-3到3
        self.od = NoWheelComboBox(); self.od.addItems(['无 OD', '前置 OD1', '前置 OD2', '前置 OD3', '后置 OD1', '后置 OD2', '后置 OD3'])
        # od变化要影响bonus选择
        self.od.currentIndexChanged.connect(self.refresh_bonus)
        self.activate_od = QCheckBox('发动')
        self.custom_label = QLineEdit(); self.custom_label.setPlaceholderText('自定义 label（非空时优先使用）')
        for w in (self.turn_no, self.extra, self.bonus, self.od, self.activate_od):
            head.addWidget(w)
        head.addWidget(self.custom_label, 2)
        for label, callback in [('↑',lambda: self.move_requested.emit(self,-1)),('↓',lambda: self.move_requested.emit(self,1)),
                                ('复制',lambda: self.copy_requested.emit(self)),('删除',lambda: self.remove_requested.emit(self))]:
            b = QPushButton(label); b.clicked.connect(callback); head.addWidget(b)
        outer.addLayout(head)
        # body部分是role，skill和target
        body = QHBoxLayout()
        self._syncing = False
        self.roles, self.skills, self.targets = [], [], []
        for i in range(3):
            col = QVBoxLayout()
            r = NoWheelComboBox(); s = NoWheelComboBox(); t = NoWheelComboBox()
            # 角色变化要影响技能选择
            r.currentIndexChanged.connect(lambda _=0, index=i: self._role_changed(index))
            col.addWidget(QLabel(f'前排 {i+1}'))
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
        # 如果之前的选中的技能现在角色也有，则恢复技能
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

    # 保存状态
    def state(self):
        return dict(turn=self.turn_no.currentIndex(), extra=self.extra.currentIndex(), bonus=self.bonus.currentIndex(), bonus_text=self.bonus.currentText(),
        od=self.od.currentIndex(), activate_od=self.activate_od.isChecked(), label=self.custom_label.text(),
        moves=[(r.currentData(),s.currentData(),t.currentData()) for r,s,t in zip(self.roles,self.skills,self.targets)])

    # 重新load已经存在的状态
    def load_state(self, state):
        self.turn_no.setCurrentIndex(state.get('turn',0))
        self.extra.setCurrentIndex(state.get('extra',0))
        self.od.setCurrentIndex(state.get('od',0))
        self.activate_od.setChecked(state.get('activate_od', False))
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

# 等待添加logger和终止程序按钮
class Worker(QThread):
    finished_text = Signal(str)
    def __init__(self, fn, *args):
        super().__init__(); self.fn, self.args = fn, args
    def run(self):
        try:
            self.fn(*self.args)
            self.finished_text.emit('执行完成')
        except Exception:
            self.finished_text.emit(traceback.format_exc())

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
        for title, callback in [('新建',self.new),('打开 HBRF',self.open_file),('保存',self.save),('另存为',lambda: self.save(True))]:
            b = QPushButton(title); b.clicked.connect(callback); toolbar.addWidget(b)
        toolbar.addStretch(); root.addLayout(toolbar)
        # 角色slot
        slots_box = QGroupBox('队伍 · Slot 1–6（点击设置风格；右键清空）')
        slots_layout = QHBoxLayout(slots_box)
        self.slot_buttons = []
        for i in range(6):
            col = QVBoxLayout()
            b = QPushButton('＋'); b.setFixedSize(92,92)
            # 左键选风格右键清除
            b.clicked.connect(lambda _=False, ix=i: self.choose_style(ix))
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
        # 添加底部行动按钮
        add_actions = QHBoxLayout()
        for title, kind in [('异时层行动', 'yishi'), ('添加回合', 'turn'), ('特殊回合行动', 'special')]:
            b = QPushButton('＋ ' + title)
            b.clicked.connect(lambda _=False, k=kind: self.add_row(kind=k))
            add_actions.addWidget(b, 1 if kind != 'turn' else 2)
        root.addLayout(add_actions)
        root.addWidget(QLabel('提示：HBRF 限制每回合恰好 3 个不同角色，且每名角色最多记录 6 个技能。'))
        # 运行游戏tab
        runner = QWidget(); tabs.addTab(runner, '运行游戏')
        form = QFormLayout(runner)
        self.window_title = QLineEdit('HeavenBurnsRed')
        form.addRow('游戏窗口标题', self.window_title)
        self.admin_status = QLabel('管理员：' + ('是' if self.is_admin() else '否'))
        form.addRow('当前权限', self.admin_status)
        admin = QPushButton('以管理员身份重启 GUI（Windows）'); admin.clicked.connect(self.restart_admin)
        form.addRow(admin)
        self.run_path = QLineEdit(); self.run_path.setPlaceholderText('未指定则使用当前编辑器脚本')
        self.run_path.editingFinished.connect(self.preview_run_file)
        select = QPushButton('选择脚本'); select.clicked.connect(self.select_run_file)
        pathrow = QHBoxLayout(); pathrow.addWidget(self.run_path); pathrow.addWidget(select)
        form.addRow('HBRF 路径', pathrow)
        self.auto_close = QCheckBox('战斗前关闭自动战斗'); self.auto_close.setChecked(True)
        form.addRow(self.auto_close)
        self.run_count = QSpinBox(); self.run_count.setRange(1,9999); self.run_count.setValue(1)
        self.ticket = QComboBox(); self.ticket.addItems(['stone','ticket','spare'])
        form.addRow('重复次数', self.run_count); form.addRow('体力类型', self.ticket)
        test = QPushButton('寻找并激活窗口'); test.clicked.connect(self.test_window)
        play = QPushButton('执行单次战斗'); play.clicked.connect(lambda: self.start_run(False))
        repeat = QPushButton('执行重复战斗'); repeat.clicked.connect(lambda: self.start_run(True))
        form.addRow(test); form.addRow(play); form.addRow(repeat)
        # 日志内容
        self.log = QTextEdit(); self.log.setReadOnly(True); form.addRow('状态', self.log)
        # 样式表设置在主窗口上，会影响它的子控件
        self.setStyleSheet('''QMainWindow,QWidget{background:#f7f8fa;color:#242933;font-size:10pt}
            QGroupBox{border:1px solid #dce2eb;border-radius:12px;margin-top:12px;padding:14px;background:white}
            QGroupBox::title{subcontrol-origin:margin;left:14px;padding:0 5px}
            QPushButton{background:white;border:1px solid #d6deea;border-radius:9px;padding:7px}
            QPushButton:hover{background:#eaf0fc} QLineEdit,QComboBox,QSpinBox,QTextEdit{
            background:white;border:1px solid #d6deea;border-radius:7px;padding:6px}
            QTabWidget::pane{border:0} QTabBar::tab{padding:10px 18px}''')

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
        return row

    # 删除row
    def remove_row(self, row):
        self.rows.remove(row); row.setParent(None); row.deleteLater()

    # 复制row，位置是被复制的行下方
    def copy_row(self, row): self.add_row(row.state(), self.rows.index(row)+1, 'turn' if isinstance(row, TurnRow) else row.kind)

    # 移动row
    def move_row(self, row, shift):
        i = self.rows.index(row); j = i + shift
        if not 0 <= j < len(self.rows): return
        self.rows.pop(i); self.rows.insert(j,row)
        self.rows_layout.removeWidget(row); self.rows_layout.insertWidget(j,row)

    # 新建页面，全部清除后加一行空turn row
    def new(self):
        self.current_path = None; self.slots = [None]*6; self.nicknames=['']*6; self.other_actions=[]
        for row in list(self.rows): self.remove_row(row)
        self.refresh_slots(); self.add_row()

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

    # 打开hbrf文件
    def open_file(self):
        path,_ = QFileDialog.getOpenFileName(self,'打开 HBRF',str(SCRIPTS),'HBRF (*.hbrf);;All files (*)')
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
            for a in script.actions:
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
                state.update(activate_od=a.od != 0, moves=moves)
                self.add_row(state, scroll=False)
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
            filename,_ = QFileDialog.getSaveFileName(self,'保存 HBRF',str(path or ROOT / 'new.hbrf'),'HBRF (*.hbrf)')
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
        self.log.append(f'可以不用但每名角色必须装备至少3个技能！')

    # 选择战斗脚本，选好后触发输出角色和技能顺序要求
    def select_run_file(self):
        p, _ = QFileDialog.getOpenFileName(self, '选择战斗脚本', str(ROOT), 'HBRF (*.hbrf)')
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
    def test_window(self):
        try:
            from window_operation import find_window
            game = find_window(self.window_title.text().strip())
            self.log.append(f'已找到：{game.title}，坐标=({game.left},{game.top})，尺寸={game.width}×{game.height}')
        except Exception as e: QMessageBox.warning(self,'窗口检测失败，请检查游戏窗口名称是否正确',str(e))

    # 通过参数判断单次/repeat战斗，启动worker进行战斗
    def start_run(self, repeated):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self,'运行中','已有任务正在运行'); return
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
        self.worker=Worker(self._run_game,script,repeated,self.run_count.value(),self.ticket.currentText(),
                           self.auto_close.isChecked(),self.window_title.text().strip())
        self.worker.finished_text.connect(self.log.append)
        self.worker.start()

    # worker执行的函数，集成常规的find_window+fight/repeat_fight流程
    @staticmethod
    def _run_game(script,repeated,count,ticket,auto_close,title):
        from window_operation import find_window
        game=find_window(title)
        if repeated:
            from repetition import repeat_fight
            repeat_fight(game,script,count,ticket=ticket)
        else:
            from fight import fight
            fight(game,script,auto_close=auto_close)

if __name__=='__main__':
    app=QApplication(sys.argv)
    window=MainWindow(); window.show()
    sys.exit(app.exec())
