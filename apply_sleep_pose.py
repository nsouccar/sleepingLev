#!/usr/bin/env python3
"""
apply_sleep_pose.py - Apply a sleeping pose to a Meshy quadruped rig

Uses sleep_parts.json from detect_parts.py to know which bones to manipulate.
Applies rotations to create a believable sleeping pose:
- Chest/Hips: slight pitch for body settling
- Head: tuck down/sideways
- Legs: fold progressively (like tucked under body)
- Tail: gentle curl

Usage (Blender CLI):
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python apply_sleep_pose.py -- \
    --in Character_output.glb \
    --parts out/sleep_parts.json \
    --out out/sleep_pose.glb \
    --intensity 0.7

Intensity: 0.0 = no change, 1.0 = full sleep pose
"""

import bpy
import sys
import os
import json
import argparse
import math
import addon_utils
from mathutils import Euler, Vector, Quaternion


# =============================================================================
# Setup / IO
# =============================================================================

def enable_gltf_addon():
    """Ensure glTF importer/exporter is available"""
    try:
        bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
    except Exception:
        addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def import_glb(path: str):
    bpy.ops.import_scene.gltf(filepath=path)


def export_glb(path: str, arm_obj=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

    # Ensure object mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Force scene update to ensure pose is applied
    bpy.context.view_layer.update()

    # Get the evaluated depsgraph
    depsgraph = bpy.context.evaluated_depsgraph_get()

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']

    for obj in mesh_objects:
        if not obj.vertex_groups:
            continue

        print(f"\n  Baking deformation for {obj.name}...")

        # Get the evaluated (deformed) object
        obj_eval = obj.evaluated_get(depsgraph)

        # Create a NEW mesh from the evaluated object (this captures the deformed state)
        new_mesh = bpy.data.meshes.new_from_object(obj_eval)
        new_mesh.name = obj.data.name + "_baked"

        # Store old mesh
        old_mesh = obj.data

        # Replace mesh data with new deformed mesh
        obj.data = new_mesh

        # Copy materials from old mesh
        new_mesh.materials.clear()
        for mat in old_mesh.materials:
            new_mesh.materials.append(mat)

        # Remove old mesh
        bpy.data.meshes.remove(old_mesh)

        # Remove armature modifier and parent
        obj.modifiers.clear()
        if obj.parent:
            matrix_world = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = matrix_world

        # Clear vertex groups since armature is gone
        obj.vertex_groups.clear()

        print(f"    Created new mesh with {len(new_mesh.vertices)} vertices")

    # Delete the armature
    if arm_obj and arm_obj.name in bpy.data.objects:
        bpy.data.objects.remove(arm_obj, do_unlink=True)
        print("  Removed armature")

    # Save debug blend after baking
    debug_path = path.replace('.glb', '_after_bake.blend')
    bpy.ops.wm.save_as_mainfile(filepath=debug_path)
    print(f"  Saved debug blend: {debug_path}")

    # Export the mesh with baked vertex positions
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        use_selection=False,
        export_animations=False,
    )


def save_blend(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)


def find_armature():
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE':
            return obj
    return None


def configure_armature_display(arm_obj):
    """Make armature bones visible as sticks"""
    # Clear custom shapes
    if arm_obj.pose:
        for pb in arm_obj.pose.bones:
            pb.custom_shape = None

    # Object display
    arm_obj.show_in_front = True
    if hasattr(arm_obj, "show_bounds"):
        arm_obj.show_bounds = False
    if hasattr(arm_obj, "display_type"):
        arm_obj.display_type = 'WIRE'

    # Armature display
    arm_data = arm_obj.data
    if hasattr(arm_data, "display_type"):
        arm_data.display_type = 'STICK'

    # Unhide all bones
    for b in arm_data.bones:
        b.hide = False

    # Unhide bone collections (Blender 4/5)
    if hasattr(arm_data, "collections_all"):
        for c in arm_data.collections_all:
            if hasattr(c, "is_visible"):
                c.is_visible = True


