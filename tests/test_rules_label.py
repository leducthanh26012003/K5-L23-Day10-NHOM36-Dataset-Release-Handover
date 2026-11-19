"""Kiểm 5 luật của TV2 bằng lỗi TỰ CÀI (có đáp án thật, không đụng _private).

  py -m unittest tests.test_rules_label -v

Chép runs/clean/delivery sang thư mục tạm, cài mỗi lỗi vào một ảnh với mức KHÓ hơn lô luyện tập
(tràn mép chỉ 0.003, box chép lệch 1 pixel, area thừa 50 pixel), rồi kiểm validator bắt đúng
những ảnh đó, không hơn không kém. Thêm một ca "gần giống nhưng khác kích thước" không được báo.
Cần tạo lô sạch trước: py scripts/inject_release.py --seed 5 --no-faults --out runs/clean
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "runs" / "clean" / "delivery"
sys.path.insert(0, str(ROOT / "validator"))

import rules_label  # noqa: E402
from common import load_delivery  # noqa: E402


def _rows(path: Path) -> list[list[str]]:
    return [ln.split() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _inner(rows: list[list[str]], W: int, H: int, margin: int = 10) -> list[str]:
    """Box cách mép ảnh ít nhất `margin` pixel: chép/nới nó không vô tình tạo thêm lỗi tràn mép."""
    for r in rows:
        x, y, w, h = map(float, r[1:5])
        if min(x - w / 2, 1 - x - w / 2) * W >= margin and min(y - h / 2, 1 - y - h / 2) * H >= margin:
            return r
    raise unittest.SkipTest("không có box cách mép đủ xa")


def _write(path: Path, rows: list[list[str]]) -> None:
    path.write_text("".join(" ".join(r) + "\n" for r in rows), encoding="utf-8")


@unittest.skipUnless(CLEAN.is_dir(), "chưa có runs/clean")
class TestRulesLabel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        d = cls.tmp / "delivery"
        shutil.copytree(CLEAN, d)
        ctx = load_delivery(d)
        names = [n for n in sorted(ctx["manifest"]) if len(_rows(d / "labels" / f"{n}.txt")) >= 2 and ctx["segments"].get(n)]
        def has_inner(n):
            try:
                _inner(_rows(d / "labels" / f"{n}.txt"), *ctx["size"][n])
                return True
            except unittest.SkipTest:
                return False
        c, g = [n for n in names if has_inner(n)][:2]   # ca chép box cần box nằm xa mép
        a, b, e, f = [n for n in names if n not in (c, g)][:4]
        cls.expect = {}

        # invalid_class: đổi lớp một box thành 80 (lệch một so với giới hạn 0..79)
        rows = _rows(d / "labels" / f"{a}.txt")
        rows[0][0] = "80"
        _write(d / "labels" / f"{a}.txt", rows)
        cls.expect[("invalid_class", a)] = True

        # bbox_out_of_bounds: kéo cạnh phải ra 1.003 (chỉ tràn 0.3%, nhỏ hơn lô luyện tập)
        rows = _rows(d / "labels" / f"{b}.txt")
        x, w = float(rows[0][1]), float(rows[0][3])
        left, right = x - w / 2, 1.003
        rows[0][1], rows[0][3] = f"{(left + right) / 2:.6f}", f"{right - left:.6f}"
        _write(d / "labels" / f"{b}.txt", rows)
        cls.expect[("bbox_out_of_bounds", b)] = True

        # duplicate_box: chép một box, dời tâm 1 pixel, giữ nguyên w h
        W, H = ctx["size"][c]
        rows = _rows(d / "labels" / f"{c}.txt")
        dup = list(_inner(rows, W, H))
        dup[1] = f"{float(dup[1]) + 1 / W:.6f}"
        _write(d / "labels" / f"{c}.txt", rows + [dup])
        cls.expect[("duplicate_box", c)] = True

        # KHÔNG phải lỗi: box gần trùng nhưng to hơn 4 pixel (giống cặp box tự nhiên của COCO)
        W, H = ctx["size"][g]
        rows = _rows(d / "labels" / f"{g}.txt")
        near = list(_inner(rows, W, H))
        near[1] = f"{float(near[1]) + 1 / W:.6f}"
        near[3] = f"{float(near[3]) + 4 / W:.6f}"
        near[4] = f"{float(near[4]) + 4 / H:.6f}"
        _write(d / "labels" / f"{g}.txt", rows + [near])
        cls.not_error = g

        pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
        anns = {Path(x["file_name"]).stem: x for x in pan["annotations"]}
        valid = {cat["id"] for cat in pan["categories"]}

        # invalid_category_id: dùng một id nằm trong KHOẢNG TRỐNG của danh sách lớp COCO
        gap = next(i for i in range(1, max(valid)) if i not in valid)
        anns[e]["segments_info"][0]["category_id"] = gap
        cls.expect[("invalid_category_id", e)] = True

        # thing_overlap: area khai thừa 50 pixel so với mask
        anns[f]["segments_info"][0]["area"] += 50
        cls.expect[("thing_overlap", f)] = True
        (d / "panoptic.json").write_text(json.dumps(pan), encoding="utf-8")

        cls.found = {(x["type"], x["target"]) for x in rules_label.run(load_delivery(d))}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_bat_du_loi_tu_cai(self):
        self.assertEqual(set(self.expect) - self.found, set(), "bỏ sót lỗi tự cài")

    def test_khong_bao_thua(self):
        self.assertEqual(self.found - set(self.expect), set(), "báo lỗi ở ảnh không cài lỗi")

    def test_cap_gan_trung_khac_kich_thuoc_khong_bi_bao(self):
        self.assertNotIn(("duplicate_box", self.not_error), self.found)


if __name__ == "__main__":
    unittest.main()
