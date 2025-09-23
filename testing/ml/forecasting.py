import pandas as pd
from django.utils.timezone import now
from finance.models import Expense
from prophet import Prophet
from sklearn.linear_model import LinearRegression
import numpy as np

def get_user_expense_forecast(user, forecast_date=None):
    """
    Hybrid forecast:
    - <100 rows & <6 months: rolling average
    - >=100 rows & <6 months: linear regression
    - >=6 months: Prophet
    Returns dict with this month expected, spent so far, next month expected
    """
    today = forecast_date or now().date()
    first_day_of_month = pd.Timestamp(today.replace(day=1))

    # ---- 1. Fetch user expenses ----
    expenses = Expense.objects.filter(user=user).order_by("date")
    if not expenses.exists():
        return {"this_month_expected": 0.0, "spent_so_far": 0.0, "next_month_expected": 0.0}

    df = pd.DataFrame(expenses.values("date", "amount"))
    df = df.rename(columns={"date": "ds", "amount": "y"})
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)
    df = df.sort_values("ds")

    # ---- 2. Spent so far this month ----
    spent_this_month_df = df[(df["ds"].dt.year == today.year) & (df["ds"].dt.month == today.month)]
    spent_so_far = spent_this_month_df["y"].sum() if not spent_this_month_df.empty else 0.0

    # ---- 3. Dataset preparation ----
    df_past = df[df["ds"] < first_day_of_month].copy()
    df_full = df.copy()

    num_rows = len(df_full)
    months_of_data = (today.year - df["ds"].min().year) * 12 + (today.month - df["ds"].min().month)

    # ---- 4. Forecast helper functions ----
    def rolling_forecast(df_input, days_in_month):
        df_daily = df_input.set_index("ds").resample("D").sum().reset_index()
        df_daily["y"] = df_daily["y"].fillna(0)
        median = df_daily["y"].median()
        df_daily["y"] = df_daily["y"].clip(upper=median*5)
        rolling_avg = df_daily["y"].rolling(window=7, min_periods=1).mean()
        return round(rolling_avg.mean() * days_in_month, 2)

    def linear_regression_forecast(df_input, days_in_month):
        df_daily = df_input.set_index("ds").resample("D").sum().reset_index()
        df_daily["y"] = df_daily["y"].fillna(0)
        median = df_daily["y"].median()
        df_daily["y"] = df_daily["y"].clip(upper=median*5)
        df_daily["day_index"] = np.arange(len(df_daily))
        X = df_daily["day_index"].values.reshape(-1, 1)
        y = df_daily["y"].values
        model = LinearRegression()
        model.fit(X, y)
        future_days = np.arange(len(df_daily), len(df_daily) + days_in_month).reshape(-1, 1)
        y_pred = model.predict(future_days)
        return round(max(y_pred.sum(), 0.0), 2)

    def prophet_forecast(df_input, days_in_month):
        df_prophet = df_input.rename(columns={"ds": "ds", "y": "y"})
        model = Prophet(daily_seasonality=True)
        model.fit(df_prophet)
        future = model.make_future_dataframe(periods=days_in_month)
        forecast = model.predict(future)
        return round(forecast['yhat'][-days_in_month:].sum(), 2)

    # ---- 5. Choose forecast model based on dataset size ----
    def choose_forecast(df_input, days_in_month):
        if num_rows < 100 and months_of_data < 6:
            return rolling_forecast(df_input, days_in_month)
        elif num_rows >= 100 and months_of_data < 6:
            return linear_regression_forecast(df_input, days_in_month)
        else:
            return prophet_forecast(df_input, days_in_month)

    # ---- 6. Current month forecast ----
    days_in_this_month = pd.Period(f"{today.year}-{today.month:02d}").days_in_month
    this_month_expected = choose_forecast(df_past, days_in_this_month)

    # ---- 7. Next month forecast ----
    next_month = (today.month % 12) + 1
    next_year = today.year + (1 if next_month == 1 else 0)
    days_in_next_month = pd.Period(f"{next_year}-{next_month:02d}").days_in_month
    next_month_expected = choose_forecast(df_full, days_in_next_month)

    return {
        "this_month_expected": this_month_expected,
        "spent_so_far": round(spent_so_far, 2),
        "next_month_expected": next_month_expected,
    }
