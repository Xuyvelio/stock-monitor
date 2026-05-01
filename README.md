# stock-monitor

自用的 A 股重大公告微信提醒工具。

它会定时抓取东财公告，按规则筛选出更值得关注的事件，结合你的自选股、忽略名单、偏好赛道和推送阈值，发送到微信。

## 当前能力

- 定时抓取 A 股公告
- 重大事件关键词识别
- 噪音公告过滤
- 自选股优先提醒
- 忽略股票 / 标题关键词过滤
- 爆发型事件优先级推送
- 流程型标题硬过滤
- 偏好赛道额外加分
- 流程性 / 不确定性 / 负面关键词扣分
- 即时提醒 + 收盘后汇总
- 每日同股只推更高分的一条
- 可选运行日志输出
- `processed_ids.json` 保存运行状态

## 文件说明

- `monitor.py`：主程序
- `config.json`：个人配置
- `processed_ids.json`：去重和每日汇总状态
- `.github/workflows/monitor.yml`：GitHub Actions 定时任务

## 配置

编辑 `config.json`：

### 1. 阈值

```json
"thresholds": {
  "min_score": 6,
  "instant_score": 9,
  "summary_score": 6,
  "watchlist_min_score": 4,
  "large_cap_penalty": 3,
  "preferred_track_bonus": 1,
  "watchlist_bonus": 2
}
```

含义：

- `min_score`：默认正向候选最低分
- `instant_score`：达到这个分数实时推送
- `summary_score`：达到这个分数进入汇总
- `watchlist_min_score`：自选股的最低实时提醒分数
- `large_cap_penalty`：大盘股降分幅度
- `preferred_track_bonus`：偏好赛道加分
- `watchlist_bonus`：自选股加分

### 2. 自选股

```json
"watchlist": {
  "codes": ["000001"],
  "names": ["平安银行"]
}
```

### 3. 忽略名单

```json
"ignore": {
  "codes": [],
  "names": [],
  "keywords": ["减持计划", "股票交易异常波动"]
}
```

### 4. 偏好赛道

```json
"preferred_tracks": ["AI人工智能", "机器人", "半导体芯片"]
```

### 5. 爆发型优先策略

```json
"explosive": {
  "instant_only_explosive": true,
  "min_score": 9,
  "allow_watchlist_override": false,
  "summary_min_score": 7
}
```

含义：
- `min_score`：即时推送的爆发型最低分
- `allow_watchlist_override`：是否允许自选股绕过爆发型限制
- `summary_min_score`：进入收盘汇总的最低分

配合以下关键词：
- `explosive_event_keywords`：真正容易引发快速拉升的核心事件
- `hard_filter_keywords`：董事会决议、提示性公告、进展/回复类等直接过滤

### 6. 汇总推送

```json
"summary": {
  "enabled": true,
  "send_after_hour": 15
}
```

### 6. 运行日志

```json
"logging": {
  "enabled": true,
  "file": "daily_log.jsonl"
}
```

开启后会把每次命中的候选公告以 JSONL 形式落盘，方便你后面复盘和调规则。

### 7. 细化扣分项

```json
"thresholds": {
  "procedural_penalty": 2,
  "uncertainty_penalty": 2,
  "negative_penalty": 5
}
```

配合以下关键词使用：
- `procedural_keywords`：流程推进类标题，降低落地强度评分
- `uncertainty_keywords`：存在审批、备案、结果未定等不确定性
- `negative_keywords`：终止、撤回、失败等明显负面词

## 微信推送说明

### 即时提醒

主要发送：
- 高分重大公告
- 或你自选股里达到自定义阈值的公告

推送内容包含：
- 事件类型
- 最终评分
- 基础分
- 加分项
- 减分项
- 主线赛道
- 核心逻辑
- 原文公告链接

### 收盘汇总

收盘后会发送当天候选公告摘要，适合复盘。

## GitHub Actions 使用

仓库需要配置 Secret：

- `SERVERCHAN_KEY`

然后启用 Actions 即可按计划运行。

## 本地运行

```bash
python monitor.py
```

## 注意

- 这是规则提醒工具，不是自动交易系统。
- 当前主要依赖公告标题做判断。
- 所有结果仅供自用参考，不构成投资建议。
