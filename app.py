# File: app.py
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
USER_SELECTION_PRESETS_DIR = SELECTION_PRESET_BASE_DIR / "user"

# Exclusion preset directories are defined but not actively managed by UI anymore
EXCLUSION_PRESET_BASE_DIR = PRESET_BASE_DIR / "exclusions" 
DEFAULT_EXCLUSION_PRESETS_DIR = EXCLUSION_PRESET_BASE_DIR / "default"

# Create necessary preset directories
for p_dir in [PRESET_BASE_DIR, SELECTION_PRESET_BASE_DIR, DEFAULT_SELECTION_PRESETS_DIR,
              USER_SELECTION_PRESETS_DIR, EXCLUSION_PRESET_BASE_DIR, # Keep if manually placing defaults
              DEFAULT_EXCLUSION_PRESETS_DIR]: 
    p_dir.mkdir(exist_ok=True)


# --- Hardcoded Active Exclusion Rules (System Default) ---
class DefaultExclusionData:
    DIRS = [".git", ".venv", "venv", ".env", "env", "node_modules", ".next", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", "target", "out", "site", ".vscode", ".idea"]
    FILES = [".DS_Store", "Thumbs.db", ".env"]
    PATTERNS = ["*.pyc", "*.pyo", "*.swp", "*.swo", "*.swn", "*.log", "*.tmp", "*.temp", "*ignore", "*.lock"]

ACTIVE_EXCLUSION_RULES = {
    "description": "Hardcoded system default exclusions.",
    "dirs": list(DefaultExclusionData.DIRS),
    "files": list(DefaultExclusionData.FILES),
    "patterns": list(DefaultExclusionData.PATTERNS)
}
app.logger.info(f"Initialized with hardcoded active exclusion rules.")


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
    if item.is_dir():
        if item.name in rules.get("dirs", []): return {"type": "Directory Name", "rule": item.name}
        for pattern in rules.get("patterns", []):
            if item.match(pattern): return {"type": "Directory Pattern", "rule": pattern}
    elif item.is_file():
        if item.name in rules.get("files", []): return {"type": "File Name", "rule": item.name}
        for pattern in rules.get("patterns", []):
            if item.match(pattern): return {"type": "File Pattern", "rule": pattern}
    return None

def dir_to_js(node: Path):
    global ACTIVE_EXCLUSION_RULES
    try:
        if not node.exists(): return {"id": str(node), "text": f"{node.name} (Not Found)", "type": "error", "icon": "jstree-warning", "children": [], "data": {"excluded_info": None}}
        exclusion_info = check_if_item_is_excluded(node, ACTIVE_EXCLUSION_RULES)
        node_text = node.name or str(node)
        jstree_node_data = {"excluded_info": exclusion_info}
        if node.is_dir():
            children_nodes = []
            try:
                for c_item in sorted(node.iterdir()): children_nodes.append(dir_to_js(c_item)) 
            except PermissionError: children_nodes.append({"id": str(node) + "/permission_error", "text": "[Permission Denied]", "type": "error", "icon": "jstree-warning", "children": [], "data": {"excluded_info": None}})
            return {"id": str(node), "text": node_text, "children": children_nodes, "type": "folder", "data": jstree_node_data}
        else: return {"id": str(node), "text": node_text, "icon": "jstree-file", "type": "file", "children": [], "data": jstree_node_data}
    except Exception as e:
        app.logger.error(f"Error processing path {node}: {e}")
        return {"id": str(node), "text": f"{node.name} (Error)", "type": "error", "icon": "jstree-warning", "children": [], "data": {"excluded_info": None}}

def build_nested_dict(paths, root_for_display: Path):
    tree = {};
    for p_str in paths:
        p = Path(p_str)
        try: abs_p = p.resolve(); rel_parts = abs_p.relative_to(root_for_display.resolve()).parts
        except ValueError: rel_parts = (p.name,)
        except Exception: rel_parts = (p.name + " (path error)",)
        cursor = tree
        for part in rel_parts: cursor = cursor.setdefault(part, {})
    return tree

def ascii_tree(d, prefix=""):
    lines = []; items = list(d.items())
    for i, (name, child) in enumerate(items):
        is_last = i == (len(items) - 1); connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + name)
        if child: extension = "    " if is_last else "│   "; lines.extend(ascii_tree(child, prefix + extension))
    return lines
# ------------------------------------------------------------------ ROUTES
@app.route("/")
def index(): return render_template("index.html", initial_path=str(INITIAL_ROOT_DIR))

