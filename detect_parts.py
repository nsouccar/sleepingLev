#!/usr/bin/env python3
"""
detect_parts.py - Rig-part detection for Meshy quadruped rigs

Analyzes rig_report.json topology + geometry to identify:
- root/hips hub
- chest hub
- tail chain
- head chain
- 4 leg chains (front/back, left/right)
- estimated axes (up/forward/right)
- confidence scores per part

Usage:
  python3 detect_parts.py out/rig_report.json --out out/sleep_parts.json
"""

import json
import argparse
import math
import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict


# =============================================================================
# Vector math helpers
# =============================================================================

Vec3 = Tuple[float, float, float]

def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def vec_scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)

def vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0]
    )

def vec_len(v: Vec3) -> float:
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

def vec_normalize(v: Vec3) -> Vec3:
    length = vec_len(v)
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    return (v[0]/length, v[1]/length, v[2]/length)

def vec_avg(vecs: List[Vec3]) -> Vec3:
    if not vecs:
        return (0.0, 0.0, 0.0)
    n = len(vecs)
    return (
        sum(v[0] for v in vecs) / n,
        sum(v[1] for v in vecs) / n,
        sum(v[2] for v in vecs) / n
    )


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class Bone:
    name: str
    parent: Optional[str]
    head: Vec3
    tail: Vec3
    children: List[str] = field(default_factory=list)

    @property
    def direction(self) -> Vec3:
        """Unit vector from head to tail"""
        return vec_normalize(vec_sub(self.tail, self.head))

    @property
    def length(self) -> float:
        return vec_len(vec_sub(self.tail, self.head))

    @property
    def midpoint(self) -> Vec3:
        return vec_scale(vec_add(self.head, self.tail), 0.5)


@dataclass
class Chain:
    """A sequence of bones from start to end (leaf)"""
    bones: List[str]

    @property
    def length(self) -> int:
        return len(self.bones)

    @property
    def start(self) -> str:
        return self.bones[0] if self.bones else ""

    @property
    def end(self) -> str:
        return self.bones[-1] if self.bones else ""


@dataclass
class DetectedPart:
    name: str
    chain: List[str]
    confidence: float
    side: Optional[str] = None  # "L", "R", or None
    notes: List[str] = field(default_factory=list)


@dataclass
class AxesEstimate:
    up: Vec3
    forward: Vec3
    right: Vec3
    confidence: float


@dataclass
class PartsReport:
    armature_name: str
    root: DetectedPart
    chest: Optional[DetectedPart]
    tail: Optional[DetectedPart]
    head: Optional[DetectedPart]
    legs: List[DetectedPart]
    axes: AxesEstimate
    warnings: List[str]

    def to_dict(self) -> Dict:
        return {
            "armature_name": self.armature_name,
            "root": asdict(self.root) if self.root else None,
            "chest": asdict(self.chest) if self.chest else None,
            "tail": asdict(self.tail) if self.tail else None,
            "head": asdict(self.head) if self.head else None,
            "legs": [asdict(leg) for leg in self.legs],
            "axes": {
                "up": list(self.axes.up),
                "forward": list(self.axes.forward),
                "right": list(self.axes.right),
                "confidence": self.axes.confidence
            },
            "warnings": self.warnings,
            "summary": {
                "leg_count": len(self.legs),
                "has_tail": self.tail is not None,
                "has_head": self.head is not None,
                "has_chest": self.chest is not None,
            }
        }


# =============================================================================
# Loading and graph building
# =============================================================================

def load_rig_report(path: str) -> Tuple[str, Dict[str, Bone]]:
    """Load rig_report.json and build bone lookup"""
    with open(path, "r") as f:
        data = json.load(f)

    armature_name = data.get("armature_object", "Armature")
    bones_data = data.get("bones", [])

    bones: Dict[str, Bone] = {}

    for b in bones_data:
        name = b["name"]
        parent = b.get("parent")
        head = tuple(b.get("head_local", [0, 0, 0]))
        tail = tuple(b.get("tail_local", [0, 0, 0]))
        bones[name] = Bone(name=name, parent=parent, head=head, tail=tail)

    # Build children lists
    for name, bone in bones.items():
        if bone.parent and bone.parent in bones:
            bones[bone.parent].children.append(name)

    return armature_name, bones


