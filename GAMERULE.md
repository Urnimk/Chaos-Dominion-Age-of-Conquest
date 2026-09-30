# 《亂世演算・征佔紀元 V19》新人完整遊戲說明

> 本說明依據 V19「地球地圖與海外撤退規則版」程式撰寫，包含目前實際執行的規則與參數。若日後程式碼更新，請以新版程式為準。
>
> 主要程式：`map_viewer.py`（視窗與操作）、`map_config.py`（大部分遊戲參數）、`map_generator.py`／`country_generator.py`（生成世界）、`war_engine.py`（經濟、AI、戰爭與領土）、`rl_brain.py`（AI 學習）。

## 1. 這是什麼遊戲？

《亂世演算》會在程序生成的世界中建立多個國家，模擬人口、糧食、木材、礦產、兵力、艦隊、領土拓荒、AI決策、戰爭、海外殖民、國家分裂與滅亡。玩家主要觀察世界演化，也可以暫停、單步推進、選擇地圖風格、存讀戰局和查詢國家。

遊戲的時間單位是「年」：引擎每次 `step(1)` 推進一年。V19目前的實際速度參數是 `SECONDS_PER_YEAR = 0.5`，也就是正常自動推進約每半秒一年；UI另外分批計算與刷新，電腦負荷會影響實際速度。這與部分舊註解提到的「每年兩秒」不同，修改時應以 `map_config.py` 的數值為準。

## 2. 啟動與基本操作

Windows 建議使用 Python 3.10 以上版本。第一次執行前，在遊戲資料夾開啟終端機並執行：

```bash
pip install -r requirements.txt
```

目前外部套件需求為 `numpy`、`pillow`、`scipy`。安裝完成後使用 `啟動遊戲.bat` 或 V19 啟動程式。首次啟動會嘗試讀取最後存檔；找不到可用存檔時會生成新世界。預設自動運行 (`AUTO_RUN_ON_START = True`)。

上方工具列：

- **Seed**：輸入世界種子。相同地圖大小、風格、Seed可重現相同地形生成結果。
- **地形風格**：選擇隨機、均衡、超級大陸、群島、破碎大陸、內海、雙大陸或地球地圖。
- **寬×高**：地球地圖限制為 1200–2000 格；其他風格由 `MapSettings` 限制為 128–8000 格。
- **新世界**：按目前 Seed、風格與尺寸重新生成世界，會開始一場新的模擬。
- **隨機Seed**：換成新的隨機種子。
- **暫停／繼續**：切換自動模擬。
- **推進1年／推進10年**：手動推進指定年數；模擬忙碌時需等候計算完成。
- **儲存戰局／讀取戰局**：保存或讀回目前遊戲狀態。

地圖可用滑鼠滾輪縮放、按住拖曳平移；地圖上方的控制可切換顯示圖層／地名。左、右主區與右側地圖／下方資訊區的分隔線可拖曳調整。國家查詢中的國家名稱、海外據點名稱可點擊定位到地圖。

## 3. 介面分區

左側有四個分頁：

1. **國家總覽**：國名、土地、人口、士兵、艦隊、聯盟與戰績。點欄位標題可排序；點國家可在地圖定位。
2. **聯盟總覽**：顯示存檔中已有的聯盟資料。注意：目前新開局各國聯盟值為 0，程式有聯盟援軍與圍剿聯軍處理，但沒有一般外交流程主動建立常設聯盟，所以空白或很少聯盟是目前程式行為。
3. **國家查詢**：選擇國家查看基本狀態、人口／建築／資源、領地資料、當前戰爭、外交／戰績及事件。領地資料列在上方兩個資訊表下方，橫跨整個左側欄，預設約三行高度，資料較多時可捲動。它包含本島與有效海外領地，顯示類型、地名、格數、建立年份、島上人口與兵力估算；不顯示座標。點海外地名可定位地圖。
4. **歷史事件**：查看政權、戰役、殖民、後撤等重大歷史。一般即時事件LOG和每國事件LOG會更詳細。

右側上方是世界地圖；下方有即時排名與即時事件LOG。國力排名顯示分數與士兵、艦隊、土地等資訊；當前綜合分數權重由 `map_viewer.py` 的 `RANK_*_WEIGHT` 控制，預設士兵×1、艦隊×1、土地×3（若希望改排名公式，調整這三個權重）。

## 4. 世界與地圖生成

### 4.1 地圖風格

- `BALANCED` 均衡世界
- `SUPERCONTINENT` 超級大陸
- `ARCHIPELAGO` 群島世界
- `FRACTURED` 破碎大陸
- `INLAND_SEAS` 內海世界
- `TWIN_CONTINENTS` 雙大陸世界
- `EARTH_MAP` 地球地圖：依經緯度輪廓繪製主要陸塊，較小島嶼簡化；台灣以獨立多邊形繪入，並切開台灣海峽以保持島嶼分離。地球地圖支援 1200×1200 至 2000×2000。
- `RANDOM` 隨機風格：由 Seed 決定抽到的風格。

一般地圖使用多尺度雜訊、海岸細節、板塊與山脈參數生成陸海；地球地圖主要使用固定輪廓遮罩，因此調一般地圖的雜訊參數不會改變地球陸塊輪廓。地形、氣候、可耕性、木材、礦產、淡水、城市價值、防禦價值與移動成本會再由環境與宜居度生成器計算。

地圖水平方向採環繞距離，東西地圖邊緣相接；南北方向不環繞。因此距離、邊界、行軍與海路計算會考慮左右邊界相接。

### 4.2 開局國家與領土

預設 `COUNTRY_COUNT = 16`。首都會挑在適合居住的大型陸塊，國家初始領土是首都周圍半徑 `INITIAL_TERRITORY_RADIUS` 內的可用陸地，最多 `INITIAL_TERRITORY_MAX_CELLS` 格；其餘空地留給後續陸上拓荒或海外擴張。

開局人口按每格城市價值估算，並有最低值；士兵約為人口的 `INITIAL_SOLDIER_RATIO`，至少 20 人且不超過人口。開局資源依領土上的產能一次給予若干倍數。開局會在合適海岸自動建港（最多 `PORTS_PER_COUNTRY` 座）；初始艦隊按每港 `INITIAL_FLEET_PER_PORT` 計算。城市、兵營、拓荒站不是開局固定配置，而由後續建築週期建立。

## 5. 每年如何推進

