# savings/ml_models.py
import numpy as np
from datetime import date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from sklearn.linear_model import LinearRegression
from savings.models import SavingsGoal
from savings.utils import calculate_monthly_surplus

def simulate_future_surplus(user, months=12):
    """
    Generate simulated surplus data for low-data scenarios.
    Takes previous month surpluses and applies +-10% random variance.
    Returns a numpy array of future monthly surpluses.
    """
    today = date.today()
    # Collect last 12 months of surplus
    last_12_surplus = []
    for i in range(12, 0, -1):
        month = today - relativedelta(months=i)
        surplus = float(calculate_monthly_surplus(user, month.year, month.month))
        last_12_surplus.append(surplus)
    
    # Calculate average surplus
    avg_surplus = np.mean(last_12_surplus) if last_12_surplus else 0.0

    # Generate 12 months of simulated surplus with +-10% variance
    simulated = []
    for _ in range(months):
        variance = np.random.uniform(-0.1, 0.1)  # +-10%
        simulated.append(max(avg_surplus * (1 + variance), 0))
    
    return np.array(simulated)


def predict_goal_probability(user, goal: SavingsGoal, simulations=1000):
    """
    Predict probability (0-100%) of reaching a goal using:
    - Linear regression on cumulative surplus for current probability
    - Monte Carlo simulations for confidence interval only
    Suggested deadline is calculated independently from probability.
    """
    today = date.today()
    
    if not goal.deadline:
        return {"probability": 100.0, "suggested_deadline": "--"}
    
    # Remaining amount to save
    remaining_amount = float(goal.remaining_amount())
    if remaining_amount <= 0:
        return {"probability": 100.0, "suggested_deadline": goal.deadline}
    
    # Collect last 12 months of surplus
    last_12_surplus = []
    for i in range(12, 0, -1):
        month = today - relativedelta(months=i)
        surplus = float(calculate_monthly_surplus(user, month.year, month.month))
        last_12_surplus.append(surplus)
    
    last_12_surplus = np.array(last_12_surplus)
    avg_surplus = np.mean(last_12_surplus)
    
    # Linear regression on cumulative surplus
    X = np.arange(len(last_12_surplus)).reshape(-1, 1)
    y = last_12_surplus.cumsum()
    model = LinearRegression()
    model.fit(X, y)
    
    # Predict cumulative surplus at original deadline
    months_left = max((goal.deadline.year - today.year) * 12 + goal.deadline.month - today.month, 1)
    predicted_cumulative = model.predict(np.array([[len(last_12_surplus) + months_left - 1]]))[0]
    predicted_total = float(goal.current_amount) + predicted_cumulative
    
    # Ensure probability always shows
    if predicted_total >= goal.target_amount:
        base_probability = 100.0
    else:
        base_probability = min(max(predicted_total / float(goal.target_amount), 0), 1) * 100
    
    # Suggested deadline (decoupled from probability)
    slope = model.coef_[0]
    if slope <= 0:
        slope = avg_surplus
    months_needed = remaining_amount / slope if slope > 0 else 120  # cap at 10 years
    suggested_deadline = today + relativedelta(months=int(np.ceil(months_needed)))
    
    # Monte Carlo for confidence interval only
    std_surplus = np.std(last_12_surplus) if len(last_12_surplus) > 1 else 0.1 * avg_surplus
    final_totals = []
    for _ in range(simulations):
        simulated_future = np.random.normal(loc=avg_surplus, scale=std_surplus, size=int(months_left))
        simulated_future = np.maximum(simulated_future, 0)
        final_total = float(goal.current_amount) + simulated_future.sum()
        final_totals.append(final_total)
    final_totals = np.array(final_totals)
    conf_interval = (np.percentile(final_totals, 5), np.percentile(final_totals, 95))
    
    return {
        "probability": round(base_probability, 2),
        "suggested_deadline": suggested_deadline,
        "confidence_interval": conf_interval
    }