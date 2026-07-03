#!/usr/bin/env python3
"""
Batch enrich SKILL.md frontmatter with tags/capabilities/scenarios/paired_with/version.
Reads existing frontmatter, infers missing fields from description + body keywords.
"""

import os
import re
import sys

SKILLS_DIR = os.path.expanduser("~/.claude/skills")

# Each skill: {name, tags, capabilities, scenarios, paired_with, version}
ENRICHMENTS = {
    "bifeng": {
        "version": "1.0.0",
        "tags": ["writing", "chinese", "content"],
        "capabilities": "公众号长文、中短篇小说、长篇小说章节、机构汇报、对公营销、法律文书六种文体创作、L0/L1/L2质量门禁、Python辅助工具链、DNA记忆系统",
        "scenarios": "中文写作、公众号文章、小说创作、机构汇报、法律文书写作",
        "paired_with": ["novel-learner", "grill-with-docs"],
    },
    "darwin-skill": {
        "version": "2.0.0",
        "tags": ["optimization", "meta", "skill-management"],
        "capabilities": "SKILL.md 9维评估、hill-climbing 自动优化、git版本控制、独立评判agent盲评、test prompt验证、视觉结果卡生成",
        "scenarios": "技能优化、技能评分、自动优化、技能质量检查",
        "paired_with": ["skill-creator", "skill-rpg-loop", "sebastian"],
    },
    "ecommerce-visual-copywriting": {
        "version": "1.0.0",
        "tags": ["copywriting", "ecommerce", "marketing"],
        "capabilities": "电商主图文案设计、详情页文案方案、画面内容+图内文案+设计说明输出、合规自审、广告法风险审查",
        "scenarios": "淘宝/天猫/京东/拼多多/抖音商品主图文案、详情页文案、listing优化",
        "paired_with": ["shuixian", "brandkit"],
    },
    "grill-with-docs": {
        "version": "1.0.0",
        "tags": ["planning", "documentation", "review"],
        "capabilities": "方案质询与压力测试、术语精度打磨、CONTEXT.md同步更新、ADR决策记录",
        "scenarios": "方案评审、需求澄清、术语统一、架构决策讨论",
        "paired_with": ["skill-creator", "darwin-skill", "domain-modeling"],
    },
    "guizang-ppt-skill": {
        "version": "1.0.0",
        "tags": ["design", "presentation", "ppt"],
        "capabilities": "横向翻页网页PPT生成(单HTML)、WebGL背景、章节幕封、数据大字报、图片网格、电子杂志×电子墨水风格、瑞士国际主义风格",
        "scenarios": "分享演讲、产品发布会、网页PPT、杂志风PPT、瑞士风PPT",
        "paired_with": ["guizang-social-card-skill", "brandkit", "shuixian"],
    },
    "guizang-social-card-skill": {
        "version": "1.0.0",
        "tags": ["design", "social-media", "image-generation"],
        "capabilities": "社交卡片图组生成、小红书图文生成、微信公众号封面生成(21:9+1:1)、3:4车图",
        "scenarios": "小红书图文、社交媒体卡片、微信公众号封面、杂志风社交图片",
        "paired_with": ["guizang-ppt-skill", "brandkit", "shuixian"],
    },
    "huashu-design": {
        "version": "1.0.0",
        "tags": ["design", "prototyping", "animation", "ui"],
        "capabilities": "HTML高保真原型、交互Demo、动画制作、幻灯片生成、设计变体探索、设计方向顾问、5维设计评审、MP4/GIF导出、带解说长视频pipeline",
        "scenarios": "原型制作、交互Demo、动画演示、设计方向咨询、设计评审",
        "paired_with": ["design-taste-frontend", "shuixian", "high-end-visual-design"],
    },
    "kami": {
        "version": "1.0.0",
        "tags": ["design", "document", "typesetting", "pdf"],
        "capabilities": "PDF/简历/作品集/白皮书/落地页排版、衬线字体层次编排、和式/中式排版风格",
        "scenarios": "简历制作、PDF排版、一页纸设计、产品落地页、作品集",
        "paired_with": ["docx", "pptx", "xlsx"],
    },
    "novel-learner": {
        "version": "1.0.0",
        "tags": ["writing", "learning", "fiction"],
        "capabilities": "从修改中学习创作原则、5维分析(逻辑/人物/节奏/文笔/世界观)、番茄小说短故事创作(4000-30000字)",
        "scenarios": "小说创作、小说修改、人物塑造讨论、情节逻辑分析",
        "paired_with": ["bifeng", "grill-with-docs"],
    },
    "panel-of-experts": {
        "version": "2.1.0",
        "tags": ["planning", "consultation", "decision-making"],
        "capabilities": "多角色专家协作讨论(9位)、差异化输出(简单/中等/复杂)、核心观点前置、用户检查点、协作反馈",
        "scenarios": "战略规划、技术选型、系统设计、职业发展、复杂决策",
        "paired_with": ["grill-with-docs", "sebastian"],
    },
    "shuixian": {
        "version": "1.0.0",
        "tags": ["design", "review", "art-direction"],
        "capabilities": "美术总监前置参数拦截、Prompt审查与风格红线注入、VND噪声密度计算、AST圆角/阴影检查、一票否决与可量化修改指令、美学记忆维护",
        "scenarios": "设计评审、AI生图Prompt审查、视觉品质控制、美术方向把关",
        "paired_with": ["brandkit", "design-taste-frontend", "high-end-visual-design", "text2img", "img2img"],
    },
    "skill-rpg-loop": {
        "version": "1.0.0",
        "tags": ["optimization", "meta", "learning", "loop"],
        "capabilities": "Skill经验值管理(ok+1/modified+3/failed+5)、XP≥5触发darwin-skill升级、等级/经验/教训/履历查看、定时自动巡检",
        "scenarios": "技能练级、技能升级、查看技能等级、技能经验审查",
        "paired_with": ["darwin-skill", "sebastian"],
    },
    "superpowers-universal": {
        "version": "1.0.0",
        "tags": ["utility", "automation"],
        "capabilities": "通用能力增强、自动化工作流",
        "scenarios": "通用自动化任务",
        "paired_with": [],
    },
    "image-recognition": {
        "version": "1.0.0",
        "tags": ["vision", "ocr", "image"],
        "capabilities": "通用识图描述、OCR文字提取(中文/英文)、物体检测定位、构图/风格/专业深度分析",
        "scenarios": "图片内容识别、图片文字提取、物体检测、图片专业分析",
        "paired_with": ["text2img", "img2img"],
    },
    "img2img": {
        "version": "1.0.0",
        "tags": ["image-generation", "image-editing"],
        "capabilities": "基于参考图的新图生成、风格转换、图片融合变换",
        "scenarios": "图生图、风格转换、图片改造",
        "paired_with": ["text2img", "image-recognition", "shuixian"],
    },
    "text2img": {
        "version": "1.0.0",
        "tags": ["image-generation"],
        "capabilities": "文生图、参数收集(风格/构图/色彩/比例)、多轮问答确定需求、配图/插图/海报生成",
        "scenarios": "生成配图、插图、海报、产品图",
        "paired_with": ["img2img", "image-recognition", "shuixian"],
    },
    "nano-banana-pro-prompts-recommend-skill": {
        "version": "1.0.0",
        "tags": ["prompts", "recommendation"],
        "capabilities": "Prompt推荐与建议",
        "scenarios": "Prompt优化、Prompt推荐",
        "paired_with": [],
    },
}

