# treeb/app.py
from flask import Flask, render_template, request, jsonify
from pathlib import Path
import itertools
import json
import os # Retained for os.path.commonpath if still used, though Pathlib is preferred

app = Flask(__name__)

# --- configuration -------------------------------------------------
# Initial root directory, can be changed by the user via the UI
INITIAL_ROOT_DIR = Path(r"/home/hencle/MinimalEcommercePrototype").resolve()  # <-- CHANGE ME if needed

# --- Preset Configuration ---
APP_ROOT = Path(__file__).resolve().parent
PRESET_BASE_DIR = APP_ROOT / "presets"
DEFAULT_PRESETS_DIR = PRESET_BASE_DIR / "default"
USER_PRESETS_DIR = PRESET_BASE_DIR / "user"

# Create preset directories if they don't exist
PRESET_BASE_DIR.mkdir(exist_ok=True)
DEFAULT_PRESETS_DIR.mkdir(exist_ok=True)
USER_PRESETS_DIR.mkdir(exist_ok=True)
# ------------------------------------------------------------------

# ------------------------------------------------------------------ PRESET HELPERS
def get_preset_path(name: str, preset_type: str) -> Path | None:
    """
    Gets the path for a preset. Name can be 'type/actual_name' or just 'actual_name'.
    If 'actual_name' is provided, preset_type must be specified.
    """
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        return None

    if preset_type == "default":
        return DEFAULT_PRESETS_DIR / f"{safe_name}.json"
    elif preset_type == "user":
        return USER_PRESETS_DIR / f"{safe_name}.json"
    else: # try to parse from name if type is not given
        if '/' in name:
            ptype, pname = name.split('/', 1)
            safe_pname = "".join(c for c in pname if c.isalnum() or c in "-_").strip()
            if not safe_pname: return None
            if ptype == "default": return DEFAULT_PRESETS_DIR / f"{safe_pname}.json"
            if ptype == "user": return USER_PRESETS_DIR / f"{safe_pname}.json"
    return None


# -------- directory → jsTree JSON ---------------------------------
def dir_to_js(node: Path):
    """Return a dict jsTree understands."""
    try:
        if not node.exists(): # Check if path exists before iterating
            return {
                "id": str(node), "text": f"{node.name} (not found or no access)",
                "type": "error", "icon": "jstree-warning", "children": []
            }
        if node.is_dir():
            children = []
            try:
                for c in sorted(node.iterdir()):
                    children.append(dir_to_js(c))
            except PermissionError:
                 children.append({
                    "id": str(node) + "/permission_error", "text": "[Permission Denied]",
                    "type": "error", "icon": "jstree-warning", "children": []
                })
            return {
                "id": str(node),
                "text": node.name or str(node),      # show root name
                "children": children,
                "type": "folder"
            }
        # It's a file
        return {
            "id": str(node),
            "text": node.name,
            "icon": "jstree-file",
            "type": "file",
            "children": []
        }
    except Exception as e: # Catch other potential errors
        app.logger.error(f"Error processing path {node}: {e}")
        return {
            "id": str(node), "text": f"{node.name} (error)",
            "type": "error", "icon": "jstree-warning", "children": []
        }


# -------- ASCII subset tree ---------------------------------------
def build_nested_dict(paths, root_for_display: Path):
    tree = {}
    for p_str in paths:
        p = Path(p_str)
        try:
            # Ensure paths are absolute before trying to make them relative
            abs_p = p.resolve()
            rel_parts = abs_p.relative_to(root_for_display.resolve()).parts
        except ValueError: # Path is not under the root_for_display
            # Fallback: use parts of the path from common ancestor or just its name
            # This makes the tree structure for mixed-root selections potentially flat or less structured
            rel_parts = (p.name,) # Show only the file/dir name if not relative
        except Exception: # Catch other resolution errors
             rel_parts = (p.name + " (path error)",)


        cursor = tree
        for part in rel_parts:
            cursor = cursor.setdefault(part, {})
    return tree

