# meshy_inspect.py
#
# Usage (UI run, recommended for saving a nice skeleton-only .blend with viewport set):
#   /Applications/Blender.app/Contents/MacOS/Blender --python "$(pwd)/meshy_inspect.py" -- \
#     --in "$(pwd)/Character_output.glb" \
#     --out-blend "$(pwd)/out/skeleton_only.blend" \
#     --report "$(pwd)/out/rig_report.json"
#
# Usage (headless run, writes report + .blend, but viewport config may not “stick”):
#   /Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --debug-python \
#     --python "$(pwd)/meshy_inspect.py" -- \
#     --in "$(pwd)/Character_output.glb" \
#     --out-blend "$(pwd)/out/skeleton_only.blend" \
#     --report "$(pwd)/out/rig_report.json"

import bpy
import sys
import os
import argparse
import addon_utils
import json
from itertools import groupby

print("MESHY_INSPECT_LOADED __name__ =", __name__)

# ----------------------------
# Setup / IO
# ----------------------------

def enable_gltf_importer():
    """Ensure the glTF importer exists even when running with --factory-startup."""
    try:
        bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
    except Exception:
        addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def import_glb(path: str):
    bpy.ops.import_scene.gltf(filepath=path)

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

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True, help="Input .glb file path")
    p.add_argument("--out-blend", required=True, help="Output .blend file path")
    p.add_argument("--report", default="", help="Optional: output rig_report.json path")
    return p.parse_args(argv)

# ----------------------------
# Armature helpers
# ----------------------------

def find_first_armature():
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE':
            return obj
    return None

def delete_everything_except(obj_to_keep):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in list(bpy.context.scene.objects):
        if obj != obj_to_keep:
            obj.select_set(True)
    bpy.ops.object.delete()

def force_all_bones_visible(arm_obj):
    # Unhide bones
    for b in arm_obj.data.bones:
        b.hide = False

    # Blender 4/5 Bone Collections can hide everything
    arm_data = arm_obj.data
    if hasattr(arm_data, "collections_all"):
        cols = list(arm_data.collections_all)
    elif hasattr(arm_data, "collections"):
        cols = list(arm_data.collections)
    else:
        cols = []

    for c in cols:
        if hasattr(c, "is_visible"):
            c.is_visible = True
        if hasattr(c, "is_solo"):
            c.is_solo = False

def clear_custom_shapes(arm_obj):
    # Clear custom shapes (often spheres/controllers)
    if not getattr(arm_obj, "pose", None):
        return
    for pb in arm_obj.pose.bones:
        pb.custom_shape = None

def configure_armature_draw(arm_obj):
    # ----- OBJECT-LEVEL draw (can cause the "bounds sphere" look) -----
    if hasattr(arm_obj, "show_bounds"):
        arm_obj.show_bounds = False
    if hasattr(arm_obj, "display_bounds_type"):
        arm_obj.display_bounds_type = 'BOX'
    if hasattr(arm_obj, "display_type"):
        arm_obj.display_type = 'WIRE'  # avoid BOUNDS

    # ----- ARMATURE/BONE draw -----
    arm_obj.show_in_front = True

    # Set bone display type - STICK is simplest and most readable
    # Valid options: 'OCTAHEDRAL', 'STICK', 'BBONE', 'ENVELOPE', 'WIRE'
    arm_data = arm_obj.data
    if hasattr(arm_data, "display_type"):
        try:
            arm_data.display_type = 'STICK'
        except Exception as e:
            print(f"Could not set display_type to STICK: {e}")

    # Disable envelope display (the circles you see)
    if hasattr(arm_data, "show_bone_envelopes"):
        arm_data.show_bone_envelopes = False

    # Blender 5.0 might use different attribute names
    if hasattr(arm_data, "display_bone_envelopes"):
        arm_data.display_bone_envelopes = False

    # Debug prints
    print("ARMATURE OBJECT display_type:", getattr(arm_obj, "display_type", None))
    print("ARMATURE OBJECT show_bounds:", getattr(arm_obj, "show_bounds", None))
    print("ARMATURE DATA display_type:", getattr(arm_data, "display_type", None))
    print("ARMATURE DATA show_bone_envelopes:", getattr(arm_data, "show_bone_envelopes", None))

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
# Viewport config (UI runs only)
# ----------------------------

