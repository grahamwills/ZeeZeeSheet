from sheet.common import Rect


def test_modify_horizontal():
    rect = Rect(left=5, right=95, top=7, bottom=777)
    assert rect.modify_horizontal(left=10, right=20) == Rect(left=10, right=20, top=7, bottom=777)
    assert rect.modify_horizontal(left=10, width=50) == Rect(left=10, right=60, top=7, bottom=777)
    assert rect.modify_horizontal(right=10, width=50) == Rect(left=-40, right=10, top=7, bottom=777)