def ascii_tree(d, prefix=""):
    """Recursive pretty-print like the Unix `tree` utility."""
    lines = []
    items = list(d.items())
    for i, (name, child) in enumerate(items):
        is_last = i == (len(items) - 1)
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + name)
        if child: # If it's a directory with children
            extension = "    " if is_last else "│   "
            lines.extend(ascii_tree(child, prefix + extension))
    return lines

# ------------------------------------------------------------------ ROUTES
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/tree")
def api_tree():
    requested_path_str = request.args.get("path")
    
    if requested_path_str:
        current_display_root = Path(requested_path_str).resolve()
    else:
        current_display_root = INITIAL_ROOT_DIR # Fallback to initial default

    if not current_display_root.is_dir(): # also implicitly checks exists() for dirs
        # If it exists but not a dir, or doesn't exist.
        # dir_to_js will handle specific error display for the node.
        # We need to return *something* for jstree.
        # Let's return the error state from dir_to_js for the root itself.
        return jsonify(dir_to_js(current_display_root))
        
    return jsonify(dir_to_js(current_display_root))

@app.post("/api/flatten")
def api_flatten():
    data = request.get_json(force=True)
    raw_paths = data.get("paths", [])
    
    if not raw_paths:
        return jsonify({"text": "No files selected."})

    files_to_process = []
    resolved_paths_for_structure = []

    for p_str in raw_paths:
        try:
            pp = Path(p_str).resolve()
            resolved_paths_for_structure.append(pp) # for building the ASCII tree
            if pp.is_file():
                files_to_process.append(pp)
        except Exception as e:
            app.logger.warning(f"Could not resolve or access path {p_str}: {e}")
    
    files_to_process.sort()

    # Determine a common root for the ASCII tree display.
    # If multiple roots were browsed and items selected from them,
    # os.path.commonpath might be C:\ or / if not careful.
    # We need a sensible display root.
    if not resolved_paths_for_structure:
        header = "No valid paths to display.\n\n"
    else:
        # Use common ancestor of all resolved paths (files and dirs) for the ASCII tree
        common_ancestor_for_tree = Path(os.path.commonpath([str(p) for p in resolved_paths_for_structure]))
        
        # Build tree structure only from selected paths (files and directories)
        subset = build_nested_dict([str(p) for p in resolved_paths_for_structure], common_ancestor_for_tree)
        
        # If the subset is based on a single common root, display that root's name.
        # Otherwise, the "root" of the ASCII tree is implicit from the structure.
        if common_ancestor_for_tree and len(subset) == 1 and next(iter(subset.keys())) == common_ancestor_for_tree.name:
             header_root_name = "" # common_ancestor_for_tree.name already part of subset
        elif common_ancestor_for_tree:
             header_root_name = f"{common_ancestor_for_tree.name}/\n" # Indicate the base
        else:
            header_root_name = "Selected Items/\n"

        header = "Structure of selected items:\n" + header_root_name
        header += "\n".join(ascii_tree(subset)) + "\n\n"

    body_parts = ["Content of selected files:\n"]
    if not files_to_process:
        body_parts.append("No files were selected or accessible to display content.\n")
    
    for f_path in files_to_process:
        try:
            # For file content headers, try to make path relative to a sensible root.
            # This could be common_ancestor_for_tree or INITIAL_ROOT_DIR or just its name.
            display_f_path = str(f_path)
            try:
                display_f_path = str(f_path.relative_to(common_ancestor_for_tree))
            except ValueError:
                # If not relative to common ancestor, use name or more absolute form
                display_f_path = f".../{f_path.parent.name}/{f_path.name}"

            body_parts.append(f"# File: {display_f_path}\n")
            body_parts.append(f_path.read_text(encoding="utf-8") + "\n\n")
        except UnicodeDecodeError:
            body_parts.append(f"# File: {display_f_path}\n[binary file skipped]\n\n")
        except Exception as e:
            body_parts.append(f"# File: {display_f_path}\n[Error reading file: {e}]\n\n")

    return jsonify({"text": header + "".join(body_parts)})

# ------------------------------------------------------------------ PRESET ROUTES
@app.get("/api/presets")
def list_presets_api():
    presets = []
    for p_file in sorted(DEFAULT_PRESETS_DIR.glob("*.json")):
        presets.append({"name": p_file.stem, "type": "default", "id": f"default/{p_file.stem}"})
    for p_file in sorted(USER_PRESETS_DIR.glob("*.json")):
        presets.append({"name": p_file.stem, "type": "user", "id": f"user/{p_file.stem}"})
    return jsonify(presets)

