// treeb/static/js/main.js
$(function () {
  const $tree = $("#tree");

  function getCurrentTreePath() {
    return $("#rootPath").val().trim();
  }

  function applyExclusionStyles(instance) {
    if (!instance) instance = $tree.jstree(true);
    if (!instance) return;

    // Iterate over all nodes. Using get_json for comprehensive data access.
    const allNodesData = instance.get_json('#', { flat: true }); 
    allNodesData.forEach(nodeDataObj => {
        const nodeInDom = instance.get_node(nodeDataObj.id, true); // Get the LI jQuery object
        if (nodeInDom && nodeInDom.length) {
            const anchor = nodeInDom.children('.jstree-anchor');
            
            // Reset styles and state first
            anchor.removeClass('excluded-item-style');
            nodeInDom.removeAttr('title');
            if (!instance.is_disabled(nodeDataObj)) { // Only enable if not already disabled for other reasons
                 instance.enable_checkbox(nodeDataObj);
            }

            if (nodeDataObj.data && nodeDataObj.data.excluded_info) {
                anchor.addClass('excluded-item-style');
                const reason = `Excluded by ${nodeDataObj.data.excluded_info.type}: "${nodeDataObj.data.excluded_info.rule}"`;
                nodeInDom.attr('title', reason);
                instance.disable_checkbox(nodeDataObj); // Disables checkbox interaction
                
                // Crucially, ensure it's visually unchecked if the cascade somehow checked it
                // before this style application or before the check_node event corrected it.
                if (instance.is_checked(nodeDataObj)) {
                    instance.uncheck_node(nodeDataObj);
                }
            }
        }
    });
  }

  function buildTree(pathArg = "") {
    const pathForTree = pathArg || getCurrentTreePath() || ""; 
    $("#rootPath").val(pathForTree); 

    if ($tree.jstree(true)) {
      $tree.jstree(true).destroy();
    }
    $tree.empty().html("Loading tree structure...");

    $tree.jstree({
      core: {
        data: {
          url: "/api/tree",
          data: function (node) { return { 'path': $("#rootPath").val().trim() }; },
          cache: false, 
          error: function(xhr, textStatus, errorThrown) { /* ... (error handling as before) ... */
              let errorMsg = "jsTree AJAX Error: Failed to load tree data.";
              if (xhr.responseJSON && xhr.responseJSON.error) { errorMsg = `Server Error: ${xhr.responseJSON.error}`; }
              else if (xhr.statusText && xhr.statusText !== "error") { errorMsg = `Server Error (${xhr.status}): ${xhr.statusText}`; }
              else if (errorThrown) { errorMsg = `Error: ${errorThrown}`; }
              $tree.html(`<p style="color:red;">${errorMsg}</p>`); console.error("jsTree AJAX data error:", xhr, textStatus, errorThrown);
          }
        },
        check_callback: true,
        themes: { responsive: false, stripes: true, dots: true }
      },
      plugins: ["checkbox", "types"],
      checkbox: { three_state: true, cascade: "up+down" }
    })
    .on('loaded.jstree', function (e, data) { applyExclusionStyles(data.instance); })
    .on('refresh.jstree', function(e, data) { applyExclusionStyles($.jstree.reference(this)); })
    .on('after_open.jstree', function(e, data){ applyExclusionStyles(data.instance); })
    .on('load_error.jstree', (e, d) => { /* ... (error handling as before) ... */
        $tree.html(`<p style="color:red;">jsTree Internal Load Error: ${d.error || 'Unknown issue'}</p>`); console.error("jsTree load_error (internal):", d);
    })
    .on('check_node.jstree', function (e, data) { // Fires AFTER a node is checked
        if (data.node && data.node.data && data.node.data.excluded_info) {
            // If an excluded node somehow got checked (e.g., cascade), immediately uncheck it.
            // This corrects the internal state and should trigger a visual update.
            data.instance.uncheck_node(data.node);
        }
    });
  }

  // --- (Selection Preset functions: refreshPresetList, button handlers for Load/Save/Delete Presets) ---
  // --- (Path input handlers: btnLoadPath, rootPath keypress) ---
  // --- (Flatten and Copy logic: btnGenerate, btnCopy) ---
  // These sections remain IDENTICAL to your last fully working version of main.js
  // that already included the refined get_checked logic for btnGenerate and btnSavePreset.
  // For brevity, only the modified/relevant parts (buildTree, applyExclusionStyles) are shown in full detail here.
  // Make sure to integrate these into your complete main.js.
  
  // Copied from previous complete version for self-containment:
  function refreshPresetList() { 
    $.getJSON("/api/presets", list => {
      const $sel = $("#presetList").empty().append('<option value="">- Select Selection Preset -</option>');
      if (list && list.length > 0) {
        let defaultGroup = $('<optgroup label="Default Selections"></optgroup>');
        let userGroup = $('<optgroup label="User Selections"></optgroup>');
        list.forEach(preset => {
          const option = $(`<option value="${$("<div/>").text(preset.id).html()}">${$("<div/>").text(preset.name).html()}</option>`);
          (preset.type === "default" ? defaultGroup : userGroup).append(option);
        });
        if (defaultGroup.children().length > 0) $sel.append(defaultGroup);
        if (userGroup.children().length > 0) $sel.append(userGroup);
      } else { $sel.append(`<option disabled value="">No selection presets yet</option>`); }
    }).fail(() => $("#presetList").empty().append(`<option disabled value="">Error loading selection presets</option>`));
  }

  $("#btnLoadPath").on("click", () => buildTree());
  $("#rootPath").on("keypress", function(e){ if(e.which === 13) $("#btnLoadPath").click(); });
  
  $("#btnSavePreset").on("click", () => {
    const n = prompt("Save selection as (user preset):"); if (!n || n.trim()==="") return;
    const ti = $tree.jstree(true); if (!ti) {alert("Tree not initialized."); return;}
    const allCheckedNodes = ti.get_checked(false); 
    const enabledCheckedNodes = allCheckedNodes.filter(nodeId => {
        const nodeObj = ti.get_node(nodeId);
        return nodeObj && !(nodeObj.data && nodeObj.data.excluded_info); 
    });
    if (allCheckedNodes.length > 0 && enabledCheckedNodes.length === 0) {
        alert("All visually selected items are excluded. No valid items to save in preset."); return;
    }
    fetch("/api/presets/"+encodeURIComponent(n.trim()), {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify({paths:enabledCheckedNodes})})
    .then(r=>{if(!r.ok)return r.json().then(e=>{throw new Error(e.error||"Failed to save selection preset")}); return r.json();})
    .then(d=>{if(d.saved){refreshPresetList();$("#presetList").val(d.id);}else alert("Error saving selection preset: "+(d.error||"Unknown error"));}).catch(e=>{alert("Error: "+e.message);console.error("Save selection preset error:",e);});
  });

  $("#btnLoadPreset").on("click", () => {
    const pId = $("#presetList").val(); if(!pId){alert("Please select a selection preset to load.");return;}
    fetch("/api/presets/"+encodeURIComponent(pId)).then(r=>{if(!r.ok)return r.json().then(e=>{throw new Error(e.error||"Failed to load selection preset paths")});return r.json();})
    .then(pths=>{
        const ti=$tree.jstree(true); if(!ti){alert("Tree not initialized. Cannot load preset.");return;} 
        ti.uncheck_all(true); 
        const sp=pths.map(p=>String(p)); 
        const nodesToActuallyCheck = []; let excludedCount = 0;
        sp.forEach(nodeId => {
            const nodeObj = ti.get_node(nodeId);
            if (nodeObj && nodeObj.data && nodeObj.data.excluded_info) { excludedCount++; }
            else if (nodeObj) { nodesToActuallyCheck.push(nodeId); }
            else { console.warn("Path from preset not found in current tree:", nodeId); }
        });
        if (excludedCount > 0) { alert(`Note: ${excludedCount} item(s) from the preset are currently excluded and will not be selected.`); }
        ti.check_node(nodesToActuallyCheck);
        applyExclusionStyles(ti); 
        nodesToActuallyCheck.forEach(nId=>{let cn=ti.get_node(nId);if(cn){let pr=ti.get_parent(cn);while(pr&&pr!=="#"){ti.open_node(pr,null,0);pr=ti.get_parent(pr);}}});
    }).catch(e=>{alert("Error loading selection preset: "+e.message);console.error("Load selection preset error:",e);});
  });

  $("#btnDeletePreset").on("click", () => {
    const pId=$("#presetList").val(); if(!pId){alert("Please select a selection preset to delete.");return;}
    if(!pId.startsWith("user/")){alert("Only user selection presets can be deleted.");return;}
    const pName = pId.substring("user/".length); if(!confirm("Delete user selection preset '"+pName+"'?"))return;
    fetch("/api/presets/"+encodeURIComponent(pId),{method:"DELETE"}).then(r=>{if(!r.ok)return r.json().then(e=>{throw new Error(e.error||"Failed to delete selection preset")});return r.json();})
    .then(d=>{if(d.deleted)refreshPresetList();else alert("Error deleting selection preset: "+(d.error||"Unknown error"));}).catch(e=>{alert("Error: "+e.message);console.error("Delete selection preset error:",e);});
  });

  $("#btnGenerate").on("click", () => {
    const treeInstance = $tree.jstree(true);
    if (!treeInstance) { alert("Tree not init."); $("#result").val("Tree N/A."); $("#charCountDisplay").html(""); return; }
    const allCheckedNodes = treeInstance.get_checked(false); 
    const nonExcludedCheckedNodes = allCheckedNodes.filter(nodeId => {
        const nodeObj = treeInstance.get_node(nodeId);
        return nodeObj && !(nodeObj.data && nodeObj.data.excluded_info);
    });
    if (allCheckedNodes.length > 0 && nonExcludedCheckedNodes.length === 0) {
        alert("All selected items are currently excluded by hardcoded rules. Nothing to generate.");
        $("#result").val("All selected items are excluded."); $("#charCountDisplay").html("0 tokens"); return;
    }
     if (nonExcludedCheckedNodes.length === 0) { 
        $("#result").val("No processable items selected."); $("#charCountDisplay").html("0 tokens"); return;
    }
    $("#result").val("Generating..."); $("#charCountDisplay").html("Calculating...");
    fetch("/api/flatten", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: nonExcludedCheckedNodes }) })
    .then(response => { if (!response.ok) { return response.json().catch(() => response.text().then(text => { throw new Error("Server error: " + (response.statusText || text)); })) .then(errData => { if (errData && errData.error) throw new Error(errData.error); if (typeof errData === 'string') throw new Error("Server error: " + errData); throw new Error("Generate failed. Status: " + response.status);  }); } return response.json(); })
    .then(data => {
        $("#result").val(data.text !== undefined ? data.text : "Error: No text.");
        let tokenInfoHtml = ""; 
        if (data.token_count !== undefined) {
            tokenInfoHtml = data.token_count + " tokens";
            if (data.model_percentages && data.model_percentages.length > 0) {
                tokenInfoHtml += " / ";
                const percentagesHtmlParts = data.model_percentages.map(m => {
                    let percVal = parseFloat(m.percentage); let displayPercStr; let color = "#333";
                    if (isNaN(percVal)) { displayPercStr = "N/A"; color = "#777"; }
                    else {
                        if (percVal === 0) { color = "#6c757d"; } else if (percVal < 50) { color = "green"; }
                        else if (percVal < 80) { color = "orange"; } else if (percVal <= 100) { color = "red"; }
                        else { color = "#b30000"; }
                        if (percVal === 0) { displayPercStr = "0"; } else if (percVal < 0.1 && percVal > 0) { displayPercStr = percVal.toFixed(2); }
                        else if (percVal < 10) { displayPercStr = percVal.toFixed(1); } else { displayPercStr = Math.round(percVal).toString(); }
                        if (displayPercStr.endsWith(".0")) { displayPercStr = displayPercStr.slice(0, -2); }
                    } return `${m.name}: <span style="color: ${color}; font-weight: normal;">${displayPercStr}%</span>`;
                }).join(", "); tokenInfoHtml += percentagesHtmlParts;
            }
        } else { tokenInfoHtml = "Token info N/A"; }
        $("#charCountDisplay").html(tokenInfoHtml);
    }).catch(error => { $("#result").val("Error: " + error.message); $("#charCountDisplay").html("Error tokenizing"); console.error("Flatten error:", error); });
  });
  $("#btnCopy").on("click", () => {
    const rt = $("#result").val(); if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(rt).catch(err => { console.error("Copy fail: ", err); alert("Copy fail."); }); } else { $("#result").select(); try { document.execCommand('copy'); } catch (err) { alert("Auto-copy fail."); } }
  });

  // BOOTSTRAP
  buildTree(); 
  refreshPresetList();  
  $("#charCountDisplay").html(""); 
});