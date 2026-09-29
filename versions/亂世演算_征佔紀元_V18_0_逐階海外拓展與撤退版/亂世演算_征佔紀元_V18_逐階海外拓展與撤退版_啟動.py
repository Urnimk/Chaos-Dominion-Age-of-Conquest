"""《亂世演算_征佔紀元 V18》啟動檔。"""

try:
    from map_viewer import main
except ImportError as exc:
    raise SystemExit(
        "缺少必要套件。請先執行：pip install -r requirements.txt\n"
        f"詳細原因：{exc}"
    ) from exc


if __name__ == "__main__":
    main()
