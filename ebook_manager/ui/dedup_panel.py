from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QProgressBar, QMessageBox, QSplitter,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QDoubleSpinBox, QFormLayout, QDialog
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QColor, QBrush

from typing import List

from ..models import BookMeta, DuplicateGroup
from ..fingerprint_calculator import FingerprintCalculator
from ..duplicate_detector import DuplicateDetector, MatchConfig
from ..recommendation_engine import RecommendationEngine
from ..recycle_bin import RecycleBin

from .compare_dialog import CompareDialog
from .stats_dialog import StatsDialog


class DedupWorker(QThread):
    progress = pyqtSignal(int, int, str)
    groups_found = pyqtSignal(list)
    finished_signal = pyqtSignal(list, dict)

    def __init__(self, books: List[BookMeta], config: MatchConfig):
        super().__init__()
        self.books = books
        self.config = config

    def run(self):
        total = len(self.books)
        self.progress.emit(0, total, "计算特征指纹...")
        calculator = FingerprintCalculator(
            progress_callback=lambda c, t, p: self.progress.emit(c, t + len(self.books), f"计算指纹: {p}")
        )
        calculator.calculate_batch(self.books)
        self.progress.emit(total, total * 2, "检测重复书籍...")
        detector = DuplicateDetector(self.config)
        groups = detector.detect(self.books)
        stats = detector.get_statistics(groups)
        self.finished_signal.emit(groups, stats)