def find_roots(bones: Dict[str, Bone]) -> List[str]:
    """Find bones with no parent (or parent not in bone set)"""
    roots = []
    for name, bone in bones.items():
        if bone.parent is None or bone.parent not in bones:
            roots.append(name)
    return roots


def trace_chain_to_leaf(bones: Dict[str, Bone], start: str) -> List[Chain]:
    """Trace all paths from start bone to leaf bones"""
    chains = []

    def recurse(bone_name: str, path: List[str]):
        current_path = path + [bone_name]
        bone = bones[bone_name]

        if not bone.children:
            # Leaf - emit chain
            chains.append(Chain(bones=current_path))
        else:
            for child in bone.children:
                recurse(child, current_path)

    recurse(start, [])
    return chains


def get_chain_endpoint_position(bones: Dict[str, Bone], chain: Chain) -> Vec3:
    """Get the tail position of the last bone in chain"""
    if not chain.bones:
        return (0.0, 0.0, 0.0)
    return bones[chain.end].tail


def get_chain_direction(bones: Dict[str, Bone], chain: Chain) -> Vec3:
    """Get overall direction vector of chain (start head to end tail)"""
    if not chain.bones:
        return (0.0, 0.0, 0.0)
    start_pos = bones[chain.start].head
    end_pos = bones[chain.end].tail
    return vec_normalize(vec_sub(end_pos, start_pos))


# =============================================================================
# Name-based hints
# =============================================================================

def name_suggests_tail(name: str) -> bool:
    return "tail" in name.lower()

def name_suggests_head(name: str) -> bool:
    s = name.lower()
    return "head" in s or "neck" in s or "skull" in s or "jaw" in s

def name_suggests_leg(name: str) -> bool:
    s = name.lower()
    return any(x in s for x in ["leg", "arm", "paw", "foot", "hand", "thigh", "shin", "calf", "femur", "tibia"])

def name_suggests_front(name: str) -> bool:
    s = name.lower()
    return "front" in s or "fore" in s or "arm" in s or "hand" in s

def name_suggests_back(name: str) -> bool:
    s = name.lower()
    return "back" in s or "rear" in s or "hind" in s

def name_suggests_left(name: str) -> bool:
    s = name.lower()
    # Check for L_ prefix or "left"
    if re.match(r'^l[_\-\.\s]', s) or s.startswith("left"):
        return True
    # If no R_ prefix and it's a leg, assume left (Meshy convention)
    return False

def name_suggests_right(name: str) -> bool:
    s = name.lower()
    # Check for R_ prefix or "right"
    if re.match(r'^r[_\-\.\s]', s) or s.startswith("right"):
        return True
    return False

def infer_side_from_chain(chain_bones: List[str]) -> Optional[str]:
    """
    Infer left/right from bone names in chain.
    Meshy convention: R_ prefix = Right, no prefix = Left
    """
    for bone_name in chain_bones:
        if name_suggests_right(bone_name):
            return "R"
        if name_suggests_left(bone_name):
            return "L"

    # If no explicit marker, check if any bone has R_ prefix
    # If not, and it's a limb, assume Left (Meshy convention)
    has_r_prefix = any(re.match(r'^r[_\-\.\s]', b.lower()) for b in chain_bones)
    if not has_r_prefix:
        return "L"  # Default to Left if no R_ prefix

    return None

def name_suggests_chest(name: str) -> bool:
    s = name.lower()
    return any(x in s for x in ["chest", "spine", "torso", "shoulder", "rib"])

def name_suggests_hip(name: str) -> bool:
    s = name.lower()
    return any(x in s for x in ["hip", "pelvis", "root"])


# =============================================================================
# Axes estimation
# =============================================================================

