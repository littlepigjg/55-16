from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from pathlib import Path

from .text_utils import TextNormalizer, ISBNNormalizer, FingerprintGenerator


@dataclass
class BookFingerprint:
    isbn_normalized: str = ""
    title_key: str = ""
    author_key: str = ""
    title_author_key: str = ""
    size_hash: str = ""
    simhash: int = 0
    text_preview: str = ""

    def to_dict(self):
        return {
            "isbn_normalized": self.isbn_normalized,
            "title_key": self.title_key,
            "author_key": self.author_key,
            "title_author_key": self.title_author_key,
            "size_hash": self.size_hash,
            "simhash": self.simhash,
            "text_preview": self.text_preview,
        }

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            isbn_normalized=d.get("isbn_normalized", ""),
            title_key=d.get("title_key", ""),
            author_key=d.get("author_key", ""),
            title_author_key=d.get("title_author_key", ""),
            size_hash=d.get("size_hash", ""),
            simhash=d.get("simhash", 0),
            text_preview=d.get("text_preview", ""),
        )


@dataclass
class DuplicateGroup:
    group_id: str = ""
    books: List["BookMeta"] = field(default_factory=list)
    similarity: float = 0.0
    match_type: str = ""

    def to_dict(self):
        return {
            "group_id": self.group_id,
            "books": [b.file_path for b in self.books],
            "similarity": self.similarity,
            "match_type": self.match_type,
        }


@dataclass
class BookMeta:
    title: str = ""
    author: str = ""
    publisher: str = ""
    publish_date: str = ""
    isbn: str = ""
    language: str = ""
    description: str = ""
    tags: list = field(default_factory=list)
    cover_path: Optional[str] = None
    file_path: str = ""
    file_format: str = ""
    file_size: int = 0
    fingerprint: BookFingerprint = field(default_factory=BookFingerprint)
    original_path: str = ""
    is_duplicate: bool = False
    duplicate_group_id: str = ""
    keep_recommendation_score: float = 0.0
    metadata_completeness: float = 0.0

    def to_dict(self):
        return {
            "title": self.title,
            "author": self.author,
            "publisher": self.publisher,
            "publish_date": self.publish_date,
            "isbn": self.isbn,
            "language": self.language,
            "description": self.description,
            "tags": self.tags,
            "cover_path": self.cover_path,
            "file_path": self.file_path,
            "file_format": self.file_format,
            "file_size": self.file_size,
            "fingerprint": self.fingerprint.to_dict(),
            "original_path": self.original_path,
            "is_duplicate": self.is_duplicate,
            "duplicate_group_id": self.duplicate_group_id,
            "keep_recommendation_score": self.keep_recommendation_score,
            "metadata_completeness": self.metadata_completeness,
        }

    @classmethod
    def from_dict(cls, d: dict):
        fp_dict = d.get("fingerprint", {})
        return cls(
            title=d.get("title", ""),
            author=d.get("author", ""),
            publisher=d.get("publisher", ""),
            publish_date=d.get("publish_date", ""),
            isbn=d.get("isbn", ""),
            language=d.get("language", ""),
            description=d.get("description", ""),
            tags=d.get("tags", []),
            cover_path=d.get("cover_path"),
            file_path=d.get("file_path", ""),
            file_format=d.get("file_format", ""),
            file_size=d.get("file_size", 0),
            fingerprint=BookFingerprint.from_dict(fp_dict),
            original_path=d.get("original_path", ""),
            is_duplicate=d.get("is_duplicate", False),
            duplicate_group_id=d.get("duplicate_group_id", ""),
            keep_recommendation_score=d.get("keep_recommendation_score", 0.0),
            metadata_completeness=d.get("metadata_completeness", 0.0),
        )

    def calculate_metadata_completeness(self) -> float:
        fields = [self.title, self.author, self.publisher, self.publish_date,
                  self.isbn, self.language, self.description]
        filled = sum(1 for f in fields if f and str(f).strip())
        return filled / len(fields) if fields else 0.0

    def generate_fingerprint_keys(self) -> None:
        norm_isbn = BookMeta.normalize_isbn(self.isbn)
        t_key, a_key, ta_key = BookMeta.generate_title_author_keys(self.title, self.author)
        self.fingerprint.isbn_normalized = norm_isbn
        self.fingerprint.title_key = t_key
        self.fingerprint.author_key = a_key
        self.fingerprint.title_author_key = ta_key
        if self.file_path:
            self.fingerprint.size_hash = FingerprintGenerator.size_hash(
                self.file_size,
                Path(self.file_path).name
            )

    @staticmethod
    def normalize_text(text: str) -> str:
        return TextNormalizer.normalize_general(text)

    @staticmethod
    def normalize_title(text: str) -> str:
        return TextNormalizer.normalize_title(text)

    @staticmethod
    def normalize_author(text: str) -> str:
        return TextNormalizer.normalize_author(text)

    @staticmethod
    def normalize_isbn(isbn: str) -> str:
        return ISBNNormalizer.normalize(isbn)

    @staticmethod
    def isbn10_to_isbn13(isbn10: str) -> str:
        return ISBNNormalizer.isbn10_to_isbn13(isbn10)

    @staticmethod
    def validate_isbn13(isbn13: str) -> bool:
        return ISBNNormalizer.validate_isbn13(isbn13)

    @staticmethod
    def generate_title_author_keys(title: str, author: str) -> Tuple[str, str, str]:
        return FingerprintGenerator.title_author_hash(title, author)

    @staticmethod
    def generate_title_author_key(title: str, author: str) -> str:
        _, _, combined = FingerprintGenerator.title_author_hash(title, author)
        return combined

    @staticmethod
    def format_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
