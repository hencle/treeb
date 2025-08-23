from flask import Flask, render_template, request, jsonify
from pathlib import Path
from typing import Optional, List # Optional for type hints, List might be needed for older 3.9 versions if list[] fails
import json
import os
import tiktoken

# --- Attempt to import tkinter and set a flag ---
TKINTER_AVAILABLE = False
TKINTER_IMPORT_ERROR_MESSAGE = ""
try:
    from tkinter import Tk, filedialog
    _test_root = Tk()
    _test_root.withdraw()
    _test_root.destroy()
    TKINTER_AVAILABLE = True
except ImportError as e:
    TKINTER_IMPORT_ERROR_MESSAGE = f"Python 'tkinter' module not found. Directory Browse feature will be disabled. Please install python3-tk (or equivalent for your OS). Error: {e}"
    print(f"WARNING: {TKINTER_IMPORT_ERROR_MESSAGE}")
except Exception as e:
    # This can catch _tkinter.TclError: couldn't connect to display
    TKINTER_IMPORT_ERROR_MESSAGE = f"Could not initialize tkinter (e.g., no display available or other TclError: {e}). Directory Browse feature will be disabled."
    print(f"WARNING: {TKINTER_IMPORT_ERROR_MESSAGE}")

app = Flask(__name__)

# --- Configuration ---
APP_ROOT = Path(__file__).resolve().parent
INITIAL_ROOT_DIR = APP_ROOT

# --- Preset Directory Configuration ---
PRESET_BASE_DIR = APP_ROOT / "presets"

SELECTION_PRESET_BASE_DIR = PRESET_BASE_DIR / "selections"
DEFAULT_SELECTION_PRESETS_DIR = SELECTION_PRESET_BASE_DIR / "default"
USER_SELECTION_PRESETS_DIR = PRESET_BASE_DIR / "user" # Corrected from PRESET_BASE_DIR to USER_SELECTION_PRESETS_DIR

EXCLUSION_PRESET_BASE_DIR = PRESET_BASE_DIR / "exclusions"
DEFAULT_EXCLUSION_PRESETS_DIR = EXCLUSION_PRESET_BASE_DIR / "default"

# Create necessary preset directories
for p_dir in [PRESET_BASE_DIR, SELECTION_PRESET_BASE_DIR, DEFAULT_SELECTION_PRESETS_DIR,
              USER_SELECTION_PRESETS_DIR, EXCLUSION_PRESET_BASE_DIR,
              DEFAULT_EXCLUSION_PRESETS_DIR]:
    p_dir.mkdir(exist_ok=True)