@app.get("/api/presets/<path:preset_id>") # path converter to allow slashes
def load_preset_api(preset_id):
    # preset_id is expected to be "type/name", e.g., "default/myconfig" or "user/mysession"
    try:
        preset_type, name = preset_id.split('/', 1)
    except ValueError:
        return jsonify({"error": "Invalid preset ID format. Expected 'type/name'."}), 400

    p = get_preset_path(name, preset_type)
    if not p or not p.exists():
        return jsonify({"error": f"Preset '{name}' of type '{preset_type}' not found"}), 404
    
    try:
        data = json.loads(p.read_text())
        # Presets store an array of paths directly
        if isinstance(data, list):
             return jsonify(data)
        else:
            app.logger.warning(f"Preset '{preset_id}' has unexpected format. Expected a list.")
            return jsonify({"error": "Invalid preset file format"}), 500
            
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid preset file format"}), 500
    except Exception as e:
        app.logger.error(f"Error loading preset {preset_id}: {e}")
        return jsonify({"error": "Failed to load preset"}), 500

@app.post("/api/presets/<name>") # Name here is just the preset name, type is implicit (user)
def save_preset_api(name):
    p = get_preset_path(name, "user")
    if not p:
        return jsonify({"error": "Invalid preset name"}), 400

    # Prevent overwriting default presets with the same name via this route
    default_p = get_preset_path(name, "default")
    if default_p and default_p.exists():
        # Check if user is trying to save a name that exists as default
        # Technically, user presets are in a different dir, so names can collide.
        # This check is more about avoiding confusion if a user names their preset "example"
        # and a default "example" exists. The paths are distinct due to subfolder.
        pass # Names can collide as they are in different folders (default/ vs user/)

    data = request.get_json(force=True)
    paths = data.get("paths", []) 
    
    try:
        p.write_text(json.dumps(paths, indent=2))
        return jsonify({"saved": True, "id": f"user/{name}"})
    except Exception as e:
        app.logger.error(f"Error saving preset {name} (user): {e}")
        return jsonify({"error": "Failed to save user preset"}), 500

@app.delete("/api/presets/<path:preset_id>") # path converter for "user/name"
def delete_preset_api(preset_id):
    try:
        preset_type, name = preset_id.split('/', 1)
    except ValueError:
        return jsonify({"error": "Invalid preset ID format. Expected 'type/name'."}), 400

    if preset_type != "user":
        return jsonify({"error": "Only user presets can be deleted."}), 403
        
    p = get_preset_path(name, "user")
    if not p: # Should not happen if type is 'user' and name is valid
        return jsonify({"error": "Invalid preset name for deletion."}), 400

    try:
        if p.exists():
            p.unlink()
            return jsonify({"deleted": True})
        else:
            return jsonify({"error": "User preset not found for deletion."}), 404
    except Exception as e:
        app.logger.error(f"Error deleting preset {preset_id}: {e}")
        return jsonify({"error": "Failed to delete preset"}), 500

if __name__ == "__main__":
    # Example: Create a dummy default preset if it doesn't exist, for testing
    dummy_default_preset_path = DEFAULT_PRESETS_DIR / "example_default.json"
    if not dummy_default_preset_path.exists():
        try:
            # This path should be an absolute path on your system where app.py exists
            # For example, if app.py is /path/to/treeb/app.py, use that.
            # Path.resolve() on a relative path here might be tricky if CWD is not project root.
            example_content_path = (APP_ROOT / "app.py").resolve()
            if example_content_path.exists():
                 dummy_default_preset_path.write_text(json.dumps([str(example_content_path)], indent=2))
            else:
                # Fallback content if app.py isn't easily resolvable this way
                dummy_default_preset_path.write_text(json.dumps(["/path/to/a/default/file.txt"], indent=2))

        except Exception as e:
            print(f"Could not create dummy default preset: {e}")
            
    app.run(debug=True, port=5000)