#!/usr/bin/env python3
"""Generate crisp, high-fidelity UI showcase screenshots for the landing page."""
from pathlib import Path
from PIL import Image, ImageDraw


def create_dashboard_showcase(path: Path) -> None:
    width, height = 1200, 750
    img = Image.new("RGB", (width, height), color="#F7F8FA")
    d = ImageDraw.Draw(img)

    # Top navigation bar
    d.rectangle([(0, 0), (width, 64)], fill="#FFFFFF", outline="#E3E6EC", width=1)
    d.rectangle([(24, 20), (48, 44)], fill="#4338CA")  # Logo badge
    d.text((60, 22), "ParkWise", fill="#111827")
    d.text((135, 24), "Enterprise Ops", fill="#8A94A6")

    # Nav links
    d.text((width - 320, 24), "Dashboard", fill="#4338CA")
    d.text((width - 220, 24), "Live Feeds", fill="#475467")
    d.text((width - 130, 24), "Settings", fill="#475467")
    d.rectangle([(width - 60, 18), (width - 24, 46)], fill="#EEF2FF", outline="#4338CA")

    # Header section
    d.text((32, 90), "OPERATIONS CENTER", fill="#4338CA")
    d.text((32, 112), "Fleet Occupancy Overview", fill="#111827")
    d.text((32, 140), "Real-time measured occupancy across 8 active parking facilities", fill="#475467")

    # 4 Metric Cards
    metrics = [
        ("TOTAL CAPACITY", "248 bays", "+12 bays online", "#0B6B4B"),
        ("CURRENT OCCUPANCY", "78.2%", "+4.1% vs peak yesterday", "#4338CA"),
        ("DETECTION CONFIDENCE", "94.8%", "YOLO26 · Zero false-free", "#0B6B4B"),
        ("ACTIVE CAMERA FEEDS", "8 / 8 live", "Avg latency 42ms", "#0B6B4B"),
    ]
    card_w = (width - 64 - 3 * 20) // 4
    for i, (title, val, sub, tone) in enumerate(metrics):
        x = 32 + i * (card_w + 20)
        y = 175
        d.rounded_rectangle([(x, y), (x + card_w, y + 105)], radius=8, fill="#FFFFFF", outline="#E3E6EC", width=1)
        d.text((x + 16, y + 14), title, fill="#5B6577")
        d.text((x + 16, y + 36), val, fill="#111827")
        d.text((x + 16, y + 74), sub, fill=tone)

    # Main Chart Panel (Left)
    chart_x, chart_y, chart_w, chart_h = 32, 305, 720, 410
    d.rounded_rectangle([(chart_x, chart_y), (chart_x + chart_w, chart_y + chart_h)], radius=8, fill="#FFFFFF", outline="#E3E6EC", width=1)
    d.text((chart_x + 20, chart_y + 18), "Occupancy Trend (Last 12 Hours)", fill="#111827")
    d.text((chart_x + 20, chart_y + 40), "Measured per-minute bay state distribution", fill="#5B6577")

    # Chart grid lines & curve
    for gy in range(chart_y + 90, chart_y + 350, 60):
        d.line([(chart_x + 30, gy), (chart_x + chart_w - 30, gy)], fill="#F1F3F6", width=1)

    points = [
        (chart_x + 40, chart_y + 300),
        (chart_x + 120, chart_y + 280),
        (chart_x + 200, chart_y + 240),
        (chart_x + 280, chart_y + 190),
        (chart_x + 360, chart_y + 160),
        (chart_x + 440, chart_y + 140),
        (chart_x + 520, chart_y + 170),
        (chart_x + 600, chart_y + 150),
        (chart_x + 680, chart_y + 180),
    ]
    for p1, p2 in zip(points[:-1], points[1:]):
        d.line([p1, p2], fill="#4338CA", width=3)
    for px, py in points:
        d.ellipse([(px - 4, py - 4), (px + 4, py + 4)], fill="#FFFFFF", outline="#4338CA", width=2)

    # Right side: Live Bay Status Matrix
    side_x, side_y, side_w, side_h = chart_x + chart_w + 20, 305, width - chart_w - 32 - 52, 410
    d.rounded_rectangle([(side_x, side_y), (side_x + side_w, side_y + side_h)], radius=8, fill="#FFFFFF", outline="#E3E6EC", width=1)
    d.text((side_x + 20, side_y + 18), "Live Bay Matrix: Zone North", fill="#111827")
    d.text((side_x + 20, side_y + 40), "Green = Free · Indigo = Occupied", fill="#5B6577")

    # Grid of bays
    cols, rows = 4, 6
    bw, bh = (side_w - 40 - (cols - 1) * 8) // cols, 38
    bay_idx = 1
    for r in range(rows):
        for c in range(cols):
            bx = side_x + 20 + c * (bw + 8)
            by = side_y + 75 + r * (bh + 10)
            is_occupied = (r * cols + c) % 3 != 0
            bg_color = "#EEF2FF" if is_occupied else "#E8F6EF"
            border_color = "#4338CA" if is_occupied else "#12915F"
            text_color = "#4338CA" if is_occupied else "#0B6B4B"
            label = f"N-{bay_idx:02d}"
            state = "OCC" if is_occupied else "FREE"
            d.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=4, fill=bg_color, outline=border_color, width=1)
            d.text((bx + 6, by + 6), label, fill=text_color)
            d.text((bx + 6, by + 22), state, fill=text_color)
            bay_idx += 1

    img.save(path, "PNG", optimize=True)
    print(f"Generated {path}")


