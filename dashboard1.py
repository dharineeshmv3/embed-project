#!/usr/bin/env python3
"""
AC Power Monitor — Real-time Dashboard
=======================================
Reads structured CSV from the STM32 AC meter (DASH_OUTPUT=1) and displays
live waveforms, power metrics, harmonic spectrum, and a PF gauge.

Usage:
    python dashboard.py COM3              # Windows
    python dashboard.py /dev/ttyACM0      # Linux
    python dashboard.py --demo            # run with simulated data

Requirements:
    pip install pyserial matplotlib numpy
"""

import sys
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Wedge
import matplotlib.patheffects as pe

# ─────────────────── Configuration ───────────────────
SERIAL_PORT = "COM3"                # overridden by argv[1]
BAUD_RATE   = 115200
CYC         = 200                   # samples per mains cycle (must match STM32)
FREQ_HZ     = 50                    # mains frequency
UPDATE_MS   = 400                   # dashboard refresh interval (ms)
DEMO_MODE   = False
# ─────────────────────────────────────────────────────


# ─────────────────── Shared live data ────────────────
class LiveData:
    """Thread-safe container for the most recent frame from the STM32."""
    def __init__(self):
        self.lock     = threading.Lock()
        self.voltage  = np.zeros(CYC)
        self.current  = np.zeros(CYC)
        self.vrms     = 0.0
        self.irms     = 0.0
        self.p        = 0.0
        self.s        = 0.0
        self.q        = 0.0
        self.pf       = 0.0
        self.thd_v    = 0.0
        self.thd_i    = 0.0
        self.crest    = 0.0
        self.vpk      = 0.0
        self.ipk      = 0.0
        self.harm_i   = np.zeros(14)   # H2..H15 (% of fundamental)
        self.harm_v   = np.zeros(14)
        self.raw_vclip = 0
        self.raw_iclip = 0
        self.updated  = False
        self.connected = False

data = LiveData()


# ─────────────────── Serial reader thread ────────────
def serial_reader():
    """Parse structured $-lines from STM32 UART."""
    import serial
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        with data.lock:
            data.connected = True
        print(f"[serial] connected to {SERIAL_PORT}")
    except Exception as e:
        print(f"[serial] FAILED: {e}")
        return

    # Temp buffers for the frame being assembled
    tv = np.zeros(CYC)
    tc = np.zeros(CYC)

    while True:
        try:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            if not line or line[0] != "$":
                continue   # skip non-structured lines (calibration msgs etc.)

            parts = line.split(",")
            tag   = parts[0]

            if tag == "$W" and len(parts) >= CYC + 2:
                vals = np.array([float(x) for x in parts[2:CYC + 2]])
                if parts[1] == "V":
                    tv[:] = vals
                elif parts[1] == "I":
                    tc[:] = vals

            elif tag == "$M" and len(parts) >= 12:
                with data.lock:
                    data.vrms   = float(parts[1])
                    data.irms   = float(parts[2])
                    data.p      = float(parts[3])
                    data.s      = float(parts[4])
                    data.q      = float(parts[5])
                    data.pf     = float(parts[6])
                    data.thd_v  = float(parts[7])
                    data.thd_i  = float(parts[8])
                    data.crest  = float(parts[9])
                    data.vpk    = float(parts[10])
                    data.ipk    = float(parts[11])

            elif tag == "$H" and len(parts) >= 16:
                vals = np.array([float(x) for x in parts[2:16]])
                with data.lock:
                    if parts[1] == "I":
                        data.harm_i[:] = vals
                    elif parts[1] == "V":
                        data.harm_v[:] = vals

            elif tag == "$R" and len(parts) >= 9:
                with data.lock:
                    data.raw_vclip = int(parts[4])
                    data.raw_iclip = int(parts[8])

            elif tag == "$E":
                # Frame complete — commit waveforms atomically
                with data.lock:
                    data.voltage[:] = tv
                    data.current[:] = tc
                    data.updated = True

        except (ValueError, IndexError):
            continue
        except Exception:
            break

    ser.close()
    with data.lock:
        data.connected = False
    print("[serial] disconnected")


