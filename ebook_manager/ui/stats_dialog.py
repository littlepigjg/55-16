from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont, QPixmap, QPainter, QColor

from typing import List, Dict
from collections import defaultdict

from ..models import BookMeta, DuplicateGroup


class StatsDialog(QDialog):
    def __init__(self, stats: Dict, groups: List[DuplicateGroup], parent=None):
        super().__init__(parent)
        self.setWindowTitle("去重统计报表")
        self.resize(800, 600)
        self._stats = stats
        self._groups = groups
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        title_label = QLabel("<h1>📊 去重统计报告</h1>")
        main_layout.addWidget(title_label)

        overview_group = QGroupBox("概览")
        overview_layout = QGridLayout(overview_group)

        saved_size = self._stats.get("saved_size_bytes", 0)
        total_size = self._stats.get("total_size_bytes", 0)
        saved_percent = (saved_size / total_size * 100) if total_size > 0 else 0

        cards = [
            ("发现重复组", f"{self._stats.get('total_groups', 0)}", "#4a9eff"),
            ("重复书籍总数", f"{self._stats.get('total_duplicate_books', 0)}", "#ff6b6b"),
            ("可移除书籍", f"{self._stats.get('books_to_remove', 0)}", "#ffa502"),
            ("预计释放空间", f"{BookMeta.format_size(saved_size)}", "#2ed573"),
        ]

        for i, (label, value, color) in enumerate(cards):
            card = self._create_card(label, value, color)
            overview_layout.addWidget(card, 0, i)

        main_layout.addWidget(overview_group)

        if saved_size > 0:
            progress_group = QGroupBox("空间释放进度")
            progress_layout = QVBoxLayout(progress_group)

            progress_label = QLabel(
                f"可释放 {BookMeta.format_size(saved_size)} / 总重复大小 {BookMeta.format_size(total_size)}"
                f" ({saved_percent:.1f}%)"
            )
            progress_layout.addWidget(progress_label)

            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(int(saved_percent))
            progress_bar.setFormat(f"{saved_percent:.1f}%")
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    text-align: center;
                    height: 25px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #2ed573, stop:1 #7bed9f);
                    border-radius: 3px;
                }
            """)
            progress_layout.addWidget(progress_bar)

            main_layout.addWidget(progress_group)

        details_layout = QHBoxLayout()

        format_group = QGroupBox("格式分布")
        format_layout = QVBoxLayout(format_group)
        format_table = self._create_format_table()
        format_layout.addWidget(format_table)
        details_layout.addWidget(format_group)

        type_group = QGroupBox("匹配类型分布")
        type_layout = QVBoxLayout(type_group)
        type_table = self._create_match_type_table()
        type_layout.addWidget(type_table)
        details_layout.addWidget(type_group)

        main_layout.addLayout(details_layout, 1)

        group_group = QGroupBox("重复组详情")
        group_layout = QVBoxLayout(group_group)
        group_table = self._create_group_table()
        group_layout.addWidget(group_table)
        main_layout.addWidget(group_group, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        main_layout.addLayout(btn_row)

    def _create_card(self, label: str, value: str, color: str) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background: {color}11;
                border: 1px solid {color}44;
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)

        text_label = QLabel(label)
        text_label.setStyleSheet("color: #666; font-size: 13px;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label)

        return widget

    def _create_format_table(self) -> QTableWidget:
        format_dist = self._stats.get("format_distribution", {})
        total = sum(format_dist.values()) if format_dist else 0

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["格式", "数量", "占比"])
        table.setRowCount(len(format_dist))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        colors = {
            "epub": "#4a9eff",
            "pdf": "#ff6b6b",
            "mobi": "#ffa502",
            "azw3": "#2ed573",
            "azw": "#7bed9f",
            "txt": "#a55eea",
        }

        for row, (fmt, count) in enumerate(sorted(format_dist.items(), key=lambda x: -x[1])):
            fmt_item = QTableWidgetItem(fmt.upper())
            fmt_item.setForeground(QBrush(QColor(colors.get(fmt, "#666"))))
            table.setItem(row, 0, fmt_item)

            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 1, count_item)

            percent = (count / total * 100) if total > 0 else 0
            percent_item = QTableWidgetItem(f"{percent:.1f}%")
            percent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, percent_item)

        return table

    def _create_match_type_table(self) -> QTableWidget:
        type_dist = self._stats.get("match_type_distribution", {})
        total = sum(type_dist.values()) if type_dist else 0

        type_labels = {
            "isbn_exact": ("📚 ISBN精确", "#2ed573"),
            "title_author_simhash": ("📖 书名+内容", "#4a9eff"),
            "simhash_content": ("📝 内容相似", "#ffa502"),
            "fuzzy_match": ("🔍 模糊匹配", "#a55eea"),
        }

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["匹配类型", "数量", "占比"])
        table.setRowCount(len(type_dist))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, (type_, count) in enumerate(sorted(type_dist.items(), key=lambda x: -x[1])):
            label, color = type_labels.get(type_, (type_, "#666"))
            type_item = QTableWidgetItem(label)
            type_item.setForeground(QBrush(QColor(color)))
            table.setItem(row, 0, type_item)

            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 1, count_item)

            percent = (count / total * 100) if total > 0 else 0
            percent_item = QTableWidgetItem(f"{percent:.1f}%")
            percent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, percent_item)

        return table

    def _create_group_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["组号", "书名", "数量", "匹配类型", "相似度"])
        table.setRowCount(len(self._groups))
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        type_labels = {
            "isbn_exact": ("ISBN", "#2ed573"),
            "title_author_simhash": ("书名+内容", "#4a9eff"),
            "simhash_content": ("内容", "#ffa502"),
            "fuzzy_match": ("模糊", "#a55eea"),
        }

        for row, group in enumerate(self._groups):
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 0, num_item)

            first_book = group.books[0] if group.books else None
            title = first_book.title if first_book else "未知"
            table.setItem(row, 1, QTableWidgetItem(title))

            count_item = QTableWidgetItem(str(len(group.books)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, count_item)

            label, color = type_labels.get(group.match_type, (group.match_type, "#666"))
            type_item = QTableWidgetItem(label)
            type_item.setForeground(QBrush(QColor(color)))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 3, type_item)

            sim_item = QTableWidgetItem(f"{group.similarity * 100:.1f}%")
            sim_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 4, sim_item)

        return table

from ..models import BookMeta
