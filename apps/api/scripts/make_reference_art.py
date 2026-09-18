"""Worked-example illustrations for the demo project.

Diagrams, not photographs. A diagram can put the one detail that matters in the
middle of an otherwise empty frame with nothing competing for attention, which
is what a worked example is for — and it does not require somebody to find a
correctly installed board and a wrongly installed one on the same day.

Two steps, because rasterising needs a browser and this file does not:

    python scripts/make_reference_art.py           # writes reference_art/svg/*.svg
    node scripts/render_reference_art.mjs \
        scripts/reference_art/svg scripts/reference_art    # writes *.png

The PNGs are committed, so neither step is needed to run the demo seed. Run
them when a lesson needs changing.
"""

from pathlib import Path

W, H = 900, 675
OUT = Path(__file__).parent / "reference_art" / "svg"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1F2933"
MUTED = "#6B7785"
BG = "#EDEFF2"
METAL = "#D8DCE1"
METAL_MID = "#B9C0C8"
METAL_DARK = "#8C959F"
DEADFRONT = "#E3E6EA"
BREAKER = "#2B3440"
CAVITY = "#343A41"
COPPER = "#B06E3B"
GOOD = "#2E7D4F"
BAD = "#B3261E"
NEAR = "#B26A00"

FONT = "font-family='DejaVu Sans, Helvetica, Arial, sans-serif'"


def ring(x, y, w, h, colour, dash=False):
    d = " stroke-dasharray='10 7'" if dash else ""
    return (
        f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='10' fill='none' "
        f"stroke='{colour}' stroke-width='5'{d}/>"
    )


def text(x, y, s, size=20, colour=INK, anchor="start", weight="normal", mono=False):
    fam = "font-family='DejaVu Sans Mono, monospace'" if mono else FONT
    return (
        f"<text x='{x}' y='{y}' {fam} font-size='{size}' fill='{colour}' "
        f"text-anchor='{anchor}' font-weight='{weight}'>{s}</text>"
    )


def svg(body):
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
        f"viewBox='0 0 {W} {H}'><rect width='{W}' height='{H}' fill='{BG}'/>{body}</svg>"
    )


def write(name, body):
    (OUT / f"{name}.svg").write_text(svg(body))


# ---------------------------------------------------------------- enclosure


def enclosure(inner=True):
    out = [
        f"<rect x='120' y='55' width='660' height='565' rx='8' fill='{METAL}' "
        f"stroke='{METAL_DARK}' stroke-width='3'/>",
        f"<rect x='138' y='73' width='624' height='529' rx='4' fill='none' "
        f"stroke='{METAL_MID}' stroke-width='2'/>",
    ]
    if inner:
        out.append(
            f"<rect x='160' y='95' width='580' height='485' rx='3' fill='{DEADFRONT}' "
            f"stroke='{METAL_MID}' stroke-width='2'/>"
        )
    return "".join(out)


def breaker(x, y, w=180, h=32, label=""):
    return "".join(
        [
            f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='3' fill='{BREAKER}'/>",
            f"<rect x='{x + w - 40}' y='{y + 7}' width='26' height='18' rx='2' fill='#E9ECEF'/>",
            text(x + 12, y + 21, label, size=13, colour="#C6CCD3", mono=True) if label else "",
        ]
    )


def filler_plate(x, y, w=180, h=32, proud=False):
    if not proud:
        return (
            f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='3' fill='#CFD4DA' "
            f"stroke='#9AA3AD' stroke-width='1.5'/>"
        )
    return "".join(
        [
            f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='3' fill='{CAVITY}'/>",
            f"<rect x='{x - 6}' y='{y - 6}' width='{w}' height='{h}' rx='3' fill='#CFD4DA' "
            f"stroke='#9AA3AD' stroke-width='1.5'/>",
            f"<line x1='{x + w - 6}' y1='{y - 6}' x2='{x + w}' y2='{y}' stroke='{CAVITY}' "
            f"stroke-width='2'/>",
        ]
    )


def opening(x, y, w=180, h=32):
    return "".join(
        [
            f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='3' fill='{CAVITY}'/>",
            f"<rect x='{x + 14}' y='{y + 11}' width='{w - 28}' height='10' rx='2' "
            f"fill='{COPPER}'/>",
        ]
    )


def breaker_column(x, y0, fills):
    """fills: list of ('breaker'|'filler'|'proud'|'open', label)."""
    out = []
    for i, (kind, label) in enumerate(fills):
        y = y0 + i * 40
        if kind == "breaker":
            out.append(breaker(x, y, label=label))
        elif kind == "filler":
            out.append(filler_plate(x, y))
        elif kind == "proud":
            out.append(filler_plate(x, y, proud=True))
        else:
            out.append(opening(x, y))
    return "".join(out)


LEFT_LABELS = ("1-3", "5-7", "9-11", "13", "15", "17", "19", "21", "23", "25")
LEFT = [("breaker", n) for n in LEFT_LABELS]
RIGHT_LABELS = ("2-4", "6-8", "10", "12", "14", "16")


