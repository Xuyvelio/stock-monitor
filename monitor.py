import os
import json
import time
import requests
from datetime import datetime, date
import re
import subprocess
import tempfile

SERVERCHAN_KEYS = [k.strip() for k in os.environ.get("SERVERCHAN_KEY", "").split(",") if k.strip()]
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
STATE_FILE = "processed_ids.json"
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "thresholds": {
        "min_score": 6,
        "instant_score": 9,
        "summary_score": 6,
        "large_cap_penalty": 3,
        "preferred_track_bonus": 1,
    },
    "ignore": {"codes": [], "names": [], "keywords": []},
    "preferred_tracks": [],
    "summary": {"enabled": True, "send_hours": [18, 24]},
    "logging": {"enabled": True, "file": "daily_log.jsonl"},
    "explosive": {
        "instant_only_explosive": True,
        "min_score": 9,
        "summary_min_score": 7
    },
    "keywords": [
        "筹划重大事项", "申请停牌", "重大事项停牌",
        "重大资产重组", "资产重组", "重组",
        "借壳", "吸收合并", "要约收购",
        "收购", "并购", "股权收购",
        "控制权变更", "实际控制人",
        "股份转让", "股权转让",
        "国资入主", "国有资本", "国有企业",
        "摘帽", "取消退市风险警示",
        "重大合同", "重大投资", "增资",
        "定向增发", "非公开发行",
        "分拆上市", "股票回购",
        "业绩预增", "业绩大幅增长",
    ],
    "blacklist": [
        "进展公告", "进展情况",
        "修订说明", "修订报告",
        "补充公告",
        "回复函", "问询函", "回复意见",
        "核查意见", "核查报告",
        "注册稿",
        "独立董事意见", "独立董事关于",
        "草案摘要", "报告书摘要",
        "说明书（",
        "第三次", "第四次", "第五次",
    ],
    "procedural_keywords": [
        "审议通过", "董事会", "监事会", "股东大会",
        "提示性公告", "风险提示", "进展",
        "完成工商变更", "签署补充协议", "补充说明",
        "交易所关注", "问询回复",
    ],
    "uncertainty_keywords": [
        "存在不确定性", "尚需", "尚存在", "最终以",
        "能否", "审批", "审议", "备案", "有待", "视情况",
    ],
    "negative_keywords": [
        "终止", "撤回", "失败", "取消", "无法", "未通过", "不再推进",
    ],
    "explosive_event_keywords": [
        "筹划重大事项", "申请停牌", "重大事项停牌",
        "要约收购",
        "重大资产重组", "借壳", "吸收合并",
        "控制权变更", "实际控制人变更",
        "国资入主", "国有资本入主",
        "摘帽", "取消退市风险警示"
    ],
    "hard_filter_keywords": [
        "董事会决议", "监事会决议", "股东大会决议",
        "提示性公告", "风险提示",
        "进展公告", "进展情况",
        "补充公告", "补充说明", "补充更正",
        "回复函", "问询函", "回复意见", "问询回复",
        "实施完成", "完成工商变更",
        "继续停牌"
    ],
    "hottrack_keywords": {
        "AI人工智能": ["人工智能", "大模型", "AI", "算力", "智算", "大数据", "云计算"],
        "半导体芯片": ["半导体", "芯片", "集成电路", "晶圆", "光刻", "EDA", "封测"],
        "机器人": ["机器人", "人形机器人", "具身智能", "智能制造"],
        "低空经济": ["低空", "无人机", "eVTOL", "飞行汽车", "通用航空"],
        "新能源": ["新能源", "锂电池", "储能", "光伏", "风电", "氢能", "固态电池"],
        "军工": ["军工", "国防", "航天", "航空", "兵器", "舰船", "卫星", "导弹"],
        "创新药": ["创新药", "生物医药", "基因", "细胞治疗", "新药", "CXO"],
        "量子/卫星": ["量子", "卫星互联网", "商业航天", "北斗"],
    },
    "large_caps": [
        "中国神华", "中国电建", "中国建筑", "中国中铁", "中国铁建",
        "工商银行", "建设银行", "农业银行", "中国银行", "招商银行",
        "中国石油", "中国石化", "中国海油", "中国移动", "中国联通",
        "中国电信", "中国人寿", "中国平安", "贵州茅台", "中国中车",
        "中国煤炭", "中国交建", "中国核电", "中国广核", "华能国际",
    ],
}


def deep_merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            user_config = json.load(f)
        return deep_merge(DEFAULT_CONFIG, user_config)
    except FileNotFoundError:
        return DEFAULT_CONFIG
    except Exception as e:
        print(f"[配置加载失败] 使用默认配置: {e}")
        return DEFAULT_CONFIG


