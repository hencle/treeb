// treeb/static/js/main.js
let currentRoot = "";   // remember which tree we’re showing

$(function () {
  //----------------------------------------------------------------
  const $tree = $("#tree");

  function buildTree(path = "") {
    currentRoot = path; // Store the path being loaded
    // Update the input field with the path being loaded, if not already set by user typing
    if ($("#rootPath").val() !== path) {
        $("#rootPath").val(path);
    }
    $.getJSON("/api/tree", { path }, data => {
      if (data.error) {
        alert("Error loading tree: " + data.error);
        // Optionally clear the tree or show an error message in the tree area
        $tree.empty().html(`<p style="color:red;">Error: ${data.error}</p>`);
        return;
      }
      // Destroy existing jstree instance if it exists, before reinitializing
      if ($tree.jstree(true)) {
        $tree.jstree(true).destroy();
      }
      $tree
        .empty() // Ensure it's empty before creating new tree
        .jstree({
          core: { 
            data: [data], 
            check_callback: true,
            themes: {
                responsive: false, // try to prevent auto-width issues
                stripes: true
            }
          },
          plugins: ["checkbox", "types"],
          checkbox: { 
            three_state: true, // Allow partial selection of folders
            cascade: "up+down" // Check/uncheck children and parents
          }
        });
    });
  }

  function refreshPresetList() {
    $.getJSON("/api/presets", list => {
      const $sel = $("#presetList").empty();
      if (list && list.length > 0) {
        list.forEach(n => $sel.append(`<option value="${$("<div/>").text(n).html()}">${$("<div/>").text(n).html()}</option>`));
      } else {
        $sel.append(`<option disabled>No presets yet</option>`);
      }
    });
  }

  //---------------------------------------------------------------- PATH HANDLING
  $("#btnLoadPath").on("click", () => {
    const p = $("#rootPath").val().trim();
    // No need for 'if (p)' check here, empty path will load default root in backend
    buildTree(p);
  });

  // Also allow loading path by pressing Enter in the input field
  $("#rootPath").on("keypress", function(e) {
    if (e.which === 13) { // Enter key pressed
      $("#btnLoadPath").click();
    }
  });

  //---------------------------------------------------------------- PRESETS
  $("#btnSavePreset").on("click", () => {
    const name = prompt("Preset name?");
    if (!name || name.trim() === "") return;
    
    const treeInstance = $tree.jstree(true);
    if (!treeInstance) {
        alert("Tree not initialized.");
        return;
    }
    const checkedNodes = treeInstance.get_checked(false); // Get IDs of checked nodes
    // We need absolute paths. jsTree node IDs are already absolute paths.

    fetch("/api/presets/" + encodeURIComponent(name.trim()), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The prompt implies the backend expects { "paths": [...] } for saving
      // And the preset file format is just [...]
      // The backend `save_preset` function should handle this by storing `paths` directly.
      body: JSON.stringify({ paths: checkedNodes }) 
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.error || "Failed to save preset") });
        }
        return response.json();
    })
    .then(data => {
        if (data.saved) {
            refreshPresetList();
        } else {
            alert("Error saving preset: " + (data.error || "Unknown error"));
        }
    })
    .catch(error => {
        alert("Error: " + error.message);
        console.error("Save preset error:", error);
    });
  });

  $("#btnLoadPreset").on("click", () => {
    const name = $("#presetList").val();
    if (!name) {
        alert("Please select a preset to load.");
        return;
    }
    fetch("/api/presets/" + encodeURIComponent(name))
      .then(r => {
        if (!r.ok) {
            return r.json().then(err => { throw new Error(err.error || "Failed to load preset paths") });
        }
        return r.json();
      })
      .then(paths => { // Expecting 'paths' to be an array of absolute path strings
        const jstreeInstance = $tree.jstree(true);
        if (!jstreeInstance) {
            alert("Tree not initialized. Cannot load preset.");
            return;
        }
        jstreeInstance.uncheck_all(true); // true to prevent event firing for each uncheck
        
        // jsTree check_node can take an array of node IDs.
        // Ensure paths are strings, as expected by jsTree.
        const stringPaths = paths.map(p => String(p));
        jstreeInstance.check_node(stringPaths);

        // Optional: Expand nodes to show checked items
        // This might be slow for many paths or deep trees.
        // Consider expanding only parents of checked nodes.
        // jstreeInstance.open_node(stringPaths); // This might not work as expected for paths.
        // A more robust way is to open parent nodes of each checked node.
        stringPaths.forEach(nodeId => {
            let parent = jstreeInstance.get_parent(nodeId);
            while(parent && parent !== "#") { // # is the root of the jstree display
                jstreeInstance.open_node(parent, null, 0); // Open parent without animation
                parent = jstreeInstance.get_parent(parent);
            }
        });

      })
      .catch(error => {
          alert("Error loading preset: " + error.message);
          console.error("Load preset error:", error);
      });
  });

  $("#btnDeletePreset").on("click", () => {
    const name = $("#presetList").val();
    if (!name) {
        alert("Please select a preset to delete.");
        return;
    }
    if (!confirm("Delete preset '" + name + "'?")) return;
    fetch("/api/presets/" + encodeURIComponent(name), { method: "DELETE" })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.error || "Failed to delete preset") });
        }
        return response.json();
    })
    .then(data => {
        if (data.deleted) {
            refreshPresetList();
        } else {
            alert("Error deleting preset: " + (data.error || "Unknown error"));
        }
    })
    .catch(error => {
        alert("Error: " + error.message);
        console.error("Delete preset error:", error);
    });
  });

  //---------------------------------------------------------------- FLATTEN
  $("#btnGenerate").on("click", () => {
    const treeInstance = $tree.jstree(true);
    if (!treeInstance) {
        alert("Tree not initialized.");
        $("#result").val("Tree not available.");
        return;
    }
    const checkedNodes = treeInstance.get_checked(false); // Get IDs of checked nodes (absolute paths)
    
    // Include currentRoot when calling flatten, so backend knows the context for ASCII tree.
    // The prompt doesn't explicitly state this, but it's useful for `build_nested_dict`
    // if the preset paths could originate from a different root than the default one.
    // However, the backend current implementation of flatten infers the root.
    // For now, we stick to the provided backend API.
    fetch("/api/flatten", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
          paths: checkedNodes
          // current_tree_root: currentRoot // Potentially useful for backend if it needs it
      })
    })
    .then(r => {
        if (!r.ok) {
            return r.text().then(text => { throw new Error("Failed to generate: " + text )});
        }
        return r.json();
    })
    .then(data => {
        if (data.text !== undefined) {
            $("#result").val(data.text);
        } else if (data.error) {
            $("#result").val("Error generating text: " + data.error);
        }
    })
    .catch(error => {
        $("#result").val("Error: " + error.message);
        console.error("Flatten error:", error);
    });
  });

  $("#btnCopy").on("click", () => {
    const resultText = $("#result").val();
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(resultText)
            .then(() => {
                // Optional: show a brief "Copied!" message
            })
            .catch(err => {
                console.error("Failed to copy text: ", err);
                alert("Failed to copy text. You might need to copy manually.");
            });
    } else {
        // Fallback for older browsers
        $("#result").select();
        try {
            document.execCommand('copy');
        } catch (err) {
            alert("Failed to copy text automatically. Please copy manually.");
        }
    }
  });

  //---------------------------------------------------------------- bootstrap
  buildTree();          // Load with default ROOT_DIR from backend
  refreshPresetList();  // Fill preset dropdown
});