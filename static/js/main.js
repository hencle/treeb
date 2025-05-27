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

      // Get all nodes currently loaded in the tree instance
      const allNodeIds = instance.get_json('#', { flat: true, no_state: true, no_data: false }).map(n => n.id);

      allNodeIds.forEach(nodeId => {
          const nodeObj = instance.get_node(nodeId);
          const domNodeLi = instance.get_node(nodeId, true); // Get the LI element

          if (nodeObj && domNodeLi && domNodeLi.length) {
              const anchor = domNodeLi.children('.jstree-anchor');

              // Reset styles first
              instance.enable_checkbox(nodeObj); // Default to enabled
              anchor.removeClass('excluded-item-style');
              domNodeLi.removeAttr('title'); // Remove old tooltip

              if (nodeObj.data && nodeObj.data.excluded_info) {
                  anchor.addClass('excluded-item-style');
                  const reason = `Excluded by ${nodeObj.data.excluded_info.type}: "${nodeObj.data.excluded_info.rule}"`;
                  domNodeLi.attr('title', reason); // Add tooltip to the LI element
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
                  data: function (node) { // node is the jstree node object
                      if (node.id === "#") { // For the initial load (root node)
                          return { 'id': '#', 'path': $("#rootPath").val().trim() };
                      } else { // For lazy loading children of an expanded node
                          // node.id is the absolute path of the parent, sent by dir_to_js_lazy
                          return { 'id': node.id };
                      }
                  },
                  cache: false, // Disable caching for dynamic content
                  error: function(xhr, textStatus, errorThrown) {
                      let errorMsg = "jsTree AJAX Error: Failed to load tree data.";
                      if (xhr.responseJSON && xhr.responseJSON.error) {
                          errorMsg = `Server Error: ${xhr.responseJSON.error}`;
                      } else if (xhr.responseJSON && Array.isArray(xhr.responseJSON) && xhr.responseJSON.length > 0 && xhr.responseJSON[0].text) {
                          // Handle cases where server returns an error node object like in api_tree
                          errorMsg = `Server: ${xhr.responseJSON[0].text}`;
                      } else if (xhr.statusText && xhr.statusText !== "error") {
                          errorMsg = `Server Error (${xhr.status}): ${xhr.statusText}`;
                      } else if (errorThrown) {
                          errorMsg = `Error: ${errorThrown}`;
                      }
                      $tree.html(`<p style="color:red;">${errorMsg}</p>`);
                      console.error("jsTree AJAX data error:", xhr, textStatus, errorThrown);
                  }
              },
              check_callback: true, // Allows checking nodes, etc.
              themes: { responsive: false, stripes: true, dots: true } // Standard theme
          },
          plugins: ["checkbox", "types", "conditionalselect"], //"wholerow"
          checkbox: {
              three_state: true, // Standard parent/child selection behavior
              cascade: "up+down" // Check/uncheckان cascades to children and parents
          },
          conditionalselect: function (node, event) {
              // Check if node itself or any parent is effectively excluded
              // This function is called BEFORE a node is selected/deselected
              let instance = $.jstree.reference(node.id); // Get instance from node
              let current = node;
              while(current) { // Iterate up to root
                  if (current.data && current.data.excluded_info) {
                      return false; // Prevent selection if node or any ancestor is excluded
                  }
                  if (current.parent === '#' || !current.parent) break; // Reached root or no parent
                  current = instance.get_node(current.parent);
              }
              return true; // Allow selection
          }
      })
      .on('loaded.jstree', function (e, data) { // After initial tree is loaded
          applyExclusionStyles(data.instance);
          // You might want to open the root node by default if it's a single root
          const rootNodeId = data.instance.get_node('#').children[0];
          if (rootNodeId) {
              data.instance.open_node(rootNodeId, null, 0); // Open silently, 0 for no animation
          }
      })
      .on('refresh.jstree', function(e, data) { // If tree is refreshed
          applyExclusionStyles($.jstree.reference(this));
      })
      .on('after_open.jstree', function(e, data){ // After a node is opened (lazy loaded its children)
          applyExclusionStyles(data.instance);
      })
      .on('load_error.jstree', (e, d) => { // Internal jsTree error on loading a node's children
          // This is different from core.data.error which is for the AJAX request itself.
          // This usually indicates a problem with the data format returned for children.
          const parentNode = d.element === -1 ? $tree.jstree(true).get_node(d.data.id) : $tree.jstree(true).get_node(d.element);
          const parentNodeText = parentNode ? parentNode.text : "Unknown node";
          $tree.append(`<p style="color:orange;">jsTree: Could not load children for "${parentNodeText}". Server response might be invalid.</p>`);
          console.error("jsTree load_error event (internal, for children of a node):", d);
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
      // get_checked(false) gets only leaf nodes if three_state is true and cascade is on.
      // get_checked(true) gets all checked nodes including indeterminate ones.
      // For saving, we want all explicitly checked nodes, even if they are directories.
      // The backend /api/flatten will handle expanding directories.
      // The node IDs are absolute paths.
      const checkedNodesPaths = ti.get_checked(true).map(nodeId => ti.get_node(nodeId).id);

      if (checkedNodesPaths.length === 0) { alert("No items selected to save in preset."); return; }

      fetch("/api/presets/"+encodeURIComponent(n.trim()), {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({paths: checkedNodesPaths}) // Send absolute paths
      })
      .then(r => { if(!r.ok) return r.json().then(e => {throw new Error(e.error || "Failed to save selection preset")}); return r.json();})
      .then(d => {
          if(d.saved){
              refreshPresetList();
              $("#presetList").val(d.id); // Select the newly saved preset
              alert(`Preset '${d.name}' saved.`);
          } else {
              alert("Error saving selection preset: "+(d.error||"Unknown error"));
          }
      }).catch(e => { alert("Error: "+e.message); console.error("Save selection preset error:", e); });
  });

  $("#btnLoadPreset").on("click", () => {
      const presetId = $("#presetList").val(); if(!presetId){alert("Please select a selection preset to load.");return;}
      fetch("/api/presets/"+encodeURIComponent(presetId))
      .then(r => { if(!r.ok) return r.json().then(e => {throw new Error(e.error || "Failed to load preset paths")}); return r.json();})
      .then(absolutePathsFromPreset => { // Expecting a list of absolute paths
          const treeInstance = $tree.jstree(true);
          if(!treeInstance){alert("Tree not initialized. Cannot load preset.");return;}
          treeInstance.uncheck_all(true); // Silent uncheck

          // With lazy loading, nodes might not exist. jsTree's check_node will only check existing nodes.
          // This is an accepted limitation for now. User might need to expand tree sections.
          // The paths in the preset are absolute paths.
          treeInstance.check_node(absolutePathsFromPreset); // Attempt to check nodes

          // Open parent nodes of newly checked items to make them visible.
          // This might be slow if many deep nodes are checked and need their parents loaded.
          // Consider if this is too aggressive for lazy loading.
          const actuallyChecked = treeInstance.get_checked(false); // Get leaves that are checked
          let loadedAndCheckedCount = 0;
          absolutePathsFromPreset.forEach(pathStr => {
              if (treeInstance.get_node(pathStr) && treeInstance.is_checked(pathStr)) {
                  loadedAndCheckedCount++;
                  let currentNode = treeInstance.get_node(pathStr);
                  if (currentNode) {
                      let parentPath = treeInstance.get_parent(currentNode);
                      while(parentPath && parentPath !== "#") {
                          treeInstance.open_node(parentPath, null, 0); // Open silently
                          parentPath = treeInstance.get_parent(parentPath);
                      }
                  }
              }
          });
          applyExclusionStyles(treeInstance); // Re-apply styles as selection might have changed disabled state visually

          if (absolutePathsFromPreset.length > 0 && loadedAndCheckedCount < absolutePathsFromPreset.length) {
              alert(`Note: ${absolutePathsFromPreset.length - loadedAndCheckedCount} item(s) from the preset were not selected. They might be excluded, not exist, or their parent directories haven't been expanded yet.`);
          }
      }).catch(e => { alert("Error loading selection preset: "+e.message); console.error("Load selection preset error:", e); });
  });

  $("#btnDeletePreset").on("click", () => {
      const pId = $("#presetList").val(); if(!pId){alert("Please select a selection preset to delete.");return;}
      if(!pId.startsWith("user/")){alert("Only user selection presets can be deleted.");return;}
      const pName = pId.substring("user/".length); if(!confirm("Delete user selection preset '"+pName+"'?"))return;
      fetch("/api/presets/"+encodeURIComponent(pId),{method:"DELETE"})
      .then(r => { if(!r.ok) return r.json().then(e => {throw new Error(e.error || "Failed to delete selection preset")}); return r.json();})
      .then(d => {
          if(d.deleted){
              refreshPresetList(); // Refresh list, deleted one will be gone
              alert(`Preset '${pName}' deleted.`);
          } else {
              alert("Error deleting selection preset: "+(d.error||"Unknown error"));
          }
      }).catch(e => { alert("Error: "+e.message); console.error("Delete selection preset error:", e); });
  });

  $("#btnGenerate").on("click", () => {
      const treeInstance = $tree.jstree(true);
      if (!treeInstance) {
          alert("Tree not initialized.");
          $("#result").val("Tree not available.");
          $("#charCountDisplay").html("");
          return;
      }
      // Get all checked nodes, including indeterminate ones (directories).
      // Their IDs are absolute paths.
      const checkedNodesPaths = treeInstance.get_checked(true).map(nodeId => treeInstance.get_node(nodeId).id);

      if (checkedNodesPaths.length === 0) {
          $("#result").val("No items selected (or all selections are filtered out by exclusion rules).");
          $("#charCountDisplay").html("0 tokens");
          return;
      }
      $("#result").val("Generating output, please wait...");
      $("#charCountDisplay").html("Calculating token count...");

      fetch("/api/flatten", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths: checkedNodesPaths }) // Send absolute paths
      })
      .then(response => {
          if (!response.ok) {
              // Try to parse JSON error first, then fallback to text
              return response.json()
                  .catch(() => response.text().then(text => { throw new Error("Server error: " + (text || response.statusText)); }))
                  .then(errData => {
                      if (errData && errData.error) throw new Error(errData.error);
                      if (typeof errData === 'string') throw new Error("Server error: " + errData); // Should be caught by .text() above
                      throw new Error("Generate failed. Status: " + response.status);
                  });
          }
          return response.json();
      })
      .then(data => {
          $("#result").val(data.text !== undefined ? data.text : "Error: No text returned from server.");
          let tokenInfoHtml = "";
          if (data.token_count !== undefined && data.token_count >= 0) {
              tokenInfoHtml = data.token_count + " tokens";
              if (data.model_percentages && data.model_percentages.length > 0) {
                  tokenInfoHtml += " / ";
                  const percentagesHtmlParts = data.model_percentages.map(m => {
                      let percVal = parseFloat(m.percentage); let displayPercStr; let color = "#333"; // Default color
                      if (isNaN(percVal)) {
                          displayPercStr = "N/A"; color = "#777"; // Grey for N/A
                      } else {
                          if (percVal === 0) { color = "#6c757d"; } // Bootstrap secondary color (greyish)
                          else if (percVal < 50) { color = "green"; }
                          else if (percVal < 80) { color = "orange"; }
                          else if (percVal <= 100) { color = "red"; }
                          else { color = "#b30000"; } // Darker red for over 100%

                          if (percVal === 0) { displayPercStr = "0"; }
                          else if (percVal < 0.1 && percVal > 0) { displayPercStr = percVal.toFixed(2); } // e.g. 0.01
                          else if (percVal < 10) { displayPercStr = percVal.toFixed(1); } // e.g. 7.5
                          else { displayPercStr = Math.round(percVal).toString(); } // e.g. 50 or 100

                          if (displayPercStr.endsWith(".0")) { displayPercStr = displayPercStr.slice(0, -2); } // 7.0 -> 7
                      }
                      return `${m.name}: <span style="color: ${color}; font-weight: normal;">${displayPercStr}%</span>`;
                  }).join(", ");
                  tokenInfoHtml += percentagesHtmlParts;
              }
          } else if (data.token_count === -1) { // Error during tokenization
               tokenInfoHtml = "Tokenization Error";
               if (data.model_percentages && data.model_percentages.length > 0 && data.model_percentages[0].name === "Error") {
                   // Additional info from server about tokenization error
               }
          }
          else {
              tokenInfoHtml = "Token info not available.";
          }
          $("#charCountDisplay").html(tokenInfoHtml);
      }).catch(error => {
          $("#result").val("Error during generation: " + error.message);
          $("#charCountDisplay").html("Error calculating tokens.");
          console.error("Flatten API call error:", error);
      });
  });

  $("#btnCopy").on("click", () => {
      const rt = $("#result").val();
      if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(rt).then(() => {
              // Optional: Show a brief "Copied!" message
          }).catch(err => {
              console.error("Async copy failed: ", err);
              alert("Automatic copy failed. Please copy manually.");
          });
      } else { // Fallback for older browsers
          $("#result").select();
          try {
              document.execCommand('copy');
          } catch (err) {
              alert("Automatic copy failed. Please copy manually.");
          }
      }
  });

  // --- Initial Setup ---
  buildTree(); // Load initial tree based on #rootPath value
  refreshPresetList(); // Populate preset dropdown
  $("#charCountDisplay").html(""); // Clear token count initially
});