def panel_scene(spare_kind, ring_colour):
    spares = (
        [("filler", ""), (spare_kind, ""), ("filler", ""), ("filler", "")]
        if spare_kind == "proud"
        else [(spare_kind, "")] * 4
    )
    right = [("breaker", lbl) for lbl in RIGHT_LABELS] + spares
    body = "".join(
        [
            enclosure(),
            text(
                450,
                130,
                "DISTRIBUTION PANEL — DEAD FRONT REMOVED",
                size=15,
                colour=MUTED,
                anchor="middle",
            ),
            breaker_column(200, 150, LEFT),
            breaker_column(510, 150, right),
            ring(496, 382, 208, 166, ring_colour),
        ]
    )
    return body


write("filler_good", panel_scene("filler", GOOD))
write("filler_missing", panel_scene("open", BAD))
write("filler_proud", panel_scene("proud", NEAR))


# ---------------------------------------------------------------- arc flash


def arc_label(x, y, w=300, h=150, faded=False, scale=1.0):
    ink = "#8A9099" if faded else "#1A1A1A"
    band = "#D9AE79" if faded else "#E8A33D"
    body_fill = "#EFEDE9" if faded else "#FFFFFF"
    lines = [
        ("Arc Flash and Shock Hazard", 17, "bold"),
        ("Appropriate PPE Required", 15, "normal"),
        ("1.8 cal/cm² at 18 in", 14, "normal"),
        ("PPE Category 1  ·  480V", 14, "normal"),
    ]
    out = [
        f"<g transform='translate({x},{y}) scale({scale})'>",
        f"<rect x='0' y='0' width='{w}' height='{h}' rx='4' fill='{body_fill}' "
        f"stroke='#777' stroke-width='2'/>",
        f"<rect x='0' y='0' width='{w}' height='38' rx='4' fill='{band}'/>",
        f"<rect x='0' y='30' width='{w}' height='8' fill='{band}'/>",
        text(w / 2, 27, "WARNING", size=22, colour="#1A1A1A", anchor="middle", weight="bold"),
    ]
    yy = 66
    for s, size, weight in lines:
        out.append(text(w / 2, yy, s, size=size, colour=ink, anchor="middle", weight=weight))
        yy += 24
    out.append("</g>")
    return "".join(out)


def door(extra="", ring_box=None):
    parts = [
        enclosure(inner=False),
        f"<rect x='160' y='95' width='580' height='485' rx='3' fill='#DEE2E6' "
        f"stroke='{METAL_MID}' stroke-width='2'/>",
        f"<rect x='690' y='300' width='16' height='76' rx='8' fill='{METAL_DARK}'/>",
        text(
            450,
            612,
            "PANEL DOOR — VIEWED FROM STANDING POSITION",
            size=15,
            colour=MUTED,
            anchor="middle",
        ),
        extra,
    ]
    if ring_box:
        parts.append(ring(*ring_box))
    return "".join(parts)


write("arcflash_good", door(arc_label(250, 190), (232, 172, 336, 186, GOOD)))
write(
    "arcflash_missing",
    door(
        "<rect x='250' y='190' width='300' height='150' rx='4' fill='#D5D9DE' "
        "stroke='#B3B8BE' stroke-width='2' stroke-dasharray='8 6'/>"
        + text(400, 270, "no label fitted", size=18, colour="#8A9099", anchor="middle"),
        (232, 172, 336, 186, BAD),
    ),
)
write(
    "arcflash_low",
    door(
        arc_label(330, 470, faded=True, scale=0.55)
        + text(
            450, 430, "label fitted low on the door, faded", size=17, colour=MUTED, anchor="middle"
        ),
        (320, 460, 182, 96, NEAR),
    ),
)


# ---------------------------------------------------------------- directory


def directory(typed=True):
    rows_left = [
        ("1", "CRAC-2A fan"),
        ("3", "CRAC-2B fan"),
        ("5", "Lighting 2-01"),
        ("7", "Lighting 2-02"),
        ("9", "Recept. 2-01"),
        ("11", "SPARE"),
    ]
    rows_right = [
        ("2", "UPS-2A bypass"),
        ("4", "Door controls"),
        ("6", "Lighting 2-03"),
        ("8", "SPARE"),
        ("10", "SPARE"),
        ("12", "SPARE"),
    ]
    out = [
        "<rect x='250' y='150' width='400' height='370' rx='4' fill='#FCFCFB' "
        "stroke='#9AA3AD' stroke-width='2'/>",
        "<rect x='250' y='150' width='400' height='44' fill='#E7E9EC'/>",
        text(
            450,
            180,
            "CIRCUIT DIRECTORY  ·  DP-2C",
            size=17,
            colour=INK,
            anchor="middle",
            weight="bold",
        ),
        "<line x1='450' y1='194' x2='450' y2='520' stroke='#C9CED4' stroke-width='1.5'/>",
    ]
    for col_x, rows in ((266, rows_left), (466, rows_right)):
        yy = 224
        for num, desc in rows:
            if typed:
                out.append(text(col_x, yy, num, size=14, colour=MUTED, mono=True))
                out.append(text(col_x + 34, yy, desc, size=14, colour=INK, mono=True))
            else:
                out.append(text(col_x, yy, num, size=14, colour=MUTED, mono=True))
                if desc != "SPARE":
                    out.append(
                        f"<path d='M{col_x + 34} {yy - 4} q 30 -9 58 0 t 54 -1' fill='none' "
                        f"stroke='#3B4A7A' stroke-width='2.4' stroke-linecap='round'/>"
                    )
            yy += 48
        if not typed:
            pass
    if not typed:
        out.append(
            text(
                450,
                540,
                "handwritten, spare ways left blank",
                size=15,
                colour=MUTED,
                anchor="middle",
            )
        )
    return "".join(out)


