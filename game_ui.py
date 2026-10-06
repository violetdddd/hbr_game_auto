#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的游戏UI模拟
- 分辨率：1920x1200（可全屏/可调）
- 底部 7 个圆形按钮：前 6 个是角色按钮（设置阶段显示 1..6，之后显示名字），最后一个稍大，文本为“结束设置/结束回合”
- 右上角圆形按钮：三档 0/1/2，点击循环切换
- 两个阶段：
  1) 设置界面：
     - 点击角色按钮可重命名（支持中文）。
     - 屏幕中央显示 4 个长方形按钮（技能槽），点击可设置技能名与是否需要目标（默认无目标）。
     - 设置好 6 个角色和技能后，点击“结束设置”进入录制界面。
  2) 技能录制界面：
     - 点击一个角色会弹出其 4 个技能槽。
     - 这时可以点击另一个角色按钮与之换位；也可以选择一个技能。
       若该技能需要目标，则需再点击另一个角色作为目标。
     - 选择后技能槽收回。
"""
import tkinter as tk
from tkinter import simpledialog, messagebox

# ----------------------------- 数据结构 -----------------------------
class Skill:
    def __init__(self, name="", needs_target=False, activated=False):
        self.name = name
        self.needs_target = needs_target
        self.is_activated = activated

    def label(self):
        if self.name:
            nm = self.name
            tgt = "有目标" if self.needs_target else "无目标"
            return f"{nm}\n[{tgt}]"
        else:
            return "无"

class Role:
    def __init__(self, name=None, ind=None):
        self.name = name
        self.ind = ind
        self.skills = [Skill() for _ in range(4)]

# ----------------------------- UI 主类 -----------------------------
class GameUI:
    def __init__(self, root, file_path):
        self.root = root
        self.file_path = file_path
        self.root.title("hbr技能录制")
        # 固定设计分辨率（可根据需要自行调整/全屏）
        self.W, self.H = 1000, 700
        # try:
        #     # 在某些高分屏上提升清晰度
        #     self.root.tk.call('tk', 'scaling', 1.0)
        # except Exception:
        #     pass

        self.canvas = tk.Canvas(root, width=self.W, height=self.H, bg="#14161a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # 模式：'setup' 或 'record'
        self.mode = 'setup'

        # 右上角事件挡位（0/1/2/3）
        self.event = 0

        # 右上角od档位（0/1/2/3）
        self.od = 0

        # 计算回合数
        self.turn = 1

        # 6 个角色
        self.roles = [Role(str(i+1), i) for i in range(6)]  # 初始显示 1..6

        # 交互状态（录制阶段）
        self.selected_role_idx = None     # 打开技能面板的角色
        self.pending_skill_idx = None     # 已选择但待确认目标的技能槽索引（若需要目标）
        self.target_bg = 0  # 提示选技能目标界面

        # 画面元素缓存（便于刷新/删除）
        self.role_btn_items = []      # [(oval_id, text_name, tag), ...]
        self.end_btn_items = ()       # (oval_id, text_name, tag)
        self.od_btn_items = ()      # (oval_id, text_name, tag)
        self.event_btn_items = ()      # (oval_id, text_name, tag)
        self.target_bg_item = None

        self.skill_panel_items = []   # 中央技能面板所有元素的 rect_id, text_name，先技能后其他

        # 事件绑定
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        self.draw_all()

    # ---------------------- 绘制整体界面 ----------------------
    def draw_all(self):
        self.canvas.delete("all")
        self.draw_header()
        self.draw_footer_buttons()
        self.draw_event_od_button()
        self.draw_hint_text()
        self.toggle_target_bg(self.target_bg)

    def draw_header(self):
        # 标题栏
        title = "设置界面" if self.mode == 'setup' else "技能录制界面"
        self.canvas.create_text(
            40, 40,
            text=title,
            anchor="w",
            fill="#dfe6ee",
            font=("Microsoft YaHei", 28, "bold"),
        )

    def draw_hint_text(self):
        if self.mode == 'setup':
            hint = (
                "提示：点击底部角色按钮可命名角色；\n"
                "点击后在中央弹出的4个技能槽上，设置技能名与是否需要目标；\n"
                "技能需要从上到下设置，通过命名为空格来取消技能；\n"
                "设置完成后点击“结束设置”进入技能录制界面。"
            )
        else:
            hint = (
                "提示：点击角色会弹出技能槽；此时可以：\n"
                "  1) 点击另一个角色按钮与之换位；\n"
                "  2) 点击一个技能；若技能需要目标，再点击一个角色作为目标；\n"
                "  3) 点击同一个角色按钮收回面板；\n"
                "右上角后置od模式点击循环切换：0，1，2，3；\n"
                "右上角事件点击循环切换：无，skip，change，前置OD；\n"
                "设置完成后点击“结束回合”进入下一回合技能录制。"
            )
        self.canvas.create_text(
            40, 90,
            text=hint,
            anchor="nw",
            fill="#9fb0c3",
            font=("Microsoft YaHei", 16),
        )

    # ---------------------- 底部按钮（6 角色 + 结束） ----------------------
    def draw_footer_buttons(self):
        self.role_btn_items.clear()

        margin_x = 30
        gap = 20  # 角色按钮间距
        btn_d = 110  # 角色按钮直径
        start_x = 30
        y = self.H - 140

        # 6 个角色按钮
        for i in range(6):
            x = start_x + i * (btn_d + gap)
            tag = f"role_{i}"
            oval = self.canvas.create_oval(x, y, x + btn_d, y + btn_d, fill="#2b3745", outline="#6a7c92", width=2, tags=(tag, "hit"))
            label = self.roles[i].name  # 初始为编号1-6
            txt = self.canvas.create_text(x + btn_d/2, y + btn_d/2, text=label, fill="#e8f0fa", font=("Microsoft YaHei", 16, "bold"), tags=(tag, "hit"))
            self.role_btn_items.append((oval, txt, tag))

        # “结束设置/结束回合”按钮（稍大）
        end_d = 150
        end_x = self.W - margin_x - end_d
        end_y = self.H - 180
        tag = "end_button"
        oval = self.canvas.create_oval(end_x, end_y, end_x + end_d, end_y + end_d, fill="#3a4a5c", outline="#7e93ad", width=3, tags=(tag, "hit"))
        label = "结束设置" if self.mode == 'setup' else "结束回合"
        txt = self.canvas.create_text(end_x + end_d/2, end_y + end_d/2, text=label, fill="#e8f0fa", font=("Microsoft YaHei", 16, "bold"), tags=(tag, "hit"))
        self.end_btn_items = (oval, txt, tag)

    # ---------------------- 右上角调档按钮 ----------------------
    def draw_event_od_button(self):

        d = 80
        sep = 30

        # od按钮
        x1, y1 = self.W - d - sep, sep
        x2, y2 = x1 + d, y1 + d
        tag = "od_button"
        oval = self.canvas.create_oval(x1, y1, x2, y2, fill="#2e3a48", outline="#6a7c92", width=2, tags=(tag, "hit"))
        txt = self.canvas.create_text((x1+x2)/2, (y1+y2)/2, text=f"{self.od}", fill="#e8f0fa", font=("Microsoft YaHei", 20, "bold"), tags=(tag, "hit"))
        self.canvas.create_text((x1+x2)/2, y2 + 20, text="后置OD", fill="#9fb0c3", font=("Microsoft YaHei", 12))
        self.od_btn_items = (oval, txt, tag)

        # 事件按钮
        x1, y1 = x1 - d - sep, sep
        x2, y2 = x1 + d, y1 + d
        tag = "event_button"
        oval = self.canvas.create_oval(x1, y1, x2, y2, fill="#2e3a48", outline="#6a7c92", width=2, tags=(tag, "hit"))
        events = ("无","skip","change","前置OD")
        text = events[self.event]
        txt = self.canvas.create_text((x1+x2)/2, (y1+y2)/2, text=text, 
        fill="#e8f0fa", font=("Microsoft YaHei", 14, "bold"), tags=(tag, "hit"))
        self.canvas.create_text((x1+x2)/2, y2 + 20, text="事件", fill="#9fb0c3", font=("Microsoft YaHei", 12))
        self.event_btn_items = (oval, txt, tag)

    # ---------------------- 选技能目标界面 ----------------------
    def toggle_target_bg(self, flag):
        if flag == 1 and self.target_bg_item is None:
            self.target_bg_item = self.canvas.create_rectangle(
                    0, 0, self.canvas.winfo_width(), self.canvas.winfo_height()-175,
                    fill="white", stipple="gray25", outline=""
                    )
            # 保证蒙板在最上层
            self.canvas.tag_raise(self.target_bg_item)
        elif flag == 0 and self.target_bg_item is not None:
            self.canvas.delete(self.target_bg_item)
            self.target_bg_item = None

    # ---------------------- 技能面板 ----------------------
    def open_skill_panel(self, role_idx):
        self.close_skill_panel()
        self.selected_role_idx = role_idx

        # 面板背景
        panel_w, panel_h = 700, 450
        x1 = (self.W - panel_w) // 2
        y1 = (self.H - panel_h) // 2 - 50
        x2, y2 = x1 + panel_w, y1 + panel_h

        bg = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#1d232c", outline="#7e93ad", width=2)
        label = self.roles[role_idx].name  # 初始为编号1-6
        title = f"技能设置（角色：{label}）"
        tt = self.canvas.create_text((x1+x2)//2, y1+30, text=title, fill="#e8f0fa", font=("Microsoft YaHei", 20, "bold"))

        # 4 个技能槽矩形
        slot_w, slot_h = 600, 60
        gap = 24
        start_y = y1 + 80
        for i in range(4):
            skill = self.roles[role_idx].skills[i]
            if self.mode == "setup" or skill.name:
                sx1 = x1 + (panel_w - slot_w) // 2
                sy1 = start_y + i * (slot_h + gap)
                sx2, sy2 = sx1 + slot_w, sy1 + slot_h
                tag = f"skill_slot_{i}"
                fill, outline= "#27313d", "#6a7c92"
                if skill.is_activated is not False:
                    fill, outline= "#ff4965", "#FFA6A9"
                rect = self.canvas.create_rectangle(sx1, sy1, sx2, sy2, fill=fill, outline=outline, width=2, tags=(tag, "hit"))
                
                label = skill.label()
                txt = self.canvas.create_text((sx1+sx2)//2, (sy1+sy2)//2, text=label, fill="#dfe6ee", font=("Microsoft YaHei", 16, "bold"), tags=(tag, "hit"))
                self.skill_panel_items += [rect, txt]

        # 关闭按钮
        close_tag = "skill_panel_close"
        btn = self.canvas.create_rectangle(x2-100, y1+10, x2-10, y1+40, fill="#3a4a5c", outline="#7e93ad", width=2, tags=(close_tag, "hit"))
        btnt = self.canvas.create_text(x2-55, y1+25, text="关闭", fill="#e8f0fa", font=("Microsoft YaHei", 12, "bold"), tags=(close_tag, "hit"))
        self.skill_panel_items += [bg, tt, btn, btnt]

        # 普通攻击
        if self.mode == "record":
            A_tag = "normal_A"
            btn = self.canvas.create_rectangle(x1+10, y1+10, x1+150, y1+40, fill="#3a4a5c", outline="#7e93ad", width=2, tags=(A_tag, "hit"))
            btnt = self.canvas.create_text(x1+80, y1+25, text="普通攻击", fill="#e8f0fa", font=("Microsoft YaHei", 12, "bold"), tags=(A_tag, "hit"))
            self.skill_panel_items += [btn, btnt]

    def close_skill_panel(self):
        for item in self.skill_panel_items:
            self.canvas.delete(item)
        self.skill_panel_items.clear()
        self.selected_role_idx = None
        self.pending_skill_idx = None

    # ---------------------- 事件处理 ----------------------
    def on_canvas_click(self, event):
        # 命中检测：通过标签 "hit" 捕获，然后根据更具体的 tag 分发
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in items[::-1]:  # 从最上层开始找
            tags = self.canvas.gettags(item)
            if "hit" not in tags:
                continue

            # 右上角档位按钮
            if "od_button" in tags:
                self.on_od_click()
                return
            
            if "event_button" in tags:
                self.on_event_click()
                return

            # 结束按钮
            if "end_button" in tags:
                self.on_end_click()
                return

            # 技能面板内部
            if self.skill_panel_items and self.selected_role_idx is not None:
                # 关闭面板
                if "skill_panel_close" in tags:
                    self.close_skill_panel()
                    return
                # 平A取消技能选择
                if "normal_A" in tags:
                    for skill in self.roles[self.selected_role_idx].skills:
                        skill.is_activated = False
                    self.close_skill_panel()
                    return
                # 点击技能槽
                for i in range(4):
                    if f"skill_slot_{i}" in tags:
                        self.on_skill_slot_click(i)
                        return

            # 角色按钮点击
            for i in range(6):
                if f"role_{i}" in tags:
                    self.on_role_click(i)
                    return

    # 挡位按钮：0 -> 1 -> 2 -> 3 -> 0
    def on_od_click(self):
        self.od = (self.od + 1) % 4
        self.draw_all()
    
    def on_event_click(self):
        self.event = (self.event + 1) % 4
        self.draw_all()

    # 结束按钮：设置界面 -> 录制界面；录制界面则记录“回合结束”
    def on_end_click(self):
        if self.mode == 'setup':
            self.event = self.od = 0
            # 转换ui模式
            self.mode = 'record'
            self.draw_all()

            # 写入配队信息
            with open(self.file_path, "a", encoding="utf-8") as f:  # "a" 表示追加写入
                f.write("# 配队和技能（用于初始化角色编号为1-6）\n")
                for i in range(6):
                    saved_skills = []
                    line = self.roles[i].name+': '
                    for skill in self.roles[i].skills:
                        if skill.name:
                            saved_skills.append(skill.name)
                    line += ", ".join(saved_skills)  # 假设你存储的信息是一个列表
                    f.write(line + "\n")  # 每条记录一行
                f.write("# 回合 = OD（后置1或2或3，前置-1或-2或-3，0为不开od）; 队伍+技能（技能位置，指向角色编号）\n")

            messagebox.showinfo("提示", "已进入技能录制界面。")
        else:
            od_mode = self.od 
            turn_event = self.event
            self.od = 0
            self.event = 0
            od_before = 1

            # 写入回合设置信息
            with open(self.file_path, "a", encoding="utf-8") as f:  # "a" 表示追加写入
                # 有其他事件发生，不要使用技能！
                if turn_event == 1:
                    f.write("skip\n")
                elif turn_event == 2:
                    f.write("change\n")
                elif turn_event == 3:
                    # f.write("前置OD\n")  V4改版后弃用
                    od_before = -1

                # 正常使用技能的回合
                else:  
                    saved_information = [f'{self.turn} = {od_mode*od_before}']
                    # 对每一个前排角色
                    for i in range(3):
                        # 考察哪个技能被选中
                        skill_arrange = '0,0'
                        for j in range(4):
                            act_mode = self.roles[i].skills[j].is_activated
                            if act_mode is not False:
                                skill_arrange = str(j+1)+','
                                if act_mode is True:
                                    skill_arrange += '0'
                                else:
                                    skill_arrange += str(act_mode+1)
                                self.roles[i].skills[j].is_activated = False
                                
                        saved_information.append(self.roles[i].name+': '+skill_arrange)
                    f.write("; ".join(saved_information) + "\n")
            
            if turn_event == 0:
                self.turn += 1
                
            self.target_bg = 0
            self.draw_all()

    # 角色按钮点击
    def on_role_click(self, idx):
        if self.mode == 'setup':
            # 重命名
            new_name = simpledialog.askstring("角色命名", f"为角色 {idx+1} 输入名字（可留空保留原名）：", parent=self.root)
            if new_name is not None and new_name.strip() != "":
                self.roles[idx].name = new_name.strip()

            # 打开技能设置面板（针对该角色）
            self.draw_all()
            self.open_skill_panel(idx)
        else:
            # 录制阶段：
            
            #若已选择角色和有指向性的技能
            if self.pending_skill_idx is not None and self.selected_role_idx is not None:
                # 正在等待选择技能目标：点击角色即作为目标
                src_role = self.selected_role_idx
                skill_idx = self.pending_skill_idx
                target_role = idx
                # 记录选择（这里仅提示，可扩展为日志）
                skill = self.roles[src_role].skills[skill_idx]
                skill.is_activated = self.roles[target_role].ind
                
                self.target_bg = 0
                self.toggle_target_bg(self.target_bg)

                self.close_skill_panel()
                return

            # 若没有选择角色：
            if self.selected_role_idx is None:
                # 打开这个角色的技能面板
                self.selected_role_idx = idx
                self.open_skill_panel(idx)

            # 若已选择了角色
            else:
                # 已经打开某个角色的技能面板：点击另一个角色 => 换位
                if idx != self.selected_role_idx:
                    self.swap_roles(self.selected_role_idx, idx)
                    self.close_skill_panel()
                    self.draw_all()
                # 再次点击同一个角色 => 面板收回
                else:
                    self.close_skill_panel()
                    


    # 技能槽点击
    def on_skill_slot_click(self, slot_idx):
        ridx = self.selected_role_idx

        if self.mode == 'setup':
            # 设置技能名与是否需要目标
            cur = self.roles[ridx].skills[slot_idx]
            new_name = simpledialog.askstring("设置技能名", f"为技能 {slot_idx+1} 输入名称：\n当前：{cur.name or '（无技能）'}",
                                              parent=self.root)
            if new_name:
                cur.name = new_name.strip()

            if cur.name:
                need = messagebox.askyesno("目标设置", "这个技能是否需要目标？\n是：有目标；否：无目标")
                cur.needs_target = bool(need)

            # 刷新面板显示
            self.open_skill_panel(ridx)
        else:
            # 录制阶段：选择技能。如果需要目标，则进入待目标状态；否则直接确认
            skill = self.roles[ridx].skills[slot_idx]

            # 使用技能
            skill.is_activated = True
            for i in range(4):
                if i != slot_idx:
                    self.roles[ridx].skills[i].is_activated = False
            # 刷新面板显示已选中的技能
            self.open_skill_panel(ridx)

            # 如果需要目标，则提示用户只能点击人物角色
            if skill.needs_target:
                self.pending_skill_idx = slot_idx
                self.target_bg = 1
                self.toggle_target_bg(self.target_bg)

            else:
                # 直接关闭
                self.close_skill_panel()



    # 交换两个角色（名字与技能整体互换）
    def swap_roles(self, i, j):
        self.roles[i], self.roles[j] = self.roles[j], self.roles[i]

    # ---------------------- 运行 ----------------------
def main(file_path):
    root = tk.Tk()

    ui = GameUI(root, file_path)

    root.geometry(f"{ui.W}x{ui.H}+200+50")  # 后面的＋是窗口位置
    root.minsize(1000, 700)
    root.mainloop()

if __name__ == "__main__":
    main("./hbrf/Ex5.hbrf")