# ─────────────────── Demo data generator ─────────────
def demo_thread():
    """Generate fake but realistic SMPS-like data for testing the UI."""
    t = np.linspace(0, 2 * np.pi, CYC, endpoint=False)
    with data.lock:
        data.connected = True
    while True:
        phase_shift = 0.25 + 0.05 * np.sin(time.time() * 0.3)
        # Voltage: nearly sinusoidal with mild clipping
        v = 340 * np.sin(t)
        v = np.clip(v, -330, 330)
        # Current: SMPS-like peaky waveform
        fund = 0.55 * np.sin(t - phase_shift)
        i = fund + 0.22 * np.sin(3 * (t - phase_shift))
        i += 0.08 * np.sin(5 * (t - phase_shift))
        i += 0.06 * np.sin(7 * (t - phase_shift))
        i += 0.05 * np.sin(9 * (t - phase_shift))
        i += 0.04 * np.sin(11 * (t - phase_shift))

        vrms = np.sqrt(np.mean(v**2))
        irms = np.sqrt(np.mean(i**2))
        p = np.mean(v * i)
        s = vrms * irms
        q = np.sqrt(max(s**2 - p**2, 0))
        pf = p / s if s > 0 else 0

        # Compute harmonics via FFT
        fft_i = np.fft.rfft(i)
        mag_i = 2.0 * np.abs(fft_i) / CYC
        h1_i = mag_i[1] if len(mag_i) > 1 else 1e-9
        harm_i_pct = np.zeros(14)
        for h in range(2, 16):
            if h < len(mag_i):
                harm_i_pct[h - 2] = 100.0 * mag_i[h] / max(h1_i, 1e-9)

        fft_v = np.fft.rfft(v)
        mag_v = 2.0 * np.abs(fft_v) / CYC
        h1_v = mag_v[1] if len(mag_v) > 1 else 1e-9
        harm_v_pct = np.zeros(14)
        for h in range(2, 16):
            if h < len(mag_v):
                harm_v_pct[h - 2] = 100.0 * mag_v[h] / max(h1_v, 1e-9)

        thd_i_val = np.sqrt(np.sum(harm_i_pct**2)) / 100.0 * 100
        thd_v_val = np.sqrt(np.sum(harm_v_pct**2)) / 100.0 * 100

        with data.lock:
            data.voltage[:] = v
            data.current[:] = i
            data.vrms = vrms
            data.irms = irms
            data.p = p
            data.s = s
            data.q = q
            data.pf = pf
            data.thd_v = thd_v_val
            data.thd_i = thd_i_val
            data.crest = np.max(np.abs(i)) / max(irms, 1e-9)
            data.vpk = np.max(np.abs(v))
            data.ipk = np.max(np.abs(i))
            data.harm_i[:] = harm_i_pct
            data.harm_v[:] = harm_v_pct
            data.raw_vclip = 0
            data.raw_iclip = 0
            data.updated = True

        time.sleep(0.5)


# ─────────────────── PF Gauge drawing ────────────────
def draw_pf_gauge(ax, pf_val):
    """Draw a semicircular power-factor gauge on the given axes."""
    ax.clear()
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.25, 1.35)
    ax.set_aspect("equal")
    ax.axis("off")

    # Colour zones (angles in degrees: 0° = right, 180° = left)
    zones = [
        (0,   54,  "#e74c3c"),   # PF 0.00–0.30  red
        (54,  108, "#f39c12"),   # PF 0.30–0.60  orange
        (108, 144, "#f1c40f"),   # PF 0.60–0.80  yellow
        (144, 162, "#2ecc71"),   # PF 0.80–0.90  light green
        (162, 180, "#27ae60"),   # PF 0.90–1.00  green
    ]
    for a1, a2, col in zones:
        w = Wedge((0, 0), 1.0, a1, a2, width=0.22, fc=col, ec="none", alpha=0.85)
        ax.add_patch(w)

    # Tick marks and labels
    for pf_tick in [0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]:
        angle = np.radians(180 * pf_tick)
        x0, y0 = np.cos(angle), np.sin(angle)
        ax.plot([0.80 * x0, 0.78 * x0], [0.80 * y0, 0.78 * y0],
                color="white", lw=1.2)
        ax.text(0.68 * x0, 0.68 * y0, f"{pf_tick:.1f}" if pf_tick < 1 else "1.0",
                ha="center", va="center", fontsize=7, color="white")

    # Needle
    angle = np.radians(180 * abs(pf_val))
    nx, ny = np.cos(angle), np.sin(angle)
    ax.plot([0, 0.88 * nx], [0, 0.88 * ny], color="white", lw=2.5,
            solid_capstyle="round",
            path_effects=[pe.Stroke(linewidth=4, foreground="#1a1a2e"), pe.Normal()])
    ax.plot(0, 0, "o", color="white", ms=6, zorder=5)

    # Central value
    ax.text(0, -0.12, f"PF = {pf_val:+.3f}",
            ha="center", va="center", fontsize=16, fontweight="bold",
            color="white",
            path_effects=[pe.withStroke(linewidth=3, foreground="#1a1a2e")])


