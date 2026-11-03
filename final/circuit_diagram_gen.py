"""Generate a plain draw.io schematic (and a PNG preview) from one geometry."""
import sys
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFont

OUT_DRAWIO, OUT_PNG = sys.argv[1], sys.argv[2]

# ---------------------------------------------------------------- geometry
sections = [  # id, x, y, w, h, title
    ("s_ac",   4,  26, 100, 140, "AC Input"),
    ("s_sens", 115, 26, 145, 150, "Sensing"),
    ("s_div",  292, 46, 126, 72, "Divider"),
    ("s_mcu",  460, 112, 130, 728, "STM32 NUCLEO-F401RE (64 MHz)"),
    ("s_apfc", 640, 168, 490, 272, "APFC Capacitor Bank + Load"),
    ("s_ahf",  690, 446, 380, 70, "AHF Output"),
    ("s_hb",   962, 582, 206, 262, "H-Bridge"),
]

boxes = {}  # id -> (x, y, w, h, label)
def box(i, x, y, w, h, label):
    boxes[i] = (x, y, w, h, label)

# AC input + sensing
box("L",    12, 42, 80, 30, "Mains L<br>230 V 50 Hz")
box("N",    25, 125, 62, 30, "Mains N")
box("CS1", 125, 40, 125, 60, "ACS712-05B<br>grid current<br>series in L")
box("ZM",  125, 115, 125, 48, "ZMPT101B<br>voltage sensor<br>across L-N")
box("DIV", 300, 68, 110, 44, "10k series<br>20k to GND<br>ratio 0.667")

# STM32 pins
PX, PW, PH = 475, 100, 30
pins = [("PA0", 150, "PA0 (A0)<br>ADC1_IN0"), ("V5", 195, "5V"),
        ("PA1", 240, "PA1 (A1)<br>ADC1_IN1"), ("PB1", 285, "PB1<br>open-drain"),
        ("PB0", 350, "PB0<br>open-drain"), ("PB2", 415, "PB2<br>push-pull"),
        ("PA4", 530, "PA4 (A2)<br>ADC1_IN4"), ("V5B", 575, "5V"),
        ("PB6", 620, "PB6 (D10)<br>TIM4_CH1 80 kHz"), ("PB8", 665, "PB8 (D15)<br>TIM4_CH3 80 kHz"),
        ("V33", 710, "3V3"), ("GND", 755, "GND"), ("UART", 800, "PA2 / PA3<br>USART2 (USB)")]
