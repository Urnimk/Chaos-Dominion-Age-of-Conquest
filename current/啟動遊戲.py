"""V22_6_5 海外戰區堅守與撤離修正版。"""
try:
    from map_viewer import main
except ImportError as exc:
    raise SystemExit("缺少必要套件，請執行：pip install -r requirements.txt\n"+str(exc)) from exc
if __name__ == '__main__':
    main()