# ─────────────────── Dashboard setup ─────────────────
BG       = "#0f0f1a"
PANEL_BG = "#16172b"
CYAN     = "#00d4ff"
ORANGE   = "#ff6b35"
GREEN    = "#2ecc71"
YELLOW   = "#f1c40f"
RED      = "#e74c3c"
GREY     = "#555577"
WHITE    = "#e0e0f0"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor":   PANEL_BG,
    "axes.edgecolor":   "#333355",
    "axes.labelcolor":  WHITE,
    "xtick.color":      GREY,
    "ytick.color":      GREY,
    "text.color":       WHITE,
    "grid.color":       "#222244",
    "grid.alpha":       0.5,
    "font.family":      "monospace",
    "font.size":        9,
})

fig = plt.figure(figsize=(15, 9))
fig.canvas.manager.set_window_title("AC Power Monitor")

# GridSpec: 3 rows, 2 cols
#   row 0: voltage waveform | current waveform + fundamental
#   row 1: PF gauge + metrics | harmonic bar chart
#   row 2: metrics strip (spanning full width)
import matplotlib.gridspec as gridspec
gs = gridspec.GridSpec(3, 2, height_ratios=[3, 3, 1.2],
                       hspace=0.35, wspace=0.25,
                       left=0.06, right=0.97, top=0.93, bottom=0.05)

ax_v    = fig.add_subplot(gs[0, 0])    # voltage waveform
ax_i    = fig.add_subplot(gs[0, 1])    # current waveform
ax_pf   = fig.add_subplot(gs[1, 0])    # PF gauge
ax_harm = fig.add_subplot(gs[1, 1])    # harmonic spectrum
ax_info = fig.add_subplot(gs[2, :])    # metrics strip

# Time axis for one cycle
t_ms = np.linspace(0, 1000.0 / FREQ_HZ, CYC, endpoint=False)

# ---- Voltage waveform ----
ax_v.set_title("AC Voltage Waveform", fontsize=11, color=CYAN, pad=8)
ax_v.set_xlabel("Time (ms)")
ax_v.set_ylabel("Voltage (V)")
ax_v.set_xlim(0, t_ms[-1])
ax_v.grid(True, ls="--", lw=0.5)
line_v, = ax_v.plot(t_ms, np.zeros(CYC), color=CYAN, lw=1.5, label="V(t)")
ax_v.axhline(0, color=GREY, lw=0.5)

# ---- Current waveform ----
ax_i.set_title("AC Current Waveform", fontsize=11, color=ORANGE, pad=8)
ax_i.set_xlabel("Time (ms)")
ax_i.set_ylabel("Current (A)")
ax_i.set_xlim(0, t_ms[-1])
ax_i.grid(True, ls="--", lw=0.5)
line_i, = ax_i.plot(t_ms, np.zeros(CYC), color=ORANGE, lw=1.5, label="I(t) actual")
line_i_fund, = ax_i.plot(t_ms, np.zeros(CYC), color=GREEN, lw=1.2,
                          ls="--", alpha=0.7, label="Fundamental")
ax_i.axhline(0, color=GREY, lw=0.5)
ax_i.legend(loc="upper right", fontsize=8, framealpha=0.3)

# ---- Harmonic spectrum ----
ax_harm.set_title("Harmonic Spectrum (% of Fundamental)", fontsize=11, color=YELLOW, pad=8)
harm_labels = [f"H{h}" for h in range(2, 16)]
x_harm = np.arange(14)
bar_width = 0.35
bars_i = ax_harm.bar(x_harm - bar_width/2, np.zeros(14), bar_width,
                     color=ORANGE, alpha=0.85, label="Current")
bars_v = ax_harm.bar(x_harm + bar_width/2, np.zeros(14), bar_width,
                     color=CYAN, alpha=0.60, label="Voltage")
