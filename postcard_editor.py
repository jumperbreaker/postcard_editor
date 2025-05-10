CODE_VERSION = "1.23"

import os
import json
import sys
from PyQt5.QtGui import QFontDatabase, QWheelEvent
from PIL import Image, ImageFont, ImageDraw
import numpy as np
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal, QTimer, QPointF
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPen, QTransform, QCursor, QKeyEvent, QTextOption, \
    QIcon
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QSpinBox, QColorDialog, QFontDialog,
                             QFileDialog, QListWidget, QToolBar, QAction, QDockWidget,
                             QScrollArea, QSizePolicy, QTextEdit, QMessageBox, QInputDialog,
                             QDialog, QGridLayout, QLineEdit, QCheckBox, QComboBox, QStyle, QShortcut)

class Canvas(QWidget):
    """Класс холста для отображения и редактирования открытки"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_editor = parent
        self.setMouseTracking(True)
        self.dragging = None  # Флаг перемещения объекта
        self.resizing = None  # Флаг изменения размера
        self.rotating = None  # Флаг вращения
        self.current_item = None  # Индекс текущего выбранного элемента
        self.start_pos = QPoint()  # Начальная позиция для операций
        self.transform_origin = QPoint()  # Центр трансформации
        self.cursor_pos = QPoint()  # Текущая позиция курсора
        self.scale_factor = 1.0  # Масштаб холста
        self.setStyleSheet("background-color: #808080;")
        self.editing_text = None  # Индекс редактируемого текста
        self.text_edit_widget = None  # Виджет для редактирования текста
        self.setFocusPolicy(Qt.StrongFocus)
        self.center_canvas()
        self.last_scale_factor = 1.0
        self.hovered_item = None  # Индекс подсвечиваемого элемента

        # Таймер для центрирования холста
        self.center_canvas_timer = QTimer()
        self.center_canvas_timer.setSingleShot(True)
        self.center_canvas_timer.timeout.connect(self.center_canvas)

        # Виджет для редактирования текста
        self.text_edit = QTextEdit(self)
        self.text_edit.setVisible(False)
        self.text_edit.setStyleSheet("background-color: white; border: 2px solid blue;")
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.textChanged.connect(self.adjust_text_edit_size)
        self.text_edit.installEventFilter(self)

        # Загрузка пользовательских шрифтов
        self.load_custom_fonts()
        self.resize_timer = QTimer()

    def load_custom_fonts(self):
        font_db = QFontDatabase()
        font_files = [
            "Monotype-Corsiva-Bold.ttf",
            "Monotype-Corsiva-Bold-Italic.ttf",
            "Monotype-Corsiva-Regular.ttf",
            "Monotype-Corsiva-Regular-Italic.ttf"
        ]

        # Проверяем несколько возможных путей
        search_paths = []

        # 1. Путь в собранном приложении (onefile)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            search_paths.append(os.path.join(sys._MEIPASS, 'fonts/Monotype-Corsiva'))

        # 2. Путь в собранном приложении (onedir)
        search_paths.append(os.path.join(os.path.dirname(sys.executable), 'fonts/Monotype-Corsiva'))

        # 3. Путь в режиме разработки
        search_paths.append(os.path.join(os.path.dirname(__file__), 'fonts/Monotype-Corsiva'))

        # 4. Системные пути
        search_paths.extend([
            '/usr/share/fonts/truetype/postcard-editor',
            '/usr/local/share/fonts',
            os.path.expanduser('~/.local/share/fonts')
        ])

        for font_file in font_files:
            loaded = False
            for path in search_paths:
                font_path = os.path.join(path, font_file)
                if os.path.exists(font_path):
                    font_id = font_db.addApplicationFont(font_path)
                    if font_id != -1:
                        print(f"Successfully loaded font: {font_path}")
                        loaded = True
                        break
            if not loaded:
                print(f"Warning: Font not found: {font_file}")

    def eventFilter(self, obj, event):
        """Обработка событий для текстового редактора"""
        if obj == self.text_edit and event.type() == event.FocusOut:
            self.finish_text_edit()
            return True
        return super().eventFilter(obj, event)

    def adjust_text_edit_size(self):
        """Автоматическая подстройка размера текстового редактора"""
        if self.editing_text is None:
            return

        layer = self.parent_editor.layers[self.editing_text]
        doc = self.text_edit.document()

        # Расчет идеальных размеров текста
        doc.adjustSize()
        text_width = doc.idealWidth()
        text_height = doc.size().height()

        # Установка новых размеров
        new_width = max(int(layer['rect'].width() * self.scale_factor), int(text_width) + 10)
        new_height = max(int(layer['rect'].height() * self.scale_factor), int(text_height) + 10)

        # Обновление размеров редактора
        rect = QRect(
            int(layer['rect'].x() * self.scale_factor),
            int(layer['rect'].y() * self.scale_factor),
            new_width,
            new_height
        )
        self.text_edit.setGeometry(rect)

        # Обновление размеров слоя
        layer['rect'].setWidth(new_width / self.scale_factor)
        layer['rect'].setHeight(new_height / self.scale_factor)

        self.update()

    def fit_to_view(self):
        """Подгонка холста под размер окна"""
        if not hasattr(self, 'minimumWidth') or not hasattr(self, 'minimumHeight'):
            return

        scroll_area = self.parent().findChild(QScrollArea)
        if not scroll_area:
            return

        viewport_size = scroll_area.viewport().size()
        if viewport_size.width() == 0 or viewport_size.height() == 0:
            return

        # Расчет масштаба для полного отображения
        width_scale = viewport_size.width() / self.minimumWidth()
        height_scale = viewport_size.height() / self.minimumHeight()
        self.scale_factor = min(width_scale, height_scale) * 0.9
        self.scale_factor = max(0.1, min(5.0, self.scale_factor))

        # Обновление размеров холста
        self.resize(
            int(self.minimumWidth() * self.scale_factor),
            int(self.minimumHeight() * self.scale_factor)
        )

        # Центрирование холста
        self.center_canvas()
        self.update()

    def center_canvas(self):
        """Центрирование холста в области просмотра"""
        scroll_area = self.parent().findChild(QScrollArea)
        if not scroll_area:
            return

        QApplication.processEvents()

        viewport = scroll_area.viewport()
        if viewport.width() == 0 or viewport.height() == 0:
            return

        if not hasattr(self, 'minimumWidth') or not hasattr(self, 'minimumHeight'):
            return

        # Расчет размеров с учетом масштаба
        canvas_width = self.minimumWidth() * self.scale_factor
        canvas_height = self.minimumHeight() * self.scale_factor

        # Расчет центра viewport
        viewport_center_x = viewport.width() / 2
        viewport_center_y = viewport.height() / 2

        # Расчет центра холста
        canvas_center_x = canvas_width / 2
        canvas_center_y = canvas_height / 2

        # Установка новых размеров
        self.resize(int(canvas_width), int(canvas_height))

        # Прокрутка к центру
        h_scroll = int(canvas_center_x - viewport_center_x)
        v_scroll = int(canvas_center_y - viewport_center_y)

        scroll_area.horizontalScrollBar().setValue(h_scroll)
        scroll_area.verticalScrollBar().setValue(v_scroll)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#808080"))

        if hasattr(self, 'minimumWidth') and hasattr(self, 'minimumHeight'):
            canvas_rect = QRect(0, 0, self.minimumWidth(), self.minimumHeight())
            scaled_rect = QRect(0, 0, int(self.minimumWidth() * self.scale_factor),
                                int(self.minimumHeight() * self.scale_factor))
            painter.fillRect(scaled_rect, Qt.white)

        if not self.parent_editor.layers:
            return

        # Отрисовка слоев с учетом масштаба
        for i in reversed(range(len(self.parent_editor.layers))):
            layer = self.parent_editor.layers[i]
            if not layer['visible'] or (self.editing_text is not None and
                                        self.editing_text == i):
                continue

            scaled_rect = QRect(
                int(layer['rect'].x() * self.scale_factor),
                int(layer['rect'].y() * self.scale_factor),
                int(layer['rect'].width() * self.scale_factor),
                int(layer['rect'].height() * self.scale_factor)
            )

            # Подсветка при наведении (кроме текущего выделенного элемента)
            if i == self.hovered_item and i != self.current_item:
                painter.setPen(QPen(QColor(100, 150, 255, 150), 3, Qt.SolidLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(scaled_rect)

            if layer['type'] == 'image':
                pixmap = QPixmap(layer['path'])
                if layer['rotation'] != 0:
                    transform = QTransform()
                    transform.translate(scaled_rect.center().x(), scaled_rect.center().y())
                    transform.rotate(layer['rotation'])
                    transform.translate(-scaled_rect.width() / 2, -scaled_rect.height() / 2)
                    painter.setTransform(transform)
                    painter.drawPixmap(QRect(0, 0, scaled_rect.width(), scaled_rect.height()),
                                       pixmap.scaled(scaled_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    painter.resetTransform()
                else:
                    painter.drawPixmap(scaled_rect,
                                       pixmap.scaled(scaled_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

            elif layer['type'] == 'text':
                # Масштабируем размер шрифта
                scaled_font_size = max(4, int(layer['font_size'] * self.scale_factor))
                font = QFont(layer['font'], scaled_font_size)
                painter.setFont(font)
                painter.setPen(QColor(layer['color']))

                if layer['rotation'] != 0:
                    painter.save()
                    painter.translate(scaled_rect.center())
                    painter.rotate(layer['rotation'])
                    painter.translate(-scaled_rect.width() / 2, -scaled_rect.height() / 2)
                    painter.drawText(QRect(0, 0, scaled_rect.width(), scaled_rect.height()),
                                     layer['alignment'], layer['text'])
                    painter.restore()
                else:
                    painter.drawText(scaled_rect, layer['alignment'], layer['text'])

        # Отрисовка выделения (без изменений)
        if self.current_item is not None and self.editing_text is None:
            layer = self.parent_editor.layers[self.current_item]
            scaled_rect = QRect(
                int(layer['rect'].x() * self.scale_factor),
                int(layer['rect'].y() * self.scale_factor),
                int(layer['rect'].width() * self.scale_factor),
                int(layer['rect'].height() * self.scale_factor)
            )

            if layer['rotation'] != 0:
                painter.save()
                painter.translate(scaled_rect.center())
                painter.rotate(layer['rotation'])
                painter.translate(-scaled_rect.width() / 2, -scaled_rect.height() / 2)

                painter.setPen(QPen(Qt.blue, 2, Qt.DashLine))
                painter.drawRect(QRect(0, 0, scaled_rect.width(), scaled_rect.height()))

                painter.setPen(QPen(Qt.black, 2))
                painter.setBrush(Qt.white)
                size = 8
                handles = [
                    QRect(0 - size // 2, 0 - size // 2, size, size),
                    QRect(scaled_rect.width() - size // 2, 0 - size // 2, size, size),
                    QRect(0 - size // 2, scaled_rect.height() - size // 2, size, size),
                    QRect(scaled_rect.width() - size // 2, scaled_rect.height() - size // 2, size, size),
                    QRect(scaled_rect.width() // 2 - size // 2, 0 - size // 2, size, size),
                    QRect(scaled_rect.width() // 2 - size // 2, scaled_rect.height() - size // 2, size, size),
                    QRect(0 - size // 2, scaled_rect.height() // 2 - size // 2, size, size),
                    QRect(scaled_rect.width() - size // 2, scaled_rect.height() // 2 - size // 2, size, size)
                ]
                for handle in handles:
                    painter.drawRect(handle)

                rotation_handle = QRect(scaled_rect.width() // 2 - size // 2, -30, size, size)
                painter.drawRect(rotation_handle)
                painter.drawLine(scaled_rect.width() // 2, 0, scaled_rect.width() // 2, -25)

                painter.restore()
            else:
                painter.setPen(QPen(Qt.blue, 2, Qt.DashLine))
                painter.drawRect(scaled_rect)

                painter.setPen(QPen(Qt.black, 2))
                painter.setBrush(Qt.white)
                size = 8
                handles = [
                    QRect(scaled_rect.left() - size // 2, scaled_rect.top() - size // 2, size, size),
                    QRect(scaled_rect.right() - size // 2, scaled_rect.top() - size // 2, size, size),
                    QRect(scaled_rect.left() - size // 2, scaled_rect.bottom() - size // 2, size, size),
                    QRect(scaled_rect.right() - size // 2, scaled_rect.bottom() - size // 2, size, size),
                    QRect(scaled_rect.center().x() - size // 2, scaled_rect.top() - size // 2, size, size),
                    QRect(scaled_rect.center().x() - size // 2, scaled_rect.bottom() - size // 2, size, size),
                    QRect(scaled_rect.left() - size // 2, scaled_rect.center().y() - size // 2, size, size),
                    QRect(scaled_rect.right() - size // 2, scaled_rect.center().y() - size // 2, size, size)
                ]
                for handle in handles:
                    painter.drawRect(handle)

                rotation_handle = QRect(scaled_rect.center().x() - size // 2, scaled_rect.top() - 30, size, size)
                painter.drawRect(rotation_handle)
                painter.drawLine(scaled_rect.center().x(), scaled_rect.top(),
                                 scaled_rect.center().x(), scaled_rect.top() - 25)

    def mousePressEvent(self, event):
        """Обработка нажатия кнопки мыши"""
        if event.button() == Qt.LeftButton:
            self.hovered_item = None
            self.start_pos = event.pos()

            if self.current_item is not None and self.editing_text is None:
                layer = self.parent_editor.layers[self.current_item]
                scaled_rect = QRect(
                    int(layer['rect'].x() * self.scale_factor),
                    int(layer['rect'].y() * self.scale_factor),
                    int(layer['rect'].width() * self.scale_factor),
                    int(layer['rect'].height() * self.scale_factor)
                )

                # Проверка нажатия на маркер вращения
                if layer['rotation'] != 0:
                    transform = QTransform()
                    transform.translate(scaled_rect.center().x(), scaled_rect.center().y())
                    transform.rotate(layer['rotation'])
                    transform.translate(-scaled_rect.width() / 2, -scaled_rect.height() / 2)
                    rotation_handle = QRect(scaled_rect.width() // 2 - 4, -30, 8, 8)
                    global_handle = transform.mapRect(rotation_handle)

                    if global_handle.contains(event.pos()):
                        self.rotating = True
                        self.transform_origin = scaled_rect.center()
                        return
                else:
                    rotation_handle = QRect(scaled_rect.center().x() - 4, scaled_rect.top() - 30, 8, 8)
                    if rotation_handle.contains(event.pos()):
                        self.rotating = True
                        self.transform_origin = scaled_rect.center()
                        return

                # Проверка нажатия на маркеры изменения размера
                size = 8
                handles = {
                    'top-left': QRect(scaled_rect.left() - size // 2, scaled_rect.top() - size // 2, size, size),
                    'top-right': QRect(scaled_rect.right() - size // 2, scaled_rect.top() - size // 2, size, size),
                    'bottom-left': QRect(scaled_rect.left() - size // 2, scaled_rect.bottom() - size // 2, size, size),
                    'bottom-right': QRect(scaled_rect.right() - size // 2, scaled_rect.bottom() - size // 2, size,
                                          size),
                    'top-center': QRect(scaled_rect.center().x() - size // 2, scaled_rect.top() - size // 2, size,
                                        size),
                    'bottom-center': QRect(scaled_rect.center().x() - size // 2, scaled_rect.bottom() - size // 2, size,
                                           size),
                    'left-center': QRect(scaled_rect.left() - size // 2, scaled_rect.center().y() - size // 2, size,
                                         size),
                    'right-center': QRect(scaled_rect.right() - size // 2, scaled_rect.center().y() - size // 2, size,
                                          size)
                }

                for handle_name, handle_rect in handles.items():
                    if handle_rect.contains(event.pos()):
                        self.resizing = handle_name
                        return

                # Проверка нажатия внутри объекта (начало перемещения)
                if scaled_rect.contains(event.pos()):
                    self.dragging = True
                    return

            # Проверка нажатия на любой слой (выбор) - теперь проверяем от верхнего к нижнему
            for i in range(len(self.parent_editor.layers)):
                layer = self.parent_editor.layers[i]
                if not layer['visible']:
                    continue

                scaled_rect = QRect(
                    int(layer['rect'].x() * self.scale_factor),
                    int(layer['rect'].y() * self.scale_factor),
                    int(layer['rect'].width() * self.scale_factor),
                    int(layer['rect'].height() * self.scale_factor)
                )

                if layer['rotation'] != 0:
                    transform = QTransform()
                    transform.translate(scaled_rect.center().x(), scaled_rect.center().y())
                    transform.rotate(layer['rotation'])
                    transform.translate(-scaled_rect.width() / 2, -scaled_rect.height() / 2)
                    inverted_transform = transform.inverted()[0]
                    local_pos = inverted_transform.map(event.pos())
                    if QRect(0, 0, scaled_rect.width(), scaled_rect.height()).contains(local_pos):
                        self.current_item = i
                        self.parent_editor.layer_list.setCurrentRow(i)
                        self.update()
                        return
                elif scaled_rect.contains(event.pos()):
                    self.current_item = i
                    self.parent_editor.layer_list.setCurrentRow(i)
                    self.update()
                    return

            # Снятие выделения при нажатии на пустую область
            self.current_item = None
            self.editing_text = None
            if self.text_edit:
                self.text_edit.hide()
            self.parent_editor.layer_list.clearSelection()
            self.update()

    def start_text_edit(self, layer):
        """Начало редактирования текста"""
        self.editing_text = self.parent_editor.layers.index(layer)

        # Установка текста и шрифта
        self.text_edit.setPlainText(layer['text'])
        self.text_edit.setFont(QFont(layer['font'], layer['font_size']))
        self.text_edit.setAlignment(layer['alignment'])

        # Отключение автоматического переноса строк
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)

        # Настройка документа без переносов
        option = QTextOption()
        option.setWrapMode(QTextOption.NoWrap)
        self.text_edit.document().setDefaultTextOption(option)

        # Установка цвета текста
        self.text_edit.setStyleSheet(f"""
            background-color: white; 
            border: 2px solid blue;
            color: {layer['color']};
            padding: 2px;
        """)

        # Позиционирование редактора
        rect = QRect(
            int(layer['rect'].x() * self.scale_factor),
            int(layer['rect'].y() * self.scale_factor),
            int(layer['rect'].width() * self.scale_factor),
            int(layer['rect'].height() * self.scale_factor)
        )
        self.text_edit.setGeometry(rect)
        self.text_edit.setVisible(True)
        self.text_edit.setFocus()

        # Отключение полос прокрутки
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.update()

    def finish_text_edit(self):
        """Завершение редактирования текста"""
        if self.editing_text is not None:
            layer = self.parent_editor.layers[self.editing_text]
            layer['text'] = self.text_edit.toPlainText()

            # Фиксация окончательных размеров
            doc = self.text_edit.document()
            doc.adjustSize()
            layer['rect'].setWidth(doc.idealWidth() / self.scale_factor + 10 / self.scale_factor)
            layer['rect'].setHeight(doc.size().height() / self.scale_factor + 10 / self.scale_factor)

            # Обновление списка слоев
            text = layer['text']
            self.parent_editor.layer_list.item(self.editing_text).setText(
                f"Текст: {text[:15] + '...' if len(text) > 15 else text}")

            # Скрытие редактора
            self.text_edit.setVisible(False)
            self.editing_text = None

            # Добавление в историю
            self.parent_editor.add_to_history()
            self.update()

    def mouseDoubleClickEvent(self, event):
        """Обработка двойного клика мыши"""
        if event.button() == Qt.LeftButton and self.current_item is not None:
            layer = self.parent_editor.layers[self.current_item]
            if layer['type'] == 'text':
                rect = QRect(
                    int(layer['rect'].x() * self.scale_factor),
                    int(layer['rect'].y() * self.scale_factor),
                    int(layer['rect'].width() * self.scale_factor),
                    int(layer['rect'].height() * self.scale_factor)
                )
                if rect.contains(event.pos()):
                    self.start_text_edit(layer)

    def keyPressEvent(self, event):
        """Обработка нажатия клавиш"""
        if self.current_item is not None and not self.editing_text:
            layer = self.parent_editor.layers[self.current_item]
            step = 5 / self.scale_factor

            if event.key() == Qt.Key_Left:
                layer['rect'].moveLeft(layer['rect'].left() - step)
                self.parent_editor.add_to_history()
                self.update()
            elif event.key() == Qt.Key_Right:
                layer['rect'].moveLeft(layer['rect'].left() + step)
                self.parent_editor.add_to_history()
                self.update()
            elif event.key() == Qt.Key_Up:
                layer['rect'].moveTop(layer['rect'].top() - step)
                self.parent_editor.add_to_history()
                self.update()
            elif event.key() == Qt.Key_Down:
                layer['rect'].moveTop(layer['rect'].top() + step)
                self.parent_editor.add_to_history()
                self.update()
            elif event.key() == Qt.Key_Delete:
                # Проверяем, что слой существует
                if 0 <= self.current_item < len(self.parent_editor.layers):
                    self.parent_editor.delete_layer()
            elif event.key() == Qt.Key_F:
                if layer['type'] == 'text':
                    self.start_text_edit(layer)
        elif event.key() == Qt.Key_Escape:
            if self.editing_text is not None:
                self.finish_text_edit()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        """Обработка перемещения мыши"""
        self.cursor_pos = event.pos()

        # Сброс подсвечивания перед проверкой
        old_hovered = self.hovered_item
        self.hovered_item = None

        # Проверка наведения на объекты (только если не выполняются другие операции)
        if not (self.dragging or self.resizing or self.rotating):
            # Идем от верхнего слоя (первого в списке) к нижнему (последнему)
            for i in range(len(self.parent_editor.layers)):
                layer = self.parent_editor.layers[i]
                if not layer['visible']:
                    continue

                scaled_rect = QRect(
                    int(layer['rect'].x() * self.scale_factor),
                    int(layer['rect'].y() * self.scale_factor),
                    int(layer['rect'].width() * self.scale_factor),
                    int(layer['rect'].height() * self.scale_factor)
                )

                if layer['rotation'] != 0:
                    # Для повернутых объектов используем более точную проверку
                    transform = QTransform()
                    transform.translate(scaled_rect.center().x(), scaled_rect.center().y())
                    transform.rotate(layer['rotation'])
                    transform.translate(-scaled_rect.width() / 2, -scaled_rect.height() / 2)
                    inverted_transform = transform.inverted()[0]
                    local_pos = inverted_transform.map(event.pos())
                    if QRect(0, 0, scaled_rect.width(), scaled_rect.height()).contains(local_pos):
                        self.hovered_item = i
                        break
                elif scaled_rect.contains(event.pos()):
                    self.hovered_item = i
                    break  # Прерываем цикл после нахождения первого подходящего слоя

        # Обновление только если состояние подсветки изменилось
        if old_hovered != self.hovered_item:
            self.update()

        # Вращение объекта
        if self.rotating and self.current_item is not None:
            layer = self.parent_editor.layers[self.current_item]
            scaled_rect = QRect(
                int(layer['rect'].x() * self.scale_factor),
                int(layer['rect'].y() * self.scale_factor),
                int(layer['rect'].width() * self.scale_factor),
                int(layer['rect'].height() * self.scale_factor)
            )
            center = scaled_rect.center()

            # Расчет угла между центром и позицией мыши
            angle = np.arctan2(event.pos().y() - center.y(), event.pos().x() - center.x()) * 180 / np.pi
            layer['rotation'] = (angle + 90) % 360  # +90 для начала сверху

            self.update()
            return

        # Изменение размера объекта
        if self.resizing and self.current_item is not None:
            layer = self.parent_editor.layers[self.current_item]
            rect = layer['rect']
            pos = event.pos()
            delta = (pos - self.start_pos) / self.scale_factor

            new_rect = QRect(rect)

            if 'top' in self.resizing:
                new_rect.setTop(int(rect.top() + delta.y()))
            if 'bottom' in self.resizing:
                new_rect.setBottom(int(rect.bottom() + delta.y()))
            if 'left' in self.resizing:
                new_rect.setLeft(int(rect.left() + delta.x()))
            if 'right' in self.resizing:
                new_rect.setRight(int(rect.right() + delta.x()))
            if 'center' in self.resizing:
                if self.resizing == 'top-center':
                    new_rect.setTop(int(rect.top() + delta.y()))
                elif self.resizing == 'bottom-center':
                    new_rect.setBottom(int(rect.bottom() + delta.y()))
                elif self.resizing == 'left-center':
                    new_rect.setLeft(int(rect.left() + delta.x()))
                elif self.resizing == 'right-center':
                    new_rect.setRight(int(rect.right() + delta.x()))

            # Сохранение пропорций для угловых маркеров
            if self.resizing in ['top-left', 'top-right', 'bottom-left', 'bottom-right']:
                aspect = rect.width() / rect.height()
                if self.resizing in ['top-left', 'bottom-right']:
                    new_width = new_rect.width()
                    new_height = int(new_width / aspect)
                    if self.resizing == 'top-left':
                        new_rect.setTop(rect.top() - (new_height - rect.height()))
                    else:
                        new_rect.setBottom(rect.bottom() + (new_height - rect.height()))
                else:
                    new_height = new_rect.height()
                    new_width = int(new_height * aspect)
                    if self.resizing == 'top-right':
                        new_rect.setRight(rect.right() + (new_width - rect.width()))
                    else:
                        new_rect.setLeft(rect.left() - (new_width - rect.width()))

            # Минимальный размер
            if new_rect.width() < 20:
                if 'left' in self.resizing:
                    new_rect.setLeft(new_rect.right() - 20)
                else:
                    new_rect.setRight(new_rect.left() + 20)
            if new_rect.height() < 20:
                if 'top' in self.resizing:
                    new_rect.setTop(new_rect.bottom() - 20)
                else:
                    new_rect.setBottom(new_rect.top() + 20)

            layer['rect'] = new_rect
            self.start_pos = event.pos()
            self.update()
            return

        # Перемещение объекта
        if self.dragging and self.current_item is not None:
            layer = self.parent_editor.layers[self.current_item]
            rect = layer['rect']
            delta = (event.pos() - self.start_pos) / self.scale_factor
            new_rect = rect.translated(int(delta.x()), int(delta.y()))
            layer['rect'] = new_rect
            self.start_pos = event.pos()
            self.update()
            return

        # Изменение формы курсора
        if self.current_item is not None and self.editing_text is None:
            layer = self.parent_editor.layers[self.current_item]
            rect = QRect(
                int(layer['rect'].x() * self.scale_factor),
                int(layer['rect'].y() * self.scale_factor),
                int(layer['rect'].width() * self.scale_factor),
                int(layer['rect'].height() * self.scale_factor)
            )

            # Проверка на маркер вращения
            rotation_handle = QRect(rect.center().x() - 4, rect.top() - 30, 8, 8)
            if rotation_handle.contains(event.pos()):
                self.setCursor(Qt.PointingHandCursor)
                return

            # Проверка на маркеры изменения размера
            size = 8
            handles = [
                QRect(rect.left() - size // 2, rect.top() - size // 2, size, size),  # Верхний-левый
                QRect(rect.right() - size // 2, rect.top() - size // 2, size, size),  # Верхний-правый
                QRect(rect.left() - size // 2, rect.bottom() - size // 2, size, size),  # Нижний-левый
                QRect(rect.right() - size // 2, rect.bottom() - size // 2, size, size),  # Нижний-правый
                QRect(rect.center().x() - size // 2, rect.top() - size // 2, size, size),  # Верхний-центральный
                QRect(rect.center().x() - size // 2, rect.bottom() - size // 2, size, size),  # Нижний-центральный
                QRect(rect.left() - size // 2, rect.center().y() - size // 2, size, size),  # Левый-центральный
                QRect(rect.right() - size // 2, rect.center().y() - size // 2, size, size)  # Правый-центральный
            ]

            for handle in handles:
                if handle.contains(event.pos()):
                    # Определение формы курсора
                    if handle == handles[0] or handle == handles[3]:  # Верхний-левый или нижний-правый
                        self.setCursor(Qt.SizeFDiagCursor)
                    elif handle == handles[1] or handle == handles[2]:  # Верхний-правый или нижний-левый
                        self.setCursor(Qt.SizeBDiagCursor)
                    elif handle == handles[4] or handle == handles[5]:  # Верхний-центральный или нижний-центральный
                        self.setCursor(Qt.SizeVerCursor)
                    else:  # Левый-центральный или правый-центральный
                        self.setCursor(Qt.SizeHorCursor)
                    return

            # Курсор перемещения внутри объекта
            if rect.contains(event.pos()):
                self.setCursor(Qt.SizeAllCursor)
                return

        # Курсор по умолчанию
        self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши"""
        if event.button() == Qt.LeftButton:
            if self.dragging or self.resizing or self.rotating:
                self.parent_editor.add_to_history()

            self.dragging = None
            self.resizing = None
            self.rotating = None

    def wheelEvent(self, event):
        """Обработка прокрутки колеса мыши с сохранением позиции объектов"""
        if event.modifiers() & Qt.ControlModifier:
            event.accept()

            # Получаем scroll area
            scroll_area = self.parent().findChild(QScrollArea)

            # Запоминаем текущую позицию курсора относительно холста
            mouse_pos = event.pos()

            # Определяем направление и силу масштабирования
            zoom_direction = 1 if event.angleDelta().y() > 0 else -1
            zoom_factor = 1.1 ** zoom_direction

            # Вычисляем новый масштаб с ограничениями
            new_scale = self.scale_factor * zoom_factor
            new_scale = max(0.1, min(5.0, new_scale))

            # Вычисляем коэффициент изменения масштаба
            scale_change = new_scale / self.scale_factor

            # Обновляем масштаб
            self.scale_factor = new_scale

            # Обновляем размер холста
            new_width = int(self.minimumWidth() * self.scale_factor)
            new_height = int(self.minimumHeight() * self.scale_factor)
            self.resize(new_width, new_height)

            # Корректируем позицию прокрутки, если scroll area найден
            if scroll_area:
                # Вычисляем новые позиции прокрутки
                h_scroll = scroll_area.horizontalScrollBar().value()
                v_scroll = scroll_area.verticalScrollBar().value()

                # Корректируем позицию с учетом масштабирования
                new_h_scroll = (h_scroll + mouse_pos.x()) * scale_change - mouse_pos.x()
                new_v_scroll = (v_scroll + mouse_pos.y()) * scale_change - mouse_pos.y()

                # Устанавливаем новые значения прокрутки
                scroll_area.horizontalScrollBar().setValue(int(new_h_scroll))
                scroll_area.verticalScrollBar().setValue(int(new_v_scroll))
            else:
                # Если scroll area не найден, просто центрируем холст
                self.center_canvas()

            self.last_scale_factor = self.scale_factor
            self.update()
        else:
            super().wheelEvent(event)


