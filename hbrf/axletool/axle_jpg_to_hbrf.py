"""HBR-AxleTool JPG -> HBRF。调用 main(jpg_path, output_path=None)。"""
import json
import re
from pathlib import Path
from paths import ROOT_DIR

SOURCE = "https://hbr-axletool.pages.dev/"
IGNORED = {None, "", "普攻", "指揮行動", "魔界騎兵起動！", "鬼神化"}
DATA_DIR = ROOT_DIR / "assets" / "char-data"

def extract_axle_json(image_path: str | Path) -> dict:
    """从网站导出的 JPG EXIF.UserComment 解压 JSON。"""
    import piexif
    from lzstring import LZString

    exif = piexif.load(str(image_path))
    custom_data = exif.get("Exif", {}).get(piexif.ExifIFD.UserComment)
    if not custom_data:
        raise ValueError("图片没有排轴 EXIF 数据，可能是截图或被重新保存过。")
    if isinstance(custom_data, bytes):
        custom_data = custom_data.decode("ascii")
    decoded = LZString().decompressFromBase64(custom_data)
    if not decoded:
        raise ValueError("LZ-String 解压失败")
    data = json.loads(decoded)
    missing = {"version", "char", "skills", "turns"} - data.keys()
    if missing:
        raise ValueError(f"排轴数据缺少字段：{missing}")
    return data


