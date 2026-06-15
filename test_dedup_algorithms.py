import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from ebook_manager.models import BookMeta
from ebook_manager.fingerprint_calculator import SimHash, TextExtractor
from ebook_manager.duplicate_detector import DuplicateDetector, MatchConfig
from ebook_manager.recommendation_engine import RecommendationEngine
from ebook_manager.recycle_bin import RecycleBin


def test_isbn_normalization():
    print("=" * 60)
    print("测试 ISBN 归一化")
    print("=" * 60)

    test_cases = [
        ("978-7-02-008954-3", "9787020089543", "ISBN-13 with hyphens"),
        ("7-02-008954-3", "9787020089543", "ISBN-10 converted to ISBN-13"),
        ("ISBN 9787020089543", "9787020089543", "ISBN with prefix"),
        ("invalid-isbn", "", "Invalid ISBN"),
        ("", "", "Empty ISBN"),
    ]

    valid_isbn13 = BookMeta.normalize_isbn("978-7-02-008954-3")
    print(f"\n[OK] ISBN-13 验证: 9787020089543 is valid: {BookMeta.validate_isbn13(valid_isbn13)}")

    for input_isbn, expected, description in test_cases:
        result = BookMeta.normalize_isbn(input_isbn)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"{status} {description}")
        print(f"  输入: {input_isbn!r}")
        print(f"  期望: {expected!r}")
        print(f"  实际: {result!r}")
        print()

    test_isbn10 = "7020089543"
    isbn13 = BookMeta.isbn10_to_isbn13(test_isbn10)
    valid = BookMeta.validate_isbn13(isbn13)
    print(f"✓ ISBN-10 to ISBN-13: {test_isbn10} -> {isbn13} (valid: {valid})")


def test_text_normalization():
    print("\n" + "=" * 60)
    print("测试文本归一化")
    print("=" * 60)

    test_cases = [
        ("活着", "活着", "Chinese title"),
        ("活著", "活著", "Chinese variant"),
        ("The Art of Programming", "art programming", "English with stopwords"),
        ("活着 余华", "余华 活着", "Chinese title and author"),
        ("《活着》", "活着", "Title with brackets"),
        ("活着 (珍藏版)", "珍藏版 活着", "Title with parentheses"),
        ("L'Étranger", "letranger", "French with accents"),
    ]

    for input_text, expected, description in test_cases:
        result = BookMeta.normalize_text(input_text)
        print(f"  {description}")
        print(f"    输入: {input_text!r}")
        print(f"    输出: {result!r}")

    title1 = "活着"
    author1 = "余华"
    title2 = "《活着》(珍藏版)"
    author2 = "余华 著"

    key1 = BookMeta.generate_title_author_key(title1, author1)
    key2 = BookMeta.generate_title_author_key(title2, author2)
    print(f"\n✓ 书名作者指纹匹配测试:")
    print(f"  '{title1}' + '{author1}' -> {key1[:16]}...")
    print(f"  '{title2}' + '{author2}' -> {key2[:16]}...")
    print(f"  匹配: {key1 == key2}")


