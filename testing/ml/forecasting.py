import pandas as pd
from django.utils.timezone import now
from finance.models import Expense
from prophet import Prophet
from sklearn.linear_model import LinearRegression
import numpy as np


def get_user_expense_forecast(user, forecast_date=None):
    """
    Hybrid expense forecast with month-end adjustment:
    - <100 rows & <6 months: rolling average
    - >=100 rows & <6 months: linear regression
    - >=6 months: Prophet
    Features:
      • Retroactive data entry (backfilled months update forecast instantly)
      • Normalization for sparse past months (<30 rows → daily baseline)
      • Month-end adjustment: forecasts lean on actuals if month is near over
      • Duplicate protection, safe fallback
    Returns:
        dict with 'this_month_expected', 'spent_so_far', 'next_month_expected'
    """
    today = forecast_date or now().date()
    first_day_of_month = pd.Timestamp(today.replace(day=1))
    days_in_this_month = pd.Period(f"{today.year}-{today.month:02d}").days_in_month
    today_day = today.day
    progress_ratio = today_day / days_in_this_month  # how far through month

    # ---- 1. Fetch user expenses ----
    expenses_qs = Expense.objects.filter(user=user).order_by("date")
    if not expenses_qs.exists():
        return {"this_month_expected": "--", "spent_so_far": "--", "next_month_expected": "--"}

    df_raw = pd.DataFrame(list(expenses_qs.values("date", "amount")))
    df_raw = df_raw.rename(columns={"date": "ds", "amount": "y"})
    df_raw["ds"] = pd.to_datetime(df_raw["ds"])
    df_raw["y"] = df_raw["y"].astype(float)

    # ---- 2. Normalize monthly data ----
    normalized_rows = []
    df_raw["YearMonth"] = df_raw["ds"].dt.to_period("M")

    for ym, group in df_raw.groupby("YearMonth"):
        if group.empty:
            continue
        month_year = ym.to_timestamp()
        # Past months only (before current month)
        if (month_year.year < today.year) or (month_year.year == today.year and month_year.month < today.month):
            if len(group) < 30:
                avg_daily = group["y"].sum() / 30.0
                days_in_month = ym.days_in_month
                days = pd.date_range(start=month_year, periods=days_in_month, freq="D")
                for d in days:
                    normalized_rows.append({"ds": d, "y_normalized": avg_daily})
            else:
                for _, row in group.iterrows():
                    normalized_rows.append({"ds": row["ds"], "y_normalized": row["y"]})
        else:
            # Current month → keep actuals only
            for _, row in group.iterrows():
                normalized_rows.append({"ds": row["ds"], "y_normalized": row["y"]})

    df = pd.DataFrame(normalized_rows).sort_values("ds").reset_index(drop=True)

    # ---- 3. Spent so far this month ----
    spent_this_month_df = df[(df["ds"].dt.year == today.year) & (df["ds"].dt.month == today.month)]
    spent_so_far_display = round(spent_this_month_df["y_normalized"].sum(), 2) if not spent_this_month_df.empty else "--"

    # ---- 4. Prepare slices ----
    df_past = df[df["ds"] < first_day_of_month].copy()       # past months only
    df_for_next_month = df_past.copy()                       # exclude current month
    df_full = df.copy()

    num_rows = len(df_full)
    min_ds = df["ds"].min()
    months_of_data = 0 if pd.isnull(min_ds) else (today.year - min_ds.year) * 12 + (today.month - min_ds.month)

    # ---- 5. Helpers ----
    def make_daily_series(df_input):
        if df_input.empty:
            return pd.DataFrame(columns=["ds", "y_normalized"])
        df_agg = df_input.groupby("ds", as_index=False)["y_normalized"].sum()
        df_daily = df_agg.set_index("ds").resample("D")["y_normalized"].sum().reset_index()
        return df_daily

    def rolling_forecast(df_input, days_in_month):
        try:
            df_daily = make_daily_series(df_input)
            if df_daily["y_normalized"].sum() == 0:
                return None
            median = df_daily["y_normalized"].median()
            cap = median * 5 if median > 0 else df_daily["y_normalized"].max()
            df_daily["y_normalized"] = df_daily["y_normalized"].clip(upper=cap)
            rolling_avg = df_daily["y_normalized"].rolling(window=7, min_periods=1).mean()
            return round(float(rolling_avg.mean() * days_in_month), 2)
        except Exception:
            return None

    def linear_regression_forecast(df_input, days_in_month):
        try:
            df_daily = make_daily_series(df_input)
            if df_daily.empty or df_daily["y_normalized"].sum() == 0:
                return None
            median = df_daily["y_normalized"].median()
            cap = median * 5 if median > 0 else df_daily["y_normalized"].max()
            df_daily["y_normalized"] = df_daily["y_normalized"].clip(upper=cap)
            df_daily = df_daily.reset_index(drop=True)
            df_daily["day_index"] = np.arange(len(df_daily))
            X = df_daily["day_index"].values.reshape(-1, 1)
            y = df_daily["y_normalized"].values
            model = LinearRegression()
            model.fit(X, y)
            future_days = np.arange(len(df_daily), len(df_daily) + days_in_month).reshape(-1, 1)
            y_pred = model.predict(future_days)
            return round(float(max(y_pred.sum(), 0.0)), 2)
        except Exception:
            return None

    def prophet_forecast(df_input, days_in_month):
        try:
            if df_input.empty or df_input["y_normalized"].sum() == 0:
                return None
            df_prophet = df_input.groupby("ds", as_index=False)["y_normalized"].sum().rename(columns={"y_normalized": "y"})
            if len(df_prophet) < 10:
                return None
            model = Prophet(daily_seasonality=True)
            model.fit(df_prophet)
            future = model.make_future_dataframe(periods=days_in_month)
            forecast = model.predict(future)
            return round(float(forecast[['yhat']].tail(days_in_month)["yhat"].sum()), 2)
        except Exception:
            return None

    def choose_forecast(df_input, days_in_month):
        if df_input.empty or df_input["y_normalized"].sum() == 0:
            return None
        if num_rows < 100 and months_of_data < 6:
            return rolling_forecast(df_input, days_in_month)
        elif num_rows >= 100 and months_of_data < 6:
            return linear_regression_forecast(df_input, days_in_month)
        else:
            return prophet_forecast(df_input, days_in_month)

    # ---- 6. Forecasts ----
    this_month_forecast = choose_forecast(df_past, days_in_this_month)
    # Month-end blending
    if this_month_forecast is not None and spent_this_month_df.shape[0] > 0:
        if progress_ratio > 0.8:  # near month end
            actual = spent_this_month_df["y_normalized"].sum()
            weight = min(1.0, progress_ratio)
            this_month_forecast = round((weight * actual) + ((1 - weight) * this_month_forecast), 2)

    this_month_display = this_month_forecast if this_month_forecast is not None else "--"

    next_month = (today.month % 12) + 1
    next_year = today.year + (1 if next_month == 1 else 0)
    days_in_next_month = pd.Period(f"{next_year}-{next_month:02d}").days_in_month
    next_month_forecast = choose_forecast(df_for_next_month, days_in_next_month)
    next_month_display = next_month_forecast if next_month_forecast is not None else "--"

    # ---- 7. Return ----
    return {
        "this_month_expected": this_month_display,
        "spent_so_far": spent_so_far_display,
        "next_month_expected": next_month_display,
    }