CONFIG = load_config()
THRESHOLDS = CONFIG["thresholds"]
KEYWORDS = CONFIG["keywords"]
BLACKLIST = CONFIG["blacklist"]
EXPLOSIVE_CONFIG = CONFIG.get("explosive", {})
EXPLOSIVE_EVENT_KEYWORDS = CONFIG.get("explosive_event_keywords", [])
HARD_FILTER_KEYWORDS = CONFIG.get("hard_filter_keywords", [])
PROCEDURAL_KEYWORDS = CONFIG.get("procedural_keywords", [])
UNCERTAINTY_KEYWORDS = CONFIG.get("uncertainty_keywords", [])
NEGATIVE_KEYWORDS = CONFIG.get("negative_keywords", [])
HOTTRACK_KEYWORDS = CONFIG["hottrack_keywords"]
LARGE_CAPS = CONFIG["large_caps"]
IGNORE_CODES = set(CONFIG["ignore"].get("codes", []))
IGNORE_NAMES = set(CONFIG["ignore"].get("names", []))
IGNORE_KEYWORDS = CONFIG["ignore"].get("keywords", [])
PREFERRED_TRACKS = set(CONFIG.get("preferred_tracks", []))
SUMMARY_CONFIG = CONFIG.get("summary", {})
LOGGING_CONFIG = CONFIG.get("logging", {})

# API key: 环境变量优先，config.json 兜底
if not DEEPSEEK_API_KEY:
    DEEPSEEK_API_KEY = CONFIG.get("deepseek_api_key", "")


# ─────────────────────────────────────────
# 动态抓取页数（根据时间段）
# ─────────────────────────────────────────
def get_pages():
    hour = datetime.now().hour
    if 15 <= hour < 20:
        return 6
    elif 9 <= hour < 15:
        return 2
    else:
        return 3


# ─────────────────────────────────────────
# 抓取公告
# ─────────────────────────────────────────
def fetch_announcements():
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    all_items = []
    pages = get_pages()
    for page in range(1, pages + 1):
        params = {
            "sr": -1,
            "page_size": 50,
            "page_index": page,
            "ann_type": "A",
            "client_source": "web",
            "f_node": 0,
            "s_node": 0,
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            items = r.json().get("data", {}).get("list", [])
            if not items:
                break
            all_items.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"[抓取第{page}页失败] {e}")
            break

    announcements = []
    for item in all_items:
        code = item.get("codes", [{}])[0].get("stock_code", "") if item.get("codes") else ""
        announcements.append({
            "id": str(item.get("art_code", "")),
            "stock_code": code,
            "stock_name": item.get("codes", [{}])[0].get("short_name", "") if item.get("codes") else "",
            "title": item.get("title", ""),
            "time": item.get("notice_date", ""),
            "url": f"https://data.eastmoney.com/notices/detail/{code}/{item.get('art_code', '')}.html",
        })
    print(f"共抓取 {len(announcements)} 条（{pages}页）")
    return announcements


# ─────────────────────────────────────────
# 过滤函数
# ─────────────────────────────────────────
def is_bond(code):
    return code.startswith("11") or code.startswith("12")


def is_noise(title):
    return any(kw in title for kw in BLACKLIST)


def is_hard_filtered(title):
    return any(kw in title for kw in HARD_FILTER_KEYWORDS)


def is_major(title):
    return any(kw in title for kw in KEYWORDS)


def is_explosive_event(title):
    return any(kw in title for kw in EXPLOSIVE_EVENT_KEYWORDS)



def is_ignored(code, name, title):
    if code in IGNORE_CODES or name in IGNORE_NAMES:
        return True
    return any(kw in title for kw in IGNORE_KEYWORDS)


def get_stock_type(code, name):
    is_st = "ST" in name
    if code.startswith("300") or code.startswith("301"):
        return "创业板", "20%涨停", True, is_st
    elif code.startswith("688") or code.startswith("689"):
        return "科创板", "20%涨停", True, is_st
    elif code.startswith("8") or code.startswith("43"):
        return "北交所", "30%涨停", True, is_st
    else:
        limit = "5%涨停" if is_st else "10%涨停"
        return "主板", limit, False, is_st


def is_large_cap(name):
    return any(lc in name for lc in LARGE_CAPS)


def get_hottrack(ann):
    text = ann["stock_name"] + ann["title"]
    return [t for t, kws in HOTTRACK_KEYWORDS.items() if any(kw in text for kw in kws)]


def hit_keywords(text, keywords):
    return [kw for kw in keywords if kw in text]


