import ftplib
import shutil
import os
import re
import subprocess
from config import FTP_PORT, FTP_USER, FTP_PASS, FTP_HOST
from datetime import datetime
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog, ttk

VIDEO_FILENAME_PATTERN = re.compile(r"^[A-Z](?P<date>\d{8})-(?P<time>\d{6})[PD]\d+"
                                    r"N(?P<channel>\d)[F]\d\.("
                                 r"264|avi)$", re.IGNORECASE)


# Connect to FTP
def connect_ftp():
    ftp = ftplib.FTP_TLS()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    return ftp

def print_hi(name):
    print(f'Hi, {name}, let\'s get some fucking files copied.')

# Request project number
def get_project_number():
    root = tk.Tk()
    root.withdraw()  # Hide main window
    project_number = simpledialog.askstring("Project Number", "Enter 5-digit project number:")
    return project_number if project_number and project_number.isdigit() and len(project_number) == 5 else None

def select_server(ftp):
    """ List root folders and prompt user to choose one via a dropdown (combobox) """
    ftp.cwd("/")  # Ensure we're at the root
    root_folders = ftp.nlst()  # List all top-level directories

    if not root_folders:
        print("No server directories found in FTP root.")
        return None

    # Create a Tkinter window
    root = tk.Tk()
    root.title("Select Server")

    # Set window size and position
    root.geometry("300x100")
    root.resizable(False, False)

    # Dropdown selection variable
    selected_server = tk.StringVar()
    selected_server.set(root_folders[0])  # Default to first option

    # Label
    label = tk.Label(root, text="Choose a server:")
    label.pack(pady=5)

    # Dropdown menu (combobox)
    dropdown = ttk.Combobox(root, textvariable=selected_server, values=root_folders, state="readonly")
    dropdown.pack(pady=5)

    server_selected = None

    # Selection change event
    def on_selection_change(event):
        nonlocal server_selected
        server_selected = event.widget.get()
        print(f"DEBUG: Selection updated to: {server_selected}")  # Debugging print

    dropdown.bind("<<ComboboxSelected>>", on_selection_change)  # Bind selection event

    # Button to confirm selection
    def on_confirm():
        root.quit()  # Close the window when confirmed

    button = tk.Button(root, text="OK", command=on_confirm)
    button.pack(pady=5)

    dropdown.focus_set()

    # Run the Tkinter event loop
    root.mainloop()
    root.destroy()

    return server_selected if server_selected in root_folders else None

# Search for project folder (latest first)
def find_project_folders(ftp, project_number, primary_server):
    """
    Search for project folders in the latest 7 weekly directories on the primary server,
    then search the same 7-week span in the secondary server.
    """

    ftp.cwd("/")  # Ensure we're at the root

    # Get a list of all servers (root folders)
    available_servers = ftp.nlst()
    if primary_server not in available_servers:
        print(f"Primary server '{primary_server}' not found.")
        return None

    # Determine the secondary server (the other one)
    secondary_server = [srv for srv in available_servers if srv != primary_server]
    secondary_server = secondary_server[0] if secondary_server else None

    matched_folders = []
    searched_weeks = []  # Store the exact 7-week span we searched in primary

    def search_in_server(server, week_range=None):
        """ Search for project folders in a given server. Limit to specific weeks if provided. """
        ftp.cwd(f"/{server}")  # Move into the selected server directory
        week_folders = sorted(ftp.nlst(), reverse=True)  # Get all week folders

        if week_range:
            # Limit search to the same 7-week span we searched in the primary server
            week_folders = [week for week in week_folders if week in week_range]

        found_folders = []
        first_match_found = False  # Track when we find the first valid project folder
        weeks_checked = 0

        for week_folder in week_folders:
            if re.match(r"^\d{3} - Week Commencing \d{2}-[A-Za-z]{3}-\d{2}$", week_folder):
                if not week_range:
                    searched_weeks.append(week_folder)  # Store this week for mirroring in secondary

                ftp.cwd(week_folder)
                project_folders = ftp.nlst()
                matched_this_week = False  # Track if we find a project in this week

                for folder in project_folders:
                    if folder.startswith(str(project_number)):  # Ensure string comparison
                        found_folders.append((server, week_folder, folder))
                        matched_this_week = True

                ftp.cwd("..")  # Move back to the server root

                # If this week contained a match, start counting subsequent weeks
                if matched_this_week:
                    first_match_found = True  # First valid project folder found

                # Once first match is found, count how many more weeks we check
                if first_match_found:
                    weeks_checked += 1
                    if weeks_checked >= 7:  # Stop after first match + next six weeks
                        break # Move back to the server root

        return found_folders

    # Step 1: Search primary server and store the exact 7-week span
    matched_folders.extend(search_in_server(primary_server))

    # Step 2: Search secondary server in the same 7-week span (whether we found matches in primary or not)
    if secondary_server and searched_weeks:
        print(f"Checking secondary server: {secondary_server} for the same weeks")
        matched_folders.extend(search_in_server(secondary_server, week_range=searched_weeks))

    return matched_folders if matched_folders else None