每推進一年，主要順序如下：

1. 年份加一，清除已結束的即時警報。
2. 檢查年滿門檻的微型島嶼清理。
3. 結算人口、糧食、木材、礦產、徵兵、士氣與疲乏。
4. 在每 10 年檢查建築；每 3 年檢查陸上拓荒。
5. 更新AI學習狀態、國王任期與AI戰爭決策。
6. 推進戰役行軍／補給，抵達時結算戰鬥。
7. 推進殖民或後撤船隊航程。
8. 每 100 年檢查領土分裂與沒有海外首都的飛地；另檢查強國分裂及殖民地獨立。

自動模擬的每秒速度與畫面刷新分開設定；大量國家、大地圖、戰爭和重繪會影響實際FPS與模擬年速。

## 6. 人口、資源與成長

### 6.1 生產與承載人口

每個已擁有的可生產土地格提供基礎糧食、木材、礦產產出；產出值取決於地圖生成時的農業、木材、礦產數值。領土一經歸屬某國，該格的產能就計入該國。

年度糧食產量大致為：

```text
土地糧食產能 × FOOD_PRODUCTION_MULTIPLIER × (1 + 城市生產加成)
城市生產加成 = min(城市數 × CITY_FOOD_PRODUCTIVITY_BONUS,
                     MAX_CITY_FOOD_PRODUCTIVITY_BONUS)
糧食承載人口 = 年糧食產量 ÷ FOOD_CONSUMPTION_PER_PERSON
```

城市提升糧食生產效率，最高受 `MAX_CITY_FOOD_PRODUCTIVITY_BONUS` 限制。糧食不足時人口成長受限；糧食存量跌為負數時會造成額外人口損失與士氣下降。

### 6.2 人口與徵兵加成

V19的糧食承載量加成：

```text
加成倍率 = 糧食承載人口 ÷ FOOD_CAPACITY_BONUS_PER_PERSON
人口成長與基礎徵兵量均乘上 (1 + 加成倍率)
```

預設 `FOOD_CAPACITY_BONUS_PER_PERSON = 100000`，承載人口 100,000 提供 +100%，也就是相同基礎增長下變為兩倍；承載人口 50,000 則提供 +50%。人口實際成長仍受可用糧食承載空間限制。休養生息期會再套用較高出生倍率與徵兵倍率。

士兵目標約為人口的 18%；人口成長、徵兵速度、戰爭疲乏和後期減速都會影響實際兵力。第 1000 年後開始逐步降低徵兵倍率，第 5000 年降到設定最低值。

### 6.3 資源用途

- **糧食**：人口消耗；陸上拓荒、建築、殖民與戰役補給需要糧食。
- **木材**：陸上拓荒、建築與殖民需要木材。
- **礦產**：城市、兵營、拓荒站、港口與造艦需要礦產。
- **艦隊**：海上遠征、海外殖民和海戰能力。港口提供艦隊上限；沒有港口不能執行出海登陸。

## 7. 建築規則

建築每 `BUILDING_CHECK_INTERVAL_YEARS` 年檢查一次，預設每 10 年；一次最多建一棟。候選位置必須是本國未被建築占用的領土格。

### 7.1 城市

目標數量為 `領土格數 // CITY_AREA_PER_BUILDING`，預設每 180 格增加一座目標城市；土地不足 180 格時城市目標為 0。位置挑城市價值較高的空地，且距首都／城市至少 `CITY_MIN_DISTANCE`（預設 60 格）。每座城市提高糧食生產加成，也增加拓荒量。

### 7.2 兵營

目標數量為 `max(1, 領土格數 // BARRACKS_AREA_PER_BUILDING)`，預設每 130 格增加一座目標兵營，至少希望有一座。會選防禦價值較高的空地，兵營間距不得小於 `BARRACKS_MIN_DISTANCE`（預設 20 格）。戰區附近兵營會提高當地可集結守軍比例；每座還會提高陸上拓荒量。

### 7.3 拓荒站

目標數量為 `max(1, 領土格數 // OUTPOST_AREA_PER_BUILDING)`，預設每 90 格增加一座目標拓荒站，至少一座。若有靠近中立空地的己方格，優先從前線候選中挑防禦價值較高的位置；否則從其他空地挑。拓荒站增加拓荒格數和所在位置的防禦力。

### 7.4 港口與艦隊

港口只能在己方海岸空格建造，會挑城市價值較高的位置。每國港口上限預設 2 座，建港後增加初始艦隊。港口已達上限但艦隊低於容量時，建築檢查會優先花資源補充艦隊，每次增加 `FLEET_BUILD_BATCH` 艘。

建造決策順序：先嘗試缺少的港口；若港口不用補，則先補艦隊；再按城市、兵營、拓荒站順序找第一種「未達目標且付得起」的建築。某種建築付不起時會繼續找下一種可付的建築。即使目標數不足，沒有可用空格／間隔位置也會跳過。

| 建築 | 糧食 | 木材 | 礦產 |
|---|---:|---:|---:|
| 城市 | 80 | 120 | 45 |
| 兵營 | 55 | 75 | 90 |
| 拓荒站 | 35 | 55 | 25 |
| 港口 | 60 | 130 | 70 |
| 艦隊補充（每批） | 12 | 30 | 18 |

> **注意：拓荒站不是海外殖民站。** 拓荒站提高陸上相鄰空地拓展能力；海外殖民是由港口出發、要符合艦隊／資源／名額等條件的另一個系統。

## 8. 陸上拓荒

每 3 年進行一次。國家只會向四方向相鄰的中立可通行陸地拓展，不會隔空認領空地。每次拓荒格數會受以下最小值限制：

- 可拓荒空格數及本國剩餘容量；
- 基本拓荒量 `BASE_EXPANSION_CELLS`，加城市、兵營、拓荒站提供的拓荒加成；
- 可支付的糧食與木材；
- 可移動的移民人口。

拓荒的上限容量為 `INITIAL_TERRITORY_MAX_CELLS + 士兵數 × EXPANSION_CELLS_PER_SOLDIER`。每新增一格需要糧食與木材，並從原領土搬出設定數量的移民；不會憑空創造人口。候選格依城市價值、農業、淡水與移動成本排序，偏好較宜居位置。

## 9. AI與學習

