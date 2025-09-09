# SPI 4-or-8 by CS — Saleae High-Level Analyzer

**HLA** extension for \[Saleae Logic 2] that works **on top of the SPI LLA** with *word size = 4 bits* and, **for each Chip Select (CS) cycle**, automatically decides how to interpret the data:

* If there is **a single nibble (4 bits)** → it is treated as a **4-bit command** (`nibble_ok`).
* If there are **multiple nibbles** → they are **paired two by two** and emitted as **8-bit bytes** (`byte_ok`).
* If the number of nibbles is **odd > 1**, in addition to emitting the expected frames, an **anomaly** is flagged with `error`.

In addition, the HLA **highlights anomalous events** within the CS cycle (see below).

---

## Why it’s useful

Many “mixed” SPI devices use **short 4-bit commands** followed by **8-bit payloads** (or vice versa). Setting the SPI LLA to 4 bits and delegating reassembly to the HLA makes interpretation easier and reduces guesswork.

---

## Requirements

* **Logic 2** (with HLA extensions enabled).
* **SPI Analyzer** active **before** this HLA.
* **SPI LLA** configured with:

  * **Word size: 4 bits**
  * Correct CPOL/CPHA
  * Correct bit order (MSB/LSB first)

> The HLA works both with LLAs that emit CS `enable/disable` and without them (in the latter case it uses an “implicit cycle” when data arrives).

---

## Included files

* `HighLevelAnalyzer.py` — HLA implementation (no settings, for maximum compatibility).
* `extension.json` — HLA extension structure.
* `README.md` — This file.

---

## Installation

1. Open **Logic 2 → Extensions**.
2. **Load Extension** 
3. Select the `extension.json` file.
4. Add the “SPI 4-or-8 by CS” HLA on top of the SPI LLA in a capture.

---

## Usage

1. Set the **SPI LLA to 4 bits**.
2. Run a capture.
3. In the “Decoded Protocol” table you will see:

   * `nibble_ok` for **1 nibble** in the CS cycle.
   * `byte_ok` for **bytes** reconstructed from pairs of nibbles.
   * `error` for any **anomalies** (see below).

### Types of emitted frames

| Type        | Fields                    | Meaning                                                                                 |
| ----------- | ------------------------- | --------------------------------------------------------------------------------------- |
| `packet`    | `dir: "CS"`, `info`       | **Enable/disable** marker of CS.                                                        |
| `nibble_ok` | `dir: "MOSI/MISO"`, `val` | **4-bit command** or valid **residual nibble**.                                         |
| `byte_ok`   | `dir: "MOSI/MISO"`, `val` | **8-bit byte** reconstructed from **2 consecutive nibbles** (order: *high\_then\_low*). |
| `error`     | `msg`                     | **Anomaly** detected (see list below).                                                  |

> Merge order is **high\_then\_low** (first nibble = high, second = low).

---

## Detected anomalies (`error`)

* **No data** in the CS cycle → interpreted as **< 4 clocks** (no nibble on MOSI/MISO).
* **Number of clocks not a multiple of 8** *(except the valid “only 4 bits” case)*, computed as `max(nibble_MOSI, nibble_MISO) × 4`.
* **Odd nibble count (> 1)** on **MOSI** or **MISO** (e.g., 12 total bits → 3 nibbles).

Errors are shown **at the start** of the CS cycle, followed by the decoded data.

---

## How it works (briefly)

* During the LLA `result` frames, the HLA **accumulates** the nibbles (with their timestamps).
* At the end of CS (`disable`), it builds an ordered list of “items” (byte/nibble/error).
* **Only at flush time** are monotonic timestamps evenly distributed between `cs_start` and `cs_end`, avoiding errors like “begin must start after the previous frame”.

---

## Troubleshooting

* **“ValidationError: Missing setting …”**
  This version **does not use settings**, so it should not appear. If you’re using variants with settings, remove the HLA from the capture, hit **Reload**, and re-add it.
* **“Invalid begin time … begin must start after the previous frame”**
  Make sure you’re using **this version** (time monotonicity handled at flush). If you mix versions, reload the extension.
* **Not seeing `enable/disable`** in the timeline?
  The HLA still works, creating an implicit cycle when data arrives. For precise boundaries, enable CS usage in the SPI LLA.
* **Payload reversed (high/low nibble)**
  This version fixes the order to *high\_then\_low*. If your device does the opposite, request/implement the *low\_then\_high* variant.

---

## Roadmap (optional)

* **Strict mode**: in case of odd nibble count > 1, emit only `error` (without residual `nibble_ok`).
* **Settings**: merge order; enable/disable MOSI/MISO; timeout to close implicit CS cycles.
* **Per-CS summary**: counters, checksums, etc.

---

## Contributing

* PRs/issues welcome. Please add capture examples (MOSI/MISO, CPOL/CPHA, bit order).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.



