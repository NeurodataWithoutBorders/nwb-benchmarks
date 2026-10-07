import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

project = "nwb_benchmarks"
copyright = "2024, Neurodata Without Borders"
author = "Cody Baker, Urjoshi Sinha, Ryan Ly, Ben Dichter, and Oliver Ruebel."

extensions = [
    "sphinx_copybutton",  # For copying code snippets
    "sphinx.ext.intersphinx",  # Allows links to other sphinx project documentation sites
    "sphinx_search.extension",  # Allows for auto search function the documentation
    "sphinx.ext.viewcode",  # Shows source code in the documentation
    "sphinx.ext.extlinks",  # Allows to use shorter external links defined in the extlinks variable.
    "sphinx_tabs.tabs",  # Groups platform-specific code blocks into synchronized tabs
]

templates_path = ["_templates"]
master_doc = "index"
exclude_patterns = ["build", "_build", "Thumbs.db", ".DS_Store"]
html_theme = "pydata_sphinx_theme"
html_logo = "assets/logo_nwb_benchmarks.png"
# html_static_path = ["_static"]

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
# html_favicon = "favicon.ico"

html_context = {
    # "github_url": "https://github.com", # or your GitHub Enterprise site
    "github_user": "neurodatawithoutborders",
    "github_repo": "nwb_benchmarks",
    "github_version": "main",
    "doc_path": "docs",
}

html_theme_options = {
    "use_edit_page_button": True,
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/neurodatawithoutborders/nwb_benchmarks",
            "icon": "fa-brands fa-github",
            "type": "fontawesome",
        },
    ],
}

linkcheck_anchors = False

# --------------------------------------------------
# Extension configuration
# --------------------------------------------------


def _correct_signatures(app, what, name, obj, options, signature, return_annotation):
    if what == "class":
        signature = str(inspect.signature(obj.__init__)).replace("self, ", "")
    return (signature, return_annotation)


# Toggleprompt
toggleprompt_offset_right = 45  # This controls the position of the prompt (>>>) for the conversion gallery
toggleprompt_default_hidden = "true"

# Intersphinx
intersphinx_mapping = {
    "hdmf": ("https://hdmf.readthedocs.io/en/stable/", None),
    "pynwb": ("https://pynwb.readthedocs.io/en/stable/", None),
}

# To shorten external links
extlinks = {}