def select_destination():
    """ Prompt the user to select either Server or Local as the destination. """
    root = tk.Tk()
    root.withdraw()  # Hide the root window immediately
    root.lift()
    root.focus_force()
    root.attributes("-topmost", True)
    root.title("Select Destination")
    root.geometry("300x150")
    root.resizable(False, False)

    # User selection storage
    destination = {"choice": None}  # Mutable so inner functions can modify it

    label = tk.Label(root, text="Select the destination for the files:")
    label.pack(pady=10)

    def set_server():
        """ Set destination to 'server' and close window """
        destination["choice"] = "server"
        root.quit()
        root.destroy()

    def set_local():
        """ Open file dialog for local destination selection """
        folder_selected = filedialog.askdirectory(title="Select Local Destination",
                                                  parent=root)
        if folder_selected:
            destination["choice"] = folder_selected
            root.quit()
            root.destroy()
        else:
            messagebox.showwarning("No Folder Selected", "Please select a folder or choose 'Server'.")

    # Buttons for selection
    server_button = tk.Button(root, text="Server", command=set_server, width=10)
    server_button.pack(pady=5)

    local_button = tk.Button(root, text="Local", command=set_local, width=10)
    local_button.pack(pady=5)

    # Run the UI
    root.deiconify()  # Show the root window after setup
    root.mainloop()

    return destination["choice"]

# Ask user for date selection
def get_date_range(ftp, site_folders):
    """ Extract available date folders and allow the user to select a date range. """
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    available_dates = set()

    # Try to find folders that match yyyy-mm-dd format
    for site_folder in site_folders:
        ftp.cwd(site_folder)
        for name, meta in ftp.mlsd():
            if meta.get("type") == "dir" and date_pattern.match(name):
                available_dates.add(name)
        ftp.cwd("..")

    available_dates = sorted(available_dates)

    # Fallback: if no folders, check for video files in root
    if not available_dates:
        for site_folder in site_folders:
            ftp.cwd(site_folder)
            files = ftp.nlst()
            for file in files:
                if VIDEO_FILENAME_PATTERN.match(file):
                    return ["NO_DATES_FOUND"]  # fallback marker
            ftp.cwd("..")
        return []  # no video files either

    if len(available_dates) == 1:
        return available_dates

    # UI prompt
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.focus_force()
    root.attributes("-topmost", True)
    root.title("Select Dates")
    root.geometry("300x400")
    root.deiconify()

    selected_dates = {}

    container = ttk.Frame(root)
    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)

    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    container.pack(fill="both", expand=True, padx=10, pady=10)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    for date in available_dates:
        var = tk.BooleanVar(master=root, value=True)
        cb = ttk.Checkbutton(scrollable_frame, text=date, variable=var)
        cb.pack(anchor="w", padx=5, pady=2)
        selected_dates[date] = var

    result = []

    def on_confirm():
        nonlocal result
        result = [date for date, var in selected_dates.items() if var.get()]
        root.quit()
        root.destroy()

    ttk.Button(root, text="OK", command=on_confirm).pack(pady=10)

    root.mainloop()
    return result
 # Ensure it returns the selected ones

