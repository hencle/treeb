# treeb/app.py
from flask import Flask, render_template, request, jsonify
from pathlib import Path
import itertools
import json, os # New import

app = Flask(__name__)

# --- configuration -------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
# ------------------------------------------------------------------
PRESET_DIR = Path.home() / ".filepicker_presets" # New
PRESET_DIR.mkdir(exist_ok=True) # New

# ------------------------------------------------------------------ PRESET HELPERS
def preset_path(name: str) -> Path: # New
    safe = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    return PRESET_DIR / f"{safe}.json"

# -------- directory → jsTree JSON ---------------------------------
def dir_to_js(node: Path):
    """Return a dict jsTree understands."""
    if node.is_dir():
        return {
            "id": str(node),
            "text": node.name or str(node),      # show root name
            "children": [dir_to_js(c) for c in sorted(node.iterdir())],
            "type": "folder"
        }
    return {
        "id": str(node),
        "text": node.name,
        "icon": "jstree-file",
        "type": "file",
        "children": []
    }

# -------- ASCII subset tree ---------------------------------------
def build_nested_dict(paths, root):
    tree = {}
    for p in paths:
        # Ensure path p is relative to the effective root for this operation
        # This might need adjustment depending on how 'root' is determined
        # in the context of presets which might span different roots.
        # For now, assuming paths in presets are absolute, and root is the original ROOT_DIR.
        # If paths in presets can be relative, this logic needs more thought.
        try:
            rel_parts = Path(p).resolve().relative_to(root.resolve()).parts
        except ValueError:
            # Path p is not under the provided root, skip or handle as error
            # For now, let's use the absolute path's parts if not relative to ROOT_DIR
            # This part of the logic might need refinement if presets are loaded
            # from a different root than the one used to build the current tree.
            # The feature description implies presets store absolute paths.
            rel_parts = Path(p).resolve().parts
            if rel_parts and rel_parts[0] == '/': # Absolute path
                rel_parts = rel_parts[1:] # remove root slash for display
            rel_parts = [Path(p).name] # Fallback: just use the name

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
        if child:
            extension = "    " if is_last else "│   "
            lines.extend(ascii_tree(child, prefix + extension))
    return lines

# ------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/tree")
def api_tree():
    # The 'path' argument from the request determines the root to display.
    # ROOT_DIR acts as the initial default and a potential security boundary.
    requested_path_str = request.args.get("path")
    
    if requested_path_str:
        current_display_root = Path(requested_path_str).resolve()
        # Security check: Ensure the requested path is either ROOT_DIR or a subdirectory of ROOT_DIR.
        # This prevents navigating outside the initially configured ROOT_DIR.
        # For more flexible root switching (any folder), this check might be removed or made configurable,
        # but implies trust in the user or additional auth.
        # The prompt implies "pick any folder", so this check could be too restrictive if
        # the intention is to truly allow *any* path.
        # However, for a web app, it's safer to keep it constrained initially.
        # Let's assume for now that "any folder" still means "any folder the app is allowed to serve from
        # by configuration or a higher-level check not shown".
        # If the goal is to allow Browse *any* arbitrary system path the Flask process has access to,
        # then the check `ROOT_DIR not in current_display_root.parents and current_display_root != ROOT_DIR`
        # might be too restrictive or need to be re-evaluated based on security implications.
        # Given the original code, let's adapt it to allow *any* path if specified,
        # falling back to ROOT_DIR if no path is given.
        # The prompt says "pick any folder, instantly reload the tree".
        # The original check was:
        # if ROOT_DIR not in root_req.parents and root_req != ROOT_DIR:
        #    return jsonify({"error": "outside allowed root"}), 400
        # For "pick any folder", this check is removed. Ensure the server has permissions.
    else:
        current_display_root = ROOT_DIR

    if not current_display_root.exists():
        return jsonify({"error": f"Path not found: {current_display_root}"}), 404
    if not current_display_root.is_dir():
        return jsonify({"error": f"Path is not a directory: {current_display_root}"}), 400
        
    return jsonify(dir_to_js(current_display_root))

