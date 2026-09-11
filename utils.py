from itertools import islice
from pathlib import Path
from typing import List, Union, Optional
import pandas as pd
from pandas import DataFrame
import igraph
from powerlaw import plot_ccdf, Fit, pdf, plot_pdf
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone, timedelta


def csv_to_df(path: Union[str, Path], name: Optional[str] = None) -> DataFrame:
    """
    Load a CSV file into a pandas DataFrame with basic delimiter auto-detection.

    - Reads a small sample of the file to guess the delimiter (',' or ';').
    - Loads the full file into a DataFrame using the detected delimiter.
    - Sets pandas to display floats with 5 decimal places.
    - If `name` is provided, also stores the DataFrame in the global namespace
      under that name (e.g. `globals()[name] = df`).

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the CSV file.
    name : str, optional
        Global variable name under which to register the DataFrame.

    Returns
    -------
    pandas.DataFrame
        The loaded DataFrame.
    """
    path = Path(path)

    # Read only a few lines to detect delimiter (more efficient than readlines())
    with path.open("r", encoding="utf-8") as file:
        header_sample = "".join(islice(file, 5))

    delimiter = ";" if ";" in header_sample else ","

    df = pd.read_csv(path, sep=delimiter)

    pd.set_option("display.float_format", lambda x: f"{x:.5f}")

    if name:
        globals()[name] = df

    return df


def load_class_contacts(csv_path, df_rfid, drop_unnamed=False):
    # Load class contact data
    df = csv_to_df(csv_path)

    # Align column name for merging
    df.rename({'Tag ID': 'Mifare ID'}, axis=1, inplace=True)

    # Some files have an extra unnamed column; drop it if requested
    if drop_unnamed and 'Unnamed: 4' in df.columns:
        df.drop(columns=['Unnamed: 4'], inplace=True)

    # Merge with RFID mapping to add tag and type info
    df_merged = df.merge(
        df_rfid[['Mifare ID', 'Tag ID', 'Type']],
        on='Mifare ID',
        how='left'
    )

    # Replace missing labels with a default, if the columns exist
    if 'Class' in df_merged.columns:
        df_merged['Class'] = df_merged['Class'].fillna('unknown')
    if 'Notes' in df_merged.columns:
        df_merged['Notes'] = df_merged['Notes'].fillna('unknown')
        # Translate Turkish 'Öğrenci' directly to English 'Student' on load
        df_merged['Notes'] = df_merged['Notes'].replace('Öğrenci', 'Student')

    return df_merged


def reindex(df: DataFrame) -> DataFrame:
    """
    Reset the index of a DataFrame in place and drop the old index column.

    This mirrors ``df.reset_index(drop=True, inplace=True)`` but returns the
    same DataFrame for convenience so it can be used in expressions.
    """
    df.reset_index(drop=True, inplace=True)
    return df


def normalize_class_notes(df: DataFrame) -> DataFrame:
    """
    Standardize 'Notes' to 'Student' where the row clearly refers to a student,
    then drop duplicates and reset the index.
    """
    # Stationary + short Student ID (numeric or short code) → student
    if "Student ID" in df.columns:
        student_id_len = df["Student ID"].astype(str).str.len()
        mask_stationary = (df["Notes"] == "Stationary") & (student_id_len < 5)
        df.loc[mask_stationary, "Notes"] = "Student"
    # Any tag with an 'unknown' role is assumed to be a student based on interaction behavior
    df.loc[df["Notes"] == "unknown", "Notes"] = "Student"

    # Convert any remaining Turkish 'Öğrenci' from source CSVs to English
    df["Notes"] = df["Notes"].replace("Öğrenci", "Student")

    df.drop_duplicates(keep="first", inplace=True)
    return reindex(df)


def get_student_class_counts(df):
    """
    Filter the dataframe for 'Student' and 'unknown' notes, 
    and return a clean summary DataFrame of population counts per class.
    """
    # Use .isin() for clean filtering, searching for 'Student' instead of 'Öğrenci'
    target_notes = ['Student', 'unknown']
    
    # Filter, count values, and instantly convert to a clean DataFrame
    counts = df[df['Notes'].isin(target_notes)]['Class'].value_counts()
    return counts.rename_axis('Class').reset_index(name='Count')


