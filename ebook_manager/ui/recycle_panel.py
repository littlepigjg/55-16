from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QDialog,
    QCheckBox, QInputDialog, QGroupBox, QSplitter, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush

from datetime import datetime
from pathlib import Path
from typing import List

from ..recycle_bin import RecycleBin, RecycleEntry
from ..models import BookMeta


class RecyclePanel(QWidget):
    entry_restored = pyqtSignal(str)
    entry_permanently_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recycle_bin = RecycleBin()
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header_group = QGroupBox("回收站")
        header_layout = QVBoxLayout(header_group)

        info_row = QHBoxLayout()
        self.info_label = QLabel("")
        info_row.addWidget(self.info_label)
        info_row.addStretch()

        self.restore_all_btn = QPushButton("↩ 恢复全部")
        self.restore_all_btn.clicked.connect(self._restore_all)
        info_row.addWidget(self.restore_all_btn)

        self.empty_btn = QPushButton("🗑 清空回收站")
        self.empty_btn.setStyleSheet("QPushButton{color:#cc0000;border-color:#cc0000}")
        self.empty_btn.clicked.connect(self._empty_trash)
        info_row.addWidget(self.empty_btn)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        info_row.addWidget(self.refresh_btn)

        header_layout.addLayout(info_row)

        tips_label = QLabel(
            "💡 <b>提示:</b> 删除的书籍会被移动到这里，而非永久删除。"
            " 你可以随时恢复或永久删除它们。30天以上的文件会被自动清理。"
        )
        tips_label.setStyleSheet("background:#d1ecf1;padding:8px;border-radius:4px;border:1px solid #bee5eb;color:#0c5460;")
        tips_label.setTextFormat(Qt.TextFormat.RichText)
        tips_label.setWordWrap(True)
        header_layout.addWidget(tips_label)

        main_layout.addWidget(header_group)

        splitter = QSplitter(Qt.Orientation.Vertical)

        table_group = QWidget()
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(0, 0, 0, 0)

        btn_row = QHBoxLayout()
        self.restore_btn = QPushButton("↩ 恢复选中")
        self.restore_btn.clicked.connect(self._restore_selected)
        self.restore_btn.setEnabled(False)
        btn_row.addWidget(self.restore_btn)

        self.delete_btn = QPushButton("✕ 永久删除")
        self.delete_btn.setStyleSheet("QPushButton{color:#cc0000;border-color:#cc0000}")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)

        btn_row.addStretch()
        table_layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        headers = ["", "文件名", "原路径", "大小", "删除时间", ""]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellClicked.connect(self._on_cell_clicked)
        table_layout.addWidget(self.table, 1)

        splitter.addWidget(table_group)

        details_group = QGroupBox("详细信息")
        details_layout = QVBoxLayout(details_group)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)
        splitter.addWidget(details_group)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

    def refresh(self):
        entries = self._recycle_bin.get_entries()
        self._populate_table(entries)
        self._update_info_label()
        self.details_text.clear()

    def _populate_table(self, entries: List[RecycleEntry]):
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.CheckState.Unchecked)
            checkbox_item.setData(Qt.ItemDataRole.UserRole, entry)
            self.table.setItem(row, 0, checkbox_item)

            name_item = QTableWidgetItem(entry.file_name)
            name_item.setData(Qt.ItemDataRole.UserRole, entry)
            self.table.setItem(row, 1, name_item)

            path_item = QTableWidgetItem(entry.original_path)
            self.table.setItem(row, 2, path_item)

            size_item = QTableWidgetItem(BookMeta.format_size(entry.file_size))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, size_item)

            try:
                dt = datetime.fromisoformat(entry.deleted_at)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = entry.deleted_at
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, time_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 0, 2, 0)

            restore_btn = QPushButton("恢复")
            restore_btn.setStyleSheet("QPushButton{background:#4a9eff;color:white;border:none;padding:3px 10px;border-radius:3px}")
            restore_btn.clicked.connect(lambda checked, e=entry: self._restore_entry(e))
            action_layout.addWidget(restore_btn)

            delete_btn = QPushButton("删除")
            delete_btn.setStyleSheet("QPushButton{background:#ff6b6b;color:white;border:none;padding:3px 10px;border-radius:3px}")
            delete_btn.clicked.connect(lambda checked, e=entry: self._delete_entry(e))
            action_layout.addWidget(delete_btn)

            self.table.setCellWidget(row, 5, action_widget)

        self.table.resizeRowsToContents()

    def _update_info_label(self):
        count = self._recycle_bin.get_total_count()
        size = self._recycle_bin.get_total_size()
        self.info_label.setText(f"📦 回收站中有 <b>{count}</b> 个文件，占用 <b>{BookMeta.format_size(size)}</b>")
        self.info_label.setTextFormat(Qt.TextFormat.RichText)

        self.empty_btn.setEnabled(count > 0)
        self.restore_all_btn.setEnabled(count > 0)

    def _on_selection_changed(self):
        selected = self.table.selectedItems()
        has_selection = len(selected) > 0
        self.restore_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _on_cell_clicked(self, row: int, col: int):
        item = self.table.item(row, 0)
        if not item:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self._show_details(entry)

    def _show_details(self, entry: RecycleEntry):
        if not entry:
            return
        details = []
        details.append(f"<h3>{self._escape_html(entry.file_name)}</h3>")
        details.append("<table border='0' cellpadding='4' style='width:100%'>")
        details.append(f"<tr><td width='100'><b>文件大小:</b></td><td>{BookMeta.format_size(entry.file_size)}</td></tr>")
        details.append(f"<tr><td><b>原路径:</b></td><td>{self._escape_html(entry.original_path)}</td></tr>")
        details.append(f"<tr><td><b>回收路径:</b></td><td>{self._escape_html(entry.recycle_path)}</td></tr>")
        try:
            dt = datetime.fromisoformat(entry.deleted_at)
            time_str = dt.strftime("%Y年%m月%d日 %H:%M:%S")
        except Exception:
            time_str = entry.deleted_at
        details.append(f"<tr><td><b>删除时间:</b></td><td>{time_str}</td></tr>")
        details.append("</table>")

        if entry.metadata:
            metadata = entry.metadata
            details.append("<h4>元数据:</h4>")
            details.append("<table border='0' cellpadding='4' style='width:100%'>")
            if metadata.get("title"):
                details.append(f"<tr><td width='100'><b>书名:</b></td><td>{self._escape_html(metadata['title'])}</td></tr>")
            if metadata.get("author"):
                details.append(f"<tr><td><b>作者:</b></td><td>{self._escape_html(metadata['author'])}</td></tr>")
            if metadata.get("publisher"):
                details.append(f"<tr><td><b>出版社:</b></td><td>{self._escape_html(metadata['publisher'])}</td></tr>")
            if metadata.get("isbn"):
                details.append(f"<tr><td><b>ISBN:</b></td><td>{self._escape_html(metadata['isbn'])}</td></tr>")
            if metadata.get("file_format"):
                details.append(f"<tr><td><b>格式:</b></td><td>{metadata['file_format'].upper()}</td></tr>")
            details.append("</table>")

        self.details_text.setHtml("".join(details))

    def _escape_html(self, text: str) -> str:
        if not text:
            return ""
        return (str(text).replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def _get_checked_entries(self) -> List[RecycleEntry]:
        entries = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    entries.append(entry)
        return entries

    def _restore_selected(self):
        entries = self._get_checked_entries()
        if not entries:
            QMessageBox.information(self, "提示", "请先选择要恢复的文件")
            return
        self._restore_entries(entries)

    def _restore_entry(self, entry: RecycleEntry):
        self._restore_entries([entry])

    def _restore_entries(self, entries: List[RecycleEntry]):
        if not entries:
            return
        reply = QMessageBox.question(
            self, "确认恢复",
            f"确定要恢复 {len(entries)} 个文件到原位置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = 0
        errors = []
        for entry in entries:
            if self._recycle_bin.restore(entry.id):
                success += 1
                self.entry_restored.emit(entry.original_path)
            else:
                errors.append(entry.file_name)

        if errors:
            QMessageBox.warning(self, "部分失败",
                              f"成功恢复 {success} 个，失败 {len(errors)} 个。\n"
                              f"失败: {', '.join(errors[:3])}")
        else:
            QMessageBox.information(self, "完成", f"已成功恢复 {success} 个文件")

        self.refresh()

    def _delete_selected(self):
        entries = self._get_checked_entries()
        if not entries:
            QMessageBox.information(self, "提示", "请先选择要删除的文件")
            return
        self._delete_entries(entries)

    def _delete_entry(self, entry: RecycleEntry):
        self._delete_entries([entry])

    def _delete_entries(self, entries: List[RecycleEntry]):
        if not entries:
            return
        reply = QMessageBox.warning(
            self, "永久删除",
            f"⚠️ 确定要永久删除 {len(entries)} 个文件吗？\n"
            f"此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = 0
        errors = []
        for entry in entries:
            if self._recycle_bin.permanent_delete(entry.id):
                success += 1
                self.entry_permanently_deleted.emit(entry.original_path)
            else:
                errors.append(entry.file_name)

        if errors:
            QMessageBox.warning(self, "部分失败",
                              f"成功删除 {success} 个，失败 {len(errors)} 个。\n"
                              f"失败: {', '.join(errors[:3])}")
        else:
            QMessageBox.information(self, "完成", f"已永久删除 {success} 个文件")

        self.refresh()

    def _restore_all(self):
        entries = self._recycle_bin.get_entries()
        if not entries:
            return
        self._restore_entries(entries)

    def _empty_trash(self):
        count = self._recycle_bin.get_total_count()
        if count == 0:
            return
        reply = QMessageBox.warning(
            self, "清空回收站",
            f"⚠️ 确定要清空回收站吗？\n"
            f"将永久删除 {count} 个文件，此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = self._recycle_bin.clear_all()
        QMessageBox.information(self, "完成", f"已清空回收站，删除了 {deleted} 个文件")
        self.refresh()
