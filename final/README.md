# Dual-Stage Grid Power Quality System — final version

| File | What it is |
|---|---|
| `main.c` | STM32F401RE firmware (CMSIS only): APFC capacitor bank + Active Harmonic Filter (TB6612FNG) |
| `dashboard.py` | Real-time PC dashboard: shared V/I waveforms, *Power Factor Correction* and *Harmonic Mitigation* tabs |
| `requirements.txt` | Python libraries for the dashboard and how to install them |
| `CAPACITOR_RELAY_GUIDELINES.txt` | **Read before using the capacitor bank**: switching rules and safety |

## Run the dashboard

```
python -m pip install -r requirements.txt
python dashboard.py --port COM6
```

`python dashboard.py --demo` runs it without the board.

## Before flashing `main.c`

| Setting | What to check |
|---|---|
| `ACS_DIV_I`, `ACS_DIV_A` | Divider ratio between each ACS712 OUT and its ADC pin (`R_bottom / (R_top + R_bottom)`, `1.0` if wired directly). Sensor I uses 10 kΩ + 20 kΩ = `0.6667`. |
| `A_SIGN` | Sensor A must read +ve when the AHF pushes current in the direction sensor I reads +ve. If grid THD **rises** when AHF is ACTIVE, flip it. |
| `AHF_SENSE_GRID` | `0` if sensor I measures the load current before the injection point, `1` if it measures the already-compensated grid current. |
| `AHF_INJ_RATIO` | Coupling-transformer ratio; `1` for direct injection. |
| `AHF_VDC`, `AHF_L_H`, `AHF_R_OHM` | Only a starting guess; the firmware measures the real values. |
| `RELAY_SSR_MASK` | Bit set = that pin drives an active-HIGH SSR (default `0x4`: PB2). Clear = 5 V active-LOW relay module. |
| `PF_TARGET` | 0.99: AUTO switches a step in whenever it brings PF closer. |
| `RELAY_MIN_ON_MS`, `CAP_RECLOSE_MS` | 5 s minimum ON and OFF time for each capacitor. |
| `A_LPF_HZ`, `A_DEADBAND` | Butterworth low-pass and noise floor for the AHF current sensor (ACS712 #2). |
| `RELAY_SYNC`, `RELAY_T_OP_MS`, `RELAY_T_REL_MS` | Relay modules open just before and close at the voltage peak, so a capacitor without a bleeder resistor is reconnected with ~0 V across the contacts. |

## Capacitor bank safety

* Fit a **bleeder resistor across every capacitor**: 2.5 µF → 820 kΩ, 10 µF → 220 kΩ, 20 µF → 100 kΩ (1 W, ≥ 400 V rated). Without it the capacitor stays charged for minutes and the relay closes onto up to 650 V, which welds its contacts.
* Prefer **zero-cross SSRs** for switching capacitors; mechanical relay modules (10 A resistive rating) are not rated for capacitor inrush.
* Use AC film capacitors (motor-run / PFC type) rated **≥ 400 VAC**, never electrolytics.
