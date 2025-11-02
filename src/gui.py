import os
import math
import multiprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from overlay import run
from stockfish_bot import StockfishBot
from selenium.common import WebDriverException
import keyboard


class GUI:
    def __init__(self, master):
        self.master = master

        # Used for closing the threads
        self.exit = False

        # The Selenium Chrome driver
        self.chrome = None

        self.chrome_url = None
        self.chrome_session_id = None
        self.player_is_white = None

        # Used for the communication between the GUI
        # and the Stockfish Bot process
        self.stockfish_bot_pipe = None
        self.overlay_screen_pipe = None

        # The Stockfish Bot process
        self.stockfish_bot_process = None
        self.overlay_screen_process = None
        self.restart_after_stopping = False

        # Used for storing the match moves
        self.match_moves = []
        # self.move_counts = {} # Removed
        
        # Used to store the last evaluation for redraws
        self.last_eval_data = None
        self.last_top_moves_data = [] # Store last top moves for toggling
        
        # self.symbol_map = { ... } # Removed symbol_map

        # Set the window properties
        master.title("PawnBit")
        master.minsize(520, 750)
        # Make sure the asset path is correct or comment out/remove if not found
        try:
            master.iconphoto(True, tk.PhotoImage(file="src/assets/pawn_32x32.png"))
        except tk.TclError:
            print("Icon 'src/assets/pawn_32x32.png' not found. Skipping.")
        master.attributes("-topmost", True)
        master.protocol("WM_DELETE_WINDOW", self.on_close_listener)

        # Change the style
        style = ttk.Style()
        style.theme_use("clam")
        # Add style for our toggle button
        style.configure("Toolbutton", anchor="w", padding=2, font=("TkDefaultFont", 9))
        
        # Configure grid layout
        master.grid_rowconfigure(0, weight=1)
        master.grid_columnconfigure(1, weight=1)

        # Left frame
        left_frame = tk.Frame(master)
        left_frame.grid(row=0, column=0, padx=5, pady=5, sticky=tk.NS)


        # Create the status text
        status_label = tk.Frame(left_frame)
        tk.Label(status_label, text="Status:").pack(side=tk.LEFT)
        self.status_text = tk.Label(status_label, text="Inactive", fg="red")
        self.status_text.pack()
        status_label.pack(anchor=tk.NW)

        # Create the website chooser radio buttons
        self.website = tk.StringVar(value="chesscom")
        self.chesscom_radio_button = tk.Radiobutton(
            left_frame,
            text="Chess.com",
            variable=self.website,
            value="chesscom"
        )
        self.chesscom_radio_button.pack(anchor=tk.NW)
        self.lichess_radio_button = tk.Radiobutton(
            left_frame,
            text="Lichess.org",
            variable=self.website,
            value="lichess"
        )
        self.lichess_radio_button.pack(anchor=tk.NW)

        # Create the open browser button
        self.opening_browser = False
        self.opened_browser = False
        self.open_browser_button = tk.Button(
            left_frame,
            text="Open Browser",
            command=self.on_open_browser_button_listener,
        )
        self.open_browser_button.pack(anchor=tk.NW)

        # Create the start button
        self.running = False
        self.start_button = tk.Button(
            left_frame, text="Start", command=self.on_start_button_listener
        )
        self.start_button["state"] = "disabled"
        self.start_button.pack(anchor=tk.NW, pady=5)

        # Create the manual mode checkbox
        self.enable_manual_mode = tk.BooleanVar(value=False)
        self.manual_mode_checkbox = tk.Checkbutton(
            left_frame,
            text="Manual Mode",
            variable=self.enable_manual_mode,
            command=self.on_manual_mode_checkbox_listener,
        )
        self.manual_mode_checkbox.pack(anchor=tk.NW)

        # Create the manual mode instructions
        self.manual_mode_frame = tk.Frame(left_frame)
        self.manual_mode_label = tk.Label(
            self.manual_mode_frame, text="\u2022 Press 3 to make the best move"
        )
        self.manual_mode_label.pack(anchor=tk.NW)
        tk.Label(self.manual_mode_frame, text="\u2022 Best (Green), 2nd (Blue), 3rd (Yellow)").pack(anchor=tk.NW)

        # Create the main display frame for manual mode
        self.manual_mode_display_frame = tk.Frame(left_frame)
        
        # --- Top Sequences Section (Now the only display) ---
        self.sequences_frame = tk.Frame(self.manual_mode_display_frame)
        tk.Label(self.sequences_frame, text="Top Moves / Sequences:", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.NW)
        
        self.sequence_vars = [tk.BooleanVar(value=False) for _ in range(3)]
        self.top_sequence_toggles = []
        self.top_sequence_labels = []

        for i in range(3):
            # Using a Checkbutton styled as a Toolbutton for the expand/collapse toggle
            var = self.sequence_vars[i]
            toggle = ttk.Checkbutton(self.sequences_frame, text="", variable=var, 
                                     command=lambda i=i: self.toggle_sequence_label(i), 
                                     style="Toolbutton")
            # Using justify=tk.LEFT for the sequence label and increased wraplength
            label = tk.Label(self.sequences_frame, text="", font=("Consolas", 9), wraplength=200, justify=tk.LEFT)
            
            # Pack the toggle; the label is packed/unpacked by the command
            toggle.pack(anchor=tk.NW, fill='x', pady=(5,0) if i == 0 else (2,0)) 
            
            self.top_sequence_toggles.append(toggle)
            self.top_sequence_labels.append(label)

            toggle.pack_forget() # Hide initially
        
        # Pack the sequences_frame directly into the main display frame
        self.sequences_frame.pack(anchor=tk.NW, pady=(5, 0), fill='x')
        
        # self.manual_mode_display_frame is packed/unpacked in on_manual_mode_checkbox_listener

        # Create the mouseless mode checkbox
        self.enable_mouseless_mode = tk.BooleanVar(value=False)
        self.mouseless_mode_checkbox = tk.Checkbutton(
            left_frame,
            text="Mouseless Mode",
            variable=self.enable_mouseless_mode
        )
        self.mouseless_mode_checkbox.pack(anchor=tk.NW)

        # Create the non-stop puzzles check button
        self.enable_non_stop_puzzles = tk.IntVar(value=0)
        self.non_stop_puzzles_check_button = tk.Checkbutton(
            left_frame,
            text="Non-stop puzzles",
            variable=self.enable_non_stop_puzzles
        )
        self.non_stop_puzzles_check_button.pack(anchor=tk.NW)

        # Create the non-stop matches check button
        self.enable_non_stop_matches = tk.IntVar(value=0)
        self.non_stop_matches_check_button = tk.Checkbutton(left_frame, text="Non-stop online matches",
                                                            variable=self.enable_non_stop_matches)
        self.non_stop_matches_check_button.pack(anchor=tk.NW)

        # Create the bongcloud check button
        self.enable_bongcloud = tk.IntVar()
        self.bongcloud_check_button = tk.Checkbutton(
            left_frame,
            text="Bongcloud",
            variable=self.enable_bongcloud
        )
        self.bongcloud_check_button.pack(anchor=tk.NW)

        # Create the mouse latency scale
        mouse_latency_frame = tk.Frame(left_frame)
        tk.Label(mouse_latency_frame, text="Mouse Latency (seconds)").pack(side=tk.LEFT, pady=(17, 0))
        self.mouse_latency = tk.DoubleVar(value=0.0)
        self.mouse_latency_scale = tk.Scale(mouse_latency_frame, from_=0.0, to=5, resolution=0.2, orient=tk.HORIZONTAL,
                                          variable=self.mouse_latency)
        self.mouse_latency_scale.pack()
        mouse_latency_frame.pack(anchor=tk.NW)

        # Separator
        separator_frame = tk.Frame(left_frame, height=20)
        separator_frame.pack(anchor=tk.NW, pady=10, expand=True, fill=tk.X)
        separator = ttk.Separator(separator_frame, orient="horizontal")
        separator.place(x=0, y=10, relwidth=1)
        label = tk.Label(separator_frame, text="Stockfish parameters", background=left_frame.cget('bg'))
        label.place(relx=0.5, y=10, anchor='center')

        # Create the Slow mover entry field
        slow_mover_frame = tk.Frame(left_frame)
        self.slow_mover_label = tk.Label(slow_mover_frame, text="Slow Mover")
        self.slow_mover_label.pack(side=tk.LEFT)
        self.slow_mover = tk.IntVar(value=100)
        self.slow_mover_entry = tk.Entry(
            slow_mover_frame, textvariable=self.slow_mover, justify="center", width=8
        )
        self.slow_mover_entry.pack()
        slow_mover_frame.pack(anchor=tk.NW)

        # Create the skill level scale
        skill_level_frame = tk.Frame(left_frame)
        tk.Label(skill_level_frame, text="Skill Level").pack(side=tk.LEFT, pady=(19, 0))
        self.skill_level = tk.IntVar(value=20)
        self.skill_level_scale = tk.Scale(
            skill_level_frame,
            from_=0,
            to=20,
            orient=tk.HORIZONTAL,
            variable=self.skill_level,
        )
        self.skill_level_scale.pack()
        skill_level_frame.pack(anchor=tk.NW)

        # Create the Stockfish depth scale
        stockfish_depth_frame = tk.Frame(left_frame)
        tk.Label(stockfish_depth_frame, text="Depth").pack(side=tk.LEFT, pady=19)
        self.stockfish_depth = tk.IntVar(value=15)
        self.stockfish_depth_scale = tk.Scale(
            stockfish_depth_frame,
            from_=1,
            to=20,
            orient=tk.HORIZONTAL,
            variable=self.stockfish_depth,
        )
        self.stockfish_depth_scale.pack()
        stockfish_depth_frame.pack(anchor=tk.NW)

        # Create the memory entry field
        memory_frame = tk.Frame(left_frame)
        tk.Label(memory_frame, text="Memory").pack(side=tk.LEFT)
        self.memory = tk.IntVar(value=512)
        self.memory_entry = tk.Entry(
            memory_frame, textvariable=self.memory, justify="center", width=9
        )
        self.memory_entry.pack(side=tk.LEFT)
        tk.Label(memory_frame, text="MB").pack()
        memory_frame.pack(anchor=tk.NW, pady=(0, 15))

        # Create the CPU threads entry field
        cpu_threads_frame = tk.Frame(left_frame)
        tk.Label(cpu_threads_frame, text="CPU Threads").pack(side=tk.LEFT)
        self.cpu_threads = tk.IntVar(value=1)
        self.cpu_threads_entry = tk.Entry(
            cpu_threads_frame, textvariable=self.cpu_threads, justify="center", width=7
        )
        self.cpu_threads_entry.pack()
        cpu_threads_frame.pack(anchor=tk.NW)

        # Separator
        separator_frame = tk.Frame(left_frame, height=20)
        separator_frame.pack(anchor=tk.NW, pady=10, expand=True, fill=tk.X)
        separator = ttk.Separator(separator_frame, orient="horizontal")
        separator.place(x=0, y=10, relwidth=1)
        label = tk.Label(separator_frame, text="Misc", background=left_frame.cget('bg'))
        label.place(relx=0.5, y=10, anchor='center')

        # Create the topmost check button
        self.enable_topmost = tk.IntVar(value=1)
        self.topmost_check_button = tk.Checkbutton(
            left_frame,
            text="Window stays on top",
            variable=self.enable_topmost,
            onvalue=1,
            offvalue=0,
            command=self.on_topmost_check_button_listener,
        )
        self.topmost_check_button.pack(anchor=tk.NW)

        # Create the select stockfish button
        self.stockfish_path = ""
        self.select_stockfish_button = tk.Button(
            left_frame,
            text="Select Stockfish",
            command=self.on_select_stockfish_button_listener,
        )
        self.select_stockfish_button.pack(anchor=tk.NW)

        # Create the stockfish path text
        self.stockfish_path_text = tk.Label(left_frame, text="", wraplength=180)
        self.stockfish_path_text.pack(anchor=tk.NW)

        # Right frame
        right_frame = tk.Frame(master)
        right_frame.grid(row=0, column=1, padx=(0, 5), pady=5, sticky=tk.NSEW)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        # Top right frame for treeview and eval bar
        top_right_frame = tk.Frame(right_frame)
        top_right_frame.grid(row=0, column=0, sticky=tk.NSEW)
        top_right_frame.grid_rowconfigure(0, weight=1)
        top_right_frame.grid_columnconfigure(0, weight=1)
        
        # Treeview frame
        treeview_frame = tk.Frame(top_right_frame)
        treeview_frame.grid(row=0, column=0, sticky=tk.NSEW)
        treeview_frame.grid_rowconfigure(0, weight=1)
        treeview_frame.grid_columnconfigure(0, weight=1)

        # Create the moves Treeview
        # Removed "W E" and "B E" columns
        self.tree = ttk.Treeview(
            treeview_frame,
            columns=("#", "White", "Black"),
            show="headings",
            selectmode="browse",
        )
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)

        # Add the scrollbar to the Treeview
        self.vsb = ttk.Scrollbar(treeview_frame, orient="vertical", command=self.tree.yview)
        self.vsb.grid(row=0, column=1, sticky=tk.NS)
        self.tree.configure(yscrollcommand=self.vsb.set)

        # Create the columns
        self.tree.column("#", anchor=tk.CENTER, width=35, stretch=False)
        self.tree.heading("#", text="#")
        self.tree.column("White", anchor=tk.W, width=100, stretch=True)
        self.tree.heading("White", text="White")
        self.tree.column("Black", anchor=tk.W, width=100, stretch=True)
        self.tree.heading("Black", text="Black")
        # Removed "W E" and "B E" column definitions

        # Create the evaluation bar using a Canvas for a modern look
        self.eval_bar_canvas = tk.Canvas(top_right_frame, width=30, highlightthickness=1, highlightbackground="gray")
        self.eval_bar_canvas.grid(row=0, column=1, padx=(5, 0), sticky=tk.NS)
        self.eval_bar_canvas.bind("<Configure>", self.redraw_eval_bar)

        # Move Legend Frame - REMOVED
        # summary_frame = ttk.LabelFrame(right_frame, text="Move Legend")
        # ... all labels inside removed ...

        # Create the export PGN button
        self.export_pgn_button = tk.Button(
            right_frame, text="Export PGN", command=self.on_export_pgn_button_listener
        )
        # Adjust grid row to account for removed legend
        self.export_pgn_button.grid(row=1, column=0, sticky=tk.EW, pady=(5,0)) # Was row 2

        # Start the process checker thread
        process_checker_thread = threading.Thread(target=self.process_checker_thread)
        process_checker_thread.start()

        # Start the browser checker thread
        browser_checker_thread = threading.Thread(target=self.browser_checker_thread)
        browser_checker_thread.start()

        # Start the process communicator thread
        process_communicator_thread = threading.Thread(target=self.process_communicator_thread)
        process_communicator_thread.start()

        # Start the keyboard listener thread
        keyboard_listener_thread = threading.Thread(target=self.keypress_listener_thread)
        keyboard_listener_thread.start()

    def on_close_listener(self):
        self.exit = True
        self.master.destroy()

    def process_checker_thread(self):
        while not self.exit:
            if (
                self.running
                and self.stockfish_bot_process is not None
                and not self.stockfish_bot_process.is_alive()
            ):
                self.on_stop_button_listener()
                if self.restart_after_stopping:
                    self.restart_after_stopping = False
                    self.on_start_button_listener()
            time.sleep(0.1)

    def browser_checker_thread(self):
        while not self.exit:
            try:
                if (
                    self.opened_browser
                    and self.chrome is not None
                    and "target window already closed"
                    in self.chrome.get_log("driver")[-1]["message"]
                ):
                    self.opened_browser = False
                    self.open_browser_button["text"] = "Open Browser"
                    self.open_browser_button["state"] = "normal"
                    self.open_browser_button.update()
                    self.on_stop_button_listener()
                    self.chrome = None
            except IndexError:
                pass
            time.sleep(0.1)

    def process_communicator_thread(self):
        while not self.exit:
            try:
                if (
                    self.stockfish_bot_pipe is not None
                    and self.stockfish_bot_pipe.poll()
                ):
                    data = self.stockfish_bot_pipe.recv()
                    if isinstance(data, dict):
                        msg_type = data.get('type')
                        if msg_type == 'TOP_MOVES':
                            self.update_top_moves_display(data.get('data', []))
                        elif msg_type == 'EVAL':
                            self.update_eval_bar(data.get('data'))
                        elif msg_type == 'PLAYER_COLOR':
                            self.player_is_white = data.get('data')
                            self.redraw_eval_bar()
                        elif msg_type == 'MOVE':
                            move_data = data.get('data')
                            if move_data:
                                move_str = move_data.get('move')
                                if move_str: # Ensure move_str is not None
                                    self.match_moves.append(move_str)
                                    self.insert_move(move_str) # Pass only the move string
                        # Removed 'MOVE_COUNTS' handler
                    elif data == "START":
                        self.clear_tree()
                        self.match_moves = []
                        # self.reset_summary_display() # Removed
                        if self.enable_manual_mode.get() == 1:
                            self.update_top_moves_display([])
                        self.status_text["text"] = "Running"
                        self.status_text["fg"] = "green"
                        self.status_text.update()
                        self.start_button["text"] = "Stop"
                        self.start_button["state"] = "normal"
                        self.start_button["command"] = self.on_stop_button_listener
                        self.start_button.update()
                    elif data[:7] == "RESTART":
                        self.restart_after_stopping = True
                        self.stockfish_bot_pipe.send("DELETE")
                    elif data[:6] == "M_MOVE":
                        moves = data[6:].split(",")
                        self.match_moves += moves
                        self.set_moves(moves)
                    elif data[:7] == "ERR_EXE":
                        tk.messagebox.showerror("Error", "Stockfish path provided is not valid!")
                    elif data[:8] == "ERR_PERM":
                        tk.messagebox.showerror("Error", "Stockfish path provided is not executable!")
                    elif data[:9] == "ERR_BOARD":
                        tk.messagebox.showerror("Error", "Cant find board!")
                    elif data[:9] == "ERR_COLOR":
                        tk.messagebox.showerror("Error", "Cant find player color!")
                    elif data[:9] == "ERR_MOVES":
                        tk.messagebox.showerror("Error", "Cant find moves list!")
                    elif data[:12] == "ERR_GAMEOVER":
                        tk.messagebox.showerror("Error", "Game has already finished!")
            except (BrokenPipeError, OSError, EOFError):
                self.stockfish_bot_pipe = None
            time.sleep(0.1)

    def keypress_listener_thread(self):
        while not self.exit:
            time.sleep(0.1)
            if not self.opened_browser:
                continue
            try:
                if keyboard.is_pressed("1"):
                    self.on_start_button_listener()
                elif keyboard.is_pressed("2"):
                    self.on_stop_button_listener()
            except ImportError: # keyboard lib may not be installed
                pass

    def on_open_browser_button_listener(self):
        self.opening_browser = True
        self.open_browser_button["text"] = "Opening Browser..."
        self.open_browser_button["state"] = "disabled"
        self.open_browser_button.update()
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('useAutomationExtension', False)
        try:
            # Reverting to the previous method for initializing ChromeService
            chrome_install = ChromeDriverManager().install()
            folder = os.path.dirname(chrome_install)
            chromedriver_path = os.path.join(folder, "chromedriver.exe") if os.name == 'nt' else "chromedriver"
            service = ChromeService(os.path.join(folder, chromedriver_path))
            self.chrome = webdriver.Chrome(service=service, options=options)
        except WebDriverException:
            self.opening_browser = False
            self.open_browser_button["text"] = "Open Browser"
            self.open_browser_button["state"] = "normal"
            self.open_browser_button.update()
            tk.messagebox.showerror("Error", "Cant find Chrome. You need to have Chrome installed for this to work.")
            return
        except Exception as e:
            self.opening_browser = False
            self.open_browser_button["text"] = "Open Browser"
            self.open_browser_button["state"] = "normal"
            self.open_browser_button.update()
            tk.messagebox.showerror("Error", f"An error occurred while opening the browser: {e}")
            return
        if self.website.get() == "chesscom":
            self.chrome.get("https://www.chess.com")
        else:
            self.chrome.get("https://www.lichess.org")
        self.chrome_url = self.chrome.service.service_url
        self.chrome_session_id = self.chrome.session_id
        self.opening_browser = False
        self.opened_browser = True
        self.open_browser_button["text"] = "Browser is open"
        self.open_browser_button["state"] = "disabled"
        self.open_browser_button.update()
        self.start_button["state"] = "normal"
        self.start_button.update()

    def on_start_button_listener(self):
        slow_mover = self.slow_mover.get()
        if slow_mover < 10 or slow_mover > 1000:
            tk.messagebox.showerror("Error", "Slow Mover must be between 10 and 1000")
            return
        if self.stockfish_path == "":
            tk.messagebox.showerror("Error", "Stockfish path is empty")
            return
        if self.enable_mouseless_mode.get() == 1 and self.website.get() == "chesscom":
            tk.messagebox.showerror("Error", "Mouseless mode is only supported on lichess.org")
            return
        parent_conn, child_conn = multiprocess.Pipe()
        self.stockfish_bot_pipe = parent_conn
        st_ov_queue = multiprocess.Queue()
        self.stockfish_bot_process = StockfishBot(
            self.chrome_url, self.chrome_session_id, self.website.get(), child_conn, st_ov_queue,
            self.stockfish_path, self.enable_manual_mode.get() == 1, self.enable_mouseless_mode.get() == 1,
            self.enable_non_stop_puzzles.get() == 1, self.enable_non_stop_matches.get() == 1,
            self.mouse_latency.get(), self.enable_bongcloud.get() == 1, self.slow_mover.get(),
            self.skill_level.get(), self.stockfish_depth.get(), self.memory.get(), self.cpu_threads.get(),
        )
        self.stockfish_bot_process.start()
        self.overlay_screen_process = multiprocess.Process(target=run, args=(st_ov_queue,))
        self.overlay_screen_process.start()
        self.running = True
        self.start_button["text"] = "Starting..."
        self.start_button["state"] = "disabled"
        self.start_button.update()

    def on_stop_button_listener(self):
        if self.stockfish_bot_process is not None and self.stockfish_bot_process.is_alive():
            self.stockfish_bot_process.kill()
        self.stockfish_bot_process = None
        if self.stockfish_bot_pipe is not None:
            self.stockfish_bot_pipe.close()
            self.stockfish_bot_pipe = None
        if self.overlay_screen_process is not None and self.overlay_screen_process.is_alive():
            self.overlay_screen_process.kill()
        self.overlay_screen_process = None
        if self.enable_manual_mode.get() == 1:
            self.update_top_moves_display([])
        self.player_is_white = None
        self.update_eval_bar(None)
        # self.reset_summary_display() # Removed
        self.running = False
        self.status_text["text"] = "Inactive"
        self.status_text["fg"] = "red"
        self.status_text.update()
        self.start_button["text"] = "Start"
        if self.opened_browser:
            self.start_button["state"] = "normal"
        self.start_button["command"] = self.on_start_button_listener
        self.start_button.update()

    def on_topmost_check_button_listener(self):
        self.master.attributes("-topmost", self.enable_topmost.get() == 1)

    def on_export_pgn_button_listener(self):
        f = filedialog.asksaveasfile(
            initialfile="match.pgn", defaultextension=".pgn",
            filetypes=[("Portable Game Notation", "*.pgn"), ("All Files", "*.*")],
        )
        if f is None:
            return
        data = ""
        for i in range(len(self.match_moves) // 2 + 1):
            if len(self.match_moves) % 2 == 0 and i == len(self.match_moves) // 2:
                continue
            data += str(i + 1) + ". "
            data += self.match_moves[i * 2] + " "
            if (i * 2) + 1 < len(self.match_moves):
                data += self.match_moves[i * 2 + 1] + " "
        f.write(data)
        f.close()

    def on_select_stockfish_button_listener(self):
        f = filedialog.askopenfilename()
        if f:
            self.stockfish_path = f
            self.stockfish_path_text["text"] = os.path.basename(f)

    def clear_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.yview_moveto(0)

    def insert_move(self, move):
        # Changed signature to accept only move string
        # Removed symbol logic
        
        children = self.tree.get_children()
        
        # Updated check to index 2 for "Black" column
        is_white_move = not children or (len(self.tree.item(children[-1])["values"]) > 2 and self.tree.item(children[-1])["values"][2] != "")


        if is_white_move:
            move_number = len(children) + 1
            # Updated values tuple
            self.tree.insert("", "end", values=(move_number, move, ""))
        else:
            last_item = children[-1]
            self.tree.set(last_item, column="Black", value=move)
            # Removed set for "B E"
            
        self.tree.yview_moveto(1)

    def set_moves(self, moves):
        self.clear_tree()
        pairs = list(zip(*[iter(moves)] * 2))
        for i, pair in enumerate(pairs):
            # Updated values tuple
            self.tree.insert("", "end", values=(str(i + 1), pair[0], pair[1]))
        if len(moves) % 2 == 1:
            # Updated values tuple
            self.tree.insert("", "end", values=(len(pairs) + 1, moves[-1], ""))
        self.tree.yview_moveto(1)

    def on_manual_mode_checkbox_listener(self):
        if self.enable_manual_mode.get() == 1:
            self.manual_mode_frame.pack(after=self.manual_mode_checkbox, anchor=tk.NW)
            # Pack the new main container
            self.manual_mode_display_frame.pack(after=self.manual_mode_frame, anchor=tk.NW, pady=5, padx=5, fill='x')
        else:
            self.manual_mode_frame.pack_forget()
            self.manual_mode_display_frame.pack_forget()
            # Reset sequence vars when hiding manual mode
            for var in self.sequence_vars:
                var.set(False)
            self.update_top_moves_display([]) # This will clear all labels

    # NEW method to toggle individual sequence labels
    def toggle_sequence_label(self, index):
        if index >= len(self.last_top_moves_data):
            return # Should not happen, but as a safeguard

        label = self.top_sequence_labels[index]
        toggle_button = self.top_sequence_toggles[index]
        move_info = self.last_top_moves_data[index]
        base_text = f"{index+1}. {move_info['move']} ({move_info['eval']})"

        if self.sequence_vars[index].get():
            # Show the label right below its toggle button
            toggle_button['text'] = f"[-] {base_text}"
            label.pack(after=toggle_button, anchor=tk.NW, padx=(20, 0), fill='x') # Indent with padding
        else:
            toggle_button['text'] = f"[+] {base_text}"
            label.pack_forget()

    def update_top_moves_display(self, moves_data):
        self.last_top_moves_data = moves_data # Store the latest data

        for i in range(3):
            toggle_button = self.top_sequence_toggles[i]
            label = self.top_sequence_labels[i]
            var = self.sequence_vars[i]

            if i < len(moves_data):
                move_info = moves_data[i]
                base_text = f"{i+1}. {move_info['move']} ({move_info['eval']})"
                
                # 2. Update expandable "Top Sequences" list
                label['text'] = move_info['sequence']
                
                # Update text based on checked state
                if var.get():
                    toggle_button['text'] = f"[-] {base_text}"
                else:
                    toggle_button['text'] = f"[+] {base_text}"

                # Make the toggle button visible
                toggle_button.pack(anchor=tk.NW, fill='x', pady=(5,0) if i == 0 else (2,0))
                
                # Re-apply packing logic for the label
                if var.get():
                    label.pack(after=toggle_button, anchor=tk.NW, padx=(20, 0), fill='x')
                else:
                    label.pack_forget()
            else:
                # Clear and hide all widgets for this index
                toggle_button['text'] = ""
                label['text'] = ""
                var.set(False)
                toggle_button.pack_forget()
                label.pack_forget()

    def redraw_eval_bar(self, event=None):
        self.update_eval_bar(self.last_eval_data)
        
    # Removed reset_summary_display
    # Removed update_move_counts_display

    def update_eval_bar(self, eval_data):
        self.last_eval_data = eval_data
        canvas = self.eval_bar_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if height <= 1 or width <= 1:
            return

        white_color = "#F0D9B5"
        black_color = "#6A6866"
        white_rel_height = 0.5
        eval_string = "0.00"

        if eval_data:
            value_type = eval_data.get('type')
            value = eval_data.get('value')
            if value_type == 'mate':
                eval_string = f"M{abs(value)}"
                white_rel_height = 1.0 if value > 0 else 0.0
            elif value_type == 'cp':
                display_value = value if self.player_is_white is not False else -value
                eval_string = f"{display_value / 100.0:+.2f}"
                capped_value = max(min(value, 1000), -1000)
                advantage = math.tanh(capped_value / 400.0)
                white_rel_height = (advantage + 1) / 2.0
        
        white_bar_total_height = height * white_rel_height
        black_bar_total_height = height - white_bar_total_height

        player_is_white = self.player_is_white if self.player_is_white is not None else True
        
        if player_is_white:
            canvas.create_rectangle(0, 0, width, black_bar_total_height, fill=black_color, outline="")
            canvas.create_rectangle(0, black_bar_total_height, width, height, fill=white_color, outline="")
            text_y = black_bar_total_height + (white_bar_total_height / 2) if white_rel_height >= 0.5 else black_bar_total_height / 2
            text_color = "black" if white_rel_height >= 0.5 else "white"
        else:
            canvas.create_rectangle(0, 0, width, white_bar_total_height, fill=white_color, outline="")
            canvas.create_rectangle(0, white_bar_total_height, width, height, fill=black_color, outline="")
            text_y = white_bar_total_height / 2 if white_rel_height >= 0.5 else white_bar_total_height + (black_bar_total_height / 2)
            text_color = "black" if white_rel_height >= 0.5 else "white"
        
        outline_color = "white" if text_color == "black" else "black"
        x, y = width / 2, text_y
        # Create a more robust outline by drawing text in 4 directions
        canvas.create_text(x - 1, y, text=eval_string, font=("Arial", 9, "bold"), fill=outline_color, anchor='center')
        canvas.create_text(x + 1, y, text=eval_string, font=("Arial", 9, "bold"), fill=outline_color, anchor='center')
        canvas.create_text(x, y - 1, text=eval_string, font=("Arial", 9, "bold"), fill=outline_color, anchor='center')
        canvas.create_text(x, y + 1, text=eval_string, font=("Arial", 9, "bold"), fill=outline_color, anchor='center')
        # Draw the main text on top
        canvas.create_text(x, y, text=eval_string, font=("Arial", 9, "bold"), fill=text_color, anchor='center')


if __name__ == "__main__":
    multiprocess.freeze_support()
    window = tk.Tk()
    my_gui = GUI(window)
    window.mainloop()