預設 `AI_MODE = "SARSA_LAMBDA"`。每個國家有自己的 Expected SARSA(λ) 國家層級Q表，另有戰術攻防Q表；分裂成立的新國家也建立獨立AI大腦。主要動作包括：

- `PASS`：本次不採取外交／戰爭動作。
- `REST_AND_REPRODUCE`：進入休養期，暫停新戰爭，恢復士氣／戰爭疲乏並提高出生、徵兵倍率。
- `ATTACK:<目標>:land/naval`：發起陸戰或海上遠征。
- `COLONIZE`：若有合法海外候選地，派殖民船隊。

AI狀態由五項離散指標組成：兵力安全、糧食年數、領土占世界比例、戰爭機會、戰爭疲乏。AI依Q值與探索率選擇行動；`AI_RL_EPSILON` 隨決策次數逐步降到 `AI_RL_MIN_EPSILON`。海外殖民與海戰獎勵可用 `OVERSEAS_RL_REWARD_MULTIPLIER` 加權。

每 5 年（`AI_WAR_CHECK_INTERVAL`）進行一次AI戰爭決策。戰爭目標受合法接壤／海路、可用兵力、戰力比、是否在休養期、同時遠征上限等約束。AI會偏好能逐步統一世界的土地較多國家，也會考慮較弱防線。國家不會無限同時派兵，預設同時行軍戰役最多 2 支。

戰術層另外從若干攻擊投入比例或防守駐軍比例中學習，考慮地形、局部守軍、戰區價值、離首都距離及登陸方式。AI不是保證最優；初期Q值接近時探索和隨機數會造成不同選擇。

`AI_MODE = "RULE"` 可切換規則式AI，但其殖民檢查流程和 SARSA 模式不同。調AI參數時注意：某些殖民機率參數在SARSA強制執行所選殖民行動時不會抽機率；請勿只改參數名稱就假設必然影響預設模式。

## 10. 戰爭與戰鬥

### 10.1 可攻擊目標

- **陸戰**：兩國有直接接壤領土即可形成合法陸戰目標。
- **海戰／登陸**：攻方必須有可用港口、海上連線、艦隊至少 301 艘（`OVERSEAS_MIN_FLEET = 301`），且目標符合海外擴張／既有海外戰區規則。依目前 `_objective` 的目標挑選程式，登陸點實際上必須是敵方沿海港口格，再從該處向內推進。設定註解提到可登陸沒有港口的敵方沿岸，但目前目標挑選仍篩選敵方港口；若要允許無港口海岸登陸，需同步修改該篩選邏輯。
- 目標不能是自己或同聯盟國；本國休養期間不發動新戰爭。
- 每國同時最多兩支進攻行軍（`AI_MAX_ACTIVE_CAMPAIGNS`）；保留最低本土守備兵力後才可派兵。

### 10.2 行軍、補給、結算

部隊由本國領土／港口出發，距離除以陸／海行軍速度決定預計抵達年份。行軍每年消耗糧食補給；短缺會削減遠征兵力。海軍攻擊承受兩棲作戰懲罰。

戰鬥勝負比較攻守戰力、士氣、地形防禦、局部兵力和隨機戰況波動。山地、高山、丘陵、河流及城市、首都、兵營、拓荒站會影響防禦。附近兵營和本地人口會提高可投入的局部守軍。

**戰果不會只有「守住、版圖不變」：勝方會取得敗方可達的邊境土地。** 攻方勝則攻方取得領土；守方勝則守方會反推並取得攻方前線／出發方向的土地。每場仍會有雙方傷亡、士氣損失與戰爭疲乏；士兵傷亡也會從人口中扣除。

一般領土捕獲範圍由投入兵力估算並限制在 `CAPTURE_RADIUS_MIN` 至 `CAPTURE_RADIUS_MAX`，但只沿接壤前線逐格擴張；不會空降到遠離邊界的內陸。海上登陸只能從指定灘頭／港口附近、同一陸塊逐格擴張。攻下海外首都時，敗方在該島剩下沒有首都錨點的土地會清空。

若首都失守：先檢查本島城市是否全失；若已無本島城市且有有效海外首都，海外首都會升為國家首都。否則若有足夠城市、土地與人口可推舉新王，會遷都；不足時國家滅亡，剩餘領土變成空地。預設遷都最低門檻為兩座城市、50格領土及80人口。

## 11. 海外征服、殖民與名額

### 11.1 海外名額

海外征服與殖民共用名額規則。除危局後撤外，不符合名額條件不能出海：

1. 本島至少 80% 土地由本國控制，且本島沒有其他國家政權，才取得第一個海外擴張名額。
2. 已持有的海外大陸／大島，必須由本國控制至少 80%，且島上沒有其他國家，才算平定；每平定一塊，增加一個下一階段名額。
3. 所有已持有海外陸塊都須平定，才能再出發找下一塊。正在航行的殖民船或遠征也會先占住預約名額，避免同年超派。
4. 海外遠征次數另有每國終身上限 `OVERSEAS_EXPEDITION_LIMIT`，預設 100；殖民和海戰共用。
5. 可考慮的海外陸塊需達「至少 3000 格」或「達最大陸塊面積 1.5%」的較高門檻，並優先挑最大的三塊。
6. 已有海外領地遭攻擊時，可在該海外戰區出兵平亂，不必等到重新達到 80%；但仍須通過引擎的出海能力檢查。

### 11.2 海外殖民

殖民需要：國家存活、本土統一（危局後撤例外）、港口、至少 301 艘艦隊、足夠殖民糧食與木材、沒有另一支在途殖民船、名額可用、目的地可達且是合格海外大島。新殖民出發有 40 年冷卻。船隊從己方港口沿水域航線實際移動，預設每年航行 10 公里；不會直接空降。

成功抵達後初始最多占 24 格，並建立海外殖民首都／殖民地；預設自動建殖民港。海外地名、人口、領土與兵力會列在國家查詢的領地資料內。殖民地達 1000 年後才開始每 20 年檢查一次低機率獨立。

### 11.3 危局後撤

當本島剩餘本國土地降到「300格」與「開局本島面積25%」兩者中較低門檻以下，國家可把危局後撤當例外，使用一趟原本海外名額外的緊急航行。後撤需要港口、足夠艦隊／船、合格可抵達島嶼；距敵方領土 4 格內的港口視為受威脅，後撤只可由安全港口出發。基礎成功機率 42%，艦隊與安全港可提高，港口都受威脅會降低，最後限制在 10%–62%。在預設 SARSA 模式中若AI選定可行後撤，程式會以強制選擇方式執行，不套用一般隨機成功率抽選。

