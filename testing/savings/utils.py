from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import models
from django.db.models import Sum, F
from finance.models import Income, Expense
from .models import SavingsGoal, SavingsDeposit, AutoSavingsRule, SurplusTracker

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def calculate_surplus(user):
    """
    Calculates current surplus: income - expenses for the last month
    """
    today = date.today()
    first_day_last_month = (today.replace(day=1) - relativedelta(months=1))
    last_day_last_month = today.replace(day=1) - relativedelta(days=1)

    total_income = Income.objects.filter(
        user=user, date__range=(first_day_last_month, last_day_last_month)
    ).aggregate(total=Sum("amount"))["total"] or 0

    total_expense = Expense.objects.filter(
        user=user, date__range=(first_day_last_month, last_day_last_month)
    ).aggregate(total=Sum("amount"))["total"] or 0

    return max(total_income - total_expense, 0)


def apply_auto_savings_rules(user):
    """
    Applies user-defined auto-savings rules first.
    Returns total amount allocated by rules.
    """
    today = date.today()
    incomes = Income.objects.filter(user=user, date__year=today.year, date__month=today.month)
    total_income = incomes.aggregate(total=Sum("amount"))["total"] or 0

    if not total_income:
        return 0

    total_allocated = 0

    rules = AutoSavingsRule.objects.filter(goal__user=user).select_related("goal")
    for rule in rules:
        should_apply = False
        if not rule.last_applied:
            should_apply = True
        else:
            delta = relativedelta(today, rule.last_applied)
            if rule.frequency == "monthly" and delta.months >= 1:
                should_apply = True
            elif rule.frequency == "quarterly" and delta.months >= 3:
                should_apply = True
            elif rule.frequency == "biannually" and delta.months >= 6:
                should_apply = True
            elif rule.frequency == "annually" and delta.years >= 1:
                should_apply = True

        if should_apply:
            allocation = (total_income * rule.percentage) / 100
            if allocation > 0:
                SavingsDeposit.objects.create(goal=rule.goal, amount=allocation)
                total_allocated += allocation
                rule.last_applied = today
                rule.save()

    return total_allocated


def auto_allocate_savings(user):
    """
    Allocates surplus to active savings goals based on priority.
    Surplus is split equally among same-priority goals and allocated
    sequentially from High → Medium → Low until exhausted.
    """
    today = date.today()
    tracker, _ = SurplusTracker.objects.get_or_create(user=user)

    # Ensure allocation only once per month
    if tracker.last_applied_month == today.month and tracker.last_applied_year == today.year:
        return tracker.last_surplus or 0

    # Step 1 → Apply auto-savings rules
    rule_allocations = apply_auto_savings_rules(user)

    # Step 2 → Calculate surplus after rules
    surplus = calculate_surplus(user) - rule_allocations
    if surplus <= 0:
        tracker.last_surplus = surplus
        tracker.last_applied_month = today.month
        tracker.last_applied_year = today.year
        tracker.save()
        return surplus

    # Step 3 → Fetch active goals, sorted by priority
    active_goals = list(
        SavingsGoal.objects.filter(user=user)
        .exclude(current_amount__gte=F("target_amount"))
        .order_by(
            models.Case(
                *[models.When(priority=p, then=v) for p, v in PRIORITY_ORDER.items()],
                default=3
            ),
            "deadline",
            "id"
        )
    )

    # Step 4 → Allocate surplus by priority
    for priority in ["High", "Medium", "Low"]:
        priority_goals = [g for g in active_goals if g.priority == priority]
        if not priority_goals:
            continue

        # Calculate total needed for all goals in this priority
        total_needed = sum(g.remaining_amount() for g in priority_goals)
        if total_needed <= 0:
            continue

        # Surplus to allocate for this priority
        allocation_amount = min(surplus, total_needed)

        # Split equally among goals
        num_goals = len(priority_goals)
        while allocation_amount > 0 and num_goals > 0:
            per_goal_allocation = allocation_amount / num_goals
            for goal in priority_goals[:]:  # Copy to allow removal
                needed = goal.remaining_amount()
                deposit_amount = min(per_goal_allocation, needed)
                SavingsDeposit.objects.create(goal=goal, amount=deposit_amount)
                allocation_amount -= deposit_amount

                # Remove fully funded goals
                if goal.current_amount + deposit_amount >= goal.target_amount:
                    priority_goals.remove(goal)

            num_goals = len(priority_goals)
        surplus -= min(surplus, total_needed)
        if surplus <= 0:
            break

    # Step 5 → Update tracker
    tracker.last_surplus = surplus
    tracker.last_applied_month = today.month
    tracker.last_applied_year = today.year
    tracker.save()

    return surplus
