"""Centralized i18n module for TicketsTrini"""
from redbot.core.i18n import Translator, set_contextual_locales_from_guild

# Single Translator instance for all modules
# The path __file__ here points to ticketstrini/i18n.py
# So translations will be loaded from ticketstrini/locales/
_ = Translator("Tickets", __file__)

# Export set_contextual_locales_from_guild for use in views and non-command code
# This MUST be called before translating strings in listeners, tasks, and views
__all__ = ["_", "set_contextual_locales_from_guild"]
