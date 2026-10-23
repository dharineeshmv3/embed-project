# Dual-Stage Grid Power Quality System — final version

| File | What it is |
|---|---|
| `main.c` | STM32F401RE firmware (CMSIS only): APFC capacitor bank + Active Harmonic Filter (TB6612FNG) |
| `dashboard.py` | Real-time PC dashboard: shared V/I waveforms, *Power Factor Correction* and *Harmonic Mitigation* tabs |
| `requirements.txt` | Python libraries for the dashboard and how to install them |

## Run the dashboard

```
python -m pip install -r requirements.txt
python dashboard.py --port COM6
```

`python dashboard.py --demo` runs it without the board.

## Before flashing `main.c`

| Setting | What to check |
|---|---|
| `A_SIGN` | Sensor A must read +ve when the AHF pushes current in the direction sensor I reads +ve. If grid THD **rises** when AHF is ACTIVE, flip it. |
| `AHF_SENSE_GRID` | `0` if sensor I measures the load current before the injection point, `1` if it measures the already-compensated grid current. |
| `AHF_INJ_RATIO` | Coupling-transformer ratio; `1` for direct injection. |
| `AHF_VDC`, `AHF_L_H`, `AHF_R_OHM` | Only a starting guess; the firmware measures the real values. |
