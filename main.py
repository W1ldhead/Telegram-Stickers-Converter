"""StickerMaker: точка входа программы с окном."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from core.tools import ToolsMissing, base_dir, check_tools
from ui.main_window import MainWindow


def main() -> int:
    if sys.platform == "win32":
        # Своя иконка на панели задач, а не иконка Python
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StickerMaker")

    app = QApplication(sys.argv)
    app.setApplicationName("StickerMaker")
    app.setWindowIcon(QIcon(str(base_dir() / "assets" / "icon.png")))
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