def load_parts(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True, help="Input .glb file")
    p.add_argument("--parts", required=True, help="Path to sleep_parts.json")
    p.add_argument("--out", required=True, help="Output .glb file")
    p.add_argument("--intensity", type=float, default=0.7,
                   help="Pose intensity 0.0-1.0 (default: 0.7)")
    p.add_argument("--side", choices=["left", "right"], default="right",
                   help="Which side the animal sleeps on (default: right)")
    p.add_argument("--blend", default="", help="Also save a .blend file for debugging")
    return p.parse_args(argv)


# =============================================================================
# Rotation helpers
# =============================================================================

def rotate_bone_local(pose_bone, axis: str, degrees: float):
    """
    Rotate a pose bone around its local axis using matrix multiplication.
    Works with any rotation mode (quaternion, euler, axis-angle).
    axis: 'X', 'Y', or 'Z'
    degrees: rotation amount in degrees
    """
    from mathutils import Matrix

    radians = math.radians(degrees)

    # Create rotation matrix for the specified axis
    if axis.upper() == 'X':
        rot_matrix = Matrix.Rotation(radians, 4, 'X')
    elif axis.upper() == 'Y':
        rot_matrix = Matrix.Rotation(radians, 4, 'Y')
    else:
        rot_matrix = Matrix.Rotation(radians, 4, 'Z')

    # Apply rotation by multiplying with current matrix
    # pose_bone.matrix_basis is the local transform matrix
    pose_bone.matrix_basis = pose_bone.matrix_basis @ rot_matrix

    # Debug: print the rotation being applied
    print(f"    DEBUG: {pose_bone.name} rotated {degrees:.1f}° around {axis}")


def rotate_bone_world_axis(pose_bone, world_axis: Vector, degrees: float):
    """
    Rotate a pose bone around a world-space axis.
    Converts to bone-local space first.
    """
    radians = math.radians(degrees)

    # Get bone's world matrix
    arm_obj = pose_bone.id_data
    bone_world_matrix = arm_obj.matrix_world @ pose_bone.matrix

    # Convert world axis to bone-local axis
    bone_local_axis = bone_world_matrix.inverted().to_3x3() @ world_axis
    bone_local_axis.normalize()

    # Create rotation quaternion around local axis
    rot_quat = Quaternion(bone_local_axis, radians)

    # Apply to current rotation
    if pose_bone.rotation_mode == 'QUATERNION':
        pose_bone.rotation_quaternion = rot_quat @ pose_bone.rotation_quaternion
    else:
        current_quat = pose_bone.rotation_euler.to_quaternion()
        new_quat = rot_quat @ current_quat
        pose_bone.rotation_euler = new_quat.to_euler(pose_bone.rotation_mode)


# =============================================================================
# Sleep pose application
# =============================================================================

def apply_chest_pose(arm_obj, parts: dict, intensity: float, side: str):
    """Apply settling rotation to chest"""
    chest_data = parts.get("chest")
    if not chest_data:
        print("  No chest detected, skipping chest pose")
        return

    chain = chest_data.get("chain", [])
    if not chain:
        return

    chest_bone_name = chain[0]
    pose_bone = arm_obj.pose.bones.get(chest_bone_name)
    if not pose_bone:
        print(f"  Chest bone '{chest_bone_name}' not found in pose bones")
        return

    # Pitch chest down slightly (animal settling)
    pitch_deg = -8.0 * intensity

    # Roll toward sleep side
    roll_deg = 5.0 * intensity if side == "right" else -5.0 * intensity

    rotate_bone_local(pose_bone, 'X', pitch_deg)
    rotate_bone_local(pose_bone, 'Y', roll_deg)

    print(f"  Chest '{chest_bone_name}': pitch {pitch_deg:.1f}°, roll {roll_deg:.1f}°")


def apply_hips_pose(arm_obj, parts: dict, intensity: float, side: str):
    """Apply counter-rotation to hips/root"""
    root_data = parts.get("root")
    if not root_data:
        return

    chain = root_data.get("chain", [])
    if not chain:
        return

    root_bone_name = chain[0]
    pose_bone = arm_obj.pose.bones.get(root_bone_name)
    if not pose_bone:
        print(f"  Root bone '{root_bone_name}' not found in pose bones")
        return

    # Slight counter-pitch to chest
    pitch_deg = 3.0 * intensity

    # Roll toward sleep side (less than chest)
    roll_deg = 3.0 * intensity if side == "right" else -3.0 * intensity

    rotate_bone_local(pose_bone, 'X', pitch_deg)
    rotate_bone_local(pose_bone, 'Y', roll_deg)

    print(f"  Hips '{root_bone_name}': pitch {pitch_deg:.1f}°, roll {roll_deg:.1f}°")


