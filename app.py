# treeb/app.py
from flask import Flask, render_template, request, jsonify
from pathlib import Path
import json
import os
import tiktoken

# --- Attempt to import tkinter and set a flag ---
TKINTER_AVAILABLE = False
TKINTER_IMPORT_ERROR_MESSAGE = ""
try:
    from tkinter import Tk, filedialog
    # Test if a basic Tk window can be initialized (catches "no display name" errors early on some systems)
    _test_root = Tk()
    _test_root.withdraw()
    _test_root.destroy()
    TKINTER_AVAILABLE = True
except ImportError as e:
    TKINTER_IMPORT_ERROR_MESSAGE = f"Python 'tkinter' module not found. Directory Browse feature will be disabled. Please install python3-tk (or equivalent for your OS). Error: {e}"
    print(f"WARNING: {TKINTER_IMPORT_ERROR_MESSAGE}")
except Exception as e: # Catches other errors like TclError if display is not available
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
USER_SELECTION_PRESETS_DIR = PRESET_BASE_DIR / "user"

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
MODEL_CONTEXT_INFO = [{"id": "gpt4o", "displayName": "4o", "window": 128000}, {"id": "claude3o", "displayName": "o3", "window": 200000}, {"id": "geminiX", "displayName": "GmP", "window": 1000000}, {"id": "grokX", "displayName": "Grk3", "window": 1000000}]
# ------------------------------------------------------------------

# ------------------------------------------------------------------ HELPER FUNCTIONS
def get_selection_preset_path(name: str, preset_type: str) -> Path | None:
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name: return None
    base_dir = DEFAULT_SELECTION_PRESETS_DIR if preset_type == "default" else USER_SELECTION_PRESETS_DIR if preset_type == "user" else None
    return base_dir / f"{safe_name}.json" if base_dir else None

def check_if_item_is_excluded(item: Path, rules: dict) -> dict | None:
    """Checks if a single item matches exclusion rules based on its name and type."""
    if item.is_dir():
        if item.name in rules.get("dirs", []):
            return {"type": "Directory Name", "rule": item.name}
        for pattern in rules.get("patterns", []): # Patterns can match directory names too
            if item.match(pattern):
                return {"type": "Directory Pattern", "rule": pattern}
    elif item.is_file():
        if item.name in rules.get("files", []):
            return {"type": "File Name", "rule": item.name}
        for pattern in rules.get("patterns", []):
            if item.match(pattern):
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


def build_nested_dict(paths: list[Path], root_for_display: Path):
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

