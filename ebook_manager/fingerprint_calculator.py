import os
import re
import hashlib
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional
from pathlib import Path
from collections import defaultdict

from .models import BookMeta, BookFingerprint


class SimHash:
    def __init__(self, hash_bits: int = 64):
        self.hash_bits = hash_bits
        self._stopwords = self._load_stopwords()

    def _load_stopwords(self):
        return {
            "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were",
            "be", "been", "being", "have", "has", "had", "do", "does",
            "did", "will", "would", "could", "should", "may", "might",
            "must", "shall", "mustn", "don", "didn", "wasn", "weren",
            "this", "that", "these", "those", "it", "its", "it's", "i", "you",
            "he", "she", "we", "they", "me", "him", "her", "us", "them",
            "my", "your", "his", "her", "our", "their", "me", "him", "her",
            "not", "no", "nor", "not", "so", "than", "too", "very", "just",
            "also", "then", "now", "here", "there", "where", "when", "why",
            "which", "who", "whom", "whose", "what", "which", "how", "all",
            "both", "each", "few", "more", "most", "other", "some", "such",
            "no", "nor", "not", "only", "own", "same", "so", "than", "too",
            "de", "la", "le", "les", "du", "des", "un", "une", "el",
            "los", "las", "al", "del", "y", "o", "en", "de", "para",
            "por", "con", "sin", "sobre", "entre", "da", "das", "dos",
            "no", "na", "nas", "nos", "em", "ao", "aos", "à", "às",
            "do", "da", "dos", "das", "em", "por", "para", "com", "sem",
            "的", "是", "在", "了", "和", "与", "及", "与", "或", "一个",
            "这", "那", "我", "你", "他", "她", "它", "我们", "你们", "他们",
            "这个", "那个", "这些", "那些", "这里", "那里", "什么", "谁", "哪",
            "就", "都", "也", "还", "又", "再", "又", "很", "更", "最",
            "不", "没", "有", "要", "会", "能", "可以", "应该", "必须",
            "因为", "所以", "但是", "虽然", "如果", "即使", "只要", "只有",
            "关于", "对于", "为了", "按照", "通过", "根据", "关于",
            "第一章", "第二章", "第三章", "第四章", "第五章", "第六章",
            "第七章", "第七章", "第八章", "第九章", "第十章", "目录", "前言",
            "序言", "引言", "摘要", "绪论", "第一章", "内容简介", "作者简介",
            "版权页", "目录页", "封面", "封底", "扉页", "内容提要",
        }

    def _tokenize(self, text: str) -> list:
        text = text.lower()
        text = re.sub(r"[^\w\u4e00-\u9fff]", " ", text)
        text = re.sub(r"\s+", " ", text)
        tokens = []
        english_words = re.findall(r"[a-zA-Z]+", text)
        tokens.extend([w for w in english_words if w not in self._stopwords and len(w) > 1])
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        chinese_text = "".join(chinese_chars)
        if len(chinese_text) >= 2:
            for i in range(len(chinese_text) - 1):
                bigram = chinese_text[i:i+2]
                if not any(c in self._stopwords for c in bigram):
                    tokens.append(bigram)
            if len(chinese_text) >= 3:
                for i in range(len(chinese_text) - 2):
                    trigram = chinese_text[i:i+3]
                    if not any(c in self._stopwords for c in trigram):
                        tokens.append(trigram)
        return tokens

    def _weighted_frequencies(self, tokens: list) -> dict:
        freq = defaultdict(int)
        for token in tokens:
            freq[token] += 1
        total = len(tokens)
        if total == 0:
            return {}
        return {word: count / total for word, count in freq.items()}

    def _hash_token(self, token: str) -> int:
        h = hashlib.sha1(token.encode("utf-8")).hexdigest()
        return int(h[:16], 16)

    def compute(self, text: str) -> int:
        tokens = self._tokenize(text)
        if not tokens:
            return 0
        weights = self._weighted_frequencies(tokens)
        if not weights:
            return 0
        v = [0.0] * self.hash_bits
        for token, weight in weights.items():
            h = self._hash_token(token)
            for i in range(self.hash_bits):
                bitmask = 1 << i
                if h & bitmask:
                    v[i] += weight
                else:
                    v[i] -= weight
        fingerprint = 0
        for i in range(self.hash_bits):
            if v[i] > 0:
                fingerprint |= (1 << i)
        return fingerprint

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        x = hash1 ^ hash2
        distance = 0
        while x:
            distance += 1
            x &= x - 1
        return distance

    @staticmethod
    def similarity(hash1: int, hash2: int, hash_bits: int = 64) -> float:
        if hash1 == 0 or hash2 == 0:
            return 0.0
        distance = SimHash.hamming_distance(hash1, hash2)
        return 1.0 - (distance / hash_bits)


