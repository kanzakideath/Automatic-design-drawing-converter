# -*- coding: utf-8 -*-
"""Runtime access to Minecraft asset directories.

The app first looks for an optional assets tree bundled under the app's data
directory, then falls back to an explicitly configured or locally installed
Minecraft assets tree.  Public builds should not redistribute third-party
textures unless the pack license allows it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from PIL import Image


CONFIG_FILE = "minecraft_assets_path.txt"
DEFAULT_LOCAL_ROOT: Path | None = None

_ROOT_CACHE: Path | None = None
_JSON_CACHE: dict[Path, dict | list | None] = {}
_MODEL_CACHE: dict[str, dict] = {}
_TEXTURE_CACHE: dict[tuple[str, bool], Image.Image | None] = {}
_LANG_CACHE: dict[str, dict] = {}

GRASS_TINT = (108, 163, 64)
FOLIAGE_TINT = (76, 135, 58)
WATER_TINT = (65, 118, 214)


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "data"
    return Path(__file__).resolve().parent / "data"


def _valid_root(path: Path | str | None) -> Path | None:
    if not path:
        return None
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = (_app_dir() / p).resolve()
        else:
            p = p.resolve()
        if (p / "textures" / "block").is_dir() and (p / "models" / "block").is_dir():
            return p
    except Exception:
        return None
    return None


def _config_roots():
    env = os.environ.get("SCHEMATIC_CONVERTER_MINECRAFT_ASSETS") or os.environ.get("MINECRAFT_ASSETS_ROOT")
    if env:
        yield env
    for base in (_app_dir(), _app_dir() / "data", _data_dir()):
        path = base / CONFIG_FILE
        try:
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    yield line
        except OSError:
            pass
    if DEFAULT_LOCAL_ROOT is not None:
        yield str(DEFAULT_LOCAL_ROOT)


def _embedded_roots():
    bases = []
    for base in (_data_dir(), _app_dir() / "data", _app_dir()):
        try:
            p = base.resolve()
        except Exception:
            p = base
        if p not in bases:
            bases.append(p)
    rels = (
        Path("minecraft_assets") / "minecraft",
        Path("minecraft_assets"),
        Path("embedded_minecraft_assets") / "minecraft",
        Path("embedded_minecraft_assets"),
        Path("assets") / "minecraft",
    )
    for base in bases:
        for rel in rels:
            yield base / rel


def _auto_roots():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    versions = Path(appdata) / ".minecraft" / "versions"
    try:
        candidates = list(versions.glob("*/*/assets/minecraft"))
    except OSError:
        candidates = []
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        yield str(p)


def assets_root() -> Path | None:
    global _ROOT_CACHE
    if _ROOT_CACHE is not None:
        return _ROOT_CACHE
    for candidate in list(_embedded_roots()) + list(_config_roots()) + list(_auto_roots() or []):
        root = _valid_root(candidate)
        if root:
            _ROOT_CACHE = root
            return root
    return None


def available() -> bool:
    return assets_root() is not None


def root_label() -> str:
    root = assets_root()
    return str(root) if root else ""


def _read_json(path: Path):
    if path in _JSON_CACHE:
        return _JSON_CACHE[path]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = None
    _JSON_CACHE[path] = data
    return data


def _normalize_ref(ref: str, kind: str) -> str:
    ref = str(ref or "").strip()
    if ref.startswith("minecraft:"):
        ref = ref.split(":", 1)[1]
    elif ":" in ref:
        namespace, rest = ref.split(":", 1)
        if namespace != "minecraft":
            return ""
        ref = rest
    if "/" not in ref:
        ref = kind + "/" + ref
    return ref


def _blockstate_model(base: str) -> str:
    root = assets_root()
    if not root:
        return "block/" + base
    data = _read_json(root / "blockstates" / (base + ".json"))
    if not isinstance(data, dict):
        return "block/" + base
    variants = data.get("variants")
    if isinstance(variants, dict) and variants:
        for key in ("", "axis=y", "facing=north", "facing=south"):
            if key in variants:
                entry = variants[key]
                if isinstance(entry, list):
                    entry = entry[0] if entry else {}
                if isinstance(entry, dict) and entry.get("model"):
                    return _normalize_ref(entry.get("model"), "block")
        first_key = sorted(variants.keys())[0]
        entry = variants[first_key]
        if isinstance(entry, list):
            entry = entry[0] if entry else {}
        if isinstance(entry, dict) and entry.get("model"):
            return _normalize_ref(entry.get("model"), "block")
    multipart = data.get("multipart")
    if isinstance(multipart, list):
        for part in multipart:
            apply = part.get("apply") if isinstance(part, dict) else None
            if isinstance(apply, list):
                apply = apply[0] if apply else {}
            if isinstance(apply, dict) and apply.get("model"):
                return _normalize_ref(apply.get("model"), "block")
    return "block/" + base


def _model_json(model_ref: str):
    root = assets_root()
    if not root:
        return None
    ref = _normalize_ref(model_ref, "block")
    if not ref:
        return None
    return _read_json(root / "models" / (ref + ".json"))


def _merged_model(model_ref: str, depth: int = 0) -> dict:
    ref = _normalize_ref(model_ref, "block")
    if not ref or depth > 12:
        return {"textures": {}, "face_textures": {}}
    cache_key = ref
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    data = _model_json(ref)
    if not isinstance(data, dict):
        result = {"textures": {}, "face_textures": {}}
        _MODEL_CACHE[cache_key] = result
        return result
    parent = data.get("parent")
    result = _merged_model(parent, depth + 1) if parent else {"textures": {}, "face_textures": {}}
    textures = dict(result.get("textures", {}))
    textures.update(data.get("textures") or {})
    face_textures = dict(result.get("face_textures", {}))
    for element in data.get("elements") or []:
        faces = element.get("faces") if isinstance(element, dict) else None
        if not isinstance(faces, dict):
            continue
        for face_name, face_data in faces.items():
            if isinstance(face_data, dict) and face_data.get("texture"):
                face_textures[face_name] = face_data.get("texture")
    result = {"textures": textures, "face_textures": face_textures}
    _MODEL_CACHE[cache_key] = result
    return result


def _resolve_texture_ref(ref: str, textures: dict, depth: int = 0) -> str:
    ref = str(ref or "")
    if depth > 8:
        return ""
    if ref.startswith("#"):
        key = ref[1:]
        return _resolve_texture_ref(textures.get(key, ""), textures, depth + 1)
    return _normalize_ref(ref, "block")


def _texture_file(texture_ref: str) -> Path | None:
    root = assets_root()
    if not root:
        return None
    ref = _normalize_ref(texture_ref, "block")
    if not ref:
        return None
    path = root / "textures" / (ref + ".png")
    return path if path.is_file() else None


def _load_texture(texture_ref: str) -> Image.Image | None:
    path = _texture_file(texture_ref)
    if not path:
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    if im.width != 16 or im.height != 16:
        im = im.resize((16, 16), Image.Resampling.NEAREST)
    return im


def _load_texture_raw(texture_ref: str) -> Image.Image | None:
    path = _texture_file(texture_ref)
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _tint_texture(im: Image.Image, tint: tuple[int, int, int], divisor: int = 170) -> Image.Image:
    src = im.convert("RGBA")
    out = Image.new("RGBA", src.size)
    sp = src.load()
    op = out.load()
    tr, tg, tb = tint
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = sp[x, y]
            op[x, y] = (
                min(255, int(r * tr / divisor)),
                min(255, int(g * tg / divisor)),
                min(255, int(b * tb / divisor)),
                a,
            )
    return out


def _special_block_texture(base: str, top: bool, face: str | None = None) -> Image.Image | None:
    if base == "grass_block":
        if face == "down":
            return _load_texture("block/dirt")
        if top or face == "up":
            tex = _load_texture("block/grass_block_top")
            return _tint_texture(tex, GRASS_TINT) if tex is not None else None
        side = _load_texture("block/grass_block_side")
        overlay = _load_texture("block/grass_block_side_overlay")
        if side is not None and overlay is not None:
            side = side.copy()
            side.alpha_composite(_tint_texture(overlay, GRASS_TINT))
            return side
        return side
    if base.endswith("_leaves") or base in {"vine", "short_grass", "fern", "large_fern"}:
        tex = _load_texture("block/" + base)
        return _tint_texture(tex, FOLIAGE_TINT) if tex is not None else None
    if base == "water":
        tex = _load_texture("block/water_still")
        return _tint_texture(tex, WATER_TINT, divisor=210) if tex is not None else None
    face_key = "top" if top or face == "up" else ("bottom" if face == "down" else "side")
    directional = {
        "barrel": {"top": "block/barrel_top", "bottom": "block/barrel_bottom", "side": "block/barrel_side"},
        "crafting_table": {"top": "block/crafting_table_top", "bottom": "block/oak_planks",
                           "side": "block/crafting_table_side", "north": "block/crafting_table_front",
                           "south": "block/crafting_table_front"},
        "furnace": {"top": "block/furnace_top", "bottom": "block/furnace_top", "side": "block/furnace_side",
                    "north": "block/furnace_front", "south": "block/furnace_front"},
        "blast_furnace": {"top": "block/blast_furnace_top", "bottom": "block/blast_furnace_top",
                          "side": "block/blast_furnace_side", "north": "block/blast_furnace_front",
                          "south": "block/blast_furnace_front"},
        "smoker": {"top": "block/smoker_top", "bottom": "block/smoker_bottom", "side": "block/smoker_side",
                   "north": "block/smoker_front", "south": "block/smoker_front"},
        "observer": {"top": "block/observer_top", "bottom": "block/observer_top", "side": "block/observer_side",
                     "north": "block/observer_front", "south": "block/observer_back"},
        "hopper": {"top": "block/hopper_top", "bottom": "block/hopper_outside", "side": "block/hopper_outside"},
        "scaffolding": {"top": "block/scaffolding_top", "bottom": "block/scaffolding_bottom",
                        "side": "block/scaffolding_side"},
        "piston": {"top": "block/piston_top", "bottom": "block/piston_bottom", "side": "block/piston_side"},
        "sticky_piston": {"top": "block/piston_top_sticky", "bottom": "block/piston_bottom",
                          "side": "block/piston_side"},
    }
    face_name = str(face or "").lower()
    if base in directional:
        entry = directional[base]
        tex = _load_texture(entry.get(face_name) or entry.get(face_key) or entry.get("side"))
        if tex is not None:
            return tex
    if base == "chest" or base == "trapped_chest":
        # Chest uses an entity atlas rather than a normal block model.  Crop a
        # readable patch so previews do not fall back to generic planks.
        tex = _load_texture_raw("entity/chest/trapped" if base == "trapped_chest" else "entity/chest/normal")
        if tex is not None:
            box = (16, 16, 32, 32) if face_key == "side" else (16, 0, 32, 16)
            return tex.crop(box).resize((16, 16), Image.Resampling.NEAREST)
    if base == "ender_chest":
        tex = _load_texture_raw("entity/chest/ender")
        if tex is not None:
            box = (16, 16, 32, 32) if face_key == "side" else (16, 0, 32, 16)
            return tex.crop(box).resize((16, 16), Image.Resampling.NEAREST)
    if base.endswith("_shulker_box") or base == "shulker_box":
        tex = _load_texture("block/" + base)
        if tex is not None:
            return tex
    return None


def get_block_texture(bid: str, top: bool = False, face: str | None = None) -> Image.Image | None:
    base = str(bid or "")
    if base.startswith("minecraft:"):
        base = base.split(":", 1)[1]
    face = str(face or ("up" if top else "")).lower()
    key = (base, bool(top), face)
    if key in _TEXTURE_CACHE:
        cached = _TEXTURE_CACHE[key]
        return cached.copy() if cached is not None else None
    special = _special_block_texture(base, bool(top), face=face or None)
    if special is not None:
        _TEXTURE_CACHE[key] = special.copy()
        return special
    model = _merged_model(_blockstate_model(base))
    textures = model.get("textures", {})
    face_textures = model.get("face_textures", {})
    face_candidates = {
        "up": ["up", "top", "end", "all", "particle", "side", "pane", "texture"],
        "down": ["down", "bottom", "end", "all", "particle", "side", "pane", "texture"],
        "north": ["north", "side", "all", "pane", "texture", "particle", "end", "top"],
        "south": ["south", "side", "all", "pane", "texture", "particle", "end", "top"],
        "east": ["east", "side", "all", "pane", "texture", "particle", "end", "top"],
        "west": ["west", "side", "all", "pane", "texture", "particle", "end", "top"],
    }
    if face in face_candidates:
        candidates = face_candidates[face]
    elif top:
        candidates = face_candidates["up"]
    else:
        candidates = ["north", "south", "east", "west", "side", "all", "pane", "texture", "particle", "end", "top"]
    refs = []
    for name in candidates:
        if name in face_textures:
            refs.append(face_textures[name])
        if name in textures:
            refs.append("#" + name)
    refs.extend([
        "block/%s_top" % base if top else "block/%s_side" % base,
        "block/%s_end" % base if top else "block/%s" % base,
        "block/%s" % base,
    ])
    texture = None
    for ref in refs:
        resolved = _resolve_texture_ref(ref, textures)
        texture = _load_texture(resolved)
        if texture is not None:
            break
    _TEXTURE_CACHE[key] = texture.copy() if texture is not None else None
    return texture


def lang_name(bid: str, locale: str = "ja_jp") -> str | None:
    root = assets_root()
    if not root:
        return None
    locale = locale.lower()
    if locale not in _LANG_CACHE:
        data = _read_json(root / "lang" / (locale + ".json"))
        _LANG_CACHE[locale] = data if isinstance(data, dict) else {}
    base = str(bid or "")
    if base.startswith("minecraft:"):
        base = base.split(":", 1)[1]
    return _LANG_CACHE[locale].get("block.minecraft." + base)
