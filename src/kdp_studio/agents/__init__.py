"""Production agents: specialised roles that work on a book as background jobs.

They are not the chat assistant (assistant/): each one answers a declared task
with a declared scope, and what it produces is a book record -- a candidate
version, a report -- through the same commands as everything else.
"""

from . import (architect, critic, designer, manifest, meta, researcher, reviser, translator, voice,  # noqa: F401 - register
               writer)                                                              # their job kinds