ax_harm.set_xticks(x_harm)
ax_harm.set_xticklabels(harm_labels, fontsize=7)
ax_harm.set_ylabel("Amplitude (%)")
ax_harm.set_ylim(0, 50)
ax_harm.legend(loc="upper right", fontsize=8, framealpha=0.3)
ax_harm.grid(True, axis="y", ls="--", lw=0.5)

# ---- Info strip ----
ax_info.axis("off")
info_text = ax_info.text(0.5, 0.5, "Waiting for data...",
                         ha="center", va="center", fontsize=12,
                         color=WHITE, fontfamily="monospace",
                         transform=ax_info.transAxes)

# Figure title
fig.suptitle("STM32 AC Power Monitor", fontsize=15, fontweight="bold",
             color=WHITE, y=0.98)


# ─────────────────── Animation update ────────────────
def update(frame):
    with data.lock:
        if not data.updated:
            return (line_v, line_i, line_i_fund, info_text)

        v   = data.voltage.copy()
        i   = data.current.copy()
        vrms_val  = data.vrms
        irms_val  = data.irms
        p_val     = data.p
        s_val     = data.s
        q_val     = data.q
        pf_val    = data.pf
        thd_v_val = data.thd_v
        thd_i_val = data.thd_i
        crest_val = data.crest
        vpk_val   = data.vpk
        ipk_val   = data.ipk
        hi        = data.harm_i.copy()
        hv        = data.harm_v.copy()
        vclip     = data.raw_vclip
        iclip     = data.raw_iclip
        data.updated = False

    # ---- Update voltage waveform ----
    line_v.set_ydata(v)
    v_lim = max(abs(v).max() * 1.15, 10)
    ax_v.set_ylim(-v_lim, v_lim)

    # ---- Update current waveform + reconstruct fundamental ----
    line_i.set_ydata(i)
    i_lim = max(abs(i).max() * 1.25, 0.1)
    ax_i.set_ylim(-i_lim, i_lim)

    # Reconstruct the fundamental via DFT bin 1
    # (one mains cycle = CYC samples, so fundamental = bin 1)
    if irms_val > 0:
        fft_i = np.fft.rfft(i)
        fund_fft = np.zeros_like(fft_i)
        fund_fft[1] = fft_i[1]          # bin 1 = fundamental only
        fundamental = np.fft.irfft(fund_fft, n=CYC)
        line_i_fund.set_ydata(fundamental)
    else:
        line_i_fund.set_ydata(np.zeros(CYC))

    # ---- Update PF gauge ----
    draw_pf_gauge(ax_pf, pf_val)

    # ---- Update harmonic bars ----
    for rect, h in zip(bars_i, hi):
        rect.set_height(h)
    for rect, h in zip(bars_v, hv):
        rect.set_height(h)
    harm_max = max(hi.max(), hv.max(), 5) * 1.2
    ax_harm.set_ylim(0, harm_max)

    # ---- Update info strip ----
    clip_warn = ""
    if vclip > 5:
        clip_warn += f"  ⚠ V CLIP={vclip}"
    if iclip > 5:
        clip_warn += f"  ⚠ I CLIP={iclip}"

    info_str = (
        f"Vrms={vrms_val:7.1f} V   Irms={irms_val:6.3f} A   "
        f"P={p_val:7.1f} W   S={s_val:7.1f} VA   Q={q_val:7.1f} var   "
        f"PF={pf_val:+.3f}   "
        f"THDv={thd_v_val:5.1f}%   THDi={thd_i_val:5.1f}%   "
        f"Crest={crest_val:.2f}"
        f"{clip_warn}"
    )
    info_text.set_text(info_str)

    return (line_v, line_i, line_i_fund, info_text)


# Need this global so the fundamental reconstruction knows the bin
MAINS_CYCLES = 5   # must match STM32 MAINS_CYCLES


# ─────────────────── Main ────────────────────────────
def main():
    global SERIAL_PORT, DEMO_MODE

    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            DEMO_MODE = True
        else:
            SERIAL_PORT = sys.argv[1]

    # Start data source thread
    if DEMO_MODE:
        print("[dashboard] running in DEMO mode")
        t = threading.Thread(target=demo_thread, daemon=True)
    else:
        print(f"[dashboard] connecting to {SERIAL_PORT} @ {BAUD_RATE}")
        t = threading.Thread(target=serial_reader, daemon=True)
    t.start()

    # Start animation
    ani = FuncAnimation(fig, update, interval=UPDATE_MS, blit=False, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()
