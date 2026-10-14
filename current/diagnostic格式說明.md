# V25_1 補充

續接檔改用 diagnostic_state.json.gz；原 JSON 相容讀取與保留，公開 JSONL/CSV 可照常閱讀。檔案鎖住時，每檔分別處理並等待下次批次重試，匯出 ZIP 使用最新記憶體資料。

CSV 新增 diagnostic_flush_ms、simulation_with_diagnostics_ms、total_recorded_ms；寫入中的快照不會預知自己的完整耗時，下一份快照或匯出才包含它。舊版缺少的逐年 I/O 不補造。詳見本次更新與效能驗證文件。

# V25 診斷格式與操作說明

此版本只新增觀察與匯出。AI、戰爭參數、候選排序、RNG、Q-table schema、存檔欄位，以及 WorldStateCache／StrategicSnapshot 的原運算維持原版。Logger 不查詢新的 AI 方案，不抽取亂數。遊戲版本為 V25；舊存檔的 V24 schema 標記仍沿用，以保持相容。

## 安裝與使用

關閉遊戲，備份程式與 saves。將本包解壓到新資料夾，把自己的 saves 複製進去，照原方式執行「啟動遊戲.bat」或「啟動遊戲.py」。本包不夾帶推進後的 saves。

`map_config.py` 新增設定預設全部關閉。總開關 False 或 detail level 0 時不建立 logger、不建立紀錄 buffer、不寫診斷檔案，也不進行診斷地圖掃描。必須重新啟動遊戲，設定才會套用。

### 長期觀察速度與快取

```python
ENABLE_DIAGNOSTIC_LOG = True
DIAGNOSTIC_DETAIL_LEVEL = 1
ENABLE_PERFORMANCE_LOG = True
ENABLE_CACHE_DIAGNOSTIC_LOG = True
```

其餘類別維持 False。這是最輕的長期模式；沒有完整決策及領土追蹤。實測成本見「LOG開關效能測試.md」。

### 長期觀察戰局停滯

在上一組設定上增加：

```python
ENABLE_STAGNATION_LOG = True
ENABLE_WAR_DIAGNOSTIC_LOG = True
ENABLE_LOGISTICS_DIAGNOSTIC_LOG = True
```

level 1 記錄歷史、戰果、物流與彙整，不保留完整 RL/candidate trace。未觀察到的限制會標示 UNKNOWN。每 100 年分析一次；國家停滯須累積至少 200 年資料，世界停滯須至少 500 年。新開 LOG 無法補造以前的決策。

### 卡住時開完整診斷

```python
ENABLE_DIAGNOSTIC_LOG = True
DIAGNOSTIC_DETAIL_LEVEL = 2
ENABLE_AI_DECISION_LOG = True
ENABLE_STAGNATION_LOG = True
ENABLE_PERFORMANCE_LOG = True
ENABLE_WAR_DIAGNOSTIC_LOG = True
ENABLE_LOGISTICS_DIAGNOSTIC_LOG = True
ENABLE_CACHE_DIAGNOSTIC_LOG = True
```

完整模式適合重現問題的期間。每次真正 strategic decision 都有唯一 ID，並記錄原演算法實際篩選過程。未重新挑選目標的年分，不會另造一份候選分析。

## 匯出分析包

GUI 上方新增「匯出診斷包」。也可以呼叫：

```python
engine.export_diagnostic_package('diagnostic_package.zip')
```

不開 GUI 的操作：

```text
python diagnostic_headless.py --save saves --years 100 --level 2 --output diagnostics_run
```

此指令只在記憶體中接續，保持來源 saves 不變，輸出 diagnostics_run_package.zip。level 0 關閉、1 摘要、2 完整。診斷未啟用時，匯出會提示先開啟設定，不會補造歷史。

請交給 AI：**diagnostic_package.zip + 同年份完整 saves + 此次程式版本 ZIP + 重現步驟／關注國家與年份**。saves 必須包含 world_map、war_state 和 war_state_rl_brains 對應檔案；不要只傳圖片或畫面事件 LOG。

## 檔案

