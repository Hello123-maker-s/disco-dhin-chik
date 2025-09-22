from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import models
from django.db.models import Sum
from finance.models import Income, Expense
from .models import SavingsGoal, SavingsDeposit, AutoSavingsRule, SurplusTracker

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def calculate_surplus(user):
    total_income = Income.objects.filter(user=user).aggregate(total=Sum("amount"))["total"] or 0
    total_expense = Expense.objects.filter(user=user).aggregate(total=Sum("amount"))["total"] or 0
    return max(total_income - total_expense, 0)


def apply_auto_savings_rules(user):
    today = date.today()
    incomes = Income.objects.filter(user=user, date__year=today.year, date__month=today.month)
    total_income = incomes.aggregate(total=Sum("amount"))["total"] or 0

    if not total_income:
        return 0

    # Pick one highest priority rule
    rule = (
        AutoSavingsRule.objects
        .filter(goal__user=user)
        .select_related("goal")
        .order_by(models.Case(
            models.When(goal__priority="High", then=0),
            models.When(goal__priority="Medium", then=1),
            models.When(goal__priority="Low", then=2),
            default=3
        ), "goal__deadline", "goal__id")
        .first()
    )

    if not rule:
        return 0

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
            # Deposit.save() will update goal.current_amount automatically
            rule.last_applied = today
            rule.save()
            return allocation

    return 0

""" def auto_allocate_savings(user):
    # Step 1 → Apply rules
    rule_allocations = apply_auto_savings_rules(user)

    # Step 2 → Calculate current surplus
    current_surplus = calculate_surplus(user) - rule_allocations

    # Get/create surplus tracker
    tracker, _ = SurplusTracker.objects.get_or_create(user=user)

    # If surplus hasn't changed → do nothing
    if current_surplus == tracker.last_surplus:
        return current_surplus

    # Otherwise, update tracker
    tracker.last_surplus = current_surplus
    tracker.save()

    # Step 3 → Only then do allocations
    if current_surplus > 0:
        goal = (
            SavingsGoal.objects
            .filter(user=user)
            .exclude(current_amount__gte=models.F("target_amount"))
            .order_by(models.Case(
                models.When(priority="High", then=0),
                models.When(priority="Medium", then=1),
                models.When(priority="Low", then=2),
                default=3
            ), "deadline", "id")
            .first()
        )
        if goal:
            needed = goal.remaining_amount()
            allocation = min(current_surplus, needed)
            SavingsDeposit.objects.create(goal=goal, amount=allocation)
            current_surplus -= allocation

    elif current_surplus < 0:
        goal = (
            SavingsGoal.objects
            .filter(user=user, current_amount__gt=0)
            .order_by(models.Case(
                models.When(priority="Low", then=0),
                models.When(priority="Medium", then=1),
                models.When(priority="High", then=2),
                default=3
            ), "-deadline", "-id")
            .first()
        )
        deficit = abs(current_surplus)
        if goal:
            withdrawal = min(goal.current_amount, deficit)
            SavingsDeposit.objects.create(goal=goal, amount=-withdrawal)
            deficit -= withdrawal
            current_surplus = -deficit

    return current_surplus """


def auto_allocate_savings(user):
    # Step 1 → Apply user-defined rules
    rule_allocations = apply_auto_savings_rules(user)

    # Step 2 → Check surplus/deficit after rules
    surplus = calculate_surplus(user) - rule_allocations

    if surplus > 0:
        # Deposit flow: pick one highest priority goal
        goal = (
            SavingsGoal.objects
            .filter(user=user)
            .exclude(current_amount__gte=models.F("target_amount"))
            .order_by(models.Case(
                models.When(priority="High", then=0),
                models.When(priority="Medium", then=1),
                models.When(priority="Low", then=2),
                default=3
            ), "deadline", "id")
            .first()
        )
        if goal:
            needed = goal.remaining_amount()
            allocation = min(surplus, needed)
            SavingsDeposit.objects.create(goal=goal, amount=allocation)
            surplus -= allocation

    elif surplus < 0:
        # Withdrawal flow: pick one lowest priority goal
        goal = (
            SavingsGoal.objects
            .filter(user=user, current_amount__gt=0)
            .order_by(models.Case(
                models.When(priority="Low", then=0),
                models.When(priority="Medium", then=1),
                models.When(priority="High", then=2),
                default=3
            ), "-deadline", "-id")
            .first()
        )
        deficit = abs(surplus)
        if goal:
            withdrawal = min(goal.current_amount, deficit)
            SavingsDeposit.objects.create(goal=goal, amount=-withdrawal)
            deficit -= withdrawal
            surplus = -deficit

    return surplus