船隊抵達後搬運當時人口的 80%，將首都遷到小島作為後撤基地；原本本島的領土、人口與建築清除。後撤基地屬於有首都繼承權的領地。若危局在船隊抵達前解除，後撤航行會取消並返還遠征物資。

## 12. 分裂、飛地清理與滅國

- **小型本土分裂碎片**：每 100 年檢查領土連通狀態。分裂形成後，位於首都同一陸塊、但不含首都的本土小塊若小於該國分裂前土地的三分之一，會清為空地；島嶼海岸或窄海隔開不會自動讓這種小本土飛地豁免。已登記殖民地與不同海外陸塊依海外首都規則處理。
- **正式政權分裂**：需有足夠大且長期分離的多塊本土領土；斷裂至少 20 年，區塊至少 30 格且占原國至少 15%。首都區保留原國，較大分離區建立新國，人口、資源、士兵和艦隊按人口比例分配。領土排名前三國家受到一般長期分離分裂保護。
- **強國內部分裂**：是另一種低機率事件，由領土排名、最低領土、機率等參數控制；需注意目前預設排名上限為第一名而前三名保護，因此預設條件彼此抵銷，預設下這條分裂路徑不會挑出合格國家。若要啟用，需一併檢查 `POWER_SPLIT_TOP_RANKS` 與 `REGIME_SPLIT_PROTECTED_TOP_RANKS`。
- **海外無首都飛地**：每 100 年清理海外陸塊上沒有有效海外首都／殖民錨點的領土；有錨點時只保留與錨點連通的領地。被清部分土地、建築與人口一併清除，該整理寫入即時LOG，但刻意不加入重大歷史事件。
- **3000年後小陸塊**：地理陸塊小於 3000 格的領土會清空，台灣在地球地圖模式特別保留。這個清理依陸塊地理面積判斷，不是「國家只剩少量領地」就直接刪國。
- **滅亡**：國家失去全部土地／人口，或首都危機下無法遷都延續時滅亡。滅國清空該國全部土地、人口、建築與海外據點；建築記錄原興建國，所以即使建築已被敵人占領，原建造國滅亡時仍會拆除。

## 13. 國王、國名與戰績

每國開局會建立王統；國王任期在 `KING_REIGN_MIN_YEARS` 至 `KING_REIGN_MAX_YEARS` 間抽取，到期退位／駕崩後由同一王族姓氏產生新國王。首都失守遷都、政權分裂、海外首都接替本島等事件會依規則更新王統。分裂國會另建新王統。

戰績紀錄勝負、領土變更、傷亡與歷史事件。勝敗描述以領土得失為核心；「戰役結束」事件仍會記雙方傷亡。

## 14. 存檔、Q表與檔案

戰局由世界資料與戰爭資料共同組成。`WarEngine.save()` 會寫出 `.npz`（格子陣列）和 `.json`（國家、事件、遠征等資料），並另存同名 `_rl_brains.json`（國家級和戰術Q表、探索狀態等）。讀取戰局要求存檔Seed與目前世界Seed相同；因此應使用同一世界的存檔組合，不可把不同Seed的戰局資料混用。

自動存檔預設啟用，每 100 年存一次，程式結束時也會依流程保存。存檔與預覽資料位於程式目錄下 `saves/`。第一次遊玩建議保留原始壓縮包備份；調整參數前另存一份 `map_config.py`，若改動過大容易找回原值。

## 15. 調整參數的安全方式

1. 先暫停遊戲，備份 `map_config.py` 與 `map_viewer.py`。
2. 只改一組相關參數，重新啟動並新建世界測試；既有存檔的世界地圖不會因改參數自動重畫。
3. 修改涉及地形或尺寸時使用 **新世界**；修改經濟／戰爭參數時舊戰局通常會使用新規則繼續跑，但存檔格式和資料相依仍可能影響相容性。
4. 比率用小數表示：`0.80` 即 80%；距離單位是地圖格；資源成本排列順序是糧食、木材、礦產。
5. 單位、年限、成功機率與上限通常互相牽動。建議每次記錄原值與新值，不要一次把AI、地圖、經濟、戰爭都改掉。

## 16. 常用參數速查

下表描述目前程式中的全域設定。最常調整的玩法參數置於 `map_config.py`；畫面排版、字體、自動存檔與排名權重有些位於 `map_viewer.py`。標為「相容／備用」者不一定會在預設模式直接生效。

### 16.1 世界、地圖、地形