# ─────────────────────────────────────────
# 行情数据（腾讯接口）
# ─────────────────────────────────────────
_market_cache = {}

def get_market_data(code):
    """获取股票实时行情数据（同轮次内缓存）"""
    if code in _market_cache:
        return _market_cache[code]
    result = _fetch_market_data(code)
    _market_cache[code] = result
    return result

def _fetch_market_data(code):
    # 腾讯行情接口: 0=深圳 1=上海
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    try:
        r = requests.get(
            f"https://qt.gtimg.cn/q={symbol}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        text = r.text
        if "=" not in text or "~" not in text:
            return None

        fields = text.split("~")
        if len(fields) < 50:
            return None

        try:
            price = float(fields[3]) if fields[3] else 0
            prev_close = float(fields[4]) if fields[4] else 0
            change_pct = float(fields[32]) if fields[32] else 0
            turnover = float(fields[38]) if fields[38] else 0
            high = float(fields[33]) if fields[33] else 0
            low = float(fields[34]) if fields[34] else 0
        except (ValueError, IndexError):
            return None

        # 判断是否涨停/跌停
        is_limit_up = False
        is_limit_down = False
        if prev_close > 0:
            # 根据板块确定涨跌停幅度
            if code.startswith("300") or code.startswith("301") or code.startswith("688") or code.startswith("689"):
                limit_pct = 20
            elif code.startswith("8") or code.startswith("43"):
                limit_pct = 30
            elif "ST" in fields[1]:
                limit_pct = 5
            else:
                limit_pct = 10

            limit_up_price = round(prev_close * (1 + limit_pct / 100), 2)
            limit_down_price = round(prev_close * (1 - limit_pct / 100), 2)

            if price >= limit_up_price:
                is_limit_up = True
            if price <= limit_down_price:
                is_limit_down = True

        return {
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "turnover": turnover,
            "high": high,
            "low": low,
            "is_limit_up": is_limit_up,
            "is_limit_down": is_limit_down,
            "volume": int(fields[6]) if fields[6] else 0,
            "amount": float(fields[37]) if fields[37] else 0,  # 万元
        }
    except Exception as e:
        print(f"[行情获取失败] {code}: {e}")
        return None


# ─────────────────────────────────────────
# AI 评分（DeepSeek）
# ─────────────────────────────────────────
_ai_call_count = 0
AI_MAX_CALLS_PER_RUN = 5

AI_PROMPT = """你是A股公告分析专家。根据公告标题和正文，判断该公告对股价的影响。

评分规则：
- 9~10分：重大利好，大概率涨停或连续涨停（停牌重组、摘帽、要约收购等）
- 7~8分：明确利好，有较高概率大涨（定增引入战投、业绩超预期、重大合同等）
- 5~6分：中性偏正，可能小幅上涨（回购、增持、中标等）
- 3~4分：中性或不确定（进展公告、审议结果等）
- 1~2分：偏负面（减持、质押、诉讼等）
- 0分：明确利空（终止重组、业绩暴雷、立案调查等）

注意以下陷阱：
- 标题写"收购"但正文可能是"收购终止"
- 标题写"重大事项"但正文可能是"终止筹划"
- "审议通过"只是流程推进，不代表落地
- "存在不确定性"意味着结果未定

请用JSON格式返回，包含以下字段：
- score: 0-10的整数
- sentiment: "利好"/"中性"/"利空"
- confidence: "高"/"中"/"低"
- reason: 一句话分析理由（30字以内）"""


def ai_score(title, content=""):
    """用 DeepSeek 对公告做智能评分"""
    global _ai_call_count
    if not DEEPSEEK_API_KEY:
        return None
    if _ai_call_count >= AI_MAX_CALLS_PER_RUN:
        print(f"[AI评分] 已达本轮上限({AI_MAX_CALLS_PER_RUN}次)，跳过")
        return None
    _ai_call_count += 1

    user_msg = f"公告标题：{title}"
    if content:
        # 限制正文长度，避免token过多
        user_msg += f"\n\n公告正文（前1500字）：\n{content[:1500]}"

    try:
        r = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": AI_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=15,
        )
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()

        # 解析JSON
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "score": int(result.get("score", 5)),
                "sentiment": result.get("sentiment", "中性"),
                "confidence": result.get("confidence", "低"),
                "reason": result.get("reason", ""),
            }
    except Exception as e:
        print(f"[AI评分失败] {e}")
    return None


