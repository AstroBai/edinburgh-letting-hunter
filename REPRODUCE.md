# Edinburgh Letting Agent Scraper — 项目复现说明

本文档供另一个 agent 完整复现本项目使用。

---

## 项目目标

每 30 分钟抓取 Edinburgh 多家租房中介网站 + SpareRoom + OpenRent 的房源，过滤出目标位置周围指定范围内 ≤2 卧室的出租房，新房源通过 Gmail 发送邮件通知。

---

## 项目结构

```
/path/to/letting_agent/
├── config.py              # 核心配置（坐标、范围、邮箱、来源列表）
├── scrape_all.py          # 主入口 — 调度所有爬虫 + 存储 + 通知
├── storage.py             # SQLite 数据库（去重）
├── notifier.py            # 邮件发送（HTML 表格，按价格排序，跨站去重）
├── geocode.py             # 邮编 → 坐标、距离计算、附近 outcode 白名单
├── setup_cron.py          # cron 任务管理器
├── install_cron.sh        # 快速安装 cron
├── remove_cron.sh         # 快速移除 cron
├── requirements.txt       # Python 依赖
├── README.md              # 用户文档
├── REPRODUCE.md           # 本文档
├── scrapers/
│   ├── __init__.py
│   ├── base.py            # 基类：_extract_price_pcm, _extract_beds, _extract_postcode, _extract_available_date, geo-filter
│   ├── citylets.py        # Citylets 爬虫 — requests + BeautifulSoup
│   ├── spareroom.py       # SpareRoom 爬虫 — 从 data-* 属性提取
│   ├── headless.py        # Playwright 工具 + ESPC/Rettie/Umega 爬虫
│   └── other_agents.py    # 所有其它中介（Belvoir, Cornerstone, Southside, OpenRent, Clan Gordon, Albany 等）
└── listings.db            # SQLite 数据库（自动创建）
```

---

## 环境要求

- Python >= 3.10
- pip 包（见 requirements.txt）:
  - requests, beautifulsoup4, lxml, haversine
- 可选：playwright（用于 JS 渲染的网站）

---

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip3 install requests beautifulsoup4 lxml haversine
```

### 2. （可选）安装 Playwright

用于抓取 JS 动态渲染的网站（Southside Management、Clan Gordon、ESPC 等）。

```bash
pip3 install playwright
playwright install chromium
```

> 注意：ESPC、s1homes、DJ Alexander 即使装了 Playwright 也可能被反爬拦截。

### 3. 配置

编辑 `config.py`：

```python
# 中心点坐标（替换为你的目标位置）
TARGET_POSTCODE = "EH9 2XX"
TARGET_LAT = 55.930000
TARGET_LON = -3.190000
RADIUS_MILES = 1.2
MAX_BEDS = 2

# Gmail 发件配置
EMAIL_FROM = "your-email@gmail.com"
EMAIL_TO = "your-email@gmail.com"
EMAIL_USERNAME = "your-email@gmail.com"
EMAIL_APP_PASSWORD = "your-16-char-app-password"  # Gmail 应用专用密码
```

Gmail 应用密码在 https://myaccount.google.com/apppasswords 生成（需开启两步验证）。

### 4. 测试运行

```bash
python3 scrape_all.py --dry-run    # 只打印，不发邮件
python3 scrape_all.py              # 正式运行并发送邮件
```

### 5. 安装定时任务（每 30 分钟）

```bash
bash install_cron.sh
```

查看日志：

```bash
tail -f /path/to/letting_agent/cron.log
```

---

## 架构设计

### 数据流

```
每个中介网站 → 继承 BaseScraper → fetch_listings() → scrape()
                                                         ↓
                                              _filter() 过滤：
                                                1. 床数 > MAX_BEDS → 排除
                                                2. outcode 预过滤（NEARBY_OUTCODES）
                                                3. 有完整邮编 → 精确 geocoding + 距离检查
                                                4. 只有 outcode → outcode 白名单检查
                                                         ↓
                                              record_listings() 写入 SQLite
                                              （去重键：source + external_id）
                                                         ↓
                                              send_notification()
                                                • 跨站去重（同 outcode + 同价格 ±£50）
                                                • 按价格升序
                                                • HTML 邮件 + 控制台打印
