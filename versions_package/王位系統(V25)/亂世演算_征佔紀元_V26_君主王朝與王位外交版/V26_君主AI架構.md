# V26 君主 AI 架構

WORLD_UNIFICATION → 治世志向 → Macro Goal → Campaign → Tactical／RL。

`king_system.py` 是唯一人物登錄表：RoyalPerson／KingProfile、DynastyProfile、ReignAmbition、KingMemory、RegencyState、Claim、RoyalMarriage、PersonalUnion、SuccessionWar。每國保存 monarch_id／king_id；同一人統治兩國時，兩個 ID 都解析到同一 KingProfile，人物不複製。

同一君主的 `reigns[str(country_id)]` 分別保存各王位登基年、任次、治世目標與功過。年齡由 birth_year 及世界年份推導。共享人格、能力、私人人際與生命週期；保留各國不同資源、軍隊與地方目標。

| 原系統 | 接入方式 |
|---|---|
| WarEngine 初始化／換王 | 建立登錄表；登基、死亡、失都換王及分裂新王統統一處理 |
| Hierarchical Strategy | 只排序原可行候選、加入小幅 action bias；不擴張 RL 狀態維度 |
| Overseas Strategy | 在原兵力估算上加入小幅風險倍率 |
| Campaign | 增加 war_goal、claimant_id、dynastic_war_id，舊戰役預設領土戰 |
| Battle | 共用行軍、消耗、戰鬥與傷亡；政治戰的結果分支略過領土攻佔與滅國 |
| Save／Load | 新版王室 payload＋各亂數狀態，NPZ 保存 initial_territory，載入地圖後清除初始化所有權快取 |
| Diagnostics | major_events 記錄政治因果；完整 AI trace 才寫逐目標評分拆解 |
| MapViewer | 現有國家資訊表格增加王室資料列與最近五任摘要 |

王國、聯盟、國家關係、王朝關係、王室婚姻與共主分開管理。共主形成後在既有出兵前過濾內部戰爭及對成員盟友的矛盾命令；行軍途中形成共主的舊命令也會取消，原有存活兵力歸建。

能力不進入攻防傷害公式。所有修正均在可行性與生存條件之後使用；單一合法動作不會因國王偏好而變出其他動作。