| 參數 | 預設 | 用途／調整效果 |
|---|---:|---|
| `MAP_WIDTH`, `MAP_HEIGHT` | 1200, 1200 | 預設世界尺寸；地球地圖固定可選範圍 1200–2000。越大越耗記憶體與計算時間。 |
| `COUNTRY_COUNT` | 16 | 開局國家數；越多會提高生成、AI、外交與戰爭成本。 |
| `MAP_CELL_SIZE_KM` | 1.0 | 每格代表公里；會影響海程距離換算。 |
| `MAP_SEED` | 隨機整數 | 世界種子；指定固定值可重現同一種地圖抽選。 |
| `WORLD_STYLE_OPTIONS` | 7種 | 可隨機抽到的風格清單；移除某值即不再隨機抽到。 |
| `TARGET_OCEAN_RATIO` | 0.70 | 一般地圖目標海洋比例；提高通常減少陸地。地球固定輪廓不以此決定海岸。 |
| `CONTINENT_CORE_MIN`, `CONTINENT_CORE_MAX` | 4, 9 | 一般地圖大陸核心數範圍。 |
| `MIN_ISLAND_AREA` | 24 | 一般地圖清除小於此面積的碎島；地球輪廓有獨立處理。 |
| `COAST_SMOOTHING_ITERATIONS` | 1 | 一般風格海岸平滑次數。 |
| `DOMAIN_WARP_STRENGTH` | 0.055 | 扭曲地形雜訊，改變大陸輪廓。 |
| `CONTINENT_NOISE_STRENGTH` | 0.42 | 大陸尺度起伏。 |
| `COAST_DETAIL_STRENGTH` | 0.18 | 海岸細節強度。 |
| `ISLAND_CHAIN_STRENGTH` | 0.12 | 群島／島鏈細節強度。 |
| `TECTONIC_PLATE_MIN`, `TECTONIC_PLATE_MAX` | 9, 16 | 板塊數量範圍，影響山系與地勢。 |
| `MOUNTAIN_STRENGTH`, `MOUNTAIN_WIDTH` | 0.22, 9.0 | 山脈起伏強度與寬度。 |
| `DEEP_OCEAN_DEPTH` | 0.12 | 深海分類深度參數。 |
| `BEACH_HEIGHT`, `PLAIN_HEIGHT`, `HILL_HEIGHT`, `MOUNTAIN_HEIGHT` | 0.025, 0.16, 0.30, 0.34 | 地形分類高度門檻／區間；調整會改變海岸、平原、丘陵與山地分布。 |
| `CHUNK_SIZE` | 256 | 地圖生成／分塊處理尺寸。 |
| `PREVIEW_FILENAME`, `DATA_FILENAME`, `INFO_FILENAME` | 檔名 | 地圖預覽、資料、資訊檔名稱。 |
| `LAKE_COUNT`, `RIVER_SOURCE_COUNT` | 18, 85 | 湖泊數與河流源頭密度，地圖面積改變時部分生成器會按比例縮放。 |
| `COUNTRY_MIN_DISTANCE_RATIO` | 0.075 | 首都候選點間距比例。 |
| `MIN_COUNTRY_LANDMASS_CELLS` | 12000 | 可選作為國家首都的大陸最小面積。 |
| `TERRITORY_RADIUS_RATIO` | 0.42 | 一般政治領土生成半徑比例；V19開局核心領土另由半徑／格數控制。 |
| `TERRITORY_ALPHA` | 0.34 | 領土疊色透明度。 |
| `TERRITORY_CELLS_PER_CITY`, `MAX_CITIES_PER_COUNTRY` | 45000, 5 | 舊／生成器城市規模參數；目前開局城市清單為空，動態建城依建築面積參數。 |
| `PORTS_PER_COUNTRY` | 2 | 每國港口數量上限；影響開局生成和後續建港。 |
| `CITY_MIN_DISTANCE` | 60 | 城市／首都間最小距離。 |
| `BARRACKS_MIN_DISTANCE` | 20 | 動態建造兵營彼此最小距離。 |

### 16.2 初始國力、經濟、人口與兵力

| 參數 | 預設 | 用途／調整效果 |
|---|---:|---|
| `WAR_START_YEAR` | 1 | 戰爭引擎起始年份。 |
| `INITIAL_TERRITORY_RADIUS` | 7 | 首都開局核心領土半徑。 |
| `INITIAL_TERRITORY_MAX_CELLS` | 150 | 每國開局最多核心領土格。 |
| `INITIAL_POPULATION_PER_CELL` | 2.4 | 開局每格人口估算倍率。 |
| `INITIAL_SOLDIER_RATIO` | 0.001 | 開局士兵占人口比例；另有至少20人限制。 |
| `INITIAL_FLEET_PER_PORT` | 18 | 每座開局港口提供的初始艦隊。 |
| `POPULATION_GROWTH` | 10 | 每年基礎人口成長人數。 |
| `REST_BIRTH_GROWTH_MULTIPLIER` | 3 | 休養生息時的出生倍率。 |
| `FOOD_PRODUCTION_MULTIPLIER` | 1.15 | 土地糧食總產出倍率。 |
| `FOOD_CONSUMPTION_PER_PERSON` | 0.18 | 每人每年糧食消耗。 |
| `FOOD_GROWTH_RESERVE_RATIO` | 0.90 | 保留給人口成長的糧食承載比例；降低會抑制人口成長。 |
| `CITY_FOOD_PRODUCTIVITY_BONUS` | 0.015 | 每座城市提供的糧食產能加成。 |
| `MAX_CITY_FOOD_PRODUCTIVITY_BONUS` | 0.30 | 城市糧食產能加成上限。 |
| `FOOD_CAPACITY_BONUS_PER_PERSON` | 100000 | 糧食承載人口每達此數值，即提升100%人口成長及增兵倍率。 |
| `ANNUAL_RECRUIT_RATIO` | 0.005 | 基礎年度徵兵比例。 |
| `RECRUIT_SLOWDOWN_START_YEAR`, `RECRUIT_SLOWDOWN_FULL_YEAR` | 1000, 5000 | 後期徵兵減速開始／完成年份。 |
| `LATE_GAME_RECRUIT_MIN_MULTIPLIER` | 0.25 | 後期徵兵最低倍率。 |
| `MIN_GARRISON_RATIO` | 0.035 | 發動遠征前保留的本土人口比例。 |
| `REST_DURATION_YEARS` | 40 | 休養生息年數／停止新戰爭期間。 |
| `REST_EXHAUSTION_RECOVERY` | 0.025 | 休養時每年恢復疲乏幅度。 |
| `PASSIVE_EXHAUSTION_RECOVERY` | 0.002 | 一般狀態每年恢復疲乏幅度。 |
| `REST_MORALE_RECOVERY` | 0.012 | 休養時每年士氣回復幅度。 |
| `WAR_EXHAUSTION_PER_BATTLE` | 0.12 | 每場戰鬥增加的基礎疲乏。 |
| `WAR_EXHAUSTION_CASUALTY_WEIGHT` | 0.35 | 傷亡占比對戰爭疲乏的影響。 |
| `WAR_EXHAUSTION_RECRUIT_PENALTY` | 0.65 | 戰爭疲乏對徵兵的最大抑制權重。 |
| `REST_ACTION_BASE_BIAS` | 0.08 | AI考慮休養的基礎偏好。 |

### 16.3 拓荒與建築

