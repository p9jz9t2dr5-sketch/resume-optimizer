"""模型调用层：把 DeepSeek（OpenAI 兼容协议）与 Qwen-VL（百炼 DashScope）封装成几个方法，
所有 prompt 也集中在这个文件里（JD 解析、简历解析、匹配分析、面试官对话、简历改写、图片 OCR）。

上层（api / services）只调用方法名，不直接接触 SDK，换模型时只改这里。
"""

import base64
import json
import logging
import os
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI

from app.config import get_settings
from app.schemas.jd import ParsedRequirement, MatchReport

settings = get_settings()

JD_PARSE_SYSTEM_PROMPT = """You are a senior HR professional and technical interviewer at a top tech company.
Analyze the following job description and extract structured requirements.

Return ONLY valid JSON with this exact structure:
{
  "company_name": "company name or null",
  "title": "job title or null",
  "parsed_requirements": {
    "skills": ["skill1", "skill2"],
    "experience_years": "3-5 years or null",
    "education": "Bachelor's in CS or null",
    "responsibilities": ["responsibility1", "responsibility2"],
    "qualifications": ["qualification1", "qualification2"],
    "keywords": ["keyword1", "keyword2"]
  }
}

Important:
- Extract ALL mentioned skills, tools, frameworks, and technologies as keywords
- Include soft skills mentioned (communication, teamwork, leadership)
- Be specific about years of experience if mentioned
- List languages, frameworks, databases, cloud platforms separately
"""

RESUME_PARSE_SYSTEM_PROMPT = """You are a senior HR professional and resume parser.
Analyze the candidate's resume and extract it into structured fields.

Return ONLY valid JSON with this exact structure:
{
  "basic_info": {
    "years_of_experience": "5 years or null",
    "job_title": "current or desired job title or null",
    "location": "city or null",
    "phone": "phone number or null",
    "email": "email or null"
  },
  "summary": "one-line professional summary or null",
  "education": [
    {"school": "school name", "degree": "Bachelor", "major": "major", "start": "2014", "end": "2018"}
  ],
  "work_experience": [
    {"company": "company", "title": "job title", "start": "2018", "end": "2021", "description": "concise summary of responsibilities and achievements"}
  ],
  "projects": [
    {"name": "project name", "role": "role", "description": "what was built and its impact", "tech_stack": ["Go", "MySQL"]}
  ],
  "skills": ["skill1", "skill2"],
  "certificates": ["certificate1"],
  "languages": ["language1"]
}

Guidelines:
- Every list must be a JSON array (empty [] if none found); every object field defaults to null if absent.
- Extract all skills, tools, frameworks, languages, and databases mentioned across the resume.
- For work_experience and projects, keep each entry's description factual and quantified where present — do not invent.
- Respond in the resume's original language for text fields.
"""

MATCH_ANALYSIS_SYSTEM_PROMPT = """You are a senior HR professional and technical interviewer.
Compare the candidate's resume against the job requirements.

Focus ONLY on skills, experience, and qualifications.

Return ONLY valid JSON:
{
  "overall_score": 75,
  "matched_keywords": ["keyword1"],
  "missing_keywords": ["keyword2"],
  "skill_gaps": ["gap description"],
  "suggestions": ["specific improvement suggestion"]
}

Scoring guidelines:
- 90-100: Excellent match, meets all core requirements
- 75-89: Good match, meets most requirements with minor gaps
- 60-74: Partial match, significant gaps in skills or experience
- 40-59: Weak match, major requirements not met
- Below 40: Poor match, fundamentally different profile

Be specific and actionable in suggestions. Reference the STAR method and quantification.
"""

