"""StickerMaker: точка входа программы с окном."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from core.tools import ToolsMissing, check_tools
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("StickerMaker")
    try:
        check_tools()
    except ToolsMissing as e:
        QMessageBox.critical(None, "StickerMaker", f"{e}\n\nПрограмма не может работать без них.")
        return 1
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