def apply_head_pose(arm_obj, parts: dict, intensity: float, side: str):
    """Apply head tuck - down and slightly to the side"""
    head_data = parts.get("head")
    if not head_data:
        print("  No head detected, skipping head pose")
        return

    chain = head_data.get("chain", [])
    if not chain:
        return

    # Apply progressive rotation down the head chain
    for i, bone_name in enumerate(chain):
        pose_bone = arm_obj.pose.bones.get(bone_name)
        if not pose_bone:
            continue

        # First bone gets most rotation, distribute along chain
        factor = 1.0 - (i / max(len(chain), 1)) * 0.5

        # Pitch down (tuck chin)
        pitch_deg = -15.0 * intensity * factor

        # Turn head toward sleep side
        yaw_deg = 10.0 * intensity * factor if side == "right" else -10.0 * intensity * factor

        rotate_bone_local(pose_bone, 'X', pitch_deg)
        rotate_bone_local(pose_bone, 'Z', yaw_deg)

        print(f"  Head '{bone_name}': pitch {pitch_deg:.1f}°, yaw {yaw_deg:.1f}°")


def apply_tail_pose(arm_obj, parts: dict, intensity: float, side: str):
    """Apply gentle curl to tail"""
    tail_data = parts.get("tail")
    if not tail_data:
        print("  No tail detected, skipping tail pose")
        return

    chain = tail_data.get("chain", [])
    if not chain:
        return

    # Curl tail progressively
    for i, bone_name in enumerate(chain):
        pose_bone = arm_obj.pose.bones.get(bone_name)
        if not pose_bone:
            continue

        # Progressive curl - more toward the tip
        progress = i / max(len(chain) - 1, 1)

        # Curl inward (toward body)
        curl_deg = 8.0 * intensity * (0.5 + progress * 0.5)

        # Curl direction based on sleep side
        if side == "right":
            rotate_bone_local(pose_bone, 'Z', curl_deg)
        else:
            rotate_bone_local(pose_bone, 'Z', -curl_deg)

        # Slight downward curve
        rotate_bone_local(pose_bone, 'X', -3.0 * intensity * progress)

        print(f"  Tail '{bone_name}': curl {curl_deg:.1f}°")


def apply_leg_pose(arm_obj, leg_data: dict, intensity: float, is_front: bool, side: str):
    """
    Apply folded pose to a single leg.
    Front legs fold forward/under, back legs fold backward/under.
    """
    chain = leg_data.get("chain", [])
    leg_side = leg_data.get("side", "")
    leg_name = leg_data.get("name", "leg")

    if not chain:
        return

    # Determine if this leg is on the "down" side (against the ground)
    is_down_side = (side == "right" and leg_side == "R") or \
                   (side == "left" and leg_side == "L")

    for i, bone_name in enumerate(chain):
        pose_bone = arm_obj.pose.bones.get(bone_name)
        if not pose_bone:
            continue

        # Progress along leg (0 = hip, 1 = foot)
        progress = i / max(len(chain) - 1, 1)

        if is_front:
            # Front legs: fold backward (under body)
            # First joint bends back, second forward, etc. (alternating)
            if i == 0:
                # Upper leg - rotate back
                fold_deg = -25.0 * intensity
            elif i == 1:
                # Middle joint - rotate forward (knee bend)
                fold_deg = 45.0 * intensity
            elif i == 2:
                # Lower joint - straighten a bit
                fold_deg = -20.0 * intensity
            else:
                fold_deg = 0
        else:
            # Back legs: similar fold pattern
            if i == 0:
                # Upper leg - rotate forward
                fold_deg = 20.0 * intensity
            elif i == 1:
                # Middle joint - rotate back (knee bend)
                fold_deg = -50.0 * intensity
            elif i == 2:
                # Lower joint
                fold_deg = 30.0 * intensity
            else:
                fold_deg = 0

        # Down-side legs are more tucked
        if is_down_side:
            fold_deg *= 1.2

        rotate_bone_local(pose_bone, 'X', fold_deg)

        # Slight inward rotation for tucked legs
        if is_down_side and i == 0:
            inward_deg = 10.0 * intensity if leg_side == "R" else -10.0 * intensity
            rotate_bone_local(pose_bone, 'Z', inward_deg)

    print(f"  Leg '{leg_name}': folded ({'down-side' if is_down_side else 'up-side'})")


