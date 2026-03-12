import os
import json
import time
import requests
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
STATE_FILE = "processed_ids.json"

KEYWORDS = [
    "重大资产重组", "资产重组", "重组",
    "收购", "并购", "合并",
    "股权收购", "要约收购",
    "控制权变更", "实际控制人",
    "重大合同", "重大投资", "增资", "借壳", "上市" ,
]

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

def analyze(ann):
    """本地关键词规则打分，不依赖外部AI"""
    title = ann["title"]
    score = 6  # 基础分
    reason = "命中重大事件关键词"
    
    if any(kw in title for kw in ["重大资产重组", "借壳", "上市" , "要约收购"]):
        score = 9
        reason = "重大资产重组/借壳/上市/要约收购，市场高度关注"
    elif any(kw in title for kw in ["收购", "并购", "合并"]):
        score = 8
        reason = "收购/并购事件，可能带来估值重塑"
    elif any(kw in title for kw in ["控制权变更", "实际控制人"]):
        score = 8
        reason = "控制权变更，公司发展方向可能改变"
    elif any(kw in title for kw in ["重大合同", "重大投资"]):
        score = 7
        reason = "重大合同/投资，业绩有望提升"
    
    # 含"终止""撤回""失败"等负面词降分
    if any(kw in title for kw in ["终止", "撤回", "失败", "取消", "无法"]):
        score = max(3, score - 4)
        reason = "事项终止或失败，可能构成利空"
    
    return {
        "is_positive": score >= 6,
        "score": score,
        "reason": reason,
        "risk": "请结合基本面自行判断",
        "suggestion": "关注后续公告进展"
    }
    prompt = f"""你是资深A股分析师，分析以下公告对股票的影响：
股票：{ann['stock_name']}（{ann['stock_code']}）
公告：{ann['title']}
只返回JSON：{{"is_positive":true或false,"score":1到10的整数,"reason":"原因50字内","risk":"风险30字内","suggestion":"建议30字内"}}"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    try:
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Gemini失败] {e}")
        return {"is_positive": True, "score": 5, "reason": "分析失败", "risk": "-", "suggestion": "请自行判断"}

def push(ann, analysis):
    if not SERVERCHAN_KEY:
        return
    score = analysis.get("score", 0)
    if not analysis.get("is_positive") or score < 6:
        print(f"[过滤] {ann['title']} 评分{score}，跳过")
        return
    stars = "⭐" * min(score, 10)
    title = f"🔔 {ann['stock_name']}（{ann['stock_code']}）重大公告"
    content = f"## {ann['title']}\n\n**时间：** {ann['time']}\n\n| 项目 | 内容 |\n|------|------|\n| 利好评分 | {stars} {score}/10 |\n| 原因 | {analysis.get('reason','-')} |\n| 风险 | {analysis.get('risk','-')} |\n| 建议 | {analysis.get('suggestion','-')} |\n\n🔗 [查看原文]({ann['url']})\n\n> ⚠️ AI分析仅供参考，不构成投资建议"
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send", data={"title": title, "desp": content}, timeout=10)
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
    for a in anns[:10]: print(f"  标题: {a['title']}")
    pushed = 0
    for ann in anns:
        if ann["id"] in ids:
            continue
        if not is_major(ann["title"]):
            ids.add(ann["id"])
            continue
        print(f"[命中] {ann['stock_name']} - {ann['title']}")
        result = analyze(ann)
        print(f"  评分: {result.get('score')}/10 | {result.get('reason')}")
        push(ann, result)
        if result.get("is_positive") and result.get("score", 0) >= 6:
            pushed += 1
        ids.add(ann["id"])
        time.sleep(1)
    save_ids(ids)
    print(f"完成，推送 {pushed} 条")

if __name__ == "__main__":
    main()