def configure_first_viewport_to_show_bones(active_obj):
    """
    UI-only: make the first 3D viewport readable for rigs.
    Uses Blender 3.2+ / 5.0 temp_override API.
    Gracefully skips if running in background mode with no UI.
    """
    # Check if we're in background mode
    if bpy.app.background:
        print("Background mode detected -> skipping viewport framing (overlay settings still applied to data)")
        # We can still set armature data properties that persist in the .blend
        try:
            active_obj.data.display_type = 'STICK'
        except Exception:
            pass
        return

    wm = bpy.context.window_manager
    if not getattr(wm, "windows", None) or len(wm.windows) == 0:
        print("No UI windows -> skipping viewport config")
        return

    # Select and activate the armature
    try:
        bpy.ops.object.select_all(action='DESELECT')
        active_obj.select_set(True)
        bpy.context.view_layer.objects.active = active_obj
    except Exception as e:
        print(f"Could not select armature: {e}")

    # Prefer stick for readability (persists in .blend)
    try:
        active_obj.data.display_type = 'STICK'
    except Exception:
        pass

    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue

            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if not region:
                continue

            space = area.spaces.active

            # Shading - SOLID reads better for bones
            if hasattr(space, "shading") and hasattr(space.shading, "type"):
                space.shading.type = 'SOLID'

            # Overlays
            ov = space.overlay
            if hasattr(ov, "show_overlays"):
                ov.show_overlays = True
            if hasattr(ov, "show_relationship_lines"):
                ov.show_relationship_lines = False  # Remove "swirly spaghetti"

            # Bone names and axes (attribute names vary by version)
            for attr in ("show_bone_names", "show_bones_names"):
                if hasattr(ov, attr):
                    setattr(ov, attr, True)
                    break
            for attr in ("show_bone_axes", "show_bones_axes"):
                if hasattr(ov, attr):
                    setattr(ov, attr, True)
                    break

            # Disable bone envelopes overlay (the circles around bones)
            for attr in ("show_bone_envelopes", "show_bones_envelopes"):
                if hasattr(ov, attr):
                    setattr(ov, attr, False)
                    break

            # Frame the armature using Blender 3.2+ / 5.0 temp_override API
            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_selected()
                print("Configured viewport (names+axes) + framed armature.")
            except Exception as e:
                print(f"Could not frame viewport: {e}")
                print("Viewport overlay settings applied, but framing skipped.")

            return

    print("No VIEW_3D area found; viewport not configured.")


# ----------------------------
# Rig topology map (terminal output)
# ----------------------------

def print_rig_topology(arm_obj):
    """
    Print a topology-first rig map to help identify legs/tail/head without relying on names.
    Shows: root bones, branching bones, and root-to-leaf chains sorted by length.
    """
    bones = arm_obj.data.bones
    if not bones:
        print("\n=== RIG TOPOLOGY MAP ===")
        print("No bones found.")
        return

    # Build parent->children map
    children_map = {}
    for b in bones:
        parent_name = b.parent.name if b.parent else None
        if parent_name not in children_map:
            children_map[parent_name] = []
        children_map[parent_name].append(b.name)

    # Find root bones (no parent)
    roots = children_map.get(None, [])

    # Find branching bones (>=2 children)
    branching = [(name, len(children_map.get(name, [])))
                 for name in children_map
                 if name is not None and len(children_map.get(name, [])) >= 2]
    branching.sort(key=lambda x: -x[1])  # Sort by child count descending

    # Find leaf bones (no children)
    all_parents = set(children_map.keys()) - {None}
    all_bone_names = set(b.name for b in bones)
    leaves = all_bone_names - all_parents

    # Build chains from each root to each leaf
    def trace_chain(bone_name, chain=None):
        if chain is None:
            chain = []
        chain = chain + [bone_name]
        kids = children_map.get(bone_name, [])
        if not kids:
            return [chain]
        all_chains = []
        for kid in kids:
            all_chains.extend(trace_chain(kid, chain))
        return all_chains

    all_chains = []
    for root in roots:
        all_chains.extend(trace_chain(root))

    # Sort chains by length (longest first)
    all_chains.sort(key=lambda c: -len(c))

    # Print report
    print("\n" + "=" * 50)
    print("RIG TOPOLOGY MAP")
    print("=" * 50)

    print(f"\nTotal bones: {len(bones)}")

    print(f"\nRoot bones ({len(roots)}):")
    for r in roots:
        print(f"  • {r}")

    print(f"\nBranching bones ({len(branching)}):")
    for name, count in branching:
        kids = children_map.get(name, [])
        print(f"  • {name} -> {count} children: {kids}")

    print(f"\nLeaf bones ({len(leaves)}):")
    for leaf in sorted(leaves):
        print(f"  • {leaf}")

    print(f"\nRoot-to-leaf chains (sorted by length, {len(all_chains)} total):")
    # Group chains by length for readability
    for length, group in groupby(all_chains, key=len):
        chains = list(group)
        print(f"\n  Length {length} ({len(chains)} chain{'s' if len(chains) > 1 else ''}):")
        for chain in chains:
            print(f"    {' -> '.join(chain)}")

    print("=" * 50 + "\n")

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

    # Clean/force skeleton-only
    clear_custom_shapes(arm)
    force_all_bones_visible(arm)
    configure_armature_draw(arm)
    delete_everything_except(arm)

    # Configure viewport (UI-only, gracefully skips in background mode)
    try:
        configure_first_viewport_to_show_bones(arm)
    except Exception as e:
        print(f"Viewport config failed (non-fatal): {e}")

    # Print topology map to terminal (always runs)
    print_rig_topology(arm)

    # Optional rig report JSON
    if args.report:
        save_json(args.report, rig_report(arm))
        print("Wrote report:", args.report)

    save_blend(args.out_blend)
    print("Saved:", args.out_blend)
    print("Armature:", arm.name, "bones:", len(arm.data.bones))

# NOTE: Call unconditionally (Blender sometimes doesn't set __name__ == "__main__")
main()