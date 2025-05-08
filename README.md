# treeb/README.md

# File-Picker & Flattener

A small Flask app that lets you:

1. Browse a directory as a collapsible, tri-state checkbox tree
2. Select files/folders (with partial selections)
3. “Generate TXT” to emit:
   - An ASCII “subset tree” of just your selections
   - All selected files concatenated (with headings)
4. Copy the result to your clipboard
5. Change the root directory being browsed at runtime.
6. Save and load sets of selected files as named "presets".

---

## Prerequisites

- **Python 3.8+**
- Git (optional)
- A UNIX-like shell (macOS, Linux, WSL, etc.)

---

## Installation

1. **Clone** or unpack the project so you have:
treeb/
├── app.py
├── requirements.txt
├── templates/index.html
├── static/js/main.js
└── (venv)/

2. **(Re)create & activate** the virtualenv:

---

cd treeb
python3 -m venv venv
source venv/bin/activate
Install dependencies:

---

pip install -r requirements.txt
Configuration
In app.py, set the initial ROOT_DIR to the absolute path you want to expose when the app first loads:

Python

# app.py
ROOT_DIR = Path("/absolute/path/to/your/default/root").resolve()
Make sure your user running the Flask app has read-access to that folder and any other folders you intend to browse.

Running
With your virtualenv active:

Bash

python app.py
Then open in your browser:

http://localhost:5000
Usage
Browse the tree. By default, it loads the ROOT_DIR from app.py.
Change Root Path: To browse a different directory, type its absolute path into the input field at the top and click "Load Path" or press Enter.
Select Files/Folders: Tick the checkboxes for the items you want.
Click Generate TXT.
A preview appears in the textarea, showing an ASCII tree of your selection followed by the content of the selected files.
Click Copy to clipboard to grab it.
Presets
Save the current selection of checked files:
Click 💾 Save as…
Enter a name for your preset and click OK.
Load an existing preset:
Choose a preset name from the dropdown list.
Click Load. The files stored in the preset will be checked in the current tree (if they exist).
Delete a preset:
Choose a preset name from the dropdown list.
Click 🗑️ (Delete).
Confirm the deletion.
Preset JSON files live in ~/.filepicker_presets/ (i.e., in a hidden folder named .filepicker_presets in your user's home directory). They are simple JSON arrays of absolute file paths.