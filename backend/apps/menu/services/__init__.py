"""Serviços do cardápio.

Este pacote nasceu como o módulo `services.py`, e `from apps.menu.services
import recalculate_recipe_costs` (e `update_ingredient_average_cost`) já estava
espalhado por `apps.menu` e `apps.stock`. As duas funções são reexportadas aqui
para que o nome público continue o mesmo: a implementação mudou de casa para
`recipes.py` quando o pacote precisou abrigar também os menus, e trocar o
import em cada ponto de uso não traria nada além de ruído no diff.
"""
from apps.menu.services.recipes import recalculate_recipe_costs, update_ingredient_average_cost

__all__ = ["recalculate_recipe_costs", "update_ingredient_average_cost"]