def make_autopct(values):
    """
    Return an autopct formatter that shows the raw integer count
    on each pie slice rather than the percentage.
    """
    def _fmt(pct):
        val = int(round(pct * sum(values) / 100.0))
        return f'{val:d}'
    return _fmt


def plot_grade_pies(
    populations: list,
    titles: list,
    save_path: Optional[str] = None,
    figsize: tuple = (8, 2.75),
) -> None:
    """
    Draw a side-by-side row of pie charts — one per grade.

    Parameters
    ----------
    populations : list of DataFrame
        Each DataFrame must have 'Class' and 'Count' columns
        (as produced by ``get_student_class_counts``).
    titles : list of str
        One title per pie chart (e.g. ['5th Grade', '6th Grade', '7th Grade']).
    save_path : str, optional
        If given, saves the figure to this file path before showing.
    figsize : tuple, optional
        Figure size passed directly to ``plt.subplots``.
    """

    # Snapshot current rcParams and temporarily reset to defaults
    _prev_rc = plt.rcParams.copy()
    plt.rcdefaults()

    n = len(populations)
    fig, axs = plt.subplots(1, n, figsize=figsize)
    if n == 1:
        axs = [axs]  # ensure iterable even for a single chart

    for ax, pop_df, title in zip(axs, populations, titles):
        counts = pop_df['Count']
        labels = pop_df['Class']

        # Auto-generate explode: highlight the last slice regardless of count
        explode: List[float] = [0.0] * len(counts)
        if len(explode) > 0:
            explode[-1] = 0.2

        ax.pie(
            counts,
            labels=labels,
            explode=explode,
            autopct=make_autopct(counts),
            startangle=140,
            textprops={'fontsize': 9},
            pctdistance=0.55,
        )
        total = counts.sum()
        ax.text(-0.85, -1.4, f'Total Students: {total}',
                verticalalignment='baseline', fontsize=10, weight='bold')
        ax.set_title(title, fontsize=12)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
    plt.show()

    # Restore previous rcParams so downstream cells are unaffected
    plt.rcParams.update(_prev_rc)


def georgian_to_unix(georgian_time: str) -> int:
    """
    Convert a date-time string to a Unix timestamp.
    Assumes the input string is Turkey Time (UTC+3) but 
    returns a standard Unix (UTC) timestamp.
    """
    dt = datetime.strptime(georgian_time, "%Y-%m-%d %H:%M:%S")
    # Force the timezone to UTC+3 (Turkey)
    tr_tz = timezone(timedelta(hours=3))
    return int(dt.replace(tzinfo=tr_tz).timestamp())


def unix_to_georgian(timestamp: float) -> str:
    """
    Convert a Unix timestamp (seconds since 1970-01-01) to a formatted
    date-time string ``'YYYY-MM-DD HH:MM:SS'`` in local time.
    """
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def merge_class_info(df: DataFrame, tag_col: str, class_df: DataFrame) -> DataFrame:
    """
    Left-join class metadata ('Class', 'Notes') onto a contact DataFrame
    for a single tag column, handling the temporary rename so pandas can
    match on 'Tag ID'.

    Parameters
    ----------
    df : DataFrame
        The contact events DataFrame (e.g. ``df7``).
    tag_col : str
        Column name containing the tag IDs to enrich
        (e.g. ``'tagid'`` or ``'touched_tagid'``).
    class_df : DataFrame
        The class-level reference DataFrame that must include
        ``'Tag ID'``, ``'Class'``, and ``'Notes'`` columns.

    Returns
    -------
    DataFrame
        The contact DataFrame with new ``'Class'`` and ``'Notes'`` columns
        appended, and the original tag column name restored.
    """
    df = df.rename(columns={tag_col: 'Tag ID'})
    df = df.merge(class_df[['Tag ID', 'Class', 'Notes']], on='Tag ID', how='left')
    return df.rename(columns={'Tag ID': tag_col})


