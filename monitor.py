import os
import json
import time
import requests
from datetime import datetime, date

SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
STATE_FILE = "processed_ids.json"

# ─────────────────────────────────────────
# 事件关键词（触发抓取）
# ─────────────────────────────────────────
KEYWORDS = [
    # 停牌信号（最早期最强信号）
    "筹划重大事项", "申请停牌", "重大事项停牌",
    # 重组并购
    "重大资产重组", "资产重组", "重组",
    "借壳", "吸收合并", "要约收购",
    "收购", "并购", "股权收购",
    # 控制权转让
    "控制权变更", "实际控制人",
    "股份转让", "股权转让",
    # 国资入主
    "国资入主", "国有资本", "国有企业",
    # ST摘帽
    "摘帽", "取消退市风险警示",
    # 融资投资
    "重大合同", "重大投资", "增资",
    "定向增发", "非公开发行",
    # 资本运作
    "分拆上市",
    "股票回购",
    # 业绩
    "业绩预增", "业绩大幅增长",
]

# ─────────────────────────────────────────
# 噪音过滤黑名单（标题含这些词直接跳过）
# ─────────────────────────────────────────
BLACKLIST = [
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
]

# ─────────────────────────────────────────
# 主线赛道关键词
# ─────────────────────────────────────────
HOTTRACK_KEYWORDS = {
    "AI人工智能": ["人工智能", "大模型", "AI", "算力", "智算", "大数据", "云计算"],
    "半导体芯片": ["半导体", "芯片", "集成电路", "晶圆", "光刻", "EDA", "封测"],
    "机器人":     ["机器人", "人形机器人", "具身智能", "智能制造"],
    "低空经济":   ["低空", "无人机", "eVTOL", "飞行汽车", "通用航空"],
    "新能源":     ["新能源", "锂电池", "储能", "光伏", "风电", "氢能", "固态电池"],
    "军工":       ["军工", "国防", "航天", "航空", "兵器", "舰船", "卫星", "导弹"],
    "创新药":     ["创新药", "生物医药", "基因", "细胞治疗", "新药", "CXO"],
    "量子/卫星":  ["量子", "卫星互联网", "商业航天", "北斗"],
}

# ─────────────────────────────────────────
# 大盘央企黑名单（连板概率极低）
# ─────────────────────────────────────────
LARGE_CAPS = [
    "中国神华", "中国电建", "中国建筑", "中国中铁", "中国铁建",
    "工商银行", "建设银行", "农业银行", "中国银行", "招商银行",
    "中国石油", "中国石化", "中国海油", "中国移动", "中国联通",
    "中国电信", "中国人寿", "中国平安", "贵州茅台", "中国中车",
    "中国煤炭", "中国交建", "中国核电", "中国广核", "华能国际",
]

# ─────────────────────────────────────────
# 动态抓取页数（根据时间段）
# ─────────────────────────────────────────
def get_pages():
    hour = datetime.now().hour
    if 15 <= hour < 20:
        return 6    # 盘后高峰300条
    elif 9 <= hour < 15:
        return 2    # 交易时间100条
    else:
        return 3    # 其他时间150条

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
            "sr": -1, "page_size": 50, "page_index": page,
            "ann_type": "A", "client_source": "web",
            "f_node": 0, "s_node": 0,
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
            "id":         str(item.get("art_code", "")),
            "stock_code": code,
            "stock_name": item.get("codes", [{}])[0].get("short_name", "") if item.get("codes") else "",
            "title":      item.get("title", ""),
            "time":       item.get("notice_date", ""),
            "url":        f"https://data.eastmoney.com/notices/detail/{code}/{item.get('art_code','')}.html",
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

def is_major(title):
    return any(kw in title for kw in KEYWORDS)

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

