# utils.py
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from dateutil import parser

def get_next_due_date(current_date, frequency):
    if frequency == "daily":
        return current_date + timedelta(days=1)
    elif frequency == "weekly":
        return current_date + timedelta(weeks=1)
    elif frequency == "monthly":
        return current_date + relativedelta(months=1)
    elif frequency == "quarterly":
        return current_date + relativedelta(months=3)
    elif frequency == "biannually":
        return current_date + relativedelta(months=6)
    elif frequency == "yearly":
        return current_date + relativedelta(years=1)
    return current_date

HEADER_MAPPING = {
    "date": ["date", "Date", "transaction_date", "income_date", "expense_date","DATE","day","day_of_transaction",],
    "source": ["source", "income_source", "from", "source_name","source_title","source_label","name","SOURCE"],
    "name": ["name", "expense_name", "item","source_name","source_title","source_label","source","NAME"],
    "amount": ["amount", "value", "price", "cost","amount_paid","amount_received","money","AMOUNT"],
    "category": ["category", "type", "group","category_name","category_title","category_label","Category","CATEGORY"]
}


def normalize_headers(fieldnames):
    normalized = {}
    for key, variations in HEADER_MAPPING.items():
        for variation in variations:
            if variation in fieldnames:
                normalized[key] = variation
                break
    return normalized

def normalize_date(date_str):
    if not date_str:
        return None
    try:
        parsed_date = parser.parse(date_str, dayfirst=False)  
        return parsed_date.date().isoformat()  # YYYY-MM-DD
    except Exception:
        try:
            parsed_date = parser.parse(date_str, dayfirst=True)  
            return parsed_date.date().isoformat()
        except Exception:
            return None  # skip if completely invalid
        
def clean_value(value, default=None, cast_type=str):

    if value is None:
        return default
    value = str(value).strip()
    if value == "":
        return default
    try:
        return cast_type(value)
    except Exception:
        return default

INCOME_CATEGORY_MAPPING = {
    "Salary": [
        "salary", "salaries", "wages", "paycheck", "monthly pay", "stipend", "SALARY", "PAYCHECK", "Monthly Payment"
    ],
    "Business": [
        "business", "self-employed", "trade", "sales", "company income", "BUSINESS"
    ],
    "Freelance": [
        "freelance", "freelancer", "contract work", "gig", "side hustle", "consulting", "FREELANCE", "CONTRACT", "Side Hustle"
    ],
    "Rental Income": [
        "rental income", "rent", "lease", "property income", "RENTAL", "RENT"
    ],
    "Dividends": [
        "dividends", "shares", "stocks", "equity return", "DIVIDENDS", "stock income", "Investment"
    ],
    "Interest Income": [
        "interest income", "bank interest", "deposit interest", "fd interest", "rd interest", "INTEREST"
    ],
    "Gifts & Donations": [
        "gifts", "gift", "donation", "donations", "present", "charity received", "GIFTS"
    ],
    "Refunds": [
        "refunds", "rebate", "cashback", "reimbursement", "REFUND"
    ],
    "Retirement Income": [
        "retirement income", "pension", "provident fund", "pf", "annuity", "RETIREMENT"
    ],
    "Bonus & Incentives": [
        "bonus", "incentive", "performance pay", "commission", "perks", "BONUS"
    ],
    "Other Income": [
        "other income", "miscellaneous", "misc", "unknown", "extra income", "OTHER"
    ]
}
def normalize_income_category(raw_category):
    raw_category = str(raw_category).strip().lower()
    for standard, synonyms in INCOME_CATEGORY_MAPPING.items():
        if raw_category in [s.lower() for s in synonyms]:
            return standard
    return "Other Income"  # fallback

EXPENSE_CATEGORY_MAPPING = {
    "Housing & Utilities": [
        "housing", "rent", "mortgage", "utilities", "electricity", "water bill", "family", "childcare", "kids", "baby", "gifts", "parents", "friends", 
        "celebration", "festivals", "FAMILY", "gas bill", "internet", "wifi", "maintenance", "household", "bills", "HOUSING"
    ],
    "Transportation": [
        "transportation", "transport", "commute", "bus", "train", "metro", "cab", "uber", "bike",
        "taxi", "car", "fuel", "petrol", "diesel", "parking", "vehicle", "TRAVEL LOCAL"
    ],
    "Food & Dining": [
        "food", "foods", "dining", "restaurant", "meal", "meals", "groceries", 
        "supermarket", "snacks", "coffee", "lunch", "dinner", "breakfast", "takeaway", "FOOD"
    ],
    "Personal & Shopping": [
        "personal", "shopping", "clothes", "apparel", "fashion", "cosmetics", 
        "beauty", "grooming", "electronics", "gadgets", "online shopping", "mall", "SHOPPING"
    ],
    "Health & Fitness": [
        "health", "fitness", "gym", "workout", "exercise", "doctor", "hospital", 
        "medicine", "pharmacy", "drugs", "clinic", "checkup", "yoga", "HEALTH"
    ],
    "Entertainment & Leisure": [
        "entertainment", "movies", "cinema", "concert", "theatre", "music", 
        "games", "gaming", "subscriptions", "netflix", "spotify", "party", "leisure", "ENTERTAINMENT"
    ],
    "Education": [
        "education", "school", "college", "tuition", "books", "courses", 
        "online courses", "training", "fees", "exam", "EDUCATION"
    ],
    "Financial": [
        "financial", "insurance", "loan", "emi", "investment", "bank charges", "stock-market", "share-market",
        "interest paid", "credit card", "tax", "fees", "finance", "FINANCIAL"
    ],
    "Travel & Vacation": [
        "travel", "vacation", "trip", "holiday", "tourism", "flight", 
        "hotel", "resort", "tickets", "visa", "tour", "TRAVEL"
    ],
    "Miscellaneous": [
        "miscellaneous", "misc", "other", "unknown", "extra", "donation", "others", "uncategorized", "MISC"
    ]
}

def normalize_expense_category(raw_category):
    raw_category = str(raw_category).strip().lower()
    for standard, synonyms in EXPENSE_CATEGORY_MAPPING.items():
        if raw_category in [s.lower() for s in synonyms]:
            return standard
    return "Miscellaneous"  # fallback


