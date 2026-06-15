from dataclasses import dataclass
from typing import List, Tuple, Optional
import re

from .text_utils import TextNormalizer
from .similarity import AuthorSimilarity, TitleSimilarity


@dataclass
class VerificationResult:
    is_same_book: bool
    author_confidence: float
    title_confidence: float
    overall_confidence: float
    reasons: List[str]
    severity: str = "low"

    def __repr__(self):
        return (f"VerificationResult(match={self.is_same_book}, "
                f"author={self.author_confidence:.2f}, "
                f"title={self.title_confidence:.2f}, "
                f"overall={self.overall_confidence:.2f})")


class AuthorVerifier:
    STRICT_AUTHOR_THRESHOLD = 0.80
    MODERATE_AUTHOR_THRESHOLD = 0.55
    MIN_AUTHOR_THRESHOLD = 0.35

    STRICT_TITLE_THRESHOLD = 0.80
    MODERATE_TITLE_THRESHOLD = 0.60
    MIN_TITLE_THRESHOLD = 0.45

    KNOWN_PSEUDONYMS = {
        frozenset(["鲁迅", "周树人"]): 1.0,
        frozenset(["老舍", "舒庆春"]): 1.0,
        frozenset(["巴金", "李尧棠"]): 1.0,
        frozenset(["茅盾", "沈德鸿"]): 1.0,
        frozenset(["曹禺", "万家宝"]): 1.0,
        frozenset(["郭沫若", "郭开贞"]): 1.0,
        frozenset(["冰心", "谢婉莹"]): 1.0,
        frozenset(["沈从文", "沈岳焕"]): 1.0,
        frozenset(["钱钟书", "钱锺书", "钱仰先"]): 1.0,
        frozenset(["张爱玲", "张煐"]): 1.0,
        frozenset(["金庸", "查良镛"]): 1.0,
        frozenset(["古龙", "熊耀华"]): 1.0,
        frozenset(["琼瑶", "陈喆"]): 1.0,
        frozenset(["三毛", "陈懋平", "陈平"]): 1.0,
        frozenset(["莫言", "管谟业"]): 1.0,
        frozenset(["余华"]): 1.0,
        frozenset(["路遥", "王卫国"]): 1.0,
        frozenset(["陈忠实"]): 1.0,
        frozenset(["贾平凹"]): 1.0,
        frozenset(["刘慈欣"]): 1.0,
        frozenset(["郝景芳"]): 1.0,
    }

    SUSPICIOUS_PAIRS = [
        ("余华", "余秋雨"),
        ("余华", "余杰"),
        ("余华", "余平"),
        ("鲁迅", "鲁"),
        ("鲁迅", "迅"),
        ("路遥", "路"),
        ("路遥", "遥远"),
        ("刘慈欣", "慈欣"),
        ("刘慈欣", "刘欣"),
        ("刘慈欣", "刘慈"),
        ("张爱玲", "爱玲"),
        ("钱钟书", "钟书"),
        ("沈从文", "从文"),
    ]

    def __init__(self):
        self._pseudonym_map = self._build_pseudonym_map()

    def _build_pseudonym_map(self) -> dict:
        alias_map = {}
        for names_set, confidence in self.KNOWN_PSEUDONYMS.items():
            names_list = list(names_set)
            for name in names_list:
                alias_map[name] = (names_list, confidence)
        return alias_map

    def verify_duplicate_candidate(
        self,
        title1: str, author1: str,
        title2: str, author2: str,
        isbn1: str = "", isbn2: str = "",
    ) -> VerificationResult:
        reasons = []

        if isbn1 and isbn2 and isbn1 == isbn2:
            return VerificationResult(
                is_same_book=True,
                author_confidence=1.0,
                title_confidence=1.0,
                overall_confidence=1.0,
                reasons=["ISBN精确匹配"],
                severity="high"
            )

        author_sim = AuthorSimilarity.compute(author1, author2)
        title_sim = TitleSimilarity.compute(title1, title2)

        pseudonym_match, pseudonym_conf = self._check_pseudonyms(author1, author2)
        if pseudonym_match:
            author_sim = max(author_sim, pseudonym_conf)
            reasons.append(f"已知笔名/别名匹配")

        suspicious = self._check_suspicious_pair(author1, author2)
        if suspicious:
            reasons.append("可疑相似作者名组合，加强验证")

        author_ok, author_conf = self._evaluate_author(author_sim, author1, author2)
        title_ok, title_conf = self._evaluate_title(title_sim, title1, title2)

        if author_ok:
            reasons.append(f"作者匹配度 {author_sim*100:.0f}%")
        else:
            reasons.append(f"作者差异大，匹配度仅 {author_sim*100:.0f}%")

        if title_ok:
            reasons.append(f"书名匹配度 {title_sim*100:.0f}%")
        else:
            reasons.append(f"书名匹配不足 {title_sim*100:.0f}%")

        overall = self._calculate_overall(author_sim, title_sim, isbn1, isbn2)

        is_match = self._final_decision(author_ok, title_ok, overall, author_sim, title_sim)

        severity = "high" if overall >= 0.9 else ("medium" if overall >= 0.7 else "low")

        if not is_match and author_sim < 0.30:
            reasons.insert(0, "❌ 作者名完全不同，疑似不同书")

        return VerificationResult(
            is_same_book=is_match,
            author_confidence=author_sim,
            title_confidence=title_sim,
            overall_confidence=overall,
            reasons=reasons,
            severity=severity
        )

    def _evaluate_author(self, sim: float, a1: str, a2: str) -> Tuple[bool, float]:
        if sim >= self.STRICT_AUTHOR_THRESHOLD:
            return True, 1.0
        if sim >= self.MODERATE_AUTHOR_THRESHOLD:
            len1 = len([c for c in a1 if "\u4e00" <= c <= "\u9fff"])
            len2 = len([c for c in a2 if "\u4e00" <= c <= "\u9fff"])
            if len1 == len2 and len1 >= 2:
                return True, 0.8
            if len1 >= 3 and len2 >= 3:
                return True, 0.7
            return False, sim
        if sim >= self.MIN_AUTHOR_THRESHOLD:
            return False, sim
        return False, 0.0

    def _evaluate_title(self, sim: float, t1: str, t2: str) -> Tuple[bool, float]:
        if sim >= self.STRICT_TITLE_THRESHOLD:
            return True, 1.0
        if sim >= self.MODERATE_TITLE_THRESHOLD:
            return True, 0.75
        if sim >= self.MIN_TITLE_THRESHOLD:
            return False, sim
        return False, 0.0

    def _calculate_overall(self, author_sim: float, title_sim: float,
                           isbn1: str = "", isbn2: str = "") -> float:
        has_isbn = bool(isbn1 and isbn2)
        if has_isbn:
            if isbn1 == isbn2:
                return 1.0
            else:
                return 0.0
        return 0.60 * author_sim + 0.40 * title_sim

    def _final_decision(self, author_ok: bool, title_ok: bool,
                        overall: float, author_sim: float, title_sim: float) -> bool:
        if author_sim < 0.30:
            return False
        if not author_ok and author_sim < 0.50:
            return False
        if overall >= 0.80 and author_ok and title_ok:
            return True
        if overall >= 0.75 and author_ok:
            return True
        if overall >= 0.85 and title_ok and author_sim >= 0.55:
            return True
        if overall < 0.60:
            return False
        if not author_ok:
            return False
        return overall >= 0.70

    def _check_pseudonyms(self, a1: str, a2: str) -> Tuple[bool, float]:
        clean1 = TextNormalizer.clean_text(a1)
        clean2 = TextNormalizer.clean_text(a2)
        if clean1 == clean2:
            return True, 1.0
        if clean1 in self._pseudonym_map:
            aliases, conf = self._pseudonym_map[clean1]
            if clean2 in aliases:
                return True, conf
        if clean2 in self._pseudonym_map:
            aliases, conf = self._pseudonym_map[clean2]
            if clean1 in aliases:
                return True, conf
        return False, 0.0

    def _check_suspicious_pair(self, a1: str, a2: str) -> bool:
        clean1 = TextNormalizer.clean_text(a1)
        clean2 = TextNormalizer.clean_text(a2)
        for (x, y) in self.SUSPICIOUS_PAIRS:
            if (clean1 == x and clean2 == y) or (clean1 == y and clean2 == x):
                return True
        return False

    def filter_false_positives(
        self,
        candidate_group: List[Tuple],
    ) -> List[Tuple]:
        if len(candidate_group) < 2:
            return candidate_group

        verified = [candidate_group[0]]
        for candidate in candidate_group[1:]:
            book1 = verified[0]
            title1, author1, isbn1 = (book1[0], book1[1], book1[2] if len(book1) > 2 else "")
            title2, author2, isbn2 = (candidate[0], candidate[1], candidate[2] if len(candidate) > 2 else "")
            result = self.verify_duplicate_candidate(
                title1, author1, title2, author2, isbn1, isbn2
            )
            if result.is_same_book:
                verified.append(candidate)
        return verified
