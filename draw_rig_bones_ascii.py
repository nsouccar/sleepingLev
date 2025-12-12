#!/usr/bin/env python3
import json, argparse, os, sys, math
from typing import List, Tuple, Dict

# ---------- ANSI color ----------
def supports_color(no_color: bool) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()

class C:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.RESET = "\033[0m" if enabled else ""
        self.DIM   = "\033[2m" if enabled else ""
        self.BOLD  = "\033[1m" if enabled else ""
        self.RED   = "\033[31m" if enabled else ""
        self.GREEN = "\033[32m" if enabled else ""
        self.YELLOW= "\033[33m" if enabled else ""
        self.BLUE  = "\033[34m" if enabled else ""
        self.MAG   = "\033[35m" if enabled else ""
        self.CYAN  = "\033[36m" if enabled else ""
        self.GRAY  = "\033[90m" if enabled else ""

# ---------- math ----------
def rot_yaw_pitch_roll(p, yaw, pitch, roll):
    """Rotate point p=(x,y,z) by yaw(Z?), pitch(X?), roll(Y?) — we’ll use:
       yaw around Y, pitch around X, roll around Z (simple and good enough)."""
    x,y,z = p
    cy, sy = math.cos(yaw), math.sin(yaw)
    cx, sx = math.cos(pitch), math.sin(pitch)
    cz, sz = math.cos(roll), math.sin(roll)

    # yaw (Y axis)
    x, z = (x*cy + z*sy), (-x*sy + z*cy)
    # pitch (X axis)
    y, z = (y*cx - z*sx), (y*sx + z*cx)
    # roll (Z axis)
    x, y = (x*cz - y*sz), (x*sz + y*cz)
    return (x,y,z)

def project(p3, plane: str):
    x,y,z = p3
    plane = plane.lower()
    if plane == "xz":
        return (x, z)
    if plane == "xy":
        return (x, y)
    if plane == "yz":
        return (y, z)
    raise ValueError("plane must be one of: xz, xy, yz")

def bresenham(x0, y0, x1, y1):
    """Integer grid line between (x0,y0) and (x1,y1)."""
    pts = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        pts.append((x,y))
        if x == x1 and y == y1:
            break
        e2 = 2*err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return pts

# ---------- loading ----------
def load_bones(path: str):
    with open(path, "r") as f:
        data = json.load(f)
    bones = data["bones"] if isinstance(data, dict) and "bones" in data else data
    out = []
    for b in bones:
        if "name" not in b: 
            continue
        h = b.get("head_local") or b.get("head") or b.get("headLocal")
        t = b.get("tail_local") or b.get("tail") or b.get("tailLocal")
        if not (isinstance(h, list) and isinstance(t, list) and len(h)==3 and len(t)==3):
            continue
        out.append({
            "name": b["name"],
            "parent": b.get("parent"),
            "head": (float(h[0]), float(h[1]), float(h[2])),
            "tail": (float(t[0]), float(t[1]), float(t[2])),
        })
    if not out:
        raise ValueError("No bones with head_local/tail_local found.")
    return out

# ---------- styling / tags ----------
def tag_for_name(name: str):
    s = name.lower()
    if "tail" in s: return "TAIL"
    if "head" in s or "neck" in s: return "HEAD"
    if "leg" in s or "arm" in s or "paw" in s or "foot" in s or "hand" in s: return "LIMB"
    if "hip" in s or "chest" in s or "spine" in s or "torso" in s: return "TORSO"
    return "BONE"

def color_for_tag(tag: str, c: C):
    if tag == "TAIL":  return c.MAG
    if tag == "HEAD":  return c.RED
    if tag == "LIMB":  return c.BLUE
    if tag == "TORSO": return c.YELLOW
    return c.RESET