# ─────────────────────────────────────────
# 公告正文抓取（巨潮PDF）
# ─────────────────────────────────────────
def fetch_notice_content(code, name, title=""):
    """从巨潮资讯网下载PDF并提取正文"""
    try:
        # 1. 搜索公告，获取PDF链接（用股票代码搜索）
        search_url = "https://www.cninfo.com.cn/new/fulltextSearch/full"
        params = {
            "searchkey": code,
            "sdate": "", "edate": "",
            "isfulltext": "false",
            "sortName": "nothing",
            "sortType": "desc",
            "pageNum": 1,
            "pageSize": 5,
        }
        r = requests.get(
            search_url, params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = r.json()
        announcements = data.get("announcements") or []

        # 找到匹配的公告（精确匹配：代码+标题关键词）
        pdf_url = None
        title_keywords = [title[:8]] if title else []
        for item in announcements:
            if item.get("secCode") == code and item.get("adjunctUrl"):
                item_title = re.sub(r"<[^>]+>", "", item.get("announcementTitle", ""))
                # 优先匹配标题相似的
                if any(kw in item_title for kw in title_keywords[:1]):
                    pdf_url = f"https://static.cninfo.com.cn/{item['adjunctUrl']}"
                    break
        # 如果没找到精确匹配，用第一条
        if not pdf_url:
            for item in announcements:
                if item.get("secCode") == code and item.get("adjunctUrl"):
                    pdf_url = f"https://static.cninfo.com.cn/{item['adjunctUrl']}"
                    break

        if not pdf_url:
            return ""

        # 2. 用curl下载PDF（避免Python SSL问题）
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name

        result = subprocess.run(
            ["curl", "-sk", pdf_url, "-o", tmp_path],
            timeout=15,
            capture_output=True,
        )
        if result.returncode != 0:
            os.unlink(tmp_path)
            return ""

        # 3. 提取文字
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(tmp_path)
            text = ""
            for page in reader.pages[:3]:  # 只取前3页
                t = page.extract_text()
                if t:
                    text += t
            return text[:3000]  # 限制长度
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        print(f"[正文获取失败] {code}: {e}")
        return ""


# ─────────────────────────────────────────
# 评分与分析
# ─────────────────────────────────────────
def analyze(ann):
    title = ann["title"]
    name = ann["stock_name"]
    code = ann["stock_code"]
    board, limit, need_perm, is_st = get_stock_type(code, name)
    large_cap = is_large_cap(name)
    explosive_event = is_explosive_event(title)
    procedural_hits = hit_keywords(title, PROCEDURAL_KEYWORDS)
    uncertainty_hits = hit_keywords(title, UNCERTAINTY_KEYWORDS)
    negative_hits = hit_keywords(title, NEGATIVE_KEYWORDS)

    score = 6
    base_score = 6
    bonuses = []
    penalties = []

    if any(kw in title for kw in ["筹划重大事项", "申请停牌", "重大事项停牌"]):
        score, base_score, event_type = 10, 10, "筹划重大事项停牌"
        reason = "信息完全空白，市场自由想象，复牌首日历史上大概率一字涨停"
    elif "要约收购" in title:
        score, base_score, event_type = 10, 10, "要约收购"
        reason = "收购方溢价收购，目标价锁定，资金疯狂追入，连板概率极高"
    elif any(kw in title for kw in ["摘帽", "取消退市风险警示"]):
        score, base_score, event_type = 10, 10, "ST摘帽"
        reason = "从5%变10%涨停，利好明确，历史上摘帽首日几乎必连板"
    elif any(kw in title for kw in ["重大资产重组", "借壳", "吸收合并"]):
        score, base_score, event_type = 9, 9, "重大资产重组/借壳"
        reason = "资产注入或借壳，估值重构，市场高度关注，连续涨停概率大"
    elif any(kw in title for kw in ["国资入主", "国有资本", "国有企业"]):
        score, base_score, event_type = 9, 9, "国资入主"
        reason = "国有资本接盘，信用背书强，市场认可度高，历史上多为连板起点"
    elif any(kw in title for kw in ["控制权变更", "股份转让", "股权转让", "实际控制人"]):
        score, base_score, event_type = 8, 8, "控制权/股权转让"
        reason = "控制权易主，公司发展方向可能根本性改变，资本市场高度敏感"
    elif any(kw in title for kw in ["收购", "并购", "股权收购"]):
        score, base_score, event_type = 8, 8, "收购/并购"
        reason = "收购并购事件，可能带来估值重塑和业务协同"
    elif "分拆上市" in title:
        score, base_score, event_type = 8, 8, "分拆上市"
        reason = "子公司独立上市，释放隐藏价值，母公司估值重塑"
    elif any(kw in title for kw in ["重大合同", "重大投资"]):
        score, base_score, event_type = 7, 7, "重大合同/投资"
        reason = "重大合同落地，业绩有望大幅提升"
    elif any(kw in title for kw in ["业绩预增", "业绩大幅增长"]):
        score, base_score, event_type = 7, 7, "业绩预增"
        reason = "业绩超预期增长，基本面改善明显"
    elif any(kw in title for kw in ["定向增发", "非公开发行"]):
        score, base_score, event_type = 7, 7, "定向增发"
        reason = "定向增发引入资金或战略投资者"
    elif "股票回购" in title:
        score, base_score, event_type = 7, 7, "股票回购"
        reason = "大额回购彰显信心，护盘意图明显"
    else:
        # 未匹配到已知事件类型（理论上不会走到这里，主循环已过滤）
        event_type = "其他公告"
        reason = "未命中已知事件类型，需人工判断"

    if explosive_event:
        bonuses.append("爆发型事件")

    if is_st and score < 10:
        score = min(10, score + 1)
        bonuses.append("ST股+1")
        reason += "。ST股体量小，资金容易拉升"

    tracks = get_hottrack(ann)
    if tracks:
        bonus = 1 if len(tracks) == 1 else 2
        score = min(10, score + bonus)
        bonuses.append(f"主线赛道+{bonus}（{'、'.join(tracks)}）")
        reason += f"。主线赛道（{'、'.join(tracks)}）+{bonus}分"

    preferred_tracks = [track for track in tracks if track in PREFERRED_TRACKS]
    if preferred_tracks:
        bonus = THRESHOLDS.get("preferred_track_bonus", 1)
        score = min(10, score + bonus)
        bonuses.append(f"偏好赛道+{bonus}（{'、'.join(preferred_tracks)}）")
        reason += f"。命中个人偏好赛道（{'、'.join(preferred_tracks)}）+{bonus}分"

    if large_cap:
        penalty = THRESHOLDS.get("large_cap_penalty", 3)
        score = max(3, score - penalty)
        penalties.append(f"大盘股-{penalty}")
        reason += "。大盘央企体量大，连板概率极低"

    if procedural_hits:
        penalty = THRESHOLDS.get("procedural_penalty", 2)
        score = max(2, score - penalty)
        penalties.append(f"流程性公告-{penalty}（{'、'.join(procedural_hits[:3])}）")
        reason += f"。标题偏流程推进，落地强度一般，-{penalty}分"

    if uncertainty_hits:
        penalty = THRESHOLDS.get("uncertainty_penalty", 2)
        score = max(2, score - penalty)
        penalties.append(f"不确定性-{penalty}（{'、'.join(uncertainty_hits[:3])}）")
        reason += f"。存在审批或结果不确定性，-{penalty}分"

    if negative_hits:
        penalty = THRESHOLDS.get("negative_penalty", 5)
        score = max(2, score - penalty)
        event_type = "事项终止/利空"
        penalties.append(f"负面事件-{penalty}（{'、'.join(negative_hits[:3])}）")
        reason = "重大事项终止、撤回或推进失败，可能构成明显利空，注意风险"
        tracks = []
        preferred_tracks = []

    # 获取行情数据
    market = get_market_data(code)
    market_info = ""
    if market:
        market_info = f"现价{market['price']} 涨跌{market['change_pct']}% 换手{market['turnover']}%"
        # 已涨停 - 可能买不进了
        if market["is_limit_up"]:
            penalty = 2
            score = max(2, score - penalty)
            penalties.append(f"已涨停-{penalty}")
            reason += f"。该股已涨停（{market['price']}），可能封板买不进"
        # 已跌停 - 利空兑现
        elif market["is_limit_down"]:
            penalty = 3
            score = max(2, score - penalty)
            penalties.append(f"已跌停-{penalty}")
            reason += f"。该股已跌停（{market['price']}），利空可能已兑现"
        # 涨幅超过5% - 追高风险
        elif market["change_pct"] > 5:
            penalty = 1
            score = max(2, score - penalty)
            penalties.append(f"已涨{market['change_pct']:.1f}%-{penalty}")
            reason += f"。盘中已涨{market['change_pct']:.1f}%，追高有风险"
        # 换手率极高（>15%）- 筹码松动
        if market["turnover"] > 15:
            penalty = 1
            score = max(2, score - penalty)
            penalties.append(f"换手率{market['turnover']:.1f}%-{penalty}")
            reason += f"。换手率{market['turnover']:.1f}%，筹码松动"

    instant_threshold = EXPLOSIVE_CONFIG.get("min_score", THRESHOLDS.get("instant_score", 9))
    min_threshold = THRESHOLDS.get("min_score", 6)
    summary_threshold = EXPLOSIVE_CONFIG.get("summary_min_score", THRESHOLDS.get("summary_score", min_threshold))
    instant_only_explosive = EXPLOSIVE_CONFIG.get("instant_only_explosive", True)
    # 正文校验：对高分公告抓取PDF，检查正文是否有负面内容
    content_verified = False
    content_text = ""
    all_negative = []
    if score >= 7 and not negative_hits:
        content_text = fetch_notice_content(code, name, title)
        if content_text:
            content_verified = True
            # 检查正文中的负面关键词
            content_negative = hit_keywords(content_text, NEGATIVE_KEYWORDS)
            # 额外检查正文特有的终止/失败模式
            content_terminate = [kw for kw in ["终止实施", "不再继续", "予以撤回", "未获通过", "审核不通过", "已过期"] if kw in content_text]
            all_negative = content_negative + content_terminate
            if all_negative:
                penalty = 4
                score = max(2, score - penalty)
                penalties.append(f"正文负面-{penalty}（{'、'.join(all_negative[:3])}）")
                reason += f"。正文发现负面信息（{'、'.join(all_negative[:2])}），标题与内容不符，-{penalty}分"
                event_type = "正文利空"
            # 检查正文中的不确定性
            content_uncertain = hit_keywords(content_text, ["尚需经", "能否获得", "最终结果", "存在重大不确定性"])
            if content_uncertain and not all_negative:
                penalty = 2
                score = max(2, score - penalty)
                penalties.append(f"正文不确定-{penalty}")
                reason += f"。正文存在不确定性表述，-{penalty}分"

    # AI 评分：对高分公告调用 DeepSeek 做智能分析
    ai_result = None
    if score >= 7 and DEEPSEEK_API_KEY and not all_negative:
        ai_result = ai_score(title, content_text)
        if ai_result:
            ai_s = ai_result["score"]
            # AI 和规则加权：规则60% + AI40%
            blended = round(score * 0.6 + ai_s * 0.4)
            # 只在AI认为明显更低时降分（防止AI误杀），AI认为更高时不加分
            if blended < score - 1:
                old_score = score
                score = max(2, blended)
                penalties.append(f"AI降分（{ai_result['reason'][:20]}）")
                reason += f"。AI分析：{ai_result['reason']}，综合评分从{old_score}调整为{score}"
            elif ai_s > score:
                # AI认为更高，小幅加分（最多+1）
                score = min(10, score + 1)
                bonuses.append(f"AI+1（{ai_result['reason'][:15]}）")

    explosive_ready = explosive_event and not procedural_hits and not uncertainty_hits and not negative_hits and not large_cap
    if instant_only_explosive:
        should_push = score >= instant_threshold and explosive_ready
    else:
        should_push = score >= instant_threshold and not negative_hits and not large_cap
    should_summary = score >= summary_threshold and not negative_hits

    if score == 10:
        level, burst, alert_tier = "🌋 核爆利好", "极高", "S"
    elif score >= 9:
        level, burst, alert_tier = "🔥 重大利好", "高", "S"
    elif score >= 7:
        level, burst, alert_tier = "⭐ 值得看", "中高", "A"
    elif score >= 6:
        level, burst, alert_tier = "📢 收盘看", "中", "B"
    else:
        level, burst, alert_tier = "⚠️ 谨慎关注", "低", "C"

    return {
        "is_positive": score >= min_threshold,
        "should_push": should_push,
        "should_summary": should_summary,
        "score": score,
        "base_score": base_score,
        "level": level,
        "burst": burst,
        "alert_tier": alert_tier,
        "event_type": event_type,
        "reason": reason,
        "tracks": tracks,
        "preferred_tracks": preferred_tracks,
        "board": board,
        "limit": limit,
        "need_perm": need_perm,
        "is_st": is_st,
        "large_cap": large_cap,
        "bonuses": bonuses,
        "penalties": penalties,
        "procedural_hits": procedural_hits,
        "uncertainty_hits": uncertainty_hits,
        "negative_hits": negative_hits,
        "explosive_event": explosive_event,
        "explosive_ready": explosive_ready,
        "market": market,
        "market_info": market_info,
        "content_verified": content_verified,
        "ai_result": ai_result,
    }


# ─────────────────────────────────────────
# 推送微信
# ─────────────────────────────────────────
def push_text(title, content):
    if not SERVERCHAN_KEYS:
        return False
    ok = False
    for key in SERVERCHAN_KEYS:
        try:
            r = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": content},
                timeout=10,
            )
            code = r.json().get("code")
            print(f"[推送] {title} → key:{key[:8]}... code:{code}")
            ok = True
        except Exception as e:
            print(f"[推送失败] key:{key[:8]}... {e}")
    return ok


