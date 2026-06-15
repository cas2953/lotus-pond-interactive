# -*- coding: utf-8 -*-
"""
荷花池互動展項 — Blender 俯視精靈圖批次渲染
============================================================
把錦鯉(FBX)與睡蓮(OBJ)從「正上方正交相機」渲染成帶透明背景的 PNG,
並輸出 assets/sprites/manifest.json 供 index.html 自動載入。
  · 錦鯉：俯視(看背部) + bend 擺尾游動循環，輸出連續幀 koiXX_00.png ...
  · 睡蓮：強制指定 diffuse 並依材質拆成「花 / 葉」各自輸出
相容 Blender 3.x / 4.x / 5.x。

使用方式（命令列，不需開 Blender 介面）：
  & "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" --background --python "tools\\render_assets.py"
============================================================
"""

import bpy
import os
import sys
import math
import json

try:
    import mathutils
except Exception:
    mathutils = None

# ============================================================
#  CONFIG  ── 路徑與參數
# ============================================================
PROJECT = r"C:/Users/陳宏錡/Desktop/Project for Claude Code/P452  pool interactive"
OUT_DIR = os.path.join(PROJECT, "assets", "sprites")

RES          = 1024     # 每張精靈圖邊長（像素）
FISH_FRAMES  = 32       # 魚游動循環的幀數（越多越順）
FISH_BEND    = 28.0     # 擺尾幅度（度，越大擺動越明顯）
FISH_MARGIN  = 1.5      # 魚四周預留（需與 index.html FISH_IMG_SCALE 一致）
PLANT_MARGIN = 1.10
SUN_ENERGY   = 4.0
WORLD_LIGHT  = 0.6

DL = r"C:/Users/陳宏錡/Downloads"
MODELS = [
    # flip=頭尾反向(繞Z 180°)；belly_flip=看到肚子時翻面(繞X 180°)
    {"name": "koi01", "kind": "fish", "flip": True, "belly_flip": False,
     "path": DL + r"/kohaku-koi-carp-2026-02-10-21-49-27-utc/[FBX] Koi01/Koi01.FBX"},
    {"name": "koi02", "kind": "fish", "flip": True, "belly_flip": False,
     "path": DL + r"/koi-carp-red-white-and-black-pattern-2026-02-10-21-52-31-utc/[FBX] koi02/koi02.FBX"},
    {"name": "lily",  "kind": "plant",
     "path": DL + r"/pink-water-lily-with-floating-pads-2026-02-06-04-38-20-utc/[OBJ] Water_Lily_03_002_Natural_Group/Water_Lily_03_002_Natural_Group.obj"},
    {"name": "lotus", "kind": "lotus",
     "path": PROJECT + r"/model/_extracted/water-lily-with-yellow-center-2026-02-08-22-51-26-utc/21 Lotus.glb"},
]

FLOWER_KEYS = ["bloom", "flower", "floret", "petal", "blossom", "pink"]
LEAF_KEYS   = ["leaf", "pad"]
STEM_KEYS   = ["stem"]

IMG_EXT = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp")


# ============================================================
#  小工具
# ============================================================
def log(*a):
    print("[render_assets]", *a)


def ensure_object_mode():
    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass


def clear_scene():
    ensure_object_mode()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for col in (bpy.data.cameras, bpy.data.lights):
        for d in list(col):
            if d.users == 0:
                col.remove(d)


def rel(path):
    return os.path.relpath(path, PROJECT).replace("\\", "/")


