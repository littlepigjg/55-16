from typing import List, Dict, Tuple
from pathlib import Path

from .models import BookMeta, DuplicateGroup


FORMAT_PRIORITY = {
    "epub": 1.0,
    "mobi": 0.8,
    "pdf": 0.6,
    "azw": 0.7,
    "azw3": 0.75,
    "txt": 0.3,
    "doc": 0.4,
    "docx": 0.45,
}

FORMAT_UNIVERSAL_SCORE = {
    "epub": 1.0,
    "pdf": 0.9,
    "mobi": 0.7,
    "azw3": 0.6,
    "azw": 0.5,
    "txt": 0.8,
    "docx": 0.5,
    "doc": 0.4,
}


class RecommendationEngine:
    def __init__(self):
        self.weights = {
            "metadata_completeness": 0.35,
            "format_universal": 0.25,
            "file_size_optimal": 0.20,
            "file_quality": 0.15,
            "filename_quality": 0.05,
        }

    def score_book(self, book: BookMeta, group: DuplicateGroup) -> float:
        scores = {}
        scores["metadata_completeness"] = self._score_metadata(book)
        scores["format_universal"] = self._score_format(book)
        scores["file_size_optimal"] = self._score_file_size(book, group)
        scores["file_quality"] = self._score_quality(book)
        scores["filename_quality"] = self._score_filename(book)
        total_score = 0.0
        for key, weight in self.weights.items():
            total_score += scores[key] * weight
        book.keep_recommendation_score = total_score
        return total_score

    def recommend_keep(self, group: DuplicateGroup) -> BookMeta:
        best_book = None
        best_score = -1.0
        for book in group.books:
            score = self.score_book(book, group)
            if score > best_score:
                best_score = score
                best_book = book
        return best_book

    def rank_books(self, group: DuplicateGroup) -> List[Tuple[BookMeta, float]]:
        ranked = []
        for book in group.books:
            score = self.score_book(book, group)
            ranked.append((book, score))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _score_metadata(self, book: BookMeta) -> float:
        return book.metadata_completeness if book.metadata_completeness > 0 else book.calculate_metadata_completeness()

    def _score_format(self, book: BookMeta) -> float:
        fmt = book.file_format.lower()
        return FORMAT_UNIVERSAL_SCORE.get(fmt, 0.3)

    def _score_file_size(self, book: BookMeta, group: DuplicateGroup) -> float:
        sizes = [b.file_size for b in group.books if b.file_size > 0]
        if not sizes:
            return 0.5
        min_size = min(sizes)
        max_size = max(sizes)
        current_size = book.file_size
        if current_size == 0:
            return 0.3
        if max_size == min_size:
            return 1.0
        avg_size = sum(sizes) / len(sizes)
        if current_size <= avg_size:
            ratio = (current_size - min_size) / (avg_size - min_size) if avg_size > min_size else 1.0
            return 0.5 + ratio * 0.5
        else:
            ratio = (max_size - current_size) / (max_size - avg_size) if max_size > avg_size else 1.0
            return 0.5 + ratio * 0.5

    def _score_quality(self, book: BookMeta) -> float:
        score = 0.5
        if book.fingerprint.simhash != 0:
            text_len = len(book.fingerprint.text_preview)
            if text_len > 500:
                score += 0.2
            elif text_len > 200:
                score += 0.1
        if book.cover_path:
            score += 0.15
        if book.tags and len(book.tags) > 0:
            score += 0.1
        return min(score, 1.0)

    def _score_filename(self, book: BookMeta) -> float:
        filename = Path(book.file_path).name
        score = 0.5
        patterns_to_avoid = [
            "副本", "copy", "备份", "backup", "untitled", "无标题",
            "新建", "new", "download", "下载", "temp", "临时"
        ]
        lower_name = filename.lower()
        for pattern in patterns_to_avoid:
            if pattern in lower_name:
                score -= 0.15
        if "[" in filename and "]" in filename:
            score -= 0.1
        if "(" in filename and ")" in filename:
            score -= 0.05
        if book.title and book.title in filename:
            score += 0.2
        if book.author and book.author in filename:
            score += 0.1
        return max(0.0, min(score, 1.0))

    def get_recommendation_reason(self, book: BookMeta, group: DuplicateGroup) -> List[str]:
        reasons = []
        fmt = book.file_format.lower()
        format_score = self._score_format(book)
        if format_score >= 0.9:
            reasons.append(f"格式通用 ({book.file_format.upper()})")
        meta_score = self._score_metadata(book)
        if meta_score >= 0.8:
            reasons.append("元数据完整")
        size_score = self._score_file_size(book, group)
        if size_score >= 0.8:
            reasons.append("体积适中")
        if book.cover_path:
            reasons.append("包含封面")
        if len(book.fingerprint.text_preview) > 300:
            reasons.append("正文完整")
        return reasons

    def get_removal_reason(self, book: BookMeta, keep_book: BookMeta) -> List[str]:
        reasons = []
        if book.metadata_completeness < keep_book.metadata_completeness:
            reasons.append("元数据较少")
        if self._score_format(book) < self._score_format(keep_book):
            reasons.append(f"格式较不通用 ({book.file_format.upper()})")
        if book.file_size > keep_book.file_size * 1.5:
            reasons.append("体积过大")
        if book.file_size < keep_book.file_size * 0.5:
            reasons.append("可能是压缩版/删减版")
        if not book.cover_path and keep_book.cover_path:
            reasons.append("缺少封面")
        return reasons
