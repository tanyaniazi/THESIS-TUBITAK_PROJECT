<<<<<<< HEAD
# TEMAS_TUBITAK_PROJECT
This repository hold codes of my research during my master's degree, which was part of a TUBITAK project.
=======
# Student Contact Network Analysis

## Overview

This repository contains the full data-processing and network-analysis pipeline for a TÜBİTAK-funded research project studying face-to-face contact patterns among primary school students. RFID proximity sensors were deployed across three grade levels (5th, 6th, and 7th) in a Turkish primary school during March 2023 to capture pairwise student interactions at high temporal resolution. The resulting contact networks are analysed for structural properties including density, clustering, modularity, degree distributions, and community structure.


## Repository Structure

```
TUBITAK-RELATED/
├── README.md
├── requirements.txt
├── .gitignore
│
├── altogether_anls.ipynb       # Main analysis (run this)
├── utils.py                    # Helper functions
│
├── data/                       # Raw input CSVs
│   ├── all1.csv
│   ├── all2.csv
│   ├── tagid-mifareid.csv
│   ├── 5tagid.csv
│   ├── 6tagid.csv
│   └── 7tagid.csv
│
├── figures/                    # Generated outputs
│
└── docs/                       # Reference documentation
    ├── data_dictionary.md
    └── variable_dictionary.md

```


## Data Description

### 1. Raw Contact Logs — `all1.csv`, `all2.csv`

These files contain the raw proximity events recorded by the RFID hardware. Each row represents a single detected contact between two sensors.

| Column | Type | Description |
|--------|------|-------------|
| `tagid` | int | Tag ID of the first sensor in the contact pair |
| `touched_tagid` | int | Tag ID of the second sensor in the contact pair |
| `min_distance` | float | Closest proximity recorded during the interaction (cm) |
| `duration` | int | Contact duration in seconds |
| `begin_time` | int | Start time as Unix timestamp in **milliseconds** |
| `end_time` | int | End time as Unix timestamp in **milliseconds** |
| `upload_time` | int | Time the data was uploaded from the sensor (ms) |
| `baseid` | int | Base station ID that received the data |

**Delimiter:** comma (`,`)

> **Important:** The RFID cards are not wiped between deployments. These files contain residual contact data from previous deployments spanning November 2022 – April 2023 (19 distinct dates total). Only three dates correspond to the target measurement days. The pipeline filters to the correct deployment date for each grade.

**Combined total:** 633,127 contact records (after dropping incomplete rows).

### 2. RFID Card Mapping — `tagid-mifareid.csv`

Maps the short internal Tag IDs used by the contact logs to the longer Mifare hardware IDs used by the class rosters.

| Column | Type | Description |
|--------|------|-------------|
| `Tag ID` | int | Short internal reference ID (used in contact logs) |
| `Mifare ID` | int | Long hardware identifier (used in class rosters) |
| `Type` | str | Physical form factor (e.g., `Card`) |

**Delimiter:** comma (`,`) · **Records:** 199

### 3. Class Rosters — `5tagid.csv`, `6tagid.csv`, `7tagid.csv`

Each file lists the registered RFID tags for one grade level, along with student metadata.

| Column | Type | Description |
|--------|------|-------------|
| `Tag ID` | int | Mifare ID of the RFID card (note: labelled "Tag ID" in the file but is actually the Mifare ID) |
| `Student ID` | str | School registry number, or sensor label (e.g., `Stat. 5-A`) |
| `Class` | str | Classroom designation (e.g., `5-A`, `6-B`, `7-C`). Empty for non-student tags |
| `Notes` | str | Role label: `Öğrenci` (Student), `Stationary`, `Teacher`, `Employee`, `Nöbetçi` |

**Delimiter:** semicolon (`;`) · **Extra column:** 5th and 6th grade files have a trailing `Unnamed: 4` column (empty) that is dropped during loading.

**Role labels and corrections applied during processing:**

### Deployment Schedule

