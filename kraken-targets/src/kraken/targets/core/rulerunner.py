import importlib
from typing import Any, Callable, Iterable

from adjudicator import Params, RulesEngine

from kraken.targets.core.goal import Goal
from kraken.targets.core.subtypes import SubtypesRegistry


class RuleRunner:
    def __init__(self, modules: Iterable[str] = ()) -> None:
        self.subtypes = SubtypesRegistry()
        self.engine = RulesEngine([], [self.subtypes])
        self.loaded_modules: set[str] = set()
        self.load(*modules)

    def load(self, *modules: str) -> None:
        """
        Populate the RuleRunner with the rules and subtypes from the specified modules by calling
        their `register()` functions. The functions should receive the RuleRunner as a positional
        argument and register their rules and subtypes with it.
        """

        for module in modules:
            if module in self.loaded_modules:
                continue
            self.loaded_modules.add(module)
            mod = importlib.import_module(module)
            register: Callable[[RuleRunner], None] = getattr(mod, "register")
            register(self)

    def run(self, goal: type[Goal], params: Params.InitType = ()) -> Goal:
        with self.engine.as_current():
            subsystem = goal.subsystem_cls()
            return self.engine.get(goal, Params(params) | Params([subsystem]))

    def get(self, type_: type[Any], params: Params.InitType) -> Any:
        with self.engine.as_current():
            return self.engine.get(type_, Params(params))
