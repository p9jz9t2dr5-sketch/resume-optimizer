"""Company seed data + idempotent seeding helper.

Single source of truth for the companies table. Used by both the app lifespan
(auto-seed on startup) and `python -m scripts.seed_companies`.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.models.company import Company

COMPANIES = [
    # Internet Giants
    {"name": "阿里巴巴", "official_site": "https://www.alibaba.com", "industry": "互联网/电商", "common_positions": ["Java开发工程师", "前端开发工程师", "算法工程师", "产品经理", "数据分析师"], "description": "全球领先的电子商务和科技公司"},
    {"name": "腾讯", "official_site": "https://www.tencent.com", "industry": "互联网/社交", "common_positions": ["后端开发工程师", "游戏开发工程师", "AI研究员", "产品经理", "安全工程师"], "description": "中国领先的互联网增值服务提供商"},
    {"name": "字节跳动", "official_site": "https://www.bytedance.com", "industry": "互联网/内容", "common_positions": ["推荐算法工程师", "后端开发工程师", "前端开发工程师", "大数据工程师", "客户端开发工程师"], "description": "全球领先的信息与内容平台公司"},
    {"name": "百度", "official_site": "https://www.baidu.com", "industry": "互联网/AI", "common_positions": ["AI算法工程师", "自动驾驶工程师", "后端开发工程师", "机器学习工程师", "NLP工程师"], "description": "全球领先的AI公司，中文搜索引擎"},
    {"name": "美团", "official_site": "https://www.meituan.com", "industry": "互联网/生活服务", "common_positions": ["Java开发工程师", "数据开发工程师", "算法工程师", "前端开发工程师", "测试开发工程师"], "description": "中国领先的生活服务电子商务平台"},
    {"name": "京东", "official_site": "https://www.jd.com", "industry": "电商/物流", "common_positions": ["Java开发工程师", "供应链算法工程师", "前端开发工程师", "运维工程师", "产品经理"], "description": "中国领先的技术驱动型电商和零售基础设施服务商"},
    {"name": "拼多多", "official_site": "https://www.pinduoduo.com", "industry": "电商", "common_positions": ["后端开发工程师", "算法工程师", "前端开发工程师", "数据科学家", "安全工程师"], "description": "中国领先的新电商平台"},
    {"name": "网易", "official_site": "https://www.netease.com", "industry": "互联网/游戏", "common_positions": ["游戏开发工程师", "后端开发工程师", "AI工程师", "前端开发工程师", "产品经理"], "description": "中国领先的互联网技术公司"},
    {"name": "快手", "official_site": "https://www.kuaishou.com", "industry": "互联网/短视频", "common_positions": ["推荐算法工程师", "音视频开发工程师", "后端开发工程师", "客户端开发工程师", "AI研究员"], "description": "领先的短视频和直播平台"},
    {"name": "小红书", "official_site": "https://www.xiaohongshu.com", "industry": "互联网/社区", "common_positions": ["后端开发工程师", "推荐算法工程师", "前端开发工程师", "数据分析师", "社区产品经理"], "description": "中国领先的生活方式分享平台"},
    {"name": "哔哩哔哩", "official_site": "https://www.bilibili.com", "industry": "互联网/视频", "common_positions": ["后端开发工程师", "前端开发工程师", "推荐算法工程师", "iOS/Android开发", "音视频开发工程师"], "description": "中国年轻世代高度聚集的文化社区和视频平台"},
    {"name": "滴滴", "official_site": "https://www.didiglobal.com", "industry": "出行/交通", "common_positions": ["算法工程师", "后端开发工程师", "大数据工程师", "安全工程师", "地图工程师"], "description": "全球领先的移动出行平台"},
    {"name": "小米", "official_site": "https://www.mi.com", "industry": "智能硬件/IoT", "common_positions": ["嵌入式开发工程师", "Android开发工程师", "AI工程师", "产品经理", "硬件工程师"], "description": "全球领先的消费电子和智能制造公司"},
    {"name": "华为", "official_site": "https://www.huawei.com", "industry": "通信/IT", "common_positions": ["通信算法工程师", "嵌入式软件工程师", "AI工程师", "操作系统开发工程师", "云计算工程师"], "description": "全球领先的ICT基础设施和智能终端提供商"},
    {"name": "蚂蚁集团", "official_site": "https://www.antgroup.com", "industry": "金融科技", "common_positions": ["Java开发工程师", "算法工程师", "安全工程师", "区块链工程师", "数据科学家"], "description": "全球领先的金融科技开放平台"},
    {"name": "SHEIN", "official_site": "https://www.shein.com", "industry": "跨境电商", "common_positions": ["后端开发工程师", "前端开发工程师", "供应链算法工程师", "数据工程师", "推荐系统工程师"], "description": "全球领先的时尚和 lifestyle 在线零售商"},
    {"name": "携程", "official_site": "https://www.ctrip.com", "industry": "在线旅游", "common_positions": ["Java开发工程师", "搜索算法工程师", "前端开发工程师", "大数据工程师", "产品经理"], "description": "中国领先的在线旅行服务公司"},
    {"name": "BOSS直聘", "official_site": "https://www.zhipin.com", "industry": "在线招聘", "common_positions": ["Java开发工程师", "推荐算法工程师", "NLP工程师", "前端开发工程师", "数据仓库工程师"], "description": "中国领先的在线招聘平台"},

    # Foreign Tech Giants
    {"name": "Google", "official_site": "https://www.google.com", "industry": "互联网/AI", "common_positions": ["Software Engineer", "ML Engineer", "Product Manager", "Data Scientist", "Site Reliability Engineer"], "description": "全球领先的科技公司，专注于搜索、广告、云计算和AI"},
    {"name": "Microsoft", "official_site": "https://www.microsoft.com", "industry": "软件/云服务", "common_positions": ["Software Engineer", "Cloud Solution Architect", "Data Scientist", "Product Manager", "Security Engineer"], "description": "全球最大的软件公司，Azure云服务和Office套件"},
    {"name": "Apple", "official_site": "https://www.apple.com", "industry": "消费电子/软件", "common_positions": ["Software Engineer", "Hardware Engineer", "ML Engineer", "iOS Developer", "Design Engineer"], "description": "全球领先的消费电子公司"},
    {"name": "Amazon", "official_site": "https://www.amazon.com", "industry": "电商/云计算", "common_positions": ["Software Development Engineer", "Solutions Architect", "Data Engineer", "Product Manager", "Applied Scientist"], "description": "全球最大电商和AWS云计算服务商"},
    {"name": "Meta", "official_site": "https://www.meta.com", "industry": "社交/VR", "common_positions": ["Software Engineer", "Research Scientist", "ML Engineer", "Product Designer", "Systems Engineer"], "description": "全球领先的社交媒体和元宇宙技术公司"},
    {"name": "NVIDIA", "official_site": "https://www.nvidia.com", "industry": "GPU/AI芯片", "common_positions": ["CUDA工程师", "AI研究科学家", "GPU架构工程师", "深度学习工程师", "自动驾驶工程师"], "description": "全球领先的GPU和AI计算公司"},
    {"name": "OpenAI", "official_site": "https://www.openai.com", "industry": "AI研究", "common_positions": ["Research Scientist", "ML Engineer", "Software Engineer", "Safety Researcher", "Infrastructure Engineer"], "description": "领先的人工智能研究公司，ChatGPT的创造者"},
    {"name": "Tesla", "official_site": "https://www.tesla.com", "industry": "电动汽车/能源", "common_positions": ["Software Engineer", "Autopilot Engineer", "嵌入式工程师", "数据工程师", "制造工程师"], "description": "领先的电动汽车和清洁能源公司"},
    {"name": "Netflix", "official_site": "https://www.netflix.com", "industry": "流媒体", "common_positions": ["Senior Software Engineer", "Data Engineer", "ML Engineer", "Security Engineer", "UI Engineer"], "description": "全球领先的流媒体娱乐服务"},
    {"name": "Airbnb", "official_site": "https://www.airbnb.com", "industry": "共享经济/旅游", "common_positions": ["Software Engineer", "Data Scientist", "ML Engineer", "Product Manager", "Design Technologist"], "description": "全球领先的民宿预订平台"},
    {"name": "Stripe", "official_site": "https://www.stripe.com", "industry": "金融科技", "common_positions": ["Software Engineer", "Infrastructure Engineer", "Data Engineer", "Security Engineer", "API Designer"], "description": "全球领先的在线支付基础设施公司"},
    {"name": "Databricks", "official_site": "https://www.databricks.com", "industry": "大数据/AI", "common_positions": ["Software Engineer", "Data Scientist", "Solutions Architect", "ML Engineer", "Platform Engineer"], "description": "领先的数据和AI平台公司"},
    {"name": "Snowflake", "official_site": "https://www.snowflake.com", "industry": "数据云", "common_positions": ["Software Engineer", "Cloud Engineer", "Data Engineer", "Solutions Architect", "Database Engineer"], "description": "领先的云数据平台公司"},

    # Chinese Tech
    {"name": "商汤科技", "official_site": "https://www.sensetime.com", "industry": "AI/计算机视觉", "common_positions": ["计算机视觉算法工程师", "深度学习工程师", "C++开发工程师", "AI产品经理", "系统架构师"], "description": "全球领先的AI软件公司"},
    {"name": "旷视科技", "official_site": "https://www.megvii.com", "industry": "AI/物联网", "common_positions": ["算法研究员", "后端开发工程师", "嵌入式AI工程师", "计算机视觉工程师", "产品经理"], "description": "领先的AIoT产品和解决方案公司"},
    {"name": "寒武纪", "official_site": "https://www.cambricon.com", "industry": "AI芯片", "common_positions": ["芯片设计工程师", "AI框架开发工程师", "编译器工程师", "深度学习算法工程师", "驱动开发工程师"], "description": "中国领先的AI芯片设计公司"},
    {"name": "地平线", "official_site": "https://www.horizon.ai", "industry": "自动驾驶/AI芯片", "common_positions": ["感知算法工程师", "自动驾驶系统工程师", "嵌入式软件工程师", "SLAM算法工程师", "芯片验证工程师"], "description": "领先的自动驾驶和AI芯片公司"},
    {"name": "大疆", "official_site": "https://www.dji.com", "industry": "无人机/机器人", "common_positions": ["嵌入式软件工程师", "控制算法工程师", "计算机视觉工程师", "机械工程师", "硬件工程师"], "description": "全球领先的无人机和摄像稳定系统公司"},
    {"name": "蔚来", "official_site": "https://www.nio.com", "industry": "智能电动汽车", "common_positions": ["自动驾驶工程师", "车载软件工程师", "电池算法工程师", "后端开发工程师", "嵌入式工程师"], "description": "中国领先的高端智能电动汽车公司"},
    {"name": "比亚迪", "official_site": "https://www.byd.com", "industry": "新能源汽车/电子", "common_positions": ["电池工程师", "电控软件工程师", "嵌入式工程师", "AI算法工程师", "硬件工程师"], "description": "全球领先的新能源汽车和电池制造商"},
    {"name": "科大讯飞", "official_site": "https://www.iflytek.com", "industry": "语音AI", "common_positions": ["语音算法工程师", "NLP工程师", "后端开发工程师", "AI产品经理", "深度学习研究员"], "description": "中国领先的智能语音和AI公司"},
    {"name": "微众银行", "official_site": "https://www.webank.com", "industry": "金融科技", "common_positions": ["区块链工程师", "Java开发工程师", "风控算法工程师", "大数据工程师", "安全架构师"], "description": "中国首家互联网银行，全球领先的数字银行"},
    {"name": "米哈游", "official_site": "https://www.mihoyo.com", "industry": "游戏", "common_positions": ["游戏引擎开发工程师", "图形学工程师", "渲染工程师", "后端开发工程师", "游戏AI工程师"], "description": "全球领先的互动娱乐公司"},

    # Startups & Unicorns
    {"name": "Notion", "official_site": "https://www.notion.so", "industry": "SaaS/协作工具", "common_positions": ["Full Stack Engineer", "Product Designer", "ML Engineer", "Infrastructure Engineer", "Developer Advocate"], "description": "领先的一体化工作空间和笔记平台"},
    {"name": "Figma", "official_site": "https://www.figma.com", "industry": "设计工具/SaaS", "common_positions": ["Software Engineer", "Graphics Engineer", "Product Designer", "Platform Engineer", "Full Stack Engineer"], "description": "领先的协作设计平台"},
    {"name": "Vercel", "official_site": "https://www.vercel.com", "industry": "云计算/前端平台", "common_positions": ["Software Engineer", "Edge/Infra Engineer", "DevOps Engineer", "Developer Advocate", "Systems Engineer"], "description": "领先的前端云平台，Next.js的创造者"},
    {"name": "Linear", "official_site": "https://www.linear.app", "industry": "SaaS/项目管理", "common_positions": ["Software Engineer", "Full Stack Engineer", "Product Designer", "Infrastructure Engineer", "Developer Experience Engineer"], "description": "新一代项目管理工具"},
    {"name": "Cursor", "official_site": "https://www.cursor.com", "industry": "AI/开发工具", "common_positions": ["Software Engineer", "ML Engineer", "Systems Engineer", "Full Stack Engineer", "AI Researcher"], "description": "AI驱动的代码编辑器"},
    {"name": "DeepSeek", "official_site": "https://www.deepseek.com", "industry": "AI/大模型", "common_positions": ["AI研究科学家", "ML系统工程师", "推理优化工程师", "训练基础设施工程师", "NLP研究员"], "description": "中国领先的AI大模型公司"},
    {"name": "智谱AI", "official_site": "https://www.zhipuai.cn", "industry": "AI/大模型", "common_positions": ["AI研究员", "NLP算法工程师", "大模型训练工程师", "推理加速工程师", "AI产品经理"], "description": "中国领先的认知智能公司"},
    {"name": "月之暗面", "official_site": "https://www.moonshot.cn", "industry": "AI/大模型", "common_positions": ["大模型算法工程师", "系统工程师", "NLP研究员", "安全研究员", "数据工程师"], "description": "中国领先的AI大模型创业公司"},
    {"name": "Minimax", "official_site": "https://www.minimax.io", "industry": "AI/多模态", "common_positions": ["多模态算法工程师", "系统工程师", "前端工程师", "后端工程师", "语音合成工程师"], "description": "领先的多模态AI公司"},
    {"name": "Cohere", "official_site": "https://www.cohere.com", "industry": "AI/企业大模型", "common_positions": ["ML Research Scientist", "Software Engineer", "NLP Engineer", "Solutions Engineer", "MLOps Engineer"], "description": "企业级AI平台公司"},
]


async def seed_companies(session_factory: async_sessionmaker) -> int:
    """Insert companies if the table is empty. Returns number inserted."""
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Company))
        if count and count > 0:
            return 0

        for company_data in COMPANIES:
            session.add(Company(**company_data))
        await session.commit()
        return len(COMPANIES)
