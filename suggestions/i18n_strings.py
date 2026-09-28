"""Generado automaticamente. No se importa: solo sirve para que ``redgettext``
extraiga al catalogo los textos que no detecta por si solo (constantes marcadas
con N_(), docstrings de comandos hibridos y textos dentro de decoradores).
"""
from redbot.core.i18n import Translator

_ = Translator("SimpleSuggestions", __file__)


def _strings() -> None:
    _("\n        Submit a new suggestion.\n        \n        You can type the suggestion directly or use the interactive modal.\n        \n        **Examples:**\n        - `[p]suggest Add more emojis to the server`\n        - `[p]suggest` (opens a modal to write)\n        ")
    _("\n        Edit your own suggestion (only if pending).\n        \n        **Examples:**\n        - `[p]editsuggest #123 New text for my suggestion`\n        - `[p]editsuggest 1234567890 New text`\n        ")
    _("View your own suggestions.")
    _("\n        Approve a suggestion.\n        \n        **Examples:**\n        - `[p]approve #123`\n        - `[p]approve #123 Great idea, we'll implement it`\n        ")
    _("\n        Deny a suggestion.\n        \n        **Examples:**\n        - `[p]deny #123`\n        - `[p]deny #123 Not feasible at this time`\n        ")
    _("\n        Change the status of a suggestion.\n        \n        **Available statuses:**\n        pending, in_review, planned, in_progress, approved, implemented, denied, duplicate, wont_do\n        ")
    _("List server suggestions.")
    _("View detailed information about a suggestion.")
    _("View the change history of a suggestion.")
    _("Pending")
    _("In Review")
    _("Planned")
    _("In Progress")
    _("Approved")
    _("Implemented")
    _("Denied")
    _("Duplicate")
    _("Won't Do")