def build_tags(analysis):
    tags = []
    if analysis.get("explosive_event"):
        tags.append("【爆发型】")
    if analysis["is_st"]:
        tags.append("【ST-5%涨停】")
    if analysis["need_perm"]:
        tags.append("【需开通权限】")
    if analysis["large_cap"]:
        tags.append("【大盘股-连板概率低】")
    if analysis["tracks"]:
        tags.append(f"【{'|'.join(analysis['tracks'])}】")
    if analysis.get("content_verified"):
        tags.append("【已校验正文】")
    return " ".join(tags)


def push_instant(ann, analysis):
    if not analysis["should_push"]:
        return False

    tier = analysis["alert_tier"]
    prefix = "🌋" if tier == "S" else "🔔"
    tag = "【立即看】" if tier == "S" else "【关注】"
    msg_title = f"{prefix} {tag}{ann['stock_name']}（{ann['stock_code']}）{analysis['event_type']}"

    score = analysis["score"]
    stars = "⭐" * min(score, 10)
    bonus_text = "、".join(analysis["bonuses"]) if analysis["bonuses"] else "—"
    penalty_text = "、".join(analysis["penalties"]) if analysis["penalties"] else "—"
    tag_str = build_tags(analysis)

    content = (
        f"## {ann['title']}\n\n"
        + (f"{tag_str}\n\n" if tag_str else "")
        + f"**提醒级别：** {analysis['alert_tier']} / {analysis['level']}\n"
        f"**时间：** {ann['time']}\n"
        f"**板块：** {analysis['board']} | 涨停幅度：{analysis['limit']}\n"
        + (f"**行情：** {analysis['market_info']}\n" if analysis.get('market_info') else "")
        + f"\n| 项目 | 内容 |\n|------|------|\n"
        f"| 事件类型 | {analysis['event_type']} |\n"
        f"| 最终评分 | {stars} {score}/10 |\n"
        f"| 基础分 | {analysis['base_score']} |\n"
        f"| 加分项 | {bonus_text} |\n"
        f"| 减分项 | {penalty_text} |\n"
        f"| 主线赛道 | {'、'.join(analysis['tracks']) if analysis['tracks'] else '—'} |\n"
        f"| 爆发概率 | {analysis['burst']} |\n"
        f"| 核心逻辑 | {analysis['reason']} |\n\n"
        f"⚠️ 仅供自用参考，不构成投资建议\n\n"
        f"🔗 [查看原文公告]({ann['url']})"
    )
    return push_text(msg_title, content)