def drop_near_dupes(
    df: DataFrame,
    sort_col: str,
    subset: list,
    tolerance: float = 3.0,
    diff_col: Optional[str] = None,
    also_check_col: Optional[str] = None,
) -> DataFrame:
    """
    Remove near-duplicate contact rows that fall within a time tolerance.

    Parameters
    ----------
    df : DataFrame
        Contact events DataFrame, must contain ``'duration'`` and *sort_col*.
    sort_col : str
        The column (+ ``'duration'``) used to sort the DataFrame before
        checking neighbours.
    subset : list of str
        Column names that define a "near-duplicate" signature.
    tolerance : float, optional
        Maximum difference for near-duplicate detection. Default is 3.
    diff_col : str, optional
        The column to compute `.diff()` on.  Defaults to *sort_col* when
        not specified (which is the common case).
    also_check_col : str, optional
        An additional column whose diff must also be within *tolerance*
        (e.g. ``'duration'``).

    Returns
    -------
    DataFrame
        The deduplicated DataFrame sorted by [*sort_col*, ``'duration'``].
    """
    if diff_col is None:
        diff_col = sort_col

    df = df.sort_values([sort_col, 'duration'])
    
    # Calculate consecutive differences within each subset group (e.g. same student pair & distance)
    diffs = df.groupby(subset)[diff_col].diff().abs()
    near_dupe_mask = df.duplicated(subset=subset) & diffs.le(tolerance)
    
    if also_check_col is not None:
        diffs_also = df.groupby(subset)[also_check_col].diff().abs()
        near_dupe_mask = near_dupe_mask & diffs_also.le(tolerance)
        
    return df[~near_dupe_mask]


def process_grade_contacts(
    df_contacts: DataFrame,
    class_csv: str,
    df_rfid: DataFrame,
    date: str,
    drop_unnamed: bool = False,
    normalize: bool = False,
    extra_note_fixes: Optional[dict] = None,
    max_distance: int = 3600,
    tolerance: float = 3.0,
) -> DataFrame:
    """
    Full pipeline: load class data, filter contacts to a school day,
    enrich with class metadata, and deduplicate.

    Parameters
    ----------
    df_contacts : DataFrame
        The master contact events DataFrame. Accepts columns named either
        ``'begin_time_s'``/``'end_time_s'`` or ``'cor_begin_time'``/
        ``'cor_end_time'``.
    class_csv : str
        Path to the grade-specific class CSV file (e.g. ``'data/7tagid.csv'``).
    df_rfid : DataFrame
        The RFID card-to-tag mapping DataFrame.
    date : str
        The school day as ``'YYYY-MM-DD'``. The window is automatically
        set to 09:00–15:00 on that day.
    drop_unnamed : bool, optional
        Whether to drop ``'Unnamed: 4'`` from the class CSV.
    normalize : bool, optional
        If True, run ``normalize_class_notes`` on the class data
        (needed for 5th graders with Stationary mislabels).
    extra_note_fixes : dict, optional
        Additional Notes value replacements, e.g. ``{'Nöbetçi': 'Student'}``.
    max_distance : int, optional
        Upper bound on ``min_distance``; rows above this are noise.
    tolerance : float, optional
        Seconds tolerance for near-duplicate removal.

    Returns
    -------
    DataFrame
        Cleaned, deduplicated contact events for this grade on this day.
    """
    # ── Load & clean class data ──────────────────────────────────────────
    class_df = load_class_contacts(class_csv, df_rfid, drop_unnamed=drop_unnamed)
    if normalize:
        class_df = normalize_class_notes(class_df)
    if extra_note_fixes:
        for old_val, new_val in extra_note_fixes.items():
            class_df['Notes'] = class_df['Notes'].replace(old_val, new_val)

    # ── Auto-detect timestamp column names ───────────────────────────────
    if 'begin_time_s' in df_contacts.columns:
        col_begin, col_end = 'begin_time_s', 'end_time_s'
    else:
        col_begin, col_end = 'cor_begin_time', 'cor_end_time'

    # ── Define time window ───────────────────────────────────────────────
    day_start = georgian_to_unix(f"{date} 09:00:00")
    day_end   = georgian_to_unix(f"{date} 15:00:00")

    # ── Filter contacts ──────────────────────────────────────────────────
    mask = (
        df_contacts[col_begin].between(day_start, day_end) &
        df_contacts[col_end].between(day_start, day_end) &
        df_contacts['duration'].ne(0) &
        df_contacts['min_distance'].ne(0) &
        df_contacts['min_distance'].lt(max_distance)
    )
    df = df_contacts[mask].copy()

    # ── Enrich with class metadata ───────────────────────────────────────
    df = merge_class_info(df, 'tagid',         class_df)
    df = merge_class_info(df, 'touched_tagid', class_df)

    # ── Exclude unregistered tags ─────────────────────────────────────────
    # Tags that do not appear in the grade's class roster receive NaN after
    # the merge (e.g. spare/test cards).  We drop any contact where either
    # participant is unregistered so that downstream analyses only contain
    # tags with known provenance.
    df.dropna(subset=['Notes_x', 'Notes_y'], how='any', inplace=True)
    df = reindex(df)

    # ── Direction-agnostic pair key (vectorized) ─────────────────────────
    df['tag_min'] = np.minimum(df['tagid'], df['touched_tagid'])
    df['tag_max'] = np.maximum(df['tagid'], df['touched_tagid'])

    # ── Exact deduplication ──────────────────────────────────────────────
    df.drop_duplicates(inplace=True)
    df = reindex(df)

    df.drop_duplicates(
        subset=[col_begin, col_end, 'min_distance',
                'tag_min', 'tag_max', 'duration'],
        inplace=True,
    )
    df = reindex(df)

    # ── Near-duplicate removal (4 passes, matching original logic) ───────
    relaxed_key = ['min_distance', 'tag_min', 'tag_max']
    exact_key   = ['min_distance', 'tag_min', 'tag_max', 'duration']

    # Pass 1: sort by begin_time, dup on relaxed, check begin_time AND duration diff
    df = drop_near_dupes(df, col_begin, relaxed_key, tolerance, also_check_col='duration')
    # Pass 2: sort by begin_time, dup on exact, check begin_time diff
    df = drop_near_dupes(df, col_begin, exact_key,   tolerance)
    # Pass 3: sort by begin_time, dup on relaxed, check END_TIME AND duration diff
    df = drop_near_dupes(df, col_begin, relaxed_key, tolerance,
                         diff_col=col_end, also_check_col='duration')
    # Pass 4: sort by end_time, dup on exact, check begin_time diff
    df = drop_near_dupes(df, col_end, exact_key, tolerance,
                         diff_col=col_begin)

    return reindex(df)


