# meshy_mesh_plus_bones.py
#
# Creates a “Mesh + Big Green Bone Shapes” debug .blend (similar to your screenshot).
# - Imports a GLB
# - Finds the first armature
# - Keeps the mesh visible
# - Assigns a bright green pyramid-ish custom shape to EVERY bone (so bones are easy to see)
# - Saves a .blend (and optionally a rig_report.json)
#
# Recommended (UI run so the viewport can be framed nicely):
#   /Applications/Blender.app/Contents/MacOS/Blender --python "$(pwd)/meshy_mesh_plus_bones.py" -- \
#     --in "$(pwd)/Character_output.glb" \
#     --out-blend "$(pwd)/out/mesh_plus_bones.blend" \
#     --report "$(pwd)/out/rig_report.json"
#
# Headless also works (but viewport framing may not apply):
#   /Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --debug-python \
#     --python "$(pwd)/meshy_mesh_plus_bones.py" -- \
#     --in "$(pwd)/Character_output.glb" \
#     --out-blend "$(pwd)/out/mesh_plus_bones.blend"

import bpy
import sys
import os
import json
import math
import argparse
import addon_utils

print("SCRIPT_LOADED __name__ =", __name__)

# ----------------------------
# Args / IO
# ----------------------------

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True, help="Input .glb file path")
    p.add_argument("--out-blend", required=True, help="Output .blend file path")
    p.add_argument("--report", default="", help="Optional output rig_report.json path")
    p.add_argument("--shape-scale", type=float, default=0.25, help="Thickness of the green bone shapes")
    p.add_argument("--emission", type=float, default=3.0, help="Emission strength for green shapes")
    return p.parse_args(argv)

def save_blend(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)

def save_json(path: str, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ----------------------------
# Blender setup / import
# ----------------------------

def enable_gltf_importer():
    # Makes GLB import work even with --factory-startup.
    try:
        bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
    except Exception:
        addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

def import_glb(path: str):
    bpy.ops.import_scene.gltf(filepath=path)

def find_first_armature():
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            return obj
    return None

# ----------------------------
# Rig report (optional)
# ----------------------------

def rig_report(arm_obj):
    bones = arm_obj.data.bones
    return {
        "armature_object": arm_obj.name,
        "bone_count": len(bones),
        "bones": [
            {
                "name": b.name,
                "parent": b.parent.name if b.parent else None,
                "head_local": [b.head_local.x, b.head_local.y, b.head_local.z],
                "tail_local": [b.tail_local.x, b.tail_local.y, b.tail_local.z],
            }
            for b in bones
        ],
    }

# ----------------------------
# Custom-shape overlay (the “green wedges”)
# ----------------------------

def get_or_create_green_material(emission_strength: float):
    mat_name = "__BONE_GREEN__"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True

    # Configure nodes
    nt = mat.node_tree
    nodes = nt.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.2, 1.0, 0.2, 1.0)
        # Blender versions differ slightly in socket names, guard them:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (0.2, 1.0, 0.2, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = emission_strength

    return mat

def get_or_create_bone_shape(emission_strength: float):
    """
    Creates a pyramid-ish mesh object used as a custom bone shape.
    We move it far away so it doesn't clutter the scene as a standalone object.
    """
    shape_name = "__BONE_SHAPE_PYRAMID__"
    shape_obj = bpy.data.objects.get(shape_name)
    if shape_obj is not None:
        return shape_obj

    # Create a pyramid-like cone (4 vertices)
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.10, depth=1.0)
    shape_obj = bpy.context.active_object
    shape_obj.name = shape_name

    # Point along +Y (bones generally point +Y in pose space display)
    shape_obj.rotation_euler = (math.radians(90), 0, 0)

    # Bright green material
    mat = get_or_create_green_material(emission_strength)
    if shape_obj.data.materials:
        shape_obj.data.materials[0] = mat
    else:
        shape_obj.data.materials.append(mat)

    # Don’t render it; keep it “out of the way”
    shape_obj.hide_render = True
    shape_obj.hide_select = True
    shape_obj.location = (10000, 10000, 10000)

    return shape_obj

def apply_green_shapes_to_bones(arm_obj, shape_scale: float, emission_strength: float):
    shape_obj = get_or_create_bone_shape(emission_strength)

    # Ensure we have pose bones loaded
    if not getattr(arm_obj, "pose", None) or not arm_obj.pose.bones:
        bpy.context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        try:
            bpy.ops.object.mode_set(mode="POSE")
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass

    # Assign shape to each pose bone
    for pb in arm_obj.pose.bones:
        pb.custom_shape = shape_obj

        # Make it proportional: longer bone -> longer wedge
        L = max(pb.bone.length, 1e-4)
        pb.custom_shape_scale_xyz = (shape_scale, L, shape_scale)

    # Make armature draw on top of mesh
    arm_obj.show_in_front = True

    # If Blender tries to show “bounds sphere”, disable that
    if hasattr(arm_obj, "show_bounds"):
        arm_obj.show_bounds = False
    if hasattr(arm_obj, "display_type"):
        arm_obj.display_type = "SOLID"

# ----------------------------
# Viewport setup (UI-only)
# ----------------------------

def configure_viewport_ui(active_obj):
    """
    UI-only: set the first 3D View to something readable and frame the selection.
    Blender 5+ safe (uses context.temp_override).
    """
    wm = bpy.context.window_manager
    if not getattr(wm, "windows", None) or len(wm.windows) == 0:
        print("No UI windows (background mode) -> skipping viewport config")
        return

    # Make active/selected
    bpy.ops.object.select_all(action="DESELECT")
    active_obj.select_set(True)
    bpy.context.view_layer.objects.active = active_obj

    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue

            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if not region:
                continue

            space = area.spaces.active

            # View settings
            try:
                space.shading.type = "MATERIAL"  # mesh looks nicer; bones still visible
            except Exception:
                pass

            ov = space.overlay
            if hasattr(ov, "show_overlays"):
                ov.show_overlays = True
            if hasattr(ov, "show_relationship_lines"):
                ov.show_relationship_lines = False

            # Frame view
            try:
                with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
                    bpy.ops.view3d.view_selected()
                print("Viewport configured + framed.")
            except Exception as e:
                print("Viewport frame skipped:", e)

            return

# ----------------------------
# Main
# ----------------------------

def main():
    print("SCRIPT_START")
    args = parse_args()

    enable_gltf_importer()
    clear_scene()
    import_glb(args.in_path)

    arm = find_first_armature()
    if not arm:
        raise RuntimeError("No ARMATURE found in this file.")

    # IMPORTANT: We KEEP the mesh (no delete_everything_except).
    apply_green_shapes_to_bones(
        arm_obj=arm,
        shape_scale=args.shape_scale,
        emission_strength=args.emission,
    )

    # Optional JSON report
    if args.report:
        save_json(args.report, rig_report(arm))
        print("Wrote report:", args.report)

    # UI-only viewport help
    try:
        configure_viewport_ui(arm)
    except Exception as e:
        print("Viewport config failed (continuing):", e)

    save_blend(args.out_blend)
    print("Saved:", args.out_blend)
    print("Armature:", arm.name, "bones:", len(arm.data.bones))

# Call unconditionally (Blender sometimes doesn't behave like standard __main__)
main()