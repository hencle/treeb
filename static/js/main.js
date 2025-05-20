// treeb/static/js/main.js
$(function () {
  const $tree = $("#tree");

  function getCurrentTreePath() {
    return $("#rootPath").val().trim();
  }

  // Helper function to apply styles AND disable checkbox for excluded nodes
  function applyExclusionStyles(instance) {
    if (!instance) instance = $tree.jstree(true);
    if (!instance) { console.warn("applyExclusionStyles: jsTree instance not found."); return; }

    const allNodeIds = instance.get_json('#', { flat: true, no_state: true, no_data: false }).map(n => n.id);

    allNodeIds.forEach(nodeId => {
        const nodeObj = instance.get_node(nodeId);
        const domNodeLi = instance.get_node(nodeId, true); 

        if (nodeObj && domNodeLi && domNodeLi.length) {
            const anchor = domNodeLi.children('.jstree-anchor');
            
            instance.enable_checkbox(nodeObj); // Default to enabled, then disable if excluded
            anchor.removeClass('excluded-item-style');
            domNodeLi.removeAttr('title'); 

            if (nodeObj.data && nodeObj.data.excluded_info) {
                anchor.addClass('excluded-item-style');
                const reason = `Excluded by ${nodeObj.data.excluded_info.type}: "${nodeObj.data.excluded_info.rule}"`;
                domNodeLi.attr('title', reason);
                instance.disable_checkbox(nodeObj); 
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
          error: function(xhr, textStatus, errorThrown) {
              let errorMsg = "jsTree AJAX Error: Failed to load tree data.";
              if (xhr.responseJSON && xhr.responseJSON.error) { errorMsg = `Server Error: ${xhr.responseJSON.error}`; }
              else if (xhr.statusText && xhr.statusText !== "error") { errorMsg = `Server Error (${xhr.status}): ${xhr.statusText}`; }
              else if (errorThrown) { errorMsg = `Error: ${errorThrown}`; }
              $tree.html(`<p style="color:red;">${errorMsg}</p>`);
              console.error("jsTree AJAX data error:", xhr, textStatus, errorThrown);
          }
        },
        check_callback: true,
        themes: { responsive: false, stripes: true, dots: true }
      },
      plugins: ["checkbox", "types", "conditionalselect"], 
      checkbox: { 
        three_state: true, 
        cascade: "up+down" 
      },
      conditionalselect: function (node, event) {
        // Check if node itself or any parent is effectively excluded
        let instance = $.jstree.reference(node.id); // Get instance from node
        let current = node;
        while(current) { // Iterate up to root
            if (current.data && current.data.excluded_info) {
                return false; // Prevent selection if node or any ancestor is excluded
            }
            if (current.parent === '#' || !current.parent) break; // Reached root or no parent
            current = instance.get_node(current.parent);
        }
        return true;
      }
    })
    .on('loaded.jstree', function (e, data) { 
        applyExclusionStyles(data.instance);
    })
    .on('refresh.jstree', function(e, data) { 
        applyExclusionStyles($.jstree.reference(this)); 
    })
    .on('after_open.jstree', function(e, data){ 
        applyExclusionStyles(data.instance); 
    })
    .on('load_error.jstree', (e, d) => { 
        $tree.html(`<p style="color:red;">jsTree Internal Load Error: ${d.error || 'Unknown jsTree issue'}</p>`);
        console.error("jsTree load_error event (internal):", d);
    });
  }

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
    const checkedNodes = ti.get_checked(false); // conditionalselect ensures these are not excluded
    if (checkedNodes.length === 0) { alert("No items selected to save in preset."); return; }
    fetch("/api/presets/"+encodeURIComponent(n.trim()), {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify({paths:checkedNodes})})
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
        
        // Attempt to check nodes; conditionalselect will prevent checking excluded ones.
        ti.check_node(sp); 
        applyExclusionStyles(ti); // Ensure styles are correct after check attempts

        const actuallyChecked = ti.get_checked(false);
        let attemptedCount = sp.length;
        if (attemptedCount > 0 && actuallyChecked.length < attemptedCount) {
             alert(`Note: ${attemptedCount - actuallyChecked.length} item(s) from the preset were not selected as they are currently excluded or do not exist.`);
        }
        actuallyChecked.forEach(nId=>{let cn=ti.get_node(nId);if(cn){let pr=ti.get_parent(cn);while(pr&&pr!=="#"){ti.open_node(pr,null,0);pr=ti.get_parent(pr);}}});
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
    const checkedNodes = treeInstance.get_checked(false); // conditionalselect ensures these are not effectively excluded
    if (checkedNodes.length === 0) {
        $("#result").val("No items selected (or all selections are excluded by hardcoded rules).");
        $("#charCountDisplay").html("0 tokens"); return;
    }
    $("#result").val("Generating..."); $("#charCountDisplay").html("Calculating...");
    fetch("/api/flatten", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: checkedNodes }) })
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