def find_inactive_tags(class_df, contact_df, grade_label):
    """Return a dict with inactive tag info for one grade."""
    registered = set(class_df['Tag ID'].unique())
    seen_as_tagid     = set(contact_df['tagid'].unique())
    seen_as_touched   = set(contact_df['touched_tagid'].unique())
    inactive = registered - (seen_as_tagid | seen_as_touched)
    return {
        'Grade':          grade_label,
        'Registered Tags': len(registered),
        'Inactive Tags':   len(inactive),
        'Inactive Tag IDs': sorted(inactive) if inactive else '—',
    }


def known_class_contacts(df: DataFrame) -> DataFrame:
    """Keep only contacts where both sides have an identified class."""
    return df[(df['Class_x'] != 'unknown') & (df['Class_y'] != 'unknown')]


def build_contact_graph(contact_df: DataFrame, class_df: DataFrame) -> igraph.Graph:
    """
    Build an undirected weighted igraph contact network from a contact DataFrame.

    Uses vectorized pandas operations (no ``iterrows``) for performance.

    Parameters
    ----------
    contact_df : DataFrame
        Student-only contact events, must contain ``'tagid'``,
        ``'touched_tagid'``, and ``'duration'`` columns.
    class_df : DataFrame
        Class reference DataFrame with ``'Tag ID'``, ``'Notes'``,
        and ``'Class'`` columns.

    Returns
    -------
    igraph.Graph
        Undirected graph where each vertex has ``'name'`` (role label),
        ``'class'``, and ``'id'`` (tag ID string) attributes, and each edge
        carries a ``'weight'`` equal to the contact duration in seconds.
    """
    # Build tag ID → metadata lookups (vectorized, no iterrows)
    id_to_name  = class_df.set_index('Tag ID')['Notes'].to_dict()
    id_to_name  = {str(k): v for k, v in id_to_name.items()}
    id_to_class = class_df.set_index('Tag ID')['Class'].to_dict()
    id_to_class = {str(k): v for k, v in id_to_class.items()}

    # Create unique, undirected pairs to ensure a simple graph (no multiple edges)
    df = contact_df.copy()
    df['student_min'] = np.minimum(df['tagid'], df['touched_tagid']).astype(str)
    df['student_max'] = np.maximum(df['tagid'], df['touched_tagid']).astype(str)
    
    # Aggregate to sum durations for each unique interacting pair
    grouped = df.groupby(['student_min', 'student_max'], as_index=False)['duration'].sum()

    # Extract edges and weights
    tagids_a = grouped['student_min'].tolist()
    tagids_b = grouped['student_max'].tolist()
    weights  = grouped['duration'].tolist()
    edges    = list(zip(tagids_a, tagids_b))

    # Unique vertex list preserving insertion order
    all_ids = list(dict.fromkeys(tagids_a + tagids_b))

    g = igraph.Graph(
        n=len(all_ids),
        directed=False,
        vertex_attrs={'id': all_ids, 'name': all_ids, 'class': all_ids},
    )
    g.add_edges(edges)
    g.es['weight'] = weights

    # Replace raw tag IDs with human-readable labels
    g.vs['name']  = [id_to_name.get(v,  v) for v in g.vs['name']]
    g.vs['class'] = [id_to_class.get(v, 'unknown') for v in g.vs['class']]

    return g