# taste-skill batch (Leonxlnx/taste-skill)
TASTE_SKILLS = {
    "full-output-enforcement": {
        "tags": ["utility", "code-generation"],
        "capabilities": "强制完整代码输出、禁止占位符/省略号/TODO、超长时整洁断点停顿等待continue续写",
        "scenarios": "需要完整代码输出的场景、防止LLM截断偷懒",
        "paired_with": ["design-taste-frontend", "high-end-visual-design"],
    },
    "gpt-taste": {
        "tags": ["design", "frontend", "gpt"],
        "capabilities": "GPT/Codex严格设计品味、高布局方差、Python伪随机打破路径依赖、GSAP ScrollTrigger动效、激进反同质化",
        "scenarios": "GPT/Codex平台的Web设计、需要严格设计品味的代码生成",
        "paired_with": ["design-taste-frontend", "high-end-visual-design", "industrial-brutalist-ui"],
    },
    "high-end-visual-design": {
        "tags": ["design", "visual", "premium"],
        "capabilities": "Awwwards级agency质感设计、精确定义字体/间距/阴影/卡片结构/动效、Geist/Clash Display字体、双边框卡片",
        "scenarios": "高端网站设计、品牌官网、Awwwards级页面",
        "paired_with": ["design-taste-frontend", "brandkit", "minimalist-ui", "shuixian"],
    },
    "image-to-code": {
        "tags": ["design", "frontend", "image-generation"],
        "capabilities": "图转代码管线——先生成高质量视觉参考图→分析→翻译为前端代码",
        "scenarios": "从设计图生成网页代码、设计稿转前端",
        "paired_with": ["design-taste-frontend", "imagegen-frontend-web", "shuixian"],
    },
    "imagegen-frontend-mobile": {
        "tags": ["design", "mobile", "image-generation"],
        "capabilities": "移动App屏幕概念图生成、流程示意图生成、多屏一致性锁定(设计圣典)、手机模型框内嵌",
        "scenarios": "App UI概念设计、移动端流程示意图、App改版视觉参考",
        "paired_with": ["imagegen-frontend-web", "design-taste-frontend", "shuixian"],
    },
    "imagegen-frontend-web": {
        "tags": ["design", "web", "image-generation"],
        "capabilities": "网站各区块高质量设计参考图生成、单图单区块、构图锚点多样变化、统一调色板",
        "scenarios": "Web设计参考图、网站页面区块视觉探索、UI设计预视觉化",
        "paired_with": ["imagegen-frontend-mobile", "design-taste-frontend", "high-end-visual-design"],
    },
    "industrial-brutalist-ui": {
        "tags": ["design", "ui", "brutalist"],
        "capabilities": "直角禁止border-radius、极端克制配色、两极分化排版、数据文本等宽字体、军事终端美学",
        "scenarios": "数据密集型页面、作品集、工业风品牌站点",
        "paired_with": ["minimalist-ui", "design-taste-frontend", "high-end-visual-design"],
    },
    "minimalist-ui": {
        "tags": ["design", "ui", "minimalist"],
        "capabilities": "Notion/Linear风格编辑型UI、暖色单色、大留白、bento-grid、纯平组件、1px细边框、圆角≤12px、动效仅transform/opacity",
        "scenarios": "编辑型网页、管理后台、B端产品UI",
        "paired_with": ["industrial-brutalist-ui", "design-taste-frontend", "high-end-visual-design"],
    },
    "redesign-existing-projects": {
        "tags": ["design", "frontend", "refactoring"],
        "capabilities": "已有项目UI审计、AI模板痕迹识别、高端设计标准定向修复、非破坏性升级(兼容任意CSS框架)",
        "scenarios": "已有项目UI改造、AI生成模板的视觉升级、设计债务清理",
        "paired_with": ["design-taste-frontend", "high-end-visual-design", "shuixian"],
    },
    "stitch-design-taste": {
        "tags": ["design", "design-system", "google"],
        "capabilities": "Google Stitch项目DESIGN.md设计规范生成、严格排版、校准配色、非对称布局、持续微动效",
        "scenarios": "Google Stitch项目设计规范编写、设计系统文档化",
        "paired_with": ["design-taste-frontend", "high-end-visual-design"],
    },
}


