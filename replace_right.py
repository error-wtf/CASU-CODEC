# Lines to generate the new right panel
# Read the player file and replace lines 399-416
with open("/repo/mpcasu_player.py", "r") as f:
    lines = f.readlines()

new_right = '''        right = tk.Frame(body, bg=PANEL, width=320); right.pack(side="right", fill="y", padx=(10, 0)); right.pack_propagate(False)
        self.right_shell = right
        rnb = ttk.Notebook(right)
        rnb.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        # --- Tab 1: FILE BROWSER ---
        fb_frame = tk.Frame(rnb, bg=PANEL)
        rnb.add(fb_frame, text="Files")
        fb_top = tk.Frame(fb_frame, bg=PANEL)
        fb_top.pack(fill="x", padx=6, pady=(6, 2))
        self._fb_search_var = tk.StringVar()
        self._fb_search_var.trace_add("write", lambda *_: self._refresh_file_browser())
        tk.Label(fb_top, text="⌕", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Entry(fb_top, textvariable=self._fb_search_var, width=18).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._fb_path_var = tk.StringVar(value=str(Path.home()))
        fb_path_entry = ttk.Entry(fb_frame, textvariable=self._fb_path_var, width=30)
        fb_path_entry.pack(fill="x", padx=6, pady=1)
        fb_path_entry.bind("<Return>", lambda _: self._refresh_file_browser())
        fb_nav = tk.Frame(fb_frame, bg=PANEL)
        fb_nav.pack(fill="x", padx=6, pady=1)
        ttk.Button(fb_nav, text="▲ Up", width=5, style="MPC.TButton", command=lambda: self._fb_navigate("..")).pack(side="left")
        ttk.Button(fb_nav, text="⌂ Home", width=5, style="MPC.TButton", command=lambda: (self._fb_path_var.set(str(Path.home())), self._refresh_file_browser())).pack(side="left", padx=3)
        ttk.Button(fb_nav, text="↻", width=3, style="MPC.TButton", command=self._refresh_file_browser).pack(side="right")
        self._fb_list = tk.Listbox(fb_frame, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self._fb_list.pack(fill="both", expand=True, padx=6, pady=(2, 4))
        self._fb_list.bind("<Double-Button-1>", lambda _: self._on_fb_activate())
        fb_status = tk.Frame(fb_frame, bg=PANEL)
        fb_status.pack(fill="x", padx=6, pady=(0, 4))
        self._fb_count_var = tk.StringVar(value="No folder selected")
        tk.Label(fb_status, textvariable=self._fb_count_var, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="left")
        ttk.Button(fb_status, text="＋ Add all", width=8, style="MPC.TButton", command=self._fb_add_all).pack(side="right")

        # --- Tab 2: DATABASE FINDER ---
        db_frame = tk.Frame(rnb, bg=PANEL)
        rnb.add(db_frame, text="Database")
        db_top = tk.Frame(db_frame, bg=PANEL)
        db_top.pack(fill="x", padx=6, pady=(6, 2))
        self._db_search_var = tk.StringVar()
        self._db_search_var.trace_add("write", lambda *_: self._refresh_db_finder())
        tk.Label(db_top, text="⌕", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Entry(db_top, textvariable=self._db_search_var, width=18).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._db_filter_var = tk.StringVar(value="all")
        db_filter_frame = tk.Frame(db_frame, bg=PANEL)
        db_filter_frame.pack(fill="x", padx=6, pady=1)
        for fname, fval in [("All","all"), ("Video","video"), ("Audio","audio"), ("CASU","casu"), ("Fav","fav")]:
            ttk.Radiobutton(db_filter_frame, text=fname, variable=self._db_filter_var, value=fval, command=self._refresh_db_finder).pack(side="left", padx=1)
        self._db_list = tk.Listbox(db_frame, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self._db_list.pack(fill="both", expand=True, padx=6, pady=(2, 4))
        self._db_list.bind("<Double-Button-1>", lambda _: self._add_db_selected())
        db_status = tk.Frame(db_frame, bg=PANEL)
        db_status.pack(fill="x", padx=6, pady=(0, 4))
        self._db_count_var = tk.StringVar(value="0 files · 0 shown")
        tk.Label(db_status, textvariable=self._db_count_var, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="left")
        ttk.Button(db_status, text="↻ Refresh", width=8, style="MPC.TButton", command=self._refresh_db_finder).pack(side="right")
        ttk.Button(db_status, text="＋ Add", width=5, style="MPC.TButton", command=self._add_db_selected).pack(side="right", padx=3)

        # --- Tab 3: PLAYLIST QUEUE ---
        pl_frame = tk.Frame(rnb, bg=PANEL)
        rnb.add(pl_frame, text="Queue")
        self._pl_search_var = tk.StringVar()
        self._pl_search_var.trace_add("write", lambda *_: self._render_playlist())
        pl_search_frame = tk.Frame(pl_frame, bg=PANEL)
        pl_search_frame.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(pl_search_frame, text="⌕", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Entry(pl_search_frame, textvariable=self._pl_search_var, width=18).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.queue = tk.Listbox(pl_frame, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.queue.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.queue.bind("<Double-Button-1>", self._play_queue_item)
        pl_actions = tk.Frame(pl_frame, bg=PANEL)
        pl_actions.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(pl_actions, text="↑", width=3, style="MPC.TButton", command=lambda: self.move_queue(-1)).pack(side="left")
        ttk.Button(pl_actions, text="↓", width=3, style="MPC.TButton", command=lambda: self.move_queue(1)).pack(side="left", padx=3)
        ttk.Button(pl_actions, text="Clear", style="MPC.TButton", command=self.clear_playlist).pack(side="right")
        ttk.Button(pl_actions, text="Save", style="MPC.TButton", command=self.save_playlist).pack(side="right", padx=3)
        pl_footer = tk.Frame(pl_frame, bg=PANEL)
        pl_footer.pack(fill="x", padx=6, pady=(0, 6))
        self._pl_count_var = tk.StringVar(value="0 items")
        tk.Label(pl_footer, textvariable=self._pl_count_var, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="left")
        tk.Label(pl_footer, text="SHUFFLE · REPEAT", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="right")
'''

# Replace lines 399-416 (0-indexed: 398-415)
start = 397  # 0-indexed, line 398
end = 416   # 0-indexed, line 416
new_lines = lines[:start] + [new_right + "\n"] + lines[end:]

with open("/repo/mpcasu_player.py", "w") as f:
    f.writelines(new_lines)

print("Right panel replaced")
import os
print(f"File size: {os.path.getsize('/repo/mpcasu_player.py')}")
