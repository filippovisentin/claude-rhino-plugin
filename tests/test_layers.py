"""Layer tree: every planned part gets a meaningful category layer (pure Python)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import SpecError, validate  # noqa: E402
from rhinospec.naming import CATEGORIES, category_path, layer_color, layer_path  # noqa: E402

FACADE = {"type": "facade", "name": "Fronte", "w": 12, "h": 10, "depth": 9, "floors": 3, "roof": "gable", "els": [
    {"k": "window", "box": [1, 4, 1.2, 2], "bars": [1, 1]},
    {"k": "window", "box": [4, 4, 1.2, 2], "shape": "arch", "bars": [1, 0]},
    {"k": "door", "box": [5, 0, 2, 3], "shape": "arch"},
    {"k": "door", "box": [9, 0.5, 1, 2.2]},
    {"k": "shop", "box": [1, 0.5, 3, 2.5]},
    {"k": "cornice", "box": [0.8, 6.1, 1.6, 0.5], "shape": "tri"},
    {"k": "molding", "box": [0, 9.4, 12, 0.6], "d": 0.6},
    {"k": "sill", "box": [0.9, 3.85, 1.4, 0.15]},
    {"k": "pillar", "box": [4.6, 0, 0.3, 3]},
    {"k": "balcony", "box": [7, 4, 3, 1.1]},
    {"k": "blind", "box": [0.5, 4, 0.5, 2]},
    {"k": "deco", "box": [5.5, 3.2, 1, 0.6]}]}


def planned(lang="en"):
    return validate({"units": "m", "layer": "Palazzo", "lang": lang, "parts": [FACADE]})["parts"]


class Categories(unittest.TestCase):
    def test_every_planned_part_has_a_known_category(self):
        for p in planned():
            self.assertEqual(p["obj"], "Fronte")
            self.assertIn(p["cat"], CATEGORIES, p["name"])

    def test_expected_layers_appear(self):
        paths = set("::".join(layer_path("Palazzo", p)) for p in planned())
        for want in ("Palazzo::Fronte::Walls", "Palazzo::Fronte::Windows::Frames", "Palazzo::Fronte::Windows::Glass",
                     "Palazzo::Fronte::Windows::Bars", "Palazzo::Fronte::Doors::Leaves", "Palazzo::Fronte::Doors::Frames",
                     "Palazzo::Fronte::Shopfronts::Glass", "Palazzo::Fronte::Cornices", "Palazzo::Fronte::Mouldings",
                     "Palazzo::Fronte::Sills", "Palazzo::Fronte::Pillars", "Palazzo::Fronte::Balconies",
                     "Palazzo::Fronte::Shutters", "Palazzo::Fronte::Ornaments", "Palazzo::Fronte::Floors",
                     "Palazzo::Fronte::Roof"):
            self.assertIn(want, paths)

    def test_italian_names(self):
        self.assertEqual(category_path("windows/glass", "it"), ["Finestre", "Vetri"])
        paths = set("::".join(layer_path("Palazzo", p, "it")) for p in planned("it"))
        self.assertIn("Palazzo::Fronte::Muri", paths)
        self.assertIn("Palazzo::Fronte::Finestre::Telai", paths)
        self.assertIn("Palazzo::Fronte::Tetto", paths)

    def test_colours_move_to_layers(self):
        parts = planned()
        self.assertTrue(all("color" not in p for p in parts))
        self.assertEqual(layer_color({"cat": "windows/glass"}), "#8fb3cf")
        coloured = validate({"parts": [dict(FACADE, color="#aa3311")]})["parts"]
        walls = [p for p in coloured if p["cat"] == "walls"]
        self.assertTrue(walls and all(p["color"] == "#aa3311" for p in walls))

    def test_building_parts(self):
        parts = validate({"parts": [{"type": "building", "name": "Casa", "footprint": [[0, 0], [8, 0], [8, 6], [0, 6]],
                                     "floors": 2, "roof": "gable"}]})["parts"]
        self.assertEqual(set(p["cat"] for p in parts), {"floors", "walls", "roof"})
        self.assertTrue(all(p["obj"] == "Casa" for p in parts))

    def test_hand_written_groups(self):
        parts = validate({"layer": "Tavolo", "parts": [
            {"type": "box", "size": [1, 1, 0.04], "group": "Piano"},
            {"type": "array", "group": "Gambe", "of": {"type": "box", "size": [0.05, 0.05, 0.7]}, "n": [2, 2, 1], "step": [0.9, 0.9, 0]},
            {"type": "box", "size": [1, 1, 1], "cat": "windows/glass", "obj": "Vetrina"}]})["parts"]
        self.assertEqual(layer_path("Tavolo", parts[0]), ["Tavolo", "Piano"])
        self.assertEqual(layer_path("Tavolo", parts[1]), ["Tavolo", "Gambe"])
        self.assertEqual(layer_path("Tavolo", parts[-1]), ["Tavolo", "Vetrina", "Windows", "Glass"])

    def test_bad_names_are_rejected(self):
        for part, msg in (({"type": "box", "size": [1, 1, 1], "group": "a::b"}, ".group"),
                          ({"type": "box", "size": [1, 1, 1], "cat": "secret"}, ".cat"),
                          ({"type": "box", "size": [1, 1, 1], "obj": "x" * 65}, ".obj")):
            with self.assertRaises(SpecError) as cm:
                validate({"parts": [part]})
            self.assertIn(msg, str(cm.exception))
        with self.assertRaises(SpecError):
            validate({"lang": "fr", "parts": [{"type": "sphere", "r": 1}]})


if __name__ == "__main__":
    unittest.main()
