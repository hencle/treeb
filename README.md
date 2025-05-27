Okay, I'll update the README with the new information, keeping it concise.

-----

## README.md (Updated)

# treeb

Flatten repos by selection and feed it into llms

`treeb` provides a web UI to visually select files and directories, then generates a combined text output including an ASCII tree and file contents. It's designed for preparing context for Large Language Models.

## Key Features

  * **Visual File/Directory Selection**: Interactive tree view to pick your context.
      * **Lazy Loading**: For improved performance with large repositories and on constrained hardware (like a Raspberry Pi), directory contents are loaded on-demand as you expand them in the tree. File contents are only read when generating the final output.
  * **Combined Text Output**: Generates an ASCII tree of the selected structure plus the content of selected files.
  * **LLM Context Awareness**:
      * Displays **token count** of the output (using `tiktoken`).
      * Shows context window usage **percentages for major LLMs**, color-coded for quick insight.
  * **Selection Presets**: Save and load frequently used file/directory selections. Starts with an empty "default" preset.
  * **Automatic Exclusions**: Common ignored items (like `.git`, `node_modules`, `__pycache__`) are visually marked as excluded (greyed out, non-selectable) and omitted from the generated output.
  * **(Optional) System Directory Browser**: A "Browse..." button allows using the native OS file explorer to select the root path for the tree. This requires `tkinter`.

## Installation & Setup

Python 3.7+ is required.

### Dependencies

The "Browse..." button, which uses a system dialog to select directories, relies on Python's `tkinter` module.

`tkinter` is often included in standard Python distributions but might be omitted in minimal installations or some virtual environments. If the "Browse..." button is disabled or non-functional, `tkinter` may need to be installed manually:

* **Linux**:
    * Debian/Ubuntu: `sudo apt-get update && sudo apt-get install python3-tk`
    * Fedora: `sudo dnf install python3-tkinter`
    * *(For other distributions, install the appropriate `python3-tk` or `python3-tkinter` package.)*
* **Windows**:
    * Usually included. If missing, ensure "tcl/tk and IDLE" was selected during Python's installation (from python.org), or modify/reinstall Python with this option.
* **macOS**:
    * Typically included with Python from Homebrew or python.org.

The application will still function without `tkinter`, but the directory Browse button will be unavailable. The startup scripts will provide a warning if `tkinter` is missing.

## Run (Unix)

```bash
chmod +x run.sh
./run.sh
```

## Run (Windows)

```bat
run.bat
```

After running, open `http://127.0.0.1:5000` in your browser.