| 檔案 | 內容 |
|---|---|
| game_metadata.json | V25、年份、Seed、尺寸、國家數、設定、Q/schema、觀察起點及截斷／錯誤 |
| ai_decisions.jsonl | 最近 100 年的完整決策與延遲 reward；每筆為一個 JSON 物件 |
| macro_events.jsonl | COMMIT、PHASE、CONTINUED、PROGRESSED、STALLED、COMPLETE、ABORT、SWITCHED |
| war_outcomes.jsonl | 戰役開始、結算、20／50 年戰果保有量、行動後國家變化 |
| territory_events.jsonl | 原函式範圍內的領土取得／損失、飛地清理、可證明的走廊切斷 |
| logistics_events.jsonl | 原 manifest 數值、兵源瀑布、出航、抵達／返鄉及實際交付 |
| stagnation_summary.json | 最近一次各國 100 年比較、200 年停滯、blocker 證據與世界停滯 |
| stagnation_events.jsonl | STAGNATION DETECTED 明細 |
| stagnation_intervals.jsonl | 每 100 年的彙整歷史 |
| performance_recent_1000y.csv | 最近 1000 年模擬與 UI 時間、exclusive phase 時間、次數、當年事件 |
| performance_summary.json | 當前視窗平均／中位／p95／最大值、phase 占比、次數及記憶體健康 |
| performance_intervals.jsonl | 每滿 1000 年的彙整歷史 |
| slow_years.json | 視窗內最慢的前 30 年，含分階段時間、次數、事件 |
| cache_summary.json | hit、miss、rebuild、invalidate、entries 及命中率 |
| logistics_summary.json | 物流成功率、運兵容量利用率、港口閒置觀察、前線健康 |
| major_events.jsonl | 國家滅亡、島嶼平定、單一存活政權、目標完成、世界停滯 |
| diagnostic_summary.md | 人類可讀摘要與資料完整性提醒 |

`diagnostic_state.json` 是本機續接用 sidecar，不放入分析 ZIP。它不寫入遊戲存檔。當同一診斷資料夾內 sidecar 的 Seed、地圖尺寸與年分和載入存檔相符，歷史會續接；不同則建立新觀察歷史並留下提醒。請不要混用不同存檔的 diagnostics 資料夾。恢復 sidecar 不會修改遊戲狀態。

## 決策 schema

共同欄位為 `schema_version`、`session_id`、`year`、`event`、`country_id`。完整決策另有：

- `decision_id`：session UUID + 單調序號；重開後仍不會撞 ID。
- `country_before`、`resource_snapshot`：人口、兵力、艦隊、糧食、疲勞及原本 snapshot 已產生的本土可抽調兵力。
- `world_goal`、`macro_goal`、`macro_target`、`strategic_phase`、`strategic_commitment`、`commitment_age`、`progress`。
- `selection`：原 RL state、合法動作、Q、bias、effective scores、epsilon、實際探索／利用結果、平手候選索引。
- `selection_source`：RL_EXPLORE、RL_EXPLOIT、MACRO_COMMITMENT 或 RULE。當只有一個 Macro binding 時，source 為 MACRO_COMMITMENT，sampling_source 仍記錄原 RL 抽樣分支；不取消 RNG 呼叫。
- `evaluations`、`legal_target_queries`、`objective_queries`：實際執行的 selector／preflight 的既有數值與排除條件。
- `pre_prerequisite_bindings`、`filtered_actions`：哪些動作本可選，後來被首港或補給前置規則拿掉；其他排除若沒有單一明確原因，標示 MACRO_BINDING_FILTER，詳細條件在 evaluations。
- `chosen_action`、`executed_action`、`success`、`next_decision_year`：策略動作到原子動作的對應和結果。

候選的 `final_score` 直接來自原 tuple，score_formula 記載原式；沒有單一 score 的本島／戰區選擇，記錄 actual defense ordering、comparison values 和目標承諾。不把排序改成新評分。沒有正式勝率模型，所以 `estimated_win_probability = null`。RULE 隨機項若未獨立保存，會標示未單獨測量，不從 final score 猜算。

延遲 reward 屬於**前一次** decision_id。Action effectiveness 的即時 success 表示執行成功，不代表戰爭勝利。平均 reward 統計原有 strategic reward，戰術回饋及物流補充 credit 不和它混為同一平均。

## 戰果與領土定義

- gross：實際所有權變更，包含同年取得後又失去的格數；巢狀接點不重複計數。
- net：視窗起終國家領土差值；和平拓荒等同時行為也可能影響 net，不能當作某一 action 的純因果效應。
- 戰役 captured indices：實際在該 battle scope 改為勝方所有的格子。
- durable_gain_after_20/50_years：結算後周年當下仍為該國所有的攻佔格子；中間失去又奪回，可從 territory events 分辨。尚未到周年為 null。
- 國家 durable_cells_20：觀察期間新得、連續持有至少 20 年的格數；無法補計開 LOG 前的取得年分。
- territory_lost：該國在戰役觀察起點至結束期間的實際 gross loss，不假定每筆損失全由該戰役造成。
- 聯軍守方傷亡是共同戰鬥數值，不能把每筆列出的敵方死亡加總；record 有 shared_battle 與 attribution 說明。
- food_consumed：原 campaign 更新實際扣掉的國家糧食，包括付不起整年供給而歸零的剩餘糧食。首年以前或舊存檔既有 campaign 的先前消耗不明，明確標示。

