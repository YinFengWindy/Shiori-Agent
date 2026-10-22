"""The kernel budget counts code lines only."""

from scripts.kernel_loc_budget import code_lines

SOURCE = '''"""Module docstring
spanning two lines."""

# A comment line.
import os  # A trailing comment keeps the line.


class Kernel:
    """Class docstring."""

    def start(self) -> str:
        """Method docstring."""
        return """a multi-line
string value"""
'''


def test_comments_docstrings_and_blank_lines_are_not_counted() -> None:
    # import, class, def, and the two lines of the returned string literal.
    assert code_lines(SOURCE) == 5
