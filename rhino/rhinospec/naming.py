# -*- coding: utf-8 -*-
"""Layer tree for built parts: rhinospec::<spec layer>::<object>::<category>[::<sub>].

Planned parts carry a category key ("cat", e.g. "windows/glass"); hand-written primitives can
name a sublayer with "group". Category names come in English or Italian; colours belong to the
layer, so recolouring or assigning a material to one layer changes every element in it.
Pure Python: tested outside Rhino.
"""

LANGS = ("en", "it")

# key -> (English, Italian, layer colour)
CATEGORIES = {
    "walls": ("Walls", "Muri", "#e8e2d6"),
    "windows": ("Windows", "Finestre", "#f4f4f2"),
    "windows/frames": ("Frames", "Telai", "#f4f4f2"),
    "windows/glass": ("Glass", "Vetri", "#8fb3cf"),
    "windows/bars": ("Bars", "Traversi", "#f4f4f2"),
    "windows/surrounds": ("Surrounds", "Mostre", "#e3dac8"),
    "doors": ("Doors", "Porte", "#6b4a2f"),
    "doors/frames": ("Frames", "Telai", "#f4f4f2"),
    "doors/leaves": ("Leaves", "Ante", "#6b4a2f"),
    "doors/glass": ("Glass", "Vetri", "#8fb3cf"),
    "doors/bars": ("Bars", "Traversi", "#f4f4f2"),
    "doors/surrounds": ("Surrounds", "Mostre", "#e3dac8"),
    "shopfronts": ("Shopfronts", "Vetrine", "#8fb3cf"),
    "shopfronts/frames": ("Frames", "Telai", "#f4f4f2"),
    "shopfronts/glass": ("Glass", "Vetri", "#8fb3cf"),
    "shopfronts/bars": ("Bars", "Traversi", "#f4f4f2"),
    "shopfronts/signs": ("Signs", "Insegne", "#f4f4f2"),
    "cornices": ("Cornices", "Cornici", "#d6cdbb"),
    "mouldings": ("Mouldings", "Modanature", "#ddd5c4"),
    "sills": ("Sills", "Davanzali", "#cfc6b4"),
    "pillars": ("Pillars", "Colonne", "#dcd3c1"),
    "balconies": ("Balconies", "Balconi", "#d6cdbb"),
    "balconies/railings": ("Railings", "Ringhiere", "#3e3e3e"),
    "balconies/glass": ("Glass", "Vetri", "#c9d6de"),
    "rustication": ("Rustication", "Bugnato", "#d9cfbd"),
    "quoins": ("Quoins", "Cantonali", "#d3c9b5"),
    "spandrels": ("Spandrels", "Pannelli marcapiano", "#3b4048"),
    "pediments": ("Pediments", "Timpani", "#d6cdbb"),
    "arcades": ("Arcades", "Portici", "#e1dacb"),
    "roof/dormers": ("Dormers", "Abbaini", "#8a4b3a"),
    "roof/dormers/glass": ("Glass", "Vetri", "#8fb3cf"),
    "roof/chimneys": ("Chimneys", "Comignoli", "#9a7a66"),
    "shutters": ("Shutters", "Persiane", "#4f6b52"),
    "ornaments": ("Ornaments", "Decorazioni", "#cbbfa6"),
    "floors": ("Floors", "Solai", "#bdb6a8"),
    "stairs": ("Stairs", "Scale", "#cfc6b4"),
    "stairs/steps": ("Steps", "Gradini", "#cfc6b4"),
    "stairs/railings": ("Railings", "Ringhiere", "#3e3e3e"),
    "roof": ("Roof", "Tetto", "#8a4b3a"),
}

# Facade element class -> category of its main part.
ELEMENT_CATEGORY = {
    "window": "windows", "door": "doors", "shop": "shopfronts", "cornice": "cornices",
    "molding": "mouldings", "sill": "sills", "pillar": "pillars", "balcony": "balconies",
    "blind": "shutters", "deco": "ornaments", "rustic": "rustication", "quoin": "quoins",
    "spandrel": "spandrels", "pediment": "pediments", "arcade": "arcades",
}


def category_path(cat, lang="en"):
    """'windows/glass' -> ['Windows', 'Glass'] (or the Italian names)."""
    i = LANGS.index(lang)
    out, key = [], ""
    for piece in cat.split("/"):
        key = piece if not key else key + "/" + piece
        out.append(CATEGORIES[key][i])
    return out


# Sides of a block, as seen from outside: key -> (English, Italian)
FACE_NAMES = {"front": ("Front", "Fronte"), "right": ("Right", "Destra"),
              "back": ("Back", "Retro"), "left": ("Left", "Sinistra")}


def layer_path(spec_layer, part, lang="en"):
    """Layer segments under the root for one part: [spec layer, object, (face,) category...]."""
    segs = [spec_layer]
    if part.get("obj"):
        segs.append(part["obj"])
    if part.get("face") in FACE_NAMES:
        segs.append(FACE_NAMES[part["face"]][LANGS.index(lang)])
    if part.get("cat"):
        segs.extend(category_path(part["cat"], lang))
    elif part.get("group"):
        segs.append(part["group"])
    return segs


def layer_color(part):
    """Colour for the deepest layer of a part, or None for user groups."""
    if part.get("cat"):
        return CATEGORIES[part["cat"]][2]
    return None
