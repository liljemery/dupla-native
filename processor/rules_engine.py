from typing import Any

class RulesEngine:
    def __init__(self, *args, **kwargs):
        pass
        
    def apply(self, takeoffs: list[Any]) -> list[Any]:
        return takeoffs

def default_rules_engine(*args, **kwargs) -> RulesEngine:
    return RulesEngine()
