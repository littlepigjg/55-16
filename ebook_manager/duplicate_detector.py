from typing import List, Dict, Tuple
from collections import defaultdict
from dataclasses import dataclass

from .models import BookMeta, DuplicateGroup, BookFingerprint
from .similarity import (
    OverallBookSimilarity, SimHashScore,
    TitleSimilarity, AuthorSimilarity, TextSimilarity
)
from .author_verifier import AuthorVerifier, VerificationResult


@dataclass
class MatchConfig:
    isbn_match_threshold: float = 1.0
    title_author_match_threshold: float = 0.90
    simhash_threshold: float = 0.80
    size_match_tolerance: float = 0.05
    min_duplicate_size: int = 2
    author_verification_strict: bool = True


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
        self.overall_similarity = OverallBookSimilarity()
        self.author_verifier = AuthorVerifier()

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
        title_author_groups = self._group_by_title_author_verified(remaining_books)

        for key, group_books in title_author_groups.items():
            if len(group_books) >= self.config.min_duplicate_size:
                verified = self._verify_group(group_books, use_simhash=True)
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
        title_only_groups = self._group_by_title_verified(remaining_books)

        for key, group_books in title_only_groups.items():
            if len(group_books) >= self.config.min_duplicate_size:
                verified = self._verify_group(group_books, use_simhash=True, require_author_match=True)
                if len(verified) >= self.config.min_duplicate_size:
                    sim = self._calculate_group_similarity(verified)
                    if sim >= 0.70:
                        group = DuplicateGroup(
                            group_id=f"group_titleonly_{group_id_counter}",
                            books=verified,
                            similarity=sim,
                            match_type="title_with_author_check"
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
                    verified = self._verify_group(group_books, use_simhash=False, require_author_match=True)
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
                verified = self._verify_group(group_books, use_simhash=True, require_author_match=True)
                if len(verified) >= self.config.min_duplicate_size:
                    sim = self._calculate_group_similarity(verified)
                    if sim >= 0.70:
                        group = DuplicateGroup(
                            group_id=f"group_fuzzy_{group_id_counter}",
                            books=verified,
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

    def _group_by_title_author_verified(self, books: List[BookMeta]) -> Dict[str, List[BookMeta]]:
        raw_groups = defaultdict(list)
        for book in books:
            ta_key = book.fingerprint.title_author_key
            if ta_key:
                raw_groups[ta_key].append(book)

        verified_groups = {}
        for key, candidate_books in raw_groups.items():
            if len(candidate_books) < 2:
                continue
            verified_list = self._author_verify_group(candidate_books)
            if len(verified_list) >= 2:
                verified_groups[key] = verified_list

        return verified_groups

    def _group_by_title_verified(self, books: List[BookMeta]) -> Dict[str, List[BookMeta]]:
        raw_groups = defaultdict(list)
        for book in books:
            t_key = book.fingerprint.title_key
            if t_key:
                raw_groups[t_key].append(book)

        verified_groups = {}
        for key, candidate_books in raw_groups.items():
            if len(candidate_books) < 2:
                continue
            verified_list = self._author_verify_group(candidate_books)
            if len(verified_list) >= 2:
                verified_groups[key] = verified_list

        return verified_groups

    def _author_verify_group(self, books: List[BookMeta]) -> List[BookMeta]:
        if len(books) < 2:
            return books

        verified = [books[0]]
        for candidate in books[1:]:
            should_add = False
            for v in verified:
                result = self.author_verifier.verify_duplicate_candidate(
                    title1=v.title, author1=v.author,
                    title2=candidate.title, author2=candidate.author,
                    isbn1=v.fingerprint.isbn_normalized,
                    isbn2=candidate.fingerprint.isbn_normalized,
                )
                if result.is_same_book:
                    should_add = True
                    break
            if should_add:
                verified.append(candidate)
        return verified

    def _group_by_simhash(self, books: List[BookMeta]) -> Dict[int, List[BookMeta]]:
        groups = defaultdict(list)
        for book in books:
            if book.fingerprint.simhash != 0:
                groups[book.fingerprint.simhash].append(book)
        return dict(groups)

    def _verify_group(
        self, books: List[BookMeta],
        use_simhash: bool = True,
        require_author_match: bool = False
    ) -> List[BookMeta]:
        if len(books) < 2:
            return books

        verified = [books[0]]
        for book in books[1:]:
            should_add = False
            for v in verified:
                overall, _ = self._calculate_pairwise_similarity(book, v)
                author_sim = AuthorSimilarity.compute(book.author, v.author)
                title_sim = TitleSimilarity.compute(book.title, v.title)

                if require_author_match:
                    if author_sim < 0.45:
                        continue

                simhash_ok = True
                if use_simhash and book.fingerprint.simhash and v.fingerprint.simhash:
                    simhash_sim = SimHashScore.similarity(book.fingerprint.simhash, v.fingerprint.simhash)
                    simhash_ok = simhash_sim >= self.config.simhash_threshold * 0.8

                if simhash_ok and overall >= 0.60:
                    should_add = True
                    break

                if title_sim >= 0.85 and author_sim >= 0.55:
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

    def _calculate_pairwise_similarity(self, book1: BookMeta, book2: BookMeta) -> Tuple[float, Dict]:
        return self.overall_similarity.compute(
            isbn1=book1.fingerprint.isbn_normalized,
            isbn2=book2.fingerprint.isbn_normalized,
            author1=book1.author, author2=book2.author,
            title1=book1.title, title2=book2.title,
            simhash1=book1.fingerprint.simhash,
            simhash2=book2.fingerprint.simhash,
            size1=book1.file_size, size2=book2.file_size,
            format1=book1.file_format, format2=book2.file_format,
        )

    def _calculate_similarity(self, book1: BookMeta, book2: BookMeta) -> float:
        sim, _ = self._calculate_pairwise_similarity(book1, book2)
        return sim

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
                ver_result = self.author_verifier.verify_duplicate_candidate(
                    title1=book1.title, author1=book1.author,
                    title2=book2.title, author2=book2.author,
                    isbn1=book1.fingerprint.isbn_normalized,
                    isbn2=book2.fingerprint.isbn_normalized,
                )
                sim = self._calculate_similarity(book1, book2)
                if ver_result.is_same_book and sim >= 0.55:
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
