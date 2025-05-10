# Данные для сборки исполняемого файла
__version__ = "1.23"
__author__ = "ОИТ ДРНУ"

import sys
from PyQt5.QtWidgets import QApplication, QStyleFactory
from postcard_editor import PostcardEditor
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))  # Windows, Linux, macOS
    editor = PostcardEditor()
    editor.show()
    sys.exit(app.exec_())