def import_model(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    else:
        raise RuntimeError("不支援的格式: " + ext)
    new = [o for o in bpy.data.objects if o not in before]
    return [o for o in new if o.type == 'MESH']


def world_bbox(objs):
    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    for o in objs:
        for corner in o.bound_box:
            wc = o.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    return mins, maxs


def find_texture(folders, keywords, exclude=None):
    """依關鍵字「優先序」挑貼圖，並跳過遮罩/法線/粗糙度等非顏色圖。"""
    if exclude is None:
        exclude = ["mask", "normal", "_norm", "bump", "rough", "metal", "gloss",
                   "spec", "_ao", "ao_", "occlusion", "grunge", "venis", "_map",
                   "map_", "map ", "variation", "_end", "sss", "ior", "opacity",
                   "reflection", "_flat"]
    files = []
    for folder in folders:
        if folder and os.path.isdir(folder):
            for fn in sorted(os.listdir(folder)):
                if fn.lower().endswith(IMG_EXT):
                    files.append(os.path.join(folder, fn))
    for k in keywords:                       # 優先序：先找非遮罩的
        for f in files:
            low = os.path.basename(f).lower()
            if k in low and not any(x in low for x in exclude):
                return f
    for k in keywords:                       # 最後手段：允許被排除者
        for f in files:
            if k in os.path.basename(f).lower():
                return f
    return None


def get_principled(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out is None:
            out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs[0], out.inputs[0])
    return nt, bsdf


def set_base_color_tex(mat, tex_path, force=False):
    """把指定貼圖接到材質的 Base Color。force=True 會覆蓋既有連線。"""
    nt, bsdf = get_principled(mat)
    base_in = bsdf.inputs.get("Base Color")
    if base_in is None:
        return
    if base_in.is_linked and not force:
        return
    for l in list(base_in.links):
        nt.links.remove(l)
    img = bpy.data.images.load(tex_path, check_existing=True)
    texnode = nt.nodes.new("ShaderNodeTexImage")
    texnode.image = img
    nt.links.new(texnode.outputs["Color"], base_in)
    if bsdf.inputs.get("Roughness"):
        bsdf.inputs["Roughness"].default_value = 0.7
    if bsdf.inputs.get("Metallic"):
        bsdf.inputs["Metallic"].default_value = 0.0


def ensure_base_color(obj, model_path):
    """魚用：若 Base Color 沒貼圖，從模型資料夾與 ../Extras 找 diffuse 接上。"""
    base_dir = os.path.dirname(model_path)
    folders = [base_dir, os.path.join(os.path.dirname(base_dir), "Extras"),
               os.path.dirname(os.path.dirname(base_dir))]
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue
        nt, bsdf = get_principled(mat)
        base_in = bsdf.inputs.get("Base Color")
        if base_in is None or base_in.is_linked:
            continue
        name = (mat.name + " " + obj.name).lower()
        kw = ["basecolor", "base_color", "diffuse", "albedo"]
        tex = find_texture(folders, kw)
        if tex:
            set_base_color_tex(mat, tex)


def setup_world_light():
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    try:
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[1].default_value = WORLD_LIGHT
    except Exception:
        pass
    light_data = bpy.data.lights.new("Sun", type='SUN')
    light_data.energy = SUN_ENERGY
    light = bpy.data.objects.new("Sun", light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = (math.radians(20), math.radians(10), 0)


def setup_render():
    scene = bpy.context.scene
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    scene.render.film_transparent = True
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'


def setup_camera(center_xy, size, top_z):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(size, 0.001)
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (center_xy[0], center_xy[1], top_z + max(size, 5.0))
    cam.rotation_euler = (0, 0, 0)
    cam_data.clip_start = 0.001
    cam_data.clip_end = (abs(top_z) + size) * 8 + 1000
    bpy.context.scene.camera = cam
    return cam


def render_to(filepath):
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)


# ============================================================
#  魚：重新定向成「俯視看背部」→ bend 擺尾 → 連續幀
# ============================================================
def reorient_fish(obj):
    """把魚轉成：最長軸(體長)→X、最短軸(左右寬)→Y、中間軸(背腹高)→Z(朝相機)。
       這樣俯視(沿 -Z)看到的就是魚背，而非側面。"""
    mins, maxs = world_bbox([obj])
    dims = [maxs[i] - mins[i] for i in range(3)]
    order = sorted(range(3), key=lambda i: dims[i])   # [最短, 中間, 最長]
    smallest, mid, largest = order[0], order[1], order[2]
    rows = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    rows[0][largest] = 1.0     # X <- 體長
    rows[1][smallest] = 1.0    # Y <- 左右寬
    rows[2][mid] = 1.0         # Z <- 背腹高（朝相機）
    R = mathutils.Matrix(rows)
    if R.determinant() < 0:
        rows[1][smallest] = -1.0
        R = mathutils.Matrix(rows)
    obj.matrix_world = R.to_4x4() @ obj.matrix_world


def process_fish(model):
    clear_scene()
    setup_world_light()
    meshes = import_model(model["path"])
    if not meshes:
        log("!! 無法匯入或無網格:", model["path"])
        return []
    for m in meshes:
        ensure_base_color(m, model["path"])

    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    fish = bpy.context.view_layer.objects.active

    reorient_fish(fish)
    if model.get("belly_flip"):
        fish.matrix_world = mathutils.Matrix.Rotation(math.pi, 4, 'X') @ fish.matrix_world
    if model.get("flip"):
        fish.matrix_world = mathutils.Matrix.Rotation(math.pi, 4, 'Z') @ fish.matrix_world
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action='DESELECT')
    fish.select_set(True)
    bpy.context.view_layer.objects.active = fish
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

    mod = fish.modifiers.new("Swim", type='SIMPLE_DEFORM')
    mod.deform_method = 'BEND'
    mod.deform_axis = 'Z'      # 俯視看不到擺動時改 'X' 或 'Y'

    mins, maxs = world_bbox([fish])
    cx = (mins[0] + maxs[0]) / 2.0
    cy = (mins[1] + maxs[1]) / 2.0
    size = max(maxs[0] - mins[0], maxs[1] - mins[1]) * FISH_MARGIN
    setup_camera((cx, cy), size, maxs[2])
    setup_render()

    frames = []
    for f in range(FISH_FRAMES):
        mod.angle = math.radians(FISH_BEND * math.sin(2 * math.pi * f / FISH_FRAMES))
        out = os.path.join(OUT_DIR, "%s_%02d.png" % (model["name"], f))
        render_to(out)
        frames.append(rel(out))
    log("魚完成:", model["name"], "共", len(frames), "幀")
    return frames