class TextExtractor:
    def __init__(self, max_chars: int = 1000):
        self.max_chars = max_chars

    def extract(self, book: BookMeta) -> str:
        ext = Path(book.file_path).suffix.lower()
        text = ""
        try:
            if ext == ".epub":
                text = self._extract_epub_text(book.file_path)
            elif ext == ".pdf":
                text = self._extract_pdf_text(book.file_path)
            elif ext == ".mobi":
                text = self._extract_mobi_text(book.file_path)
        except Exception:
            pass
        return text[:self.max_chars]

    def _extract_epub_text(self, file_path: str) -> str:
        text_parts = []
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                opf_path = self._find_opf_path(zf)
                if not opf_path:
                    return ""
                opf_dir = str(Path(opf_path).parent)
                root = ET.fromstring(zf.read(opf_path))
                manifest = root.find(".//{http://www.idpf.org/2007/opf}manifest")
                spine = root.find(".//{http://www.idpf.org/2007/opf}spine")
                if manifest is None or spine is None:
                    return ""
                hrefs = []
                for itemref in spine:
                    id_ref = itemref.get("idref")
                    for item in manifest:
                        if item.get("id") == id_ref:
                            href = item.get("href", "")
                            if href.endswith((".xhtml", ".html", ".htm")):
                                hrefs.append(href)
                                break
                chars_collected = 0
                for href in hrefs:
                    if chars_collected >= self.max_chars:
                        break
                    if opf_dir:
                        full_path = str(Path(opf_dir) / href)
                    else:
                        full_path = href
                    full_path = full_path.replace("\\", "/")
                    try:
                        content = zf.read(full_path).decode("utf-8", errors="ignore")
                        clean_text = re.sub(r"<[^>]+>", " ", content)
                        clean_text = re.sub(r"\s+", " ", clean_text)
                        text_parts.append(clean_text.strip())
                        chars_collected += len(clean_text)
                    except Exception:
                        continue
        except Exception:
            pass
        return " ".join(text_parts)

    def _find_opf_path(self, zf: zipfile.ZipFile) -> Optional[str]:
        try:
            container = zf.read("META-INF/container.xml").decode("utf-8", errors="ignore")
            root = ET.fromstring(container)
            rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            if rootfile is not None:
                return rootfile.get("full-path")
        except Exception:
            pass
        for name in zf.namelist():
            if name.endswith(".opf"):
                return name
        return None

    def _extract_pdf_text(self, file_path: str) -> str:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text_parts = []
            chars_collected = 0
            for page in reader.pages:
                if chars_collected >= self.max_chars:
                    break
                try:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
                    chars_collected += len(page_text)
                except Exception:
                    continue
            return " ".join(text_parts)
        except Exception:
            return ""

    def _extract_mobi_text(self, file_path: str) -> str:
        try:
            with open(file_path, "rb") as f:
                header = f.read(78)
                if len(header) < 78:
                    return ""
                mobi_start = int.from_bytes(header[60:64], "big")
                f.seek(mobi_start)
                mobi_header = f.read(200)
                if len(mobi_header) < 24:
                    return ""
                encoding = int.from_bytes(mobi_header[12:16], "big")
                codec = "utf-8" if encoding == 65001 else "cp1252"
                text_start = int.from_bytes(mobi_header[184:188], "big")
                text_len = int.from_bytes(mobi_header[188:192], "big")
                f.seek(text_start)
                raw_text = f.read(min(text_len, self.max_chars * 4))
                try:
                    text = raw_text.decode(codec, errors="ignore")
                except Exception:
                    text = raw_text.decode("utf-8", errors="ignore")
                text = re.sub(r"[^\w\u4e00-\u9fff\s]", " ", text)
                text = re.sub(r"\s+", " ", text)
                return text.strip()
        except Exception:
            return ""


class FingerprintCalculator:
    def __init__(self, progress_callback=None):
        self.simhash = SimHash()
        self.text_extractor = TextExtractor(max_chars=1000)
        self.progress_callback = progress_callback

    def calculate(self, book: BookMeta) -> BookFingerprint:
        book.generate_fingerprint_keys()
        text = self.text_extractor.extract(book)
        book.fingerprint.text_preview = text[:200]
        book.fingerprint.simhash = self.simhash.compute(text)
        return book.fingerprint

    def calculate_batch(self, books: list) -> list:
        results = []
        total = len(books)
        for i, book in enumerate(books):
            if self.progress_callback:
                self.progress_callback(i + 1, total, book.file_path)
            book.fingerprint = self.calculate(book)
            book.metadata_completeness = book.calculate_metadata_completeness()
            results.append(book)
        return results