def ascii_tree(d, prefix=""):
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
        # Extract a more user-friendly part of the error or a generic message.
        user_error_message = "Directory Browse feature is disabled because the 'tkinter' Python module is not available or failed to initialize."
        if "module not found" in TKINTER_IMPORT_ERROR_MESSAGE.lower():
            user_error_message += " Please install python3-tk (or equivalent for your OS)."
        elif "display" in TKINTER_IMPORT_ERROR_MESSAGE.lower() or "tclerror" in TKINTER_IMPORT_ERROR_MESSAGE.lower():
             user_error_message += " Ensure a display environment is available (e.g., for Linux/WSL, ensure X11/WSLg is working)."

        return jsonify({"error": user_error_message, "selected_path": None}), 501 # 501 Not Implemented or 503 Service Unavailable

    try:
        # These need to be here as Tk() can fail if no display
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()  
        root.attributes('-topmost', True)
        directory_path = filedialog.askdirectory(
            title="Select Root Directory for Treeb"
        )
        root.destroy() 

        if directory_path: 
            selected_path = str(Path(directory_path).resolve())
            return jsonify({"selected_path": selected_path})
        else: 
            return jsonify({"selected_path": None})
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
            items = sorted(list(current_scan_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
            for child_item in items:
                children_nodes.append(dir_to_js_lazy(child_item))
        except PermissionError:
            app.logger.warning(f"Permission denied while listing children of {current_scan_path}")
        except Exception as e:
            app.logger.error(f"Error listing children for {current_scan_path}: {e}")
        return jsonify(children_nodes)


@app.post("/api/flatten")
def api_flatten():
    global ACTIVE_EXCLUSION_RULES
    data = request.get_json(force=True)
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

        if current_path in visited_for_walk and current_path.is_dir():
            continue
        
        if current_path.is_dir():
            visited_for_walk.add(current_path)

        if current_path not in initial_selection_nodes: 
            exclusion_info = check_if_item_is_excluded(current_path, ACTIVE_EXCLUSION_RULES)
            if exclusion_info:
                app.logger.debug(f"Flatten: Traversed item {current_path} excluded by rule: {exclusion_info}. Skipping its children.")
                continue 

        resolved_paths_for_structure_set.add(current_path)

        if current_path.is_file():
            files_to_process_set.add(current_path)
        elif current_path.is_dir():
            try:
                children = sorted(list(current_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
                for child_item in children:
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
        if token_count > 0:
            for model in MODEL_CONTEXT_INFO:
                percentage = round((token_count / model["window"]) * 100, 2); model_percentages.append({"name": model["displayName"], "percentage": (0.01 if 0 < percentage < 0.01 else percentage)})
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
                 common_ancestor_for_tree = Path(".").resolve() 
            else:
                common_ancestor_str = os.path.commonpath(abs_path_strings_for_commonpath)
                common_ancestor_for_tree = Path(common_ancestor_str)
                if common_ancestor_for_tree.is_file(): 
                    common_ancestor_for_tree = common_ancestor_for_tree.parent
        except ValueError: 
            common_ancestor_for_tree = Path(".").resolve() 
        
        subset = build_nested_dict(final_resolved_paths_for_structure, common_ancestor_for_tree)
        
        header_root_name_display = ""
        if common_ancestor_for_tree:
            name_to_display = common_ancestor_for_tree.name
            if not name_to_display or name_to_display == ".": 
                name_to_display = str(common_ancestor_for_tree) if str(common_ancestor_for_tree) != "." else "Selected Structure"
            header_root_name_display = f"{name_to_display}/\n"
        else:
            header_root_name_display = "Selected Structure/\n" 

        header = "code:\n" + header_root_name_display + "\n".join(ascii_tree(subset)) + "\n\n"

    body_parts = ["Content of selected files:\n"]
    if not final_files_to_process:
        body_parts.append("No files selected/accessible/found (after exclusion and directory expansion).\n")
    else:
        for f_path in final_files_to_process: 
            display_f_path_str = ""
            try:
                if common_ancestor_for_tree and common_ancestor_for_tree.is_dir():
                    try:
                        display_f_path_str = str(f_path.relative_to(common_ancestor_for_tree))
                    except ValueError: 
                        display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent and f_path.parent.name else f_path.name
                else: 
                    display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent and f_path.parent.name else f_path.name

                content = f_path.read_text(encoding="utf-8", errors="replace") 
                body_parts.append(f"# File: {display_f_path_str}\n{content}\n\n")
            except UnicodeDecodeError: 
                body_parts.append(f"# File: {display_f_path_str or f_path.name}\n[binary file or undecodable content skipped]\n\n")
            except Exception as e:
                body_parts.append(f"# File: {display_f_path_str or f_path.name}\n[Error reading file: {e}]\n\n")

    final_text = header + "".join(body_parts)
    if ENCODING:
        try:
            tokens = ENCODING.encode(final_text, disallowed_special=())
            token_count = len(tokens)
        except Exception as e:
            app.logger.error(f"Error tokenizing final text: {e}")
            token_count = -1 
    else:
        app.logger.warning("Tiktoken encoding not available. Token count 0.")

    if token_count >= 0 : 
        for model in MODEL_CONTEXT_INFO:
            if token_count == 0 and model["window"] == 0 : 
                percentage = 0.0
            elif model["window"] == 0: 
                percentage = 100.0 
            else:
                percentage = round((token_count / model["window"]) * 100, 2)
            
            model_percentages.append({
                "name": model["displayName"],
                "percentage": (0.01 if 0 < percentage < 0.01 else percentage) 
            })
    elif token_count == -1: 
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
def load_selection_preset_api(preset_id):
    try: preset_type, name = preset_id.split('/', 1)
    except ValueError: return jsonify({"error": "Invalid preset ID format."}), 400
    p = get_selection_preset_path(name, preset_type)
    if not p or not p.exists(): return jsonify({"error": f"Preset '{name}' not found"}), 404
    try:
        paths_from_preset_file = json.loads(p.read_text(encoding='utf-8'))
        resolved_absolute_paths = []
        if isinstance(paths_from_preset_file, list):
            for path_str_in_file in paths_from_preset_file:
                path_obj = Path(path_str_in_file)
                if path_obj.is_absolute():
                    resolved_absolute_paths.append(str(path_obj.resolve()))
                else:
                    resolved_absolute_paths.append(str((APP_ROOT / path_obj).resolve()))
            return jsonify(resolved_absolute_paths)
        else: return jsonify({"error": "Invalid preset file format"}), 500
    except Exception as e: return jsonify({"error": f"Failed to load preset: {e}"}), 500

@app.post("/api/presets/<name>")
def save_selection_preset_api(name):
    preset_file_path = get_selection_preset_path(name, "user")
    if not preset_file_path: return jsonify({"error": "Invalid preset name"}), 400
    data = request.get_json(force=True)
    absolute_paths_from_client = data.get("paths", []) 
    paths_to_save_in_preset = [] 

    for abs_path_str in absolute_paths_from_client:
        path_obj = Path(abs_path_str).resolve() 
        try:
            relative_path = path_obj.relative_to(APP_ROOT.resolve())
            paths_to_save_in_preset.append(str(relative_path))
        except ValueError: 
            paths_to_save_in_preset.append(str(path_obj))
    try:
        preset_file_path.parent.mkdir(parents=True, exist_ok=True)
        preset_file_path.write_text(json.dumps(paths_to_save_in_preset, indent=2), encoding='utf-8')
        return jsonify({"saved": True, "id": f"user/{name}", "name": name, "type": "user"})
    except Exception as e: return jsonify({"error": f"Failed to save user preset: {e}"}), 500

@app.delete("/api/presets/<path:preset_id>")
def delete_selection_preset_api(preset_id):
    try: preset_type, name = preset_id.split('/', 1)
    except ValueError: return jsonify({"error": "Invalid preset ID format."}), 400
    if preset_type != "user": return jsonify({"error": "Only user presets can be deleted."}), 403
    p = get_selection_preset_path(name, "user")
    if not p: return jsonify({"error": "Invalid preset name for deletion."}), 400 
    try:
        if p.exists():
            p.unlink()
            return jsonify({"deleted": True, "id": preset_id})
        else:
            return jsonify({"error": "User preset not found."}), 404
    except Exception as e: return jsonify({"error": f"Failed to delete preset: {e}"}), 500

if __name__ == "__main__":
    def create_default_selection_preset(preset_name: str, relative_paths_to_store: list[str]):
        preset_file = DEFAULT_SELECTION_PRESETS_DIR / f"{preset_name}.json"
        
        if preset_name == "default" and not preset_file.exists(): 
            try:
                preset_file.parent.mkdir(parents=True, exist_ok=True)
                preset_file.write_text(json.dumps([], indent=2), encoding='utf-8')
                app.logger.info(f"Created empty default selection preset: {preset_file.name}")
            except Exception as e:
                app.logger.error(f"Could not create empty default preset {preset_file.name}: {e}")
            return

        verified_paths_to_store = []
        for rel_path_str in relative_paths_to_store:
            abs_path = (APP_ROOT / Path(rel_path_str)).resolve()
            if abs_path.exists():
                verified_paths_to_store.append(rel_path_str) 
            else:
                app.logger.warning(f"Default preset '{preset_name}': path '{rel_path_str}' not found relative to APP_ROOT. Skipping.")

        if not preset_file.exists() and verified_paths_to_store: 
            try:
                preset_file.parent.mkdir(parents=True, exist_ok=True)
                preset_file.write_text(json.dumps(verified_paths_to_store, indent=2), encoding='utf-8')
                app.logger.info(f"Created default selection preset: {preset_file.name} with {len(verified_paths_to_store)} items.")
            except Exception as e:
                app.logger.error(f"Could not create default preset {preset_file.name}: {e}")
        elif preset_file.exists() and verified_paths_to_store:
            app.logger.info(f"Default selection preset '{preset_file.name}' already exists. Not overwriting with verified paths.")
        elif not preset_file.exists() and not verified_paths_to_store and preset_name != "default": 
            app.logger.info(f"Default selection preset '{preset_name}' not created as no verified paths were provided.")

    create_default_selection_preset("default", []) 
    app.run(debug=True, port=5005)