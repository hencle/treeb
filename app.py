# treeb/app.py
from flask import Flask, render_template, request, jsonify
from pathlib import Path
import json
import os
import tiktoken

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
        if not item.exists(): # Should ideally be checked by caller before passing to this func for children
            return {"id": str(item), "text": f"{item.name} (Not Found)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}

        exclusion_info = check_if_item_is_excluded(item, ACTIVE_EXCLUSION_RULES)
        # Use item.name for display, but item itself (or its string representation) if name is empty (e.g. for "C:/")
        node_text = item.name if item.name else str(item)
        item_abs_path_str = str(item.resolve()) # Use resolved absolute path for ID

        jstree_node_data = {"excluded_info": exclusion_info}

        if item.is_dir():
            return {
                "id": item_abs_path_str,
                "text": node_text,
                "children": True,  # Assume directories can have children; jstree expansion will verify
                "type": "folder", # jstree can use this for specific folder icons
                "data": jstree_node_data
            }
        else:  # File
            return {
                "id": item_abs_path_str,
                "text": node_text,
                "icon": "jstree-file", # jstree can use this for specific file icons
                "type": "file",
                "children": False, # Files don't have expandable children in this context
                "data": jstree_node_data
            }
    except Exception as e:
        app.logger.error(f"Error processing path {item} for lazy tree node: {e}")
        # Fallback error node for unexpected issues
        return {"id": str(item), "text": f"{item.name} (Processing Error)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}


def build_nested_dict(paths: list[Path], root_for_display: Path):
    tree = {}
    resolved_root_for_display = root_for_display.resolve()
    for p in paths:
        try:
            abs_p = p.resolve()
            # Ensure path is relative to the display root for the tree structure
            if resolved_root_for_display in abs_p.parents or resolved_root_for_display == abs_p:
                 rel_parts = abs_p.relative_to(resolved_root_for_display).parts
                 if not rel_parts: # case where p is the root_for_display itself
                     rel_parts = (abs_p.name,) if abs_p.name else (str(abs_p),) # Use name or full path if name is empty
            else: # Path is not under root_for_display, show its own name or full path as top level
                 rel_parts = (abs_p.name,) if abs_p.name else (str(abs_p),)

        except ValueError: # Path cannot be made relative (e.g. different drive on Windows)
            rel_parts = (p.name if p.name else str(p),) # Fallback to its own name
        except Exception as e: # Other path errors
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
        if child: # If this node has children, recurse
            extension = "    " if is_last else "│   "
            lines.extend(ascii_tree(child, prefix + extension))
    return lines
# ------------------------------------------------------------------ ROUTES
@app.route("/")
def index():
    return render_template("index.html", initial_path=str(INITIAL_ROOT_DIR))

@app.get("/api/tree")
def api_tree():
    node_id_param = request.args.get("id")
    initial_path_param = request.args.get("path") # Sent by jsTree on initial load with id='#'

    current_scan_path = None

    if node_id_param == "#":  # Initial load for the root of the tree
        path_str = initial_path_param if initial_path_param else str(INITIAL_ROOT_DIR)
        try:
            current_scan_path = Path(path_str).resolve()
        except Exception as e: # Handle potential errors during path resolution (e.g. invalid chars)
            app.logger.error(f"Invalid initial path resolution for '{path_str}': {e}")
            error_node = {"id": path_str, "text": f"{Path(path_str).name} (Invalid Path)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}
            return jsonify([error_node])

        if not current_scan_path.exists() or not current_scan_path.is_dir():
            display_name = current_scan_path.name if current_scan_path.name else str(current_scan_path)
            error_node = {"id": str(current_scan_path), "text": f"{display_name} (Not Found or Not a Dir)", "type": "error", "icon": "jstree-warning", "children": False, "data": {"excluded_info": None}}
            return jsonify([error_node])
        # For initial load, jsTree expects a list containing the root node object itself
        root_node_obj = dir_to_js_lazy(current_scan_path)
        return jsonify([root_node_obj])
    else:  # Expansion of an existing node (node_id_param is the absolute path)
        try:
            current_scan_path = Path(node_id_param).resolve()
        except Exception as e:
            app.logger.error(f"Invalid node ID path resolution for '{node_id_param}': {e}")
            return jsonify([]) # Return empty list on error for children

        if not current_scan_path.is_dir(): # Should not happen if "children:true" was set correctly for dirs
            return jsonify([]) # Not a directory, so no children to list

        children_nodes = []
        try:
            # Sort items: directories first, then files, then alphabetically
            items = sorted(list(current_scan_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
            for child_item in items:
                children_nodes.append(dir_to_js_lazy(child_item))
        except PermissionError:
            app.logger.warning(f"Permission denied while listing children of {current_scan_path}")
            # Optionally return a special node indicating permission error
            # children_nodes.append({"id": str(current_scan_path) + "/permission_error", "text": "[Permission Denied]", "type": "error", ...})
        except Exception as e:
            app.logger.error(f"Error listing children for {current_scan_path}: {e}")
        return jsonify(children_nodes)


@app.post("/api/flatten")
def api_flatten():
    global ACTIVE_EXCLUSION_RULES
    data = request.get_json(force=True)
    # raw_paths_from_client are absolute paths of nodes selected in jsTree
    raw_paths_from_client = data.get("paths", [])
    token_count = 0
    model_percentages = []

    # Store resolved Path objects to avoid re-resolving and for consistency
    resolved_paths_for_structure_set = set() # For ASCII tree (all items: files and dirs)
    files_to_process_set = set()             # For file content reading (only files)

    # Phase 1: Filter initial user-selected paths if they are directly excluded or non-existent
    initial_selection_nodes = [] # Store Path objects
    for p_str in raw_paths_from_client:
        try:
            path_item = Path(p_str).resolve()
        except Exception as e:
            app.logger.warning(f"Flatten: Invalid path string {p_str} from client: {e}. Skipping.")
            continue

        if not path_item.exists():
            app.logger.warning(f"Flatten: Selected path {p_str} (resolved to {path_item}) does not exist. Skipping.")
            continue

        # Check if the selected item itself is directly excluded
        exclusion_info = check_if_item_is_excluded(path_item, ACTIVE_EXCLUSION_RULES)
        if exclusion_info:
            app.logger.debug(f"Flatten: Directly selected item {path_item} is excluded by rule: {exclusion_info}. Skipping.")
            continue
        initial_selection_nodes.append(path_item)

    # Phase 2: Recursively expand selected directories and collect all relevant items
    queue = list(initial_selection_nodes) # Use Path objects in queue
    # visited_for_walk helps avoid re-processing if a dir is reachable via multiple selected paths or symlinks
    # but primarily to avoid redundant os calls for children of an already processed directory.
    visited_for_walk = set()

    while queue:
        current_path = queue.pop(0) # current_path is a Path object

        if current_path in visited_for_walk and current_path.is_dir():
            # If it's a directory and we've already processed its children, skip.
            # Files don't get "re-walked" in this sense, they are just added.
            continue
        
        # For directories, mark as visited *before* iterating children to handle self-referential symlinks (though less likely here)
        # More importantly, this prevents adding children multiple times if a dir is selected + one of its children is also selected.
        if current_path.is_dir():
            visited_for_walk.add(current_path)

        # Re-check exclusion for items encountered during traversal (children).
        # Items from initial_selection_nodes already passed their direct check.
        # This check is for items *not* directly selected by the user but found via traversal.
        if current_path not in initial_selection_nodes: # only re-check if it wasn't an original explicit selection
            exclusion_info = check_if_item_is_excluded(current_path, ACTIVE_EXCLUSION_RULES)
            if exclusion_info:
                app.logger.debug(f"Flatten: Traversed item {current_path} excluded by rule: {exclusion_info}. Skipping its children.")
                continue # Skip this item and do not add its children to the queue

        # At this point, current_path is considered included for the structure
        resolved_paths_for_structure_set.add(current_path)

        if current_path.is_file():
            files_to_process_set.add(current_path)
        elif current_path.is_dir():
            # If it's a directory, add its children to the queue for processing
            try:
                # Sort children for consistent processing order
                children = sorted(list(current_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
                for child_item in children:
                    # Add to queue. Exclusion will be checked when child_item becomes current_path.
                    # No need to check visited_for_walk here for adding to queue, it's checked at pop.
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

    # Convert sets of Path objects to sorted lists of Path objects
    final_resolved_paths_for_structure = sorted(list(resolved_paths_for_structure_set), key=lambda p: str(p).lower())
    final_files_to_process = sorted(list(files_to_process_set), key=lambda p: str(p).lower())
    
    header = ""
    common_ancestor_for_tree = None
    if not final_resolved_paths_for_structure:
        header = "No valid paths for structure (after exclusion).\n\n"
    else:
        try:
            # Ensure all paths are strings and absolute for commonpath
            abs_path_strings_for_commonpath = [str(p.resolve()) for p in final_resolved_paths_for_structure]
            if not abs_path_strings_for_commonpath:
                 common_ancestor_for_tree = Path(".").resolve() # Default fallback
            else:
                common_ancestor_str = os.path.commonpath(abs_path_strings_for_commonpath)
                common_ancestor_for_tree = Path(common_ancestor_str)
                # If commonpath returns a file path (e.g. if only one file selected), use its parent
                if common_ancestor_for_tree.is_file(): # This can happen if all paths are files in the same dir
                    common_ancestor_for_tree = common_ancestor_for_tree.parent
        except ValueError: # E.g. on Windows with mixed drive paths, or empty list
            common_ancestor_for_tree = Path(".").resolve() # Or decide a better fallback
        
        subset = build_nested_dict(final_resolved_paths_for_structure, common_ancestor_for_tree)
        
        header_root_name_display = ""
        if common_ancestor_for_tree:
            name_to_display = common_ancestor_for_tree.name
            if not name_to_display or name_to_display == ".": # Handle cases like root "/" or "C:\"
                name_to_display = str(common_ancestor_for_tree) if str(common_ancestor_for_tree) != "." else "Selected Structure"

            # If the subset's top level keys are exactly the children of common_ancestor_for_tree,
            # then common_ancestor_for_tree.name should be the prefix.
            # If build_nested_dict already created a root node with common_ancestor_for_tree.name, don't repeat.
            # The current build_nested_dict makes paths relative to common_ancestor_for_tree.
            # So the tree starts with children of common_ancestor_for_tree.
            header_root_name_display = f"{name_to_display}/\n"
        else:
            header_root_name_display = "Selected Structure/\n" # Fallback if no common ancestor determined

        header = "code:\n" + header_root_name_display + "\n".join(ascii_tree(subset)) + "\n\n"

    body_parts = ["Content of selected files:\n"]
    if not final_files_to_process:
        body_parts.append("No files selected/accessible/found (after exclusion and directory expansion).\n")
    else:
        for f_path in final_files_to_process: # This is now a list of Path objects
            display_f_path_str = ""
            try:
                # Make file paths in output relative to the common_ancestor_for_tree for readability
                if common_ancestor_for_tree and common_ancestor_for_tree.is_dir():
                    try:
                        display_f_path_str = str(f_path.relative_to(common_ancestor_for_tree))
                    except ValueError: # f_path is not under common_ancestor_for_tree
                        # Fallback: show path relative to its own parent, or just its name
                        display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent and f_path.parent.name else f_path.name
                else: # No common ancestor or it's not a dir, use a fallback display path
                    display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent and f_path.parent.name else f_path.name

                content = f_path.read_text(encoding="utf-8", errors="replace") # Added errors='replace' for robustness
                body_parts.append(f"# File: {display_f_path_str}\n{content}\n\n")
            except UnicodeDecodeError: # Should be less frequent with errors='replace'
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
            token_count = -1 # Indicate error
    else:
        app.logger.warning("Tiktoken encoding not available. Token count 0.")

    if token_count > 0: # Also handle token_count == -1 if error
        for model in MODEL_CONTEXT_INFO:
            percentage = round((token_count / model["window"]) * 100, 2)
            model_percentages.append({
                "name": model["displayName"],
                "percentage": (0.01 if 0 < percentage < 0.01 else percentage)
            })
    elif token_count == -1:
        model_percentages.append({"name": "Error", "percentage": "Tokenization failed"})


    return jsonify({"text": final_text, "token_count": token_count, "model_percentages": model_percentages})

# ---------------------------------------------------------- SELECTION PRESET ROUTES
# (These routes: /api/presets, /api/presets/<path:preset_id>, POST /api/presets/<name>, DELETE /api/presets/<path:preset_id>
#  remain largely unchanged in their core logic, as they deal with lists of paths.
#  The frontend's ability to *apply* these presets to a lazy-loaded tree might be affected if nodes aren't loaded,
#  but the backend storage/retrieval of paths is the same.)

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
                # Presets store paths relative to APP_ROOT or absolute. We need to return absolute paths.
                if path_obj.is_absolute():
                    resolved_absolute_paths.append(str(path_obj.resolve()))
                else:
                    # This logic assumes paths in presets are relative to APP_ROOT if not absolute.
                    # This needs to be consistent with how they are saved.
                    resolved_absolute_paths.append(str((APP_ROOT / path_obj).resolve()))
            return jsonify(resolved_absolute_paths)
        else: return jsonify({"error": "Invalid preset file format"}), 500
    except Exception as e: return jsonify({"error": f"Failed to load preset: {e}"}), 500

@app.post("/api/presets/<name>")
def save_selection_preset_api(name):
    preset_file_path = get_selection_preset_path(name, "user")
    if not preset_file_path: return jsonify({"error": "Invalid preset name"}), 400
    data = request.get_json(force=True)
    absolute_paths_from_client = data.get("paths", []) # These are expected to be absolute paths from jsTree
    paths_to_save_in_preset = [] # Store as strings, relative to APP_ROOT if possible, else absolute

    for abs_path_str in absolute_paths_from_client:
        path_obj = Path(abs_path_str).resolve() # Ensure it's resolved and absolute
        try:
            # Try to make it relative to APP_ROOT for portability
            relative_path = path_obj.relative_to(APP_ROOT.resolve())
            paths_to_save_in_preset.append(str(relative_path))
        except ValueError: # Not under APP_ROOT, save as absolute path
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
    if not p: return jsonify({"error": "Invalid preset name for deletion."}), 400 # Should not happen if format is good
    try:
        if p.exists():
            p.unlink()
            return jsonify({"deleted": True, "id": preset_id})
        else:
            return jsonify({"error": "User preset not found."}), 404
    except Exception as e: return jsonify({"error": f"Failed to delete preset: {e}"}), 500

if __name__ == "__main__":
    # --- Default Selection Preset Generation ---
    def create_default_selection_preset(preset_name: str, relative_paths_to_store: list[str]):
        preset_file = DEFAULT_SELECTION_PRESETS_DIR / f"{preset_name}.json"
        # Always create/overwrite the 'default' preset with empty list if it's the "default" one and no paths given
        # Or only if it doesn't exist. For now, let's be gentle: only if not exists or if paths are given.
        if not preset_file.exists() or (relative_paths_to_store and preset_name == "default"): # Overwrite "default" only if specific paths are given
             if not relative_paths_to_store and preset_name == "default" and not preset_file.exists(): # Special: create empty "default"
                try:
                    preset_file.parent.mkdir(parents=True, exist_ok=True)
                    preset_file.write_text(json.dumps([], indent=2), encoding='utf-8')
                    app.logger.info(f"Created empty default selection preset: {preset_file.name}")
                except Exception as e:
                    app.logger.error(f"Could not create empty default preset {preset_file.name}: {e}")
                return

        # Logic for creating presets with actual paths (mostly for future use, "default" is usually empty)
        verified_paths_to_store = []
        for rel_path_str in relative_paths_to_store:
            abs_path = (APP_ROOT / Path(rel_path_str)).resolve()
            if abs_path.exists():
                verified_paths_to_store.append(rel_path_str) # Store as relative string
            else:
                app.logger.warning(f"Default preset '{preset_name}': path '{rel_path_str}' not found relative to APP_ROOT. Skipping.")

        if not preset_file.exists() and verified_paths_to_store: # Only create if doesn't exist and has content
            try:
                preset_file.parent.mkdir(parents=True, exist_ok=True)
                preset_file.write_text(json.dumps(verified_paths_to_store, indent=2), encoding='utf-8')
                app.logger.info(f"Created default selection preset: {preset_file.name} with {len(verified_paths_to_store)} items.")
            except Exception as e:
                app.logger.error(f"Could not create default preset {preset_file.name}: {e}")
        elif preset_file.exists() and verified_paths_to_store:
            app.logger.info(f"Default selection preset '{preset_file.name}' already exists. Not overwriting with verified paths.")
        elif not preset_file.exists() and not verified_paths_to_store and preset_name != "default": # Don't log for "default" if no paths
            app.logger.info(f"Default selection preset '{preset_name}' not created as no verified paths were provided.")


    create_default_selection_preset("default", []) # Ensure an empty "default.json" exists in selections/default

    app.run(debug=True, port=5005)