| Grade | Deployment Date | School Hours Window | Classes |
|-------|----------------|---------------------|---------|
| 7th | 2023-03-15 (Wednesday) | 09:00 – 15:00 | 7-A, 7-B, 7-C, 7-D, 7-E, 7-F |
| 6th | 2023-03-20 (Monday) | 09:00 – 15:00 | 6-A, 6-B, 6-C, 6-D, 6-E, 6-F |
| 5th | 2023-03-22 (Wednesday) | 09:00 – 15:00 | 5-A, 5-B, 5-C, 5-D, 5-E, 5-F |


## Analysis Pipeline

The notebook `altogether_anls.ipynb` executes the following stages sequentially. All cells must be run **in order from top to bottom**.

### Stage 1 — Environment Setup & Data Loading
1. Install dependencies (`requirements.txt`).
2. Import libraries and custom functions from `utils.py`.
3. Load the RFID card mapping (`tagid-mifareid.csv`).
4. Load and merge class rosters for all three grades against the RFID mapping.
5. Normalize role labels (translate Turkish labels, fix mislabelled tags).

### Stage 2 — Contact Data Preprocessing
6. Load raw contact logs (`all1.csv` + `all2.csv`), drop incomplete rows, concatenate.
7. Convert timestamps from milliseconds to seconds.
8. Remove unused columns (`baseid`, `upload_time`, raw timestamps).

### Stage 3 — Per-Grade Processing & Deduplication
9. For each grade, run `process_grade_contacts()` from `utils.py`, which:
   - Filters to the deployment date and school hours (09:00–15:00).
   - Removes zero-duration contacts, zero-distance readings, and sensor noise (≥3600 cm).
   - Joins class/role metadata to both participants.
   - Drops contacts involving unregistered tags (NaN after merge).
   - Creates direction-agnostic pair keys (`tag_min`, `tag_max`).
   - Performs exact deduplication.
   - Runs 4-pass near-duplicate removal with 3-second tolerance (grouped by student pair).

### Stage 4 — Student-Only & Known-Class Filtering
10. Filter to student-to-student contacts only (exclude `Stationary`, `Teacher`, `Employee`).
11. Further filter to known-class contacts (exclude `unknown` class labels).

### Stage 5 — Network Construction
12. Build contact graphs using `igraph` via `build_contact_graph()`:
    - **All-students graphs** (`contact_net5/6/7`): include students with unknown classes.
    - **Known-class graphs** (`known_net5/6/7`): only students with identified classrooms.
13. Simplify multigraphs → single weighted edges (weight = sum of contact durations).
14. Contract graphs to classroom-level networks for inter-class analysis.

### Stage 6 — Threshold Optimisation
15. Sweep contact duration thresholds (0–60 seconds) measuring:
    - Classroom modularity (community detection quality).
    - Network density.
16. Compute combined normalised change scores.
17. Select optimal threshold at point of maximum combined change.
18. Apply threshold to produce final baseline networks:
    - `g5/6/7_baseline` (known-class only)
    - `g5/6/7_baseline_all` (all students)

### Stage 7 — Network Metrics & Visualisation
19. Compute network-level metrics: density, average degree, clustering coefficient, average shortest path, max clique size, weight/degree ratio.
20. Compute node-level metrics: individual degree, clustering coefficient, total contact weight.
21. Z-score normalisation for cross-grade comparison.
22. Generate visualisations:
    - Network topology plots (Fruchterman-Reingold / MDS layouts).
    - Inter-class interaction heatmaps (duration, count, unique pairs).
    - Stationary sensor location contact timelines.
    - Average degree over time.
    - Modularity/density threshold sweep curves.
    - Node-level metric violin plots.
    - Degree and duration distribution fits (power-law analysis).
    - Weight-degree correlation scatter plots.


## Reproduction Instructions

### Prerequisites


### Step 1 — Clone or Download

Download or clone this repository to your local machine. Ensure the `data/` folder contains all six CSV files listed above.

### Step 2 — Create a Virtual Environment