| 參數 | 預設 | 用途／調整效果 |
|---|---:|---|
| `EXPANSION_INTERVAL_YEARS` | 3 | 陸上拓荒檢查年距。 |
| `BASE_EXPANSION_CELLS` | 6 | 每次拓荒基本格數。 |
| `EXPANSION_CELLS_PER_SOLDIER` | 6 | 每名士兵支援的領土容量格數。 |
| `EXPANSION_FOOD_COST_PER_CELL` | 0.5 | 每拓一格糧食成本。 |
| `EXPANSION_TIMBER_COST_PER_CELL` | 0.2 | 每拓一格木材成本。 |
| `SETTLER_POPULATION_PER_CELL` | 1 | 拓荒／殖民每格需要搬移的人口。 |
| `BUILDING_CHECK_INTERVAL_YEARS` | 10 | 建築檢查週期。 |
| `CITY_AREA_PER_BUILDING` | 180 | 每達此領土格數增加一座城市目標。 |
| `BARRACKS_AREA_PER_BUILDING` | 130 | 每達此領土格數增加一座兵營目標。 |
| `OUTPOST_AREA_PER_BUILDING` | 90 | 每達此領土格數增加一座拓荒站目標。 |
| `CITY_EXPANSION_BONUS` | 2 | 每座城市增加每次陸拓格數。 |
| `BARRACKS_EXPANSION_BONUS` | 3 | 每座兵營增加每次陸拓格數。 |
| `OUTPOST_EXPANSION_BONUS` | 2 | 每座拓荒站增加每次陸拓格數。 |
| `CITY_COST`, `BARRACKS_COST`, `OUTPOST_COST`, `PORT_COST` | 見建築表 | 建築資源成本，順序都是糧食、木材、礦產。 |
| `FLEET_CAPACITY_PER_PORT` | 180 | 每港口艦隊容量。 |
| `FLEET_BUILD_BATCH` | 18 | 每次造艦數量。 |
| `FLEET_BUILD_COST` | (12,30,18) | 每批造艦資源成本。 |

### 16.4 行軍、戰爭與戰術

| 參數 | 預設 | 用途／調整效果 |
|---|---:|---|
| `LAND_MARCH_CELLS_PER_YEAR`, `SEA_MARCH_CELLS_PER_YEAR` | 38, 75 | 陸／海每年行軍距離。 |
| `NAVAL_OPERATION_RANGE` | 620 | 港口海上作戰距離。 |
| `SUPPLY_PER_SOLDIER_CELL` | 0.000018 | 每兵每格距離補給成本係數。 |
| `SUPPLY_SHORTAGE_ATTRITION` | 0.12 | 缺糧時遠征兵力年度損耗比例。 |
| `MOUNTAIN_DEFENSE_BONUS`, `HILL_DEFENSE_BONUS`, `RIVER_DEFENSE_BONUS` | 0.55, 0.22, 0.12 | 山地、丘陵、河流防禦加成。 |
| `AMPHIBIOUS_ATTACK_PENALTY` | 0.28 | 海上登陸攻擊力懲罰。 |
| `AI_MODE` | SARSA_LAMBDA | `SARSA_LAMBDA` 使用各國學習AI；`RULE` 使用規則式AI。 |
| `AI_RL_ALPHA`, `AI_RL_GAMMA`, `AI_RL_TRACE_LAMBDA` | 0.12, 0.92, 0.65 | Q值學習率、未來回饋折扣、資格跡線衰減。 |
| `AI_RL_EPSILON`, `AI_RL_MIN_EPSILON`, `AI_RL_EPSILON_DECAY_DECISIONS` | 0.12, 0.04, 300 | 初始探索率、最低探索率、衰減所需決策數。 |
| `OVERSEAS_MIN_FLEET` | 301 | 海外征戰／殖民艦隊門檻。 |
| `OVERSEAS_RL_REWARD_MULTIPLIER` | 2.0 | SARSA海外行動回饋倍率。 |
| `AI_RL_NAVAL_ACTION_BIAS`, `AI_RL_COLONY_ACTION_BIAS` | 0.06, 0.40 | SARSA海戰／殖民行動的額外偏好。 |
| `AI_WAR_CHECK_INTERVAL` | 5 | AI戰爭決策週期。 |
| `AI_BASE_WAR_CHANCE` | 0.10 | 規則式AI基礎戰爭機率；預設SARSA模式不按同一方式使用。 |
| `AI_MIN_ATTACK_SOLDIERS` | 20 | 發動遠征的最低士兵數。 |
| `AI_MIN_POWER_RATIO`, `AI_UNIFICATION_MIN_POWER_RATIO` | 0.85, 0.55 | 規則式門檻／統一世界AI容許的最低戰力比，實際適用分支不同。 |
| `AI_UNIFICATION_TARGET_LAND_WEIGHT` | 1.2 | 對較大領土目標的AI偏好權重。 |
| `AI_MAX_ACTIVE_CAMPAIGNS` | 2 | 每國同時行軍戰役上限。 |
| `COALITION_THREAT_SHARE`, `COALITION_MAX_MEMBERS` | 0.16, 5 | 觸發反霸權圍剿的世界土地占比門檻、最多圍剿國數。 |
| `CAPTURE_RADIUS_MIN`, `CAPTURE_RADIUS_MAX` | 10, 36 | 戰後領土捕獲半徑下／上限。 |
| `BATTLE_RANDOMNESS` | 0.22 | 戰場攻防隨機波動幅度。 |
| `BATTLE_BASE_GARRISON_SHARE` | 0.22 | 局部守軍基礎比例。 |
| `BATTLE_LOCAL_POPULATION_WEIGHT` | 0.35 | 戰區人口占比對守軍投入的影響。 |
| `BATTLE_MAX_LOCAL_GARRISON_SHARE` | 0.75 | 局部守軍投入上限。 |
| `BATTLE_LEARNED_GARRISON_SHARES` | 0.10–0.70 | 戰術AI可選擇的駐軍比例。 |
| `TACTICAL_ATTACK_FRACTIONS` | 0.18–0.70 | 戰術AI可選擇的投入攻兵比例。 |
| `TACTICAL_LEARNING_ALPHA`, `TACTICAL_EXPLORATION` | 0.10, 0.08 | 戰術Q表學習率與探索率。 |
| `TACTICAL_WEAK_FRONT_WEIGHT` | 1.0 | 弱防線目標偏好權重。 |
| `BARRACKS_BATTLE_RADIUS` | 24 | 計算戰區附近支援兵營的半徑。 |
| `BARRACKS_GARRISON_SHARE_BONUS`, `BARRACKS_GARRISON_MAX_BONUS` | 0.08, 0.24 | 每座附近兵營加成與總加成上限。 |
| `BARRACKS_POSITION_DEFENSE_BONUS`, `OUTPOST_POSITION_DEFENSE_BONUS`, `CITY_POSITION_DEFENSE_BONUS` | 0.06, 0.10, 0.06 | 建築所在格的額外防禦加成。 |
| `ALLIANCE_COUNT` | 6 | 聯盟相關舊／展示設定；不是AI會自動建立六個聯盟的保證。 |
| `ALLIANCE_REINFORCEMENT_RATIO` | 0.18 | 若存檔已有聯盟，援軍比例。 |

