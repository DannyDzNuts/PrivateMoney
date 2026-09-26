from datetime import date
from .models import Account, Transaction, Budget, RecurringCharge

ACCOUNTS = [
    Account("local-checking", "Everyday Checking", "checking", "Local", 3842.18, 3680.12, "0421"),
    Account("local-savings", "Savings", "savings", "Local", 8650.00, 8650.00, "1187"),
    Account("local-credit", "Credit Card", "credit", "Local", -812.18, None, "5520"),
]

TRANSACTIONS = [
    Transaction(date(2026, 9, 25), "Kroger", "Groceries", "Everyday Checking", -86.42),
    Transaction(date(2026, 9, 24), "Walmart", "Household", "Everyday Checking", -47.18),
    Transaction(date(2026, 9, 23), "Payroll", "Income", "Everyday Checking", 1480.00),
    Transaction(date(2026, 9, 22), "Shell", "Gas", "Everyday Checking", -41.55),
    Transaction(date(2026, 9, 21), "Spotify", "Subscriptions", "Credit Card", -11.99),
    Transaction(date(2026, 9, 20), "Local Restaurant", "Dining", "Credit Card", -32.64),
    Transaction(date(2026, 9, 18), "Electric Utility", "Utilities", "Everyday Checking", -129.12),
    Transaction(date(2026, 9, 17), "Auto Insurance", "Insurance", "Everyday Checking", -142.80),
]

BUDGETS = [
    Budget("Groceries", 328.44, 450.00),
    Budget("Dining", 126.20, 180.00),
    Budget("Gas", 117.85, 160.00),
    Budget("Fun", 89.00, 150.00),
]

RECURRING = [
    RecurringCharge("Spotify", 11.99, "Monthly", date(2026, 10, 21), "Subscriptions"),
    RecurringCharge("Auto Insurance", 142.80, "Monthly", date(2026, 10, 17), "Insurance"),
    RecurringCharge("Electric Utility", 129.12, "Monthly", date(2026, 10, 18), "Utilities"),
]

NET_WORTH = [
    ("Apr", 8420), ("May", 9015), ("Jun", 9650), ("Jul", 10280), ("Aug", 10940), ("Sep", 11680)
]

SPENDING = [
    ("Housing", 740), ("Groceries", 328), ("Transport", 260), ("Bills", 272), ("Dining", 126), ("Other", 164)
]

CASHFLOW = [
    ("Apr", 2232, 1810), ("May", 2232, 1760), ("Jun", 2232, 1685), ("Jul", 2232, 1710), ("Aug", 2232, 1745), ("Sep", 2232, 1890)
]