def build_matrix(df, classes, mode='duration'):
    """Builds a symmetric matrix for 'duration', raw 'count', or 'unique_pairs' using fast pandas vectorization."""
    n = len(classes)
    mat = np.zeros((n, n), dtype=float)
    
    # Map classes to their matrix indices (0 to n-1)
    class_map = {c: i for i, c in enumerate(classes)}
    
    # Work on a copy to avoid SettingWithCopyWarnings
    d = df.copy()
    
    # Drop rows that have 'unknown' or unmapped classes
    d = d[d['Class_x'].isin(class_map) & d['Class_y'].isin(class_map)]
    
    # Map class strings to matrix index integers
    d['i'] = d['Class_x'].map(class_map)
    d['j'] = d['Class_y'].map(class_map)
    
    # Ensure (i, j) is an unordered pair where i <= j, so we only group once per pair of classes
    d['min_idx'] = np.minimum(d['i'], d['j'])
    d['max_idx'] = np.maximum(d['i'], d['j'])
    
    # Pre-process unique pairs to avoid double-counting students
    if mode == 'unique_pairs':
        # Fast way to drop duplicate student interactions without apply()
        d['student_min'] = np.minimum(d['tagid'], d['touched_tagid'])
        d['student_max'] = np.maximum(d['tagid'], d['touched_tagid'])
        d = d.drop_duplicates(subset=['student_min', 'student_max'])
        
    # Group by the class pairs and aggregate
    if mode == 'duration':
        agg = d.groupby(['min_idx', 'max_idx'])['duration'].sum()
    else:
        agg = d.groupby(['min_idx', 'max_idx']).size()
        
    # Populate the symmetric matrix
    for (i, j), val in agg.items():
        mat[int(i), int(j)] = val
        if i != j:
            mat[int(j), int(i)] = val
            
    return mat


def filter_graph_by_duration(base_net, threshold_seconds):
    """
    Creates a copy of a base contact graph and removes any edges
    with a contact duration strictly less than the specified threshold.
    Isolated nodes are also removed.
    """
    g = base_net.copy()
    edges_to_delete = g.es.select(weight_lt=threshold_seconds)
    g.delete_edges(edges_to_delete)
    
    isolated_nodes = g.vs.select(_degree=0)
    g.delete_vertices(isolated_nodes)
    
    return g