def estimate_axes(bones: Dict[str, Bone], root_name: str,
                  leg_chains: List[Chain], chest_name: Optional[str]) -> AxesEstimate:
    """
    Estimate coordinate axes from rig geometry:
    - UP: opposite of average leg direction (legs go down)
    - FORWARD: root to chest direction (or best guess)
    - RIGHT: cross product
    """
    confidence = 0.5

    # Estimate UP from leg directions (legs point down, so negate)
    if leg_chains:
        leg_dirs = [get_chain_direction(bones, chain) for chain in leg_chains]
        avg_leg_dir = vec_normalize(vec_avg(leg_dirs))
        up = vec_scale(avg_leg_dir, -1.0)  # Legs go down, so up is opposite
        confidence += 0.2
    else:
        # Fallback: assume Y-up (common in Blender)
        up = (0.0, 1.0, 0.0)

    # Estimate FORWARD from root to chest
    if chest_name and chest_name in bones:
        root_pos = bones[root_name].midpoint
        chest_pos = bones[chest_name].midpoint
        forward_raw = vec_sub(chest_pos, root_pos)
        # Remove up component to get horizontal forward
        up_component = vec_scale(up, vec_dot(forward_raw, up))
        forward = vec_normalize(vec_sub(forward_raw, up_component))
        confidence += 0.2
    else:
        # Fallback: assume -Y forward (common for quadrupeds facing -Y)
        forward = (0.0, -1.0, 0.0)

    # RIGHT is cross product of up and forward
    right = vec_normalize(vec_cross(up, forward))

    # Re-orthogonalize forward
    forward = vec_normalize(vec_cross(right, up))

    return AxesEstimate(
        up=up,
        forward=forward,
        right=right,
        confidence=min(1.0, confidence)
    )


# =============================================================================
# Part detection
# =============================================================================