# ─────────────────────────────────────────
# 评分与分析
# ─────────────────────────────────────────
def analyze(ann):
    title = ann["title"]
    name  = ann["stock_name"]
    code  = ann["stock_code"]
    board, limit, need_perm, is_st = get_stock_type(code, name)
    large_cap = is_large_cap(name)

    score = 6
    event_type = "重大事件"
    reason = "命中重大事件关键词"

    if any(kw in title for kw in ["筹划重大事项", "申请停牌", "重大事项停牌"]):
        score, event_type = 10, "筹划重大事项停牌"
        reason = "信息完全空白，市场自由想象，复牌首日历史上大概率一字涨停"

    elif "要约收购" in title:
        score, event_type = 10, "要约收购"
        reason = "收购方溢价收购，目标价锁定，资金疯狂追入，连板概率极高"

    elif any(kw in title for kw in ["摘帽", "取消退市风险警示"]):
        score, event_type = 10, "ST摘帽"
        reason = "从5%变10%涨停，利好明确，历史上摘帽首日几乎必连板"

    elif any(kw in title for kw in ["重大资产重组", "借壳", "吸收合并"]):
        score, event_type = 9, "重大资产重组/借壳"
        reason = "资产注入或借壳，估值重构，市场高度关注，连续涨停概率大"

    elif any(kw in title for kw in ["国资入主", "国有资本", "国有企业"]):
        score, event_type = 9, "国资入主"
        reason = "国有资本接盘，信用背书强，市场认可度高，历史上多为连板起点"

    elif any(kw in title for kw in ["控制权变更", "股份转让", "股权转让", "实际控制人"]):
        score, event_type = 8, "控制权/股权转让"
        reason = "控制权易主，公司发展方向可能根本性改变，资本市场高度敏感"

    elif any(kw in title for kw in ["收购", "并购", "股权收购"]):
        score, event_type = 8, "收购/并购"
        reason = "收购并购事件，可能带来估值重塑和业务协同"

    elif "分拆上市" in title:
        score, event_type = 8, "分拆上市"
        reason = "子公司独立上市，释放隐藏价值，母公司估值重塑"

    elif any(kw in title for kw in ["重大合同", "重大投资"]):
        score, event_type = 7, "重大合同/投资"
        reason = "重大合同落地，业绩有望大幅提升"

    elif any(kw in title for kw in ["业绩预增", "业绩大幅增长"]):
        score, event_type = 7, "业绩预增"
        reason = "业绩超预期增长，基本面改善明显"

    elif any(kw in title for kw in ["定向增发", "非公开发行"]):
        score, event_type = 7, "定向增发"
        reason = "定向增发引入资金或战略投资者"

    elif "股票回购" in title:
        score, event_type = 7, "股票回购"
        reason = "大额回购彰显信心，护盘意图明显"

    # ST加分
    if is_st and score < 10:
        score = min(10, score + 1)
        reason += "。ST股体量小，资金容易拉升"

    # 主线赛道加分
    tracks = get_hottrack(ann)
    if tracks:
        bonus = 1 if len(tracks) == 1 else 2
        score = min(10, score + bonus)
        reason += f"。主线赛道（{'、'.join(tracks)}）+{bonus}分"

    # 大盘股降分
    if large_cap:
        score = max(3, score - 3)
        reason += "。大盘央企体量大，连板概率极低"

    # 负面词降分
    if any(kw in title for kw in ["终止", "撤回", "失败", "取消", "无法"]):
        score = max(2, score - 5)
        event_type = "事项终止"
        reason = "重大事项终止或撤回，可能构成利空，注意风险"
        tracks = []

    # 利好等级
    if score == 10:
        level, burst = "🌋 核爆利好", "极高"
    elif score >= 9:
        level, burst = "🔥 重大利好", "高"
    elif score >= 8:
        level, burst = "⭐ 明显利好", "中高"
    elif score >= 6:
        level, burst = "📢 值得关注", "中"
    else:
        level, burst = "⚠️ 谨慎关注", "低"

    return {
        "is_positive": score >= 6,
        "score": score, "level": level, "burst": burst,
        "event_type": event_type, "reason": reason,
        "tracks": tracks, "board": board, "limit": limit,
        "need_perm": need_perm, "is_st": is_st, "large_cap": large_cap,
    }

