import os
import json
import time
import hashlib
import requests
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
STATE_FILE = "processed_ids.json"

KEYWORDS = [
    "重大资产重组", "资产重组", "重组",
    "收购", "并购", "合并",
    "股权收购", "要约收购",
    "战略合作", "重大合同",
    "借壳", "重大资产购买",
    "控制权变更", "实际控制人",
    "重大投资", "增资",
]

def fetch_sse_announcements():
    url = "http://query.sse.com.cn/security/stock/queryCompanyAnnouncementNew.do"
    params = {"isPagination": "true", "pageHelp.pageSize": 30, "pageHelp.pageNo": 1, "pageHelp.beginPage": 1, "pageHelp.endPage": 1, "pageHelp.cacheSize": 1, "annType": "A", "token": ""}
    headers = {"Referer": "http://www.sse.com.cn/", "User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        announcements = []
        for item in r.json().get("pageHelp", {}).get("data", []):
            announcements.append({"id": f"SSE_{item.get('announcementId','')}", "exchange": "上交所", "stock_code": item.get("stockCode",""), "stock_name": item.get("secName",""), "title": item.get("announcementTitle",""), "time": item.get("announcementTime",""), "url": f"http://www.sse.com.cn/disclosure/listedinfo/announcement/c/{item.get('attachPath','')}"})
        return announcements
    except Exception as e:
        print(f"[SSE] 抓取失败: {e}")
        return []

def fetch_szse_announcements():
    url = "https://www.szse.cn/api/report/show/bond/bulletinType/index"
    params = {"SHOWTYPE": "JSON", "CATALOGID": "1", "tabkey": "tab1", "random": str(time.time())}
    headers = {"Referer": "https://www.szse.cn/", "User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        announcements = []
        for item in r.json().get("data", []):
            ann_id = item.get("id") or hashlib.md5(item.get("doctitle","").encode()).hexdigest()
            announcements.append({"id": f"SZSE_{ann_id}", "exchange": "深交所", "stock_code": item.get("stockcode",""), "stock_name": item.get("stockname",""), "title": item.get("doctitle",""), "time": item.get("doctime",""), "url": f"https://www.szse.cn{item.get('docurl','')}"})
        return announcements
    except Exception as e:
        print(f"[SZSE] 抓取失败: {e}")
        return []

def is_major_announcement(title):
    return any(kw in title for kw in KEYWORDS)

def analyze_with_gemini(ann):
    if not GEMINI_API_KEY:
        return {"is_positive": True, "analysis": "未配置Gemini Key", "score": 5}
    prompt = f"""你是资深A股分析师，分析以下公告对股票的影响：
股票：{ann['stock_name']}（{ann['stock_code']}）交易所：{ann['exchange']}
公告标题：{ann['title']}
只返回JSON：{{"is_positive":true/false,"score":1-10,"reason":"原因50字内","risk":"风险30字内","suggestion":"建议30字内"}}"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    try:
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Gemini] 失败: {e}")
        return {"is_positive": True, "score": 5, "reason": "AI分析失败", "risk": "未知", "suggestion": "请自行判断"}

def push_to_wechat(ann, analysis):
    if not SERVERCHAN_KEY:
        return
    score = analysis.get("score", 0)
    if not analysis.get("is_positive") or score < 6:
        print(f"[过滤] {ann['title']} 评分{score}分，跳过")
        return
    stars = "⭐" * min(score, 10)
    title = f"🔔 {ann['stock_name']}（{ann['stock_code']}）重大公告"
    content = f"## {ann['title']}\n\n**交易所：** {ann['exchange']}  \n**时间：** {ann['time']}\n\n| 项目 | 内容 |\n|------|------|\n| 利好评分 | {stars} {score}/10 |\n| 原因 | {analysis.get('reason','-')} |\n| 风险 | {analysis.get('risk','-')} |\n| 建议 | {analysis.get('suggestion','-')} |\n\n🔗 [查看原文]({ann['url']})\n\n> ⚠️ AI分析仅供参考，不构成投资建议"
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send", data={"title": title, "desp": content}, timeout=10)
        print(f"[推送] {r.json()}")
    except Exception as e:
        print(f"[推送异常] {e}")

def load_processed_ids():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f).get("ids", []))
    except:
        return set()

def save_processed_ids(ids):
    with open(STATE_FILE, "w") as f:
        json.dump({"ids": list(ids)[-1000:], "updated": str(datetime.now())}, f, ensure_ascii=False)

def main():
    print(f"监控启动 {datetime.now()}")
    processed_ids = load_processed_ids()
    all_ann = fetch_sse_announcements() + fetch_szse_announcements()
    print(f"抓取公告：{len(all_ann)} 条")
    pushed = 0
    for ann in all_ann:
        if ann["id"] in processed_ids:
            continue
        if not is_major_announcement(ann["title"]):
            processed_ids.add(ann["id"])
            continue
        print(f"[命中] {ann['stock_name']} - {ann['title']}")
        analysis = analyze_with_gemini(ann)
        push_to_wechat(ann, analysis)
        if analysis.get("is_positive") and analysis.get("score", 0) >= 6:
            pushed += 1
        processed_ids.add(ann["id"])
        time.sleep(1)
    save_processed_ids(processed_ids)
    print(f"完成，推送 {pushed} 条")

if __name__ == "__main__":
    main()