def get_geo_data(df: DataFrame, class_df: DataFrame, start_time: int, end_time: int) -> DataFrame:
    """
    Extracts stationary sensor location contacts and bins them into 3-minute buckets.
    Robustly handles various schemas (codes vs tag_min/tag_max) and ID types.
    """
    # 1. Clean stationary sensor mapping
    stats = class_df[class_df['Notes'] == 'Stationary'].copy()
    
    # helper to clean IDs: 284824.0 (float) -> 284824 (int) -> "284824" (str)
    def clean_id(val):
        try: return str(int(float(val)))
        except: return str(val)

    stats['Tag ID'] = stats['Tag ID'].apply(clean_id)
    
    m = stats.set_index('Tag ID')['Student ID']
    m = m.str.replace('Stat. Kantin', 'Cafeteria', regex=False) \
         .str.replace('Stat. Kapı', 'Main Door', regex=False) \
         .str.replace('Stat[ .]*', '', regex=True)
    mapping_dict = m.to_dict()

    # 2. Detect column names
    col_time = 'begin_time_s' if 'begin_time_s' in df.columns else 'cor_begin_time'
    
    # 3. Filter contacts to window
    df = df[(df[col_time] >= start_time) & (df[col_time] < end_time)].copy()
    if df.empty:
        return pd.DataFrame(index=range((end_time - start_time) // 180))

    # 4. Robust Mapping Logic
    def map_robust(row):
        # Case A: tag_min and tag_max
        if 'tag_min' in row and 'tag_max' in row:
            for t in [row['tag_min'], row['tag_max']]:
                st = clean_id(t)
                if st in mapping_dict: return mapping_dict[st]
            
        # Case B: codes collection
        if 'codes' in row:
            cv = row['codes']
            if isinstance(cv, str):
                for tid, loc in mapping_dict.items():
                    if tid in cv: return loc
            elif isinstance(cv, (list, tuple, np.ndarray)):
                for cid in cv:
                    scid = clean_id(cid)
                    if scid in mapping_dict: return mapping_dict[scid]
        return np.nan

    df['loc'] = df.apply(map_robust, axis=1)
    df = df.dropna(subset=['loc'])
    
    total_bins = (end_time - start_time) // 180
    if df.empty:
        return pd.DataFrame(index=range(total_bins))
    
    # 5. Bin and Aggregate
    df['bin'] = (df[col_time] - start_time) // 180
    res = df.groupby(['loc', 'bin']).size().unstack(0, fill_value=0)
    return res.reindex(range(total_bins), fill_value=0)


def plot_stationary_contacts(df, class_df, start_time: int, end_time: int, title: str, ax=None):
    """
    Extracts stationary sensor data and produces a standardized visualization.
    If 'ax' is provided, it plots on that axis (useful for subplots).
    """
    # 1. Extract and Bin data
    res = get_geo_data(df, class_df, start_time, end_time)
    
    # Track if we need to show the plot at the end (standalone mode)
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(15, 6))
    
    if res.empty:
        ax.text(0.5, 0.5, f"No data for {title}", ha='center', va='center')
        return

    # 2. Plotting logic
    colors = plt.cm.get_cmap('tab20')(np.linspace(0, 1, res.shape[1]))
    for idx, sensor in enumerate(res.columns):
        ax.plot(res.index, res[sensor], label=sensor, color=colors[idx], marker='s', markersize=4, linewidth=1)

    # 3. Styling (Research Style / Times New Roman)
    ax.set_title(title, fontsize=16, fontname='Times New Roman', loc='left', pad=10)
    ax.grid(False)
    ax.set_facecolor('white')
    for spine in ax.spines.values():
        spine.set_color('black')
        spine.set_linewidth(1)

    # Tick formatting
    tick_pos = range(0, 121, 10)
    tick_labels = ['9', '9:30', '10', '10:30', '11', '11:30', '12', '12:30', '13', '13:30', '14', '14:30', '15']
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, fontname='Times New Roman', fontsize=11)
    
    # Legend
    ax.legend(fontsize=9, prop={'family': 'Times New Roman'}, loc='upper right', frameon=True, shadow=True)

    if standalone:
        plt.tight_layout()
        plt.show()