def push_summary(candidates, state):
    if not SERVERCHAN_KEYS or not SUMMARY_CONFIG.get("enabled", True):
        return False

    now = datetime.now()
    current_hour = now.hour
    send_hours = sorted(SUMMARY_CONFIG.get("send_hours", [18, 24]))

    today = str(date.today())
    summary_state = state.get("summary", {})

    # 新的一天重置状态
    if summary_state.get("date") != today:
        summary_state = {"date": today, "sent_hours": [], "pushed_ids": []}

    sent_hours = summary_state.get("sent_hours", [])

    # 找到下一个还没推过、且当前时间已过的推送时间点
    target_hour = None
    for h in send_hours:
        # 24点特殊处理：hour=0表示午夜
        effective_h = h % 24
        if h == 24:
            # 午夜汇总：23:00之后或次日0:00都算
            if effective_h not in sent_hours and (current_hour >= 23 or current_hour == 0):
                target_hour = h
                break
        elif effective_h not in sent_hours and current_hour >= effective_h:
            target_hour = h
            break

    if target_hour is None:
        return False

    # 过滤掉已经推过的公告
    pushed_ids = set(summary_state.get("pushed_ids", []))
    summary_items = [
        (ann, result) for ann, result in candidates
        if result["should_summary"] and ann["id"] not in pushed_ids
    ]

    if not summary_items:
        state["summary"] = {
            "date": today,
            "sent_hours": sent_hours + [target_hour],
            "pushed_ids": list(pushed_ids)
        }
        return False

    summary_items.sort(key=lambda item: item[1]["score"], reverse=True)
    top_items = summary_items[:10]

    time_label = "盘后" if target_hour <= 18 else "晚间"
    lines = []
    for ann, result in top_items:
        flags = []
        if result["tracks"]:
            flags.append("/".join(result["tracks"]))
        flag_text = f"（{'；'.join(flags)}）" if flags else ""
        market_str = ""
        if result.get("market_info"):
            market_str = f" | {result['market_info']}"
        lines.append(
            f"- {ann['stock_name']}（{ann['stock_code']}） {result['score']}/10 {result['event_type']}{flag_text}{market_str}"
        )

    title = f"📒 {time_label}公告汇总 {today}"
    content = (
        f"## {time_label}重点公告汇总\n\n"
        f"- 新增候选：{len(summary_items)} 条\n"
        f"- 立即看级别：{sum(1 for _, r in summary_items if r['alert_tier'] == 'S')} 条\n\n"
        f"### Top 列表\n"
        + "\n".join(lines)
        + "\n\n⚠️ 仅供自用复盘参考，不构成投资建议"
    )

    ok = push_text(title, content)
    if ok:
        new_pushed_ids = list(pushed_ids | {ann["id"] for ann, _ in summary_items})
        state["summary"] = {
            "date": today,
            "sent_hours": sent_hours + [target_hour],
            "pushed_ids": new_pushed_ids[-500:]
        }
    return ok


