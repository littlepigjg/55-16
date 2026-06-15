import re
import hashlib
from difflib import SequenceMatcher
from typing import Tuple, List, Dict
from collections import defaultdict

from .text_utils import TextNormalizer


class TextSimilarity:
    @staticmethod
    def jaccard_similarity(set1: set, set2: set) -> float:
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def ngram_similarity(text1: str, text2: str, n: int = 3) -> float:
        if not text1 or not text2:
            return 0.0
        if text1 == text2:
            return 1.0
        def get_ngrams(text, n):
            text = text.replace(" ", "")
            if len(text) < n:
                return {text}
            return {text[i:i+n] for i in range(len(text) - n + 1)}
        grams1 = get_ngrams(text1, n)
        grams2 = get_ngrams(text2, n)
        return TextSimilarity.jaccard_similarity(grams1, grams2)

    @staticmethod
    def sequence_similarity(text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        if text1 == text2:
            return 1.0
        return SequenceMatcher(None, text1, text2).ratio()

    @staticmethod
    def combined_similarity(text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        if text1 == text2:
            return 1.0
        norm1 = TextNormalizer.normalize_general(text1)
        norm2 = TextNormalizer.normalize_general(text2)
        if norm1 and norm1 == norm2:
            return 0.98
        clean1 = TextNormalizer.clean_text(text1)
        clean2 = TextNormalizer.clean_text(text2)
        seq_sim = TextSimilarity.sequence_similarity(clean1, clean2)
        ngram2_sim = TextSimilarity.ngram_similarity(clean1, clean2, n=2)
        ngram3_sim = TextSimilarity.ngram_similarity(clean1, clean2, n=3)
        token_set1 = set(norm1.split()) if norm1 else set()
        token_set2 = set(norm2.split()) if norm2 else set()
        jaccard_sim = TextSimilarity.jaccard_similarity(token_set1, token_set2)
        weights = {
            "seq": 0.30,
            "ngram2": 0.25,
            "ngram3": 0.30,
            "jaccard": 0.15,
        }
        total_w = sum(weights.values())
        return (
            weights["seq"] * seq_sim +
            weights["ngram2"] * ngram2_sim +
            weights["ngram3"] * ngram3_sim +
            weights["jaccard"] * jaccard_sim
        ) / total_w


class AuthorSimilarity:
    CHINESE_AUTHOR_SURNAME_SET = {
        "李", "王", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
        "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
        "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
        "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
        "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎",
        "余", "潘", "杜", "戴", "夏", "钟", "汪", "田", "任", "姜",
        "范", "方", "石", "姚", "谭", "廖", "邹", "熊", "金", "陆",
        "郝", "孔", "白", "崔", "康", "毛", "邱", "秦", "江", "史",
        "顾", "侯", "邵", "孟", "龙", "万", "段", "雷", "钱", "汤",
        "尹", "黎", "易", "常", "武", "乔", "贺", "赖", "龚", "文",
        "鲁", "路", "乔", "文", "欧", "欧阳", "司马", "上官", "诸葛",
        "皇甫", "尉迟", "公孙", "慕容", "令狐", "宇文", "独孤",
        "余", "华", "平", "寒", "朔",
    }

    @staticmethod
    def compute(author1: str, author2: str) -> float:
        if not author1 or not author2:
            return 0.5
        clean1 = TextNormalizer.normalize_author(author1)
        clean2 = TextNormalizer.normalize_author(author2)
        if clean1 == clean2:
            return 1.0
        raw1 = TextNormalizer.clean_text(author1)
        raw2 = TextNormalizer.clean_text(author2)
        if raw1 == raw2:
            return 0.95
        is_cn1 = bool(re.search(r"[\u4e00-\u9fff]", raw1))
        is_cn2 = bool(re.search(r"[\u4e00-\u9fff]", raw2))
        if is_cn1 and is_cn2:
            return AuthorSimilarity._chinese_author_similarity(raw1, raw2, clean1, clean2)
        else:
            return AuthorSimilarity._western_author_similarity(raw1, raw2, clean1, clean2)

    @staticmethod
    def _chinese_author_similarity(raw1: str, raw2: str, norm1: str, norm2: str) -> float:
        chars1 = [c for c in raw1 if "\u4e00" <= c <= "\u9fff"]
        chars2 = [c for c in raw2 if "\u4e00" <= c <= "\u9fff"]
        if not chars1 or not chars2:
            return TextSimilarity.combined_similarity(raw1, raw2)
        len1, len2 = len(chars1), len(chars2)
        if len1 == len2 == 1:
            return 1.0 if chars1[0] == chars2[0] else 0.0
        if len1 == len2 == 2:
            if chars1 == chars2:
                return 1.0
            if chars1[0] == chars2[0] and chars1[1] != chars2[1]:
                return 0.25
            if chars1[1] == chars2[1] and chars1[0] != chars2[0]:
                return 0.15
            return 0.0
        if len1 == len2 == 3:
            if chars1 == chars2:
                return 1.0
            if chars1[0] == chars2[0] and chars1[1:] == chars2[1:]:
                return 0.9
            if chars1[0] == chars2[0] and chars1[1] == chars2[1]:
                return 0.6
            if chars1[0] == chars2[0]:
                return 0.25
            if chars1[1:] == chars2[1:]:
                return 0.35
            return TextSimilarity.ngram_similarity("".join(chars1), "".join(chars2), n=2) * 0.5
        base_sim = TextSimilarity.sequence_similarity("".join(chars1), "".join(chars2))
        first_char_match = 1.0 if chars1 and chars2 and chars1[0] == chars2[0] else 0.0
        all_match_ratio = len(set(chars1) & set(chars2)) / max(len(set(chars1)), len(set(chars2)))
        if len(chars1) >= 2 and len(chars2) >= 2:
            suffix1 = "".join(chars1[1:])
            suffix2 = "".join(chars2[1:])
            suffix_match = TextSimilarity.sequence_similarity(suffix1, suffix2)
        else:
            suffix_match = 0.0
        score = (
            0.25 * first_char_match +
            0.35 * suffix_match +
            0.20 * base_sim +
            0.20 * all_match_ratio
        )
        if len(chars1) <= 2 and len(chars2) <= 2 and len(chars1) != len(chars2):
            score *= 0.5
        return min(score, 1.0)

    @staticmethod
    def _western_author_similarity(raw1: str, raw2: str, norm1: str, norm2: str) -> float:
        def split_parts(name):
            cleaned = re.sub(r"[^a-zA-Z\s]", " ", name.lower())
            tokens = [t for t in cleaned.split() if len(t) > 1]
            return tokens
        tokens1 = split_parts(raw1)
        tokens2 = split_parts(raw2)
        if not tokens1 or not tokens2:
            return TextSimilarity.combined_similarity(raw1, raw2)
        if tokens1[-1].lower() == tokens2[-1].lower():
            surname_score = 1.0
        else:
            surname_score = 0.0
        given_sim = 0.0
        if len(tokens1) > 1 and len(tokens2) > 1:
            given1 = " ".join(tokens1[:-1])
            given2 = " ".join(tokens2[:-1])
            given_sim = TextSimilarity.combined_similarity(given1, given2)
        initials1 = {t[0] for t in tokens1[:-1]}
        initials2 = {t[0] for t in tokens2[:-1]}
        if initials1 and initials2:
            initial_sim = len(initials1 & initials2) / len(initials1 | initials2)
        else:
            initial_sim = 0.0
        score = (
            0.50 * surname_score +
            0.30 * given_sim +
            0.20 * initial_sim
        )
        return score


class TitleSimilarity:
    @staticmethod
    def compute(title1: str, title2: str) -> float:
        if not title1 or not title2:
            return 0.0
        clean1 = TextNormalizer.clean_text(title1)
        clean2 = TextNormalizer.clean_text(title2)
        if clean1 == clean2:
            return 1.0
        norm1 = TextNormalizer.normalize_title(title1)
        norm2 = TextNormalizer.normalize_title(title2)
        if norm1 == norm2 and norm1:
            return 0.98
        cn1 = bool(re.search(r"[\u4e00-\u9fff]", clean1))
        cn2 = bool(re.search(r"[\u4e00-\u9fff]", clean2))
        if cn1 and cn2:
            return TitleSimilarity._chinese_title_similarity(clean1, clean2, norm1, norm2)
        else:
            return TitleSimilarity._western_title_similarity(clean1, clean2, norm1, norm2)

    @staticmethod
    def _chinese_title_similarity(raw1: str, raw2: str, norm1: str, norm2: str) -> float:
        ngram2 = TextSimilarity.ngram_similarity(raw1, raw2, n=2)
        ngram3 = TextSimilarity.ngram_similarity(raw1, raw2, n=3)
        seq_sim = TextSimilarity.sequence_similarity(raw1, raw2)
        chars1 = set(re.findall(r"[\u4e00-\u9fff]", raw1))
        chars2 = set(re.findall(r"[\u4e00-\u9fff]", raw2))
        char_jaccard = TextSimilarity.jaccard_similarity(chars1, chars2)
        score = (
            0.30 * ngram2 +
            0.25 * ngram3 +
            0.25 * seq_sim +
            0.20 * char_jaccard
        )
        return score

    @staticmethod
    def _western_title_similarity(raw1: str, raw2: str, norm1: str, norm2: str) -> float:
        return TextSimilarity.combined_similarity(raw1, raw2)


class OverallBookSimilarity:
    def __init__(self):
        self.weights = {
            "isbn": 0.40,
            "author": 0.25,
            "title": 0.20,
            "simhash": 0.10,
            "size": 0.05,
        }

    def compute(
        self,
        isbn1: str, isbn2: str,
        author1: str, author2: str,
        title1: str, title2: str,
        simhash1: int, simhash2: int,
        size1: int, size2: int,
        format1: str = "", format2: str = "",
    ) -> Tuple[float, Dict[str, float]]:
        scores = {}
        scores["isbn"] = self._isbn_score(isbn1, isbn2)
        scores["author"] = AuthorSimilarity.compute(author1, author2)
        scores["title"] = TitleSimilarity.compute(title1, title2)
        scores["simhash"] = self._simhash_score(simhash1, simhash2)
        scores["size"] = self._size_score(size1, size2, format1, format2)

        weights = dict(self.weights)
        if not (isbn1 and isbn2):
            weights["simhash"] += weights["isbn"] * 0.6
            weights["title"] += weights["isbn"] * 0.2
            weights["author"] += weights["isbn"] * 0.2
            weights["isbn"] = 0.0
        if simhash1 == 0 or simhash2 == 0:
            extra = weights["simhash"]
            weights["title"] += extra * 0.5
            weights["author"] += extra * 0.3
            weights["size"] += extra * 0.2
            weights["simhash"] = 0.0

        total_weight = sum(weights.values())
        if total_weight == 0:
            return 0.0, scores

        weighted = sum(scores[k] * weights[k] for k in scores)
        final_score = weighted / total_weight

        if scores["author"] < 0.25 and scores["isbn"] < 0.5:
            final_score = min(final_score, 0.35)
        elif scores["author"] < 0.45 and scores["isbn"] < 0.5:
            final_score = min(final_score, 0.65)

        if scores["title"] < 0.4:
            final_score = min(final_score, 0.45)

        return final_score, scores

    @staticmethod
    def _isbn_score(isbn1: str, isbn2: str) -> float:
        if not isbn1 or not isbn2:
            return 0.0
        return 1.0 if isbn1 == isbn2 else 0.0

    @staticmethod
    def _simhash_score(hash1: int, hash2: int) -> float:
        if hash1 == 0 or hash2 == 0:
            return 0.0
        return SimHashScore.similarity(hash1, hash2)

    @staticmethod
    def _size_score(size1: int, size2: int, fmt1: str = "", fmt2: str = "") -> float:
        if size1 == 0 or size2 == 0:
            return 0.5
        ratio = min(size1, size2) / max(size1, size2)
        if fmt1 and fmt2 and fmt1.lower() != fmt2.lower():
            return min(ratio + 0.15, 1.0)
        return ratio


class SimHashScore:
    HASH_BITS = 64

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        x = hash1 ^ hash2
        distance = 0
        while x:
            distance += 1
            x &= x - 1
        return distance

    @staticmethod
    def similarity(hash1: int, hash2: int) -> float:
        if hash1 == 0 or hash2 == 0:
            return 0.0
        if hash1 == hash2:
            return 1.0
        distance = SimHashScore.hamming_distance(hash1, hash2)
        return 1.0 - (distance / SimHashScore.HASH_BITS)
