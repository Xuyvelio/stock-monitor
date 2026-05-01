# stock-monitor

自用的 A 股重大公告微信提醒工具。

定时抓取东财公告，按关键词打分，结合盘中行情、公告正文校验和 AI 智能分析，推送到微信。

## 工作流程

```
东财公告 → 标题关键词打分(6~10)
         → 加分项(赛道偏好/ST)
         → 扣分项(大盘股/流程性/不确定性/负面)
         → 行情校验(涨停-2/跌停-3/已涨>5%-1/换手>15%-1)
         → 正文校验(巨潮PDF, 负面关键词-4/不确定性-2)
         → AI校验(DeepSeek, 规则60%+AI40%加权)
         → 即时推送 / 18:00+24:00 汇总
```

## 当前能力

### 数据源
- 东财公告 API（全市场 5000+ 只 A 股）
- 腾讯行情接口（实时股价/涨跌/换手/涨停判断）
- 巨潮资讯网（公告 PDF 下载，正文提取）

### 评分体系
- 标题关键词匹配（10 级评分：停牌重组 10 分 → 回购 7 分）
- 赛道加分（AI/半导体/机器人/低空经济等 8 条赛道）
- 偏好赛道额外加分
- ST 股加分
- 大盘股扣分 / 流程性扣分 / 不确定性扣分 / 负面扣分

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

### AI 评分（仅 ≥7 分公告）
- DeepSeek API（OpenAI 格式）
- 规则 60% + AI 40% 加权
- AI 认为明显更低时降分，认为更高时最多 +1
- 每轮最多调 5 次，防止超额

### 推送策略
- 即时推送：爆发型事件得分 ≥9
- 每日两次汇总：18:00 盘后 + 24:00 晚间
- 晚间只推 18:00 之后新增的公告，不重复
- 每日同股只推更高分的一条

### 过滤机制
- 债券公告（11/12 开头）直接跳过
- 忽略名单（股票代码/名称/关键词）
- 硬过滤（董事会决议/回复函/进展公告等）
- 噪音过滤（修订报告/核查意见/独立董事意见等）

## 文件说明

| 文件 | 说明 |
|------|------|
| `monitor.py` | 主程序（~1050 行） |
| `config.json` | 个人配置（阈值/关键词/赛道/忽略名单/API key） |
| `processed_ids.json` | 去重和汇总状态（自动维护） |
| `requirements.txt` | Python 依赖（requests, PyPDF2） |
| `.github/workflows/monitor.yml` | GitHub Actions 定时任务 |
| `.gitignore` | 排除缓存和日志 |

## 配置

编辑 `config.json`：

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

### 汇总推送时间

```json
"summary": {
  "enabled": true,
  "send_hours": [18, 24]
}
```

### 爆发型策略

```json
"explosive": {
  "instant_only_explosive": true,
  "min_score": 9,
  "summary_min_score": 7
}
```

### DeepSeek API

```json
"deepseek_api_key": "sk-xxx"
```

也可通过环境变量 `DEEPSEEK_API_KEY` 设置。

## GitHub Actions 使用

仓库需要配置 Secrets：

- `SERVERCHAN_KEY`：Server 酱推送 key
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
- 当前主要依赖公告标题做判断，正文做二次校验
- AI 评分仅辅助，不会完全替代规则
- 所有结果仅供自用参考，不构成投资建议
