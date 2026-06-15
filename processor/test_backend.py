from app.core.schemas import QuantityTakeoff
from app.budget.composer import compose_budget
import json

# Let's check what json.dumps does
print(json.dumps({"quantity": float('nan')}))
