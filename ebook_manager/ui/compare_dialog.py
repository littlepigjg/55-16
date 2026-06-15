from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
    QRadioButton, QButtonGroup, QGroupBox, QSplitter,
    QMessageBox, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

from pathlib import Path
from typing import List, Tuple

from ..models import BookMeta, DuplicateGroup
from ..recommendation_engine import RecommendationEngine


class CompareDialog(QDialog):
    def __init__(self, group: DuplicateGroup, recommender: RecommendationEngine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("书籍对比 - 选择保留版本")
        self.resize(1000, 700)
        self._group = group
        self._recommender = recommender
        self._result_keep = None
        self._result_remove = []
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        header_label = QLabel(
            f"<h2>发现 {len(self._group.books)} 个重复版本</h2>"
            f"<p>匹配类型: {self._get_match_type_label(self._group.match_type)} | "
            f"相似度: {self._group.similarity * 100:.1f}%</p>"
        )
        header_label.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(header_label)

        info_label = QLabel(
            "💡 <b>提示:</b> 系统已根据元数据完整性、格式通用性、文件大小等指标自动推荐了保留版本。"
            " 请确认或手动选择要保留的书籍。未被选中的将被移动到回收站。"
        )
        info_label.setStyleSheet("background:#fff3cd;padding:10px;border-radius:4px;border:1px solid #ffeaa7;")
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        splitter = QSplitter(Qt.Orientation.Vertical)

        table_group = QGroupBox("书籍对比")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        headers = ["选择", "书名", "作者", "格式", "大小", "元数据", "评分"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        ranked = self._recommender.rank_books(self._group)
        self._radio_group = QButtonGroup(self)

        for row, (book, score) in enumerate(ranked):
            radio = QRadioButton()
            if row == 0:
                radio.setChecked(True)
                radio.setText("⭐ 推荐")
            self._radio_group.addButton(radio, row)
            radio_widget = QWidget()
            radio_layout = QHBoxLayout(radio_widget)
            radio_layout.setContentsMargins(4, 0, 0, 0)
            radio_layout.addWidget(radio)
            radio_layout.addStretch()
            self.table.setCellWidget(row, 0, radio_widget)
            self._fill_row(row, book, score, row == 0)

        self.table.resizeRowsToContents()
        self.table.cellClicked.connect(self._on_cell_clicked)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_group)

        details_group = QGroupBox("详细对比")
        details_layout = QVBoxLayout(details_group)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)

        splitter.addWidget(details_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.confirm_btn = QPushButton("✓ 确认移除其余版本")
        self.confirm_btn.setStyleSheet(
            "QPushButton{background:#4a9eff;color:white;border:none;border-radius:4px;padding:8px 24px;font-weight:bold}"
            "QPushButton:hover{background:#3d8be0}"
        )
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)

        main_layout.addLayout(btn_row)

        self._radio_group.buttonClicked.connect(self._update_details)
        self._update_details()

    def _fill_row(self, row: int, book: BookMeta, score: float, is_recommended: bool):
        items = [
            (1, book.title or Path(book.file_path).name),
            (2, book.author or "-"),
            (3, book.file_format.upper()),
            (4, BookMeta.format_size(book.file_size)),
            (5, f"{book.metadata_completeness * 100:.0f}%"),
            (6, f"{score * 100:.1f}"),
        ]
        for col, text in items:
            item = QTableWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, book)
            if is_recommended:
                item.setBackground(QBrush(QColor(230, 255, 230)))
            self.table.setItem(row, col, item)

        if is_recommended:
            for col in range(1, 7):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QBrush(QColor(230, 255, 230)))

    def _on_cell_clicked(self, row: int, col: int):
        radio = self._radio_group.button(row)
        if radio:
            radio.setChecked(True)
        self._update_details()

    def _update_details(self):
        selected_id = self._radio_group.checkedId()
        if selected_id < 0:
            return

        keep_book = None
        for row in range(self.table.rowCount()):
            radio = self._radio_group.button(row)
            if radio and radio.isChecked():
                item = self.table.item(row, 1)
                if item:
                    keep_book = item.data(Qt.ItemDataRole.UserRole)
                break

        if not keep_book:
            return

        details = []
        reasons = self._recommender.get_recommendation_reason(keep_book, self._group)

        details.append("<h3>保留: " + self._escape_html(keep_book.title or Path(keep_book.file_path).name) + "</h3>")
        if reasons:
            details.append(f"<p><b>推荐理由:</b> {', '.join(reasons)}</p>")

        details.append("<table border='0' cellpadding='4' style='width:100%'>")
        details.append(f"<tr><td width='120'><b>作者:</b></td><td>{self._escape_html(keep_book.author or '-')}</td></tr>")
        details.append(f"<tr><td><b>出版社:</b></td><td>{self._escape_html(keep_book.publisher or '-')}</td></tr>")
        details.append(f"<tr><td><b>出版日期:</b></td><td>{self._escape_html(keep_book.publish_date or '-')}</td></tr>")
        details.append(f"<tr><td><b>ISBN:</b></td><td>{self._escape_html(keep_book.isbn or '-')}</td></tr>")
        details.append(f"<tr><td><b>语言:</b></td><td>{self._escape_html(keep_book.language or '-')}</td></tr>")
        details.append(f"<tr><td><b>格式:</b></td><td>{keep_book.file_format.upper()}</td></tr>")
        details.append(f"<tr><td><b>大小:</b></td><td>{BookMeta.format_size(keep_book.file_size)}</td></tr>")
        details.append(f"<tr><td><b>元数据完整度:</b></td><td>{keep_book.metadata_completeness * 100:.0f}%</td></tr>")
        details.append("</table>")

        if keep_book.description:
            details.append(f"<h4>简介:</h4><p>{self._escape_html(keep_book.description[:300])}</p>")

        if keep_book.fingerprint.text_preview:
            details.append(f"<h4>正文预览:</h4><p style='color:#666;font-family:monospace;font-size:12px'>"
                         f"{self._escape_html(keep_book.fingerprint.text_preview[:300])}</p>")

        remove_books = [b for b in self._group.books if b.file_path != keep_book.file_path]
        if remove_books:
            details.append("<h3>将移除:</h3>")
            details.append("<ul>")
            for b in remove_books:
                reasons = self._recommender.get_removal_reason(b, keep_book)
                reason_text = f" ({', '.join(reasons)})" if reasons else ""
                details.append(f"<li>{self._escape_html(Path(b.file_path).name)} "
                             f"<span style='color:#888'>[{b.file_format.upper()}, {BookMeta.format_size(b.file_size)}]</span>"
                             f"<span style='color:#cc0000'>{self._escape_html(reason_text)}</span></li>")
            details.append("</ul>")

        self.details_text.setHtml("".join(details))

    def _get_match_type_label(self, match_type: str) -> str:
        return {
            "isbn_exact": "📚 ISBN精确匹配",
            "title_author_simhash": "📖 书名作者+内容匹配",
            "simhash_content": "📝 内容相似匹配",
            "fuzzy_match": "🔍 模糊匹配",
        }.get(match_type, match_type)

    def _escape_html(self, text: str) -> str:
        if not text:
            return ""
        return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def _on_confirm(self):
        keep_book = None
        for row in range(self.table.rowCount()):
            radio = self._radio_group.button(row)
            if radio and radio.isChecked():
                item = self.table.item(row, 1)
                if item:
                    keep_book = item.data(Qt.ItemDataRole.UserRole)
                break

        if not keep_book:
            QMessageBox.warning(self, "提示", "请选择要保留的书籍")
            return

        remove_books = [b for b in self._group.books if b.file_path != keep_book.file_path]
        if not remove_books:
            QMessageBox.information(self, "提示", "没有需要移除的书籍")
            self.reject()
            return

        self._result_keep = keep_book
        self._result_remove = remove_books
        self.accept()

    def get_result(self) -> Tuple[BookMeta, List[BookMeta]]:
        return self._result_keep, self._result_remove

from ..models import BookMeta