走廊切斷只在刪除／攻佔格子後，該島剩餘領土的原版 **四鄰接、水平不環繞**連通分量增加時記錄。這是具體拓樸證據，不推測對方戰術意圖。既有 cleanup 函式造成的 loss 可歸因於飛地清理。每 100 年完整模式採樣島內分量、最大分量、首都／港口連通、前線寬度與當地兵力。

`effective_front_cell_army` 是位於鄰接敵方格子的士兵，和原演算法可從全島抽調的攻擊兵力不同；定義寫在 record，不能因此斷言內陸兵力無法作戰。島內其他政權數也不等於全球外交敵國數。

## Blocker 與訊號

每項 blocker 都附 evidence。分類語彙包含 TXT 所列 NO_LEGAL_TARGET、NO_VIABLE_TARGET、TARGET_TOO_STRONG、運輸／兵源／糧食／港口限制、復原與禁征、聯盟、目標循環、低效戰果、飛地與走廊等。沒有足夠 evidence 就用 UNKNOWN。

Q_PREFERS_IDLE／DEFENSE 必須真的有合法進攻候選，而且所選動作 effective score 嚴格高於進攻，不能把 epsilon 探索或 Q 平手抽樣說成 Q 偏好。LOW_DECISION_ENTROPY、UNDERPERFORMING_MAJOR_POWER、GLOBAL_STALEMATE、重複戰敗與目標 A/B/A/B 是觀察訊號，不會反過來改 AI。

## 效能與快取

計時沿原 call chain 分為 population_economy、buildings、territory_expansion、AI_decisions、war_campaigns、battle、overseas_theatres、reinforcement／colony voyages、connectivity／splits、geography、world_totals、pathfinding、sea_route_A_star、brains／RL／monarchs、diagnostics 與 other。

巢狀計時扣除子階段，模擬占比不重複加總。UI 的 raster render、canvas redraw、ranking/log panels、map snapshot、autosave 另列，UI 不算入 simulation_ms。UI 年份歸屬目前顯示的模擬年。批次磁碟 flush 的 session I/O 時間另列；實測 ON/OFF 的總執行秒數包含自動 flush，所以兩者成本都看得到。手動匯出時間不計進 100 年 simulation runtime。

counts 記錄原 `_sea_route` 呼叫、真正 A* 搜尋與節點展開、route cache hit/miss、地理重建、模擬中的 ndimage.label、已接點的 full world scan／spatial rebuild、原 AI 決策、target evaluation 接點、campaign、reinforcement checks、save、UI refresh、render。不要把未接點的生成期 NumPy 操作理解成完整 CPU 指令追蹤。

快取 aggregate 涵蓋 WorldStateCache、StrategicSnapshot memo、spatial indices、sea route、colony context、territory revision。未知全域 invalidation 原因以 unknown_global_reason 留下，不臆測。RSS 在可用 psutil 或 Linux /proc 時記錄；Windows 未安裝 psutil 時可以為 null，遊戲仍可執行。

## 保留期限與容量

AI 明細 100 年；其他明細與效能 1000 年；批次 flush 20 年。輪替會重寫檔案，硬碟上也不會留下被淘汰的舊 JSONL 行。每 100／1000 年 summaries 保留到 2000 個視窗；重大摘要上限 10000 筆。

每類 event stream 預設最多 100000 筆及約 64 MiB 序列化內容，durable cell references 預設最多 1000000。觸及上限會在 dropped_records 標示；戰果追蹤截斷時 durable 值為 null，絕不把不完整資料當成完整戰果。序列化大小不是 process RSS 的精確大小，RSS 另列。

僅觀察到結構持續長大，會標示 GROWING_REVIEW_REQUIRED；`unused_history_confirmed = false`，不自行刪除遊戲資料或武斷認為它沒有用途。

## 驗證與範例

「diagnostic範例」是同一真实 saves 推進 100 年的輸出，並附 ZIP。未滿 200／500 年的範例不會偽造停滯事件。44 項測試包含原有 27 項；新增完整一致性、輪替、決策／RNG、sidecar、Q 平手、走廊／durable、世界停滯等。100 年完整狀態及耗時見驗證文件。


## 重現 100 年比較

以下指令在程式資料夾執行。baseline 的第三個參數是未修改原版程式資料夾，不能拿 V25 自己當原版：

```text
python verify_diagnostics_100y.py baseline saves ../原版程式
python verify_diagnostics_100y.py off saves
python verify_diagnostics_100y.py light saves
python verify_diagnostics_100y.py summary saves
python verify_diagnostics_100y.py on saves
```

會輸出 benchmark_MODE.json，內含耗時、各欄位 SHA256、combined_state_sha256、來源 saves 未變更的檢查。不同模式的 fields 必須全部一致；同一環境測一次的耗時不等於穩定平均，若要細比較速度，請交錯重複測量後看中位數。