class NewCanvasDialog(QDialog):
    """Диалог создания нового холста"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый холст")
        self.setModal(True)

        layout = QGridLayout()

        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 5000)
        self.width_spin.setValue(800)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 5000)
        self.height_spin.setValue(600)

        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)

        layout.addWidget(QLabel("Ширина:"), 0, 0)
        layout.addWidget(self.width_spin, 0, 1)
        layout.addWidget(QLabel("Высота:"), 1, 0)
        layout.addWidget(self.height_spin, 1, 1)
        layout.addWidget(self.ok_button, 2, 0)
        layout.addWidget(self.cancel_button, 2, 1)

        self.setLayout(layout)


class ExportJpgDialog(QDialog):
    """Диалог настройки параметров экспорта JPG"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Параметры экспорта JPG")
        self.setModal(True)

        layout = QGridLayout()

        # Качество изображения
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(95)
        self.quality_spin.setSuffix("%")

        # Размер изображения
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "Оригинальный размер",
            "50% от оригинала",
            "25% от оригинала",
            "1920x1080 (Full HD)",
            "1280x720 (HD)",
            "800x600"
        ])

        # Кнопки
        self.ok_button = QPushButton("Экспорт")
        self.ok_button.clicked.connect(self.accept)

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)

        # Добавление элементов в layout
        layout.addWidget(QLabel("Качество:"), 0, 0)
        layout.addWidget(self.quality_spin, 0, 1)
        layout.addWidget(QLabel("Размер:"), 1, 0)
        layout.addWidget(self.size_combo, 1, 1)
        layout.addWidget(self.ok_button, 2, 0)
        layout.addWidget(self.cancel_button, 2, 1)

        self.setLayout(layout)

    def get_quality(self):
        return self.quality_spin.value()

    def get_target_size(self, original_size):
        """Возвращает целевой размер изображения"""
        text = self.size_combo.currentText()
        width, height = original_size

        if text == "Оригинальный размер":
            return (width, height)
        elif text == "50% от оригинала":
            return (int(width * 0.5), int(height * 0.5))
        elif text == "25% от оригинала":
            return (int(width * 0.25), int(height * 0.25))
        elif text == "1920x1080 (Full HD)":
            return (1920, 1080)
        elif text == "1280x720 (HD)":
            return (1280, 720)
        elif text == "800x600":
            return (800, 600)

        return (width, height)