### 16.5 海外、後撤、分裂、 UI與存檔

| 參數 | 預設 | 用途／調整效果 |
|---|---:|---|
| `OVERSEAS_EXPEDITION_LIMIT` | 100 | 每國一生殖民與海外征服遠征總次數上限。 |
| `OVERSEAS_CAPITAL_MAX_PER_COUNTRY` | 99 | 舊存檔相容欄位；實際名額由動態規則計算。 |
| `OVERSEAS_REGION_CONTROL_SHARE_REQUIRED` | 0.80 | 本土／海外陸塊統一比例。 |
| `OVERSEAS_INITIAL_EXPEDITION_SLOTS` | 1 | 本土統一後起始海外名額。 |
| `OVERSEAS_MAJOR_LANDMASS_MIN_CELLS` | 3000 | 海外大島最低絕對格數。 |
| `OVERSEAS_MAJOR_LANDMASS_LARGEST_RATIO` | 0.015 | 海外大島相對最大陸塊比例門檻。 |
| `OVERSEAS_PREFERRED_LANDMASS_COUNT` | 3 | 優先選擇最大的幾個海外陸塊。 |
| `OVERSEAS_EXPANSION_REQUIRES_HOMELAND_UNIFIED` | True | 是否要求先統一本土才可海外擴張。 |
| `OVERSEAS_RETREAT_HOME_MAX_CELLS`, `OVERSEAS_RETREAT_INITIAL_HOME_SHARE` | 300, 0.25 | 後撤危局雙門檻；取較低者。 |
| `OVERSEAS_RETREAT_BASE_CHANCE` | 0.42 | 規則式流程的後撤基礎機率。 |
| `OVERSEAS_RETREAT_PORT_THREAT_RADIUS` | 4 | 判定港口受敵人威脅的距離。 |
| `LATE_GAME_SMALL_TERRITORY_CLEANUP_YEAR` | 3000 | 小陸塊清理開始年份。 |
| `LATE_GAME_SMALL_LANDMASS_MAX_CELLS` | 3000 | 清理的陸塊大小界線；地球地圖台灣例外保留。 |
| `TERRITORY_SPLIT_MIN_FRACTION` | 1/3 | 小型本土分裂碎片清除比例門檻。 |
| `CAPITAL_RELOCATION_MIN_CITIES` | 2 | 首都失守後允許推舉新王的最低城市數。 |
| `CAPITAL_RELOCATION_CITY_RADIUS` | 80 | 遷都候選城市群搜尋半徑。 |
| `CAPITAL_RELOCATION_MIN_TERRITORY`, `CAPITAL_RELOCATION_MIN_POPULATION` | 50, 80 | 遷都最低領土與人口。 |
| `TERRITORY_SPLIT_GRACE_YEARS` | 20 | 長期斷裂成為正式政權分裂前的等待年數。 |
| `TERRITORY_SPLIT_CHECK_INTERVAL` | 100 | 領土斷裂、小本土飛地與無首都海外飛地檢查間隔。 |
| `TERRITORY_SPLIT_MIN_CELLS`, `TERRITORY_SPLIT_MIN_SHARE` | 30, 0.15 | 可分裂區塊最低格數、占原國比例。 |
| `KING_REIGN_MIN_YEARS`, `KING_REIGN_MAX_YEARS` | 5, 80 | 國王任期抽選範圍。 |
| `GEOGRAPHIC_LABEL_MIN_CELLS`, `GEOGRAPHIC_MAX_VISIBLE_LABELS` | 120, 80 | 地名顯示的最小區塊與同畫面上限。 |
| `POWER_SPLIT_CHECK_INTERVAL`, `POWER_SPLIT_TOP_RANKS`, `POWER_SPLIT_CHANCE`, `POWER_SPLIT_MIN_TERRITORY` | 25, 1, 0.003, 80000 | 強國分裂檢查週期、排名範圍、機率、最低土地。 |
| `REGIME_SPLIT_PROTECTED_TOP_RANKS` | 3 | 保護不因一般分離而分裂的強國排名範圍。 |
| `COLONY_CHECK_INTERVAL`, `COLONY_FOUND_CHANCE`, `COLONY_COOLDOWN_YEARS` | 5, 0.90, 40 | 規則式殖民檢查週期／機率／冷卻時間；SARSA模式部分不同。 |
| `COLONY_MAX_PER_COUNTRY` | 99 | 舊欄位相容；現制以動態名額控制。 |
| `COLONY_SHIP_SPEED_KM_PER_YEAR` | 10.0 | 殖民船年度航速。 |
| `COLONY_MIN_FLEET`, `COLONY_TRANSPORT_FLEET` | 8, 5 | 殖民啟航艦隊最低量、運輸後扣留艦隊。另受301艘海外規則限制。 |
| `COLONY_SETTLER_POPULATION`, `COLONY_INITIAL_CELLS` | 30, 24 | 殖民搬運人口與初始占地格數上限。 |
| `COLONY_MIN_DISTANCE` | 60 | 殖民點離本國首都的最小距離。 |
| `COLONY_PRIORITIZE_EMPTY_ISLANDS` | True | 是否偏好尚無政權的海外陸塊。 |
| `COLONY_AUTO_PORT` | True | 殖民地成立時是否自動建港。 |
| `COLONY_FOOD_COST`, `COLONY_TIMBER_COST` | 80, 60 | 殖民遠征糧食、木材成本。 |
| `COLONY_INDEPENDENCE_MIN_YEARS`, `COLONY_INDEPENDENCE_CHECK_INTERVAL`, `COLONY_INDEPENDENCE_CHANCE` | 1000, 20, 0.001 | 殖民地可獨立的最早年份、檢查間隔與單次機率。 |
| `NAVAL_COASTAL_LANDING_ENABLED` | True | 是否啟用海岸登陸規則開關。 |
| `AI_NAVAL_TARGET_BONUS` | 0.35 | 規則式AI海戰目標加權。 |
| `SECONDS_PER_YEAR` | 0.5 | 自動模擬每一年使用的秒數。數字越小，模擬越快。 |
| `AUTO_RUN_ON_START` | True | 啟動後是否自動運行。 |
| `UI_REFRESH_EVERY_YEARS`, `AUTO_SAVE_EVERY_YEARS` | 1, 100 | UI刷新與自動存檔年距。 |
| `COUNTRY_NAME_FONT_SIZE`, `COUNTRY_NAME_FONT_BOLD`, `COUNTRY_NAME_OUTLINE_WIDTH`, `MAP_BUILDING_ICON_SIZE` | 12, True, 2, 1 | 地圖文字與建築圖示外觀。 |
| `LEFT_PANEL_WIDTH`, `RIGHT_PANEL_WIDTH` | 330, 430 | 主面板寬度相關初始設定；實際可拖曳調整。 |
| `AUTO_SAVE_ENABLED`, `AUTO_LOAD_LAST_SAVE` | True, True | 開／關自動存檔、啟動時載入上次存檔。 |
| `COUNTRY_FOCUS_MARGIN`, `COUNTRY_FOCUS_MIN_ZOOM`, `COUNTRY_FOCUS_MAX_ZOOM` | 0.82, 0.35, 8.0 | 點國家定位地圖時的留白與縮放範圍。 |
| `RANK_SOLDIER_WEIGHT`, `RANK_FLEET_WEIGHT`, `RANK_LAND_WEIGHT` | 1, 1, 3 | UI綜合排名各項權重。 |

