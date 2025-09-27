import pandas as pd
from django.utils.timezone import now
from finance.models import Expense
from prophet import Prophet
from sklearn.linear_model import LinearRegression
import numpy as np

def get_user_expense_forecast(user, forecast_date=None):
    """
    Hybrid expense forecast:
    - <100 rows & <6 months: rolling average
    - >=100 rows & <6 months: linear regression
    - >=6 months: Prophet
    Bulk past month handling: <30 rows/month → distribute over 30 days
    Returns dict with:
        this_month_expected, spent_so_far, next_month_expected
    Uses '--' when prediction is unavailable
    """
    today = forecast_date or now().date()
    first_day_of_month = pd.Timestamp(today.replace(day=1))

    # ---- 1. Fetch user expenses ----
    expenses = Expense.objects.filter(user=user).order_by("date")
    if not expenses.exists():
        return {"this_month_expected": "--", "spent_so_far": "--", "next_month_expected": "--"}

    df = pd.DataFrame(expenses.values("date", "amount"))
    df = df.rename(columns={"date": "ds", "amount": "y"})
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)

    # ---- 2. Bulk-month normalization (<30 rows/month), only for past months ----
    df["YearMonth"] = df["ds"].dt.to_period("M")
    normalized_amounts = []

    for ym, group in df.groupby("YearMonth"):
        if group.empty:
            continue  # skip empty groups

        month_num = group["ds"].dt.month.iloc[0]  # safe access
        # Only normalize past months with <30 rows
        if month_num < today.month and len(group) < 30:
            avg_daily = group["y"].sum() / 30.0
            normalized_amounts.extend([avg_daily] * len(group))
        else:
            normalized_amounts.extend(group["y"].tolist())

    # Ensure lengths match
    if len(normalized_amounts) != len(df):
        raise ValueError("Length mismatch after normalization")

    df["y_normalized"] = normalized_amounts

    # ---- 3. Spent so far this month ----
    spent_this_month_df = df[(df["ds"].dt.year == today.year) & (df["ds"].dt.month == today.month)]
    spent_so_far_display = round(spent_this_month_df["y"].sum(), 2) if not spent_this_month_df.empty else "--"

    # ---- 4. Dataset preparation ----
    df_past = df[df["ds"] < first_day_of_month].copy()  # past months only
    df_for_next_month = df[df["ds"] < first_day_of_month].copy()  # exclude partial current month
    df_full = df.sort_values("ds").copy()  # all data for optional extended forecast

    num_rows = len(df_full)
    months_of_data = (today.year - df["ds"].min().year) * 12 + (today.month - df["ds"].min().month)

    # ---- 5. Forecast helper functions ----
    def rolling_forecast(df_input, days_in_month):
        if df_input.empty or df_input["y_normalized"].sum() == 0:
            return None
        df_daily = df_input.set_index("ds").resample("D")["y_normalized"].sum().reset_index()
        median = df_daily["y_normalized"].median()
        df_daily["y_normalized"] = df_daily["y_normalized"].clip(upper=median*5)
        rolling_avg = df_daily["y_normalized"].rolling(window=7, min_periods=1).mean()
        return round(rolling_avg.mean() * days_in_month, 2)

    def linear_regression_forecast(df_input, days_in_month):
        if df_input.empty or df_input["y_normalized"].sum() == 0:
            return None
        df_daily = df_input.set_index("ds").resample("D")["y_normalized"].sum().reset_index()
        median = df_daily["y_normalized"].median()
        df_daily["y_normalized"] = df_daily["y_normalized"].clip(upper=median*5)
        df_daily["day_index"] = np.arange(len(df_daily))
        X = df_daily["day_index"].values.reshape(-1, 1)
        y = df_daily["y_normalized"].values
        model = LinearRegression()
        model.fit(X, y)
        future_days = np.arange(len(df_daily), len(df_daily) + days_in_month).reshape(-1, 1)
        y_pred = model.predict(future_days)
        return round(max(y_pred.sum(), 0.0), 2)

    def prophet_forecast(df_input, days_in_month):
        if df_input.empty or df_input["y_normalized"].sum() == 0:
            return None
        df_prophet = df_input.rename(columns={"ds": "ds", "y_normalized": "y"})
        model = Prophet(daily_seasonality=True)
        model.fit(df_prophet)
        future = model.make_future_dataframe(periods=days_in_month)
        forecast = model.predict(future)
        return round(forecast['yhat'][-days_in_month:].sum(), 2)

    # ---- 6. Choose forecast model ----
    def choose_forecast(df_input, days_in_month):
        if df_input.empty or df_input["y_normalized"].sum() == 0:
            return None
        if num_rows < 100 and months_of_data < 6:
            return rolling_forecast(df_input, days_in_month)
        elif num_rows >= 100 and months_of_data < 6:
            return linear_regression_forecast(df_input, days_in_month)
        else:
            return prophet_forecast(df_input, days_in_month)

    # ---- 7. Current month forecast ----
    days_in_this_month = pd.Period(f"{today.year}-{today.month:02d}").days_in_month
    this_month_forecast = choose_forecast(df_past, days_in_this_month)
    this_month_display = this_month_forecast if this_month_forecast is not None else "--"

    # ---- 8. Next month forecast (exclude partial current month) ----
    next_month = (today.month % 12) + 1
    next_year = today.year + (1 if next_month == 1 else 0)
    days_in_next_month = pd.Period(f"{next_year}-{next_month:02d}").days_in_month
    next_month_forecast = choose_forecast(df_for_next_month, days_in_next_month)
    next_month_display = next_month_forecast if next_month_forecast is not None else "--"

    # ---- 9. Return final dict ----
    return {
        "this_month_expected": this_month_display,
        "spent_so_far": spent_so_far_display,
        "next_month_expected": next_month_display,
    }
