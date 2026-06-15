import hashlib
from typing import List, Dict, Tuple
from collections import defaultdict
from dataclasses import dataclass

from .models import BookMeta, DuplicateGroup, BookFingerprint
from .fingerprint_calculator import SimHash


@dataclass
class MatchConfig:
    isbn_match_threshold: float = 1.0
    title_author_match_threshold: float = 0.95
    simhash_threshold: float = 0.85
    size_match_tolerance: float = 0.05
    min_duplicate_size: int = 2


class MatchResult:
    def __init__(self, book1: BookMeta, book2: BookMeta, similarity: float, match_type: str):
        self.book1 = book1
        self.book2 = book2
        self.similarity = similarity
        self.match_type = match_type

    def __repr__(self):
        return f"MatchResult({self.book1.title} vs {self.book2.title}, sim={self.similarity:.2f}, type={self.match_type})"


class DuplicateDetector:
    def __init__(self, config: MatchConfig = None):
        self.config = config or MatchConfig()
        self.simhash = SimHash()

    def detect(self, books: List[BookMeta]) -> List[DuplicateGroup]:
        groups = []
        group_id_counter = 0
        processed = set()
        isbn_groups = self._group_by_isbn(books)
        for isbn, group_books in isbn_groups.items():
            if len(group_books) >= self.config.min_duplicate_size:
                group = DuplicateGroup(
                    group_id=f"group_isbn_{group_id_counter}",
                    books=list(group_books),
                    similarity=1.0,
                    match_type="isbn_exact"
                )
                groups.append(group)
                processed.update(b.file_path for b in group_books)
                group_id_counter += 1
        remaining_books = [b for b in books if b.file_path not in processed]
        title_author_groups = self._group_by_title_author(remaining_books)
        for key, group_books in title_author_groups.items():
            if len(group_books) >= self.config.min_duplicate_size:
                verified = self._verify_by_simhash(group_books)
                if len(verified) >= self.config.min_duplicate_size:
                    sim = self._calculate_group_similarity(verified)
                    group = DuplicateGroup(
                        group_id=f"group_title_{group_id_counter}",
                        books=verified,
                        similarity=sim,
                        match_type="title_author_simhash"
                    )
                    groups.append(group)
                    processed.update(b.file_path for b in verified)
                    group_id_counter += 1
        remaining_books = [b for b in remaining_books if b.file_path not in processed]
        simhash_groups = self._group_by_simhash(remaining_books)
        for simhash_val, group_books in simhash_groups.items():
            if len(group_books) >= self.config.min_duplicate_size:
                sim = self._calculate_group_similarity(group_books)
                if sim >= self.config.simhash_threshold:
                    verified = [b for b in group_books if self._verify_size_match(b, group_books[0])]
                    if len(verified) >= self.config.min_duplicate_size:
                        group = DuplicateGroup(
                            group_id=f"group_simhash_{group_id_counter}",
                            books=verified,
                            similarity=sim,
                            match_type="simhash_content"
                        )
                        groups.append(group)
                        processed.update(b.file_path for b in verified)
                        group_id_counter += 1
        remaining_books = [b for b in remaining_books if b.file_path not in processed]
        fuzzy_groups = self._fuzzy_grouping(remaining_books)
        for group_books in fuzzy_groups:
            if len(group_books) >= self.config.min_duplicate_size:
                sim = self._calculate_group_similarity(group_books)
                if sim >= 0.7:
                    group = DuplicateGroup(
                        group_id=f"group_fuzzy_{group_id_counter}",
                        books=group_books,
                        similarity=sim,
                        match_type="fuzzy_match"
                    )
                    groups.append(group)
                    group_id_counter += 1
        return groups

    def _group_by_isbn(self, books: List[BookMeta]) -> Dict[str, List[BookMeta]]:
        groups = defaultdict(list)
        for book in books:
            isbn = book.fingerprint.isbn_normalized
            if isbn:
                groups[isbn].append(book)
        return dict(groups)

    def _group_by_title_author(self, books: List[BookMeta]) -> Dict[str, List[BookMeta]]:
        groups = defaultdict(list)
        for book in books:
            key = book.fingerprint.title_author_key
            if key:
                groups[key].append(book)
        return dict(groups)

    def _group_by_simhash(self, books: List[BookMeta]) -> Dict[int, List[BookMeta]]:
        groups = defaultdict(list)
        for book in books:
            if book.fingerprint.simhash != 0:
                groups[book.fingerprint.simhash].append(book)
        return dict(groups)

    def _verify_by_simhash(self, books: List[BookMeta]) -> List[BookMeta]:
        if len(books) < 2:
            return books
        verified = [books[0]]
        for book in books[1:]:
            should_add = False
            for v in verified:
                sim = self._calculate_similarity(book, v)
                if sim >= self.config.simhash_threshold:
                    should_add = True
                    break
            if should_add:
                verified.append(book)
        return verified

    def _verify_size_match(self, book1: BookMeta, book2: BookMeta) -> bool:
        if book1.file_size == 0 or book2.file_size == 0:
            return True
        size_diff = abs(book1.file_size - book2.file_size)
        max_size = max(book1.file_size, book2.file_size)
        ratio = size_diff / max_size
        if ratio < 0.3:
            return True
        if book1.file_format != book2.file_format:
            return True
        return ratio < self.config.size_match_tolerance

    def _calculate_similarity(self, book1: BookMeta, book2: BookMeta) -> float:
        if book1.fingerprint.isbn_normalized and book1.fingerprint.isbn_normalized == book2.fingerprint.isbn_normalized:
            return 1.0

        author_penalty = 1.0
        if book1.author and book2.author:
            author_sim = self._text_similarity(book1.author, book2.author)
            if author_sim < 0.3:
                author_penalty = 0.3
            elif author_sim < 0.5:
                author_penalty = 0.6

        title_sim = self._text_similarity(book1.title, book2.title)
        author_sim_score = self._text_similarity(book1.author, book2.author) if (book1.author and book2.author) else 0.5
        title_author_sim = 0.6 * title_sim + 0.4 * author_sim_score

        if book1.fingerprint.title_author_key and book1.fingerprint.title_author_key == book2.fingerprint.title_author_key:
            title_author_sim = 1.0

        simhash_sim = SimHash.similarity(
            book1.fingerprint.simhash,
            book2.fingerprint.simhash
        )
        size_sim = self._size_similarity(book1, book2)

        has_simhash = book1.fingerprint.simhash != 0 and book2.fingerprint.simhash != 0
        has_isbn = bool(book1.fingerprint.isbn_normalized and book2.fingerprint.isbn_normalized)

        if has_isbn:
            isbn_weight = 0.4
            isbn_score = 1.0 if book1.fingerprint.isbn_normalized == book2.fingerprint.isbn_normalized else 0.0
        else:
            isbn_weight = 0.0
            isbn_score = 0.0

        if has_simhash:
            simhash_weight = 0.4
        else:
            simhash_weight = 0.1

        weights = {
            "isbn": isbn_weight,
            "title_author": 0.3,
            "simhash": simhash_weight,
            "size": 0.2,
        }
        total_weight = sum(weights.values())
        weighted_sim = (
            weights["isbn"] * isbn_score +
            weights["title_author"] * title_author_sim +
            weights["simhash"] * simhash_sim +
            weights["size"] * size_sim
        )

        final_sim = weighted_sim / total_weight if total_weight > 0 else 0.0
        final_sim *= author_penalty

        if title_sim < 0.5:
            final_sim = min(final_sim, 0.5)

        return final_sim

    def _calculate_group_similarity(self, books: List[BookMeta]) -> float:
        if len(books) < 2:
            return 0.0
        total_sim = 0.0
        count = 0
        for i in range(len(books)):
            for j in range(i + 1, len(books)):
                total_sim += self._calculate_similarity(books[i], books[j])
                count += 1
        return total_sim / count if count > 0 else 0.0

    def _text_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        norm1 = BookMeta.normalize_text(text1)
        norm2 = BookMeta.normalize_text(text2)
        if norm1 == norm2:
            return 1.0
        set1 = set(norm1.split())
        set2 = set(norm2.split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        jaccard = intersection / union if union > 0 else 0.0
        len1 = len(norm1)
        len2 = len(norm2)
        longer = max(len1, len2)
        matches = 0
        if longer > 0:
            s1, s2 = (norm1, norm2) if len1 >= len2 else (norm2, norm1)
            for i in range(len(s2) - 2):
                substr = s2[i:i+3]
                if substr in s1:
                    matches += 1
            substring_sim = matches / max(len(s2) - 2, 1)
        else:
            substring_sim = 0.0
        return 0.7 * jaccard + 0.3 * substring_sim

    def _size_similarity(self, book1: BookMeta, book2: BookMeta) -> float:
        if book1.file_size == 0 or book2.file_size == 0:
            return 0.5
        size1 = book1.file_size
        size2 = book2.file_size
        ratio = min(size1, size2) / max(size1, size2)
        if book1.file_format != book2.file_format:
            return min(ratio + 0.2, 1.0)
        return ratio

    def _fuzzy_grouping(self, books: List[BookMeta]) -> List[List[BookMeta]]:
        if len(books) < 2:
            return []
        groups = []
        processed = set()
        for i, book1 in enumerate(books):
            if book1.file_path in processed:
                continue
            group = [book1]
            processed.add(book1.file_path)
            for j, book2 in enumerate(books[i + 1:]):
                if book2.file_path in processed:
                    continue
                sim = self._calculate_similarity(book1, book2)
                if sim >= 0.6:
                    group.append(book2)
                    processed.add(book2.file_path)
            if len(group) >= self.config.min_duplicate_size:
                groups.append(group)
        return groups

    def get_statistics(self, groups: List[DuplicateGroup]) -> Dict:
        total_books = sum(len(g.books) for g in groups)
        books_to_remove = total_books - len(groups)
        total_size = 0
        saved_size = 0
        for group in groups:
            group_size = sum(b.file_size for b in group.books)
            total_size += group_size
            max_book = max(group.books, key=lambda b: b.file_size)
            saved_size += group_size - max_book.file_size
        format_counts = defaultdict(int)
        type_counts = defaultdict(int)
        for group in groups:
            type_counts[group.match_type] += 1
            for book in group.books:
                format_counts[book.file_format] += 1
        return {
            "total_groups": len(groups),
            "total_duplicate_books": total_books,
            "books_to_remove": books_to_remove,
            "total_size_bytes": total_size,
            "saved_size_bytes": saved_size,
            "format_distribution": dict(format_counts),
            "match_type_distribution": dict(type_counts),
        }