YAML_DELIMITER = re.compile(r"^---\s*$", re.MULTILINE)


def parse_frontmatter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, None
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, text, None
    fm_lines = lines[1:end_idx]
    body_lines = lines[end_idx + 1:]
    return "\n".join(fm_lines), "\n".join(body_lines).strip(), end_idx


def add_fields_to_frontmatter(fm_text, skill_name, enrichments):
    """Add missing fields to existing frontmatter text."""
    existing = set()
    for line in fm_text.split("\n"):
        m = re.match(r"^(\w+):", line.strip())
        if m:
            existing.add(m.group(1))

    additions = []
    fields_to_add = ["version", "tags", "capabilities", "scenarios", "paired_with"]
    for f in fields_to_add:
        if f in existing:
            continue
        if f in enrichments:
            val = enrichments[f]
            if isinstance(val, list):
                additions.append(f"{f}: [{', '.join(val)}]")
            else:
                additions.append(f"{f}: {val}")

    if not additions:
        return fm_text

    return fm_text.rstrip() + "\n" + "\n".join(additions)


def main():
    version_enrich = {}
    version_enrich.update({k: {"version": "1.0.0", **v} for k, v in ENRICHMENTS.items()})
    version_enrich.update({k: {"version": "1.0.0", **v} for k, v in TASTE_SKILLS.items()})

    count = 0
    errors = []

    for skill_name, enrich in version_enrich.items():
        fp = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        if not os.path.exists(fp):
            errors.append(f"{skill_name}: file not found")
            continue

        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()

        fm_text, body, end_line = parse_frontmatter(text)
        if fm_text is None:
            errors.append(f"{skill_name}: no frontmatter")
            continue

        new_fm = add_fields_to_frontmatter(fm_text, skill_name, enrich)
        if new_fm == fm_text:
            continue

        new_text = "---\n" + new_fm + "\n---\n\n" + body

        with open(fp, "w", encoding="utf-8") as f:
            f.write(new_text)

        print(f"  [OK] {skill_name}")
        count += 1

    print(f"\nUpdated {count} skill(s)")
    if errors:
        for e in errors:
            print(f"  [ERR] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