# ─────────────────────────────────────────
# 状态管理
# ─────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
            state.setdefault("ids", [])
            state.setdefault("daily", {})
            state.setdefault("summary", {})
            return state
    except FileNotFoundError:
        return {"ids": [], "daily": {}, "summary": {}}
    except Exception as e:
        print(f"[状态加载失败] 重置状态: {e}")
        return {"ids": [], "daily": {}, "summary": {}}


def save_state(state):
    state["ids"] = list(state["ids"])[-2000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def append_log(record):
    if not LOGGING_CONFIG.get("enabled", False):
        return
    log_file = LOGGING_CONFIG.get("file", "daily_log.jsonl")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[日志写入失败] {e}")


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    global _ai_call_count, _market_cache
    _ai_call_count = 0
    _market_cache = {}
    print(f"\n{'=' * 50}")
    print(f"监控启动 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    state = load_state()
    processed_ids = set(state.get("ids", []))
    today = str(date.today())

    daily_best = state.get("daily", {})
    if daily_best.get("date") != today:
        daily_best = {"date": today, "stocks": {}}

    anns = fetch_announcements()
    candidates = []
    stats = {"seen": len(anns), "processed": 0, "ignored": 0, "noise": 0, "non_major": 0, "bond": 0}

    for ann in anns:
        ann_id = ann["id"]
        code = ann["stock_code"]
        name = ann["stock_name"]
        title = ann["title"]

        if ann_id in processed_ids:
            continue
        stats["processed"] += 1

        if is_bond(code):
            processed_ids.add(ann_id)
            stats["bond"] += 1
            continue
        if is_ignored(code, name, title):
            processed_ids.add(ann_id)
            stats["ignored"] += 1
            continue
        if is_hard_filtered(title):
            processed_ids.add(ann_id)
            stats["noise"] += 1
            continue
        if is_noise(title):
            processed_ids.add(ann_id)
            stats["noise"] += 1
            continue
        if not is_major(title):
            processed_ids.add(ann_id)
            stats["non_major"] += 1
            continue

        print(f"[命中] {ann['stock_name']}（{code}）- {title}")
        result = analyze(ann)
        print(f"  → {result['level']} {result['score']}/10 | {result['event_type']}")
        append_log({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "stock_code": code,
            "stock_name": name,
            "title": title,
            "announcement_id": ann_id,
            "score": result["score"],
            "event_type": result["event_type"],
            "should_push": result["should_push"],
            "should_summary": result["should_summary"],
            "bonuses": result["bonuses"],
            "penalties": result["penalties"],
            "tracks": result["tracks"],
            "url": ann["url"],
        })
        candidates.append((ann, result))
        processed_ids.add(ann_id)

    to_push = {}
    for ann, result in candidates:
        code = ann["stock_code"]
        score = result["score"]
        best_score = daily_best["stocks"].get(code, 0)
        if score > best_score and (result["should_push"] or result["should_summary"]):
            to_push[code] = (ann, result)
            daily_best["stocks"][code] = score

    pushed = 0
    instant_pushed = 0
    summary_candidates = []
    for code, (ann, result) in to_push.items():
        summary_candidates.append((ann, result))
        if result["should_push"]:
            if push_instant(ann, result):
                instant_pushed += 1
                pushed += 1
            time.sleep(0.5)

    if push_summary(summary_candidates, state):
        pushed += 1

    state["ids"] = list(processed_ids)
    state["daily"] = daily_best
    save_state(state)

    print(f"本轮完成：抓取 {stats['seen']} 条 | 新处理 {stats['processed']} 条 | 命中 {len(candidates)} 条")
    print(f"过滤统计：债券 {stats['bond']} | 忽略 {stats['ignored']} | 噪音 {stats['noise']} | 非目标 {stats['non_major']}")
    print(f"推送统计：即时 {instant_pushed} 条 | 总推送 {pushed} 条")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
