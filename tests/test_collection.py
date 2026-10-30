from pathlib import Path

from csp.collection import arrange, categories, category_label


def test_category_is_the_top_folder_below_the_common_root():
    root = Path("/x/examples")
    files = [root / "a.txt", root / "japanese-food" / "f.txt", root / "demo" / "sub" / "g.txt"]
    assert categories(files) == {files[0]: None, files[1]: "japanese-food", files[2]: "demo"}
    assert categories([root / "demo" / "one.txt"]) == {root / "demo" / "one.txt": None}


def test_category_label_reads_as_a_heading():
    assert category_label("japanese-food") == "Japanese food"
    assert category_label("wie-doet-het-met-wie") == "Wie doet het met wie"


def test_murdoku_first_demo_leading_then_families_with_natural_order():
    root = Path("/x/examples")
    kinds = {
        root / "sudoku_1_4x4.txt": "sudoku",
        root / "akari_1_6x6.txt": "akari",
        root / "zoo" / "t-12x12.txt": "murdoku",
        root / "zoo" / "t-6x6.txt": "murdoku",
        root / "demo" / "house.txt": "murdoku",
        root / "apple" / "a.txt": "murdoku",
    }
    listed = arrange(kinds)
    assert [item.path.name for item in listed] == [
        "house.txt", "a.txt", "t-6x6.txt", "t-12x12.txt", "akari_1_6x6.txt", "sudoku_1_4x4.txt"
    ]  # fmt: skip
    assert [item.number for item in listed] == [1, 2, 3, 4, 5, 6]
    assert listed[0].section == "Murdoku \u00b7 Demo"
    assert listed[4].section == "Akari"


def test_display_aliases_have_distinct_collection_sections():
    root = Path("/x/examples")
    paths = {
        root / "queens_1_4x4.txt": "queens",
        root / "queens_2_5x5.txt": "queens",
        root / "binairo_3_4x4.txt": "binairo",
        root / "tango_2_4x4.txt": "binairo",
    }
    names = {
        root / "queens_1_4x4.txt": "queens",
        root / "queens_2_5x5.txt": "queens",
        root / "binairo_3_4x4.txt": "binairo",
        root / "tango_2_4x4.txt": "tango",
    }
    sections = {item.path.name: item.section for item in arrange(paths, names)}
    assert sections == {
        "queens_1_4x4.txt": "Queens",
        "queens_2_5x5.txt": "Queens",
        "binairo_3_4x4.txt": "Binairo",
        "tango_2_4x4.txt": "Tango",
    }
