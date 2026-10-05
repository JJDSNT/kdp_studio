"""Production agents: specialised roles that work on a book as background jobs.

They are not the chat assistant (assistant/): each one answers a declared task
with a declared scope, and what it produces is a book record -- a candidate
version, a report -- through the same commands as everything else.
"""

from . import voice  # noqa: F401 - registers its job kind
