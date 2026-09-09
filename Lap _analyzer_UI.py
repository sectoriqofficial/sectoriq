"""
Lap Time Analyzer - Basic UI
-----------------------------
A simple window that lets you analyze your latest Assetto Corsa
session and see your history, without touching the terminal.

This file doesn't duplicate any analysis logic, it just imports
and reuses everything already built in lap_analyzer.py.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from collections import defaultdict

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from lap_analyzer import (
    read_lap_data_from_ac_json,
    find_best_lap,
    compare_to_best,
    save_session_to_history,
    delete_session_from_history,
    export_history_to_excel,
)


# -----------------------------------------------
# Finds the REAL folder this app lives in, whether
# it's running as a plain .py script or as a bundled
# PyInstaller .exe. This matters because PyInstaller's
# --onefile mode extracts to a temporary folder at
# runtime, so __file__ alone points to the wrong place
# and would cause saved data to vanish when you close
# the app.
# -----------------------------------------------
def get_app_folder():
    if getattr(sys, "frozen", False):
        # Running as a bundled .exe, use the actual .exe's location.
        return os.path.dirname(sys.executable)
    else:
        # Running as a normal .py script.
        return os.path.dirname(os.path.abspath(__file__))


# -----------------------------------------------
# Builds a report string from ANY session's saved
# laps, whether it's the live one or a past one
# pulled from history.json.
# -----------------------------------------------
def build_report_text(track_name, car_name, laps, saved_note=None):
    best_lap = find_best_lap(laps)
    comparisons = compare_to_best(laps, best_lap)

    lines = []
    lines.append(f"Track: {track_name}")
    lines.append(f"Car: {car_name}")
    lines.append(f"Best Lap: Lap {best_lap['lap']} — {best_lap['total_time']}s\n")
    lines.append(f"{'Lap':<5}{'Sec1 +/-':<12}{'Sec2 +/-':<12}{'Sec3 +/-':<12}{'Total +/-':<10}")
    lines.append("-" * 51)
    for c in comparisons:
        lines.append(
            f"{c['lap']:<5}{c['sector1_diff']:<12}{c['sector2_diff']:<12}"
            f"{c['sector3_diff']:<12}{c['total_diff']:<10}"
        )

    if saved_note:
        lines.append(f"\n{saved_note}")

    return "\n".join(lines)


# -----------------------------------------------
# Helper: same logic as the script's __main__ block,
# but returns text instead of printing directly.
# -----------------------------------------------
def analyze_latest_session():
    script_folder = get_app_folder()
    history_path = os.path.join(script_folder, "history.json")

    documents_folder = os.path.join(os.environ["USERPROFILE"], "Documents")
    json_path = os.path.join(documents_folder, "Assetto Corsa", "out", "race_out.json")

    with open(json_path, "r") as f:
        raw_data = json.load(f)
    track_name = raw_data["track"]
    car_name = raw_data["players"][0]["car"]

    laps = read_lap_data_from_ac_json(json_path)

    if not laps:
        return "No valid laps found in the latest session.", None

    best_lap = find_best_lap(laps)
    save_session_to_history(history_path, track_name, car_name, laps, best_lap)

    saved_note = f"Session saved to history ({track_name}, best lap {best_lap['total_time']}s)"
    report_text = build_report_text(track_name, car_name, laps, saved_note)

    return report_text, history_path


# -----------------------------------------------
# Button action: run analysis, show results or error
# -----------------------------------------------
def on_analyze_click():
    try:
        report_text, history_path = analyze_latest_session()
        output_box.delete("1.0", tk.END)
        output_box.insert(tk.END, report_text)
        refresh_history_list(history_path)
    except FileNotFoundError:
        messagebox.showerror(
            "File Not Found",
            "Couldn't find race_out.json. Make sure you've completed "
            "at least one clean lap in Assetto Corsa first.",
        )
    except Exception as e:
        messagebox.showerror("Error", f"Something went wrong:\n{e}")


# -----------------------------------------------
# Refreshes the session history list on the side.
# Keeps the full history data in memory too, so
# clicking an entry can pull up its saved laps.
# -----------------------------------------------
loaded_history = []  # holds the full history data, most recent first
current_history_path = None  # tracks where history.json actually lives


def refresh_history_list(history_path=None):
    global loaded_history, current_history_path

    history_list.delete(0, tk.END)

    if history_path is None:
        script_folder = get_app_folder()
        history_path = os.path.join(script_folder, "history.json")

    current_history_path = history_path

    if not os.path.exists(history_path):
        loaded_history = []
        return

    with open(history_path, "r") as f:
        history = json.load(f)

    # Show most recent sessions first, and keep this order
    # in memory too, so listbox index matches loaded_history index.
    loaded_history = list(reversed(history))

    for entry in loaded_history:
        summary = f"{entry['date']} — {entry['track']} — {entry['best_lap_time']}s"
        history_list.insert(tk.END, summary)


# -----------------------------------------------
# Click handler: when a past session is selected,
# show its full lap breakdown in the output box.
# -----------------------------------------------
def on_history_select(event):
    selection = history_list.curselection()
    if not selection:
        return

    index = selection[0]
    entry = loaded_history[index]

    report_text = build_report_text(
        entry["track"], entry["car"], entry["laps"],
        saved_note=f"(Viewing saved session from {entry['date']})"
    )

    output_box.delete("1.0", tk.END)
    output_box.insert(tk.END, report_text)


# -----------------------------------------------
# Delete button: removes the currently selected
# history entry, with a confirmation prompt first.
# -----------------------------------------------
def on_delete_click():
    selection = history_list.curselection()
    if not selection:
        messagebox.showinfo("No Selection", "Select a session in the history list first.")
        return

    listbox_index = selection[0]
    entry = loaded_history[listbox_index]

    confirm = messagebox.askyesno(
        "Delete Session",
        f"Delete this session?\n\n{entry['date']} — {entry['track']} — {entry['best_lap_time']}s"
    )
    if not confirm:
        return

    # loaded_history is newest-first, but the actual file is
    # oldest-first, so convert the index before deleting.
    real_index = len(loaded_history) - 1 - listbox_index
    delete_session_from_history(current_history_path, real_index)

    refresh_history_list(current_history_path)
    output_box.delete("1.0", tk.END)


# -----------------------------------------------
# Export button: saves your full history to an
# Excel file, letting you pick where to save it.
# -----------------------------------------------
def on_export_click():
    if not current_history_path or not os.path.exists(current_history_path):
        messagebox.showinfo("No Data Yet", "Analyze at least one session first before exporting.")
        return

    output_path = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        filetypes=[("Excel files", "*.xlsx")],
        initialfile="lap_data_export.xlsx",
        title="Save Excel Export As"
    )

    if not output_path:
        return  # user cancelled

    try:
        export_history_to_excel(current_history_path, output_path)
        messagebox.showinfo("Export Complete", f"Saved to:\n{output_path}")
    except Exception as e:
        messagebox.showerror("Export Failed", f"Something went wrong:\n{e}")


# -----------------------------------------------
# Trend graph: opens a new window with a dropdown
# to pick a track, then shows one line per car used
# on that track, since lap times only compare
# meaningfully within the same track.
# -----------------------------------------------
def on_trends_click():
    if not loaded_history:
        messagebox.showinfo("No Data Yet", "Analyze at least a couple of sessions first to see trends.")
        return

    # Chronological order (oldest first), since loaded_history
    # is currently newest-first.
    sessions_oldest_first = list(reversed(loaded_history))

    # Group all sessions by track first, so the dropdown only
    # lists tracks you've actually driven.
    by_track = defaultdict(list)
    for entry in sessions_oldest_first:
        by_track[entry["track"]].append(entry)

    track_names = sorted(by_track.keys())

    trend_window = tk.Toplevel(root)
    trend_window.title("Lap Time Trends")
    trend_window.geometry("850x600")

    # Dropdown to pick which track to focus on
    top_bar = tk.Frame(trend_window)
    top_bar.pack(fill=tk.X, padx=10, pady=10)

    tk.Label(top_bar, text="Track:", font=("Arial", 11)).pack(side=tk.LEFT)

    selected_track = tk.StringVar(value=track_names[0])
    track_dropdown = tk.OptionMenu(top_bar, selected_track, *track_names)
    track_dropdown.pack(side=tk.LEFT, padx=(5, 0))

    # Explains what "session number" actually counts, since it's
    # easy to misread as "overall session 1, 2, 3" rather than
    # "the Nth time you drove THIS car on THIS track."
    explainer = tk.Label(
        trend_window,
        text="Each line's session numbers count only that car's laps on this track, "
             "not your overall session count.",
        font=("Arial", 9), fg="#555555", wraplength=800, justify="left"
    )
    explainer.pack(fill=tk.X, padx=10, pady=(0, 5))

    # Chart area, created once, redrawn whenever the track changes
    fig = Figure(figsize=(8, 5.5), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=trend_window)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def format_lap_time(total_seconds):
        """Converts 95.664 into '1:35.664', the way lap times are
        normally written, instead of raw seconds."""
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:06.3f}"

    def draw_chart_for_track(*args):
        track = selected_track.get()
        entries_for_track = by_track[track]

        # Within this track, group by car so each car gets its own line
        by_car = defaultdict(list)
        for entry in entries_for_track:
            by_car[entry["car"]].append(entry)

        ax.clear()
        for car, car_entries in by_car.items():
            x_values = list(range(1, len(car_entries) + 1))
            y_values = [entry["best_lap_time"] for entry in car_entries]
            line, = ax.plot(x_values, y_values, marker="o", linewidth=2, markersize=7, label=car)

            # Label each point with its actual lap time, so you don't
            # have to squint at the axis to read exact values.
            for x, y in zip(x_values, y_values):
                ax.annotate(
                    format_lap_time(y), (x, y),
                    textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=8, color=line.get_color()
                )

        # Only show whole numbers on the x-axis, since "session 2.5"
        # doesn't mean anything.
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))

        # Show the y-axis in lap-time format (1:35.664) instead of
        # raw seconds (95.664).
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda val, pos: format_lap_time(val))
        )

        ax.set_xlabel("Session number (per car)", fontsize=11)
        ax.set_ylabel("Best lap time (min:sec.ms)", fontsize=11)
        ax.set_title(f"Best Lap Time Over Time — {track}", fontsize=13, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        canvas.draw()

    # Redraw automatically whenever the dropdown selection changes
    selected_track.trace_add("write", draw_chart_for_track)

    # Draw the initial chart for whichever track is selected first
    draw_chart_for_track()


# -----------------------------
# Build the window
# -----------------------------
root = tk.Tk()
root.title("Lap Time Analyzer")
root.geometry("800x500")

# Left side: analyze button + report output
left_frame = tk.Frame(root)
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

analyze_button = tk.Button(
    left_frame, text="Analyze Latest Session", command=on_analyze_click,
    font=("Arial", 12), bg="#2e7d32", fg="white", pady=8
)
analyze_button.pack(fill=tk.X, pady=(0, 10))

trends_button = tk.Button(
    left_frame, text="View Trends", command=on_trends_click,
    font=("Arial", 12), bg="#1565c0", fg="white", pady=8
)
trends_button.pack(fill=tk.X, pady=(0, 10))

export_button = tk.Button(
    left_frame, text="Export to Excel", command=on_export_click,
    font=("Arial", 12), bg="#00695c", fg="white", pady=8
)
export_button.pack(fill=tk.X, pady=(0, 10))

output_box = scrolledtext.ScrolledText(left_frame, font=("Consolas", 10))
output_box.pack(fill=tk.BOTH, expand=True)

# Right side: session history list
right_frame = tk.Frame(root, width=250)
right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

history_label = tk.Label(right_frame, text="Session History", font=("Arial", 12, "bold"))
history_label.pack(anchor="w")

history_list = tk.Listbox(right_frame, width=35, font=("Consolas", 9))
history_list.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
history_list.bind("<<ListboxSelect>>", on_history_select)

delete_button = tk.Button(
    right_frame, text="Delete Selected Session", command=on_delete_click,
    font=("Arial", 10), bg="#c62828", fg="white", pady=4
)
delete_button.pack(fill=tk.X, pady=(8, 0))

# Load any existing history when the app opens
refresh_history_list()

root.mainloop()