def get_avg_degree(df, start_time: int, end_time: int) -> pd.Series:
    """
    Calculates the average degree (average number of contacts per active person)
    in 3-minute intervals using high-speed grouping.
    """
    col_time = 'begin_time_s' if 'begin_time_s' in df.columns else 'cor_begin_time'
    
    # 1. Filter to window and calculate bins
    d = df[(df[col_time] >= start_time) & (df[col_time] < end_time)].copy()
    d['bin'] = (d[col_time] - start_time) // 180
    
    # 2. Vectorized calculation: Total Contacts / Unique People per bin
    agg = d.groupby('bin')['tagid'].agg(['count', 'nunique'])
    return (agg['count'] / agg['nunique']).reindex(range(121), fill_value=0)


def build_visual_style(g: igraph.Graph, class_colors: dict) -> dict:
    """
    Builds a dictionary of visual attributes for igraph plotting via Matplotlib.
    Handles node coloring by class and edge styling by weights.
    """
    classes = g.vs['class']
    vertex_colors = [class_colors.get(cls, '#cccccc') for cls in classes]

    edge_colors = []
    edge_widths = []
    for edge in g.es:
        src_cls = classes[edge.source]
        tgt_cls = classes[edge.target]
        if src_cls == tgt_cls:
            edge_colors.append((0.4, 0.4, 0.8, 0.15)) # Light blue internal
            edge_widths.append(0.4)
        else:
            edge_colors.append((0.2, 0.2, 0.2, 0.6))  # Gray bridge
            edge_widths.append(0.8)

    if g.ecount() > 0 and 'weight' in g.edge_attributes():
        weights = np.array(g.es['weight'])
        max_w = weights.max() if weights.max() > 0 else 1
        edge_widths = [ew * (w / max_w) * 2.0 for ew, w in zip(edge_widths, weights)]

    layout = g.layout('fr', niter=500) 

    return {
        'layout':       layout,
        'vertex_size':  10,
        'vertex_color': vertex_colors,
        'vertex_frame_width': 0.3,
        'vertex_frame_color': 'white',
        'edge_width':   edge_widths,
        'edge_color':   edge_colors,
        'margin':       60,
    }


def make_legend_patches(g: igraph.Graph, class_colors: dict) -> list:
    """Build matplotlib legend patches for the unique classes in a graph."""
    import matplotlib.patches as mpatches
    unique_classes = sorted(set(g.vs['class']))
    return [
        mpatches.Patch(color=class_colors.get(cls, '#cccccc'), label=cls)
        for cls in unique_classes
    ]


def plot_basics_ccdf(data, data_inst: int, fig, units: str, n_graphs: int, n_data: int) -> None:
    """
    Plot the complementary cumulative distribution function (CCDF) of ``data``
    on a log scale in the given matplotlib figure.

    Parameters
    ----------
    data : array-like
        Sample data to plot.
    data_inst : int
        Index (1-based) of the subplot in the ``n_graphs × n_data`` grid.
    fig : matplotlib.figure.Figure
        Figure to which the subplot is added.
    units : str
        Label for the x-axis.
    n_graphs : int
        Number of subplot rows.
    n_data : int
        Number of subplot columns.
    """
    ax = fig.add_subplot(n_graphs, n_data, data_inst)
    plot_ccdf(data, ax=ax, color="r", linewidth=0.5)
    ax.set_xlabel(units)


def plot_fit_pdf(data, data_inst: int, fig, units: str, n_graphs: int, n_data: int) -> None:
    """
    Plot the empirical PDF of ``data`` with fitted power-law and exponential
    models on a log-log scale.

    Parameters are the same as for :func:`plot_basics_ccdf`.
    """
    ax = fig.add_subplot(n_graphs, n_data, data_inst)

    fit = Fit(data, discrete=True)
    fit.plot_pdf(ax=ax, color="r")
    fit.power_law.plot_pdf(ax=ax, linestyle=":", color="g")
    fit.exponential.plot_pdf(ax=ax, linestyle=":", color="b")

    ax.set_ylim(1e-8, 1)
    ax.set_xlabel(units)