def create_live_showcase(path: Path) -> None:
    width, height = 1200, 750
    img = Image.new("RGB", (width, height), color="#0E1116")  # Professional dark monitor mode
    d = ImageDraw.Draw(img)

    # Header
    d.rectangle([(0, 0), (width, 64)], fill="#151A22", outline="#262D39", width=1)
    d.rectangle([(24, 20), (48, 44)], fill="#5B5BD6")
    d.text((60, 22), "ParkWise Live Stream Monitor", fill="#E6E9EF")
    d.text((width - 240, 24), "STREAM #1: GATE A (1080p 30fps)", fill="#4CC38A")

    # Left: Video Player mockup
    vx, vy, vw, vh = 32, 90, 780, 520
    d.rounded_rectangle([(vx, vy), (vx + vw, vy + vh)], radius=8, fill="#1B212B", outline="#262D39", width=1)

    # Parking lot asphalt lines & camera perspective
    d.line([(vx + 40, vy + vh - 40), (vx + 340, vy + 80)], fill="#262D39", width=2)
    d.line([(vx + 260, vy + vh - 40), (vx + 440, vy + 80)], fill="#262D39", width=2)
    d.line([(vx + 500, vy + vh - 40), (vx + 560, vy + 80)], fill="#262D39", width=2)

    # Overlay bounding boxes with bay polygons
    bays = [
        ([(vx + 60, vy + 300), (vx + 200, vy + 280), (vx + 240, vy + 450), (vx + 90, vy + 480)], "#5B5BD6", "Bay 01: OCCUPIED (Car 98.4%)"),
        ([(vx + 230, vy + 260), (vx + 360, vy + 245), (vx + 400, vy + 410), (vx + 270, vy + 430)], "#4CC38A", "Bay 02: FREE (0.0%)"),
        ([(vx + 380, vy + 230), (vx + 490, vy + 220), (vx + 530, vy + 370), (vx + 420, vy + 385)], "#5B5BD6", "Bay 03: OCCUPIED (SUV 96.1%)"),
        ([(vx + 510, vy + 210), (vx + 610, vy + 200), (vx + 640, vy + 330), (vx + 540, vy + 345)], "#4CC38A", "Bay 04: FREE (0.0%)"),
    ]
    for poly, color, label in bays:
        d.polygon(poly, outline=color, width=2)
        # Label pill above bay
        lx, ly = poly[0][0], poly[0][1] - 18
        d.rectangle([(lx, ly), (lx + 180, ly + 16)], fill="#151A22", outline=color)
        d.text((lx + 4, ly + 2), label, fill="#E6E9EF")

    # Bottom Player Controls
    cx, cy, cw, ch = vx, vy + vh + 16, vw, 90
    d.rounded_rectangle([(cx, cy), (cx + cw, cy + ch)], radius=8, fill="#151A22", outline="#262D39", width=1)
    d.text((cx + 20, cy + 18), "LIVE WEBSOCKET INFERENCE · 0-COPY CANVAS", fill="#A3ACBA")
    d.text((cx + 20, cy + 42), "Model: YOLO26s-ONNX · Latency: 14.2ms · ByteTrack IDs: [102, 104, 105]", fill="#E6E9EF")

    # Right: Telemetry & Event Stream
    rx, ry, rw, rh = vx + vw + 20, 90, width - vw - 84, 626
    d.rounded_rectangle([(rx, ry), (rx + rw, ry + rh)], radius=8, fill="#151A22", outline="#262D39", width=1)
    d.text((rx + 20, ry + 18), "Live Telemetry", fill="#E6E9EF")
    d.text((rx + 20, ry + 38), "Real-time state change events", fill="#8993A4")

    events = [
        ("14:24:02", "Bay 01 Occupied", "Vehicle ID #102 parked", "#5B5BD6"),
        ("14:23:45", "Bay 04 Cleared", "Vehicle ID #98 departed", "#4CC38A"),
        ("14:21:10", "Bay 03 Occupied", "Vehicle ID #95 parked", "#5B5BD6"),
        ("14:18:22", "Confidence Check", "Mean 94.6% (Passed)", "#4CC38A"),
        ("14:15:00", "Stream Heartbeat", "RTSP sync 1080p OK", "#8993A4"),
    ]
    for i, (ts, title, desc, col) in enumerate(events):
        ey = ry + 80 + i * 85
        d.rounded_rectangle([(rx + 16, ey), (rx + rw - 16, ey + 70)], radius=6, fill="#1B212B", outline="#262D39")
        d.rectangle([(rx + 16, ey), (rx + 22, ey + 70)], fill=col)
        d.text((rx + 30, ey + 10), f"{ts} · {title}", fill="#E6E9EF")
        d.text((rx + 30, ey + 36), desc, fill="#A3ACBA")

    img.save(path, "PNG", optimize=True)
    print(f"Generated {path}")


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parents[1] / "web" / "public" / "showcase"
    out_dir.mkdir(parents=True, exist_ok=True)
    create_dashboard_showcase(out_dir / "dashboard-light.png")
    create_live_showcase(out_dir / "live-analysis.png")
