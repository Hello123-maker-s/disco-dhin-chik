from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import SavingsGoal, SavingsDeposit, AutoSavingsRule
from .forms import SavingsGoalForm, SavingsDepositForm, AutoSavingsRuleForm
from .utils import auto_allocate_savings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

@login_required
def savings_dashboard(request):
    surplus = auto_allocate_savings(request.user)

    # All goals (for chart & stats)
    all_goals = SavingsGoal.objects.filter(user=request.user).order_by("deadline", "id")

    # Paginate for table only
    paginator = Paginator(all_goals, 10)  # 10 rows per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Sliding window pagination
    total_pages = paginator.num_pages
    current_page = page_obj.number
    window_size = 4
    start_page = max(current_page - 2, 1)
    end_page = min(start_page + window_size - 1, total_pages)
    if end_page - start_page < window_size - 1:
        start_page = max(end_page - window_size + 1, 1)
    page_range = range(start_page, end_page + 1)
    
    # Summary stats
    total_goals = all_goals.count()
    total_target = sum(goal.target_amount for goal in all_goals)
    total_current = sum(goal.current_amount for goal in all_goals)
    overall_progress = 0
    if total_target > 0:
        overall_progress = (total_current / total_target) * 100

    # Chart data uses ALL goals, not just paginated
    labels = [goal.name for goal in all_goals]
    progress = [float(goal.progress()) for goal in all_goals]

    context = {
        "labels": labels,
        "progress": progress,
        "goals": page_obj,      # paginated table
        "page_obj": page_obj,
        "page_range": page_range,
        "total_goals": total_goals,
        "total_target": total_target,
        "total_current": total_current,
        "remaining_surplus": surplus,
        "overall_progress": overall_progress
    }
    return render(request, "savings/dashboard.html", context)

@login_required
def delete_selected_goals(request):
    if request.method == "POST":
        selected_ids = request.POST.get("selected_ids", "")
        if not selected_ids.strip():
            messages.error(request, "⚠️ Please select at least one goal for deletion.")
            return redirect("savings_dashboard")

        ids_list = [int(i) for i in selected_ids.split(",") if i.isdigit()]
        if ids_list:
            SavingsGoal.objects.filter(id__in=ids_list, user=request.user).delete()
            messages.success(request, f"🗑️ {len(ids_list)} goal(s) deleted successfully!")
        else:
            messages.error(request, "⚠️ No valid goals selected.")
    return redirect("savings_dashboard")


@login_required
def delete_all_goals(request):
    if request.method == "POST":
        total = SavingsGoal.objects.filter(user=request.user).count()
        if total == 0:
            messages.error(request, "⚠️ No goals available to delete.")
        else:
            SavingsGoal.objects.filter(user=request.user).delete()
            messages.success(request, f"🗑️ All {total} goals deleted successfully!")
    return redirect("savings_dashboard")

@login_required
def goal_form(request, id=None):
    if id:  # Editing
        goal = get_object_or_404(SavingsGoal, id=id, user=request.user)
    else:   # Adding
        goal = None

    if request.method == "POST":
        form = SavingsGoalForm(request.POST, instance=goal)
        if form.is_valid():
            new_goal = form.save(commit=False)
            new_goal.user = request.user
            new_goal.save()
            if goal:
                messages.success(request, "Savings goal updated!")
            else:
                messages.success(request, "Savings goal added!")
            return redirect("savings_dashboard")
    else:
        form = SavingsGoalForm(instance=goal)
        
    context = {
        "form": form,
        "goal": goal
    }
    return render(request, "savings/goal_form.html", context)   

@login_required
def delete_goal(request, id):
    goal = get_object_or_404(SavingsGoal, id=id, user=request.user)
    if request.method == "POST":
        goal.delete()
        messages.success(request, "Savings goal deleted!")
    return redirect("savings_dashboard")

@login_required
def deposit_form(request, id=None):
    deposit = get_object_or_404(SavingsDeposit, id=id, goal__user=request.user) if id else None

    if request.method == "POST":
        form = SavingsDepositForm(request.POST, instance=deposit, user=request.user)
        if form.is_valid():
            new_deposit = form.save(commit=False)
            new_deposit.save()
            messages.success(request, "Deposit saved and goal progress updated!")
            return redirect('savings_dashboard')  # redirect to goals
    else:
        form = SavingsDepositForm(instance=deposit, user=request.user)

    return render(request, 'savings/deposit_form.html', {'form': form})

@login_required
def manage_auto_savings(request, edit_id=None, delete_id=None):
    rules = AutoSavingsRule.objects.filter(goal__user=request.user)
    edit_rule = None
    form = AutoSavingsRuleForm(user=request.user)

    # ✅ Handle Delete
    if delete_id:
        rule = get_object_or_404(AutoSavingsRule, id=delete_id, goal__user=request.user)
        if request.method == "POST":
            rule.delete()
            messages.success(request, "Auto-savings rule deleted!")
            return redirect("manage_auto_savings")
        return redirect("manage_auto_savings")

    # ✅ Handle Edit
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

    # ✅ Handle Add
    elif request.method == "POST":
        form = AutoSavingsRuleForm(request.POST, user=request.user)
        if form.is_valid():
            rule = form.save(commit=False)
            if rule.goal.user == request.user:  # safeguard
                rule.save()
                messages.success(request, "Auto-savings rule added!")
            return redirect("manage_auto_savings")

    context = {
        "rules": rules,
        "form": form,
        "edit_rule": edit_rule
    }
    return render(request, "savings/manage_auto_savings.html", context)