def detect_parts(armature_name: str, bones: Dict[str, Bone]) -> PartsReport:
    """Main detection logic"""
    warnings = []

    # --- Find root ---
    roots = find_roots(bones)
    if len(roots) == 0:
        raise ValueError("No root bone found!")
    if len(roots) > 1:
        warnings.append(f"Multiple roots found: {roots}. Using first.")

    root_name = roots[0]
    root_bone = bones[root_name]

    root_part = DetectedPart(
        name="root",
        chain=[root_name],
        confidence=1.0,
        notes=[f"Root bone: {root_name}, {len(root_bone.children)} children"]
    )

    # --- Trace all chains from root ---
    all_chains = trace_chain_to_leaf(bones, root_name)
    print(f"\nFound {len(all_chains)} chains from root '{root_name}':")
    for chain in all_chains:
        print(f"  [{chain.length}] {' -> '.join(chain.bones)}")

    # --- Identify chest hub ---
    # Chest is typically a child of root that has multiple children (branches to head + front legs)
    chest_part: Optional[DetectedPart] = None
    chest_name: Optional[str] = None

    for child_name in root_bone.children:
        child = bones[child_name]
        # Look for a bone that:
        # 1. Has name suggesting chest/spine, OR
        # 2. Has multiple children (hub), AND
        # 3. Is not obviously a leg or tail

        is_hub = len(child.children) >= 2
        name_hint = name_suggests_chest(child_name)
        not_leg = not name_suggests_leg(child_name)
        not_tail = not name_suggests_tail(child_name)

        if (name_hint or is_hub) and not_leg and not_tail:
            chest_name = child_name
            conf = 0.5
            if name_hint:
                conf += 0.3
            if is_hub:
                conf += 0.2

            chest_part = DetectedPart(
                name="chest",
                chain=[child_name],
                confidence=min(1.0, conf),
                notes=[f"Hub with {len(child.children)} children"]
            )
            break

    if not chest_part:
        warnings.append("Could not identify chest hub - will use root for breathing")

    # --- Classify chains ---
    tail_chains: List[Tuple[Chain, float]] = []  # (chain, score)
    head_chains: List[Tuple[Chain, float]] = []
    leg_chains: List[Tuple[Chain, float, str]] = []  # (chain, score, position_hint)

    for chain in all_chains:
        # Skip single-bone chains (just root)
        if chain.length <= 1:
            continue

        # Get the first bone after root to classify
        first_bone_name = chain.bones[1] if chain.length > 1 else chain.bones[0]
        chain_dir = get_chain_direction(bones, chain)

        # Check name hints
        has_tail_name = any(name_suggests_tail(b) for b in chain.bones)
        has_head_name = any(name_suggests_head(b) for b in chain.bones)
        has_leg_name = any(name_suggests_leg(b) for b in chain.bones)
        has_front_name = any(name_suggests_front(b) for b in chain.bones)
        has_back_name = any(name_suggests_back(b) for b in chain.bones)

        # Check if chain starts from chest (front leg/head) or root (back leg/tail)
        starts_from_chest = chest_name and chain.bones[1] == chest_name if chain.length > 1 else False
        # Check if the chain goes through chest
        goes_through_chest = chest_name and chest_name in chain.bones

        # Score for tail
        tail_score = 0.0
        if has_tail_name:
            tail_score += 0.8
        if not goes_through_chest and not has_leg_name and not has_head_name:
            tail_score += 0.3
        if chain.length >= 3:  # Tails tend to be longer
            tail_score += 0.1

        # Score for head
        head_score = 0.0
        if has_head_name:
            head_score += 0.8
        if goes_through_chest and not has_leg_name:
            head_score += 0.2

        # Score for leg
        leg_score = 0.0
        if has_leg_name:
            leg_score += 0.7
        # Legs typically have 3-5 bones
        if 3 <= chain.length <= 6:
            leg_score += 0.2

        # Determine front/back
        position = "unknown"
        if has_front_name:
            position = "front"
        elif has_back_name:
            position = "back"
        elif goes_through_chest:
            position = "front"
        elif not goes_through_chest and leg_score > 0:
            position = "back"

        # Classify
        if tail_score >= 0.5:
            tail_chains.append((chain, tail_score))
        elif head_score >= 0.5:
            head_chains.append((chain, head_score))
        elif leg_score >= 0.3:
            leg_chains.append((chain, leg_score, position))

    # --- Pick best tail ---
    tail_part: Optional[DetectedPart] = None
    if tail_chains:
        tail_chains.sort(key=lambda x: -x[1])
        best_tail, score = tail_chains[0]
        # Remove root from tail chain
        tail_bones = best_tail.bones[:]
        if tail_bones and tail_bones[0] == root_name:
            tail_bones = tail_bones[1:]
        if tail_bones:
            tail_part = DetectedPart(
                name="tail",
                chain=tail_bones,
                confidence=min(1.0, score),
                notes=[f"{len(tail_bones)} bones"]
            )
    if not tail_part:
        warnings.append("No tail chain detected")

    # --- Pick best head ---
    head_part: Optional[DetectedPart] = None
    if head_chains:
        head_chains.sort(key=lambda x: -x[1])
        best_head, score = head_chains[0]
        # Head chain: typically we want chest -> head, not including chest
        # Find where chest is and take from there
        head_bones = best_head.bones
        if chest_name and chest_name in head_bones:
            idx = head_bones.index(chest_name)
            head_bones = head_bones[idx+1:]  # After chest

        if head_bones:
            head_part = DetectedPart(
                name="head",
                chain=head_bones,
                confidence=min(1.0, score),
                notes=[f"{len(head_bones)} bones"]
            )
    else:
        warnings.append("No head chain detected")

    # --- Process legs ---
    detected_legs: List[DetectedPart] = []

    for chain, score, position in leg_chains:
        # Get the leg bones (skip root and chest if present)
        leg_bones = chain.bones[:]
        if leg_bones and leg_bones[0] == root_name:
            leg_bones = leg_bones[1:]
        if leg_bones and chest_name and leg_bones[0] == chest_name:
            leg_bones = leg_bones[1:]

        if not leg_bones:
            continue

        # Determine left/right from bone names in this chain
        side = infer_side_from_chain(leg_bones)

        leg_name = f"{position}_{side}" if side else position
        detected_legs.append(DetectedPart(
            name=leg_name,
            chain=leg_bones,
            confidence=min(1.0, score),
            side=side,
            notes=[f"{position} leg, {len(leg_bones)} bones"]
        ))

    # Sort legs: front-left, front-right, back-left, back-right
    def leg_sort_key(leg: DetectedPart):
        pos_order = {"front": 0, "back": 1, "unknown": 2}
        side_order = {"L": 0, "R": 1, None: 2}
        pos = leg.name.split("_")[0] if "_" in leg.name else leg.name
        return (pos_order.get(pos, 2), side_order.get(leg.side, 2))

    detected_legs.sort(key=leg_sort_key)

    if len(detected_legs) < 4:
        warnings.append(f"Only {len(detected_legs)} legs detected (expected 4)")

    # --- Estimate axes ---
    # Convert detected legs to Chain objects for axes estimation
    leg_chain_objs = [Chain(bones=leg.chain) for leg in detected_legs]
    axes = estimate_axes(bones, root_name, leg_chain_objs, chest_name)

    # --- Build report ---
    return PartsReport(
        armature_name=armature_name,
        root=root_part,
        chest=chest_part,
        tail=tail_part,
        head=head_part,
        legs=detected_legs,
        axes=axes,
        warnings=warnings
    )