# --- Default Exclusion Data (Master Definition for system_defaults.json) ---
class DefaultExclusionData:
    DIRS = [".git", ".venv", "venv", ".env", "env", "node_modules", ".next", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", "target", "out", "site", ".vscode", ".idea"]
    FILES = [".DS_Store", "Thumbs.db", ".env"] # .env file specifically
    PATTERNS = ["*.pyc", "*.pyo", "*.swp", "*.swo", "*.swn", "*.log", "*.tmp", "*.temp", "*ignore", "*.lock"]

# --- Function to Load Initial Active Exclusions ---
def load_or_create_initial_exclusions() -> dict:
    default_exclusion_file_path = DEFAULT_EXCLUSION_PRESETS_DIR / "system_defaults.json"
    rules_from_code = {
        "description": "System default exclusions (source: app.py DefaultExclusionData). Applied at startup.",
        "dirs": list(DefaultExclusionData.DIRS),
        "files": list(DefaultExclusionData.FILES),
        "patterns": list(DefaultExclusionData.PATTERNS)
    }

    if default_exclusion_file_path.exists():
        try:
            with open(default_exclusion_file_path, 'r', encoding='utf-8') as f:
                loaded_rules = json.load(f)
            if all(key in loaded_rules for key in ["description", "dirs", "files", "patterns"]) and \
               isinstance(loaded_rules["dirs"], list) and \
               isinstance(loaded_rules["files"], list) and \
               isinstance(loaded_rules["patterns"], list):
                app.logger.info(f"Loaded active exclusion rules from {default_exclusion_file_path}")
                return loaded_rules
            else:
                app.logger.warning(f"File {default_exclusion_file_path} has invalid structure. Using internal defaults and attempting to recreate file.")
        except Exception as e:
            app.logger.error(f"Error loading {default_exclusion_file_path}: {e}. Using internal defaults and attempting to recreate file.")

    app.logger.info(f"Using internal DefaultExclusionData. Creating/overwriting {default_exclusion_file_path} for user reference.")
    try:
        DEFAULT_EXCLUSION_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        with open(default_exclusion_file_path, 'w', encoding='utf-8') as f:
            json.dump(rules_from_code, f, indent=2)
        app.logger.info(f"Created/Updated default exclusion file: {default_exclusion_file_path}")
    except Exception as e:
        app.logger.error(f"Could not create/update default exclusion file {default_exclusion_file_path}: {e}")
    return rules_from_code

ACTIVE_EXCLUSION_RULES = load_or_create_initial_exclusions()


# --- Tiktoken Configuration & LLM Context ---
TIKTOKEN_ENCODING_NAME = "cl100k_base"
ENCODING = None
try:
    ENCODING = tiktoken.get_encoding(TIKTOKEN_ENCODING_NAME)
    app.logger.info(f"Successfully loaded tiktoken encoding: {TIKTOKEN_ENCODING_NAME}")
except Exception as e:
    app.logger.error(f"Could not load tiktoken encoding '{TIKTOKEN_ENCODING_NAME}': {e}.")
MODEL_CONTEXT_INFO = [
    {"id": "gpt4o", "displayName": "4o", "window": 128000},
    {"id": "claude3o", "displayName": "o3", "window": 200000},
    {"id": "gemini25pro", "displayName": "G2.5", "window": 1048576},
    {"id": "grok3", "displayName": "G3", "window": 1000000},
    {"id": "grok4", "displayName": "G4", "window": 256000},
    {"id": "gpt41", "displayName": "4.1", "window": 32768},
]
# ------------------------------------------------------------------

# ------------------------------------------------------------------ HELPER FUNCTIONS

def get_selection_preset_path(name: str, preset_type: str) -> Optional[Path]:
    """Return the JSON preset file path for a given name/type, or None if invalid."""
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        return None

    if preset_type == "default":
        base_dir = DEFAULT_SELECTION_PRESETS_DIR
    elif preset_type == "user":
        base_dir = USER_SELECTION_PRESETS_DIR
    else:
        return None

    return base_dir / f"{safe_name}.json"

def check_if_item_is_excluded(item: Path, rules: dict) -> Optional[dict]: # MODIFIED HERE
    """Checks if a single item matches exclusion rules based on its name and type."""
    if item.is_dir():
        if item.name in rules.get("dirs", []):
            return {"type": "Directory Name", "rule": item.name}
        for pattern in rules.get("patterns", []): # Patterns can match directory names too
            if item.match(pattern): # Path.match is available in Python 3.5+
                return {"type": "Directory Pattern", "rule": pattern}
    elif item.is_file():
        if item.name in rules.get("files", []):
            return {"type": "File Name", "rule": item.name}
        for pattern in rules.get("patterns", []):
            if item.match(pattern): # Path.match is available in Python 3.5+
                return {"type": "File Pattern", "rule": pattern}
    return None

# --- Lazy Loading Tree Node Builder ---
def dir_to_js_lazy(item: Path) -> dict:
    global ACTIVE_EXCLUSION_RULES
    try:
        if not item.exists():
            return {"id": str(item), "text": f"{item.name} (Not Found)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}

        exclusion_info = check_if_item_is_excluded(item, ACTIVE_EXCLUSION_RULES)
        node_text = item.name if item.name else str(item)
        item_abs_path_str = str(item.resolve())

        jstree_node_data = {"excluded_info": exclusion_info}

        if item.is_dir():
            return {
                "id": item_abs_path_str,
                "text": node_text,
                "children": True,
                "type": "folder",
                "data": jstree_node_data
            }
        else:  # File
            return {
                "id": item_abs_path_str,
                "text": node_text,
                "icon": "jstree-file",
                "type": "file",
                "children": False,
                "data": jstree_node_data
            }
    except Exception as e:
        app.logger.error(f"Error processing path {item} for lazy tree node: {e}")
        return {"id": str(item), "text": f"{item.name} (Processing Error)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}


def build_nested_dict(paths: List[Path], root_for_display: Path) -> dict: # Used List[Path] for clarity for 3.9
    tree = {}
    resolved_root_for_display = root_for_display.resolve()
    for p in paths:
        try:
            abs_p = p.resolve()
            if resolved_root_for_display in abs_p.parents or resolved_root_for_display == abs_p:
                 rel_parts = abs_p.relative_to(resolved_root_for_display).parts
                 if not rel_parts:
                     rel_parts = (abs_p.name,) if abs_p.name else (str(abs_p),)
            else:
                 rel_parts = (abs_p.name,) if abs_p.name else (str(abs_p),)

        except ValueError:
            rel_parts = (p.name if p.name else str(p),)
        except Exception as e:
            app.logger.error(f"Path resolution error in build_nested_dict for {p} relative to {root_for_display}: {e}")
            rel_parts = (p.name + " (path error)",)

        cursor = tree
        for part in rel_parts:
            cursor = cursor.setdefault(part, {})
    return tree

def ascii_tree(d: dict, prefix: str = "") -> List[str]: # Used List[str] and dict
    lines = []
    items = list(d.items())
    for i, (name, child) in enumerate(items):
        is_last = i == (len(items) - 1)
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + name)
        if child:
            extension = "    " if is_last else "│   "
            lines.extend(ascii_tree(child, prefix + extension))
    return lines

# ------------------------------------------------------------------ ROUTES
@app.route("/")
def index():
    return render_template("index.html",
                           initial_path=str(INITIAL_ROOT_DIR),
                           tkinter_available=TKINTER_AVAILABLE)

@app.route('/api/browse-for-directory', methods=['GET'])
def browse_for_directory_api():
    if not TKINTER_AVAILABLE:
        app.logger.warning(f"Browse directory attempt failed: tkinter support not available. Original import error: {TKINTER_IMPORT_ERROR_MESSAGE}")
        user_error_message = "Directory Browse feature is disabled because the 'tkinter' Python module is not available or failed to initialize."
        if "module not found" in TKINTER_IMPORT_ERROR_MESSAGE.lower():
            user_error_message += " Please install python3-tk (or equivalent for your OS)."
        elif "display" in TKINTER_IMPORT_ERROR_MESSAGE.lower() or "tclerror" in TKINTER_IMPORT_ERROR_MESSAGE.lower():
             user_error_message += " Ensure a display environment is available (e.g., for Linux/WSL, ensure X11/WSLg is working)."

        return jsonify({"error": user_error_message, "selected_path": None}), 501

    try:
        # Re-import locally in case the initial global import failed but condition changed (unlikely but safer)
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        directory_path = filedialog.askdirectory(
            initialdir=str(INITIAL_ROOT_DIR), # Start Browse from a sensible default
            title="Select Root Directory for Treeb"
        )
        root.destroy()

        if directory_path:
            selected_path = str(Path(directory_path).resolve())
            return jsonify({"selected_path": selected_path})
        else:
            return jsonify({"selected_path": None}) # User cancelled
    except Exception as e:
        app.logger.error(f"Error opening directory dialog with tkinter: {e}")
        error_message = "Could not open directory dialog."
        if "display name" in str(e).lower() or "main window" in str(e).lower() or isinstance(e, NameError) and "Tk" in str(e):
            error_message += " Ensure a display environment is available (e.g., WSLg or X11 forwarding for Linux/WSL)."
        else:
            error_message += f" Unexpected error: {e}"
        return jsonify({"error": error_message, "selected_path": None}), 500

@app.get("/api/tree")
def api_tree():
    node_id_param = request.args.get("id")
    initial_path_param = request.args.get("path")

    current_scan_path = None

    if node_id_param == "#":
        path_str = initial_path_param if initial_path_param else str(INITIAL_ROOT_DIR)
        try:
            current_scan_path = Path(path_str).resolve()
        except Exception as e:
            app.logger.error(f"Invalid initial path resolution for '{path_str}': {e}")
            error_node = {"id": path_str, "text": f"{Path(path_str).name} (Invalid Path)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}
            return jsonify([error_node])

        if not current_scan_path.exists() or not current_scan_path.is_dir():
            display_name = current_scan_path.name if current_scan_path.name else str(current_scan_path)
            error_node = {"id": str(current_scan_path), "text": f"{display_name} (Not Found or Not a Dir)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}
            return jsonify([error_node])
        root_node_obj = dir_to_js_lazy(current_scan_path)
        return jsonify([root_node_obj])
    else:
        try:
            current_scan_path = Path(node_id_param).resolve()
        except Exception as e:
            app.logger.error(f"Invalid node ID path resolution for '{node_id_param}': {e}")
            return jsonify([])

        if not current_scan_path.is_dir():
            return jsonify([])

        children_nodes = []
        try:
            # Sort directories first, then files, all alphabetically
            items = sorted(list(current_scan_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
            for child_item in items:
                children_nodes.append(dir_to_js_lazy(child_item))
        except PermissionError:
            app.logger.warning(f"Permission denied while listing children of {current_scan_path}")
            # Optionally return a node indicating permission error to the UI
            # return jsonify([{"id": str(current_scan_path) + "_perm_denied", "text": "Permission Denied", "icon": "jstree-warning", "children": False, "type": "error", "data": {}}])
        except Exception as e:
            app.logger.error(f"Error listing children for {current_scan_path}: {e}")
        return jsonify(children_nodes)


@app.post("/api/flatten")
def api_flatten():
    global ACTIVE_EXCLUSION_RULES
    data = request.get_json(force=True) # Add force=True if content-type might be an issue
    raw_paths_from_client = data.get("paths", [])
    token_count = 0
    model_percentages = []

    resolved_paths_for_structure_set = set()
    files_to_process_set = set()

    initial_selection_nodes = []
    for p_str in raw_paths_from_client:
        try:
            path_item = Path(p_str).resolve()
        except Exception as e:
            app.logger.warning(f"Flatten: Invalid path string {p_str} from client: {e}. Skipping.")
            continue

        if not path_item.exists():
            app.logger.warning(f"Flatten: Selected path {p_str} (resolved to {path_item}) does not exist. Skipping.")
            continue

        exclusion_info = check_if_item_is_excluded(path_item, ACTIVE_EXCLUSION_RULES)
        if exclusion_info:
            app.logger.debug(f"Flatten: Directly selected item {path_item} is excluded by rule: {exclusion_info}. Skipping.")
            continue
        initial_selection_nodes.append(path_item)

    queue = list(initial_selection_nodes)
    visited_for_walk = set()

    while queue:
        current_path = queue.pop(0)

        if current_path in visited_for_walk and current_path.is_dir(): # Avoid re-processing dirs already fully walked
            continue
        
        if current_path.is_dir():
            visited_for_walk.add(current_path)

        # Crucially, items passed directly by user are added to structure/content regardless of their *own* exclusion,
        # UNLESS they were filtered out by `initial_selection_nodes` block above.
        # Exclusion rules primarily apply to *children* discovered during directory traversal.
        if current_path not in initial_selection_nodes: # Only check exclusion for *descendants*, not original selections
            exclusion_info = check_if_item_is_excluded(current_path, ACTIVE_EXCLUSION_RULES)
            if exclusion_info:
                app.logger.debug(f"Flatten: Traversed item {current_path} excluded by rule: {exclusion_info}. Skipping its children.")
                continue

        resolved_paths_for_structure_set.add(current_path) # Add all traversable, non-excluded items to structure

        if current_path.is_file():
            files_to_process_set.add(current_path)
        elif current_path.is_dir():
            try:
                # Sort children for consistent processing order
                children = sorted(list(current_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
                for child_item in children: # Add all children to queue; they'll be checked for exclusion when popped
                    queue.append(child_item)
            except PermissionError:
                app.logger.warning(f"Flatten: Permission error iterating directory {current_path}")
            except Exception as e:
                app.logger.error(f"Flatten: Error iterating directory {current_path}: {e}")

    if not resolved_paths_for_structure_set and not files_to_process_set:
        text_content = "No files or directories selected, or all selected items/contents are excluded by current rules."
        if ENCODING:
            try: tokens = ENCODING.encode(text_content, disallowed_special=()); token_count = len(tokens)
            except Exception as e: app.logger.error(f"Error tokenizing message: {e}")
        if token_count > 0: # Or >=0 if you want to show models even for 0 tokens
            for model in MODEL_CONTEXT_INFO:
                percentage = round((token_count / model["window"]) * 100, 2) if model["window"] > 0 else (100.0 if token_count > 0 else 0.0)
                model_percentages.append({"name": model["displayName"], "percentage": (0.01 if 0 < percentage < 0.01 else percentage)})
        return jsonify({"text": text_content, "token_count": token_count, "model_percentages": model_percentages})

    final_resolved_paths_for_structure = sorted(list(resolved_paths_for_structure_set), key=lambda p: str(p).lower())
    final_files_to_process = sorted(list(files_to_process_set), key=lambda p: str(p).lower())
    
    header = ""
    common_ancestor_for_tree = None
    if not final_resolved_paths_for_structure:
        header = "No valid paths for structure (after exclusion).\n\n"
    else:
        try:
            abs_path_strings_for_commonpath = [str(p.resolve()) for p in final_resolved_paths_for_structure]
            if not abs_path_strings_for_commonpath:
                 common_ancestor_for_tree = Path(".").resolve() # Fallback
            else:
                common_ancestor_str = os.path.commonpath(abs_path_strings_for_commonpath)
                common_ancestor_for_tree = Path(common_ancestor_str)
                if common_ancestor_for_tree.is_file(): # commonpath can return a file if all paths are that file
                    common_ancestor_for_tree = common_ancestor_for_tree.parent
        except ValueError: # commonpath raises ValueError if paths are on different drives (Windows)
            common_ancestor_for_tree = Path(".").resolve() # Fallback
        
        subset = build_nested_dict(final_resolved_paths_for_structure, common_ancestor_for_tree)
        
        header_root_name_display = ""
        if common_ancestor_for_tree:
            name_to_display = common_ancestor_for_tree.name
            # Handle cases where common_ancestor is root (e.g., '/', 'C:\') or '.'
            if not name_to_display or name_to_display == "." and str(common_ancestor_for_tree) != ".":
                name_to_display = str(common_ancestor_for_tree)
            elif name_to_display == "." and str(common_ancestor_for_tree) == ".":
                 name_to_display = "Selected Structure" # Or APP_ROOT.name or similar context
            header_root_name_display = f"{name_to_display}/\n" if name_to_display else "Selected Structure/\n"
        else: # Should ideally not happen if common_ancestor_for_tree is set
            header_root_name_display = "Selected Structure/\n"

        header = "code base:\n" + header_root_name_display + "\n".join(ascii_tree(subset)) + "\n\n"

    body_parts = ["Context files:\n"]
    if not final_files_to_process:
        body_parts.append("No files selected/accessible/found (after exclusion and directory expansion).\n")
    else:
        for f_path in final_files_to_process:
            display_f_path_str = ""
            try:
                if common_ancestor_for_tree and common_ancestor_for_tree.is_dir():
                    try:
                        # Attempt to make path relative to the common ancestor for display
                        display_f_path_str = str(f_path.relative_to(common_ancestor_for_tree))
                    except ValueError: # path is not under common_ancestor (e.g. different drive, or complex selection)
                        display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent and f_path.parent.name else f_path.name
                else: # Fallback if no good common_ancestor
                    display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent and f_path.parent.name else f_path.name

                content = f_path.read_text(encoding="utf-8", errors="replace")
                body_parts.append(f"{display_f_path_str}\n\"\"\"\n{content}\n\"\"\"\n\n")
            except UnicodeDecodeError:
                body_parts.append(f"{display_f_path_str}\n\"\"\"\n[binary file or undecodable content skipped]\n\"\"\"\n\n")
            except Exception as e:
                body_parts.append(f"{display_f_path_str}\n\"\"\"\n[Error reading file: {e}]\n\"\"\"\n\n")

    final_text = header + "".join(body_parts)
    if ENCODING:
        try:
            tokens = ENCODING.encode(final_text, disallowed_special=()) # Consider allowed_special if needed
            token_count = len(tokens)
        except Exception as e:
            app.logger.error(f"Error tokenizing final text: {e}")
            token_count = -1 # Indicate error
    else:
        app.logger.warning("Tiktoken encoding not available. Token count 0.")
        # token_count remains 0

    if token_count >= 0 : # Valid token count (0 or more)
        for model in MODEL_CONTEXT_INFO:
            if token_count == 0 and model["window"] == 0 : # Avoid division by zero if both are zero
                percentage = 0.0
            elif model["window"] == 0: # Model has "infinite" window or not applicable
                percentage = 100.0 if token_count > 0 else 0.0 # Full if there are tokens, else 0
            else:
                percentage = round((token_count / model["window"]) * 100, 2)
            
            # Ensure very small percentages are still visible (e.g., 0.01%)
            model_percentages.append({
                "name": model["displayName"],
                "percentage": (0.01 if 0 < percentage < 0.01 else percentage)
            })
    elif token_count == -1: # Tokenization error
        model_percentages.append({"name": "LLMs", "percentage": "N/A (Tokenization Error)"})


    return jsonify({"text": final_text, "token_count": token_count, "model_percentages": model_percentages})

# ---------------------------------------------------------- SELECTION PRESET ROUTES
@app.get("/api/presets")
def list_selection_presets_api():
    presets = []
    for p_file in sorted(DEFAULT_SELECTION_PRESETS_DIR.glob("*.json")): presets.append({"name": p_file.stem, "type": "default", "id": f"default/{p_file.stem}"})
    for p_file in sorted(USER_SELECTION_PRESETS_DIR.glob("*.json")): presets.append({"name": p_file.stem, "type": "user", "id": f"user/{p_file.stem}"})
    return jsonify(presets)

@app.get("/api/presets/<path:preset_id>")
def load_selection_preset_api(preset_id: str):
    try: preset_type, name = preset_id.split('/', 1)
    except ValueError: return jsonify({"error": "Invalid preset ID format."}), 400
    p = get_selection_preset_path(name, preset_type)
    if not p or not p.exists(): return jsonify({"error": f"Preset '{name}' of type '{preset_type}' not found"}), 404
    try:
        paths_from_preset_file = json.loads(p.read_text(encoding='utf-8'))
        resolved_absolute_paths = []
        if isinstance(paths_from_preset_file, list):
            for path_str_in_file in paths_from_preset_file:
                path_obj = Path(path_str_in_file)
                # If path is relative, it's assumed to be relative to APP_ROOT
                # If absolute, it's used as is.
                # Presets should ideally store paths relative to APP_ROOT or be very explicit about absolute paths.
                if not path_obj.is_absolute():
                    path_obj = (APP_ROOT / path_obj).resolve()
                else:
                    path_obj = path_obj.resolve() # Ensure absolute paths are also resolved (e.g. symlinks)
                resolved_absolute_paths.append(str(path_obj))
            return jsonify(resolved_absolute_paths)
        else: return jsonify({"error": "Invalid preset file format (expected a list of paths)"}), 500
    except json.JSONDecodeError as e: return jsonify({"error": f"Failed to parse preset JSON: {e}"}), 500
    except Exception as e: return jsonify({"error": f"Failed to load preset: {e}"}), 500

@app.post("/api/presets/<name>")
def save_selection_preset_api(name: str):
    preset_file_path = get_selection_preset_path(name, "user")
    if not preset_file_path: return jsonify({"error": "Invalid preset name (contains invalid characters or is empty)."}), 400
    data = request.get_json(force=True)
    absolute_paths_from_client = data.get("paths", []) # Expecting a list of absolute paths from client
    paths_to_save_in_preset = []

    app_root_resolved = APP_ROOT.resolve()
    for abs_path_str in absolute_paths_from_client:
        path_obj = Path(abs_path_str).resolve()
        try:
            # Try to make path relative to APP_ROOT for portability
            relative_path = path_obj.relative_to(app_root_resolved)
            paths_to_save_in_preset.append(str(relative_path))
        except ValueError:
            # If not relative to APP_ROOT (e.g. different drive, or outside structure), save the absolute path
            paths_to_save_in_preset.append(str(path_obj))
    try:
        preset_file_path.parent.mkdir(parents=True, exist_ok=True)
        preset_file_path.write_text(json.dumps(paths_to_save_in_preset, indent=2), encoding='utf-8')
        return jsonify({"saved": True, "id": f"user/{name}", "name": name, "type": "user"})
    except Exception as e: return jsonify({"error": f"Failed to save user preset: {e}"}), 500

@app.delete("/api/presets/<path:preset_id>")
def delete_selection_preset_api(preset_id: str):
    try: preset_type, name = preset_id.split('/', 1)
    except ValueError: return jsonify({"error": "Invalid preset ID format."}), 400
    if preset_type != "user": return jsonify({"error": "Only user presets can be deleted."}), 403
    p = get_selection_preset_path(name, "user")
    if not p: return jsonify({"error": "Invalid preset name for deletion."}), 400 # Should not happen if split was okay
    try:
        if p.exists():
            p.unlink()
            return jsonify({"deleted": True, "id": preset_id})
        else:
            return jsonify({"error": "User preset not found."}), 404
    except Exception as e: return jsonify({"error": f"Failed to delete preset: {e}"}), 500

if __name__ == "__main__":
    def create_default_selection_preset(preset_name: str, relative_paths_to_store: List[str]):
        preset_file = DEFAULT_SELECTION_PRESETS_DIR / f"{preset_name}.json"
        
        # Special handling for the "default" preset to ensure it exists, possibly empty
        if preset_name == "default" and not preset_file.exists():
            try:
                preset_file.parent.mkdir(parents=True, exist_ok=True)
                # Create it empty if paths are not provided or not valid for "default"
                preset_file.write_text(json.dumps(relative_paths_to_store if relative_paths_to_store else [], indent=2), encoding='utf-8')
                app.logger.info(f"Created empty default selection preset: {preset_file.name}")
            except Exception as e:
                app.logger.error(f"Could not create empty default preset {preset_file.name}: {e}")
            return # Exit after creating the 'default' preset

        # For other default presets (if any in future) or if 'default' exists and we want to populate it (though current logic creates it empty above)
        verified_paths_to_store = []
        for rel_path_str in relative_paths_to_store:
            abs_path = (APP_ROOT / Path(rel_path_str)).resolve() # Paths are relative to APP_ROOT
            if abs_path.exists():
                verified_paths_to_store.append(rel_path_str) # Store the original relative string
            else:
                app.logger.warning(f"Default preset '{preset_name}': path '{rel_path_str}' not found relative to APP_ROOT. Skipping.")

        if not preset_file.exists() and verified_paths_to_store: # Only create if it doesn't exist AND there's something to save
            try:
                preset_file.parent.mkdir(parents=True, exist_ok=True)
                preset_file.write_text(json.dumps(verified_paths_to_store, indent=2), encoding='utf-8')
                app.logger.info(f"Created default selection preset: {preset_file.name} with {len(verified_paths_to_store)} items.")
            except Exception as e:
                app.logger.error(f"Could not create default preset {preset_file.name}: {e}")
        elif preset_file.exists() and verified_paths_to_store: # If it exists, don't overwrite from this function, admin should manage it.
            app.logger.info(f"Default selection preset '{preset_file.name}' already exists. Not overwriting with verified paths.")
        elif not preset_file.exists() and not verified_paths_to_store and preset_name != "default": # Don't create if no valid paths unless it's the special "default"
            app.logger.info(f"Default selection preset '{preset_name}' not created as no verified paths were provided.")

    # Ensure a "default.json" selection preset exists (can be empty)
    create_default_selection_preset("default", [])
    # Example of creating another default preset if needed:
    # create_default_selection_preset("my_app_core_files", ["app.py", "static/js/main.js", "templates/index.html"])

    # Run the Flask app
    # Set host='0.0.0.0' to make it accessible from the network
    app.run(debug=True, port=5006, host='0.0.0.0')