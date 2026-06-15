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


def test_weight_sum_is_one():
    overall = OverallBookSimilarity()
    total = sum(overall.weights.values())
    print(f"  各字段权重: {overall.weights}")
    print(f"  权重总和: {total}")
    assert abs(total - 1.0) < 1e-6, f"权重总和必须等于1.0，实际: {total}"
    assert overall.weights["author"] == 0.60, f"作者权重必须等于0.60，实际: {overall.weights['author']}"
    assert overall.weights["author"] > overall.weights["title"], "作者权重必须大于书名权重"
    print("✓ test_weight_sum_is_one 通过")


def test_author_weight_dominates_title():
    overall = OverallBookSimilarity()

    same_author_same_title, _ = overall.compute(
        isbn1="", isbn2="",
        author1="余华", author2="余华",
        title1="活着", title2="活着",
        simhash1=0, simhash2=0, size1=1000, size2=1000,
        format1="epub", format2="epub"
    )

    diff_author_same_title, _ = overall.compute(
        isbn1="", isbn2="",
        author1="余华", author2="余秋雨",
        title1="活着", title2="活着",
        simhash1=0, simhash2=0, size1=1000, size2=1000,
        format1="epub", format2="epub"
    )

    same_author_diff_title, _ = overall.compute(
        isbn1="", isbn2="",
        author1="余华", author2="余华",
        title1="活着", title2="兄弟",
        simhash1=0, simhash2=0, size1=1000, size2=1000,
        format1="epub", format2="epub"
    )

    print(f"  同作者同名书:     {same_author_same_title:.4f}")
    print(f"  异作者同名书(余华vs余秋雨): {diff_author_same_title:.4f}")
    print(f"  同作者异名书:     {same_author_diff_title:.4f}")

    assert same_author_same_title > 0.90, "同作者同名书相似度应该很高"
    assert diff_author_same_title < 0.50, f"异作者同名书相似度必须低于0.50，实际: {diff_author_same_title}"
    assert same_author_diff_title < diff_author_same_title * 1.5, "作者权重占主导时，异作者惩罚应更明显"

    penalty = (same_author_same_title - diff_author_same_title) / same_author_same_title * 100
    print(f"  作者差异造成的相似度惩罚: -{penalty:.1f}%")
    assert penalty >= 50, f"作者差异惩罚必须至少50%，实际: {penalty:.1f}%"
    print("✓ test_author_weight_dominates_title 通过")


def test_empty_author_sim_low():
    author_sim = AuthorSimilarity.compute("余华", "")
    print(f"  余华 vs 空作者: {author_sim:.4f}")
    assert author_sim <= 0.3, f"空作者相似度必须<=0.3，实际: {author_sim}"

    overall = OverallBookSimilarity()
    overall_sim, scores = overall.compute(
        isbn1="", isbn2="",
        author1="余华", author2="",
        title1="活着", title2="活着",
        simhash1=0, simhash2=0, size1=1000, size2=1000,
        format1="epub", format2="epub"
    )
    print(f"  综合相似度(空作者): {overall_sim:.4f}, author_score={scores['author']:.4f}")
    assert overall_sim <= 0.30, f"空作者综合相似度必须<=0.30，实际: {overall_sim}"
    print("✓ test_empty_author_sim_low 通过")


def test_author_verifier_thresholds():
    verifier = AuthorVerifier()

    result = verifier.verify_duplicate_candidate(
        title1="活着", author1="余华",
        title2="活着", author2="余秋雨"
    )
    author_sim = AuthorSimilarity.compute("余华", "余秋雨")
    print(f"  余华 vs 余秋雨 作者相似度: {author_sim:.4f}")
    print(f"  验证结果: is_same_book={result.is_same_book}, overall={result.overall_confidence:.2f}")
    assert not result.is_same_book, "余华与余秋雨不能判定为同一作者"
    assert author_sim < 0.50, f"余华vs余秋雨作者相似度应<0.5，实际: {author_sim}"

    result2 = verifier.verify_duplicate_candidate(
        title1="平凡的世界", author1="路遥",
        title2="平凡的世界", author2="路遥远"
    )
    author_sim2 = AuthorSimilarity.compute("路遥", "路遥远")
    print(f"  路遥 vs 路遥远 作者相似度: {author_sim2:.4f}")
    print(f"  验证结果: is_same_book={result2.is_same_book}")
    assert not result2.is_same_book, "路遥与路遥远不能判定为同一作者"
    print("✓ test_author_verifier_thresholds 通过")