# Ask user for time periods
def get_time_periods(survey_dates):
    """
    Prompt user to assign survey periods to each selected date.
    Allows shared or separate schedules and returns a dict:
    {date: [ (start_hr, start_min, end_hr, end_min), ... ]}
    """
    def prompt_same_schedule():
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.focus_force()
        root.attributes("-topmost", True)
        root.title("Survey Time Periods")
        root.geometry("350x150")
        root.deiconify()

        answer = {"same": None}

        def choose_same():
            answer["same"] = True
            root.quit()
            root.destroy()

        def choose_different():
            answer["same"] = False
            root.quit()
            root.destroy()

        label = tk.Label(root, text="Do the same survey times apply to all dates?", font=("Segoe UI", 10))
        label.pack(pady=15)

        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=10)

        yes_btn = ttk.Button(btn_frame, text="Yes", width=12, command=choose_same)
        yes_btn.grid(row=0, column=0, padx=10)

        no_btn = ttk.Button(btn_frame, text="No", width=12, command=choose_different)
        no_btn.grid(row=0, column=1, padx=10)

        root.mainloop()
        return answer["same"]

    def prompt_time_periods(num_periods=1):
        periods = []

        def on_proceed():
            try:
                for i in range(num_periods):
                    start_hr = int(start_hrs[i].get())
                    start_min = int(start_mins[i].get())
                    end_hr = int(end_hrs[i].get())
                    end_min = int(end_mins[i].get())
                    periods.append((start_hr, start_min, end_hr, end_min))
                window.quit()
                window.destroy()
            except ValueError:
                messagebox.showerror("Input Error", "Please enter valid times for all periods.")

        def on_restart():
            window.quit()
            window.destroy()
            window.quit()
            window.destroy()
            return None

        window = tk.Tk()
        window.title("Select Survey Time Periods")
        window.geometry("420x300")
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()

        ttk.Label(window, text="Number of survey periods per day:").pack(pady=(10, 4))
        period_select = ttk.Combobox(window, values=[1, 2, 3, 4, 5], state="readonly",
                                     width=3)
        period_select.current(num_periods - 1)
        period_select.pack()

        frm = ttk.Frame(window)
        frm.pack(pady=10)

        start_hrs, start_mins, end_hrs, end_mins = [], [], [], []

        def update_time_fields(event=None):
            # Clear old widgets
            for widget in frm.winfo_children():
                widget.destroy()

            start_hrs.clear()
            start_mins.clear()
            end_hrs.clear()
            end_mins.clear()

            count = int(period_select.get())
            if count == 1:
                defaults = [(7, 0, 19, 0)]
            elif count == 2:
                defaults = [(7, 0, 10, 0), (16, 0, 19, 0)]
            else:
                defaults = [(7, 0, 10, 0), (16, 0, 19, 0)] + [(12, 0, 12, 0)] * (
                            count - 2)

            for i in range(count):
                ttk.Label(frm, text=f"Survey Period {i + 1}").grid(row=i * 2, column=0,
                                                                   columnspan=6,
                                                                   pady=(6, 2))
                ttk.Label(frm, text="Start Time").grid(row=i * 2 + 1, column=0,
                                                       padx=(5, 2))
                ttk.Label(frm, text="End Time").grid(row=i * 2 + 1, column=3,
                                                     padx=(20, 2))

                sh = ttk.Spinbox(frm, from_=0, to=24, width=3, format="%02.0f")
                sm = ttk.Spinbox(frm, from_=0, to=59, width=3, format="%02.0f")
                eh = ttk.Spinbox(frm, from_=0, to=24, width=3, format="%02.0f")
                em = ttk.Spinbox(frm, from_=0, to=59, width=3, format="%02.0f")

                sh.grid(row=i * 2 + 1, column=1, padx=(0, 5))
                sm.grid(row=i * 2 + 1, column=2, padx=(0, 15))
                eh.grid(row=i * 2 + 1, column=4, padx=(0, 5))
                em.grid(row=i * 2 + 1, column=5, padx=(0, 5))

                d = defaults[i]
                sh.insert(0, f"{d[0]:02d}")
                sm.insert(0, f"{d[1]:02d}")
                eh.insert(0, f"{d[2]:02d}")
                em.insert(0, f"{d[3]:02d}")

                start_hrs.append(sh)
                start_mins.append(sm)
                end_hrs.append(eh)
                end_mins.append(em)

        # Bind dropdown changes to live update fields
        period_select.bind("<<ComboboxSelected>>", update_time_fields)
        update_time_fields()  # initial render

        btns = ttk.Frame(window)
        btns.pack(pady=8)
        ttk.Button(btns, text="Restart Selection", command=on_restart).grid(row=0, column=0, padx=10)
        ttk.Button(btns, text="Proceed", command=on_proceed).grid(row=0, column=1, padx=10)

        window.mainloop()

        return periods

    same = prompt_same_schedule()

    survey_schedule = {}

    if same:
        window = tk.Tk()
        window.withdraw()
        window.title("Select Number of Survey Periods")
        window.geometry("300x150")
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
        window.deiconify()

        selection = {"count": 1}

        def confirm_count():
            try:
                selection["count"] = int(period_box.get())
                window.quit()
                window.destroy()
            except ValueError:
                messagebox.showerror("Invalid Selection", "Please select a valid number of periods.")

        ttk.Label(window, text="Select how many periods per day:").pack(pady=(20, 8))
        period_box = ttk.Combobox(window, values=[1, 2, 3, 4, 5], state="readonly")
        period_box.current(0)
        period_box.pack()

        ttk.Button(window, text="Continue", command=confirm_count).pack(pady=10)

        window.mainloop()

        num_periods = selection["count"]
        periods = prompt_time_periods(num_periods)
        if periods is None:
            return None

        for date in survey_dates:
            survey_schedule[date] = periods

    else:
        # Collect times for each group of dates until all are covered
        remaining_dates = set(survey_dates)

        while remaining_dates:
            # Build UI for selecting subset of dates
            root = tk.Tk()
            root.title("Choose dates for time period set")
            root.geometry("300x400")
            root.attributes("-topmost", True)
            root.lift()
            root.focus_force()

            ttk.Label(root, text="Select dates for the {} time period:".format(
                "first" if len(survey_schedule) == 0 else "next"
            )).pack(pady=10)

            container = ttk.Frame(root)
            canvas = tk.Canvas(container, highlightthickness=0)
            scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            container.pack(fill="both", expand=True, padx=10, pady=5)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            date_vars = {}
            for date in sorted(remaining_dates):
                var = tk.BooleanVar(master=root, value=False)
                cb = ttk.Checkbutton(scrollable_frame, text=date, variable=var, offvalue=False, onvalue=True)
                cb.pack(anchor="w")
                date_vars[date] = var

            selected = []

            def confirm_dates():
                nonlocal selected
                selected = [date for date, var in date_vars.items() if var.get()]
                if not selected:
                    messagebox.showwarning("No Dates Selected", "Please select at least one date.")
                    return
                root.quit()
                root.destroy()

            ttk.Button(root, text="Next", command=confirm_dates).pack(pady=10)
            root.mainloop()

            if not selected:
                continue  # User didn't confirm any selection, retry

            # Prompt for time periods for this date group
            num_window = tk.Tk()
            num_window.withdraw()
            num_window.title("Select Number of Survey Periods")
            num_window.geometry("300x150")
            num_window.attributes("-topmost", True)
            num_window.lift()
            num_window.focus_force()
            num_window.deiconify()

            selection = {"count": 1}

            def confirm_count():
                try:
                    selection["count"] = int(period_box.get())
                    num_window.quit()
                    num_window.destroy()
                except ValueError:
                    messagebox.showerror("Invalid Selection", "Please select a valid number of periods.")

            ttk.Label(num_window, text="Select how many periods per day:").pack(pady=(20, 8))
            period_box = ttk.Combobox(num_window, values=[1, 2, 3, 4, 5], state="readonly")
            period_box.current(0)
            period_box.pack()

            ttk.Button(num_window, text="Continue", command=confirm_count).pack(pady=10)
            num_window.mainloop()

            num_periods = selection["count"]
            periods = prompt_time_periods(num_periods)
            if periods is None:
                return None

            for date in selected:
                survey_schedule[date] = periods
                remaining_dates.remove(date)

            return survey_schedule


