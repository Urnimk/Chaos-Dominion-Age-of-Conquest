# 亂世演算／征佔紀元 V26

請先閱讀「V26_君主系統說明.md」。本版包含君主策略、王朝、政治聯姻、血緣宣稱、跨國繼承、共主邦聯、王位戰爭與長期整合。

執行「啟動遊戲.py」或「啟動遊戲.bat」。原套件依賴不變；舊完整存檔可複製進 saves 載入。V26 存檔不能交回 V25_1 使用。

完整測試：`python -m unittest discover -p "test_*.py" -v`

延續存檔驗證：`python verify_v26.py --save saves --years 500 --output validation/run.json`

生成小世界測試：`python verify_v26.py --years 1000 --seed 2026 --output validation/world.json`

效能對照：同一存檔各跑一百年，一次加 `--off`，另一次不加，並使用不同輸出路徑。測試會讀取原存檔，在輸出目錄寫入檢查點，不覆蓋原件。

本包的「驗證資料」包含實際執行結果、自然政治因果鏈及測試紀錄。V25_1 原有報告保留於「舊版參考」；不能用它們當作 V26 驗證結果。
