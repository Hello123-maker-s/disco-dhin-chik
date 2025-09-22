# budget/views.py
from decimal import Decimal
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Budget, BudgetCategory
from .forms import BudgetForm, BudgetCategoryForm, calculate_recurring_total
from django.core.paginator import Paginator
from finance.models import Income, RecurringIncome
from django.db import models


def get_available_income(start_date, end_date, user):
    # Total one-time income in period (user-specific)
    income_total = Income.objects.filter(
        user=user,
        date__range=[start_date, end_date]
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal("0.00")

    recurring_total = calculate_recurring_total(start_date, end_date, user=user)

    return income_total + recurring_total


@login_required
def budget_list(request):
    budgets = Budget.objects.filter(user=request.user)

    total_spent = Decimal("0.00")
    total_amount = Decimal("0.00")
    total_remaining = Decimal("0.00")

    budget_data = []
    for b in budgets:
        spent = sum(Decimal(cat.spent()) for cat in b.categories.all())
        total = Decimal(b.total_amount)
        remaining = total - spent
        percent = Decimal("0") if total == 0 else (spent / total) * 100

        budget_data.append({
            "obj": b,
            "spent": spent,
            "remaining": remaining,
            "percent": percent
        })

        total_spent += spent
        total_amount += total
        total_remaining += remaining

    overall_percent = Decimal("0") if total_amount == 0 else (total_spent / total_amount) * 100

    paginator = Paginator(budget_data, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    total_pages = paginator.num_pages
    current_page = page_obj.number
    window_size = 4
    start_page = max(current_page - 2, 1)
    end_page = min(start_page + window_size - 1, total_pages)
    if end_page - start_page < window_size - 1:
        start_page = max(end_page - window_size + 1, 1)
    page_range = range(start_page, end_page + 1)

    context = {
        "budgets": budgets,
        "budget_data": page_obj,
        "total_spent": total_spent,
        "total_amount": total_amount,
        "total_remaining": total_remaining,
        "overall_percent": overall_percent,
        "page_obj": page_obj,
        "page_range": page_range,
    }

    return render(request, "budget/budget_list.html", context)


@login_required
def add_budget(request):
    available_income = None
    
    if request.method == "POST":
        form = BudgetForm(request.POST)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user   # assign logged-in user
            budget.save()
            messages.success(request, "Budget created successfully.")
            return redirect("budget_detail", budget_id=budget.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = BudgetForm()
        start_date = form.fields['start_date']
        end_date = form.fields['end_date']
        if start_date.initial and end_date.initial:
            available_income = get_available_income(start_date.initial, end_date.initial, request.user)

    context = {
        "form": form,
        "available_income": available_income
    }
    return render(request, "budget/add_budget.html", context)


@login_required
def edit_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    available_income = get_available_income(budget.start_date, budget.end_date, request.user)

    if request.method == "POST":
        form = BudgetForm(request.POST, instance=budget)
        if form.is_valid():
            form.save()
            messages.success(request, "Budget updated successfully.")
            return redirect("budget_detail", budget_id=budget.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = BudgetForm(instance=budget)

    context = {
        "form": form,
        "budget": budget,
        "edit_mode": True,
        "available_income": available_income
    }
    return render(request, "budget/add_budget.html", context)


@login_required
def budget_detail(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    available_income = get_available_income(budget.start_date, budget.end_date, request.user)
    
    category_data = []
    total_spent = Decimal("0")
    total_limit = Decimal("0")
    
    for cat in budget.categories.all():
        limit = Decimal(cat.limit)
        spent = Decimal(cat.spent())
        percent = Decimal("0") if limit == 0 else (spent / limit) * 100
        percent_of_budget = Decimal("0") if budget.total_amount == 0 else (limit / Decimal(budget.total_amount)) * 100    
        
        total_spent += spent
        total_limit += limit
        
        category_data.append({
            "obj": cat,
            "spent": spent,
            "limit": limit,
            "percent": percent,
            "percent_of_budget": percent_of_budget,
        })
        
    overall_percent = Decimal("0") if total_limit == 0 else (total_spent / total_limit) * 100
    total_percent_of_budget = Decimal("0") if budget.total_amount == 0 else (total_limit / Decimal(budget.total_amount)) * 100
    form = BudgetCategoryForm(budget=budget)
    
    context = {
        "budget": budget,
        "category_data": category_data,
        "form": form,
        "total_spent": total_spent,
        "total_limit": total_limit,
        "overall_percent": overall_percent,
        "total_percent_of_budget": total_percent_of_budget,
        "available_income": available_income,
    }

    return render(request, "budget/budget_detail.html", context)


@login_required
def add_category(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)

    if request.method == "POST":
        form = BudgetCategoryForm(request.POST, budget=budget)
        if form.is_valid():
            category = form.save(commit=False)
            category.budget = budget
            category.limit = form.cleaned_data["limit"]
            category.save()
            messages.success(request, "Category added successfully.")
            return redirect("budget_detail", budget_id=budget.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "limit":
                        messages.error(request, error)
                    else:
                        messages.error(request, f"{field}: {error}")
                               
    return redirect("budget_detail", budget_id=budget.id)


@login_required
def edit_category(request, category_id):
    category = get_object_or_404(BudgetCategory, id=category_id, budget__user=request.user)
    budget = category.budget

    if request.method == "POST":
        form = BudgetCategoryForm(request.POST, instance=category, budget=budget)
        if form.is_valid():
            category = form.save(commit=False)
            category.limit = form.cleaned_data["limit"]
            category.save()
            messages.success(request, "Category updated successfully.")
            return redirect("budget_detail", budget_id=budget.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BudgetCategoryForm(instance=category, budget=budget)

    context = {
        "budget": budget,
        "form": form
    }
    return render(request, "budget/budget_detail.html", context)


@login_required
def delete_selected_budgets(request):
    if request.method == "POST":
        ids = request.POST.get("selected_ids", "")
        if ids:
            id_list = [int(i) for i in ids.split(",") if i.isdigit()]
            Budget.objects.filter(id__in=id_list, user=request.user).delete()
            messages.success(request, "Selected budget(s) deleted successfully.")
        else:
            messages.warning(request, "No budgets selected for deletion.")
    return redirect("budget_list")


@login_required
def bulk_delete_budget(request):
    if request.method == "POST":
        count = Budget.objects.filter(user=request.user).count()
        Budget.objects.filter(user=request.user).delete()
        messages.success(request, f"All {count} budgets deleted successfully.")
    return redirect("budget_list")


@login_required
def delete_selected_categories(request):
    if request.method == "POST":
        ids = request.POST.get("selected_ids", "")
        if ids:
            id_list = [int(i) for i in ids.split(",") if i.isdigit()]
            first_category = BudgetCategory.objects.filter(id__in=id_list, budget__user=request.user).first()
            budget_id = first_category.budget.id if first_category else None
            deleted_count = BudgetCategory.objects.filter(id__in=id_list, budget__user=request.user).delete()[0]
            messages.success(request, f"{deleted_count} category(s) deleted successfully.")
        else:
            messages.warning(request, "No categories selected for deletion.")
            budget_id = request.POST.get("budget_id")

        return redirect("budget_detail", budget_id=budget_id) if budget_id else redirect("budget_list")


@login_required
def bulk_delete_categories(request):
    if request.method == "POST":
        budget_id = request.POST.get("budget_id")
        if budget_id:
            budget = get_object_or_404(Budget, id=budget_id, user=request.user)
            count = budget.categories.count()
            budget.categories.all().delete()
            messages.success(request, f"All {count} categories deleted successfully.")
            return redirect("budget_detail", budget_id=budget.id)
        else:
            messages.warning(request, "Budget not specified for bulk delete.")
            return redirect("budget_list")