def find_survey_files(ftp, site_folders, survey_periods):
    """
    Identify and return a list of video files that match the provided
    site folders and survey period date/time windows.

    This will use VIDEO_FILENAME_PATTERN to parse filenames and filter
    based on matching dates and hour/minute ranges.

    Parameters:
        ftp (ftplib.FTP): Active FTP session
        site_folders (list): List of site folder paths to scan
        survey_periods (dict): {date: [ (start_hr, start_min, end_hr, end_min), ... ]}

    Returns:
        list of (site_folder, filename) tuples matching the criteria
    """
    pass  # To be implemented after get_time_periods


# Confirm file copying
def confirm_transfer():
    root = tk.Tk()
    root.withdraw()
    return messagebox.askyesno("Confirm", "Start copying files?")

# Rename .264 to .avi
def rename_files(ftp, path):
    ftp.cwd(path)
    for file in ftp.nlst():
        if file.endswith(".264"):
            new_name = file.replace(".264", ".avi")
            ftp.rename(file, new_name)

# Folder renaming prompt
def rename_folders(folders):
    root = tk.Tk()
    root.withdraw()
    new_names = {}

    for folder in folders:
        new_name = simpledialog.askstring("Rename Folder", f"Rename {folder} (leave blank to keep):")
        if new_name:
            new_names[folder] = new_name

    return new_names