# ─────────────────────────────────────────
# 推送微信
# ─────────────────────────────────────────
def push(ann, analysis):
    if not SERVERCHAN_KEY:
        return
    score = analysis["score"]
    if not analysis["is_positive"] or score < 6:
        print(f"[过滤] {ann['title']} 评分{score}")
        return

    tracks    = analysis["tracks"]
    is_st     = analysis["is_st"]
    need_perm = analysis["need_perm"]
    large_cap = analysis["large_cap"]

    tags = []
    if is_st:       tags.append("【ST-5%涨停】")
    if need_perm:   tags.append("【需开通权限】")
    if large_cap:   tags.append("【大盘股-连板概率低】")
    if tracks:      tags.append(f"【{'|'.join(tracks)}】")
    tag_str = " ".join(tags) if tags else ""

    if score == 10:
        msg_title = f"🌋 {ann['stock_name']}（{ann['stock_code']}）核爆公告"
    elif tracks:
        msg_title = f"🚀 【主线】{ann['stock_name']}（{ann['stock_code']}）重大公告"
    else:
        msg_title = f"🔔 {ann['stock_name']}（{ann['stock_code']}）重大公告"

    stars = "⭐" * min(score, 10)
    content = (
        f"## {ann['title']}\n\n"
        + (f"{tag_str}\n\n" if tag_str else "")
        + f"**🕐 时间：** {ann['time']}\n"
        f"**📈 板块：** {analysis['board']} | 涨停幅度：{analysis['limit']}\n\n"
        f"---\n\n"
        f"| 项目 | 内容 |\n|------|------|\n"
        f"| 利好等级 | {analysis['level']} |\n"
        f"| 综合评分 | {stars} {score}/10 |\n"
        f"| 事件类型 | {analysis['event_type']} |\n"
        f"| 主线赛道 | {'、'.join(tracks) if tracks else '—'} |\n"
        f"| 爆发概率 | {analysis['burst']} |\n"
        f"| 核心逻辑 | {analysis['reason']} |\n\n"
        f"---\n\n"
        f"⚠️ 以上为规则分析，仅供参考，不构成投资建议\n\n"
        f"🔗 [查看原文公告]({ann['url']})"
    )
    try:
        r = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data={"title": msg_title, "desp": content},
            timeout=10
        )
        print(f"[推送] {msg_title} → code:{r.json().get('code')}")
    except Exception as e:
        print(f"[推送失败] {e}")

# ─────────────────────────────────────────
# 状态管理
# ─────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"ids": [], "daily": {}}

def save_state(state):
    state["ids"] = list(state["ids"])[-2000:]
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False)

# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"监控启动 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    state = load_state()
    processed_ids = set(state.get("ids", []))
    today = str(date.today())

    daily_best = state.get("daily", {})
    if daily_best.get("date") != today:
        daily_best = {"date": today, "stocks": {}}

    anns = fetch_announcements()
    candidates = []

    for ann in anns:
        ann_id = ann["id"]
        code   = ann["stock_code"]

        if ann_id in processed_ids:
            continue
        if is_bond(code):
            processed_ids.add(ann_id)
            continue
        if is_noise(ann["title"]):
            processed_ids.add(ann_id)
            continue
        if not is_major(ann["title"]):
            processed_ids.add(ann_id)
            continue

        print(f"[命中] {ann['stock_name']}（{code}）- {ann['title']}")
        result = analyze(ann)
        print(f"  → {result['level']} {result['score']}/10 | {result['event_type']}")
        candidates.append((ann, result))
        processed_ids.add(ann_id)

    # 同一股票今日只推最高分
    to_push = {}
    for ann, result in candidates:
        code  = ann["stock_code"]
        score = result["score"]
        if score > daily_best["stocks"].get(code, 0) and result["is_positive"] and score >= 6:
            to_push[code] = (ann, result)
            daily_best["stocks"][code] = score

    pushed = 0
    for code, (ann, result) in to_push.items():
        push(ann, result)
        pushed += 1
        time.sleep(0.5)

    state["ids"]   = list(processed_ids)
    state["daily"] = daily_best
    save_state(state)

    print(f"本轮完成：命中 {len(candidates)} 条，推送 {pushed} 条")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
