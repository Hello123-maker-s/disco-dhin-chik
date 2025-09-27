from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator


from .models import SavingsGoal, SavingsDeposit, AutoSavingsRule
from .forms import SavingsGoalForm, SavingsDepositForm, AutoSavingsRuleForm
from .utils import auto_allocate_savings, delete_goals_with_refund


# -------------------------
# Dashboard
# -------------------------
@login_required
def savings_dashboard(request):
    # Automatically update accumulated balance and allocate to goals
    balances = auto_allocate_savings(request.user)

    all_goals = SavingsGoal.objects.filter(user=request.user).order_by("deadline", "id")
    paginator = Paginator(all_goals, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    total_goals = all_goals.count()
    total_target = sum(goal.target_amount for goal in all_goals)
    total_current = sum(goal.current_amount for goal in all_goals)

    # Overall progress across all goals
    overall_progress = (total_current / total_target * 100) if total_target else 0

    labels = [goal.name for goal in all_goals]
    progress = [float(goal.progress()) for goal in all_goals]

    # Current month balance (income - expense this month)
    current_balance = balances["current_balance"]

    # Accumulated balance (previous months) after allocation to goals
    accumulated_balance = balances["accumulated_balance"]

    # Total deposited into goals from accumulated balance + deposits = total current
    total_current_display = total_current

    return render(request, "savings/dashboard.html", {
        "labels": labels,
        "progress": progress,
        "goals": page_obj,
        "page_obj": page_obj,
        "total_goals": total_goals,
        "total_target": total_target,
        "total_current": total_current_display,
        "accumulated_balance": accumulated_balance,
        "current_balance": current_balance,
        "overall_progress": overall_progress
    })


# -------------------------
# CRUD: Goals Form
# -------------------------
@login_required
def goal_form(request, id=None):
    goal = get_object_or_404(SavingsGoal, id=id, user=request.user) if id else None
    if request.method == "POST":
        form = SavingsGoalForm(request.POST, instance=goal)
        if form.is_valid():
            new_goal = form.save(commit=False)
            new_goal.user = request.user
            new_goal.save()
            msg = "updated" if goal else "added"
            messages.success(request, f"Savings goal {msg} successfully!")
            return redirect("savings_dashboard")
    else:
        form = SavingsGoalForm(instance=goal)
    return render(request, "savings/goal_form.html", {"form": form, "goal": goal})


# -------------------------
# DELETE Goals (with refund)
# -------------------------
@login_required
def delete_goal(request, id):
    if request.method == "POST":
        goal = get_object_or_404(SavingsGoal, id=id, user=request.user)
        count, refund = delete_goals_with_refund(request.user, SavingsGoal.objects.filter(id=goal.id))
        messages.success(request, f"Goal '{goal.name}' deleted and {refund} refunded to accumulated balance!")
    return redirect("savings_dashboard")


@login_required
def delete_selected_goals(request):
    if request.method == "POST":
        ids_list = [int(i) for i in request.POST.get("selected_ids", "").split(",") if i.isdigit()]
        if ids_list:
            goals = SavingsGoal.objects.filter(id__in=ids_list, user=request.user)
            count, refund = delete_goals_with_refund(request.user, goals)
            messages.success(request, f"{count} goals deleted and {refund} refunded to accumulated balance!")
        else:
            messages.error(request, "No valid goals selected.")
    return redirect("savings_dashboard")


@login_required
def delete_all_goals(request):
    if request.method == "POST":
        goals = SavingsGoal.objects.filter(user=request.user)
        if goals.exists():
            count, refund = delete_goals_with_refund(request.user, goals)
            messages.success(request, f"All {count} goals deleted and {refund} refunded to accumulated balance!")
        else:
            messages.error(request, "No goals available to delete.")
    return redirect("savings_dashboard")


# -------------------------
# CRUD: Deposits
# -------------------------
@login_required
def deposit_form(request, id=None):
    deposit = get_object_or_404(SavingsDeposit, id=id, goal__user=request.user) if id else None
    if request.method == "POST":
        form = SavingsDepositForm(request.POST, instance=deposit, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Deposit saved and goal progress updated!")
            return redirect("savings_dashboard")
    else:
        form = SavingsDepositForm(instance=deposit, user=request.user)
    return render(request, "savings/deposit_form.html", {"form": form})


# -------------------------
# Auto-Savings Rules
# -------------------------
@login_required
def manage_auto_savings(request, edit_id=None, delete_id=None):
    rules = AutoSavingsRule.objects.filter(goal__user=request.user)
    edit_rule = None
    form = AutoSavingsRuleForm(user=request.user)

    if delete_id:
        rule = get_object_or_404(AutoSavingsRule, id=delete_id, goal__user=request.user)
        if request.method == "POST":
            rule.delete()
            messages.success(request, "Auto-savings rule deleted!")
            return redirect("manage_auto_savings")

    if edit_id:
        edit_rule = get_object_or_404(AutoSavingsRule, id=edit_id, goal__user=request.user)
        if request.method == "POST":
            form = AutoSavingsRuleForm(request.POST, instance=edit_rule, user=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Auto-savings rule updated!")
                return redirect("manage_auto_savings")
        else:
            form = AutoSavingsRuleForm(instance=edit_rule, user=request.user)
    elif request.method == "POST":
        form = AutoSavingsRuleForm(request.POST, user=request.user)
        if form.is_valid():
            rule = form.save(commit=False)
            if rule.goal.user == request.user:
                rule.save()
                messages.success(request, "Auto-savings rule added!")
            return redirect("manage_auto_savings")

    return render(request, "savings/manage_auto_savings.html", {
        "rules": rules,
        "form": form,
        "edit_rule": edit_rule
    })
