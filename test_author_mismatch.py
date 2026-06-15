import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import hashlib
from ebook_manager.models import BookMeta, BookFingerprint
from ebook_manager.duplicate_detector import DuplicateDetector, MatchConfig
from ebook_manager.similarity import (
    OverallBookSimilarity, TitleSimilarity, AuthorSimilarity, SimHashScore
)
from ebook_manager.author_verifier import AuthorVerifier, VerificationResult


def make_fingerprint(title, author, isbn="", simhash=0, size=0):
    fp = BookFingerprint()
    fp.isbn_normalized = isbn
    fp.title_key = hashlib.md5(BookMeta.normalize_title(title).encode()).hexdigest()
    fp.author_key = hashlib.md5(BookMeta.normalize_author(author).encode()).hexdigest()
    ta_hash = BookMeta.generate_title_author_key(title, author)
    fp.title_author_key = ta_hash
    fp.size_hash = hashlib.md5(f"{size}|{title}.epub".encode()).hexdigest()
    fp.simhash = simhash
    return fp


def make_book(title, author, file_path, isbn="", size=1000000, simhash=0, fmt="epub"):
    book = BookMeta(
        title=title, author=author, file_path=file_path,
        file_format=fmt, file_size=size, isbn=isbn,
        publisher="测试出版社", publish_date="2020-01-01"
    )
    book.fingerprint = make_fingerprint(title, author, isbn, simhash, size)
    book.metadata_completeness = book.calculate_metadata_completeness()
    return book


def test_title_author_keys_separation():
    t1, a1, _ = BookMeta.generate_title_author_keys("活着", "余华")
    t2, a2, _ = BookMeta.generate_title_author_keys("活着", "王小明")
    assert t1 == t2, "相同书名应该产生相同的title_key"
    assert a1 != a2, "不同作者应该产生不同的author_key"
    ta1 = BookMeta.generate_title_author_key("活着", "余华")
    ta2 = BookMeta.generate_title_author_key("活着", "王小明")
    assert ta1 != ta2, "不同作者的同名书title_author_key必须不同"
    print("✓ test_title_author_keys_separation 通过")


def test_author_verifier_same_title_different_author():
    verifier = AuthorVerifier()

    result = verifier.verify_duplicate_candidate(
        title1="活着", author1="余华",
        title2="活着", author2="王小明"
    )
    assert not result.is_same_book, f"两本《活着》作者完全不同，绝不能判定为重复，但结果为True，总体置信度{result.overall_confidence}"
    assert result.author_confidence <= 0.3, f"作者置信度应该很低，实际: {result.author_confidence}"
    print(f"  总体置信度: {result.overall_confidence:.2f}, 作者置信度: {result.author_confidence:.2f}, 书名置信度: {result.title_confidence:.2f}")
    print(f"  原因: {result.reasons}")
    print("✓ test_author_verifier_same_title_different_author 通过")


def test_author_verifier_pen_name():
    verifier = AuthorVerifier()
    result = verifier.verify_duplicate_candidate(
        title1="活着", author1="余华",
        title2="活着", author2="余华 著"
    )
    assert result.is_same_book, "带'著'后缀的应该识别为同一作者"
    print("✓ test_author_verifier_pen_name 通过")


def test_similarity_author_penalty():
    overall = OverallBookSimilarity()

    same_book_sim, _ = overall.compute(
        isbn1="", isbn2="",
        author1="余华", author2="余华",
        title1="活着", title2="活着",
        simhash1=0, simhash2=0, size1=1000, size2=1000,
        format1="epub", format2="epub"
    )

    diff_author_sim, _ = overall.compute(
        isbn1="", isbn2="",
        author1="余华", author2="王小明",
        title1="活着", title2="活着",
        simhash1=0, simhash2=0, size1=1000, size2=1000,
        format1="epub", format2="epub"
    )

    diff_pct = (same_book_sim - diff_author_sim) / same_book_sim * 100
    print(f"  同作者同名相似度: {same_book_sim:.4f}")
    print(f"  异作者同名相似度: {diff_author_sim:.4f}")
    print(f"  作者差异惩罚: -{diff_pct:.1f}%")
    assert same_book_sim > diff_author_sim, "同作者相似度必须高于异作者"
    assert diff_author_sim < 0.70, "异作者同名相似度必须低于0.70以避免误判"
    print("✓ test_similarity_author_penalty 通过")


def test_detector_not_group_different_authors():
    config = MatchConfig(
        title_author_match_threshold=0.90,
        simhash_threshold=0.80
    )
    detector = DuplicateDetector(config=config)

    books = [
        make_book("活着", "余华", "C:\\books\\活着_余华.epub", size=2000000, simhash=123456789),
        make_book("活着", "王小明", "C:\\books\\活着_王小明.epub", size=1800000, simhash=987654321),
        make_book("三体", "刘慈欣", "C:\\books\\三体_刘慈欣.epub", size=3000000, simhash=112233445),
        make_book("三体 典藏版", "刘慈欣", "C:\\books\\三体_刘慈欣_典藏.epub", size=3100000, simhash=112233445),
    ]

    groups = detector.detect(books)
    print(f"  检测到 {len(groups)} 组重复:")
    for g in groups:
        titles = ", ".join(f"{b.title}({b.author})" for b in g.books)
        print(f"    - [{g.match_type}] {titles} 相似度={g.similarity:.2f}")

    huozhe_groups = [g for g in groups if any("活着" in b.title for b in g.books)]
    if huozhe_groups:
        for g in huozhe_groups:
            authors = {b.author for b in g.books}
            assert len(authors) == 1, f"《活着》重复组中混入了不同作者: {authors}"

    santi_groups = [g for g in groups if any("三体" in b.title for b in g.books)]
    assert len(santi_groups) >= 1, "刘慈欣的两本《三体》应该被识别为重复"

    print("✓ test_detector_not_group_different_authors 通过")


