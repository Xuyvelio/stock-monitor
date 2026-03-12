import os
import json
import time
import requests
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
STATE_FILE = "processed_ids.json"

# ─────────────────────────────────────────
# 事件关键词（触发抓取）
# ─────────────────────────────────────────
KEYWORDS = [
    # 停牌信号（最早期最强信号）
    "筹划重大事项", "申请停牌", "重大事项停牌", "重大事项",
    # 重组并购
    "重大资产重组", "资产重组", "重组",
    "借壳", "吸收合并",
    "收购", "并购", "合并",
    "股权收购", "要约收购",
    # 控制权转让
    "控制权变更", "实际控制人",
    "股份转让", "股权转让",
    # 融资投资
    "重大合同", "重大投资", "增资",
    "定向增发", "非公开发行",
    # 资本运作
    "分拆上市", "分拆",
    "股票回购", "回购",
    # 业绩
    "业绩预增", "业绩大幅增长",
]

# ─────────────────────────────────────────
# 主线赛道关键词（公司名/公告内容匹配加分）
# ─────────────────────────────────────────
HOTTRACK_KEYWORDS = {
    "AI人工智能": ["人工智能", "大模型", "AI", "算力", "智算", "大数据", "云计算", "数字化"],
    "半导体芯片": ["半导体", "芯片", "集成电路", "晶圆", "光刻", "存储", "EDA", "封测"],
    "机器人": ["机器人", "人形机器人", "工业机器人", "具身智能", "智能制造", "自动化"],
    "低空经济": ["低空", "无人机", "eVTOL", "飞行汽车", "航空器", "通用航空"],
    "新能源": ["新能源", "锂电池", "储能", "光伏", "风电", "氢能", "固态电池"],
    "军工": ["军工", "国防", "航天", "航空", "兵器", "舰船", "卫星", "导弹"],
    "创新药": ["创新药", "生物医药", "基因", "细胞治疗", "新药", "医疗器械", "CXO"],
    "量子/卫星": ["量子", "卫星互联网", "商业航天", "北斗", "遥感"],
}

def fetch_announcements():
    """通过东方财富抓取全市场最新公告"""
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {
        "sr": -1,
        "page_size": 50,
        "page_index": 1,
        "ann_type": "A",
        "client_source": "web",
        "f_node": 0,
        "s_node": 0,
    }
    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        announcements = []
        for item in data.get("data", {}).get("list", []):
            announcements.append({
                "id": str(item.get("art_code", "")),
                "exchange": item.get("market", ""),
                "stock_code": item.get("codes", [{}])[0].get("stock_code", "") if item.get("codes") else "",
                "stock_name": item.get("codes", [{}])[0].get("short_name", "") if item.get("codes") else "",
                "title": item.get("title", ""),
                "time": item.get("notice_date", ""),
                "url": f"https://data.eastmoney.com/notices/detail/{item.get('codes', [{}])[0].get('stock_code', '')}/{item.get('art_code', '')}.html",
            })
        return announcements
    except Exception as e:
        print(f"[抓取失败] {e}")
        return []

def is_major(title):
    return any(kw in title for kw in KEYWORDS)

def get_hottrack(ann):
    """检测是否属于主线赛道，返回赛道名称列表"""
    text = ann["stock_name"] + ann["title"]
    matched = []
    for track, kws in HOTTRACK_KEYWORDS.items():
        if any(kw in text for kw in kws):
            matched.append(track)
    return matched

