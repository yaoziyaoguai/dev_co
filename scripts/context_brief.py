"""提取恢复所需章节；保留原文和缺口，不生成第二份当前计划。"""
from __future__ import annotations

import re

DEFAULT_SECTIONS = ("本轮目标", "验收标准", "项目约束", "当前决定", "代码导航", "推进约定", "最近验证", "下一步")


def summarize(body: str, selected: object = None) -> str:
    titles = list(DEFAULT_SECTIONS) if selected is None else selected
    if (not isinstance(titles, list) or not titles
            or not all(isinstance(t, str) and t.strip() for t in titles)
            or len(set(titles)) != len(titles)):
        raise ValueError("brief_sections 必须为不重复的章节标题列表。")
    if len(body.strip()) <= 6500:
        return body.strip()

    lines = body.splitlines()
    headings = []
    fence = None
    for index, line in enumerate(lines):
        if fence:
            if re.fullmatch(r"\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line):
                fence = None
            continue
        opening = re.match(r"\s*(`{3,}|~{3,})", line)
        if opening:
            fence = opening[1]
            continue
        heading = re.match(r"^ {0,3}(#{1,2})[ \t]+(.+?)\s*#*\s*$", line)
        if heading:
            headings.append((heading[2], index, len(heading[1])))
    sections = []
    for index, (title, start, level) in enumerate(headings):
        end = headings[index + 1][1] if index + 1 < len(headings) else len(lines)
        if level == 2:
            sections.append((title, start + 1, end, "\n".join(lines[start + 1:end]).strip()))

    result = ["按恢复章节提取原文（行号相对正文）；截断、缺项或未列入的约束需按导航补读，不能据此宣称已完整接手。"]
    prefix_end = next((start for _, start, level in headings if level == 2), len(lines))
    intro = "\n".join(lines[:prefix_end]).strip()
    if intro:
        result.append("正文前言：\n" + intro[:400] + ("\n[前言截断，需补读]" if len(intro) > 400 else ""))
    found = [title for title in titles if any(s[0] == title for s in sections)]
    # 给每个恢复字段留位置，长历史不会挤掉末尾的下一步或验收。
    allowance = max(80, (5200 - sum(len(t) for t in found)) // max(1, len(found)))
    for title in found:
        entries = [s for s in sections if s[0] == title]
        if len(entries) != 1:
            result.append("## " + title + "\n同名段落存在歧义，请核对正文行号：" + ", ".join(str(s[1]) for s in entries))
            continue
        _, start, end, text = entries[0]
        excerpt = text[:allowance]
        if len(text) > allowance:
            excerpt += "\n[本段截断；仍需读取完整约束]"
        result.append(f"## {title}（正文 {start}–{end} 行）\n{excerpt}")
    missing = [t for t in titles if t not in found]
    if missing:
        result.append("未定位恢复章节：" + "、".join(missing) + "。按项目原章节补读；可在 brief_sections 映射实际标题。")
    other = [f"{title}（正文 {start} 行）" for title, start, _, _ in sections if title not in titles]
    if other:
        result.append("其他章节按需读取：" + "；".join(other[:12]) + ("；其余见原文" if len(other) > 12 else ""))
    if not found:
        result.append("没有可用的结构化恢复段落；请直接定位原记录中的目标、约束、验收与下一步。")
    if fence:
        result.append("发现未闭合代码围栏，后续章节可能未识别；核对原文。")
    return "\n\n".join(result)