write("directory_good", door(directory(True), (238, 138, 424, 394, GOOD)))
write("directory_hand", door(directory(False), (238, 138, 424, 394, BAD)))


# ---------------------------------------------------------------- nameplate


def nameplate_scene(plate_tag, drawing_tag, ring_colour):
    return "".join(
        [
            enclosure(inner=False),
            f"<rect x='160' y='95' width='580' height='485' rx='3' fill='#DEE2E6' "
            f"stroke='{METAL_MID}' stroke-width='2'/>",
            # engraved nameplate
            "<rect x='300' y='180' width='300' height='92' rx='3' fill='#2B3440' "
            "stroke='#11161C' stroke-width='2'/>",
            text(
                450,
                222,
                plate_tag,
                size=34,
                colour="#F2F4F6",
                anchor="middle",
                weight="bold",
                mono=True,
            ),
            text(450, 252, "480/277V  3PH  4W", size=15, colour="#AEB6BF", anchor="middle"),
            # the drawing, held up beside it
            "<rect x='300' y='340' width='300' height='190' rx='3' fill='#FBFBF9' "
            "stroke='#9AA3AD' stroke-width='2'/>",
            text(320, 370, "E-201  ONE LINE (rev C)", size=13, colour=MUTED),
            "<line x1='320' y1='384' x2='580' y2='384' stroke='#C9CED4' stroke-width='1.5'/>",
            "<rect x='350' y='406' width='200' height='58' rx='2' fill='none' stroke='#3B4A7A' "
            "stroke-width='2'/>",
            text(450, 442, drawing_tag, size=26, colour="#1F2933", anchor="middle", mono=True),
            text(450, 500, "as scheduled", size=14, colour=MUTED, anchor="middle"),
            ring(284, 164, 332, 124, ring_colour),
            text(
                450,
                612,
                "NAMEPLATE AGAINST THE SCHEDULED TAG",
                size=15,
                colour=MUTED,
                anchor="middle",
            ),
        ]
    )


write("nameplate_good", nameplate_scene("SWBD-2A", "SWBD-2A", GOOD))
write("nameplate_wrong", nameplate_scene("SWBD-2B", "SWBD-2A", BAD))


# ---------------------------------------------------------------- ground bar


def ground_bar(conductors, ring_colour, note):
    """conductors: list of (lug_index, count, torque_stripe)."""
    out = [
        enclosure(),
        text(450, 132, "GROUND BAR — LOWER GUTTER", size=15, colour=MUTED, anchor="middle"),
        f"<rect x='220' y='300' width='460' height='54' rx='4' fill='{COPPER}' "
        f"stroke='#8A5328' stroke-width='2'/>",
    ]
    for i in range(6):
        x = 246 + i * 74
        out.append(f"<circle cx='{x + 18}' cy='327' r='9' fill='#7A4A24'/>")
    for lug, count, stripe in conductors:
        x = 246 + lug * 74
        for c in range(count):
            off = (c - (count - 1) / 2) * 16
            out.append(
                f"<path d='M{x + 18 + off} 327 C {x + 18 + off} 250, {x - 40 + off} 210, "
                f"{x - 60 + off} 150' fill='none' stroke='#2E7D32' stroke-width='11' "
                f"stroke-linecap='round'/>"
            )
        out.append(
            f"<rect x='{x + 2}' y='312' width='32' height='30' rx='3' fill='#9AA3AD' "
            f"stroke='#6E7680' stroke-width='1.5'/>"
        )
        if stripe:
            out.append(f"<rect x='{x + 14}' y='300' width='6' height='56' rx='2' fill='#D4341F'/>")
    out.append(ring(224, 232, 300, 140, ring_colour))
    out.append(text(450, 430, note, size=16, colour=MUTED, anchor="middle"))
    return "".join(out)


write(
    "ground_good",
    ground_bar(
        [(0, 1, True), (1, 1, True), (3, 1, True)],
        GOOD,
        "one conductor per lug, torque stripe applied",
    ),
)
write(
    "ground_untorqued",
    ground_bar(
        [(0, 1, False), (1, 1, False), (3, 1, True)],
        NEAR,
        "landed, but no torque stripe on two lugs",
    ),
)
write(
    "ground_double",
    ground_bar([(0, 2, True), (1, 1, True), (3, 1, True)], BAD, "two conductors under one lug"),
)

print("\n".join(sorted(p.name for p in OUT.iterdir())))