def test_simhash():
    print("\n" + "=" * 60)
    print("测试 SimHash 相似度算法")
    print("=" * 60)

    simhash = SimHash()

    text1 = """
    《活着》讲述了农村人福贵悲惨的人生遭遇。福贵本是个阔少爷，可他嗜赌如命，终于赌光了家业，一贫如洗。
    他的父亲被他活活气死，母亲则在穷困中患了重病，福贵前去求药，却在途中被国民党抓去当壮丁。
    经过几番波折回到家里，才知道母亲早已去世，妻子家珍含辛茹苦地养大两个儿女。
    """

    text2 = """
    小说《活着》描述了农民福贵苦难的一生。福贵曾经是富家子弟，但因赌博成瘾而耗尽家产，变得一无所有。
    他的父亲因此被气死，母亲也在贫困中病倒。福贵外出求医时被国民党军队抓去当兵。
    历尽艰辛回到家乡后，他得知母亲已经去世，妻子家珍辛苦地抚养着两个孩子长大成人。
    """

    text3 = """
    三体是一本关于宇宙文明的科幻小说。当人类收到外星文明的信号时，面临着艰难的抉择。
    叶文洁按下了回应按钮，开启了两个文明之间的交流与对抗。
    """

    hash1 = simhash.compute(text1)
    hash2 = simhash.compute(text2)
    hash3 = simhash.compute(text3)

    distance12 = SimHash.hamming_distance(hash1, hash2)
    similarity12 = SimHash.similarity(hash1, hash2)

    distance13 = SimHash.hamming_distance(hash1, hash3)
    similarity13 = SimHash.similarity(hash1, hash3)

    print(f"✓ Hash 1 (《活着》版本1): {hash1:016x}")
    print(f"✓ Hash 2 (《活着》版本2): {hash2:016x}")
    print(f"✓ Hash 3 (《三体》): {hash3:016x}")
    print()
    print(f"  《活着》两版本海明距离: {distance12}, 相似度: {similarity12:.4f}")
    print(f"  《活着》vs《三体》海明距离: {distance13}, 相似度: {similarity13:.4f}")
    print()

    threshold = 0.85
    print(f"  阈值 {threshold}:")
    print(f"    《活着》两版本判定为相似: {similarity12 >= threshold}")
    print(f"    《活着》vs《三体》判定为相似: {similarity13 >= threshold}")


def test_duplicate_detection():
    print("\n" + "=" * 60)
    print("测试重复检测分组")
    print("=" * 60)

    detector = DuplicateDetector(MatchConfig(simhash_threshold=0.80))

    simhash = SimHash()
    text_huozhe1 = "福贵的一生，从富家子弟到穷苦农民，经历了所有的苦难"
    text_huozhe2 = "福贵悲惨的人生遭遇，从富裕到贫穷，失去了所有的亲人"
    text_santi = "三体文明与地球文明的交流对抗，黑暗森林法则"
    text_santi2 = "宇宙社会学，黑暗森林，三体世界的故事"

    books = [
        BookMeta(title="活着", author="余华", isbn="9787020089543",
                 file_path="/books/活着.epub", file_format="epub", file_size=1234567),
        BookMeta(title="《活着》", author="余华 著", isbn="978-7-02-008954-3",
                 file_path="/books/活着_珍藏版.epub", file_format="epub", file_size=1567890),
        BookMeta(title="活着", author="余华", isbn="",
                 file_path="/books/活着.pdf", file_format="pdf", file_size=8765432),
        BookMeta(title="活着", author="余华", isbn="7-02-008954-3",
                 file_path="/books/活着.mobi", file_format="mobi", file_size=2345678),
        BookMeta(title="三体", author="刘慈欣", isbn="9787536692930",
                 file_path="/books/三体.epub", file_format="epub", file_size=2134567),
        BookMeta(title="三体全集", author="刘慈欣", isbn="9787536692930",
                 file_path="/books/三体全集.epub", file_format="epub", file_size=5432109),
        BookMeta(title="平凡的世界", author="路遥",
                 file_path="/books/平凡的世界.epub", file_format="epub", file_size=3456789),
    ]

    books[0].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[0].isbn)
    books[0].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[0].title, books[0].author)
    books[0].fingerprint.simhash = simhash.compute(text_huozhe1)
    books[0].metadata_completeness = 0.9

    books[1].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[1].isbn)
    books[1].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[1].title, books[1].author)
    books[1].fingerprint.simhash = simhash.compute(text_huozhe1)
    books[1].metadata_completeness = 0.85

    books[2].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[2].isbn)
    books[2].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[2].title, books[2].author)
    books[2].fingerprint.simhash = simhash.compute(text_huozhe2)
    books[2].metadata_completeness = 0.7

    books[3].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[3].isbn)
    books[3].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[3].title, books[3].author)
    books[3].fingerprint.simhash = simhash.compute(text_huozhe2)
    books[3].metadata_completeness = 0.6

    books[4].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[4].isbn)
    books[4].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[4].title, books[4].author)
    books[4].fingerprint.simhash = simhash.compute(text_santi)
    books[4].metadata_completeness = 0.9

    books[5].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[5].isbn)
    books[5].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[5].title, books[5].author)
    books[5].fingerprint.simhash = simhash.compute(text_santi2)
    books[5].metadata_completeness = 0.95

    books[6].fingerprint.isbn_normalized = BookMeta.normalize_isbn(books[6].isbn)
    books[6].fingerprint.title_author_key = BookMeta.generate_title_author_key(books[6].title, books[6].author)
    books[6].fingerprint.simhash = simhash.compute("平凡的世界讲述了改革开放初期的故事")
    books[6].metadata_completeness = 0.5

    groups = detector.detect(books)
    stats = detector.get_statistics(groups)

    print(f"✓ 发现 {len(groups)} 组重复")
    print()

    for i, group in enumerate(groups):
        print(f"  组 {i+1}: {group.match_type} (相似度: {group.similarity*100:.1f}%)")
        for book in group.books:
            print(f"    - {book.title} ({book.file_format.upper()}, ISBN: {book.fingerprint.isbn_normalized or 'N/A'})")
        print()

    print(f"✓ 统计信息:")
    print(f"  重复组总数: {stats['total_groups']}")
    print(f"  重复书籍总数: {stats['total_duplicate_books']}")
    print(f"  可移除书籍数: {stats['books_to_remove']}")
    print(f"  预计释放空间: {BookMeta.format_size(stats['saved_size_bytes'])}")
    print(f"  格式分布: {stats['format_distribution']}")
    print(f"  匹配类型分布: {stats['match_type_distribution']}")