@app.get("/api/tree")
def api_tree():
    requested_path_str = request.args.get("path")
    current_display_root = Path(requested_path_str).resolve() if requested_path_str else INITIAL_ROOT_DIR
    if not current_display_root.is_dir(): return jsonify(dir_to_js(current_display_root))
    return jsonify(dir_to_js(current_display_root))

@app.post("/api/flatten")
def api_flatten():
    global ACTIVE_EXCLUSION_RULES
    data = request.get_json(force=True)
    raw_paths_from_client = data.get("paths", [])
    token_count = 0; model_percentages = []
    
    filtered_raw_paths = []
    for p_str in raw_paths_from_client:
        path_item = Path(p_str).resolve()
        excluded_by_dir_rule = False
        current_path_for_check = path_item
        while True:
            if current_path_for_check.name in ACTIVE_EXCLUSION_RULES.get("dirs", []):
                excluded_by_dir_rule = True; break
            if current_path_for_check == current_path_for_check.parent: break
            current_path_for_check = current_path_for_check.parent
        if excluded_by_dir_rule: app.logger.debug(f"Flatten: Excluded by dir rule: {p_str}"); continue
        
        if path_item.is_file():
            if path_item.name in ACTIVE_EXCLUSION_RULES.get("files", []): app.logger.debug(f"Flatten: Excluded by file name: {p_str}"); continue
            if any(path_item.match(p) for p in ACTIVE_EXCLUSION_RULES.get("patterns", [])): app.logger.debug(f"Flatten: Excluded by file pattern: {p_str}"); continue
        elif path_item.is_dir():
            if any(path_item.match(p) for p in ACTIVE_EXCLUSION_RULES.get("patterns", [])): app.logger.debug(f"Flatten: Excluded by dir pattern: {p_str}"); continue
        filtered_raw_paths.append(p_str)

    if not filtered_raw_paths:
        text_content = "No files selected or all selected items are excluded."
        if ENCODING:
            try: tokens = ENCODING.encode(text_content, disallowed_special=()); token_count = len(tokens)
            except Exception as e: app.logger.error(f"Error tokenizing message: {e}")
        if token_count > 0:
            for model in MODEL_CONTEXT_INFO:
                percentage = round((token_count / model["window"]) * 100, 2); model_percentages.append({"name": model["displayName"], "percentage": (0.01 if 0 < percentage < 0.01 else percentage)})
        return jsonify({"text": text_content, "token_count": token_count, "model_percentages": model_percentages})

    files_to_process = []
    resolved_paths_for_structure = []
    # *** THIS IS THE CORRECTED TRY-EXCEPT BLOCK ***
    for p_str in filtered_raw_paths:
        try:
            pp = Path(p_str).resolve() # Statement 1
            resolved_paths_for_structure.append(pp) # Statement 2
            if pp.is_file(): # This was indicated as line 160
                files_to_process.append(pp) # Statement 3
        except Exception as e: # Correctly aligned `except`
            app.logger.warning(f"Could not resolve or access path {p_str} during flatten content stage: {e}")
    # *** END OF CORRECTION ***
    files_to_process.sort()
    
    header = ""; common_ancestor_for_tree = None 
    if not resolved_paths_for_structure: header = "No valid paths for structure (after exclusion).\n\n"
    else:
        try:
            abs_paths_for_commonpath = [str(p.resolve()) for p in resolved_paths_for_structure]
            common_ancestor_str = os.path.commonpath(abs_paths_for_commonpath)
            common_ancestor_for_tree = Path(common_ancestor_str)
        except ValueError: common_ancestor_for_tree = Path(".").resolve()
        subset = build_nested_dict([str(p) for p in resolved_paths_for_structure], common_ancestor_for_tree)
        header_root_name = ""
        if common_ancestor_for_tree and len(subset) == 1 and next(iter(subset.keys())) == common_ancestor_for_tree.name: header_root_name = "" 
        elif common_ancestor_for_tree:
            name_to_display = common_ancestor_for_tree.name
            if not name_to_display or name_to_display == ".": name_to_display = str(common_ancestor_for_tree) if str(common_ancestor_for_tree) != "." else "Selected Items"
            header_root_name = f"{name_to_display}/\n"
        else: header_root_name = "Selected Items/\n"
        header = "Structure of selected items:\n" + header_root_name + "\n".join(ascii_tree(subset)) + "\n\n"
    body_parts = ["Content of selected files:\n"]
    if not files_to_process: body_parts.append("No files selected/accessible (after exclusion).\n")
    else:
        for f_path in files_to_process:
            display_f_path_str = "" 
            try:
                try: display_f_path_str = str(f_path.relative_to(common_ancestor_for_tree))
                except ValueError: display_f_path_str = f".../{f_path.parent.name}/{f_path.name}" if f_path.parent.name else f_path.name
                content = f_path.read_text(encoding="utf-8")
                body_parts.append(f"# File: {display_f_path_str}\n{content}\n\n")
            except UnicodeDecodeError: body_parts.append(f"# File: {display_f_path_str or f_path.name}\n[binary file skipped]\n\n")
            except Exception as e: body_parts.append(f"# File: {display_f_path_str or f_path.name}\n[Error reading file: {e}]\n\n")
    final_text = header + "".join(body_parts)
    if ENCODING:
        try: tokens = ENCODING.encode(final_text, disallowed_special=()); token_count = len(tokens)
        except Exception as e: app.logger.error(f"Error tokenizing final text: {e}")
    else: app.logger.warning("Tiktoken encoding not available. Token count 0.")
    if token_count > 0:
        for model in MODEL_CONTEXT_INFO:
            percentage = round((token_count / model["window"]) * 100, 2); model_percentages.append({"name": model["displayName"], "percentage": (0.01 if 0 < percentage < 0.01 else percentage)})
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
        paths_from_preset_file = json.loads(p.read_text())
        resolved_absolute_paths = []
        if isinstance(paths_from_preset_file, list):
            for path_str_in_file in paths_from_preset_file:
                path_obj = Path(path_str_in_file)
                if path_obj.is_absolute(): resolved_absolute_paths.append(str(path_obj.resolve()))
                else: resolved_absolute_paths.append(str((APP_ROOT / path_obj).resolve()))
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
        path_obj = Path(abs_path_str)
        try:
            relative_path = path_obj.resolve().relative_to(APP_ROOT.resolve())
            paths_to_save_in_preset.append(str(relative_path))
        except ValueError: paths_to_save_in_preset.append(str(path_obj.resolve()))
    try:
        preset_file_path.parent.mkdir(parents=True, exist_ok=True)
        preset_file_path.write_text(json.dumps(paths_to_save_in_preset, indent=2))
        return jsonify({"saved": True, "id": f"user/{name}"})
    except Exception as e: return jsonify({"error": f"Failed to save user preset: {e}"}), 500

