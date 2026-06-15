from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QMessageBox, QTabWidget, QLabel, QApplication,
    QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from ..models import BookMeta
from ..scanner import BookshelfScanner
from ..metadata_parser import MetadataParser
from ..metadata_editor import MetadataEditor
from ..network_source import NetworkSourceManager
from ..converter import FormatConverter
from ..recycle_bin import RecycleBin

from .scanner_panel import ScannerPanel
from .book_table import BookTableWidget
from .edit_panel import MetadataEditPanel
from .search_dialog import OnlineSearchDialog
from .convert_dialog import ConvertDialog
from .workers import ScanWorker, ParseWorker
from .dedup_panel import DedupPanel
from .recycle_panel import RecyclePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📚 电子书元数据管理器 - 智能去重助手")
        self.setMinimumSize(1300, 800)

        self._books: list = []
        self._scanner = BookshelfScanner()
        self._parser = MetadataParser()
        self._editor = MetadataEditor()
        self._source_manager = NetworkSourceManager()
        self._converter = FormatConverter()
        self._recycle_bin = RecycleBin()

        self._init_ui()
        self._init_menu()
        self._init_statusbar()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        self.library_tab = self._create_library_tab()
        self.dedup_tab = self._create_dedup_tab()
        self.recycle_tab = self._create_recycle_tab()

        self.tab_widget.addTab(self.library_tab, "📚 书库")
        self.tab_widget.addTab(self.dedup_tab, "🔍 智能去重")
        self.tab_widget.addTab(self.recycle_tab, "🗑 回收站")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tab_widget)

        self.setStyleSheet("""
            QMainWindow { background: #f5f6fa; }
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background: #e9ecef;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 20px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #4a9eff;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #dee2e6;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                gridline-color: #eee;
                selection-background-color: #4a9eff33;
                selection-color: #000;
            }
            QTableWidget::item:hover { background: #f0f7ff; }
            QHeaderView::section {
                background: #fafafa;
                border: none;
                border-bottom: 2px solid #ddd;
                padding: 6px;
                font-weight: bold;
            }
            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #4a9eff;
            }
            QPushButton {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 12px;
                background: white;
            }
            QPushButton:hover { background: #f0f7ff; border-color: #4a9eff; }
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background: #4a9eff33;
                color: #000;
            }
        """)

    def _create_library_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scanner_panel = ScannerPanel()
        self.scanner_panel.scan_requested.connect(self._on_scan_requested)
        layout.addWidget(self.scanner_panel)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.book_table = BookTableWidget()
        self.book_table.selection_changed.connect(self._on_selection_changed)
        self.book_table.edit_requested.connect(self._on_edit_requested)
        self.book_table.convert_requested.connect(self._on_convert_requested)
        self.book_table.search_meta_requested.connect(self._on_search_meta_requested)
        splitter.addWidget(self.book_table)

        self.edit_panel = MetadataEditPanel()
        self.edit_panel.save_requested.connect(self._on_save_metadata)
        splitter.addWidget(self.edit_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        return tab

    def _create_dedup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        self.dedup_panel = DedupPanel(self._books)
        self.dedup_panel.books_removed.connect(self._on_books_removed)
        layout.addWidget(self.dedup_panel, 1)

        return tab

    def _create_recycle_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        self.recycle_panel = RecyclePanel()
        self.recycle_panel.entry_restored.connect(self._on_entry_restored)
        self.recycle_panel.entry_permanently_deleted.connect(self._on_entry_permanently_deleted)
        layout.addWidget(self.recycle_panel, 1)

        return tab

    def _init_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")
        import_action = QAction("导入文件(&I)...", self)
        import_action.triggered.connect(self._import_files)
        file_menu.addAction(import_action)

        import_dir_action = QAction("导入目录(&D)...", self)
        import_dir_action.triggered.connect(self._import_directory)
        file_menu.addAction(import_dir_action)

        file_menu.addSeparator()
        exit_action = QAction("退出(&Q)", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("编辑(&E)")
        batch_edit_action = QAction("批量编辑(&B)", self)
        batch_edit_action.triggered.connect(lambda: self._on_edit_requested(self.book_table.get_selected_books()))
        edit_menu.addAction(batch_edit_action)

        search_meta_action = QAction("在线搜索元数据(&S)", self)
        search_meta_action.triggered.connect(lambda: self._on_search_meta_requested(self.book_table.get_selected_books()))
        edit_menu.addAction(search_meta_action)

        tool_menu = menubar.addMenu("工具(&T)")
        convert_action = QAction("格式转换(&C)...", self)
        convert_action.triggered.connect(lambda: self._on_convert_requested(self.book_table.get_selected_books()))
        tool_menu.addAction(convert_action)

        dedup_action = QAction("🔍 智能去重(&D)", self)
        dedup_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(1))
        tool_menu.addAction(dedup_action)

        recycle_action = QAction("🗑 回收站(&R)", self)
        recycle_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(2))
        tool_menu.addAction(recycle_action)

        tool_menu.addSeparator()

        calibre_status = QAction("Calibre 状态检查", self)
        calibre_status.triggered.connect(self._check_calibre)
        tool_menu.addAction(calibre_status)

        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _init_statusbar(self):
        self.statusBar().showMessage("就绪")

    def _on_tab_changed(self, index: int):
        if index == 1:
            self.dedup_panel.update_books(self._books)
        elif index == 2:
            self.recycle_panel.refresh()

    def _on_scan_requested(self, directories: list, recursive: bool):
        self.statusBar().showMessage("正在扫描目录...")
        self._scan_worker = ScanWorker(directories, recursive)
        self._scan_worker.progress.connect(self.scanner_panel.on_scan_progress)
        self._scan_worker.finished_signal.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_scan_finished(self, files: list):
        self.scanner_panel.on_scan_complete(len(files))
        if not files:
            self.statusBar().showMessage("未找到电子书文件")
            return
        self.statusBar().showMessage(f"扫描到 {len(files)} 个文件，正在解析元数据...")
        self._parse_worker = ParseWorker(files)
        self._parse_worker.progress.connect(
            lambda c, t, p: self.statusBar().showMessage(f"解析中 {c}/{t}: {Path(p).name}")
        )
        self._parse_worker.finished_signal.connect(self._on_parse_finished)
        self._parse_worker.start()

    def _on_parse_finished(self, books: list):
        self._books = books
        self.book_table.load_books(books)
        self.statusBar().showMessage(f"已加载 {len(books)} 本电子书")
        if self.tab_widget.currentIndex() == 1:
            self.dedup_panel.update_books(self._books)

    def _on_selection_changed(self, selected: list):
        self.edit_panel.set_books(selected)
        self.statusBar().showMessage(f"已选择 {len(selected)} 本")

    def _on_edit_requested(self, books: list):
        if books:
            self.edit_panel.set_books(books)

    def _on_save_metadata(self, books: list, changes: dict):
        self._editor.apply_batch(books, changes)
        for book in books:
            if book.file_format == "epub":
                self._editor.save_epub_metadata(book)
        self.book_table.load_books(self._books)
        self.statusBar().showMessage(f"已更新 {len(books)} 本书的元数据")

    def _on_search_meta_requested(self, books: list):
        if not books:
            QMessageBox.information(self, "提示", "请先选择书籍")
            return
        dialog = OnlineSearchDialog(books, self._source_manager, self)
        if dialog.exec() == OnlineSearchDialog.DialogCode.Accepted:
            data = dialog.get_selected_data()
            if data:
                overwrite = QMessageBox.question(
                    self,
                    "确认",
                    "是否用搜索结果覆盖已有元数据？\n选\"是\"覆盖全部，选\"否\"仅填充空字段",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                )
                if overwrite == QMessageBox.StandardButton.Cancel:
                    return
                for book in books:
                    self._editor.merge_from_source(book, data, overwrite=(overwrite == QMessageBox.StandardButton.Yes))
                    if book.file_format == "epub":
                        self._editor.save_epub_metadata(book)
                self.book_table.load_books(self._books)
                self.statusBar().showMessage(f"已从在线源填充 {len(books)} 本书的元数据")

    def _on_convert_requested(self, books: list):
        if not books:
            books = self.book_table.get_selected_books()
        if not books:
            QMessageBox.information(self, "提示", "请先选择要转换的书籍")
            return
        dialog = ConvertDialog(books, self._converter, self)
        dialog.exec()

    def _on_books_removed(self, books: list):
        removed_paths = {b.original_path for b in books}
        self._books = [b for b in self._books if b.file_path not in removed_paths]
        self.book_table.load_books(self._books)
        self.statusBar().showMessage(f"已移除 {len(books)} 本重复书籍")
        if self.tab_widget.currentIndex() == 2:
            self.recycle_panel.refresh()

    def _on_entry_restored(self, original_path: str):
        for entry in self._recycle_bin.get_entries():
            if entry.original_path == original_path:
                try:
                    book = self._parser.parse(original_path)
                    self._books.append(book)
                except Exception:
                    pass
                break
        self.book_table.load_books(self._books)
        self.statusBar().showMessage("文件已恢复")

    def _on_entry_permanently_deleted(self, original_path: str):
        self._books = [b for b in self._books if b.file_path != original_path and b.original_path != original_path]
        self.book_table.load_books(self._books)

    def _import_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择电子书文件", "",
            "电子书 (*.epub *.mobi *.pdf);;所有文件 (*)"
        )
        if files:
            self._parse_and_add(files)

    def _import_directory(self):
        d = QFileDialog.getExistingDirectory(self, "选择电子书目录")
        if d:
            files = self._scanner.scan_directory(d)
            if files:
                self._parse_and_add(files)

    def _parse_and_add(self, files: list):
        existing_paths = {b.file_path for b in self._books}
        new_files = [f for f in files if f not in existing_paths]
        if not new_files:
            self.statusBar().showMessage("文件已存在于列表中")
            return
        parser = MetadataParser()
        for f in new_files:
            try:
                book = parser.parse(f)
                self._books.append(book)
            except Exception:
                self._books.append(BookMeta(file_path=f, file_format=Path(f).suffix.lstrip("."), title=Path(f).stem))
        self.book_table.load_books(self._books)
        self.statusBar().showMessage(f"已导入 {len(new_files)} 本电子书")
        if self.tab_widget.currentIndex() == 1:
            self.dedup_panel.update_books(self._books)

    def _check_calibre(self):
        if self._converter.is_calibre_available:
            QMessageBox.information(self, "Calibre 状态", "✅ Calibre (ebook-convert) 已安装且可用")
        else:
            QMessageBox.warning(
                self, "Calibre 状态",
                "❌ 未检测到 Calibre\n\n格式转换功能需要 Calibre 支持。\n"
                "请从 https://calibre-ebook.com 下载安装，\n"
                "并确保 ebook-convert 在系统 PATH 中。"
            )

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            "📚 电子书元数据管理器 v2.0\n\n"
            "✨ 新增：智能去重助手\n\n"
            "功能特点：\n"
            "• 多维特征指纹（ISBN、书名作者归一化、文件哈希）\n"
            "• SimHash正文相似度算法\n"
            "• 智能推荐策略（元数据完整度、格式通用性、体积适中）\n"
            "• 软删除（移动到回收站）+ 恢复功能\n"
            "• 详细统计报表（重复组数、预计释放空间）\n\n"
            "支持 EPUB/MOBI/PDF 元数据编辑与格式转换\n"
            "元数据来源: 豆瓣读书、OpenLibrary\n"
            "格式转换依赖: Calibre (ebook-convert)"
        )