for pid, cy, lab in pins:
    box(pid, PX, cy - PH // 2, PW, PH, lab)
pin_y = {p: cy for p, cy, _ in pins}

# APFC rows
PCC_X, NB_X = 665, 1105
LOAD_Y = 205
rows = {"K2": 259, "K1": 324, "K3": 395}
box("LOAD", 830, LOAD_Y - 17, 110, 34, "Load<br>charger / laptop / fan")
box("K2", 700, 247, 105, 50, "Relay K2<br>5 V active-LOW<br>10 A")
box("K1", 700, 312, 105, 50, "Relay K1<br>5 V active-LOW<br>10 A")
box("K3", 700, 383, 105, 42, "SSR K3<br>zero-cross<br>active-HIGH")
for k, n, c in (("K2", "2", "C2 10 uF<br>400 VAC<br>bleeder 220k 1 W"),
                ("K1", "1", "C1 2.5 uF<br>400 VAC<br>bleeder 820k 1 W"),
                ("K3", "3", "C3 20 uF<br>400 VAC<br>bleeder 100k 1 W")):
    y = rows[k]
    box("NTC" + n, 835, y - 15, 90, 30, "NTC 10D-9<br>recommended")
    box("C" + n, 955, y - 22, 120, 44, c)

# AHF output + H-bridge
AHF_Y = 480
box("RINJ", 700, AHF_Y - 15, 75, 30, "Resistor<br>10 W")
box("CS2",  815, AHF_Y - 22, 115, 44, "ACS712-05B<br>AHF current")
box("IND",  970, AHF_Y - 15, 85, 30, "Inductor<br>10 mH")
box("TB",   980, 600, 170, 175, "TB6612FNG<br><br>VCC 3.3 V<br>VM 12 V<br>STBY, PWMA = HIGH")
box("PSU", 1023, 800, 85, 34, "12 V DC<br>supply")
box("PC",   640, 783, 100, 34, "PC dashboard<br>115200 baud")

dots = {}  # junction dots
def dot(i, x, y):
    dots[i] = (x, y)
dot("jL", 108, 57)
dot("PCC", PCC_X, LOAD_Y)
dot("jP2", PCC_X, rows["K2"]); dot("jP1", PCC_X, rows["K1"]); dot("jP3", PCC_X, rows["K3"])
dot("jN0", NB_X, LOAD_Y)
dot("jN2", NB_X, rows["K2"]); dot("jN1", NB_X, rows["K1"]); dot("jN3", NB_X, rows["K3"])
dot("j5a", 290, 195)
dot("j5b", 605, 272)

# ---------------------------------------------------------------- wires
# (src, dst, [points incl. both ends], kind)  kind: mains | sig | pwr
wires = []
def w(s, d, pts, kind="sig"):
    wires.append((s, d, pts, kind))

# mains
w("L", "jL", [(92, 57), (108, 57)], "mains")
w("jL", "CS1", [(108, 57), (125, 57)], "mains")
w("jL", "ZM", [(108, 57), (108, 128), (125, 128)], "mains")
w("N", "ZM", [(87, 140), (125, 140)], "mains")
w("N", "jN0", [(25, 140), (8, 140), (8, 12), (NB_X, 12), (NB_X, LOAD_Y)], "mains")
w("CS1", "PCC", [(250, 57), (PCC_X, 57), (PCC_X, LOAD_Y)], "mains")
w("PCC", "LOAD", [(PCC_X, LOAD_Y), (830, LOAD_Y)], "mains")
w("LOAD", "jN0", [(940, LOAD_Y), (NB_X, LOAD_Y)], "mains")
w("PCC", "jP2", [(PCC_X, LOAD_Y), (PCC_X, rows["K2"])], "mains")
w("jP2", "jP1", [(PCC_X, rows["K2"]), (PCC_X, rows["K1"])], "mains")
w("jP1", "jP3", [(PCC_X, rows["K1"]), (PCC_X, rows["K3"])], "mains")
w("jN0", "jN2", [(NB_X, LOAD_Y), (NB_X, rows["K2"])], "mains")
w("jN2", "jN1", [(NB_X, rows["K2"]), (NB_X, rows["K1"])], "mains")
w("jN1", "jN3", [(NB_X, rows["K1"]), (NB_X, rows["K3"])], "mains")
for k, n, jp, jn in (("K2", "2", "jP2", "jN2"), ("K1", "1", "jP1", "jN1"), ("K3", "3", "jP3", "jN3")):
    y = rows[k]
    w(jp, k, [(PCC_X, y), (700, y)], "mains")
    w(k, "NTC" + n, [(805, y), (835, y)], "mains")
    w("NTC" + n, "C" + n, [(925, y), (955, y)], "mains")
    w("C" + n, jn, [(1075, y), (NB_X, y)], "mains")

# AHF power path
w("jP3", "RINJ", [(PCC_X, rows["K3"]), (PCC_X, AHF_Y), (700, AHF_Y)], "mains")
w("RINJ", "CS2", [(775, AHF_Y), (815, AHF_Y)], "mains")
w("CS2", "IND", [(930, AHF_Y), (970, AHF_Y)], "mains")
w("IND", "TB", [(1055, AHF_Y), (1080, AHF_Y), (1080, 600)], "mains")      # AO1
w("jN3", "TB", [(NB_X, rows["K3"]), (NB_X, 600)], "mains")                 # AO2
w("PSU", "TB", [(1065, 800), (1065, 775)], "sig")                          # VM

# sensor signals
w("CS1", "DIV", [(250, 90), (300, 90)])
w("DIV", "PA0", [(410, 90), (445, 90), (445, 150), (475, 150)])
w("ZM", "PA1", [(160, 163), (160, 240), (475, 240)])
w("CS1", "j5a", [(235, 100), (235, 108), (290, 108), (290, 195)], "pwr")
w("ZM", "j5a", [(210, 163), (210, 195), (290, 195)], "pwr")
w("j5a", "V5", [(290, 195), (475, 195)], "pwr")
w("PA4", "CS2", [(575, 530), (850, 530), (850, 502)])
w("V5B", "CS2", [(575, 575), (895, 575), (895, 502)], "pwr")

# relay control
w("PB1", "K2", [(575, 285), (700, 285)])
w("PB0", "K1", [(575, 350), (700, 350)])
w("PB2", "K3", [(575, 415), (700, 415)])
w("V5", "j5b", [(575, 195), (605, 195), (605, 272)], "pwr")
w("j5b", "K2", [(605, 272), (700, 272)], "pwr")
w("j5b", "K1", [(605, 272), (605, 337), (700, 337)], "pwr")

# H-bridge inputs, USB
for p in ("PB6", "PB8", "V33", "GND"):
    w(p, "TB", [(575, pin_y[p]), (980, pin_y[p])], "pwr" if p in ("V33", "GND") else "sig")
w("UART", "PC", [(575, 800), (640, 800)])

# small net / pin labels: (text, x, y, anchor)  anchor l = text starts at x
labels = [
    ("IP+", 112, 46, "l"), ("IP-", 254, 50, "l"), ("OUT", 254, 80, "l"), ("VCC", 205, 107, "l"),
    ("L", 112, 117, "l"), ("N", 112, 143, "l"), ("OUT", 164, 168, "l"), ("VCC", 214, 168, "l"),
    ("PCC", PCC_X - 30, LOAD_Y - 14, "l"), ("N", NB_X + 6, LOAD_Y - 14, "l"),
    ("IN", 678, 278, "l"), ("VCC", 672, 265, "l"), ("IN", 678, 343, "l"), ("VCC", 672, 330, "l"),
    ("DC+", 674, 408, "l"),
    ("OUT", 822, 512, "l"), ("VCC", 899, 512, "l"),
    ("AO1", 1084, 590, "l"), ("AO2", 1109, 590, "l"),
    ("AIN1", 940, 612, "l"), ("AIN2", 940, 657, "l"), ("VCC", 944, 702, "l"), ("GND", 944, 747, "l"),
    ("VM", 1069, 785, "l"), ("USB", 600, 792, "l"),
]

# ---------------------------------------------------------------- draw.io
def cell_geom(i):
    if i in boxes:
        x, y, ww, hh, _ = boxes[i]
        return x, y, ww, hh
    x, y = dots[i]
    return x - 3.5, y - 3.5, 7, 7

xml = []
def add(s):
    xml.append(s)

add('<mxfile host="app.diagrams.net"><diagram name="Schematic" id="sch">')
add('<mxGraphModel dx="1400" dy="900" grid="1" gridSize="5" guides="1" tooltips="1" connect="1" '
    'arrows="0" fold="1" page="1" pageScale="1" pageWidth="1200" pageHeight="900" math="0" shadow="0">')
add('<root><mxCell id="0"/><mxCell id="1" parent="0"/>')
for sid, x, y, ww, hh, t in sections:
    add(f'<mxCell id="{sid}" value="{escape(t)}" style="rounded=0;whiteSpace=wrap;html=1;fillColor=none;'
        f'strokeColor=#999999;verticalAlign=top;align=left;spacingLeft=5;spacingTop=-2;fontSize=10;'
        f'fontColor=#444444;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{ww}" height="{hh}" as="geometry"/></mxCell>')
for bid, (x, y, ww, hh, lab) in boxes.items():
    add(f'<mxCell id="{bid}" value="{escape(lab)}" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;'
        f'strokeColor=#000000;fontSize=10;fontColor=#000000;" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{ww}" height="{hh}" as="geometry"/></mxCell>')
for did, (x, y) in dots.items():
    add(f'<mxCell id="{did}" value="" style="ellipse;whiteSpace=wrap;html=1;fillColor=#000000;strokeColor=#000000;'
        f'aspect=fixed;" vertex="1" parent="1"><mxGeometry x="{x-3.5}" y="{y-3.5}" width="7" height="7" as="geometry"/></mxCell>')
for n, (s, d, pts, kind) in enumerate(wires):
    sx, sy, sw, sh = cell_geom(s)
    dx_, dy_, dw, dh = cell_geom(d)
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    ex, ey = (x0 - sx) / sw, (y0 - sy) / sh
    nx, ny = (x1 - dx_) / dw, (y1 - dy_) / dh
    width = 2 if kind == "mains" else 1
    dash = "dashed=1;dashPattern=4 3;" if kind == "pwr" else ""
    style = (f"edgeStyle=none;rounded=0;html=1;endArrow=none;startArrow=none;strokeColor=#000000;"
             f"strokeWidth={width};{dash}exitX={ex:.4f};exitY={ey:.4f};exitDx=0;exitDy=0;exitPerimeter=0;"
             f"entryX={nx:.4f};entryY={ny:.4f};entryDx=0;entryDy=0;entryPerimeter=0;")
    mid = "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in pts[1:-1])
    arr = f'<Array as="points">{mid}</Array>' if mid else ""
    add(f'<mxCell id="w{n}" style="{style}" edge="1" parent="1" source="{s}" target="{d}">'
        f'<mxGeometry relative="1" as="geometry">{arr}</mxGeometry></mxCell>')
for n, (t, x, y, _a) in enumerate(labels):
    add(f'<mxCell id="t{n}" value="{escape(t)}" style="text;html=1;align=left;verticalAlign=middle;'
        f'fontSize=9;fontColor=#000000;spacing=0;" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y-6}" width="{max(14, 6*len(t))}" height="12" as="geometry"/></mxCell>')
add('</root></mxGraphModel></diagram></mxfile>')
open(OUT_DRAWIO, "w").write("".join(xml))

# ---------------------------------------------------------------- preview
S = 2
W_, H_ = 1180, 860
img = Image.new("RGB", (W_ * S, H_ * S), "white")
g = ImageDraw.Draw(img)
fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
f10, f9, f8 = (ImageFont.truetype(fp, z * S) for z in (9, 8, 7))
def P(x, y):
    return (x * S, y * S)
for _sid, x, y, ww, hh, t in sections:
    g.rectangle([P(x, y), P(x + ww, y + hh)], outline=(153, 153, 153), width=S)
    g.text(P(x + 5, y + 3), t, fill=(68, 68, 68), font=f9)
for s, d, pts, kind in wires:
    width = 2 * S if kind == "mains" else S
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if kind == "pwr":
            L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            k = 0.0
            while k < L:
                e = min(k + 4, L)
                g.line([P(ax + (bx - ax) * k / L, ay + (by - ay) * k / L),
                        P(ax + (bx - ax) * e / L, ay + (by - ay) * e / L)], fill="black", width=width)
                k += 7
        else:
            g.line([P(ax, ay), P(bx, by)], fill="black", width=width)
for bid, (x, y, ww, hh, lab) in boxes.items():
    g.rectangle([P(x, y), P(x + ww, y + hh)], fill="white", outline="black", width=S)
    lines = lab.split("<br>")
    lh = 11
    y0 = y + hh / 2 - lh * len(lines) / 2
    for i, ln in enumerate(lines):
        tw = g.textlength(ln, font=f10) / S
        g.text(P(x + ww / 2 - tw / 2, y0 + i * lh), ln, fill="black", font=f10)
for _d, (x, y) in dots.items():
    g.ellipse([P(x - 3.5, y - 3.5), P(x + 3.5, y + 3.5)], fill="black")
for t, x, y, _a in labels:
    g.text(P(x, y - 5), t, fill="black", font=f8)
img.save(OUT_PNG)
print("ok", len(boxes), "boxes", len(wires), "wires", len(dots), "dots")
