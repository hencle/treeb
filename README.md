
# File-Picker & Flattener

A small Flask app that lets you:

1. Browse a directory as a collapsible, tri-state checkbox tree  
2. Select files/folders (with partial selections)  
3. “Generate TXT” to emit:
   - An ASCII “subset tree” of just your selections  
   - All selected files concatenated (with headings)  
4. Copy the result to your clipboard

---

## Prerequisites

- **Python 3.8+**  
- Git (optional)  
- A UNIX-like shell (macOS, Linux, WSL, etc.)

---

## Installation

1. **Clone** or unpack the project so you have:
```

treeb/
├── app.py
├── requirements.txt
├── templates/index.html
├── static/js/main.js
└── (venv)/

````
2. **(Re)create & activate** the virtualenv:
```bash
cd treeb
python3 -m venv venv
source venv/bin/activate
````

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

In `app.py`, set `ROOT_DIR` to the absolute path you want to expose:

```python
# app.py
ROOT_DIR = Path("/absolute/path/to/your/root").resolve()
```

Make sure your user has read-access (and write, if needed) to that folder.

---

## Running

With your virtualenv active:

```bash
python app.py
```

Then open in your browser:

```
http://localhost:5000
```

---

## Usage

1. **Browse** the tree and tick the files/folders you want.
2. Click **Generate TXT**.
3. A preview appears in the textarea.
4. Click **Copy to clipboard** to grab it.

### Example Output

```
└── treeb
    ├── templates
    │   └── index.html
    ├── static
    │   └── js
    │       └── main.js
    ├── requirements.txt
    └── app.py

# templates/index.html
<!doctype html>…

# static/js/main.js
$(function () { … })

# requirements.txt
Flask==3.1.0
…

# app.py
from flask import Flask, …
```

---
# treeb
