"""Count the queries a code path issues, because nothing else will tell you.

An N+1 does not raise, does not log, does not show up in a slow query report, and does not
move a p50 on the machine it was written on. Each query is fast. There are simply a hundred
of them, and the cost is the hundred round trips, which cost nothing locally and a great
deal across a network.
"""

from n_plus_one_budget.config import ConfigError, LoadConfig
from n_plus_one_budget.counting import BudgetExceeded, QueryCounter, connect

__all__ = ["LoadConfig", "ConfigError", "QueryCounter", "BudgetExceeded", "connect"]
__version__ = "0.1.0"
