// treeb/static/js/main.js
$(function () {
  //----------------------------------------------------------------
  const $tree = $("#tree");
  let currentRoot = ""; // To remember the current root path being displayed

  function buildTree(path = "") {
    currentRoot = path; // Store the path being loaded
    if ($("#rootPath").val() !== path) {
        $("#rootPath").val(path);
    }
    
    $tree.html('Loading tree...'); // Placeholder while loading

    $.getJSON("/api/tree", { path })
      .done(data => {
        if ($tree.jstree(true)) {
          $tree.jstree(true).destroy();
        }
        $tree.empty().jstree({
            core: { 
              data: [data],  // data should be the root node object
              check_callback: true,
              themes: { responsive: false, stripes: true }
            },
            plugins: ["checkbox", "types"],
            checkbox: { 
              three_state: true, 
              cascade: "up+down" 
            }
          })
          .on('loaded.jstree', function () {
            // Expand the root node slightly if you want
            // $tree.jstree('open_node', $tree.jstree('get_node', '#').children[0]);
          })
          .on('load_error.jstree', function (e, data) {
            $tree.html(`<p style="color:red;">Error loading tree: ${data.error || 'Unknown jstree error'}</p>`);
          });
      })
      .fail((jqXHR, textStatus, errorThrown) => {
        let errorMsg = "Failed to load tree data.";
        if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
            errorMsg = jqXHR.responseJSON.error;
        } else if (jqXHR.responseText) {
            try {
                const resp = JSON.parse(jqXHR.responseText);
                errorMsg = resp.error || errorMsg;
            } catch(e) { /* ignore parsing error if not JSON */ }
        }
        $tree.html(`<p style="color:red;">Error: ${errorMsg}</p>`);
        console.error("Build tree error:", textStatus, errorThrown, jqXHR.responseText);
      });
  }

  function refreshPresetList() {
    $.getJSON("/api/presets", list => {
      const $sel = $("#presetList").empty();
      if (list && list.length > 0) {
        let defaultGroup = $('<optgroup label="Default Presets"></optgroup>');
        let userGroup = $('<optgroup label="User Presets"></optgroup>');
        
        list.forEach(preset => {
          const option = $(`<option value="${$("<div/>").text(preset.id).html()}">${$("<div/>").text(preset.name).html()}</option>`);
          if (preset.type === "default") {
            defaultGroup.append(option);
          } else {
            userGroup.append(option);
          }
        });

        if (defaultGroup.children().length > 0) $sel.append(defaultGroup);
        if (userGroup.children().length > 0) $sel.append(userGroup);
        
        if ($sel.children().length === 0) { // Should not happen if list has items, but good fallback
             $sel.append(`<option disabled value="">No presets found</option>`);
        }
      } else {
        $sel.append(`<option disabled value="">No presets yet</option>`);
      }
    }).fail(() => {
        $("#presetList").empty().append(`<option disabled value="">Error loading presets</option>`);
    });
  }

  //---------------------------------------------------------------- PATH HANDLING
  $("#btnLoadPath").on("click", () => {
    const p = $("#rootPath").val().trim();
    buildTree(p);
  });

  $("#rootPath").on("keypress", function(e) {
    if (e.which === 13) { // Enter key pressed
      $("#btnLoadPath").click();
    }
  });

  //---------------------------------------------------------------- PRESETS
  $("#btnSavePreset").on("click", () => {
    const name = prompt("Save preset as (user preset):");
    if (!name || name.trim() === "") return;
    
    const treeInstance = $tree.jstree(true);
    if (!treeInstance) {
        alert("Tree not initialized."); return;
    }
    const checkedNodes = treeInstance.get_checked(false); 

    fetch("/api/presets/" + encodeURIComponent(name.trim()), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: checkedNodes }) 
    })
    .then(response => {
        if (!response.ok) return response.json().then(err => { throw new Error(err.error || "Failed to save preset") });
        return response.json();
    })
    .then(data => {
        if (data.saved) {
            refreshPresetList();
            // Optionally select the newly saved preset
            $("#presetList").val(data.id);
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
    const presetId = $("#presetList").val(); // This is now "type/name"
    if (!presetId) {
        alert("Please select a preset to load."); return;
    }
    fetch("/api/presets/" + encodeURIComponent(presetId)) // presetId already includes type/name
      .then(r => {
        if (!r.ok) return r.json().then(err => { throw new Error(err.error || "Failed to load preset paths") });
        return r.json();
      })
      .then(paths => { 
        const jstreeInstance = $tree.jstree(true);
        if (!jstreeInstance) {
            alert("Tree not initialized. Cannot load preset."); return;
        }
        jstreeInstance.uncheck_all(true); 
        const stringPaths = paths.map(p => String(p));
        jstreeInstance.check_node(stringPaths);

        stringPaths.forEach(nodeId => {
            let currentNode = jstreeInstance.get_node(nodeId);
            if (currentNode) { // Ensure node exists in current tree
                let parent = jstreeInstance.get_parent(currentNode);
                while(parent && parent !== "#") { 
                    jstreeInstance.open_node(parent, null, 0); 
                    parent = jstreeInstance.get_parent(parent);
                }
            } else {
                console.warn("Preset path not found in current tree:", nodeId);
            }
        });
      })
      .catch(error => {
          alert("Error loading preset: " + error.message);
          console.error("Load preset error:", error);
      });
  });

  $("#btnDeletePreset").on("click", () => {
    const presetId = $("#presetList").val(); // This is "type/name"
    if (!presetId) {
        alert("Please select a preset to delete."); return;
    }
    if (!presetId.startsWith("user/")) {
        alert("Only user presets can be deleted through this interface."); return;
    }
    const presetName = presetId.substring("user/".length); // Get actual name for confirm dialog
    if (!confirm("Delete user preset '" + presetName + "'?")) return;

    fetch("/api/presets/" + encodeURIComponent(presetId), { method: "DELETE" })
    .then(response => {
        if (!response.ok) return response.json().then(err => { throw new Error(err.error || "Failed to delete preset") });
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
    const checkedNodes = treeInstance.get_checked(false); 
    
    fetch("/api/flatten", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: checkedNodes })
    })
    .then(r => {
        if (!r.ok) return r.text().then(text => { throw new Error("Failed to generate text. Server said: " + text )});
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
        $("#result").val("Error while generating: " + error.message);
        console.error("Flatten error:", error);
    });
  });

  $("#btnCopy").on("click", () => {
    const resultText = $("#result").val();
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(resultText)
            .then(() => { /* Optional: show "Copied!" message */ })
            .catch(err => {
                console.error("Failed to copy text: ", err);
                alert("Failed to copy text. You might need to copy manually.");
            });
    } else {
        $("#result").select();
        try { document.execCommand('copy'); } 
        catch (err) { alert("Failed to copy text automatically. Please copy manually."); }
    }
  });

  //---------------------------------------------------------------- bootstrap
  buildTree($("#rootPath").val().trim()); // Load with initial path from input, or default if empty
  refreshPresetList();  // Fill preset dropdown
});