CHAT_SYSTEM_PROMPT = """你是一位资深技术面试官，正在对候选人进行一对一的模拟面试。你的任务是围绕候选人简历里的项目经历、工作经历和技能，像真实面试官一样提问、追问。

面试原则：
1. 一次只问一个问题，语气自然、口语化，像真人面试官，绝不一次性抛出多个问题或列清单
2. 围绕简历中的项目经历、工作经历深入追问，考察真实性、技术深度和思考过程
3. 追问细节：项目背景、你的具体角色与职责、技术选型与权衡、遇到的最大难点、量化成果、复盘反思
4. 用 STAR 方法引导候选人完整陈述（情境-任务-行动-结果）
5. 候选人回答后，先简短回应（表示你在听、点出关键点），再自然追问下一个问题或换个方向
6. 适当追问简历里模糊、夸大或前后矛盾的地方，考察真实水平
7. 全程用中文，专业、友好、有分寸

注意：
- 你的每条回复应该像面试官说的一段话，而不是一堆问题列表或长篇分析
- 不要变成简历修改顾问，不要主动给出"标准答案"
- 只有当候选人明确请你"点评我的回答"或"总结面试表现"时，才给出点评或总结"""


IMAGE_PARSE_SYSTEM_PROMPT = """你是一个专业的简历 OCR 与结构化助手。用户会给你一张简历图片（可能是手机截图、带照片和彩色版块的"视觉简历"，如锤子简历、Canva 模板等）。

你的任务：把图片中的全部可见文字按原图版面结构转写成 Markdown 文本，要求：
1. 用 "#"/"##"/"###" 还原原图的版块层级（如 个人信息、求职意向、教育背景、工作经历、项目经历、专业技能、证书与荣誉、自我评价 等）
2. 保留所有文字内容，包括姓名、电话、邮箱、公司名、职位、项目名、时间、数字指标、技能名词等，不要省略、不要概括
3. 原图中的列表项用 "- " 表示
4. 头像、图标、装饰图形等无文字内容可以忽略，但凡是图内文字（含图标旁的标签）都要读出
5. 输出纯 Markdown，不要外加 ```markdown 代码块围栏，也不要加任何解释
6. 如果图片是中文简历，就用中文输出；其他语言保持原文

注意：后续系统会自动对姓名、电话、邮箱做去隐私处理，所以请如实读出这些信息，不要自行遮盖。"""


AVATAR_BBOX_SYSTEM_PROMPT = """你是一个图像分析助手。请在一张简历图片中找到"求职者的照片/头像"（通常是人物正脸照片，圆形或方形，位于简历顶部或个人信息区域）。

调用方式：我会先把图片等比缩放到"长边不超过 800 像素"再发给你，并在 user 文案里明确告诉你这张图的 (宽, 高) 是多少像素。请**严格按这个尺寸**返回 bbox——**坐标系就是这张缩放后的图的像素坐标**，**不要**返回原图尺寸，**不要**返回百分比。

请严格只返回一个 JSON 对象，不要任何解释、不要代码块围栏：
{
  "has_avatar": true 或 false,
  "x": 头像外接矩形左上角横坐标（按提示的图像宽理解）,
  "y": 头像外接矩形左上角纵坐标（按提示的图像高理解）,
  "width": 头像外接宽度,
  "height": 头像外接高度
}

要求：
- **坐标就是提示中的图像尺寸**（例如提示"图大小 564x800"则 x 取 0~564 之间的整数）。
- 原点为图像左上角，x/y 表示头像外接矩形左上角，width/height 是其宽高。
- 框选范围宁可稍紧（贴合人像脸部/肩部），不要包含周围大片空白或装饰边框。
- 如果图片中没有人脸照片（如纯文字简历、只有公司 logo 或图标），has_avatar 必须为 false，其余字段为 0。
- 若头像为圆形裁剪，请按外接矩形框选。
"""


