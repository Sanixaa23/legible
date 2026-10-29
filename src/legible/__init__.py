"""legible -- restructures lesson material, and proves it kept the meaning.

The default path never changes a word. See `transform.py` for why that is a
guarantee rather than a policy, and `facts.py` for what is checked when the
opt-in path does change one.
"""
__version__ = "0.1.0"

__all__ = ["evidence", "facts", "readability", "transform", "restructure"]