```bash
cd TUBITAK-RELATED

# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate          # Windows
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

**Core dependencies and their roles:**

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | 3.0.1 | Data manipulation and DataFrames |
| `numpy` | 2.4.3 | Numerical computing |
| `igraph` | 1.0.0 | Network/graph construction and analysis |
| `matplotlib` | 3.10.8 | Primary plotting library |
| `seaborn` | 0.13.2 | Statistical visualisation |
| `powerlaw` | 2.0.0 | Heavy-tailed distribution fitting ([Alstott et al., 2014](https://doi.org/10.1371/journal.pone.0085777)) |
| `scipy` | 1.17.1 | Scientific computing and statistics |
| `fitter` | 1.8.0 | Distribution fitting |
| `distfit` | 2.0.1 | Distribution fitting and plotting |
| `statsmodels` | 0.14.6 | Statistical models and tests |
| `cairocffi` | 1.7.1 | Cairo graphics backend for igraph plotting |
| `pillow` | 12.1.1 | Image processing |

### Step 4 — Run the Notebook

Open `altogether_anls.ipynb` in your Jupyter environment and execute all cells sequentially from top to bottom:

```bash
# Option A: VS Code
code altogether_anls.ipynb

# Option B: JupyterLab
jupyter lab altogether_anls.ipynb

# Option C: Classic Notebook
jupyter notebook altogether_anls.ipynb
```

> **Note:** The first cell enables `%autoreload 2` so that any edits to `utils.py` are automatically picked up without restarting the kernel.

### Step 5 — Verify Outputs

After a successful run, you should see:

  - Tag & role breakdown per grade.
  - Data quality and filtering statistics.
  - Network metrics (both known-class and all-students).
  - Threshold sweep results.

### Expected Key Results (All-Students Baseline Networks)

| Metric | 7th Grade | 6th Grade | 5th Grade |
|--------|-----------|-----------|-----------|
| Nodes | 168 | 162 | 185 |
| Edges | 5,299 | 4,479 | 6,990 |
| Network Density | 0.378 | 0.343 | 0.411 |
| Avg Degree | 63.083 | 55.296 | 75.568 |
| Avg Contact Duration (min) | 21.573 | 25.742 | 19.150 |
| Avg Clustering Coefficient | 0.518 | 0.539 | 0.557 |
| Avg Shortest Path | 1.623 | 1.660 | 1.590 |
| Max Clique Size | 30 | 32 | 41 |


## Key Utility Functions (`utils.py`)

| Function | Description |
|----------|-------------|
| `csv_to_df()` | Load CSV with auto-detected delimiter (`,` or `;`) |
| `load_class_contacts()` | Load class roster, rename columns, merge with RFID mapping, translate labels |
| `normalize_class_notes()` | Fix mislabelled Stationary/unknown tags, translate Turkish labels, deduplicate |
| `process_grade_contacts()` | Full pipeline: time-window filter → quality filter → class enrichment → deduplication |
| `drop_near_dupes()` | Grouped 3-second tolerance near-duplicate removal |
| `build_contact_graph()` | Build undirected weighted igraph graph from contact DataFrame |
| `build_matrix()` | Build symmetric adjacency matrices (duration, count, or unique-pairs mode) |
| `filter_graph_by_duration()` | Remove edges below a duration threshold and prune isolated nodes |
| `get_geo_data()` | Extract stationary sensor contacts binned into 3-minute intervals |
| `build_visual_style()` | Generate igraph visual styling (node colours by class, edge widths by weight) |
| `plot_basics_ccdf()` / `plot_fit_pdf()` / `plot_fit_ccdf()` | Power-law distribution visualisations |

For complete function signatures and parameters, see the docstrings in [`utils.py`](utils.py).


## Reference Documentation



## Citation

If you use the `powerlaw` package in your analysis, please cite:

> Alstott, J., Bullmore, E., & Plenz, D. (2014). **powerlaw: A Python Package for Analysis of Heavy-Tailed Distributions.** *PLoS ONE*, 9(1), e85777. https://doi.org/10.1371/journal.pone.0085777


## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` on first run | Run `pip install -r requirements.txt` inside the activated virtual environment |
| `cairocffi` installation fails | Install system Cairo library first: `brew install cairo` (macOS) or `sudo apt install libcairo2-dev` (Ubuntu) |
| Figures not saving | Ensure the `figures/` directory exists: `mkdir -p figures` |
| Kernel dies on large operations | Ensure at least 4 GB of free RAM; the full pipeline uses ~2 GB peak |
| Different numerical results | Ensure you are running **all cells in order** from a fresh kernel restart (`Kernel → Restart & Run All`) |
>>>>>>> c071c65 (Add published student contact analysis dataset and code)