def analyze(ann):
    """本地关键词规则打分 + 主线赛道加分"""
    title = ann["title"]
    score = 6
    reason = "命中重大事件关键词"

    # ── 事件评分 ──────────────────────────
    # 最强信号：停牌筹划
    if any(kw in title for kw in ["筹划重大事项", "申请停牌", "重大事项停牌"]):
        score = 10
        reason = "筹划重大事项申请停牌，信息空白期想象空间极大，历史连板概率最高"

    # 顶级：重组借壳要约
    elif any(kw in title for kw in ["重大资产重组", "借壳", "要约收购", "吸收合并"]):
        score = 9
        reason = "重大资产重组/借壳/要约收购，市场高度关注，连续涨停概率大"

    # 控制权/股权转让
    elif any(kw in title for kw in ["控制权变更", "股份转让", "股权转让", "实际控制人"]):
        score = 8
        reason = "控制权/股权转让，公司方向可能改变，资本市场高度敏感"

    # 收购并购
    elif any(kw in title for kw in ["收购", "并购", "合并"]):
        score = 8
        reason = "收购/并购事件，可能带来估值重塑"

    # 分拆
    elif any(kw in title for kw in ["分拆上市", "分拆"]):
        score = 8
        reason = "分拆上市，子公司独立估值重塑"

    # 融资投资
    elif any(kw in title for kw in ["重大合同", "重大投资"]):
        score = 7
        reason = "重大合同/投资，业绩有望提升"
    elif any(kw in title for kw in ["业绩预增", "业绩大幅增长"]):
        score = 7
        reason = "业绩超预期增长，基本面改善"
    elif any(kw in title for kw in ["定向增发", "非公开发行"]):
        score = 7
        reason = "定向增发引入资金，看好公司发展"
    elif any(kw in title for kw in ["股票回购", "回购"]):
        score = 7
        reason = "大额回购彰显信心，护盘意图明显"

    # ── 主线赛道加分 ──────────────────────
    tracks = get_hottrack(ann)
    track_bonus = 0
    track_label = ""
    if tracks:
        track_bonus = 1 if len(tracks) == 1 else 2  # 多个赛道叠加加2分
        track_label = f"【主线赛道：{'、'.join(tracks)}】额外加{track_bonus}分"
        score = min(10, score + track_bonus)
        reason = reason + f"。{track_label}"

    # ── 负面词降分 ────────────────────────
    if any(kw in title for kw in ["终止", "撤回", "失败", "取消", "无法"]):
        score = max(3, score - 4)
        reason = "事项终止或失败，可能构成利空"
        tracks = []

    return {
        "is_positive": score >= 6,
        "score": score,
        "reason": reason,
        "risk": "请结合基本面自行判断",
        "suggestion": "关注后续公告进展，优先关注主线赛道标的" if tracks else "关注后续公告进展",
        "tracks": tracks,
    }

def push(ann, analysis):
    if not SERVERCHAN_KEY:
        return
    score = analysis.get("score", 0)
    if not analysis.get("is_positive") or score < 6:
        print(f"[过滤] {ann['title']} 评分{score}，跳过")
        return

    stars = "⭐" * min(score, 10)
    tracks = analysis.get("tracks", [])
    track_tag = "  ".join([f"`{t}`" for t in tracks]) if tracks else "—"

    title = f"🔔 {ann['stock_name']}（{ann['stock_code']}）重大公告"
    if tracks:
        title = f"🚀 【主线】{ann['stock_name']}（{ann['stock_code']}）重大公告"

    content = (
        f"## {ann['title']}\n\n"
        f"**时间：** {ann['time']}\n\n"
        f"| 项目 | 内容 |\n|------|------|\n"
        f"| 利好评分 | {stars} {score}/10 |\n"
        f"| 主线赛道 | {track_tag} |\n"
        f"| 事件分析 | {analysis.get('reason', '-')} |\n"
        f"| 主要风险 | {analysis.get('risk', '-')} |\n"
        f"| 操作建议 | {analysis.get('suggestion', '-')} |\n\n"
        f"🔗 [查看原文公告]({ann['url']})\n\n"
        f"> ⚠️ 以上为规则分析，仅供参考，不构成投资建议"
    )
    try:
        r = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data={"title": title, "desp": content},
            timeout=10
        )
        print(f"[推送结果] {r.json()}")
    except Exception as e:
        print(f"[推送失败] {e}")

def load_ids():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f).get("ids", []))
    except:
        return set()

def save_ids(ids):
    with open(STATE_FILE, "w") as f:
        json.dump({"ids": list(ids)[-1000:], "updated": str(datetime.now())}, f, ensure_ascii=False)

def main():
    print(f"监控启动 {datetime.now()}")
    ids = load_ids()
    anns = fetch_announcements()
    print(f"抓取公告：{len(anns)} 条")
    pushed = 0
    for ann in anns:
        if ann["id"] in ids:
            continue
        if not is_major(ann["title"]):
            ids.add(ann["id"])
            continue
        print(f"[命中] {ann['stock_name']} - {ann['title']}")
        result = analyze(ann)
        print(f"  评分: {result.get('score')}/10 | 赛道: {result.get('tracks')} | {result.get('reason')}")
        push(ann, result)
        if result.get("is_positive") and result.get("score", 0) >= 6:
            pushed += 1
        ids.add(ann["id"])
        time.sleep(1)
    save_ids(ids)
    print(f"完成，推送 {pushed} 条")

if __name__ == "__main__":
    main()