# =============================================================================
# Pretty printing
# =============================================================================

def print_report(report: PartsReport):
    """Print a human-readable summary"""
    print("\n" + "=" * 60)
    print("RIG PARTS DETECTION REPORT")
    print("=" * 60)

    print(f"\nArmature: {report.armature_name}")

    def print_part(label: str, part: Optional[DetectedPart]):
        if part:
            conf_pct = int(part.confidence * 100)
            chain_str = " -> ".join(part.chain[:5])
            if len(part.chain) > 5:
                chain_str += f" ... ({len(part.chain)} bones)"
            print(f"\n{label} [{conf_pct}% conf]")
            print(f"  Chain: {chain_str}")
            for note in part.notes:
                print(f"  Note: {note}")
        else:
            print(f"\n{label}: NOT DETECTED")

    print_part("ROOT", report.root)
    print_part("CHEST", report.chest)
    print_part("TAIL", report.tail)
    print_part("HEAD", report.head)

    print(f"\nLEGS ({len(report.legs)} detected)")
    for leg in report.legs:
        conf_pct = int(leg.confidence * 100)
        side_str = f" ({leg.side})" if leg.side else ""
        chain_str = " -> ".join(leg.chain[:4])
        if len(leg.chain) > 4:
            chain_str += f" ... ({len(leg.chain)} bones)"
        print(f"  {leg.name}{side_str} [{conf_pct}%]: {chain_str}")

    print(f"\nAXES ESTIMATE [{int(report.axes.confidence * 100)}% conf]")
    print(f"  Up:      ({report.axes.up[0]:.2f}, {report.axes.up[1]:.2f}, {report.axes.up[2]:.2f})")
    print(f"  Forward: ({report.axes.forward[0]:.2f}, {report.axes.forward[1]:.2f}, {report.axes.forward[2]:.2f})")
    print(f"  Right:   ({report.axes.right[0]:.2f}, {report.axes.right[1]:.2f}, {report.axes.right[2]:.2f})")

    if report.warnings:
        print(f"\nWARNINGS ({len(report.warnings)})")
        for w in report.warnings:
            print(f"  ! {w}")

    print("\n" + "=" * 60)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Detect rig parts from rig_report.json")
    parser.add_argument("json_path", help="Path to rig_report.json")
    parser.add_argument("--out", "-o", default="out/sleep_parts.json",
                        help="Output path for sleep_parts.json")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress verbose output")
    args = parser.parse_args()

    # Load rig
    armature_name, bones = load_rig_report(args.json_path)
    print(f"Loaded {len(bones)} bones from {args.json_path}")

    # Detect parts
    report = detect_parts(armature_name, bones)

    # Print report
    if not args.quiet:
        print_report(report)

    # Save JSON
    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