class LLMService:
    def __init__(self):
        """准备两个客户端：DeepSeek（对话 / 改写）与 DashScope（图片简历 OCR）。"""
        import httpx
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        # 视觉模型客户端（图片简历 OCR）—— 阿里云 DashScope 的 OpenAI 兼容端点
        self.vision_client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
            timeout=httpx.Timeout(90.0, connect=10.0),
        )

    def _get_model(self, is_premium: bool = False) -> str:
        """按账号档位选模型：会员用 AI_PREMIUM_MODEL，免费用户用 AI_FAST_MODEL。"""
        return settings.AI_PREMIUM_MODEL if is_premium else settings.AI_FAST_MODEL

    async def parse_jd(self, raw_text: str, is_premium: bool = False) -> dict:
        """Parse a job description into structured requirements."""
        response = await self.client.chat.completions.create(
            model=self._get_model(is_premium),
            messages=[
                {"role": "system", "content": JD_PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Parse this job description:\n\n{raw_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    async def parse_resume(self, anonymized_resume: str, is_premium: bool = False) -> dict:
        """Parse an anonymized resume into structured fields (education/work/projects/skills...)."""
        response = await self.client.chat.completions.create(
            model=self._get_model(is_premium),
            messages=[
                {"role": "system", "content": RESUME_PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Parse this resume:\n\n{anonymized_resume}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=3000,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)


    async def detect_avatar_bbox(self, image_path: str) -> Optional[dict]:
        """Detect the person's photo bounding box in a resume image via Qwen-VL.

        Returns {"x": px, "y": px, "width": px, "height": px} in pixel coords,
        or None if no avatar is found / the vision call fails.

        NOTE: For new code prefer detect_avatar_bbox_with_size() which lets the
        caller control the image sent to the model and pass its (W, H) explicitly.
        This raw version is kept for backwards compatibility — it just resizes
        the file the same way and annotates the (W, H) in the user text.
        """
        if not settings.DASHSCOPE_API_KEY:
            return None

        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        # Pre-resize the image to a known coordinate space (long edge 800)
        # and tell the model the size explicitly.
        try:
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                W, H = im.size
            import io
            scale = 800.0 / max(W, H) if max(W, H) > 800 else 1.0
            nW = max(1, int(round(W * scale)))
            nH = max(1, int(round(H * scale)))
            with Image.open(image_path) as im:
                im = im.convert("RGB").resize((nW, nH), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="PNG", optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return await self.detect_avatar_bbox_with_size(
                image_b64=b64, mime="image/png", width=nW, height=nH
            )
        except Exception:
            return None

    async def detect_avatar_bbox_with_size(
        self,
        image_b64: str,
        mime: str,
        width: int,
        height: int,
    ) -> Optional[dict]:
        """Same as detect_avatar_bbox, but accepts a pre-encoded image and its
        pixel dimensions. Coordinates in the returned bbox are relative to the
        given (width, height).
        """
        if not settings.DASHSCOPE_API_KEY:
            return None

        try:
            response = await self.vision_client.chat.completions.create(
                model=settings.QWEN_VL_MODEL,
                messages=[
                    {"role": "system", "content": AVATAR_BBOX_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"图大小 {width}x{height} 像素。"
                                    "请找出这张简历图片中求职者的头像位置，"
                                    "按上方 JSON 格式返回。"
                                    f"坐标请严格基于 {width}x{height} 这个尺寸。"
                                ),
                            },
                        ],
                    },
                ],
                temperature=0.0,
                max_tokens=500,
            )
        except Exception:
            return None

        raw = (response.choices[0].message.content or "").strip()
        # Strip optional code fences if the model added them despite instructions.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except Exception:
            return None

        if not data.get("has_avatar"):
            return None

        try:
            x = float(data.get("x", 0))
            y = float(data.get("y", 0))
            w = float(data.get("width", 0))
            h = float(data.get("height", 0))
        except (TypeError, ValueError):
            return None

        if w <= 0 or h <= 0:
            return None

        return {"x": x, "y": y, "width": w, "height": h}

    async def parse_image(self, image_path: str, is_premium: bool = False) -> str:
        """OCR a resume image (png/jpg/jpeg/webp) into Markdown text via Qwen-VL.

        The image is read locally, base64-encoded, and sent as a data URL in the
        vision request. Returns the model's Markdown transcription (raw text,
        before anonymization). Raises RuntimeError if the vision API fails.
        """
        if not settings.DASHSCOPE_API_KEY:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法识别图片简历")

        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")

        response = await self.vision_client.chat.completions.create(
            model=settings.QWEN_VL_MODEL,
            messages=[
                {"role": "system", "content": IMAGE_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": "请按上方要求，将这张简历图片转写为 Markdown 文本。",
                        },
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        return (response.choices[0].message.content or "").strip()

    async def analyze_match(
        self, anonymized_resume: str, parsed_requirements: dict, is_premium: bool = False
    ) -> MatchReport:
        """Generate a match score and missing keywords report."""
        response = await self.client.chat.completions.create(
            model=self._get_model(is_premium),
            messages=[
                {"role": "system", "content": MATCH_ANALYSIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Resume:\n{anonymized_resume}\n\nJob Requirements:\n{json.dumps(parsed_requirements, ensure_ascii=False)}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return MatchReport(**data)

    async def interview_opening(
        self,
        resume_text: str,
        jd_text: str,
        is_premium: bool = False,
    ) -> str:
        """Generate the interviewer's opening line to kick off a mock interview."""
        system_message = f"""你是一位资深技术面试官，即将开始一场一对一的模拟面试。

=== 候选人简历 ===
{resume_text}

=== 目标岗位 JD ===
{jd_text}

你的任务：作为面试官，自然地开启这场面试。请用中文说一段开场白，包含：
1. 简短自我介绍（你是面试官，今天来聊聊）
2. 简单说明今天的面试会围绕简历里的项目和经历展开
3. 提出第一个问题（引导候选人先做个自我介绍）

要求：
- 语气自然、口语化，像真人面试官，不要机械、不要啰嗦
- 开场白控制在 100 字左右
- 直接输出开场白文字，不要任何 Markdown 标题、符号或列表
"""
        response = await self.client.chat.completions.create(
            model=self._get_model(is_premium),
            messages=[{"role": "system", "content": system_message}],
            temperature=0.8,
            max_tokens=300,
        )
        return response.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[dict],
        anonymized_resume: str,
        jd_text: str,
        is_premium: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream an interviewer reply during a mock interview."""
        logger = logging.getLogger("uvicorn")
        logger.info(
            "llm chat_stream: model=%s resume_len=%d jd_len=%d history=%d",
            self._get_model(is_premium), len(anonymized_resume or ""), len(jd_text or ""), len(messages),
        )

        system_message = {
            "role": "system",
            "content": CHAT_SYSTEM_PROMPT
            + f"\n\n=== RESUME ===\n{anonymized_resume}\n\n=== JOB DESCRIPTION ===\n{jd_text}",
        }

        full_messages = [system_message] + messages

        stream = await self.client.chat.completions.create(
            model=self._get_model(is_premium),
            messages=full_messages,
            stream=True,
            temperature=0.7,
            max_tokens=4096,
        )

        async for chunk in stream:
            # `choices` can legitimately be empty (e.g. the trailing usage-only
            # chunk), so never index it blindly — that raises IndexError mid-stream
            # and the caller reports it to the user as a generic AI service error.
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content

    async def polish_stream(
        self,
        anonymized_resume: str,
        jd_text: str,
        match_report: dict | None = None,
        is_premium: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream a polished/rewritten resume tailored to the job description."""
        gaps_note = ""
        if match_report:
            gaps_note = f"\n\n=== 匹配分析与差距 ===\n综合评分: {match_report.get('overall_score', 'N/A')}/100\n缺失关键词: {', '.join(match_report.get('missing_keywords', []))}\n技能差距: {'; '.join(match_report.get('skill_gaps', []))}\n优化建议: {'; '.join(match_report.get('suggestions', []))}"

        system_message = f"""你是一位顶级科技公司的资深简历顾问和HR专家，擅长用STAR方法论指导简历优化。

=== 原始简历 ===
{anonymized_resume}

=== 目标岗位JD ===
{jd_text}
{gaps_note}

你的任务：针对这份简历和目标岗位，给出具体、可落地的简历优化建议。
注意：输出的是「优化建议」，不是直接改写后的完整简历。

【建议内容】
1. 整体匹配度评价：简历与岗位的匹配点、明显差距
2. 逐段优化建议：教育背景、专业技能、工作经历、项目经历各自怎么改
3. 经历改写示例：挑 1-2 段经历，给出 STAR 方法论改写的前后对比
4. 关键词补充：JD 里缺失的关键词，以及如何自然融入
5. 量化建议：哪些地方可以补充数字、百分比、规模

【要求】
- 只能基于简历已有内容给建议，绝不编造经历
- 每条建议要具体、可执行，说清楚「为什么改」和「怎么改」
- 用 Markdown 输出，结构清晰、层次分明
"""
        stream = await self.client.chat.completions.create(
            model=self._get_model(is_premium),
            messages=[{"role": "system", "content": system_message}],
            stream=True,
            temperature=0.6,
            max_tokens=4096,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content


llm_service = LLMService()