class PostcardEditor(QMainWindow):
    """Главное окно редактора открыток"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Редактор открыток (" + CODE_VERSION + ")")
        self.setGeometry(100, 100, 1000, 700)
        self.clipboard = None  # Буфер обмена для копирования/вставки
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.handle_resize)
        self.layers = []  # Список слоев
        self.history = []  # История изменений
        self.current_history_index = -1  # Текущая позиция в истории
        self.init_ui()
        self.setup_shortcuts()

    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Центральный виджет и основной макет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Область холста
        self.canvas = Canvas(self)
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.canvas)
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area, 1)

        # Правая панель
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(5, 5, 5, 5)

        # Виджет истории
        history_group = QVBoxLayout()
        history_group.addWidget(QLabel("История изменений:"))

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.history_item_clicked)
        history_group.addWidget(self.history_list)

        right_panel.addLayout(history_group)

        # Список слоев
        self.layer_list = QListWidget()
        self.layer_list.itemSelectionChanged.connect(self.layer_selection_changed)
        self.layer_list.itemDoubleClicked.connect(self.layer_double_clicked)
        right_panel.addWidget(QLabel("Слои:"))
        right_panel.addWidget(self.layer_list)

        # Управление слоями
        layer_controls = QGridLayout()

        # Кнопки управления слоями
        self.move_up_button = QPushButton("Вверх")
        self.move_up_button.setIcon(self.get_icon('move_up'))
        self.move_up_button.clicked.connect(self.move_layer_up)
        layer_controls.addWidget(self.move_up_button, 0, 0)

        self.move_down_button = QPushButton("Вниз")
        self.move_down_button.setIcon(self.get_icon('move_down'))
        self.move_down_button.clicked.connect(self.move_layer_down)
        layer_controls.addWidget(self.move_down_button, 0, 1)

        self.visible_checkbox = QPushButton("Скрыть")
        self.visible_checkbox.setIcon(self.get_icon('visible'))
        self.visible_checkbox.setCheckable(True)
        self.visible_checkbox.setChecked(True)
        self.visible_checkbox.clicked.connect(self.toggle_layer_visibility)
        layer_controls.addWidget(self.visible_checkbox, 1, 0)

        delete_button = QPushButton("Удалить")
        delete_button.setIcon(self.get_icon('delete'))
        delete_button.clicked.connect(self.delete_layer)
        layer_controls.addWidget(delete_button, 1, 1)

        right_panel.addLayout(layer_controls)

        # Управление текстом
        right_panel.addWidget(QLabel("Свойства текста:"))

        self.text_edit = QTextEdit()
        self.text_edit.setMaximumHeight(100)
        self.text_edit.textChanged.connect(self.update_text_layer)
        right_panel.addWidget(self.text_edit)

        self.alignment_combo = QComboBox()
        self.alignment_combo.addItems(["Выравнивание: слева", "Выравнивание: по центру", "Выравнивание: справа"])
        self.alignment_combo.currentIndexChanged.connect(self.change_text_alignment)
        right_panel.addWidget(self.alignment_combo)

        font_button = QPushButton("Шрифт...")
        font_button.setIcon(self.get_icon('font'))
        font_button.clicked.connect(self.change_font)
        right_panel.addWidget(font_button)

        color_button = QPushButton("Цвет...")
        color_button.setIcon(self.get_icon('color'))
        color_button.clicked.connect(self.change_color)
        right_panel.addWidget(color_button)

        right_panel.addStretch()

        main_layout.addLayout(right_panel)

        # Главное меню
        self.init_menu_bar()

        # Панель инструментов
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # Действия на панели инструментов
        new_action = QAction(self.get_icon('new'), "Новый холст", self)
        new_action.triggered.connect(self.new_canvas)
        toolbar.addAction(new_action)

        open_action = QAction(self.get_icon('open'), "Открыть проект", self)
        open_action.triggered.connect(self.open_project)
        toolbar.addAction(open_action)

        save_action = QAction(self.get_icon('save'), "Сохранить проект", self)
        save_action.triggered.connect(self.save_project)
        toolbar.addAction(save_action)

        export_action = QAction(self.get_icon('export'), "Экспорт в JPG", self)
        export_action.triggered.connect(self.export_jpg)
        toolbar.addAction(export_action)

        toolbar.addSeparator()

        add_image_action = QAction(self.get_icon('add_image'), "Добавить изображение", self)
        add_image_action.triggered.connect(self.add_image)
        toolbar.addAction(add_image_action)

        add_text_action = QAction(self.get_icon('add_text'), "Добавить текст", self)
        add_text_action.triggered.connect(self.add_text)
        toolbar.addAction(add_text_action)

        toolbar.addSeparator()

        undo_action = QAction(self.get_icon('undo'), "Отменить", self)
        undo_action.triggered.connect(self.undo)
        toolbar.addAction(undo_action)

        redo_action = QAction(self.get_icon('redo'), "Повторить", self)
        redo_action.triggered.connect(self.redo)
        toolbar.addAction(redo_action)

        # Строка состояния
        self.statusBar().showMessage("Готово")

    def copy_object(self):
        """Копирование выбранного объекта в буфер обмена"""
        if self.canvas.current_item is None:
            return

        index = self.canvas.current_item
        layer = self.layers[index]

        # Создаем копию слоя, преобразуя сложные объекты в простые типы
        self.clipboard = {
            'type': layer['type'],
            'rect': {
                'x': layer['rect'].x(),
                'y': layer['rect'].y(),
                'width': layer['rect'].width(),
                'height': layer['rect'].height()
            },
            'visible': layer['visible'],
            'rotation': layer['rotation']
        }

        if layer['type'] == 'image':
            self.clipboard['path'] = layer['path']
        elif layer['type'] == 'text':
            self.clipboard.update({
                'text': layer['text'],
                'font': layer['font'],
                'font_size': layer['font_size'],
                'color': layer['color'],
                'alignment': int(layer['alignment'])  # Преобразуем в int
            })

        self.statusBar().showMessage("Объект скопирован в буфер", 2000)

    def paste_object(self):
        """Вставка объекта из буфера обмена"""
        if not hasattr(self, 'clipboard') or not self.clipboard:
            return

        # Создаем новый слой из буфера
        new_layer = {
            'type': self.clipboard['type'],
            'rect': QRect(
                self.clipboard['rect']['x'] + 20,
                self.clipboard['rect']['y'] + 20,
                self.clipboard['rect']['width'],
                self.clipboard['rect']['height']
            ),
            'visible': self.clipboard['visible'],
            'rotation': self.clipboard['rotation']
        }

        if self.clipboard['type'] == 'image':
            new_layer['path'] = self.clipboard['path']
        elif self.clipboard['type'] == 'text':
            new_layer.update({
                'text': self.clipboard['text'],
                'font': self.clipboard['font'],
                'font_size': self.clipboard['font_size'],
                'color': self.clipboard['color'],
                'alignment': self.clipboard['alignment']
            })

        # Добавляем новый слой
        self.layers.insert(0, new_layer)

        # Обновляем список слоев
        if new_layer['type'] == 'image':
            self.layer_list.insertItem(0, f"Изображение: {os.path.basename(new_layer['path'])}")
        elif new_layer['type'] == 'text':
            text = new_layer['text']
            self.layer_list.insertItem(0, f"Текст: {text[:15] + '...' if len(text) > 15 else text}")

        # Выбираем новый слой
        self.layer_list.setCurrentRow(0)
        self.canvas.current_item = 0
        self.canvas.update()
        self.add_to_history()
        self.statusBar().showMessage("Объект вставлен из буфера", 2000)

    def setup_shortcuts(self):
        """Настройка горячих клавиш"""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        # Перемещение слоев вверх/вниз
        move_up_shortcut = QShortcut(QKeySequence("Ctrl+Up"), self)
        move_up_shortcut.activated.connect(self.move_layer_up)

        move_down_shortcut = QShortcut(QKeySequence("Ctrl+Down"), self)
        move_down_shortcut.activated.connect(self.move_layer_down)

        # Переключение видимости слоя
        toggle_visible_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        toggle_visible_shortcut.activated.connect(self.toggle_layer_visibility)

        # Увеличение/уменьшение масштаба
        zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+Plus"), self)
        zoom_in_shortcut.activated.connect(self.zoom_in)

        zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+Minus"), self)
        zoom_out_shortcut.activated.connect(self.zoom_out)

        # Подгонка под размер окна
        fit_view_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        fit_view_shortcut.activated.connect(self.canvas.fit_to_view)


    def zoom_in(self):
        """Увеличение масштаба"""
        event = QWheelEvent(QPointF(), QPointF(), QPoint(0, 120), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        self.canvas.wheelEvent(event)

    def zoom_out(self):
        """Уменьшение масштаба"""
        event = QWheelEvent(QPointF(), QPointF(), QPoint(0, -120), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        self.canvas.wheelEvent(event)

    def init_menu_bar(self):
        """Инициализация меню"""
        menubar = self.menuBar()

        # Меню Файл
        file_menu = menubar.addMenu("Файл")

        new_action = QAction(self.get_icon('new'), "Новый", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_canvas)
        file_menu.addAction(new_action)

        open_action = QAction(self.get_icon('open'), "Открыть...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        save_action = QAction(self.get_icon('save'), "Сохранить", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        export_action = QAction(self.get_icon('export'), "Экспорт в JPG...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.export_jpg)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("Выход", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню Правка
        edit_menu = menubar.addMenu("Правка")

        undo_action = QAction(self.get_icon('undo'), "Отменить", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction(self.get_icon('redo'), "Повторить", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        copy_action = QAction("Копировать", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_object)
        edit_menu.addAction(copy_action)

        paste_action = QAction("Вставить", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.paste_object)
        edit_menu.addAction(paste_action)

        # Меню Слой
        layer_menu = menubar.addMenu("Слой")

        add_image_action = QAction(self.get_icon('add_image'), "Добавить изображение", self)
        add_image_action.setShortcut("Ctrl+I")
        add_image_action.triggered.connect(self.add_image)
        layer_menu.addAction(add_image_action)

        add_text_action = QAction(self.get_icon('add_text'), "Добавить текст", self)
        add_text_action.setShortcut("Ctrl+T")
        add_text_action.triggered.connect(self.add_text)
        layer_menu.addAction(add_text_action)

        # Меню Справка
        help_menu = menubar.addMenu("Справка")

        about_action = QAction(self.get_icon('about'), "О программе", self)
        about_action.setShortcut("F1")
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        # Строка состояния
        self.statusBar().showMessage("Готово")

    def get_icon(self, icon_name):
        """Получение иконки из файла с поддержкой Linux"""
        # Словарь соответствия имен иконок файлам
        icon_files = {
            'new': "new.png",
            'open': "open.png",
            'save': "save.png",
            'export': "export.png",
            'add_image': "add_image.png",
            'add_text': "add_text.png",
            'undo': "undo.png",
            'redo': "redo.png",
            'move_up': "move_up.png",
            'move_down': "move_down.png",
            'visible': "visible.png",
            'delete': "delete.png",
            'font': "font.png",
            'color': "color.png",
            'about': "about.png"
        }

        # Определяем базовый путь
        if getattr(sys, 'frozen', False):
            # Режим собранного exe
            base_path = sys._MEIPASS
            icon_path = os.path.join(base_path, "icons", icon_files.get(icon_name, "default.png"))
        else:
            # Режим разработки - ищем иконки в нескольких возможных местах
            base_path = os.path.dirname(os.path.abspath(__file__))

            # Вариант 1: иконки в подпапке icons рядом со скриптом
            icon_path = os.path.join(base_path, "icons", icon_files.get(icon_name, "default.png"))

            # Вариант 2: для PyCharm и других IDE, где рабочая директория может быть другой
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_path, "..", "icons", icon_files.get(icon_name, "default.png"))

            # Вариант 3: абсолютный путь к /usr/share/ для системных установок
            if not os.path.exists(icon_path):
                icon_path = os.path.join("/usr/share/postcard_editor/icons", icon_files.get(icon_name, "default.png"))

        if os.path.exists(icon_path):
            return QIcon(icon_path)
        else:
            print(f"[DEBUG] Icon search paths:")
            print(f"1. {os.path.join(base_path, 'icons', icon_files.get(icon_name, 'default.png'))}")
            print(f"2. {os.path.join(base_path, '..', 'icons', icon_files.get(icon_name, 'default.png'))}")
            print(f"3. {os.path.join('/usr/share/postcard_editor/icons', icon_files.get(icon_name, 'default.png'))}")
            return self.style().standardIcon(QStyle.SP_FileIcon)

    def show_about_dialog(self):
        """Отображение диалога 'О программе' с прокруткой"""
        about_text = """
        <h2>Редактор открыток</h2>
        <p><b>Версия """+CODE_VERSION+"""</b></p>

        <h3>Описание программы</h3>
        <p>Программа для создания и редактирования открыток с поддержкой многослойности.</p>
        <p>Написана на Python с использованием библиотеки PyQt5 для графического интерфейса.</p>

        <h3>Используемые модули</h3>
        <ul>
            <li>PyQt5 - для графического интерфейса</li>
            <li>Pillow (PIL) - для работы с изображениями</li>
            <li>NumPy - для математических вычислений</li>
        </ul>

        <h3>Основные возможности</h3>
        <ul>
            <li>Создание нового холста с произвольными размерами</li>
            <li>Добавление текстовых и графических слоев</li>
            <li>Редактирование свойств текста (шрифт, цвет, выравнивание)</li>
            <li>Перемещение, масштабирование и вращение элементов</li>
            <li>Управление слоями (видимость, порядок, удаление)</li>
            <li>Сохранение и загрузка проектов в собственном формате (.pep)</li>
            <li>Экспорт в формат JPG</li>
            <li>Отмена и повтор действий</li>
        </ul>

        <h3>Как пользоваться</h3>
        <ol>
            <li>Создайте новый холст (Файл → Новый)</li>
            <li>Добавьте изображения и текст через меню "Слой" или панель инструментов</li>
            <li>Выделяйте элементы для редактирования (клик левой кнопкой мыши)</li>
            <li>Используйте маркеры для изменения размера и вращения</li>
            <li>Двойной клик по тексту открывает редактор текста</li>
            <li>Управляйте слоями через правую панель</li>
            <li>Сохраните проект (Файл → Сохранить) или экспортируйте в JPG</li>
        </ol>

        <h3>Горячие клавиши</h3>
        <ul>
            <li>Ctrl+N - Новый холст</li>
            <li>Ctrl+O - Открыть проект</li>
            <li>Ctrl+S - Сохранить проект</li>
            <li>Ctrl+E - Экспорт в JPG</li>
            <li>Ctrl+Z - Отменить</li>
            <li>Ctrl+Y - Повторить</li>
            <li>Ctrl+C - Копировать</li>
            <li>Ctrl+V - Вставить</li>
            <li>Ctrl+I - Добавить изображение</li>
            <li>Ctrl+T - Добавить текст</li>
            <li>Ctrl+Up/Down - Переместить слой вверх/вниз</li>
            <li>Ctrl+H - Скрыть/показать слой</li>
            <li>Ctrl+Plus/Minus - Увеличить/уменьшить масштаб</li>
            <li>Ctrl+0 - Подогнать под размер окна</li>
            <li>Стрелки - Перемещение выделенного элемента</li>
            <li>Delete - Удалить выделенный элемент</li>
            <li>F - Редактировать текст (при выделенном текстовом слое)</li>
        </ul>

        <h3>Системные требования</h3>
        <ul>            
            <li>Рекомендуется 4 ГБ оперативной памяти</li>
            <li>Разрешение экрана не менее 1024×768</li>
        </ul>

        <p>© 2025 Димитриев А.В.</p>
        """

        # Создаем диалоговое окно с прокруткой
        dialog = QDialog(self)
        dialog.setWindowTitle("О программе")
        dialog.setMinimumSize(500, 400)  # Минимальный размер окна

        # Создаем scroll area
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)

        # Создаем виджет для содержимого
        content = QWidget()
        scroll.setWidget(content)

        # Создаем layout для содержимого
        layout = QVBoxLayout(content)

        # Добавляем текст в QLabel
        label = QLabel(about_text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        layout.addWidget(label)

        # Добавляем кнопку закрытия
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(dialog.close)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        # Устанавливаем layout для диалога
        main_layout = QVBoxLayout(dialog)
        main_layout.addWidget(scroll)

        dialog.exec_()

    def move_layer_up(self):
        """Перемещение выбранного слоя вверх"""
        if self.canvas.current_item is None or self.canvas.current_item == 0:
            return

        current_index = self.canvas.current_item
        new_index = current_index - 1

        # Перемещение слоя в списке
        self.layers.insert(new_index, self.layers.pop(current_index))

        # Обновление списка слоев
        item = self.layer_list.takeItem(current_index)
        self.layer_list.insertItem(new_index, item)

        # Обновление текущего выбранного элемента
        self.canvas.current_item = new_index
        self.layer_list.setCurrentRow(new_index)
        self.add_to_history()

    def move_layer_down(self):
        """Перемещение выбранного слоя вниз"""
        if (self.canvas.current_item is None or
                self.canvas.current_item == len(self.layers) - 1):
            return

        current_index = self.canvas.current_item
        new_index = current_index + 1

        # Перемещение слоя в списке
        self.layers.insert(new_index, self.layers.pop(current_index))

        # Обновление списка слоев
        item = self.layer_list.takeItem(current_index)
        self.layer_list.insertItem(new_index, item)

        # Обновление текущего выбранного элемента
        self.canvas.current_item = new_index
        self.layer_list.setCurrentRow(new_index)
        self.add_to_history()

    def resizeEvent(self, event):
        """Обработка изменения размера окна"""
        super().resizeEvent(event)
        self.resize_timer.start(100)

    def handle_resize(self):
        """Обработка завершения изменения размера"""
        if hasattr(self.canvas, 'scale_factor'):
            self.canvas.center_canvas_timer.start(100)

    def update_history_list(self):
        """Обновление списка истории"""
        self.history_list.clear()
        for i, state in enumerate(self.history):
            self.history_list.addItem(f"Состояние {i + 1}")

        if self.current_history_index >= 0:
            self.history_list.setCurrentRow(self.current_history_index)

    def restore_history_state(self, index):
        """Восстановление состояния из истории"""
        if index < 0 or index >= len(self.history):
            return

        self.current_history_index = index
        self.restore_from_history()

    def history_item_clicked(self, item):
        """Обработка выбора элемента истории"""
        index = self.history_list.row(item)
        self.restore_history_state(index)

    def new_canvas(self):
        """Создание нового холста"""
        dialog = NewCanvasDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            width = dialog.width_spin.value()
            height = dialog.height_spin.value()

            self.layers = []
            self.history = []
            self.current_history_index = -1
            self.layer_list.clear()
            self.canvas.current_item = None
            self.canvas.setMinimumSize(width, height)

            # Центрирование нового холста
            QApplication.processEvents()
            self.canvas.fit_to_view()
            self.canvas.center_canvas_timer.start(100)

            self.canvas.update()
            self.add_to_history()

    def add_image(self):
        """Добавление изображения на холст"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Открыть изображение", "",
                                                   "Изображения (*.png *.jpg *.jpeg)")
        if not file_path:
            return

        image = QImage(file_path)
        if image.isNull():
            QMessageBox.warning(self, "Предупреждение", "Не удалось загрузить изображение.")
            return

        # Если это первый слой, создаем холст с размерами изображения
        if not self.layers:
            self.canvas.setMinimumSize(image.width(), image.height())
            self.canvas.resize(image.width(), image.height())

            # Получаем размеры области просмотра
            scroll_area = self.findChild(QScrollArea)
            if scroll_area:
                viewport_size = scroll_area.viewport().size()

                # Если изображение больше области просмотра, масштабируем
                if (image.width() > viewport_size.width() or
                        image.height() > viewport_size.height()):
                    # Вычисляем коэффициент масштабирования
                    width_ratio = viewport_size.width() / image.width()
                    height_ratio = viewport_size.height() / image.height()
                    scale_factor = min(width_ratio, height_ratio) * 0.9  # 90% от максимального размера

                    # Применяем масштабирование
                    self.canvas.scale_factor = scale_factor
                    self.canvas.resize(
                        int(image.width() * scale_factor),
                        int(image.height() * scale_factor))

                    # Центрируем холст
                    self.canvas.center_canvas()

            rect = QRect(0, 0, image.width(), image.height())
        else:
            rect = QRect(50, 50, image.width(), image.height())

        # Добавление слоя
        self.layers.insert(0, {
            'type': 'image',
            'path': file_path,
            'rect': rect,
            'visible': True,
            'rotation': 0
        })

        # Добавление в список слоев
        self.layer_list.insertItem(0, f"Изображение: {os.path.basename(file_path)}")
        self.layer_list.setCurrentRow(0)
        self.canvas.current_item = 0
        self.canvas.update()
        self.add_to_history()

    def add_text(self):
        """Добавление текстового слоя"""
        if not self.layers and not hasattr(self.canvas, 'minimumSize'):
            self.canvas.setMinimumSize(800, 600)

        rect = QRect(100, 100, 200, 100)
        text = "Новый текст"

        # Добавление текстового слоя
        self.layers.insert(0, {
            'type': 'text',
            'text': text,
            'rect': rect,
            'visible': True,
            'font': "Monotype Corsiva Bold",
            'font_size': 24,
            'color': "#000000",
            'rotation': 0,
            'alignment': Qt.AlignLeft | Qt.AlignTop
        })

        # Добавление в список слоев
        self.layer_list.insertItem(0, f"Текст: {text[:15] + '...' if len(text) > 15 else text}")
        self.layer_list.setCurrentRow(0)
        self.canvas.current_item = 0
        self.text_edit.setPlainText(text)
        self.canvas.update()
        self.add_to_history()

    def layer_selection_changed(self):
        """Обработка изменения выбранного слоя"""
        if not self.layer_list.selectedItems() or not self.layers:
            self.canvas.current_item = None
            if hasattr(self.canvas, 'text_edit_widget') and self.canvas.text_edit_widget:
                self.canvas.text_edit_widget.hide()
            self.canvas.editing_text = None
            self.text_edit.setEnabled(False)
            self.canvas.update()
            return

        index = self.layer_list.currentRow()
        if 0 <= index < len(self.layers):  # Добавлена проверка на корректность индекса
            self.canvas.current_item = index
            layer = self.layers[index]

            self.visible_checkbox.setChecked(layer['visible'])
            self.visible_checkbox.setText("Скрыть" if layer['visible'] else "Показать")

            if layer['type'] == 'text':
                self.text_edit.setEnabled(True)
                self.text_edit.setPlainText(layer['text'])

                # Обновление выравнивания
                if layer['alignment'] & Qt.AlignHCenter:
                    self.alignment_combo.setCurrentIndex(1)
                elif layer['alignment'] & Qt.AlignRight:
                    self.alignment_combo.setCurrentIndex(2)
                else:
                    self.alignment_combo.setCurrentIndex(0)
            else:
                self.text_edit.setEnabled(False)

            self.canvas.update()

    def layer_double_clicked(self, item):
        """Обработка двойного клика по слою"""
        index = self.layer_list.row(item)
        if index < 0 or index >= len(self.layers):
            return

        layer = self.layers[index]
        if layer['type'] == 'text':
            self.layer_list.setCurrentRow(index)
            self.canvas.start_text_edit(layer)

    def toggle_layer_visibility(self):
        """Переключение видимости слоя"""
        if self.canvas.current_item is None:
            return

        index = self.canvas.current_item
        self.layers[index]['visible'] = not self.layers[index]['visible']
        self.visible_checkbox.setText("Скрыть" if self.layers[index]['visible'] else "Показать")
        self.canvas.update()
        self.add_to_history()

    def delete_layer(self):
        """Удаление выбранного слоя"""
        if self.canvas.current_item is None or not self.layers:
            return

        index = self.canvas.current_item
        if 0 <= index < len(self.layers):  # Проверка на корректность индекса
            self.layers.pop(index)
            self.layer_list.takeItem(index)

            # Обновляем текущий выбранный элемент
            if self.layers:
                new_index = min(index, len(self.layers) - 1)
                self.layer_list.setCurrentRow(new_index)
                self.canvas.current_item = new_index
            else:
                self.layer_list.clear()
                self.canvas.current_item = None

            if hasattr(self.canvas, 'text_edit_widget') and self.canvas.text_edit_widget:
                self.canvas.text_edit_widget.hide()
            self.canvas.editing_text = None
            self.canvas.update()
            self.add_to_history()

    def update_text_layer(self):
        """Обновление текстового слоя при изменении текста"""
        if self.canvas.current_item is None or self.layers[self.canvas.current_item]['type'] != 'text':
            return

        index = self.canvas.current_item
        self.layers[index]['text'] = self.text_edit.toPlainText()

        # Обновление имени слоя
        text = self.layers[index]['text']
        self.layer_list.item(index).setText(f"Текст: {text[:15] + '...' if len(text) > 15 else text}")

        self.canvas.update()

    def change_text_alignment(self):
        """Изменение выравнивания текста"""
        if self.canvas.current_item is None or self.layers[self.canvas.current_item]['type'] != 'text':
            return

        index = self.alignment_combo.currentIndex()
        alignment = Qt.AlignLeft | Qt.AlignTop

        if index == 1:
            alignment = Qt.AlignHCenter | Qt.AlignTop
        elif index == 2:
            alignment = Qt.AlignRight | Qt.AlignTop

        self.layers[self.canvas.current_item]['alignment'] = alignment
        self.canvas.update()
        self.add_to_history()

    def change_font(self):
        """Изменение шрифта текста"""
        if self.canvas.current_item is None or self.layers[self.canvas.current_item]['type'] != 'text':
            return

        current_layer = self.layers[self.canvas.current_item]
        current_font = QFont(current_layer['font'], current_layer['font_size'])

        font, ok = QFontDialog.getFont(current_font, self, "Выберите шрифт")
        if ok:
            font_db = QFontDatabase()
            available_families = font_db.families()

            if font.family() in available_families:
                index = self.canvas.current_item
                self.layers[index]['font'] = font.family()
                self.layers[index]['font_size'] = font.pointSize()

                if self.canvas.editing_text == index:
                    self.canvas.text_edit.setFont(font)

                self.canvas.update()
                self.add_to_history()
            else:
                QMessageBox.warning(self, "Ошибка", "Выбранный шрифт недоступен")

    def change_color(self):
        """Изменение цвета текста"""
        if self.canvas.current_item is None or self.layers[self.canvas.current_item]['type'] != 'text':
            return

        color = QColorDialog.getColor()
        if color.isValid():
            index = self.canvas.current_item
            self.layers[index]['color'] = color.name()
            self.canvas.update()
            self.add_to_history()

    def save_project(self):
        """Сохранение проекта в файл"""
        if not self.layers:
            QMessageBox.warning(self, "Предупреждение", "Нет проекта для сохранения.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить проект", "",
                                                   "Проект редактора открыток (*.pep)")
        if not file_path:
            return

        if not file_path.endswith('.pep'):
            file_path += '.pep'

        # Подготовка данных проекта
        project_data = {
            'canvas_size': {
                'width': self.canvas.minimumSize().width(),
                'height': self.canvas.minimumSize().height()
            },
            'layers': []
        }

        # Обработка слоев
        for layer in self.layers:
            layer_data = {
                'type': layer['type'],
                'rect': {
                    'x': layer['rect'].x(),
                    'y': layer['rect'].y(),
                    'width': layer['rect'].width(),
                    'height': layer['rect'].height()
                },
                'visible': layer['visible'],
                'rotation': layer['rotation']
            }

            if layer['type'] == 'image':
                # Чтение данных изображения в base64
                with open(layer['path'], 'rb') as f:
                    image_data = f.read()
                import base64
                layer_data['image_data'] = base64.b64encode(image_data).decode('utf-8')
                layer_data['image_format'] = os.path.splitext(layer['path'])[1][1:].lower()

            elif layer['type'] == 'text':
                layer_data.update({
                    'text': layer['text'],
                    'font': layer['font'],
                    'font_size': layer['font_size'],
                    'color': layer['color'],
                    'alignment': int(layer['alignment'])
                })

            project_data['layers'].append(layer_data)

        # Сохранение файла проекта
        try:
            with open(file_path, 'w') as f:
                json.dump(project_data, f, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "Предупреждение", f"Не удалось сохранить проект: {str(e)}")
            return

        self.statusBar().showMessage(f"Проект сохранен в {file_path}", 5000)

    def open_project(self):
        """Открытие проекта из файла"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Открыть проект", "",
                                                   "Проект редактора открыток (*.pep)")
        if not file_path:
            return

        # Чтение файла проекта
        try:
            with open(file_path, 'r') as f:
                project_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Предупреждение", f"Не удалось открыть проект: {str(e)}")
            return

        # Очистка текущего проекта
        self.layers = []
        self.layer_list.clear()
        self.history = []
        self.current_history_index = -1

        # Установка размеров холста
        canvas_size = project_data['canvas_size']
        self.canvas.setMinimumSize(canvas_size['width'], canvas_size['height'])

        # Загрузка слоев
        for layer_data in project_data['layers']:
            layer = {
                'type': layer_data['type'],
                'rect': QRect(layer_data['rect']['x'], layer_data['rect']['y'],
                              layer_data['rect']['width'], layer_data['rect']['height']),
                'visible': layer_data['visible'],
                'rotation': layer_data['rotation']
            }

            if layer_data['type'] == 'image':
                try:
                    import base64
                    import tempfile

                    image_data = base64.b64decode(layer_data['image_data'])
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{layer_data['image_format']}") as tmp:
                        tmp.write(image_data)
                        tmp_path = tmp.name

                    layer['path'] = tmp_path
                    self.layers.append(layer)
                    self.layer_list.addItem(f"Изображение: {os.path.basename(tmp_path)}")
                except Exception as e:
                    print(f"Ошибка загрузки изображения: {str(e)}")
                    continue

            elif layer_data['type'] == 'text':
                layer.update({
                    'text': layer_data['text'],
                    'font': layer_data['font'],
                    'font_size': layer_data['font_size'],
                    'color': layer_data['color'],
                    'alignment': layer_data.get('alignment', Qt.AlignLeft | Qt.AlignTop)
                })
                self.layers.append(layer)
                text = layer['text']
                self.layer_list.addItem(f"Текст: {text[:15] + '...' if len(text) > 15 else text}")

        if self.layers:
            self.layer_list.setCurrentRow(0)
            self.canvas.current_item = 0

        self.canvas.update()
        self.add_to_history()
        self.statusBar().showMessage(f"Проект загружен из {file_path}", 5000)

    def export_jpg(self):
        """Экспорт проекта в JPG с настройками"""
        if not self.layers:
            QMessageBox.warning(self, "Предупреждение", "Нет проекта для экспорта.")
            return

        # Получаем параметры экспорта от пользователя
        dialog = ExportJpgDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return

        # Получаем путь для сохранения
        file_path, _ = QFileDialog.getSaveFileName(self, "Экспорт JPG", "",
                                                   "JPEG изображение (*.jpg)")
        if not file_path:
            return

        if not file_path.endswith('.jpg'):
            file_path += '.jpg'

        # Оригинальные размеры холста
        original_width = self.canvas.minimumSize().width()
        original_height = self.canvas.minimumSize().height()

        # Получаем целевой размер
        target_width, target_height = dialog.get_target_size((original_width, original_height))
        quality = dialog.get_quality()

        # Создаем изображение с целевыми размерами
        pixmap = QPixmap(target_width, target_height)
        pixmap.fill(Qt.white)

        # Создаем QPainter для рисования
        painter = QPainter(pixmap)

        # Масштабирующий коэффициент
        scale_x = target_width / original_width
        scale_y = target_height / original_height

        # Отрисовка всех видимых слоев с учетом масштабирования (в обратном порядке)
        for layer in reversed(self.layers):
            if not layer['visible']:
                continue

            if layer['type'] == 'image':
                # Загрузка изображения
                image = QImage(layer['path'])
                if image.isNull():
                    continue

                # Применение трансформаций с учетом масштабирования
                rect = QRect(
                    int(layer['rect'].x() * scale_x),
                    int(layer['rect'].y() * scale_y),
                    int(layer['rect'].width() * scale_x),
                    int(layer['rect'].height() * scale_y)
                )

                transform = QTransform()
                transform.translate(rect.x() + rect.width() / 2,
                                    rect.y() + rect.height() / 2)
                transform.rotate(layer['rotation'])
                transform.translate(-rect.width() / 2, -rect.height() / 2)

                painter.save()
                painter.setTransform(transform)
                painter.drawImage(QRect(0, 0, rect.width(), rect.height()),
                                  image,
                                  QRect(0, 0, image.width(), image.height()))
                painter.restore()

            elif layer['type'] == 'text':
                painter.save()
                font = QFont(layer['font'], int(layer['font_size'] * min(scale_x, scale_y)))
                painter.setFont(font)
                painter.setPen(QColor(layer['color']))

                rect = QRect(
                    int(layer['rect'].x() * scale_x),
                    int(layer['rect'].y() * scale_y),
                    int(layer['rect'].width() * scale_x),
                    int(layer['rect'].height() * scale_y)
                )

                if layer['rotation'] != 0:
                    painter.translate(rect.center())
                    painter.rotate(layer['rotation'])
                    painter.translate(-rect.width() / 2, -rect.height() / 2)
                    painter.drawText(QRect(0, 0, rect.width(), rect.height()),
                                     layer['alignment'],
                                     layer['text'])
                else:
                    painter.drawText(rect, layer['alignment'], layer['text'])
                painter.restore()

        painter.end()

        # Сохранение в файл
        if not pixmap.save(file_path, "JPEG", quality=quality):
            QMessageBox.warning(self, "Предупреждение", "Не удалось сохранить изображение")
        else:
            self.statusBar().showMessage(
                f"Изображение экспортировано в {file_path} (размер: {target_width}x{target_height}, качество: {quality}%)",
                5000)

    def add_to_history(self):
        """Добавление текущего состояния в историю"""
        if self.current_history_index < len(self.history) - 1:
            self.history = self.history[:self.current_history_index + 1]

        # Добавление текущего состояния
        state = {
            'layers': [layer.copy() for layer in self.layers],
            'canvas_size': (self.canvas.minimumSize().width(), self.canvas.minimumSize().height())
        }

        for i, layer in enumerate(state['layers']):
            if layer['type'] == 'image':
                state['layers'][i]['rect'] = QRect(layer['rect'])
            elif layer['type'] == 'text':
                state['layers'][i]['rect'] = QRect(layer['rect'])

        self.history.append(state)
        self.current_history_index = len(self.history) - 1

        # Ограничение размера истории
        if len(self.history) > 50:
            self.history.pop(0)
            self.current_history_index -= 1

        self.update_history_list()

    def undo(self):
        """Отмена последнего действия"""
        if self.current_history_index <= 0:
            return

        self.current_history_index -= 1
        self.restore_from_history()

    def redo(self):
        """Повтор отмененного действия"""
        if self.current_history_index >= len(self.history) - 1:
            return

        self.current_history_index += 1
        self.restore_from_history()

    def restore_from_history(self):
        """Восстановление состояния из истории"""
        if not self.history or self.current_history_index < 0:
            return

        state = self.history[self.current_history_index]

        self.layers = [layer.copy() for layer in state['layers']]
        for layer in self.layers:
            if layer['type'] == 'image':
                layer['rect'] = QRect(layer['rect'])
            elif layer['type'] == 'text':
                layer['rect'] = QRect(layer['rect'])

        self.canvas.setMinimumSize(state['canvas_size'][0], state['canvas_size'][1])

        # Обновление списка слоев
        self.layer_list.clear()
        for layer in self.layers:
            if layer['type'] == 'image':
                self.layer_list.addItem(f"Изображение: {os.path.basename(layer['path'])}")
            elif layer['type'] == 'text':
                text = layer['text']
                self.layer_list.addItem(f"Текст: {text[:15] + '...' if len(text) > 15 else text}")

        if self.layers:
            self.layer_list.setCurrentRow(0)
            self.canvas.current_item = 0

        self.canvas.update()
        self.update_history_list()


if __name__ == "__main__":
    app = QApplication([])
    editor = PostcardEditor()
    editor.show()
    app.exec_()