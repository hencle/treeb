// treeb/static/js/main.js
$(function () {
  const $tree = $("#tree");
  const $rootPathInput = $("#rootPath");
  const $btnBrowsePath = $("#btnBrowsePath"); // Will be disabled/enabled by template
  const $btnLoadPath = $("#btnLoadPath");
  const $charCountDisplay = $("#charCountDisplay");
  const $resultTextArea = $("#result");


  function getCurrentTreePath() {
      return $rootPathInput.val().trim();
  }

  function applyExclusionStyles(instance) {
      if (!instance) instance = $tree.jstree(true);
      if (!instance) { console.warn("applyExclusionStyles: jsTree instance not found."); return; }

      const allNodeIds = instance.get_json('#', { flat: true, no_state: true, no_data: false }).map(n => n.id);

      allNodeIds.forEach(nodeId => {
          const nodeObj = instance.get_node(nodeId);
          const domNodeLi = instance.get_node(nodeId, true); 

          if (nodeObj && domNodeLi && domNodeLi.length) {
              const anchor = domNodeLi.children('.jstree-anchor');
              
              instance.enable_checkbox(nodeObj); 
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
      $rootPathInput.val(pathForTree);

      if ($tree.jstree(true)) {
          $tree.jstree(true).destroy();
      }
      $tree.empty().html("<i>Loading tree structure, please wait...</i>");

      $tree.jstree({
          core: {
              data: {
                  url: "/api/tree",
                  data: function (node) { 
                      if (node.id === "#") { 
                          return { 'id': '#', 'path': $("#rootPath").val().trim() };
                      } else { 
                          return { 'id': node.id }; 
                      }
                  },
                  cache: false, 
                  error: function(xhr, textStatus, errorThrown) {
                      let errorMsg = "jsTree AJAX Error: Failed to load tree data.";
                      if (xhr.responseJSON && xhr.responseJSON.error) {
                          errorMsg = `Server Error: ${xhr.responseJSON.error}`;
                      } else if (xhr.responseJSON && Array.isArray(xhr.responseJSON) && xhr.responseJSON.length > 0 && xhr.responseJSON[0].text && xhr.responseJSON[0].type === 'error') {
                          errorMsg = `Server: ${xhr.responseJSON[0].text}`;
                      } else if (xhr.statusText && xhr.statusText !== "error") {
                          errorMsg = `Server Error (${xhr.status}): ${xhr.statusText}`;
                      } else if (errorThrown) {
                          errorMsg = `Error: ${errorThrown}`;
                      }
                      $tree.html(`<p style="color:red; font-style:italic;">${errorMsg}</p>`);
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
              let instance = $.jstree.reference(node.id); 
              let current = node;
              while(current) { 
                  if (current.data && current.data.excluded_info) {
                      return false; 
                  }
                  if (current.parent === '#' || !current.parent) break; 
                  current = instance.get_node(current.parent);
              }
              return true; 
          }
      })
      .on('loaded.jstree', function (e, data) { 
          applyExclusionStyles(data.instance);
          const rootNodeId = data.instance.get_node('#').children[0];
          if (rootNodeId) { 
              data.instance.open_node(rootNodeId, null, 0); 
          } else {
              if (data.instance.get_json('#', { flat: true }).length === 0 || 
                  (data.instance.get_json('#', { flat: true }).length === 1 && data.instance.get_node(rootNodeId) && data.instance.get_node(rootNodeId).type === 'error')) {
                  // Tree is effectively empty or shows an error, no further action.
              } else {
                   $tree.html("<i>Tree loaded but no expandable root found. Check path or server logs.</i>");
              }
          }
      })
      .on('refresh.jstree', function(e, data) { 
          applyExclusionStyles($.jstree.reference(this));
      })
      .on('after_open.jstree', function(e, data){ 
          applyExclusionStyles(data.instance);
      })
      .on('load_error.jstree', (e, d) => { 
          const parentNodeId = d.data && d.data.id ? d.data.id : (d.element && d.element !== -1 ? d.element[0].id : 'unknown_node');
          const parentNode = $tree.jstree(true).get_node(parentNodeId);
          const parentNodeText = parentNode ? parentNode.text : parentNodeId;
          const errorDisplay = $(`<p style="color:orange; font-style:italic;">jsTree: Could not load children for "${parentNodeText}". Server may have encountered an issue or the path is inaccessible.</p>`);
           if(parentNode && parentNode.id !== '#') {
               $tree.jstree(true).get_node(parentNode, true).find('> .jstree-children').first().prepend(errorDisplay);
           } else {
               $tree.prepend(errorDisplay);
           }
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

  $btnLoadPath.on("click", () => buildTree());
  $rootPathInput.on("keypress", function(e){ if(e.which === 13) $btnLoadPath.click(); });

  // Check if the browse button exists and is not disabled (it might be if tkinter is not available)
  if ($btnBrowsePath.length && !$btnBrowsePath.is(':disabled')) {
      $btnBrowsePath.on("click", function() {
          const originalButtonText = $(this).text();
          $rootPathInput.prop('disabled', true);
          $(this).prop('disabled', true).text("Opening...");

          fetch("/api/browse-for-directory")
              .then(response => {
                  if (!response.ok) {
                      return response.json().then(errData => { // Try to parse JSON error from server
                          throw new Error(errData.error || `Server error: ${response.statusText} (Status: ${response.status})`);
                      }).catch(() => { // Fallback if response isn't JSON or errData.error isn't set
                          throw new Error(`Network error: ${response.statusText} (Status: ${response.status})`);
                      });
                  }
                  return response.json();
              })
              .then(data => {
                  if (data.selected_path) {
                      $rootPathInput.val(data.selected_path);
                      $btnLoadPath.click(); 
                  } else if (data.error) {
                      alert("Could not browse for directory: " + data.error);
                  }
              })
              .catch(error => {
                  console.error("Error fetching directory path:", error);
                  alert("Failed to open directory browser: " + error.message);
              })
              .finally(() => {
                   $rootPathInput.prop('disabled', false);
                   // Only re-enable if it was not disabled by the template initially
                   if ($btnBrowsePath.attr('disabled') !== 'disabled' || $btnBrowsePath.prop('disabled') === true) {
                      $btnBrowsePath.prop('disabled', false).text(originalButtonText);
                   }
              });
      });
  }


  $("#btnSavePreset").on("click", () => {
      const n = prompt("Save current selection as (user preset name):"); if (!n || n.trim()==="") return;
      const ti = $tree.jstree(true); if (!ti) {alert("Tree not initialized."); return;}
      const checkedNodesPaths = ti.get_checked(true).map(nodeId => ti.get_node(nodeId).id);

      if (checkedNodesPaths.length === 0) { alert("No items selected to save in preset."); return; }

      fetch("/api/presets/"+encodeURIComponent(n.trim()), {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({paths: checkedNodesPaths}) 
      })
      .then(r => { if(!r.ok) return r.json().then(e => {throw new Error(e.error || "Failed to save selection preset")}); return r.json();})
      .then(d => {
          if(d.saved){
              refreshPresetList();
              $("#presetList").val(d.id); 
              alert(`Preset '${d.name}' saved successfully.`);
          } else {
              alert("Error saving selection preset: "+(d.error||"Unknown error"));
          }
      }).catch(e => { alert("Error: "+e.message); console.error("Save selection preset error:", e); });
  });

  $("#btnLoadPreset").on("click", () => {
      const presetId = $("#presetList").val(); if(!presetId){alert("Please select a selection preset to load.");return;}
      fetch("/api/presets/"+encodeURIComponent(presetId))
      .then(r => { if(!r.ok) return r.json().then(e => {throw new Error(e.error || "Failed to load preset paths")}); return r.json();})
      .then(absolutePathsFromPreset => { 
          const treeInstance = $tree.jstree(true);
          if(!treeInstance){alert("Tree not initialized. Cannot load preset.");return;}
          treeInstance.uncheck_all(true); 
          
          treeInstance.check_node(absolutePathsFromPreset); 

          let loadedAndCheckedCount = 0;
          let firstVisibleNodeToReveal = null;

          absolutePathsFromPreset.forEach(pathStr => {
              const nodeObj = treeInstance.get_node(pathStr);
              if (nodeObj && treeInstance.is_checked(pathStr)) {
                  loadedAndCheckedCount++;
                  if (!firstVisibleNodeToReveal) firstVisibleNodeToReveal = nodeObj.id;

                  let parentPath = treeInstance.get_parent(nodeObj);
                  while(parentPath && parentPath !== "#") {
                      treeInstance.open_node(parentPath, null, 0); 
                      parentPath = treeInstance.get_parent(parentPath);
                  }
              }
          });
          applyExclusionStyles(treeInstance); 

          if(firstVisibleNodeToReveal){
              const nodeElement = treeInstance.get_node(firstVisibleNodeToReveal, true);
              if(nodeElement && nodeElement.length){
                   nodeElement[0].scrollIntoView({behavior: "smooth", block: "nearest"});
              }
          }

          if (absolutePathsFromPreset.length > 0 && loadedAndCheckedCount < absolutePathsFromPreset.length) {
              alert(`Note: ${absolutePathsFromPreset.length - loadedAndCheckedCount} out of ${absolutePathsFromPreset.length} item(s) from the preset were not selected. They might be excluded, not exist, or their parent directories haven't been expanded yet.`);
          } else if (loadedAndCheckedCount > 0) {
              // alert(`${loadedAndCheckedCount} item(s) from the preset loaded and selected.`);
          } else if (absolutePathsFromPreset.length > 0) {
               alert("No items from the preset could be selected. They might be excluded, not exist, or their parent directories haven't been expanded.");
          }

      }).catch(e => { alert("Error loading selection preset: "+e.message); console.error("Load selection preset error:", e); });
  });

  $("#btnDeletePreset").on("click", () => {
      const pId=$("#presetList").val(); if(!pId){alert("Please select a selection preset to delete.");return;}
      if(!pId.startsWith("user/")){alert("Only user selection presets can be deleted.");return;}
      const pName = pId.substring("user/".length); if(!confirm("Are you sure you want to delete the user selection preset '"+pName+"'?"))return;
      fetch("/api/presets/"+encodeURIComponent(pId),{method:"DELETE"})
      .then(r=>{if(!r.ok)return r.json().then(e=>{throw new Error(e.error||"Failed to delete selection preset")});return r.json();})
      .then(d=>{if(d.deleted){refreshPresetList(); alert(`Preset '${pName}' deleted.`);}else alert("Error deleting selection preset: "+(d.error||"Unknown error"));}).catch(e=>{alert("Error: "+e.message);console.error("Delete selection preset error:",e);});
  });

  $("#btnGenerate").on("click", () => {
      const treeInstance = $tree.jstree(true);
      if (!treeInstance) {
          alert("Tree not initialized.");
          $resultTextArea.val("Tree not available for generation.");
          $charCountDisplay.html("");
          return;
      }
      const checkedNodesPaths = treeInstance.get_checked(true).map(nodeId => treeInstance.get_node(nodeId).id);

      if (checkedNodesPaths.length === 0) {
          $resultTextArea.val("No items selected. Please select files or directories to include in the output.");
          $charCountDisplay.html("0 tokens");
          return;
      }
      $resultTextArea.val("Generating output, please wait... This may take a moment for large selections.");
      $charCountDisplay.html("<i>Calculating token count...</i>");

      fetch("/api/flatten", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths: checkedNodesPaths }) 
      })
      .then(response => {
          if (!response.ok) {
              return response.json()
                  .catch(() => response.text().then(text => { throw new Error("Server error: " + (text || response.statusText)); }))
                  .then(errData => {
                      if (errData && errData.error) throw new Error(errData.error);
                      throw new Error("Generate failed. Status: " + response.status);
                  });
          }
          return response.json();
      })
      .then(data => {
          $resultTextArea.val(data.text !== undefined ? data.text : "Error: No text returned from server.");
          let tokenInfoHtml = "";
          if (data.token_count !== undefined && data.token_count >= 0) {
              tokenInfoHtml = `<strong>${data.token_count}</strong> tokens`;
              if (data.model_percentages && data.model_percentages.length > 0) {
                  tokenInfoHtml += " || ";
                  const percentagesHtmlParts = data.model_percentages.map(m => {
                      if (m.name === "LLMs" && m.percentage === "N/A (Tokenization Error)") { 
                           return `${m.name}: <span style="color: red; font-weight: normal;">${m.percentage}</span>`;
                      }
                      let percVal = parseFloat(m.percentage); let displayPercStr; let color = "#333"; 
                      if (isNaN(percVal)) {
                          displayPercStr = "N/A"; color = "#777"; 
                      } else {
                          if (percVal === 0) { color = "#6c757d"; } 
                          else if (percVal < 50) { color = "green"; }
                          else if (percVal < 80) { color = "orange"; }
                          else if (percVal <= 100) { color = "red"; }
                          else { color = "#b30000"; } 

                          if (percVal === 0) { displayPercStr = "0"; }
                          else if (percVal < 0.1 && percVal > 0) { displayPercStr = percVal.toFixed(2); } 
                          else if (percVal < 10) { displayPercStr = percVal.toFixed(1); } 
                          else { displayPercStr = Math.round(percVal).toString(); } 

                          if (displayPercStr.endsWith(".0")) { displayPercStr = displayPercStr.slice(0, -2); } 
                      }
                      return `${m.name}: <span style="color: ${color}; font-weight: normal;">${displayPercStr}%</span>`;
                  }).join(" |  ");
                  tokenInfoHtml += percentagesHtmlParts;
              }
          } else if (data.token_count === -1) { 
               tokenInfoHtml = "<strong style='color:red;'>Tokenization Error</strong>";
               if (data.model_percentages && data.model_percentages.length > 0 && data.model_percentages[0].name === "LLMs") {
                   tokenInfoHtml += ` / ${data.model_percentages[0].name}: <span style="color: red; font-weight: normal;">${data.model_percentages[0].percentage}</span>`
               }
          }
          else {
              tokenInfoHtml = "Token info not available.";
          }
          $charCountDisplay.html(tokenInfoHtml);
      }).catch(error => {
          $resultTextArea.val("Error during generation: " + error.message);
          $charCountDisplay.html("<span style='color:red;'>Error calculating tokens.</span>");
          console.error("Flatten API call error:", error);
      });
  });

  $("#btnCopy").on("click", () => {
      const rt = $resultTextArea.val();
      if (!rt) {
          // alert("Nothing to copy."); // Optional: too noisy?
          return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(rt).then(() => {
              const originalText = $("#btnCopy").text();
              $("#btnCopy").text("Copied!");
              setTimeout(() => $("#btnCopy").text(originalText), 1500);
          }).catch(err => {
              console.error("Async copy failed: ", err);
              alert("Automatic copy failed. Please copy manually.");
          });
      } else { 
          $resultTextArea.select();
          try {
              document.execCommand('copy');
              const originalText = $("#btnCopy").text();
              $("#btnCopy").text("Copied! (fallback)");
              setTimeout(() => $("#btnCopy").text(originalText), 1500);
          } catch (err) {
              alert("Automatic copy failed (fallback). Please copy manually.");
          }
      }
  });

  buildTree(); 
  refreshPresetList(); 
  $charCountDisplay.html("Select items and click 'Generate TXT'."); 
});