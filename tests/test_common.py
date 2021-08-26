from sheet.common import Rect


def test_modify_horizontal():
    rect = Rect.make(left=5, right=95, top=7, bottom=777)
    assert rect.make_column(left=10, right=20) == Rect.make(left=10, right=20, top=7, bottom=777)
    assert rect.make_column(left=10, width=50) == Rect.make(left=10, right=60, top=7, bottom=777)
    assert rect.make_column(right=10, width=50) == Rect.make(left=-40, right=10, top=7, bottom=777)
