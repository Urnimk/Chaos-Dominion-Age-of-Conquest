# V24 WorldStateCache 與 dirty invalidation

## 真實資料與快取邊界

`world.territory`、`world.continent`、`local_population`、`local_soldiers` 仍是權威資料。`WorldStateCache` 不保存進存檔；每個摘要都可由權威陣列重建。這個版本只 cache profiler 證明重複且穩定的領土統計，沒有為人口／兵力另造容易失同步的永久總計。

## 快取的項目

| Cache | Key | 值 | 失效條件 |
|---|---|---|---|
| 陸塊所有權統計 | landmass ID | 陸格數、各國格數、正領土國家集合 | 該陸塊領土有變化 |
| 國家控制陸塊 | country ID | 該國目前持有的陸塊集合 | 該國領土有變化 |
| `_spatial_indices` | country ID × landmass ID | territory array 的扁平索引 | 該國在該陸塊領土有變化 |
| `_spatial_indices` 全國索引 | country ID × None | 該國全域索引 | 該國任何領土改變 |
| 海路 | 起點港 × 目標岸格 × navigation epoch | 相同 A* 回傳路徑／無路 | 航海 epoch 改變；LRU 容量 4096 |

## Decision-scoped StrategicSnapshot

每個到期 AI 戰略決策建立一個 `StrategicSnapshot`，共享該國 home landmass、home population／soldiers、available home soldiers、controlled landmasses、海外據點、fleet、ports、war exhaustion 及 active campaigns。`legal_targets`、Macro Measure 和 theatre 查詢只在同一次決策內 memoize。決策 state/actions 建構完成即清除 snapshot；執行 action 前它已不存在。Snapshot 不含 RNG，不寫入存檔，故不會把港口、外交或資源變更跨決策緩存。

20 年 profile 中共建立 22 個 snapshots，`_legal_targets_uncached` 由 41 次降為 26 次，`_macro_measure_uncached` 由 82 次降為 59 次。海路搜尋仍是主成本，snapshot 本身沒有明顯改變全局 wall-clock。

## Dirty 事件

`_mark_world_changed(..., landmass_ids=...)` 同時維持舊有全域 epoch（供其他 V23.2 cache 使用），並增加國家／國家×陸塊 epoch。已盤點的領土清除、殖民、拓荒、分裂、攻佔及撤退路徑都傳入受影響陸塊。相鄰陸塊及其他國家的 spatial index 不會失效。未知範圍的未來呼叫若省略 `landmass_ids`，採安全的全域 fallback 清除。

Sea route 只依賴目前不可變的 terrain/water 與端點；港口效度由呼叫端驗證，港口失守不會讓船隊沿著失效港口出發。`navigation_epoch` 預設為 0，為將來若實作會改變航行地形時提供明確 cache key。LRU 只移除快取項目，重算仍走同一 A*，路徑及遊戲規則不變。

## Debug consistency

`WorldStateCache.debug_assert_consistent()` 會用全掃描重算目前已建立的統計並逐項 assert。測試 `test_world_state_cache.py` 驗證完整掃描與 selective invalidation；`headless_sanity.py --cache-assert-every N` 可選擇每 N 年全掃描。正式 benchmark 預設 0，不逐年付出驗證成本。

## 保留給第二階段

- Population/soldiers incremental totals：目前 profiler 時間占比低；人口、招募、傷兵、撤退與海運多處直接寫 array，須先集中 mutation API 才能低風險維護。
- 跨年份永久 StrategicSnapshot/legal-target cache：目前只在一次 decision cycle 內 memoize；若未來要跨決策保留，需先定義外交、港口、艦隊、資源與戰役的完整 revision key。
- `_build_geography` 局部更新、connected-component dirty flags：這個 20 年窗口只有 4 次 geography build、約 0.15 秒；目前重寫風險高於收益。
- Numba：A* 的 Python tight loop 是剩餘最大熱點，可列為第二階段原型；需在路徑序列完全相同的 route fixtures 與 100 年完整等價測試通過後才納入。