def apply_legs_pose(arm_obj, parts: dict, intensity: float, side: str):
    """Apply folded pose to all legs"""
    legs = parts.get("legs", [])
    if not legs:
        print("  No legs detected, skipping leg poses")
        return

    for leg_data in legs:
        leg_name = leg_data.get("name", "")
        is_front = "front" in leg_name.lower()
        apply_leg_pose(arm_obj, leg_data, intensity, is_front, side)


def apply_sleep_pose(arm_obj, parts: dict, intensity: float, side: str):
    """Apply complete sleep pose to armature"""
    print(f"\nApplying sleep pose (intensity={intensity}, side={side})")

    # Ensure we're in pose mode
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='POSE')

    # Reset all pose bones to rest position first
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()

    print("\nPosing body:")
    apply_hips_pose(arm_obj, parts, intensity, side)
    apply_chest_pose(arm_obj, parts, intensity, side)

    print("\nPosing head:")
    apply_head_pose(arm_obj, parts, intensity, side)

    print("\nPosing tail:")
    apply_tail_pose(arm_obj, parts, intensity, side)

    print("\nPosing legs:")
    apply_legs_pose(arm_obj, parts, intensity, side)

    # Bake pose as keyframes so it exports in glTF
    bake_pose_as_action(arm_obj, "sleep_pose")

    # Return to object mode
    bpy.ops.object.mode_set(mode='OBJECT')

    print("\nSleep pose applied!")


def bake_pose_as_action(arm_obj, action_name: str):
    """
    Bake the current pose as keyframes in an action.
    This ensures the pose exports properly in glTF.
    """
    print(f"\nBaking pose as action '{action_name}'...")

    # Create or get action
    if arm_obj.animation_data is None:
        arm_obj.animation_data_create()

    action = bpy.data.actions.new(name=action_name)
    arm_obj.animation_data.action = action

    # Set current frame
    bpy.context.scene.frame_set(1)

    # Keyframe all pose bones
    for pose_bone in arm_obj.pose.bones:
        # Insert keyframes for location, rotation, scale
        pose_bone.keyframe_insert(data_path="location", frame=1)

        if pose_bone.rotation_mode == 'QUATERNION':
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=1)
        else:
            pose_bone.keyframe_insert(data_path="rotation_euler", frame=1)

        pose_bone.keyframe_insert(data_path="scale", frame=1)

    print(f"  Keyframed {len(arm_obj.pose.bones)} bones at frame 1")


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 60)
    print("APPLY SLEEP POSE")
    print("=" * 60)

    args = parse_args()

    print(f"\nInput GLB: {args.in_path}")
    print(f"Parts JSON: {args.parts}")
    print(f"Output GLB: {args.out}")
    print(f"Intensity: {args.intensity}")
    print(f"Sleep side: {args.side}")

    # Setup
    enable_gltf_addon()
    clear_scene()

    # Import
    print(f"\nImporting {args.in_path}...")
    import_glb(args.in_path)

    # Find armature
    arm_obj = find_armature()
    if not arm_obj:
        raise RuntimeError("No armature found in GLB!")
    print(f"Found armature: {arm_obj.name}")

    # Configure display so bones are visible
    configure_armature_display(arm_obj)

    # Load parts
    parts = load_parts(args.parts)
    print(f"Loaded parts: {list(parts.keys())}")

    # Apply pose
    apply_sleep_pose(arm_obj, parts, args.intensity, args.side)

    # Optionally save .blend for debugging (BEFORE export, which destroys armature)
    if args.blend:
        print(f"\nSaving debug .blend to {args.blend}...")
        save_blend(args.blend)
        print(f"Saved: {args.blend}")

    # Export
    print(f"\nExporting to {args.out}...")
    export_glb(args.out, arm_obj)
    print(f"Saved: {args.out}")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