def test_detector_author_threshold_055():
    config = MatchConfig()
    detector = DuplicateDetector(config=config)

    authors = [
        ("余华", True),
        ("余华 著", True),
        ("余秋雨", False),
        ("余杰", False),
        ("余平", False),
        ("鲁迅", False),
        ("路遥", False),
    ]

    books = []
    for i, (author, should_match) in enumerate(authors):
        books.append(make_book(
            "活着", author, f"C:\\books\\活着_{i}.epub",
            size=1000000 + i * 10000, simhash=12345 if i == 0 else 0
        ))

    groups = detector.detect(books)
    print(f"  检测到 {len(groups)} 组重复:")
    matched_authors = set()
    for g in groups:
        authors_in_group = [b.author for b in g.books]
        matched_authors.update(authors_in_group)
        print(f"    - [{g.match_type}] {authors_in_group} 相似度={g.similarity:.2f}")

    expected_match = {"余华", "余华 著"}
    for author in expected_match:
        assert author in matched_authors, f"余华和余华 著应该被识别为同一作者"

    for author in ["余秋雨", "余杰", "余平", "鲁迅", "路遥"]:
        assert author not in matched_authors, f"{author}不应与余华混在同一组"

    for g in groups:
        authors_in_group = {b.author for b in g.books}
        if authors_in_group & {"余秋雨", "余杰", "余平", "鲁迅", "路遥"}:
            assert False, f"重复组中混入了不同作者: {authors_in_group}"
    print("✓ test_detector_author_threshold_055 通过")


def test_classic_mismatch_case():
    config = MatchConfig()
    detector = DuplicateDetector(config=config)

    books = [
        make_book("活着", "余华", "C:\\books\\活着_余华.epub", size=2000000, simhash=11111111),
        make_book("活着", "余秋雨", "C:\\books\\活着_余秋雨.epub", size=1900000, simhash=22222222),
        make_book("活着", "王小明", "C:\\books\\活着_王小明.epub", size=2100000, simhash=33333333),
        make_book("活着", "余华 著", "C:\\books\\活着_余华_著.epub", size=2050000, simhash=11111111),
        make_book("三体", "刘慈欣", "C:\\books\\三体.epub", size=3000000, simhash=44444444),
        make_book("三体 典藏版", "刘慈欣", "C:\\books\\三体_典藏.epub", size=3100000, simhash=44444444),
    ]

    groups = detector.detect(books)
    print(f"  检测到 {len(groups)} 组重复:")
    for g in groups:
        titles = ", ".join(f"{b.title}({b.author})" for b in g.books)
        print(f"    - [{g.match_type}] {titles} 相似度={g.similarity:.2f}")

    huozhe_groups = [g for g in groups if any("活着" in b.title for b in g.books)]
    assert len(huozhe_groups) >= 1, "至少应该识别出余华的两本《活着》"
    for g in huozhe_groups:
        authors_in_group = {b.author for b in g.books}
        for bad_author in ["余秋雨", "王小明"]:
            assert bad_author not in authors_in_group, f"《活着》组中混入了 {bad_author}，这是完全不同的作者"
        assert "余华" in authors_in_group, "余华应该在《活着》重复组中"

    santi_groups = [g for g in groups if any("三体" in b.title for b in g.books)]
    assert len(santi_groups) >= 1, "刘慈欣的两本《三体》应该被识别为重复"

    print("✓ test_classic_mismatch_case 通过")


def test_suspicious_surname_pair_not_matched():
    verifier = AuthorVerifier()

    test_cases = [
        ("余华", "余秋雨", False),
        ("余华", "余杰", False),
        ("鲁迅", "鲁", False),
        ("路遥", "路", False),
        ("路遥", "遥远", False),
        ("刘慈欣", "慈欣", False),
        ("刘慈欣", "刘欣", False),
        ("刘慈欣", "刘慈", False),
        ("钱钟书", "钟书", False),
        ("沈从文", "从文", False),
        ("张爱玲", "爱玲", False),
        ("路遥", "王卫国", True),
        ("鲁迅", "周树人", True),
        ("余华", "余华 著", True),
    ]

    all_pass = True
    for a1, a2, expected in test_cases:
        result = verifier.verify_duplicate_candidate(
            title1="测试书", author1=a1,
            title2="测试书", author2=a2
        )
        status = "✓" if result.is_same_book == expected else "✗"
        print(f"  {status} {a1:>6} vs {a2:<8} -> match={result.is_same_book} (期望{expected}), author_sim={result.author_confidence:.2f}")
        if result.is_same_book != expected:
            all_pass = False

    assert all_pass, "有作者对匹配结果不符合预期"
    print("✓ test_suspicious_surname_pair_not_matched 通过")


def run_all_tests():
    print("=" * 70)
    print("作者权重 0.6 + 阈值同步调高 - 专项验证测试")
    print("=" * 70)

    tests = [
        ("权重总和=1.0 且作者=0.60", test_weight_sum_is_one),
        ("作者权重主导，异作者惩罚>=50%", test_author_weight_dominates_title),
        ("空作者相似度<=0.3", test_empty_author_sim_low),
        ("AuthorVerifier 阈值(0.85/0.65/0.45)", test_author_verifier_thresholds),
        ("检测器 author_sim 阈值 0.55", test_detector_author_threshold_055),
        ("经典误判案例：活着余华 vs 余秋雨 vs 王小明", test_classic_mismatch_case),
        ("可疑姓氏组合 + 笔名验证", test_suspicious_surname_pair_not_matched),
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

    print("\n" + "=" * 70)
    print(f"测试结果: {passed}/{len(tests)} 通过")
    if failed:
        print(f"失败的测试:")
        for name, err in failed:
            print(f"  ✗ {name}: {err}")
        return False
    print("🎉 全部通过！")
    return True


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