class DedupPanel(QWidget):
    dedup_completed = pyqtSignal(list)
    books_removed = pyqtSignal(list)

    def __init__(self, books: List[BookMeta], parent=None):
        super().__init__(parent)
        self._books = books
        self._groups: List[DuplicateGroup] = []
        self._stats = {}
        self._recommender = RecommendationEngine()
        self._recycle_bin = RecycleBin()
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        config_group = QGroupBox("检测设置")
        config_layout = QFormLayout(config_group)

        self.simhash_threshold = QDoubleSpinBox()
        self.simhash_threshold.setRange(0.5, 1.0)
        self.simhash_threshold.setSingleStep(0.05)
        self.simhash_threshold.setValue(0.85)
        config_layout.addRow("内容相似度阈值:", self.simhash_threshold)

        self.size_tolerance = QDoubleSpinBox()
        self.size_tolerance.setRange(0.01, 0.5)
        self.size_tolerance.setSingleStep(0.01)
        self.size_tolerance.setValue(0.05)
        config_layout.addRow("文件大小容差:", self.size_tolerance)

        self.enable_fuzzy = QCheckBox("启用模糊匹配")
        self.enable_fuzzy.setChecked(True)
        config_layout.addRow("", self.enable_fuzzy)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("🔍 开始检测重复")
        self.start_btn.setStyleSheet(
            "QPushButton{background:#ff6b6b;color:white;border:none;border-radius:4px;padding:8px 20px;font-weight:bold}"
            "QPushButton:hover{background:#ee5a5a}"
        )
        self.start_btn.clicked.connect(self._start_detection)
        btn_row.addWidget(self.start_btn)

        self.stats_btn = QPushButton("📊 查看统计")
        self.stats_btn.clicked.connect(self._show_stats)
        self.stats_btn.setEnabled(False)
        btn_row.addWidget(self.stats_btn)

        self.auto_dedup_btn = QPushButton("⚡ 一键去重")
        self.auto_dedup_btn.clicked.connect(self._auto_dedup)
        self.auto_dedup_btn.setEnabled(False)
        btn_row.addWidget(self.auto_dedup_btn)

        btn_row.addStretch()
        config_layout.addRow(btn_row)

        main_layout.addWidget(config_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        main_layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("<b>重复分组</b>"))
        self.group_count_label = QLabel("")
        left_header.addStretch()
        left_header.addWidget(self.group_count_label)
        left_layout.addLayout(left_header)

        self.group_list = QListWidget()
        self.group_list.itemSelectionChanged.connect(self._on_group_selected)
        left_layout.addWidget(self.group_list, 1)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("<b>组内书籍</b>"))
        right_header.addStretch()

        self.compare_btn = QPushButton("对比选择")
        self.compare_btn.clicked.connect(self._compare_books)
        self.compare_btn.setEnabled(False)
        right_header.addWidget(self.compare_btn)

        self.keep_selected_btn = QPushButton("✓ 保留选中")
        self.keep_selected_btn.clicked.connect(self._keep_selected)
        self.keep_selected_btn.setEnabled(False)
        right_header.addWidget(self.keep_selected_btn)

        right_layout.addLayout(right_header)

        self.book_table = QTableWidget()
        self.book_table.setColumnCount(6)
        self.book_table.setHorizontalHeaderLabels([
            "", "书名", "作者", "格式", "大小", "推荐保留"
        ])
        self.book_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.book_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.book_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.book_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        right_layout.addWidget(self.book_table, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, 1)

    def update_books(self, books: List[BookMeta]):
        self._books = books
        self._groups = []
        self._stats = {}
        self.group_list.clear()
        self.book_table.setRowCount(0)
        self.group_count_label.setText("")
        self.stats_btn.setEnabled(False)
        self.auto_dedup_btn.setEnabled(False)
        self.status_label.setText("就绪")

    def _start_detection(self):
        if not self._books:
            QMessageBox.information(self, "提示", "请先扫描或导入书籍")
            return

        config = MatchConfig(
            simhash_threshold=self.simhash_threshold.value(),
            size_match_tolerance=self.size_tolerance.value(),
        )
        if not self.enable_fuzzy.isChecked():
            config.min_duplicate_size = 999

        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在检测重复...")

        self._worker = DedupWorker(self._books, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_signal.connect(self._on_detection_finished)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_detection_finished(self, groups: List[DuplicateGroup], stats: dict):
        self._groups = groups
        self._stats = stats
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.group_list.clear()
        for i, group in enumerate(groups):
            first_book = group.books[0] if group.books else None
            title = first_book.title if first_book else f"组 {i+1}"
            match_type = {
                "isbn_exact": "📚 ISBN精确匹配",
                "title_author_simhash": "📖 书名作者+内容",
                "simhash_content": "📝 内容相似",
                "fuzzy_match": "🔍 模糊匹配",
            }.get(group.match_type, group.match_type)
            item_text = f"{match_type} | {title} ({len(group.books)}本, {group.similarity*100:.1f}%)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, group)
            self.group_list.addItem(item)

        count = len(groups)
        total_dup = sum(len(g.books) for g in groups)
        self.group_count_label.setText(f"共 {count} 组 / {total_dup} 本")
        self.stats_btn.setEnabled(count > 0)
        self.auto_dedup_btn.setEnabled(count > 0)

        if count == 0:
            self.status_label.setText("未发现重复书籍")
        else:
            saved = BookMeta.format_size(stats.get("saved_size_bytes", 0))
            self.status_label.setText(f"发现 {count} 组重复书籍，预计可释放 {saved}")

        self.dedup_completed.emit(groups)

    def _on_group_selected(self):
        items = self.group_list.selectedItems()
        if not items:
            self.book_table.setRowCount(0)
            self.compare_btn.setEnabled(False)
            self.keep_selected_btn.setEnabled(False)
            return

        group = items[0].data(Qt.ItemDataRole.UserRole)
        self._populate_book_table(group)
        self.compare_btn.setEnabled(True)
        self.keep_selected_btn.setEnabled(True)

    def _populate_book_table(self, group: DuplicateGroup):
        ranked = self._recommender.rank_books(group)
        keep_book = ranked[0][0] if ranked else None

        self.book_table.setRowCount(len(ranked))
        for row, (book, score) in enumerate(ranked):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.CheckState.Checked if book == keep_book else Qt.CheckState.Unchecked)
            checkbox_item.setData(Qt.ItemDataRole.UserRole, book)
            self.book_table.setItem(row, 0, checkbox_item)

            title_item = QTableWidgetItem(book.title or Path(book.file_path).name)
            title_item.setData(Qt.ItemDataRole.UserRole, book)
            self.book_table.setItem(row, 1, title_item)

            author_item = QTableWidgetItem(book.author or "-")
            self.book_table.setItem(row, 2, author_item)

            format_item = QTableWidgetItem(book.file_format.upper())
            self.book_table.setItem(row, 3, format_item)

            size_item = QTableWidgetItem(BookMeta.format_size(book.file_size))
            self.book_table.setItem(row, 4, size_item)

            reasons = self._recommender.get_recommendation_reason(book, group)
            reason_text = "⭐ 推荐保留" if book == keep_book else f"{score*100:.0f}%"
            if reasons:
                reason_text += f" ({', '.join(reasons[:2])})"
            rec_item = QTableWidgetItem(reason_text)
            if book == keep_book:
                rec_item.setBackground(QBrush(QColor(200, 255, 200)))
                rec_item.setForeground(QBrush(QColor(0, 150, 0)))
            self.book_table.setItem(row, 5, rec_item)

        self.book_table.resizeRowsToContents()

    def _show_stats(self):
        if not self._stats:
            return
        dialog = StatsDialog(self._stats, self._groups, self)
        dialog.exec()

    def _compare_books(self):
        items = self.group_list.selectedItems()
        if not items:
            return
        group = items[0].data(Qt.ItemDataRole.UserRole)
        dialog = CompareDialog(group, self._recommender, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            keep_book, remove_books = dialog.get_result()
            if keep_book and remove_books:
                self._perform_removal(keep_book, remove_books, group)

    def _keep_selected(self):
        items = self.group_list.selectedItems()
        if not items:
            return
        group = items[0].data(Qt.ItemDataRole.UserRole)

        selected_book = None
        for row in range(self.book_table.rowCount()):
            item = self.book_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_book = item.data(Qt.ItemDataRole.UserRole)
                break

        if not selected_book:
            QMessageBox.warning(self, "提示", "请先选择要保留的书籍")
            return

        remove_books = [b for b in group.books if b.file_path != selected_book.file_path]
        if not remove_books:
            QMessageBox.information(self, "提示", "没有需要移除的书籍")
            return

        self._perform_removal(selected_book, remove_books, group)

    def _auto_dedup(self):
        if not self._groups:
            return

        reply = QMessageBox.question(
            self, "确认一键去重",
            "将根据推荐策略自动处理所有重复组。\n"
            "保留评分最高的书籍，其余移动到回收站。\n\n"
            "是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed_books = []
        errors = []

        for group in self._groups:
            keep_book = self._recommender.recommend_keep(group)
            remove_books = [b for b in group.books if b.file_path != keep_book.file_path]
            for book in remove_books:
                entry = self._recycle_bin.delete(book, {"group_id": group.group_id})
                if entry:
                    removed_books.append(book)
                else:
                    errors.append(book.file_path)

        if errors:
            QMessageBox.warning(
                self, "部分失败",
                f"成功处理 {len(removed_books)} 本，失败 {len(errors)} 本。\n"
                f"失败文件: {', '.join(errors[:3])}"
            )
        else:
            QMessageBox.information(
                self, "完成",
                f"已将 {len(removed_books)} 本重复书籍移动到回收站。\n"
                f"可通过工具栏的『回收站』功能恢复或永久删除。"
            )

        self.books_removed.emit(removed_books)
        self._clear_processed_groups()

    def _perform_removal(self, keep_book: BookMeta, remove_books: List[BookMeta], group: DuplicateGroup):
        names = "\n".join([f"  • {Path(b.file_path).name}" for b in remove_books])
        reply = QMessageBox.question(
            self, "确认移除",
            f"将保留:\n  ✓ {Path(keep_book.file_path).name}\n\n"
            f"将移动到回收站:\n{names}\n\n"
            "是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed = []
        errors = []
        for book in remove_books:
            entry = self._recycle_bin.delete(book, {"group_id": group.group_id})
            if entry:
                removed.append(book)
            else:
                errors.append(book.file_path)

        if errors:
            QMessageBox.warning(self, "部分失败", f"失败: {', '.join(errors)}")

        if removed:
            self.books_removed.emit(removed)
            self._remove_processed_group(group)

    def _remove_processed_group(self, group: DuplicateGroup):
        for i in range(self.group_list.count()):
            item = self.group_list.item(i)
            g = item.data(Qt.ItemDataRole.UserRole)
            if g.group_id == group.group_id:
                self.group_list.takeItem(i)
                break

        self._groups = [g for g in self._groups if g.group_id != group.group_id]
        self.book_table.setRowCount(0)
        self.compare_btn.setEnabled(False)
        self.keep_selected_btn.setEnabled(False)

        count = len(self._groups)
        total_dup = sum(len(g.books) for g in self._groups)
        self.group_count_label.setText(f"共 {count} 组 / {total_dup} 本")
        self.stats_btn.setEnabled(count > 0)
        self.auto_dedup_btn.setEnabled(count > 0)

    def _clear_processed_groups(self):
        self._groups = []
        self.group_list.clear()
        self.book_table.setRowCount(0)
        self.group_count_label.setText("")
        self.stats_btn.setEnabled(False)
        self.auto_dedup_btn.setEnabled(False)
        self.compare_btn.setEnabled(False)
        self.keep_selected_btn.setEnabled(False)
        self.status_label.setText("已处理所有重复组")

from pathlib import Path
