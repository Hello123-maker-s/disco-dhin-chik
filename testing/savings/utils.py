from datetime import date
from decimal import Decimal
from django.db.models import Sum, F, Case, When
from dateutil.relativedelta import relativedelta

from finance.models import Income, Expense
from .models import SavingsGoal, AutoSavingsRule


# -------------------------
# Auto-Savings Rules
# -------------------------
def apply_auto_savings_rules(user):
    """
    Apply auto-savings rules for the current month.
    """
    today = date.today()
    current_month_income = Income.objects.filter(
        user=user, date__year=today.year, date__month=today.month
    ).aggregate(Sum("amount"))["amount__sum"] or 0
    if current_month_income <= 0:
        return Decimal(0)

    # Pick highest priority rule
    rule = (
        AutoSavingsRule.objects.filter(goal__user=user)
        .select_related("goal")
        .order_by(
            Case(
                When(goal__priority="High", then=0),
                When(goal__priority="Medium", then=1),
                When(goal__priority="Low", then=2),
                default=3
            ),
            "goal__deadline", "goal__id"
        )
        .first()
    )

    if not rule:
        return Decimal(0)

    # Check frequency
    apply_rule = False
    if not rule.last_applied:
        apply_rule = True
    else:
        delta = relativedelta(today, rule.last_applied)
        if (rule.frequency == "monthly" and delta.months >= 1) or \
           (rule.frequency == "quarterly" and delta.months >= 3) or \
           (rule.frequency == "biannually" and delta.months >= 6) or \
           (rule.frequency == "annually" and delta.years >= 1):
            apply_rule = True

    if apply_rule:
        allocation = (Decimal(current_month_income) * rule.percentage) / Decimal(100)
        if allocation > 0:
            from .models import SavingsDeposit  # import locally to avoid circular issues
            SavingsDeposit.objects.create(goal=rule.goal, amount=allocation)
            rule.last_applied = today
            rule.save()
            return allocation

    return Decimal(0)


# -------------------------
# Monthly Surplus
# -------------------------
def calculate_monthly_surplus(user, year, month):
    total_income = Income.objects.filter(
        user=user, date__year=year, date__month=month
    ).aggregate(Sum("amount"))["amount__sum"] or 0

    total_expense = Expense.objects.filter(
        user=user, date__year=year, date__month=month
    ).aggregate(Sum("amount"))["amount__sum"] or 0

    return max(Decimal(total_income) - Decimal(total_expense), Decimal(0))


def calculate_current_month_balance(user):
    today = date.today()
    total_income = Income.objects.filter(
        user=user, date__year=today.year, date__month=today.month
    ).aggregate(Sum("amount"))["amount__sum"] or 0

    total_expense = Expense.objects.filter(
        user=user, date__year=today.year, date__month=today.month
    ).aggregate(Sum("amount"))["amount__sum"] or 0

    return max(Decimal(total_income) - Decimal(total_expense), Decimal(0))


# -------------------------
# Auto Allocate Surplus
# -------------------------
def auto_allocate_savings(user):
    """
    Handles accumulated balance and goal allocation.
    """
    from .models import SurplusTracker, SavingsDeposit

    tracker, _ = SurplusTracker.objects.get_or_create(user=user)
    today = date.today()
    first_day_current_month = date(today.year, today.month, 1)

    # 1️⃣ Calculate total surplus of previous months (excluding current month)
    total_income_prev = Income.objects.filter(user=user, date__lt=first_day_current_month).aggregate(Sum("amount"))["amount__sum"] or 0
    total_expense_prev = Expense.objects.filter(user=user, date__lt=first_day_current_month).aggregate(Sum("amount"))["amount__sum"] or 0
    previous_surplus = Decimal(total_income_prev) - Decimal(total_expense_prev)

    # 2️⃣ Total deposits already made
    total_deposits = SavingsDeposit.objects.filter(goal__user=user).aggregate(Sum("amount"))["amount__sum"] or 0

    # 3️⃣ Update accumulated balance in tracker
    tracker.last_surplus = max(previous_surplus - Decimal(total_deposits), Decimal(0))
    tracker.save()

    # 4️⃣ Apply accumulated balance to goals by priority (High → Medium → Low)
    surplus_to_allocate = tracker.last_surplus
    if surplus_to_allocate > 0:
        goals = SavingsGoal.objects.filter(user=user, current_amount__lt=F("target_amount")).order_by(
            Case(
                When(priority="High", then=0),
                When(priority="Medium", then=1),
                When(priority="Low", then=2),
                default=3
            ),
            "deadline", "id"
        )

        while surplus_to_allocate > 0 and goals.exists():
            first_priority = goals.first().priority
            same_priority_goals = goals.filter(priority=first_priority)
            share = surplus_to_allocate / same_priority_goals.count()

            for goal in same_priority_goals:
                needed = goal.remaining_amount()
                allocation = min(share, needed)
                if allocation > 0:
                    SavingsDeposit.objects.create(goal=goal, amount=allocation)
                    surplus_to_allocate -= allocation

            # Refresh goal list
            goals = SavingsGoal.objects.filter(user=user, current_amount__lt=F("target_amount")).order_by(
                Case(
                    When(priority="High", then=0),
                    When(priority="Medium", then=1),
                    When(priority="Low", then=2),
                    default=3
                ),
                "deadline", "id"
            )

    # 5️⃣ Update leftover accumulated balance
    tracker.last_surplus = surplus_to_allocate
    tracker.save()

    return {
        "accumulated_balance": tracker.last_surplus,
        "current_balance": calculate_current_month_balance(user)
    }


# -------------------------
# Goal Deletion / Refund
# -------------------------
def delete_goals_with_refund(user, goals_queryset):
    """
    Deletes goals and refunds their deposited amount to accumulated balance.
    """
    from .models import SurplusTracker

    tracker, _ = SurplusTracker.objects.get_or_create(user=user)
    refund = goals_queryset.aggregate(total=Sum("current_amount"))["total"] or 0
    tracker.last_surplus += Decimal(refund)
    tracker.save()
    count = goals_queryset.count()
    goals_queryset.delete()
    return count, refund