def plot_fit_ccdf(data, data_inst: int, fig, units: str, n_graphs: int, n_data: int) -> None:
    """
    Plot the CCDF of ``data`` together with fitted power-law models for
    different lower cutoffs.

    Parameters are the same as for :func:`plot_basics_ccdf`.
    """
    ax = fig.add_subplot(n_graphs, n_data, data_inst)

    fit_default = Fit(data, discrete=True)
    fit_default.plot_ccdf(ax=ax, color="r")
    fit_default.power_law.plot_ccdf(ax=ax, linestyle=":", color="g")

    fit_xmin1 = Fit(data, discrete=True, xmin=1)
    fit_xmin1.power_law.plot_ccdf(ax=ax, linestyle="--", color="b")

    if data_inst == 1:
        ax.set_ylim(1e-5, 1)
    else:
        ax.set_ylim(1e-3, 1)

    ax.set_xlabel(units)


def run_single_simulation(args):
    """Worker function to run a single bootstrap simulation of power-law fit."""
    import numpy as np
    import powerlaw
    
    toy_data, prob_above, xmin_val, alpha_val, D_emp, durations_below = args
    n_total = len(toy_data)
    
    n_sim_above = np.random.binomial(n_total, prob_above)
    n_sim_below = n_total - n_sim_above
    
    if n_sim_below > 0 and len(durations_below) > 0:
        body_samples = np.random.choice(durations_below, size=n_sim_below, replace=True)
    else:
        body_samples = np.array([])
        
    if n_sim_above > 0:
        tail_generator = powerlaw.Power_Law(xmin=xmin_val, parameters=[alpha_val], discrete=True)
        tail_samples = tail_generator.generate_random(n_sim_above)
    else:
        tail_samples = np.array([])
        
    sim_data = np.concatenate([body_samples, tail_samples])
    
    try:
        # Search xmin restricted to range (10, 100) for speed
        fit_sim = powerlaw.Fit(sim_data, xmin=(10, 100), discrete=True, verbose=False)
        return 1 if fit_sim.D >= D_emp else 0
    except Exception:
        return 0


def calculate_ks_p_value_parallel(durations, num_simulations=100):
    """
    Computes the Clauset et al. (2009) bootstrap p-value for the power-law fit in parallel.
    Uses all available CPU cores and restricts xmin search range for 20x speedup.
    """
    import numpy as np
    import powerlaw
    import multiprocessing
    import warnings
    warnings.filterwarnings('ignore')
    
    print("Fitting empirical data (restricting xmin search to range [10, 100])...")
    # Restrict search space of xmin to range (10, 100) since we know the optimal xmin is around 25-35s
    fit_emp = powerlaw.Fit(durations, xmin=(10, 100), discrete=True)
    D_emp = fit_emp.D
    xmin = fit_emp.xmin
    alpha = fit_emp.alpha
    
    print(f"Empirical Optimal xmin: {xmin:.1f} seconds")
    print(f"Empirical scaling exponent (beta): {alpha:.4f}")
    print(f"Empirical KS distance (D): {D_emp:.4f}")
    
    durations_below = durations[durations < xmin]
    durations_above = durations[durations >= xmin]
    n_total = len(durations)
    n_above = len(durations_above)
    prob_above = n_above / n_total
    
    # Prepare arguments for each process
    args_list = [(durations, prob_above, xmin, alpha, D_emp, durations_below) for _ in range(num_simulations)]
    
    num_cores = multiprocessing.cpu_count()
    print(f"\nRunning {num_simulations} bootstrap simulations in parallel across {num_cores} cores...")
    
    import time
    t0 = time.time()
    results = []
    with multiprocessing.Pool(processes=num_cores) as pool:
        for idx, res in enumerate(pool.imap_unordered(run_single_simulation, args_list), 1):
            results.append(res)
            if idx % 100 == 0 or idx == num_simulations:
                print(f"  Completed {idx}/{num_simulations} simulations...")
    t1 = time.time()
    
    p_val = sum(results) / num_simulations
    print(f"\n--- Results ---")
    print(f"Bootstrap KS p-value: {p_val:.4f}")
    print(f"Calculation completed in {t1 - t0:.2f} seconds!")
    return p_val