@app.delete("/api/presets/<path:preset_id>") 
def delete_selection_preset_api(preset_id):
    try: preset_type, name = preset_id.split('/', 1)
    except ValueError: return jsonify({"error": "Invalid preset ID format."}), 400
    if preset_type != "user": return jsonify({"error": "Only user presets can be deleted."}), 403
    p = get_selection_preset_path(name, "user")
    if not p: return jsonify({"error": "Invalid preset name."}), 400
    try:
        if p.exists(): p.unlink(); return jsonify({"deleted": True})
        else: return jsonify({"error": "User preset not found."}), 404
    except Exception as e: return jsonify({"error": f"Failed to delete preset: {e}"}), 500

# REMOVED: All /api/exclusions/* routes

if __name__ == "__main__":
    def create_default_selection_preset(preset_name: str, relative_paths_to_store: list[str]):
        preset_file = DEFAULT_SELECTION_PRESETS_DIR / f"{preset_name}.json"
        if not relative_paths_to_store:
            if not preset_file.exists():
                try:
                    preset_file.parent.mkdir(parents=True, exist_ok=True)
                    preset_file.write_text(json.dumps([], indent=2))
                    app.logger.info(f"Created empty default selection preset: {preset_file.name}")
                except Exception as e: app.logger.error(f"Could not create empty default preset {preset_file.name}: {e}")
            else: app.logger.info(f"Empty default selection preset '{preset_file.name}' already exists.")
            return
        verified_paths_to_store = []
        for rel_path_str in relative_paths_to_store:
            abs_path = (APP_ROOT / Path(rel_path_str)).resolve()
            if abs_path.exists(): verified_paths_to_store.append(rel_path_str)
            else: app.logger.warning(f"Default preset '{preset_name}': path '{rel_path_str}' not found.")
        if not preset_file.exists() and verified_paths_to_store:
            try:
                preset_file.parent.mkdir(parents=True, exist_ok=True)
                preset_file.write_text(json.dumps(verified_paths_to_store, indent=2))
                app.logger.info(f"Created default selection preset: {preset_file.name}")
            except Exception as e: app.logger.error(f"Could not create default preset {preset_file.name}: {e}")
        elif preset_file.exists(): app.logger.info(f"Default selection preset '{preset_file.name}' already exists.")

    create_default_selection_preset("default", []) # Default is empty
            
    app.run(debug=True, port=5000)