"""测试 Server酱 微信推送是否正常"""
import os
import sys
import requests

def test_push(send_key):
    """发送一条测试消息到微信"""
    title = "stock-monitor 推送测试"
    content = (
        "## 测试成功\n\n"
        "如果你收到这条消息，说明 **Server酱推送通道正常**。\n\n"
        "- 项目：stock-monitor\n"
        "- 时间：当前\n"
        "- 用途：A股重大公告微信提醒\n\n"
        "⚠️ 这是一条测试消息"
    )

    try:
        r = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={"title": title, "desp": content},
            timeout=10,
        )
        result = r.json()
        code = result.get("code")
        if code == 0:
            print("✅ 推送成功！请检查微信是否收到消息。")
            return True
        else:
            print(f"❌ 推送返回异常 code={code}，response={result}")
            return False
    except Exception as e:
        print(f"❌ 推送失败: {e}")
        return False


if __name__ == "__main__":
    # 优先从命令行参数读取
    if len(sys.argv) > 1:
        key = sys.argv[1]
    else:
        key = os.environ.get("SERVERCHAN_KEY", "")

    if not key:
        print("=" * 50)
        print("未找到 SERVERCHAN_KEY")
        print("")
        print("使用方法：")
        print("  python test_push.py <你的Server酱SendKey>")
        print("")
        print("获取 SendKey：")
        print("  1. 打开 https://sct.ftqq.com/")
        print("  2. 微信扫码登录")
        print("  3. 复制你的 SendKey")
        print("=" * 50)
        sys.exit(1)

    print(f"使用 SendKey: {key[:8]}...{key[-4:]}")
    test_push(key)