### 16.6 介面排版參數（`map_viewer.py`）

| 參數 | 預設 | 用途 |
|---|---:|---|
| `WINDOW_SIZE` | 1900×1000 | 主視窗初始尺寸。 |
| `UI_LEFT_PANEL_RATIO` | 0.46 | 左右主區初始比例；使用者仍可拖曳。 |
| `UI_MAP_HEIGHT_RATIO` | 0.70 | 右側地圖相對高度初始比例。 |
| `UI_FONT_FAMILY`, `UI_FONT_SIZE` | Microsoft JhengHei UI, 12 | 主介面字型及基準大小。 |
| `UI_FONT_SIZE_HEADER`, `UI_FONT_SIZE_TAB`, `UI_FONT_SIZE_DETAIL`, `UI_FONT_SIZE_LOG`, `UI_FONT_SIZE_RANK` | 12 | 標題、分頁、詳細欄、LOG、排名字級。 |
| `UI_RANK_FONT_FAMILY`, `UI_RANK_LINE_SPACING` | Consolas, 2 | 排名等寬字型與行距。 |
| `UI_COUNTRY_NAME_FONT_SIZE`, `UI_TREE_ROW_HEIGHT` | 14, 30 | 地圖國名標籤字級、表格行高。 |
| `MAP_FIT_MARGIN`, `MAP_MIN_ZOOM`, `MAP_MAX_ZOOM` | 0.96, 0.10, 15 | 地圖適配留白與縮放上下限。 |
| `MAP_WHEEL_ZOOM_IN`, `MAP_WHEEL_ZOOM_OUT` | 1.25, 0.80 | 滾輪每階縮放倍率。 |
| `UI_LEFT_MIN_PIXELS`, `UI_RIGHT_MIN_PIXELS`, `UI_MAP_MIN_PIXELS`, `UI_BOTTOM_MIN_PIXELS` | 520, 620, 360, 180 | 面板拖曳時保留的最小像素。 |
| `SIM_CLOCK_POLL_MS`, `SIM_MAX_BATCH_YEARS`, `SIM_MAX_BACKLOG_YEARS` | 10, 1, 250 | 模擬時鐘輪詢、每次背景推進年數與最多追趕積欠年數。 |
| `MAP_REFRESH_SECONDS` | 0.50 | 地圖重繪間隔。 |

## 17. 常見疑問

**為什麼有空地，AI沒有馬上去拓荒？** 陸拓每三年才檢查一次，而且必須與本國土地四方向相鄰、能通行，還要有剩餘土地容量、糧食、木材和移民人口。隔海的空地不屬於陸拓；需符合殖民條件後由港口派船。

**為什麼國家有兩個以上海外地區？** 海外名額是「同時持有／正在預約的擴張階段」規則：本土統一先開一格，每平定一塊海外大陸再解鎖下一格。程序也會把同一陸塊上的多個據點合併計數，不會一島一個據點就多算；真正發動新遠征仍要符合名額、艦隊及土地條件。

**為什麼一個國家看起來沒有城市？** 城市按領土面積設定目標且不是開局必有；領土不到 180 格時目標為 0。即使達標，也要等到建築檢查年份、有空格、符合 60 格間距並付得起資源才會建造。

**海岸小飛地會因為靠海而保留嗎？** 不會單靠海岸就免清。若是首都所在本島上的分離小塊、不含首都又未達三分之一比例，定期檢查時會清空；海外陸塊則依有效海外首都與連通區塊規則清理。

**為什麼領土改變但國家沒有滅亡？** 首都被攻下時還會檢查海外首都繼承或本土遷都條件；只要符合其一，政權就能延續。只有無有效領土／人口或無法延續政權才會滅亡。

## 18. 程式檔案導覽

| 檔案 | 主要內容 |
|---|---|
| `map_config.py` | 全域玩法參數、地圖尺寸、經濟、戰爭、AI、殖民與後撤設定。 |
| `map_generator.py` | 地圖尺寸驗證、風格、地形、地球輪廓、生成與存取地圖。 |
| `environment_generator.py`、`climate_rules.py`、`terrain_rules.py` | 地形環境、氣候、水文與類型判斷。 |
| `habitability_generator.py` | 農業、木材、礦產、淡水、城市與防禦價值、移動成本。 |
| `country_generator.py` | 首都、開局國家、初始領土、港口、道路及海路。 |
| `war_engine.py` | 年度經濟、建築、拓荒、AI決策、殖民、戰役、分裂、滅亡、存檔。 |
| `rl_brain.py` | SARSA國家Q表、戰術Q表、探索與學習更新。 |
| `map_viewer.py` | Tkinter操作介面、表格、地圖繪製、排名、LOG、自動存檔與模擬時鐘。 |
| `requirements.txt` | Python外部套件需求。 |

---

## 版本提醒

本文件記錄 V19 的預設規則。遊戲參數集中在 `map_config.py`，但不是每個變數都在每一種AI模式或每一條程式分支中生效；標示為相容欄位、舊設定或模式限定的項目，調整前請先確認對應使用位置。改參數後最好建立新世界並觀察數百年，再視結果調校。