def convert_axle_data(data, output_path):
    """从已解压 JSON 转换；返回 (Path, warnings)，方便单元测试和 GUI 调用。"""
    from hbrf import model as m

    warnings, roles, metadata = [], [], []
    # 解析开头角色部分
    tab, characters = next(iter(data["char"].items()))  # 由于异时层，保存tab队伍
    slots, style_slots = {}, {}
    for i in range(1, 7):
        item = characters[str(i)]
        name, title, team = item["character"], item["style"], item["team"]
        db = json.loads((DATA_DIR / f"{team}.json").read_text(encoding="utf-8"))
        record = db.get(name)
        style_record = next(
            (v for v in record.get("style", {}).values()
            if isinstance(v, dict) and v.get("value") == title),
            None
        )
        # 在对应队伍json文件中找不到角色或者风格
        if record is None or style_record is None:
            warnings.append(f"Slot {i} 风格未匹配：{team}/{name}/{title}")
        # 优先获取国服简中CN-CN
        zh = (record or {}).get("names", {}).get("zh-CN-CN") or (record or {}).get("names", {}).get("zh-CN") or name
        roles.append(m.Role(i, re.sub(r"\s+", "", zh), []))  # 空白字符替换消除
        english = (record or {}).get("english name")
        sid = item["style_id"]
        sid = sid[0] if isinstance(sid, list) else sid  # 多个id选第一个
        metadata.append({"team": team, "english": english, "id": str(sid)})
        slots[(str(tab), title)] = i  # (tab, 风格名): slot
        style_slots[name] = i

    # 仅读取轻量的特殊技能配置，不遍历各队角色和技能数据库。
    special_file = DATA_DIR / "special_skills.json"
    special = json.loads(special_file.read_text(encoding="utf-8")) if special_file.exists() else {}
    links = {}
    for name, groups in special.get("switchable", {}).items():
        if name not in style_slots:
            continue
        # group是一个风格及其所对应的技能，这里保存了(slot, skill名): link名
        for group in groups.values():
            links.update({(style_slots[name], v["value"]): v["link"] for v in group.values()})

    # 第一次遍历：按出现顺序收集技能；可切换的一对技能仅占一个技能槽。
    used = {i: [] for i in range(1, 7)}
    initial = {}
    # 每行行动
    for row in data["skills"]:
        # 每个slot行动
        for cell in row:
            skill = cell.get("skill")
            slot = slots.get((str(cell.get("selectedTab")), cell.get("style")))
            # 排除普攻、指挥、null和特殊行动等
            if slot is None or skill in IGNORED:
                continue
            # 可切换技能用技能对frozenset表示，不可切换则是技能value本身
            link = links.get((slot, skill))
            key = frozenset((skill, link)) if link else skill
            if key not in used[slot]:
                used[slot].append(key)
            # 对于可切换技能initial默认为第一次出现的技能，用户可以通过再次保存以更改
            if link:
                initial.setdefault((slot, key), skill)
    # 还原角色使用过的技能，不检查技能合法性
    for role in roles:
        role.skills = [
            initial[(role.slot, s)] + "/" + next(v for v in s if v != initial[(role.slot, s)])
            if isinstance(s, frozenset) else s for s in used[role.slot]
        ]

    # 第二次遍历：构造行动；技能切换及可怜变身都插在 BattleTurn 前。
    actions, current_skill, current_form = [], dict(initial), {}
    last_turn, seen_plain, previous_front = {"t":"T1", "od":""}, set(), [1, 2, 3]
    for index, (row, turn) in enumerate(zip(data["skills"], data["turns"]), 1):
        # 目前先忽略Switch切换队伍部分
        if turn.get("turn") == "Switch":
            continue
        # 首先解析行动部分
        moves, switches, buttons = [], [], []
        # 对3个前排position分别确定行动
        for position, cell in enumerate(row):
            now_slot = slots.get((str(cell.get("selectedTab")), cell.get("style")))
            # 例如单人追加回合里其他位置会是null，沿用之前角色
            if now_slot is None:
                slot = previous_front[position]
            else:
                slot = now_slot
            skill = cell.get("skill")  # 如果now_slot就没有那skill也是None
            if skill == "魔界騎兵起動！":
                buttons.append(m.SpecialGlobalButton("waki"))
                skill = None
            elif skill == "鬼神化":
                buttons.append(m.SpecialRoleButton(slot, position, "siling"))
                skill = None
            form = cell.get("activeFormId")
            if form is not None:
                # 可怜第一次见默认009-1
                if slot not in current_form:
                    current_form[slot] = "009-1"
                if current_form[slot] != form:
                    switches.append(m.SpecialRoleButton(slot, position, "kelian"))
                current_form[slot] = form
            # 确定一般技能行动
            if skill in (None, "", "普攻", "指揮行動"):
                skill_id = 0
            else:
                link = links.get((slot, skill))
                key = frozenset((skill, link)) if link else skill
                skill_id = used[slot].index(key) + 1
                if link and current_skill[(slot, key)] != skill:
                    switches.append(m.SkillSwitch(slot, skill_id, position))
                    current_skill[(slot, key)] = skill
            target = cell.get("target")
            target = style_slots.get(target, target) if isinstance(target, str) else target  # 有就是1-6，没有就是None
            moves.append(m.SkillAction(slot, skill_id, target))
        actions.extend(buttons)
        actions.extend(switches)
        # 既有waki/司令按钮又有index非0的普通技能
        if buttons and any(a.skill for a in moves):
            warnings.append(f"第 {index} 行特殊按钮与技能混用，已拆分行动")
        # 只有特殊按钮就直接下一回合
        if buttons and not any(a.skill for a in moves):
            continue

        # 由于特殊按钮不需要label，因此后解析label
        t, od = turn.get("turn"), turn.get("od")
        # 不是追加回合则更新last_turn，否则延续之前的
        if t and t != "追加回合":  # 无论什么语言，追加回合在json中都写作简体中文
            last_turn["t"], last_turn["od"] = t, od
        extra = t == "追加回合"
        label = last_turn["t"]  # 现在的label应该是Tn
        # 处于od内
        if last_turn["od"]:
            match = re.search(r"OD([123])(?:/Bonus([123]))?", last_turn["od"])
            if match:
                level, bonus = match.groups()
                direction = "后置" if not bonus or last_turn["t"] in seen_plain else "前置"
                # 没有bonus的默认后置OD-OD前
                if bonus:
                    label += f"-{direction}OD{level}-bonus{bonus}"
                else:
                    label += f"-{direction}OD{level}-OD前"
        # 不处于od内则只需要考虑是否新过了一个回合
        else:
            if t and t != "追加回合":
                seen_plain.add(t)
        if extra:
            label += "-追加"

        # 正常行动加入BattleTurn，暂时不写入od值，这里一定len(moves)=3
        if moves:
            actions.append(m.BattleTurn(label, 0, moves))
            previous_front = [a.role for a in moves]

    # 第三次遍历：通过相邻回合确定 OD 的发动位置和方向。
    turns = [a for a in actions if isinstance(a, m.BattleTurn)]
    for i, turn in enumerate(turns, 1):  # turn是turns[i-1]
        # 前置OD可以直接判断
        pre = re.search(r"-前置OD([123])-bonus1(?:-追加)?$", turn.label)
        if pre and not turn.label.endswith("-追加"):
            turn.od = -int(pre.group(1))
        # 后置OD需要用下一个turn判断，同时更改label为OD前
        if i < len(turns):
            nxt = turns[i]
            post = re.search(r"-后置OD([123])-bonus1(?:-追加)?$", nxt.label)
            if post and not nxt.label.endswith("-追加"):
                level = int(post.group(1))
                base = re.match(r"T\d+", nxt.label)
                if base:
                    turn.label = f"{base.group()}-后置OD{level}-OD前" + (
                        "-追加" if turn.label.endswith("-追加") else "")
                    turn.od = level

    script = m.BattleScript(roles, actions)
    m.validate_hbrf(script)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # 先写入hbrf
    m.save_hbrf(script, output)
    # 然后额外添加文件头来源注释和底部HBRTOOL_STYLE注释
    saved = output.read_text(encoding="utf-8")
    title = str(data.get("axleName") or "").replace("\n", " ").replace("\r", " ")
    header = f"# 来源：{SOURCE}，需要手动检查调整并重新保存\n# 原图轴名称：{title}\n\n"
    footer = "\n# HBRTool style metadata\n" + "".join(
        f"# HBRTOOL_STYLE {i} {json.dumps(info, ensure_ascii=False)}\n"
        for i, info in enumerate(metadata, 1)
    )
    output.write_text(header + saved + footer, encoding="utf-8")
    return output, warnings


def main(image_path, output_path=None):
    """供 GUI 或其他 Python 文件直接调用：main('axle.jpg')。"""
    path = Path(image_path)
    return convert_axle_data(
        extract_axle_json(path),
        output_path or path.with_suffix(".hbrf"),
    )


# if __name__ == "__main__":
#     main()