# ---------- rendering ----------
def render_ascii(bones, plane, width, height, yaw_deg, pitch_deg, roll_deg, no_color, endpoints, legend_max):
    c = C(supports_color(no_color) is True)

    yaw   = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    roll  = math.radians(roll_deg)

    # Rotate + project all points to get bounds
    segs2 = []
    pts2 = []
    for b in bones:
        h3 = rot_yaw_pitch_roll(b["head"], yaw, pitch, roll)
        t3 = rot_yaw_pitch_roll(b["tail"], yaw, pitch, roll)
        h2 = project(h3, plane)
        t2 = project(t3, plane)
        segs2.append((b, h2, t2))
        pts2.extend([h2, t2])

    minx = min(p[0] for p in pts2); maxx = max(p[0] for p in pts2)
    miny = min(p[1] for p in pts2); maxy = max(p[1] for p in pts2)

    # pad bounds a bit
    padx = (maxx - minx) * 0.05 or 1.0
    pady = (maxy - miny) * 0.05 or 1.0
    minx -= padx; maxx += padx
    miny -= pady; maxy += pady

    def to_grid(p):
        x, y = p
        gx = int((x - minx) / (maxx - minx) * (width - 1))
        gy = int((y - miny) / (maxy - miny) * (height - 1))
        # terminal y goes downward; we flip so bigger y is higher
        gy = (height - 1) - gy
        return gx, gy

    grid = [[" " for _ in range(width)] for _ in range(height)]
    color_grid = [["" for _ in range(width)] for _ in range(height)]

    # draw longer bones last so they “sit on top” less (we'll sort short->long then draw)
    def seg_len(h2, t2):
        return (h2[0]-t2[0])**2 + (h2[1]-t2[1])**2

    segs2.sort(key=lambda s: seg_len(s[1], s[2]))

    for b, h2, t2 in segs2:
        x0,y0 = to_grid(h2)
        x1,y1 = to_grid(t2)
        tag = tag_for_name(b["name"])
        col = color_for_tag(tag, c)

        pts = bresenham(x0,y0,x1,y1)
        for (x,y) in pts:
            if 0 <= x < width and 0 <= y < height:
                # choose a basic line char
                ch = "·"
                if len(pts) > 1:
                    if x0 == x1: ch = "│"
                    elif y0 == y1: ch = "─"
                    else: ch = "╱" if (x1-x0)*(y1-y0) < 0 else "╲"
                grid[y][x] = ch
                color_grid[y][x] = col

        if endpoints:
            for (x,y,ch) in [(x0,y0,"●"), (x1,y1,"●")]:
                if 0 <= x < width and 0 <= y < height:
                    grid[y][x] = ch
                    color_grid[y][x] = col + c.BOLD

    # print
    print(f"{c.DIM}ASCII bone projection plane={plane.upper()}  yaw={yaw_deg}  pitch={pitch_deg}  roll={roll_deg}{c.RESET}")
    for y in range(height):
        line = []
        for x in range(width):
            col = color_grid[y][x]
            ch = grid[y][x]
            if col:
                line.append(col + ch + c.RESET)
            else:
                line.append(ch)
        print("".join(line))

    # legend (optional)
    if legend_max and legend_max > 0:
        # show most common tags present
        tags_present = sorted({tag_for_name(b["name"]) for b in bones})
        print("\nLEGEND")
        for t in tags_present:
            col = color_for_tag(t, c)
            print(f"  {col}{t}{c.RESET}")

        # show a few bone names as sanity anchors
        print("\nBONES (sample)")
        for b in bones[:legend_max]:
            tag = tag_for_name(b["name"])
            col = color_for_tag(tag, c)
            print(f"  {col}{b['name']}{c.RESET}")

def main():
    ap = argparse.ArgumentParser(description="Draw bones (head->tail) as ASCII by projecting into 2D.")
    ap.add_argument("json_path", help="Path to rig_report.json")
    ap.add_argument("--plane", default="xz", choices=["xz","xy","yz"], help="Projection plane")
    ap.add_argument("--width", type=int, default=120, help="Terminal drawing width")
    ap.add_argument("--height", type=int, default=40, help="Terminal drawing height")
    ap.add_argument("--yaw", type=float, default=0.0, help="Yaw degrees (rotate around Y)")
    ap.add_argument("--pitch", type=float, default=0.0, help="Pitch degrees (rotate around X)")
    ap.add_argument("--roll", type=float, default=0.0, help="Roll degrees (rotate around Z)")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--no-endpoints", action="store_true", help="Don’t draw endpoint dots")
    ap.add_argument("--legend", type=int, default=20, help="Show legend + first N bone names (0 disables)")
    args = ap.parse_args()

    bones = load_bones(args.json_path)
    render_ascii(
        bones=bones,
        plane=args.plane,
        width=args.width,
        height=args.height,
        yaw_deg=args.yaw,
        pitch_deg=args.pitch,
        roll_deg=args.roll,
        no_color=args.no_color,
        endpoints=(not args.no_endpoints),
        legend_max=args.legend,
    )

if __name__ == "__main__":
    main()