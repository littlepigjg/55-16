import os
import shutil
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field

from .models import BookMeta


@dataclass
class RecycleEntry:
    id: str
    original_path: str
    recycle_path: str
    file_name: str
    file_size: int
    deleted_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            id=d.get("id", ""),
            original_path=d.get("original_path", ""),
            recycle_path=d.get("recycle_path", ""),
            file_name=d.get("file_name", ""),
            file_size=d.get("file_size", 0),
            deleted_at=d.get("deleted_at", ""),
            metadata=d.get("metadata", {}),
        )


class RecycleBin:
    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = Path.home() / ".ebook_manager" / "recycle_bin"
        self.base_path = Path(base_path)
        self.files_path = self.base_path / "files"
        self.index_file = self.base_path / "index.json"
        self._ensure_directories()
        self._entries: Dict[str, RecycleEntry] = {}
        self._load_index()

    def _ensure_directories(self):
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.files_path.mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = {
                    entry_id: RecycleEntry.from_dict(entry_data)
                    for entry_id, entry_data in data.items()
                }
            except Exception:
                self._entries = {}
        else:
            self._entries = {}

    def _save_index(self):
        try:
            data = {
                entry_id: entry.to_dict()
                for entry_id, entry in self._entries.items()
            }
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存回收站索引失败: {e}")

    def delete(self, book: BookMeta, metadata: dict = None) -> Optional[RecycleEntry]:
        original_path = Path(book.file_path)
        if not original_path.exists():
            return None
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{timestamp}_{entry_id[:8]}_{original_path.name}"
        recycle_path = self.files_path / safe_name
        try:
            shutil.move(str(original_path), str(recycle_path))
        except Exception as e:
            print(f"移动文件到回收站失败: {e}")
            return None
        entry = RecycleEntry(
            id=entry_id,
            original_path=str(original_path),
            recycle_path=str(recycle_path),
            file_name=original_path.name,
            file_size=book.file_size,
            deleted_at=datetime.now().isoformat(),
            metadata=metadata or book.to_dict(),
        )
        self._entries[entry_id] = entry
        self._save_index()
        book.original_path = str(original_path)
        book.file_path = str(recycle_path)
        return entry

    def restore(self, entry_id: str) -> bool:
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        recycle_path = Path(entry.recycle_path)
        original_path = Path(entry.original_path)
        if not recycle_path.exists():
            del self._entries[entry_id]
            self._save_index()
            return False
        try:
            original_path.parent.mkdir(parents=True, exist_ok=True)
            if original_path.exists():
                base, ext = os.path.splitext(str(original_path))
                counter = 1
                while True:
                    new_path = f"{base}_restored{counter}{ext}"
                    if not Path(new_path).exists():
                        original_path = Path(new_path)
                        break
                    counter += 1
            shutil.move(str(recycle_path), str(original_path))
            del self._entries[entry_id]
            self._save_index()
            return True
        except Exception as e:
            print(f"恢复文件失败: {e}")
            return False

    def permanent_delete(self, entry_id: str) -> bool:
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        recycle_path = Path(entry.recycle_path)
        try:
            if recycle_path.exists():
                os.remove(str(recycle_path))
            del self._entries[entry_id]
            self._save_index()
            return True
        except Exception as e:
            print(f"永久删除文件失败: {e}")
            return False

    def get_entries(self) -> List[RecycleEntry]:
        return sorted(
            self._entries.values(),
            key=lambda x: x.deleted_at,
            reverse=True
        )

    def get_entry(self, entry_id: str) -> Optional[RecycleEntry]:
        return self._entries.get(entry_id)

    def clear_all(self) -> int:
        count = 0
        for entry_id in list(self._entries.keys()):
            if self.permanent_delete(entry_id):
                count += 1
        return count

    def get_total_size(self) -> int:
        return sum(entry.file_size for entry in self._entries.values())

    def get_total_count(self) -> int:
        return len(self._entries)

    def cleanup_old(self, days: int = 30) -> int:
        if days <= 0:
            return 0
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        count = 0
        for entry_id, entry in list(self._entries.items()):
            try:
                deleted_at = datetime.fromisoformat(entry.deleted_at)
                if deleted_at < cutoff:
                    if self.permanent_delete(entry_id):
                        count += 1
            except Exception:
                continue
        return count
