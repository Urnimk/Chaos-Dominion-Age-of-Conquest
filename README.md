# 亂世演算：征佔紀元

《亂世演算：征佔紀元》（Chaos Dominion: Age of Conquest）是以 Python 製作的地圖戰略模擬遊戲。世界由 Seed 驅動生成，涵蓋地形、氣候、可居住性、國家、經濟、拓荒、殖民、外交與戰爭。國家從小型核心領土起步，逐步建設、擴張，並可能分裂、遷都或滅亡。

目前 `current/` 為 **V10｜國家 Q 表獨立 JSON 版**。各國學習資料另存 JSON，並新增相容載入流程；AI 模式仍可切換，預設使用原本規則 AI。本 Repository 是地圖戰爭模擬支線；各版本的原始說明集中於 `notes/`，歷代程式快照保存於 `versions/`。

## 功能概覽

- 以固定 Seed 生成世界地圖，可調整尺寸與世界風格。
- 生成氣候、水文、生態、農業、木材、礦產、淡水、建城與防禦等格子資料。
- 模擬國家人口、資源、城市、港口、軍隊、聯盟與 AI 決策。
- 以拓荒、遠征、補給、地形防禦和逐格占領推進領土變化。
- 支援海外殖民、殖民地獨立及跨海登陸；V8.4 的殖民港也能成為後續遠征據點。
- 提供可縮放、拖曳及點擊查詢的地圖介面，並顯示國家資訊、歷史事件及戰鬥紀錄。
- 可儲存與讀取地圖及戰局。

## 專案結構

```text
Chaos-Dominion-Age-of-Conquest/
├─ current/              # 目前可執行版本的程式與啟動檔
├─ notes/                # V1.0 至 V10 的版本說明原文
├─ versions/             # 合併至既有 Repository 後保留的歷代程式快照
├─ CHANGELOG.md           # 歷代版本重點索引
├─ README.md              # 專案介紹與執行方式
├─ requirements.txt       # Python 套件清單
└─ .gitignore             # 排除存檔、快取與暫存資料
```

### V10 `current/` 模組

| 檔案 | 用途 |
| --- | --- |
| `亂世演算_征佔紀元_V10_啟動.py` | 啟動遊戲介面 |
| `map_viewer.py` | Tkinter 介面、地圖互動、時間推進及存檔操作 |
| `war_engine.py` | 國家年度更新、AI 決策、拓荒、殖民、外交、遠征及戰鬥規則 |
| `map_generator.py` | 依設定建立或載入世界資料 |
| `environment_generator.py` | 氣候與水文等自然環境資料 |
| `habitability_generator.py` | 農業、木材、礦產、淡水及建城等適居性資料 |
| `country_generator.py` | 國家、首都與初始領土資料 |
| `map_renderer.py` | 將地形、領土及地圖圖層繪製成畫面 |
| `map_config.py` | 地圖、拓荒、殖民、戰爭及介面參數 |
| `terrain_rules.py`、`climate_rules.py` | 地形與氣候規則 |

## 安裝與啟動

建議使用 **Python 3.10 以上版本**。Windows 使用者請確認 Python 安裝時包含 `tkinter`。

在 Repository 根目錄安裝相依套件：

```bat
python -m pip install -r requirements.txt
```

切換到 `current/` 後啟動：

```bat
cd current
python "亂世演算_征佔紀元_V10_啟動.py"
```

Windows 也可在 `current/` 內執行 `啟動遊戲.bat`。一般請由啟動檔開啟，不要直接執行 `war_engine.py`。

## 基本操作

- 用滑鼠拖曳平移地圖，滾輪縮放；點選格子或國家可查看資料。
- 從介面控制模擬暫停、逐年／逐批推進及執行速度。
- 左側查看選定國家的狀態、領土、人口、軍隊、資源、建築與殖民地；排名可切換查詢對象。
- 事件區可查看國家歷史與戰鬥紀錄；殖民地或歷史地名可用介面提供的連結定位地圖。

## 參數與世界生成

`current/map_config.py` 集中放置地圖與模擬參數。常見設定包括：