def check_local_storage(required_size, destination_path):
    """Check if the USB has enough space for the required footage, allowing for some leeway"""

    total, used, free = shutil.disk_usage(destination_path)

    # Allow ~5% leeway for filesystem differences
    required_size_with_buffer = required_size * 1.05

    if free < required_size_with_buffer:
        print(f"⚠ WARNING: Not enough space on {destination_path}!")
        print(f"Required: {required_size_with_buffer/1e9:.2f} GB, Available: {free/1e9:.2f} GB")
        return False
    return True

def check_existing_files(destination_path):
    """Check if the destination folder contains existing files and prompt user"""
    if os.listdir(destination_path):  # If folder is not empty
        root = tk.Tk()
        root.withdraw()

        response = messagebox.askyesnocancel(
            "Existing Files Found",
            "There are existing files in this location. Proceed and overwrite them?",
        )

        if response is None:
            return "cancel"
        elif response:
            return "overwrite"
        else:
            return "format"
    return "proceed"

def get_available_drives():
    """Return a list of all available drive letters in Windows."""
    return [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]

def select_local_folder():
    """Prompt user to choose a local storage location, defaulting to 'This PC' (all drives)."""
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.focus_force()

    # Try using an available drive as the initial directory, else default to Desktop
    initial_dir = get_available_drives()[0] if get_available_drives() else os.path.expanduser("~\\Desktop")

    folder = filedialog.askdirectory(
        title="Select Local Storage Location (USB or Folder)",
        initialdir=initial_dir  # Default to first detected drive (or Desktop if none)
    )

    return folder if folder else None

def format_usb(drive_letter):
    """Quick-format the selected USB drive with the best compatible filesystem, with user confirmation pop-ups"""

    # Determine the best filesystem (NTFS for large files, FAT32 for smaller USBs)
    filesystem = "FAT32" if shutil.disk_usage(drive_letter)[0] < 32e9 else "NTFS"

    # Confirm formatting
    root = tk.Tk()
    root.withdraw()
    confirm = messagebox.askyesno(
        "Format USB Drive",
        f"Are you sure you want to format {drive_letter}?\n"
        "This will erase all data on the drive!"
    )

    if not confirm:
        return False  # User cancelled formatting

    # Run Windows format command
    try:
        subprocess.run(["format", drive_letter, "/FS:" + filesystem, "/Q", "/Y"], check=True)
        messagebox.showinfo("Success", f"✅ USB {drive_letter} formatted successfully.")
        return True
    except subprocess.CalledProcessError:
        retry = messagebox.askretrycancel("Format Failed", f"❌ Failed to format {drive_letter}.\n"
                                    "Would you like to try again or select a different USB?")
        if retry:
            return format_usb(drive_letter)  # Retry formatting
        return False  # User chose to cancel