```

### 关键文件说明

#### `config.py`
```python
SOURCES = [
    ("Citylets", "scrapers.citylets", "CityletsScraper", True),
    ("SpareRoom", "scrapers.spareroom", "SpareRoomScraper", True),
    ...
]
```
每行 = (显示名称, 模块路径, 类名, 启用状态)

#### `geocode.py`
- `NEARBY_OUTCODES` — 通过 outcode 预过滤的白名单（1.2 英里范围）
- `BROAD_OUTCODES` — 更宽松的集合，用于第一轮过滤
- `geocode_postcode()` — 调用 postcodes.io API
- `is_within_radius()` — Haversine 距离计算

#### `scrapers/base.py`
BaseScraper 提供：
- `_extract_price_pcm(text)` — 支持 `£X pcm`, `£X pw`, `£X per month`, `£X /month`
- `_extract_beds(text)` — 匹配 `N bed`/`N Bedroom`
- `_extract_postcode(text)` — 匹配 UK 完整邮编
- `_extract_available_date(text)` — 匹配 `Available From: ...`, `Available Now`
- `_filter(listings)` — 地理 + 床数过滤 + 按价格排序

#### `notifier.py`
- 跨站去重：同一 outcode + 同一价格（±£50）视为重复
- HTML 邮件：Source / Title + Available Date / Beds / Price / Location
- 按价格从低到高排序

---

## 爬虫编写指南

### 如何添加新网站

1. 在 `scrapers/other_agents.py` 末尾添加新类：

```python
class MyNewScraper(OtherAgentsScraper):
    SOURCE_NAME = "My Agency"
    SEARCH_URL = "https://example.com/properties-to-rent"
    EXTRACT_STRATEGY = "html"  # 或 "embedded_js" 或 "json_ld"

    def fetch_listings(self) -> list[dict]:
        soup = self._soup(self.SEARCH_URL)
        if not soup:
            return []
        results = []
        for card in soup.select(".property-card"):
            link = card.find("a", href=True)
            text = card.get_text(" ", strip=True)
            results.append({
                "external_id": link["href"],
                "url": link["href"],
                "title": text[:100],
                "price_pcm": self._extract_price_pcm(text),
                "beds": self._extract_beds(text),
                "address": text[:80],
                "postcode": self._extract_postcode(text),
                "available_date": self._extract_available_date(text),
            })
        return results
```

2. 在 `config.py` 的 `SOURCES` 列表添加：

```python
("My Agency", "scrapers.other_agents", "MyNewScraper", True),
```

3. 测试：

```bash
python3 -c "from scrapers.other_agents import MyNewScraper; s=MyNewScraper(); print(s.scrape())"
```

### 价格格式支持

`_extract_price_pcm` 支持以下格式：
- `£1,000 pcm`
- `£1,000 per month`
- `£250 pw` / `£250 per week`
- `£1,000 /month`

如需新格式，在 `scrapers/base.py` 中添加正则。

---

## 已启用来源列表

| # | 名称 | 方式 | 状态 |
|---|------|------|------|
| 1 | Citylets | requests + BS4 | ✅ |
| 2 | SpareRoom | requests + BS4 (data-*) | ✅ |
| 3 | ESPC | Playwright | ⚠️ 反爬 |
| 4 | s1homes | Playwright | ⚠️ 反爬 |
| 5 | Belvoir | requests + BS4 | ✅ ~8条 |
| 6 | Northwood | requests + BS4 | ⏸️ 禁用（数据乱）|
| 7 | A Flat in Town | JS | ❌ 未解析 |
| 8 | Dove Davies | requests + BS4 | ✅ 有数据 |
| 9 | Cornerstone | requests + BS4 | ✅ ~2条 |
| 10 | Southside Mgmt | Playwright | ✅ ~1条 |
| 11 | Edinburgh LC | requests + BS4 | ✅ ~2条 |
| 12 | Glenham | requests + BS4 | ✅ 有数据 |
| 13 | Murray & Currie | requests + BS4 | ✅ 有数据 |
| 14 | Clan Gordon | Playwright | ✅ ~1-2条 |
| 15 | Albany Lettings | requests + BS4 | ✅ ~1条 |
| 16 | OpenRent | requests + BS4 | ✅ ~10条 |
| 17 | DJ Alexander | Playwright | ⚠️ 反爬 |

---

## 常见问题

### Q: 邮件发不出去？
检查 `config.py` 中的 Gmail 应用密码是否正确，或设成环境变量：
```bash
export LETTING_AGENT_EMAIL_USER="your-email@gmail.com"
export LETTING_AGENT_EMAIL_PASS="16位密码"
```

### Q: 没有新房源？
1. 先清除数据库再跑：`rm listings.db && python3 scrape_all.py`
2. 看看哪些中介有数据：检查控制台输出中 "Fetched X raw listings"

### Q: 太多重复？
notifier.py 中有跨站去重逻辑（同 outcode + 同价格）。如需更严格，可增加地址文本相似度匹配。

### Q: 想改频率？
```bash
(crontab -l | grep -v scrape_all; echo "*/15 * * * * /path/to/python3 /path/to/scrape_all.py >> /path/to/cron.log 2>&1") | crontab -
```