- `MAP_WIDTH`、`MAP_HEIGHT`、`MAP_SEED`、`WORLD_STYLE`：地圖尺寸、Seed 與世界風格。
- `COUNTRY_COUNT`：開局國家數量。
- `INITIAL_TERRITORY_RADIUS`、`INITIAL_TERRITORY_MAX_CELLS`：新國家初始核心領土。
- `EXPANSION_*`、`BUILDING_*`：拓荒與建築節奏及成本。
- `COLONY_*`：殖民條件、成本、殖民港與獨立設定。
- `NAVAL_*`、`AI_NAVAL_TARGET_BONUS`：海上作戰與 AI 目標評估。
- `COUNTRY_NAME_FONT_SIZE`、`COUNTRY_NAME_FONT_BOLD`、`COUNTRY_NAME_OUTLINE_WIDTH`：地圖國名樣式。

預設地圖為 2000×2000 格，對記憶體與運算能力需求較高。初次測試或效能有限時，可先降低 `MAP_WIDTH`、`MAP_HEIGHT` 再啟動。

> **速度設定提醒：** V10 的程式碼目前在 `map_viewer.py` 將 `SECONDS_PER_YEAR` 設為 `0.01` 秒，`map_config.py` 也有同名參數；介面實際採用 `map_viewer.py` 的值，目標約為每秒 100 年。部分版本說明仍寫每年 2 秒，與程式預設值不一致。若要調整實際速度，請先修改介面使用的常數。

## 可切換 AI 模式

在 `current/map_config.py` 設定全域變數：

```python
AI_MODE = "RULE"          # 目前既有規則 AI，預設值
AI_MODE = "SARSA_LAMBDA"  # 各國獨立的 Expected SARSA(λ) 模式
```

每個國家各有一個 `CountryBrain`，其 Q 表、探索亂數與 eligibility trace 都獨立保存；新分裂政權會建立全新的大腦，不複製母國的學習資料。學習器的狀態固定為四個離散維度：

1. 軍隊／人口比例（安全狀態）
2. 糧食可支應年數（經濟狀態）
3. 本國領土占比（相對國力）
4. 可合法攻擊目標中的最佳戰力比（進攻機會）

每維四個級距，狀態最多 4 維、256 種組合；行動是「暫不開戰」或「選擇一個符合原有最低勝算門檻的合法戰爭目標」。這個模式只替換一般 AI 的開戰／目標選擇；經濟、建築、拓荒與自動反霸權圍剿仍沿用原有規則。`AI_MODE = "RULE"` 時不執行強化學習更新，保留原有玩法；學習資料另存為 `saves/war_state_rl_brains.json`，以國家 ID 區分並包含完整學習狀態。載入時優先使用與當前戰局快照相符的獨立 JSON；若沒有該檔，會回退讀取主戰局 JSON 內嵌的 Q 表，因此 V9 舊存檔可續載。V8.4 舊存檔缺少學習資料時則建立空白大腦。這次改動存檔架構，依版本規則升為整數大版本 V10。

在 `current/` 目錄執行回歸測試：

```bat
python -m unittest discover -s tests -v
```

**目前驗證結果：** 固定 Seed 的 512×512 長跑 1,000 年，地圖實際生成 24 國，期間分裂至 27 國；所有 27 國都有獨立大腦並產生更新。16 國存活，資源皆非負、士兵不超過人口。這是功能與穩定性測試，不代表強化學習策略已比既有 AI 更強。

## 存檔與重開新世界

程式會在 `current/saves/` 建立執行資料，例如地圖資料、預覽圖、世界資訊、戰局存檔及 `war_state_rl_brains.json`。請定期備份此資料夾。若要重新生成全新世界，先關閉遊戲，再將 `current/saves/` 移出或清空後重新啟動；這會一併移除目前的世界和戰局進度。

`saves/`、Python 快取及暫存檔不屬於原始碼，已由 `.gitignore` 排除，不應提交到 GitHub。

## 版本資料

- [CHANGELOG.md](CHANGELOG.md)：快速查閱 V1.0 至 V10 的版本重點。
- `notes/`：逐版原始說明；各檔記載當時功能、參數與測試紀錄。
- `versions/`：歷代完整程式快照，用於回溯與比較。執行最新版請使用 `current/`。

## 開發與測試範圍

版本說明中的長期模擬與功能測試，是各版本說明所記錄的結果；不代表每次上傳 GitHub 前都重新執行過相同測試。若修改戰爭、人口或存檔邏輯，建議固定 Seed，並檢查資源非負、存檔重載與 GUI 操作。
