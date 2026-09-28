# 亂世演算：征佔紀元

《亂世演算：征佔紀元》（Chaos Dominion: Age of Conquest）是以 Python 製作的地圖戰略模擬遊戲。世界由 Seed 驅動生成，涵蓋地形、氣候、可居住性、國家、經濟、拓荒、殖民、外交與戰爭。國家從小型核心領土起步，逐步建設、擴張，並可能分裂、遷都或滅亡。


## 功能概覽

- 以 Seed 生成世界地圖，可調整尺寸與世界風格；預設每次啟動抽取新 Seed，風格由 Seed 穩定抽選。
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
├─ notes/                # 保留的版本說明文件
├─ CHANGELOG.md           # 歷代版本重點索引
├─ README.md              # 專案介紹與執行方式
├─ requirements.txt       # Python 套件清單
└─ .gitignore             # 排除存檔、快取與暫存資料
```

### `current/` 模組

| 檔案 | 用途 |
| --- | --- |
| `亂世演算_征佔紀元_VX_啟動.py` | 啟動遊戲介面 |
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
python "亂世演算_征佔紀元_VX_啟動.py"
```

Windows 也可在 `current/` 內執行 `啟動遊戲.bat`。一般請由啟動檔開啟，不要直接執行 `war_engine.py`。

## 基本操作

- 用滑鼠拖曳平移地圖，滾輪縮放；點選格子或國家可查看資料。
- 從介面控制模擬暫停、逐年／逐批推進及執行速度。
- 左側查看選定國家的狀態、領土、人口、軍隊、資源、建築與殖民地；排名可切換查詢對象。
- 事件區可查看國家歷史與戰鬥紀錄；殖民地或歷史地名可用介面提供的連結定位地圖。

## 參數與世界生成

`current/map_config.py` 集中放置地圖與模擬參數。常見設定包括：

- `MAP_WIDTH`、`MAP_HEIGHT`、`MAP_CELL_SIZE_KM`、`MAP_SEED`、`WORLD_STYLE`：地圖尺寸、每格公里數、Seed 與世界風格。
- `COUNTRY_COUNT`：開局國家數量。
- `INITIAL_TERRITORY_RADIUS`、`INITIAL_TERRITORY_MAX_CELLS`：新國家初始核心領土。
- `EXPANSION_*`、`BUILDING_*`：拓荒與建築節奏及成本。
- `COLONY_*`：殖民條件、成本、殖民港與獨立設定。
- `NAVAL_*`、`AI_NAVAL_TARGET_BONUS`：海上作戰與規則 AI 目標評估。
- `AI_RL_NAVAL_ACTION_BIAS`、`AI_RL_COLONY_ACTION_BIAS`：SARSA 模式中新海上攻擊與殖民行動的初始偏好。
- `COLONY_COOLDOWN_YEARS`、`COLONY_MAX_PER_COUNTRY`：所有 AI 模式共用的殖民冷卻（80 年）與每國殖民地上限（6 個）。
- `PORTS_PER_COUNTRY`、`FLEET_*`：初始港口數、艦隊容量、補充批次與成本。
- `BATTLE_*`、`BARRACKS_*_BONUS`：戰場隨機波動、區域守軍與兵營防守參數。
- `COUNTRY_NAME_FONT_SIZE`、`COUNTRY_NAME_FONT_BOLD`、`COUNTRY_NAME_OUTLINE_WIDTH`：地圖國名樣式。

預設地圖為 2000×2000 格，對記憶體與運算能力需求較高。初次測試或效能有限時，可先降低 `MAP_WIDTH`、`MAP_HEIGHT` 再啟動。

> **航線顯示：** 船隊仍依每年 10 公里的速度逐年航行，畫面不再逐年重繪船隻位置。出航時地圖繪製靜態航線，各國事件紀錄會列出預計抵達年份與目的海岸；實際殖民地仍要等航程完成後才建立。

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

每維四個級距，狀態最多 4 維、256 種組合。SARSA 模式可選行動包括：

- `PASS`：暫不發動一般戰爭。
- `ATTACK:<國家ID>:land/naval`：攻擊符合現有合法目標條件、戰力比至少 0.85 的國家，允許承擔適度劣勢。海上行動還需要有效航線、港口、艦隊與可出征兵力；新的 naval 行動有持續選擇偏置，即使既有 Q table 已有該行動紀錄也會生效。
- `COLONIZE`：只有港口、最低艦隊、糧食、木材及可用海外沿岸地都符合條件時才加入行動清單；RULE 與 SARSA 模式都必須距離上次殖民至少 80 年，且每國最多 6 個殖民地。AI 選擇殖民後，船隊沿可通行海面航線逐年航行，每年 10 公里；抵達前不建立殖民地。路線與航程進度會保存並在載入後接續，各國日誌記錄預計抵達年份。

這個模式只讓 Q table 決定一般戰爭、海上遠征和是否殖民；經濟、建築、陸上拓荒及反霸權圍剿仍依既有規則運作。`AI_MODE = "RULE"` 仍是預設，保留既有規則 AI 與原殖民檢查。

各國大腦仍然獨立，分裂新國使用空白 Q table。Q table 只寫入／讀取 `current/saves/war_state_rl_brains.json`，戰局 JSON 不再寫入或讀取 V9 的內嵌 `rl_brains`。V9 只有內嵌 Q table 的舊存檔會建立空白大腦；有相符獨立 JSON 的 V10 戰局可續用。

在 `current/` 目錄執行回歸測試：

```bat
python -m unittest discover -s tests -v
```

## 存檔與重開新世界

程式會在 `current/saves/` 建立執行資料，例如地圖資料、預覽圖、世界資訊、戰局存檔及 `war_state_rl_brains.json`。請定期備份此資料夾。若要重新生成全新世界，先關閉遊戲，再將 `current/saves/` 移出或清空後重新啟動；這會一併移除目前的世界和戰局進度。

`saves/`、Python 快取及暫存檔不屬於原始碼，已由 `.gitignore` 排除，不應提交到 GitHub。

## 版本資料

- [CHANGELOG.md](CHANGELOG.md)：快速查閱各期版本重點。
- `notes/`：本次保留的版本說明文件。
執行最新版請使用 `current/`。

## 開發與測試範圍

版本說明中的長期模擬與功能測試，是各版本說明所記錄的結果；不代表每次上傳 GitHub 前都重新執行過相同測試。若修改戰爭、人口或存檔邏輯，建議固定 Seed，並檢查資源非負、存檔重載與 GUI 操作。
