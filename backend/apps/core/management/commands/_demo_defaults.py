"""Valores configuraveis usados pelos comandos de dados demonstrativos."""

from decouple import config


DEFAULT_ACCOUNT_SLUG = config("DEFAULT_ACCOUNT_SLUG", default="starchef-demo")
DEFAULT_ACCOUNT_NAME = config("DEFAULT_ACCOUNT_NAME", default="StarChef Demo")
DEFAULT_RESTAURANT_NAME = config("DEFAULT_RESTAURANT_NAME", default="Burger Palace")
DEFAULT_BRANCH_NAME = config("DEFAULT_BRANCH_NAME", default="Copacabana")
DEFAULT_USERNAME = config("DEFAULT_USERNAME", default="admin")
DEFAULT_EMAIL = config("DEFAULT_EMAIL", default="admin@starchef.test")
DEFAULT_PASSWORD = config("DEFAULT_PASSWORD", default="admin12345")