def test_edge_case_similar_surname():
    config = MatchConfig()
    detector = DuplicateDetector(config=config)

    books = [
        make_book("平凡的世界", "路遥", "C:\\books\\平凡的世界_路遥.epub", size=5000000),
        make_book("平凡的世界", "路遥著", "C:\\books\\平凡的世界_路遥著.epub", size=5000000),
        make_book("平凡的世界", "路遥远", "C:\\books\\平凡的世界_路遥远.epub", size=4900000),
    ]

    groups = detector.detect(books)
    print(f"  检测到 {len(groups)} 组重复:")
    for g in groups:
        titles = ", ".join(f"{b.title}({b.author})" for b in g.books)
        print(f"    - [{g.match_type}] {titles} 相似度={g.similarity:.2f}")

    for g in groups:
        for b in g.books:
            if "路遥远" in b.author:
                coauthors = {x.author for x in g.books if x != b}
                assert "路遥" not in coauthors, "路遥 与 路遥远 是不同作者，不应被分组"
    print("✓ test_edge_case_similar_surname 通过")


def test_edge_case_anonymous_author():
    config = MatchConfig()
    detector = DuplicateDetector(config=config)

    books = [
        make_book("佚名作品集", "佚名", "C:\\books\\佚名作品集_a.epub", size=1000000),
        make_book("佚名作品集", "佚名", "C:\\books\\佚名作品集_b.epub", size=1000000),
        make_book("佚名作品集", "", "C:\\books\\佚名作品集_noauthor.epub", size=990000),
    ]

    groups = detector.detect(books)
    print(f"  检测到 {len(groups)} 组重复:")
    for g in groups:
        titles = ", ".join(f"{b.title}({b.author or '空'})" for b in g.books)
        print(f"    - [{g.match_type}] {titles} 相似度={g.similarity:.2f}")

    print("✓ test_edge_case_anonymous_author 通过")


def test_many_different_authors():
    config = MatchConfig()
    detector = DuplicateDetector(config=config)

    same_title_authors = [
        "余华", "王小明", "张三", "李四", "陈晓明",
        "李华", "王建国", "刘芳", "赵卫东", "孙丽萍"
    ]

    books = []
    for i, author in enumerate(same_title_authors):
        books.append(make_book(
            "活着", author,
            f"C:\\books\\活着_{i}.epub",
            size=1000000 + i * 10000,
            simhash=i * 1000
        ))

    books.append(make_book(
        "活着", "余华",
        "C:\\books\\活着_余华_修订版.epub",
        size=1050000, simhash=0
    ))

    groups = detector.detect(books)
    print(f"  检测到 {len(groups)} 组重复:")
    for g in groups:
        authors = [b.author for b in g.books]
        print(f"    - [{g.match_type}] 作者: {authors} 相似度={g.similarity:.2f}")

    total_in_groups = sum(len(g.books) for g in groups)
    unique_authors_in_groups = set()
    for g in groups:
        group_authors = {b.author for b in g.books}
        assert len(group_authors) == 1, f"单个重复组中出现了多个作者: {group_authors}"
        unique_authors_in_groups.update(group_authors)

    print(f"  共 {len(books)} 本书，被分到 {total_in_groups} 本进重复组")
    print(f"  涉及 {len(unique_authors_in_groups)} 位作者")
    assert "余华" in unique_authors_in_groups, "余华的两本《活着》应该被识别为重复"
    print("✓ test_many_different_authors 通过")


def run_all_tests():
    print("=" * 60)
    print("同名不同作者误判问题修复 - 专项测试")
    print("=" * 60)

    tests = [
        ("书名/作者指纹分离", test_title_author_keys_separation),
        ("作者验证器 - 同名异作者", test_author_verifier_same_title_different_author),
        ("作者验证器 - 笔名/著后缀", test_author_verifier_pen_name),
        ("相似度惩罚机制", test_similarity_author_penalty),
        ("检测器 - 不混入异作者", test_detector_not_group_different_authors),
        ("边界 - 相似姓氏", test_edge_case_similar_surname),
        ("边界 - 匿名/空作者", test_edge_case_anonymous_author),
        ("压力 - 10作者同名书", test_many_different_authors),
    ]

    passed = 0
    failed = []
    for name, test_fn in tests:
        print(f"\n【测试】{name}")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"✗ {name} 失败: {e}")
            failed.append((name, str(e)))
        except Exception as e:
            print(f"✗ {name} 异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed.append((name, f"{type(e).__name__}: {e}"))

    print("\n" + "=" * 60)
    print(f"测试结果: {passed}/{len(tests)} 通过")
    if failed:
        print(f"失败的测试:")
        for name, err in failed:
            print(f"  ✗ {name}: {err}")
        return False
    print("全部通过！🎉")
    return True


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