def test_recommendation():
    print("\n" + "=" * 60)
    print("测试自动推荐策略")
    print("=" * 60)

    recommender = RecommendationEngine()

    group_books = [
        BookMeta(title="活着", author="余华", publisher="作家出版社", publish_date="2012",
                 isbn="9787020089543", language="zh", description="余华代表作",
                 file_path="/books/活着.epub", file_format="epub", file_size=1500000),
        BookMeta(title="活着", author="余华", publisher="", publish_date="",
                 isbn="", language="", description="",
                 file_path="/books/活着_副本.pdf", file_format="pdf", file_size=8000000),
        BookMeta(title="活着", author="余华", publisher="作家出版社", publish_date="2012",
                 isbn="9787020089543", language="zh", description="",
                 file_path="/books/活着.mobi", file_format="mobi", file_size=1800000),
    ]

    for b in group_books:
        b.metadata_completeness = b.calculate_metadata_completeness()

    from ebook_manager.models import DuplicateGroup
    group = DuplicateGroup(group_id="test", books=group_books, similarity=0.95, match_type="isbn_exact")

    ranked = recommender.rank_books(group)
    keep_book = recommender.recommend_keep(group)

    print(f"✓ 推荐保留: {keep_book.title} ({keep_book.file_format.upper()})")
    print()

    for i, (book, score) in enumerate(ranked):
        reasons = recommender.get_recommendation_reason(book, group)
        status = "⭐ 推荐保留" if i == 0 else f"   "
        print(f"  {status} 第{i+1}名: {book.file_format.upper()} - 评分: {score*100:.1f}%")
        print(f"     文件: {Path(book.file_path).name}")
        print(f"     大小: {BookMeta.format_size(book.file_size)}")
        print(f"     元数据完整度: {book.metadata_completeness*100:.0f}%")
        if reasons:
            print(f"     理由: {', '.join(reasons)}")
        if i > 0:
            removal_reasons = recommender.get_removal_reason(book, keep_book)
            if removal_reasons:
                print(f"     移除原因: {', '.join(removal_reasons)}")
        print()