# Main execution
def main():
    ftp = connect_ftp()

    # Step 1: Get Project Number
    project_number = get_project_number()
    if not project_number:
        print("Invalid project number.")
        return

    # Step 2: Find All Matching Project Folders Across Both Servers
    primary_server = select_server(ftp)  # User picks primary server
    if not primary_server:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Invalid server selection", "This is not a valid server "
                                                         "selection.")
        return

    project_folders = find_project_folders(ftp, project_number, primary_server)
    if not project_folders:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Project Folder Error", f"No project folders"
                                f"found for {project_number} "
                                      f"on this server.")
        return

    print(f"Found {len(project_folders)} matching project folders:")
    for server, week, folder in project_folders:
        print(f"- {server}/{week}/{folder}")

    def select_folders(ftp, project_path):
        ftp.cwd(project_path)
        folders = ftp.nlst()

        if not folders:
            print("No site folders found.")
            return []

        root = tk.Tk()
        root.title("Select Site Folders")
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()

        folder_count = len(folders)
        min_height = 150
        max_height = 500
        window_height = min(max_height, max(min_height, folder_count * 25 + 60))
        root.geometry(f"400x{window_height}")

        container = ttk.Frame(root)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollable_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scrollable_frame.bind("<Configure>",
                              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        selected_vars = {}

        for folder in folders:
            var = tk.BooleanVar(master=root, value=True)
            cb = ttk.Checkbutton(
                scrollable_frame,
                text=folder,
                variable=var
            )
            cb.pack(anchor="w", padx=5, pady=2)
            selected_vars[folder] = var

        result = []

        def on_confirm():
            nonlocal result
            result = [folder for folder, var in selected_vars.items() if var.get()]
            print("Final selected folders:", result)
            root.quit()
            root.destroy()

        confirm_button = ttk.Button(root, text="OK", command=on_confirm)
        confirm_button.pack(pady=10)

        def _on_mouse_wheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        canvas.bind_all("<MouseWheel>", _on_mouse_wheel)

        root.after(100, lambda: root.attributes("-topmost", False))
        root.mainloop()

        return result

    selected_folders = []

    # Step 3: Let user select site folders for each matching project folder
    for server, week, project_path in project_folders:
        full_path = f"/{server}/{week}/{project_path}"
        site_folders = select_folders(ftp, full_path)
        if site_folders:
            selected_folders.extend([(full_path, site) for site in site_folders])

    if not selected_folders:
        print("No site folders selected.")
        return

    def get_file_size(ftp, ftp_paths, site_folders):
        pass

    # Step 4: Ask if the user wants 'server' or 'local path'
    destination = select_destination()

    # Step 5: Get Date & Time Selections before we know file size
    survey_dates = get_date_range(ftp, site_folders)
    while True:
        survey_periods = get_time_periods(survey_dates)
        if survey_periods is not None:
            break  # success!
        # else, the user clicked restart — show everything again

    if destination != "server":
        # Treat anything else as a local folder path
        local_path = destination
        if not os.path.isdir(local_path):
            print("Invalid local destination. Aborting.")
            return

        # Step 4b: Calculate required file space (placeholder call)
        required_size = sum([
            get_file_size(ftp, survey_periods)
            for project_path, site_folder in selected_folders
        ])

        # Step 4c: Check if there's enough space
        if not check_local_storage(required_size, local_path):
            print("Not enough space on selected device. Aborting.")
            return

        # Step 4d: Check for existing files and prompt user
        file_action = check_existing_files(local_path)
        if file_action == "cancel":
            print("User cancelled operation. Aborting.")
            return
        elif file_action == "format":
            drive_letter = local_path[:3]  # e.g., "E:\\"
            format_usb(drive_letter)

    # Step 6: Confirm File Copying
    if confirm_transfer():
        if destination == "server":
            for project_path, site_folder in selected_folders:
                client_results_path = f"{project_path}/Client Results"
                try:
                    ftp.mkd(client_results_path)
                except ftplib.error_perm:
                    pass  # Folder already exists

                rename_files(ftp, f"{project_path}/{site_folder}")

        else:  # Copy to local storage
            for project_path, site_folder in selected_folders:
                download_files(ftp, f"{project_path}/{site_folder}", local_path)

        print("Files copied successfully.")

    # Step 7: Rename Folders (if needed)
    new_names = rename_folders([site for _, site in selected_folders])
    for (project_path, old_name), new_name in new_names.items():
        ftp.rename(f"{project_path}/{old_name}", f"{project_path}/{new_name}")

    ftp.quit()
    print("FTP session closed.")


if __name__ == "__main__":
    print_hi('floppy dick')
    main()

