try:
    from .main import main
except ImportError:  # pragma: no cover - script/PyInstaller fallback
    from awl_text_sync.main import main

raise SystemExit(main())