@app.post("/api/flatten")
def api_flatten():
    data = request.get_json(force=True)
    raw_paths = data.get("paths", [])
    
    # Determine the effective root for displaying the tree structure.
    # This should ideally come from the client, indicating which root was active when these paths were selected.
    # For simplicity, if a currentRoot is active on the client, it should send it.
    # If not, we might fall back to ROOT_DIR or try to infer.
    # The paths in 'raw_paths' are absolute as per jsTree node IDs.
    # We need a common ancestor to make the ASCII tree make sense.
    
    if not raw_paths:
        return jsonify({"text": "No files selected."})

    # Heuristic: Find common parent of selected paths to use as a local root for ASCII tree.
    # Or, client could send its `currentRoot` when calling flatten.
    # For now, let's try to find a common ancestor.
    common_path = Path(os.path.commonpath([Path(p).parent for p in raw_paths])) if raw_paths else ROOT_DIR
    
    files = []
    for p_str in raw_paths:
        pp = Path(p_str).resolve()
        # Security: Ensure files are still accessible and within a reasonable scope if necessary.
        # The original check was `(ROOT_DIR in pp.parents or pp == ROOT_DIR)`.
        # With arbitrary root paths, this check needs to be re-evaluated.
        # For now, we assume any path passed is valid if it's a file.
        if pp.is_file():
            files.append(pp)
    
    files.sort() # Ensure consistent order

    # Use the determined common_path as the root for build_nested_dict
    subset_root_for_ascii = common_path
    # However, if all files are under the global ROOT_DIR, prefer that for consistency
    # in relative_to calls for file content headers.
    # This needs careful consideration based on `currentRoot` from the client.
    # Let's assume client's `currentRoot` should be used if available.
    # The prompt doesn't specify sending `currentRoot` with flatten, so we infer.

    # If all paths are under a known root (e.g. the initial ROOT_DIR or a common parent)
    # the ASCII tree and relative paths will be more sensible.
    # The `build_nested_dict` and `ascii_tree` will use the paths as they are.
    # The relative paths for file content headers need a sensible root.

    # Let's use a dynamic root for the ASCII tree display based on selected files:
    if files:
        # Determine a suitable root for the ASCII tree representation.
        # This could be the common ancestor of all selected files.
        display_tree_root = Path(os.path.commonpath([str(f.parent) for f in files]))
    else:
        display_tree_root = Path(request.args.get("path", str(ROOT_DIR))).resolve() # Fallback to current or default root

    subset = build_nested_dict([str(f) for f in files], display_tree_root)
    header = "└── " + display_tree_root.name + "\n" # Start with the root of the selection
    header += "\n".join(ascii_tree(subset, "    ")) + "\n\n"


    body_parts = []
    for f in files:
        # For the content header, make path relative to the display_tree_root if possible,
        # otherwise show a more absolute-like path.
        try:
            rel_path_for_header = f.relative_to(display_tree_root)
        except ValueError:
            # If not directly under display_tree_root (e.g. display_tree_root is a deeper common parent)
            # show path from a higher sensible root, or absolute.
            # This can happen if files are selected from different "root" Browse sessions.
            # For simplicity, just use the name or a simplified absolute path.
            rel_path_for_header = f"../{f.name}" # Placeholder, ideally improve this

        body_parts.append(f"# {rel_path_for_header}\n")
        try:
            body_parts.append(f.read_text(encoding="utf-8") + "\n\n") # Add newline for separation
        except UnicodeDecodeError:
            body_parts.append("[binary file skipped]\n\n")
        except Exception as e:
            body_parts.append(f"[Error reading file {f.name}: {e}]\n\n")


    return jsonify({"text": header + "".join(body_parts)})

# ------------------------------------------------------------------ PRESET ROUTES
@app.get("/api/presets") # New
def list_presets():
    files = sorted(p.with_suffix("").name for p in PRESET_DIR.glob("*.json"))
    return jsonify(files)

@app.get("/api/presets/<name>") # New
def load_preset(name):
    p = preset_path(name)
    if not p.exists():
        return jsonify({"error": "not found"}), 404
    try:
        data = json.loads(p.read_text())
        # The prompt implies presets store an array of paths.
        # The example shows `{"paths": [...]}` in the POST body,
        # but the file format example is just `[...]`.
        # Let's assume the file stores the array directly as per "Preset storage details".
        if isinstance(data, dict) and "paths" in data: # To be robust
             return jsonify(data["paths"])
        elif isinstance(data, list):
             return jsonify(data) # Assuming file directly contains list of paths
        else:
            # Fallback for the POST body format just in case it was stored like that
            app.logger.warning(f"Preset '{name}' has unexpected format. Trying to read as list.")
            return jsonify(data) # Or handle error more strictly
            
    except json.JSONDecodeError:
        return jsonify({"error": "invalid preset file format"}), 500
    except Exception as e:
        app.logger.error(f"Error loading preset {name}: {e}")
        return jsonify({"error": "failed to load preset"}), 500


@app.post("/api/presets/<name>") # New
def save_preset(name):
    data = request.get_json(force=True)
    paths = data.get("paths", []) # Expects {"paths": [...]} in request body
    # Store as a simple list of paths in the JSON file as per "Preset storage details"
    try:
        preset_path(name).write_text(json.dumps(paths, indent=2))
        return jsonify({"saved": True})
    except Exception as e:
        app.logger.error(f"Error saving preset {name}: {e}")
        return jsonify({"error": "failed to save preset"}), 500


@app.delete("/api/presets/<name>") # New
def delete_preset(name):
    p = preset_path(name)
    try:
        if p.exists():
            p.unlink()
        return jsonify({"deleted": True})
    except Exception as e:
        app.logger.error(f"Error deleting preset {name}: {e}")
        return jsonify({"error": "failed to delete preset"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)