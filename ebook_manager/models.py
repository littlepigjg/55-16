from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from pathlib import Path
import hashlib
import re
import unicodedata


@dataclass
class BookFingerprint:
    isbn_normalized: str = ""
    title_author_key: str = ""
    size_hash: str = ""
    simhash: int = 0
    text_preview: str = ""

    def to_dict(self):
        return {
            "isbn_normalized": self.isbn_normalized,
            "title_author_key": self.title_author_key,
            "size_hash": self.size_hash,
            "simhash": self.simhash,
            "text_preview": self.text_preview,
        }

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            isbn_normalized=d.get("isbn_normalized", ""),
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

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFKD", text)
        ascii_text = text.encode("ascii", "ignore").decode("ascii")
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        text = ascii_text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
                     "of", "with", "by", "from", "is", "are", "was", "were",
                     "be", "been", "being", "have", "has", "had", "do", "does",
                     "did", "will", "would", "could", "should", "may", "might",
                     "must", "shall", "can", "need", "dare", "ought", "used",
                     "de", "la", "le", "les", "du", "des", "un", "une", "el",
                     "los", "las", "al", "del", "y", "o", "en", "de", "para",
                     "por", "con", "sin", "sobre", "entre", "a", "o", "e", "do",
                     "da", "das", "dos", "no", "na", "nas", "nos", "em", "por",
                     "para", "com", "sem", "sobre", "entre",
                     "著", "编", "译", "作者", "主编", "校对", "注释",
                     "新版", "修订版", "珍藏版", "典藏版", "精装版", "平装版",
                     "全集", "选集", "合集", "套装", "上下册", "全册"}
        chinese_stopwords = {"著", "编", "译", "作者", "主编", "校对", "注释",
                            "新版", "修订版", "珍藏版", "典藏版", "精装版", "平装版",
                            "全集", "选集", "合集", "套装", "上下册", "全册",
                            "的", "了", "和", "与", "及", "或", "一个", "是", "在",
                            "我", "你", "他", "她", "它", "这", "那", "有", "不", "没",
                            "就", "都", "也", "还", "又", "再", "很", "更", "最"}
        words = [w for w in text.split() if w and w not in stopwords]
        chinese_filtered = [c for c in chinese_chars if c not in chinese_stopwords]
        result_words = sorted(words)
        if chinese_filtered:
            result_words.extend(sorted(chinese_filtered))
        return " ".join(result_words)

    @staticmethod
    def normalize_isbn(isbn: str) -> str:
        if not isbn:
            return ""
        digits = re.sub(r"[^\dXx]", "", isbn)
        digits = digits.upper()
        if len(digits) == 10:
            return BookMeta.isbn10_to_isbn13(digits)
        elif len(digits) == 13:
            return digits if BookMeta.validate_isbn13(digits) else ""
        return ""

    @staticmethod
    def isbn10_to_isbn13(isbn10: str) -> str:
        if len(isbn10) != 10:
            return ""
        prefix = "978" + isbn10[:9]
        total = 0
        for i, c in enumerate(prefix):
            digit = int(c)
            total += digit * (1 if i % 2 == 0 else 3)
        check = (10 - (total % 10)) % 10
        return prefix + str(check)

    @staticmethod
    def validate_isbn13(isbn13: str) -> bool:
        if len(isbn13) != 13 or not isbn13.isdigit():
            return False
        total = 0
        for i, c in enumerate(isbn13[:12]):
            digit = int(c)
            total += digit * (1 if i % 2 == 0 else 3)
        check = (10 - (total % 10)) % 10
        return str(check) == isbn13[12]

    @staticmethod
    def generate_title_author_key(title: str, author: str) -> str:
        def clean_title(t):
            if not t:
                return ""
            t = re.sub(r"[《》【】\[\]()（）\s]", "", t)
            t = re.sub(r"(珍藏版|典藏版|修订版|新版|精装版|平装版|全集|选集|合集|套装|上下册|全册|完整版|精简版)$", "", t)
            t = re.sub(r"(珍藏版|典藏版|修订版|新版|精装版|平装版|全集|选集|合集|套装|上下册|全册|完整版|精简版)", "", t)
            return t

        def clean_author(a):
            if not a:
                return ""
            a = re.sub(r"[《》【】\[\]()（）\s]", "", a)
            a = re.sub(r"[著编译注主编校对]$", "", a)
            a = re.sub(r"[著编译注主编校对]", "", a)
            return a

        clean_t = clean_title(title)
        clean_a = clean_author(author)
        norm_title = BookMeta.normalize_text(clean_t)
        norm_author = BookMeta.normalize_text(clean_a)
        key = f"{norm_title}|{norm_author}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    @staticmethod
    def format_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