# ============================================================
#  睡蓮：強制指定 diffuse → 依材質拆「花 / 葉」→ 各自輸出
# ============================================================
def make_solid_material(name, rgb):
    """全新乾淨材質：Principled + 純色，避開壞掉的原始材質節點。（rgb 為 linear）"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    if bsdf.inputs.get("Roughness"):
        bsdf.inputs["Roughness"].default_value = 0.6
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return mat


def recalc_normals(objs):
    if not objs:
        return
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        log("recalc_normals 失敗:", e)


def separate_by_material(meshes):
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    active = None
    for m in meshes:
        if m and m.name in bpy.data.objects:
            m.select_set(True)
            active = m
    if active is None:
        return [o for o in bpy.data.objects if o.type == 'MESH']
    bpy.context.view_layer.objects.active = active
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='MATERIAL')
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        log("separate_by_material 失敗:", e)
    return [o for o in bpy.data.objects if o.type == 'MESH']


def keep_large_parts(objs, frac=0.12):
    """把這些物件依 loose 拆開，只留 XY 投影面積較大的部分（去掉夾在葉裡的小花托）。"""
    if not objs:
        return []
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    active = None
    for o in objs:
        if o.name in bpy.data.objects:
            o.select_set(True); active = o
    if active is None:
        return objs
    bpy.context.view_layer.objects.active = active
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        log("keep_large_parts loose 失敗:", e)
    parts = [o for o in bpy.data.objects if o.type == 'MESH' and o.select_get()]
    if not parts:
        return objs
    areas = []
    for o in parts:
        areas.append(sum(p.area for p in o.data.polygons))   # 實際表面積
    if not areas:
        return parts
    # 只保留表面積最大的一片乾淨浮葉（花托/小塊都比它小，全部移除）
    best = areas.index(max(areas))
    keep = [parts[best]]
    drop = [o for i, o in enumerate(parts) if i != best]
    for o in drop:
        bpy.data.objects.remove(o, do_unlink=True)
    log("keep_large_parts: 保留 1 大片浮葉 / 移除 %d" % len(drop))
    return keep


def used_material_name(obj):
    me = obj.data
    if me.polygons:
        idx = me.polygons[0].material_index
        if idx < len(obj.material_slots) and obj.material_slots[idx].material:
            return obj.material_slots[idx].material.name
    for s in obj.material_slots:
        if s.material:
            return s.material.name
    return obj.name


def classify_plant(obj):
    n = (obj.name + " " + used_material_name(obj)).lower()
    if any(k in n for k in FLOWER_KEYS):
        return "flower"
    if any(k in n for k in STEM_KEYS):
        return "stem"
    if any(k in n for k in LEAF_KEYS):
        return "leaf"
    return "other"


def process_plant(model):
    clear_scene()
    setup_world_light()
    meshes = import_model(model["path"])
    if not meshes:
        log("!! 無法匯入或無網格:", model["path"])
        return {"flowers": [], "leaves": []}

    parts = separate_by_material(meshes)
    flower_mat = make_solid_material("LilyFlower", (0.90, 0.20, 0.38))
    leaf_mat = make_solid_material("LilyLeaf", (0.16, 0.42, 0.10))

    groups = {"flower": [], "leaf": [], "stem": []}
    log("---- 睡蓮物件清單（依材質拆分後） ----")
    for m in parts:
        cls = classify_plant(m)
        if cls == "other":
            cls = "leaf"          # 非花非莖 → 視為葉
        groups[cls].append(m)
        log("  %-30s -> %-7s  原材質:[%s]" % (m.name, cls, used_material_name(m)))

    # 葉群常夾著睡蓮花托(小塊)，依 loose 拆開只留大片浮葉，去掉那朵被當成葉的小花
    groups["leaf"] = keep_large_parts(groups["leaf"])

    for m in groups["flower"]:
        m.data.materials.clear(); m.data.materials.append(flower_mat)
    for m in groups["leaf"]:
        m.data.materials.clear(); m.data.materials.append(leaf_mat)
    recalc_normals(groups["flower"] + groups["leaf"])
    log("  分類統計: 花 %d / 葉(大片) %d / 莖 %d"
        % (len(groups["flower"]), len(groups["leaf"]), len(groups["stem"])))

    setup_render()
    out = {"flowers": [], "leaves": []}

    def render_group(objs, fname):
        if not objs:
            return None
        all_meshes = [o for o in bpy.data.objects if o.type == 'MESH']
        for m in all_meshes:
            m.hide_render = True
        for o in objs:
            o.hide_render = False
        mins, maxs = world_bbox(objs)
        cx = (mins[0] + maxs[0]) / 2.0
        cy = (mins[1] + maxs[1]) / 2.0
        size = max(maxs[0] - mins[0], maxs[1] - mins[1]) * PLANT_MARGIN
        setup_camera((cx, cy), size, maxs[2])
        path = os.path.join(OUT_DIR, fname)
        render_to(path)
        return rel(path)

    f = render_group(groups["flower"], "lily_flower.png")
    if f:
        out["flowers"].append(f)
    l = render_group(groups["leaf"], "lily_leaf.png")
    if l:
        out["leaves"].append(l)
    if not out["flowers"] and not out["leaves"]:
        whole = render_group(parts, "lily_full.png")
        if whole:
            out["flowers"].append(whole)
    log("睡蓮完成: 花", len(out["flowers"]), "/ 葉", len(out["leaves"]))
    return out


# ============================================================
#  荷花（單朵 glb，多顏色 × 俯視/傾斜兩角度）
# ============================================================
def set_mat_base_color(mat, rgb):
    nt, bsdf = get_principled(mat)
    base = bsdf.inputs.get("Base Color")
    if base is None:
        return
    for l in list(base.links):
        nt.links.remove(l)
    base.default_value = (rgb[0], rgb[1], rgb[2], 1.0)


# ---- 多角度打光（讓荷花有立體層次，不再單調） ----
def make_sun(name):
    d = bpy.data.lights.new(name, type='SUN')
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    return o


def set_world_strength(v):
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    try:
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[1].default_value = v
    except Exception:
        pass


# 三組打光：暖側光 / 冷側光 / 柔正光 —— 每朵花會分別用不同組打光，產生立體變化
LOTUS_LIGHTS = [
    {"key_rot": (30, -24, 0), "key_e": 5.2, "key_col": (1.00, 0.95, 0.86),
     "fill_rot": (40, 42, 0),  "fill_e": 1.6, "fill_col": (0.78, 0.90, 1.00), "world": 0.50},
    {"key_rot": (18, 34, 0),  "key_e": 4.4, "key_col": (1.00, 0.90, 0.78),
     "fill_rot": (44, -34, 0), "fill_e": 1.5, "fill_col": (0.84, 0.92, 1.00), "world": 0.60},
    {"key_rot": (10, 2, 0),   "key_e": 3.8, "key_col": (1.00, 0.98, 0.93),
     "fill_rot": (32, 168, 0), "fill_e": 2.2, "fill_col": (0.92, 0.96, 1.00), "world": 0.80},
]


def apply_light(key, fill, preset):
    key.data.energy = preset["key_e"]
    key.data.color = preset["key_col"]
    key.rotation_euler = tuple(math.radians(a) for a in preset["key_rot"])
    fill.data.energy = preset["fill_e"]
    fill.data.color = preset["fill_col"]
    fill.rotation_euler = tuple(math.radians(a) for a in preset["fill_rot"])
    set_world_strength(preset["world"])


def render_lotus_view(center, size, tilt_deg, azim, fname):
    """以「接近正上方」的小傾角渲染：tilt_deg=0 為正式俯視；3~5 度為稍微傾角。"""
    cam = bpy.data.cameras.new("C")
    cam.type = 'ORTHO'
    cam.ortho_scale = size * (1.0 + tilt_deg * 0.012)   # 傾角越大略放大避免裁切
    cam.clip_start = 0.001
    cam.clip_end = size * 40 + 1000
    co = bpy.data.objects.new("C", cam)
    bpy.context.scene.collection.objects.link(co)
    C = mathutils.Vector(center)
    th = math.radians(tilt_deg)
    dist = size + 1.0
    dirx = math.sin(azim) * math.sin(th)
    diry = -math.cos(azim) * math.sin(th)
    co.location = (center[0] + dirx * dist, center[1] + diry * dist, center[2] + math.cos(th) * dist)
    d = C - co.location
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = co
    path = os.path.join(OUT_DIR, fname)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(co, do_unlink=True)
    return rel(path)


LOTUS_COLORS = [
    ("pink", None),                        # 保留原始(最美)
    ("white", (0.93, 0.93, 0.96)),
    ("gold", (0.95, 0.74, 0.24)),
    ("lavender", (0.74, 0.60, 0.92)),
    ("purple", (0.60, 0.32, 0.80)),
]


def dump_lotus_structure(meshes):
    """印出荷花模型結構：物件 / 材質 / ShapeKeys / 頂點群組 / 骨架 —— 供「花苞開合動畫」評估。"""
    log("==== 荷花模型結構（供花苞開合動畫評估）====")
    for o in meshes:
        sk = o.data.shape_keys
        skn = [k.name for k in sk.key_blocks] if sk else []
        vg = [g.name for g in o.vertex_groups]
        mats = [s.material.name for s in o.material_slots if s.material]
        log("  物件:%-22s 頂點:%-6d 材質:%s ShapeKeys:%s 頂點群組:%s"
            % (o.name, len(o.data.vertices), mats, skn, vg))
    arm = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    log("  骨架(Armature):", [a.name for a in arm])
    log("===========================================")


def process_lotus(model):
    clear_scene()
    key = make_sun("KeySun")
    fill = make_sun("FillSun")
    bpy.ops.import_scene.gltf(filepath=model["path"])
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        log("!! 荷花匯入失敗:", model["path"])
        return []
    dump_lotus_structure(meshes)
    # 隱藏綠葉，只渲花(Pink/Yellow)
    bloom, pink_mats = [], []
    for o in meshes:
        mats = [s.material for s in o.material_slots if s.material]
        names = " ".join(m.name.lower() for m in mats)
        if "green" in names:
            o.hide_render = True
        else:
            bloom.append(o)
            for m in mats:
                if "pink" in m.name.lower() and m not in pink_mats:
                    pink_mats.append(m)
    if not bloom:
        bloom = meshes
    mn, mx = world_bbox(bloom)
    center = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2)
    size = max(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]) * 1.12
    setup_render()
    out = []
    n = len(LOTUS_COLORS)
    for ci, (cname, rgb) in enumerate(LOTUS_COLORS):
        if rgb is not None:
            for m in pink_mats:
                set_mat_base_color(m, rgb)
        base_az = ci * (2 * math.pi / n)
        # 正式正上方(0°，柔正光) ＋ 稍微傾角 4°/5°（暖側光 / 冷側光，不同方位避免每朵同向）
        apply_light(key, fill, LOTUS_LIGHTS[2])
        out.append(render_lotus_view(center, size, 0.0, 0.0, "lotus_%s_top.png" % cname))
        apply_light(key, fill, LOTUS_LIGHTS[0])
        out.append(render_lotus_view(center, size, 4.0, base_az, "lotus_%s_tiltA.png" % cname))
        apply_light(key, fill, LOTUS_LIGHTS[1])
        out.append(render_lotus_view(center, size, 5.0, base_az + 2.1, "lotus_%s_tiltB.png" % cname))
        log("荷花完成:", cname, "(0°/4°/5°)")
    return [p for p in out if p]


# ============================================================
#  主流程
# ============================================================
def parse_only():
    """命令列 `-- --only lotus` → 只重渲某類(lotus/fish/plant)，其餘沿用既有 manifest。"""
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if "--only" in rest:
            i = rest.index("--only")
            if i + 1 < len(rest):
                return rest[i + 1]
    return None


def load_manifest():
    p = os.path.join(OUT_DIR, "manifest.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            pass
    return {"flowers": [], "leaves": [], "fish": {}}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if mathutils is None:
        log("!! 找不到 mathutils,請確認以 Blender 內建 Python 執行。")
        return
    only = parse_only()
    manifest = load_manifest() if only else {"flowers": [], "leaves": [], "fish": {}}
    manifest.setdefault("flowers", [])
    manifest.setdefault("leaves", [])
    manifest.setdefault("fish", {})
    if only:
        log("== 只重渲:", only, "（其餘類別沿用既有 manifest）==")
    for model in MODELS:
        if only and model["kind"] != only:
            continue
        if not os.path.isfile(model["path"]):
            log("!! 找不到檔案,略過:", model["path"])
            continue
        if model["kind"] == "fish":
            frames = process_fish(model)
            if frames:
                manifest["fish"][model["name"]] = {"frames": frames}
        elif model["kind"] == "lotus":
            manifest["flowers"] = process_lotus(model)      # 花用荷花模型（多打光×多角度）
        else:
            res = process_plant(model)
            manifest["leaves"] = res["leaves"]              # 睡蓮只取浮葉

    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)
    log("=== 全部完成 ===")
    log("manifest:", json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
