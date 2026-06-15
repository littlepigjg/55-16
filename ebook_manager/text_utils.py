import re
import unicodedata
import hashlib
from typing import List, Set, Tuple


class TextNormalizer:
    ENGLISH_STOPWORDS: Set[str] = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might",
        "must", "shall", "can", "need", "dare", "ought", "used",
        "this", "that", "these", "those", "it", "its", "i", "you",
        "he", "she", "we", "they", "me", "him", "her", "us", "them",
        "my", "your", "his", "her", "our", "their", "not", "no",
        "nor", "so", "than", "too", "very", "just", "also", "then",
        "now", "here", "there", "where", "when", "why", "which",
        "who", "whom", "what", "how", "all", "both", "each", "few",
        "more", "most", "other", "some", "such", "only", "own",
        "same", "as", "if", "than", "because", "about", "into",
    }

    ROMANCE_STOPWORDS: Set[str] = {
        "de", "la", "le", "les", "du", "des", "un", "une", "el",
        "los", "las", "al", "del", "y", "o", "en", "para", "por",
        "con", "sin", "sobre", "entre", "a", "e", "do", "da",
        "das", "dos", "no", "na", "nas", "nos", "em", "ao", "aos",
        "à", "às", "como", "quando", "onde", "qual", "quais",
        "quem", "muito", "mais", "menos", "bem", "mal", "já",
        "ainda", "também", "tambem", "assim", "mesmo", "mesma",
    }

    CHINESE_STOPWORDS_SINGLE: Set[str] = {
        "的", "了", "和", "与", "及", "或", "是", "在", "我", "你",
        "他", "她", "它", "这", "那", "有", "不", "没", "就", "都",
        "也", "还", "又", "再", "很", "更", "最", "被", "把", "让",
        "给", "从", "向", "往", "由", "以", "于", "因", "为",
        "如", "若", "虽", "但", "而", "且", "并", "等", "等", "啊",
        "吗", "呢", "吧", "呀", "哦", "嗯", "之", "其", "此", "彼",
    }

    CHINESE_STOPWORDS_MULTI: Set[str] = {
        "一个", "一些", "一样", "一定", "一起", "一直", "已经", "可以",
        "但是", "因为", "所以", "虽然", "如果", "即使", "只要", "只有",
        "关于", "对于", "为了", "按照", "通过", "根据", "以及", "而且",
        "或者", "还是", "不是", "没有", "不能", "不会", "不要", "不可",
        "什么", "怎么", "为什么", "哪里", "哪个", "哪些", "谁的",
        "现在", "以前", "以后", "当时", "同时", "然后", "最后", "首先",
    }

    BOOK_TITLE_SUFFIXES: Set[str] = {
        "珍藏版", "典藏版", "修订版", "新版", "精装版", "平装版",
        "全集", "选集", "合集", "套装", "上下册", "全册", "完整版",
        "精简版", "插图版", "注释版", "导读版", "纪念版", "限量版",
        "第一版", "第二版", "第三版", "增订版", "补编版", "译文版",
        "原版", "影印版", "扫描版", "电子版", "网络版", "试行版",
    }

    AUTHOR_ROLE_SUFFIXES: Set[str] = {
        "著", "编", "译", "注", "主编", "校对", "注释", "编写",
        "编著", "编译", "译注", "审校", "校注", "整理", "改编",
        "口述", "执笔", "绘", "画", "摄影", "篆刻", "书",
    }

    PUNCTUATION_PATTERN = re.compile(
        r"[《》【】\[\]()（）{}<>〈〉「」『』《》〈〉、，。；：\"\"''！？·—…～\-/\\\|`~@#\$%\^&\*\+=]"
    )

    @classmethod
    def normalize_title(cls, title: str) -> str:
        if not title:
            return ""
        text = cls._remove_punctuation(title)
        for suffix in sorted(cls.BOOK_TITLE_SUFFIXES, key=len, reverse=True):
            text = text.replace(suffix, "")
            if text.endswith(suffix):
                text = text[:-len(suffix)]
        text = text.strip()
        return cls._normalize_general(text, for_author=False)

    @classmethod
    def normalize_author(cls, author: str) -> str:
        if not author:
            return ""
        text = cls._remove_punctuation(author)
        for role in sorted(cls.AUTHOR_ROLE_SUFFIXES, key=len, reverse=True):
            text = text.replace(role, "")
            if text.endswith(role):
                text = text[:-len(role)]
        separators = ["，", ",", "、", ";", "；", "和", "与", "及", "等", "/", "\\"]
        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                text = parts[0].strip()
                break
        text = text.strip()
        return cls._normalize_general(text, for_author=True)

    @classmethod
    def normalize_general(cls, text: str) -> str:
        if not text:
            return ""
        return cls._normalize_general(text, for_author=False)

    @classmethod
    def _normalize_general(cls, text: str, for_author: bool = False) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", text)
        ascii_part = ""
        chinese_chars = []
        for ch in text:
            cp = ord(ch)
            if 0x4e00 <= cp <= 0x9fff:
                chinese_chars.append(ch)
            elif 0 <= cp < 128:
                ascii_part += ch
            else:
                decomposed = unicodedata.normalize("NFKD", ch)
                ascii_candidates = [c for c in decomposed if ord(c) < 128]
                ascii_part += "".join(ascii_candidates)
        ascii_part = ascii_part.lower()
        ascii_part = re.sub(r"[^a-z0-9\s]", " ", ascii_part)
        ascii_part = re.sub(r"\s+", " ", ascii_part).strip()
        ascii_words = [
            w for w in ascii_part.split()
            if len(w) > 1 and w not in cls.ENGLISH_STOPWORDS and w not in cls.ROMANCE_STOPWORDS
        ]
        chinese_filtered = []
        if for_author:
            chinese_filtered = list(chinese_chars)
        else:
            stopwords_single = cls.CHINESE_STOPWORDS_SINGLE
            chinese_joined = "".join(chinese_chars)
            for sw in cls.CHINESE_STOPWORDS_MULTI:
                chinese_joined = chinese_joined.replace(sw, "")
            for ch in chinese_joined:
                if ch not in stopwords_single:
                    chinese_filtered.append(ch)
        result_tokens = []
        if ascii_words:
            result_tokens.extend(sorted(ascii_words))
        if chinese_filtered:
            if for_author:
                result_tokens.append("".join(chinese_filtered))
            else:
                result_tokens.extend(sorted(chinese_filtered))
        return " ".join(result_tokens)

    @classmethod
    def _remove_punctuation(cls, text: str) -> str:
        if not text:
            return ""
        text = cls.PUNCTUATION_PATTERN.sub(" ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class ISBNNormalizer:
    @staticmethod
    def normalize(isbn: str) -> str:
        if not isbn:
            return ""
        digits = re.sub(r"[^\dXx]", "", isbn)
        digits = digits.upper()
        if len(digits) == 10:
            return ISBNNormalizer.isbn10_to_isbn13(digits)
        elif len(digits) == 13:
            return digits if ISBNNormalizer.validate_isbn13(digits) else ""
        return ""

    @staticmethod
    def isbn10_to_isbn13(isbn10: str) -> str:
        if len(isbn10) != 10:
            return ""
        prefix = "978" + isbn10[:9]
        total = 0
        for i, c in enumerate(prefix):
            try:
                digit = int(c)
            except ValueError:
                return ""
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


class FingerprintGenerator:
    @staticmethod
    def title_hash(title: str) -> str:
        norm = TextNormalizer.normalize_title(title)
        return hashlib.md5(norm.encode("utf-8")).hexdigest()

    @staticmethod
    def author_hash(author: str) -> str:
        norm = TextNormalizer.normalize_author(author)
        return hashlib.md5(norm.encode("utf-8")).hexdigest()

    @staticmethod
    def title_author_hash(title: str, author: str) -> Tuple[str, str, str]:
        t_hash = FingerprintGenerator.title_hash(title)
        a_hash = FingerprintGenerator.author_hash(author)
        combined = f"{t_hash}|{a_hash}"
        return t_hash, a_hash, hashlib.md5(combined.encode("utf-8")).hexdigest()

    @staticmethod
    def size_hash(file_size: int, filename: str = "") -> str:
        if filename:
            size_str = f"{file_size}|{filename.lower()}"
        else:
            size_str = str(file_size)
        return hashlib.md5(size_str.encode("utf-8")).hexdigest()
