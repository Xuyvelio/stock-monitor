# stock-monitor

自用的 A 股重大公告微信提醒工具。

定时抓取东财公告，按关键词打分，结合盘中行情、市值过滤、公告正文校验和 AI 智能分析，即时推送到微信。

## 工作流程

```
东财公告 → 关键词初筛
         → 过滤(债券/大盘股/忽略/硬过滤/噪音)
         → 市值过滤(400亿以上跳过)
         → 标题关键词打分(7~10)
         → 加分项(赛道偏好/ST)
         → 扣分项(流程性/不确定性/负面)
         → 行情校验(涨停-2/跌停-3/已涨>5%-1/换手>15%-1)
         → 正文校验(巨潮PDF, 负面关键词-4/不确定性-2)
         → AI校验(DeepSeek, 规则60%+AI40%加权)
         → 即时推送(爆发型≥7分) / 盘后汇总(19:00)
```

## 当前能力

### 数据源
- 东财公告 API（全市场 5000+ 只 A 股）
- 腾讯行情接口（实时股价/涨跌/换手/涨停判断/总市值）
- 巨潮资讯网（公告 PDF 下载，正文提取）

### 评分体系
- 标题关键词匹配（10 级评分：停牌重组 10 分 → 回购 7 分）
- 赛道加分（AI/半导体/机器人/低空经济等 8 条赛道）
- 偏好赛道额外加分
- ST 股加分
- 流程性扣分 / 不确定性扣分 / 负面扣分

### 市值过滤
- 总市值 > 400 亿直接跳过，不评分不推送
- 已知大盘蓝筹（工商银行/茅台/中石油等 25 只）在过滤阶段直接拦截
- 阈值可在 `config.json` 的 `max_market_cap` 调整

### 行情校验
- 已涨停 → -2 分（封板买不进）
- 已跌停 → -3 分（利空已兑现）
- 盘中已涨 >5% → -1 分（追高风险）
- 换手率 >15% → -1 分（筹码松动）

### 正文校验（仅 ≥7 分公告）
- 巨潮资讯网搜索 → 下载 PDF → PyPDF2 提取文字
- 正文负面关键词 → -4 分（终止/撤回/未通过等）
- 正文不确定性 → -2 分（尚需经/能否获得等）
- 校验通过打【已校验正文】标签

### AI 评分（≥7 分 + 正文无负面触发）
- DeepSeek API（OpenAI 格式）
- 规则 60% + AI 40% 加权
- AI 降分才生效，升分最多 +1（防 AI 误判）
- 每轮最多调 5 次，防止超额

### 推送策略
- 即时推送：爆发型事件（重组/借壳/要约收购/国资入主/摘帽等）得分 ≥7，立即推
- 每日汇总：19:00（北京时间）一次，汇总当天所有 ≥7 分公告
- 同一只股每天只推最高分的一条
- 已推过的汇总不会重复推送
- 支持多个方糖 Key 逗号分隔，轮发到不同微信

### 过滤机制
- 债券公告（11/12 开头）直接跳过
- 大盘股名单（25 只央企大蓝筹）直接跳过
- 忽略名单（股票代码/名称/关键词）
- 硬过滤（董事会决议/回复函/进展公告等）
- 噪音过滤（修订报告/核查意见/独立董事意见等）
- 市值超标（>400 亿）跳过

### 动态抓取
- 根据时间段自动调整抓取页数，确保覆盖当天全部公告
- 盘中 40 页 / 盘后 60 页 / 深夜 80 页
- 日志显示实抓页数，最后一页满时有 ⚠️ 警告

## 文件说明

| 文件 | 说明 |
|------|------|
| `monitor.py` | 主程序 |
| `config.json` | 个人配置（阈值/关键词/赛道/忽略名单/市值上限） |
| `processed_ids.json` | 去重和汇总状态（自动维护） |
| `requirements.txt` | Python 依赖（requests, PyPDF2） |
| `.github/workflows/monitor.yml` | GitHub Actions 定时任务 |
| `.gitignore` | 排除缓存和日志 |

## 配置

编辑 `config.json`：

### 推送策略

```json
"explosive": {
  "instant_only_explosive": true,
  "min_score": 7,
  "summary_min_score": 7
},
"summary": {
  "enabled": true,
  "send_hours": [19]
}
```

### 阈值

```json
"thresholds": {
  "min_score": 6,
  "instant_score": 9,
  "summary_score": 6,
  "large_cap_penalty": 3,
  "preferred_track_bonus": 1,
  "procedural_penalty": 2,
  "uncertainty_penalty": 2,
  "negative_penalty": 5
}
```

### 市值上限

```json
"max_market_cap": 400
```

单位亿元，超过的不抓不推。

### 偏好赛道

```json
"preferred_tracks": ["AI人工智能", "机器人", "半导体芯片", "低空经济"]
```

### 忽略名单

```json
"ignore": {
  "codes": [],
  "names": [],
  "keywords": ["减持计划", "股份质押", "对外担保"]
}
```

### DeepSeek API

```json
"deepseek_api_key": "sk-xxx"
```

也可通过环境变量 `DEEPSEEK_API_KEY` 设置，环境变量优先。

## GitHub Actions 使用

仓库需要配置 Secrets：

- `SERVERCHAN_KEY`：Server 酱推送 key，多账号用英文逗号分隔，如 `key1,key2`
- `DEEPSEEK_API_KEY`：DeepSeek API key

Workflow permissions 需设为 **Read and write permissions**（用于推送状态文件）。

然后启用 Actions 即可，每 5 分钟自动运行（周一到周五，UTC 1:00-14:59，即北京时间 9:00-22:59）。

## 本地运行

```bash
pip install -r requirements.txt
python monitor.py
```

## 注意

- 这是规则提醒工具，不是自动交易系统
- 主要依赖公告标题做判断，正文做二次校验
- AI 评分仅辅助，不会完全替代规则
- 所有结果仅供自用参考，不构成投资建议