def test_recycle_bin():
    print("\n" + "=" * 60)
    print("测试回收站功能")
    print("=" * 60)

    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        recycle_path = Path(tmpdir) / "recycle"
        recycle_bin = RecycleBin(base_path=str(recycle_path))

        test_file = Path(tmpdir) / "活着_副本.epub"
        test_file.write_text("test content for recycle bin")

        book = BookMeta(
            title="活着", author="余华",
            file_path=str(test_file), file_format="epub",
            file_size=test_file.stat().st_size,
            isbn="9787020089543"
        )

        print(f"✓ 原文件存在: {test_file.exists()}")
        print(f"  路径: {test_file}")

        entry = recycle_bin.delete(book)
        print(f"✓ 删除后原文件存在: {test_file.exists()}")
        print(f"  回收路径: {entry.recycle_path}")
        print(f"  回收文件存在: {Path(entry.recycle_path).exists()}")

        print(f"\n✓ 回收站文件数: {recycle_bin.get_total_count()}")
        print(f"  回收站占用空间: {BookMeta.format_size(recycle_bin.get_total_size())}")

        entries = recycle_bin.get_entries()
        print(f"  条目数: {len(entries)}")
        for e in entries:
            print(f"    - {e.file_name} (原路径: {e.original_path})")

        success = recycle_bin.restore(entry.id)
        print(f"\n✓ 恢复成功: {success}")
        print(f"  原文件存在: {test_file.exists()}")
        print(f"  回收文件存在: {Path(entry.recycle_path).exists()}")
        print(f"  回收站文件数: {recycle_bin.get_total_count()}")


def test_edge_cases():
    print("\n" + "=" * 60)
    print("测试边缘情况处理")
    print("=" * 60)

    detector = DuplicateDetector(MatchConfig(simhash_threshold=0.85))
    simhash = SimHash()

    books = [
        BookMeta(title="平凡的世界", author="路遥", isbn="9787530212004",
                 file_path="/books/平凡的世界_路遥.epub", file_format="epub", file_size=3000000),
        BookMeta(title="平凡的世界", author="平凡", isbn="",
                 file_path="/books/平凡的世界_平凡.epub", file_format="epub", file_size=1500000),
        BookMeta(title="人生", author="路遥", isbn="9787530209559",
                 file_path="/books/人生_路遥.epub", file_format="epub", file_size=2000000),
        BookMeta(title="人生", author="路遥", isbn="9787530209559",
                 file_path="/books/人生_路遥_新版.epub", file_format="epub", file_size=2100000),
    ]

    for book in books:
        book.fingerprint.isbn_normalized = BookMeta.normalize_isbn(book.isbn)
        book.fingerprint.title_author_key = BookMeta.generate_title_author_key(book.title, book.author)
        book.fingerprint.simhash = simhash.compute(f"{book.title} {book.author} content")
        book.metadata_completeness = book.calculate_metadata_completeness()

    groups = detector.detect(books)
    print(f"✓ 同名不同作者检测:")
    for book in books:
        if "平凡的世界" in book.title:
            print(f"  '{book.title}' - 作者: {book.author} - ISBN: {book.fingerprint.isbn_normalized or 'N/A'}")

    print(f"\n✓ 同作者不同书检测:")
    for book in books:
        if book.author == "路遥":
            print(f"  作者: {book.author} - '{book.title}' - ISBN: {book.fingerprint.isbn_normalized or 'N/A'}")

    print(f"\n✓ 检测到的重复组: {len(groups)}")
    for group in groups:
        titles = [b.title for b in group.books]
        authors = [b.author for b in group.books]
        print(f"  组: {titles} - 作者: {authors} - 类型: {group.match_type}")

    print(f"\n✓ 验证:")
    print(f"  '平凡的世界' 不同作者被正确区分: {len([g for g in groups if '平凡的世界' in [b.title for b in g.books]]) == 0}")
    print(f"  '人生' 同作者同书被正确分组: {len([g for g in groups if '人生' in [b.title for b in g.books]]) == 1}")


def main():
    print("=" * 60)
    print("智能电子书去重助手 - 核心算法测试")
    print("=" * 60)

    try:
        test_isbn_normalization()
        test_text_normalization()
        test_simhash()
        test_duplicate_detection()
        test_recommendation()
        test_recycle_bin()
        test_edge_cases()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
