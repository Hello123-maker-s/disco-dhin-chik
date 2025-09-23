from decimal import ROUND_HALF_UP, Decimal
from urllib import request
import csv
import datetime
import calendar
from unicodedata import category

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, ExtractWeek, ExtractMonth
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .models import (
    Expense, Income, RecurringIncome, RecurringExpense, 
    Category
)
from .forms import (
    IncomeForm, ExpenseForm, RecurringIncomeForm, RecurringExpenseForm,
    CategoryForm
)
from .utils import (
    get_next_due_date, normalize_headers, normalize_date, 
    clean_value, normalize_expense_category, normalize_income_category
)

from ml.classifier import predict_category
from ml.forecasting import get_user_expense_forecast
from savings.utils import auto_allocate_savings



# Create your views here.
@login_required
def add_expense(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user

            # ------------------ Auto ML Category Prediction ------------------ #
            if expense.category == 'Auto-predict' and expense.name:
                predicted_category = predict_category([expense.name])[0]  # returns a list
                # Validate predicted category against CATEGORY_CHOICES (excluding Auto-predict)
                valid_categories = [choice[0] for choice in Expense.CATEGORY_CHOICES if choice[0] != 'Auto-predict']
                if predicted_category in valid_categories:
                    expense.category = predicted_category
                else:
                    expense.category = 'Miscellaneous'
                    messages.warning(request, f"Predicted category '{predicted_category}' is invalid. Using Miscellaneous.")

            # ------------------ Totals Calculation ------------------ #
            total_income = Income.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            total_expense = Expense.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            # Check if this expense surpasses income
            if (Decimal(total_expense) + Decimal(expense.amount)) > Decimal(total_income):
                messages.error(request, "Expense cannot surpass total income!")
            else:
                expense.save()
                auto_allocate_savings(request.user)
                messages.success(request, "Expense added successfully!")
                return redirect('add_expense')

    else:
        form = ExpenseForm()

    # ------------------ Chart Data ------------------ #
    categories = [choice[0] for choice in Expense.CATEGORY_CHOICES if choice[0] != 'Auto-predict']
    chart_data = []
    for cat in categories:
        total = Expense.objects.filter(category=cat, user=request.user).aggregate(Sum('amount'))['amount__sum'] or 0
        chart_data.append(float(total))

    context = {
        'form': form,
        'categories': categories,
        'chart_data': chart_data,
        'timezone': timezone.now()
    }
    return render(request, 'finance/add_expense.html', context)

@login_required
def add_income(request):
    if request.method == 'POST':
        form = IncomeForm(request.POST)
        if form.is_valid():
            income = form.save(commit=False)
            income.user = request.user
            income.save()
            auto_allocate_savings(request.user)
            messages.success(request, "Income added successfully!")
            return redirect('add_income')
    else:
        form = IncomeForm()

    categories = [choice[0] for choice in Income.CATEGORY_CHOICES]
    chart_data = []
    for cat in categories:
        total = Income.objects.filter(category=cat, user=request.user).aggregate(Sum('amount'))['amount__sum'] or 0
        chart_data.append(float(total))

    context = {
        'form': form,
        'categories': categories,
        'chart_data': chart_data,
        'timezone': timezone.now()
    }
    return render(request, 'finance/add_income.html', context)

@login_required
def edit_income(request, id):
    income = get_object_or_404(Income, id=id, user=request.user)

    if request.method == "POST":
        form = IncomeForm(request.POST, instance=income)
        if form.is_valid():
            form.save()
            messages.success(request, "Income updated successfully!")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect("income_history")
  
@login_required
def delete_income(request, id):
    income = get_object_or_404(Income, id=id, user=request.user)
    if request.method == "POST":
        income.delete()
        messages.success(request, "Income deleted successfully!")
    return redirect("income_history")

@login_required
def edit_expense(request, id):
    expense = get_object_or_404(Expense, id=id, user=request.user)
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated successfully!")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect("expense_log")

@login_required
def delete_expense(request, id):
    expense = get_object_or_404(Expense, id=id, user=request.user)
    if request.method == "POST":
        expense.delete()
        messages.success(request, "Expense deleted successfully!")
    return redirect("expense_log")

@login_required
def upload_income_csv(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")

        # File size limit (1MB = 1,048,576 bytes)
        if csv_file.size > 1048576:
            messages.error(request, "File too large! Please upload a CSV under 1 MB.")
            return redirect("add_income")

        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Only CSV files are allowed!")
            return redirect("add_income")
        
        try:
            file_data = csv_file.read().decode("utf-8").splitlines()
            reader = csv.DictReader(file_data)

            field_map = normalize_headers([h.strip().lower() for h in reader.fieldnames])

            for row in reader:
                date_str = normalize_date(row.get(field_map.get("date")))
                source = clean_value(row.get("source"), default="Unknown")
                amount = clean_value(row.get(field_map.get("amount")), default=0, cast_type=Decimal)
                if amount:
                    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                raw_category = clean_value(row.get("category"), default="Other Income")
                category = normalize_income_category(raw_category)         #normalise category

                # Skip if essential data missing
                if not date_str or amount == 0 or not source:
                    continue

                try:
                    Income.objects.create(
                        date=date_str,
                        source=source,
                        amount=amount,
                        category=category,
                        user=request.user
                    )
                except Exception as e:
                    messages.error(request, f"Error saving row: {str(e)}")
                    continue  # skip bad rows

            messages.success(request, "CSV uploaded successfully!")
        except Exception as e:
            messages.error(request, f"Error processing CSV: {str(e)}")
            return redirect("add_income")
        return redirect("income_history")

    return redirect("add_income")

@login_required
def upload_expense_csv(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        
        if not csv_file:
            messages.error(request, "No file uploaded!")
            return redirect("add_expense")
        
        # File size limit (1MB)
        if csv_file.size > 1048576:
            messages.error(request, "File too large! Please upload a CSV under 1 MB.")
            return redirect("add_expense")

        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Only CSV files are allowed!")
            return redirect("add_expense")
        
        try:
            file_data = csv_file.read().decode("utf-8").splitlines()
            reader = csv.DictReader(file_data)

            # Prepare valid categories (excluding Auto-predict)
            valid_categories = [choice[0] for choice in Expense.CATEGORY_CHOICES if choice[0] != 'Auto-predict']

            for row in reader:
                # ------------------ Column Mapping / Normalization ------------------ #
                date_str = normalize_date(
                    row.get("Date") or row.get("Transaction Date") or row.get("Posted Date")
                )
                name = clean_value(
                    row.get("Description") or row.get("Transaction Details") or row.get("Memo"),
                    default="Unknown Expense"
                )

                # Amount normalization: handle Debit/Credit or single Amount column
                amount = None
                if row.get("Debit"):
                    amount = clean_value(row.get("Debit"), default=0, cast_type=Decimal)
                elif row.get("Credit"):
                    amount = -clean_value(row.get("Credit"), default=0, cast_type=Decimal)
                elif row.get("Amount"):
                    amount = clean_value(row.get("Amount"), default=0, cast_type=Decimal)

                if amount is None or amount == 0:
                    continue
                amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                if not date_str or not name:
                    continue

                # ------------------ ML Category Prediction ------------------ #
                predicted_category = predict_category([name])[0]
                category = predicted_category if predicted_category in valid_categories else "Miscellaneous"

                # ------------------ Income Check ------------------ #
                total_income = Income.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                total_expense = Expense.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                if (total_expense + amount) > total_income:
                    messages.warning(request, f"Skipping '{name}' - exceeds total income!")
                    continue

                # ------------------ Save Expense ------------------ #
                try:
                    Expense.objects.create(
                        date=date_str,
                        name=name,
                        amount=amount,
                        category=category,
                        user=request.user
                    )
                except Exception as e:
                    messages.error(request, f"Error saving '{name}': {str(e)}")
                    continue

            # ------------------ Post Processing ------------------ #
            auto_allocate_savings(request.user)
            messages.success(request, "CSV uploaded successfully!")

        except Exception as e:
            messages.error(request, f"Error processing CSV: {str(e)}")
            return redirect("add_expense")

        return redirect("expense_log")

    return redirect("add_expense")

@login_required
def expense_log(request):
    # Process recurring transactions first
    process_recurring_transactions(request.user)

    # Get all expenses for the user, most recent first
    expenses = Expense.objects.filter(user=request.user).order_by('-date')

    # Exclude 'Auto-predict' from categories for charts/filters
    categories = [choice[0] for choice in Expense.CATEGORY_CHOICES if choice[0] != 'Auto-predict']

    # Labels and data for chart
    labels = [expense.date.strftime('%Y-%m-%d') for expense in expenses]
    data = [float(expense.amount) for expense in expenses]

    # Pagination: 20 expenses per page
    paginator = Paginator(expenses, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Sliding window of 5 pages
    total_pages = paginator.num_pages
    current_page = page_obj.number
    window_size = 5
    start_page = max(current_page - 2, 1)
    end_page = min(start_page + window_size - 1, total_pages)
    if end_page - start_page < window_size - 1:
        start_page = max(end_page - window_size + 1, 1)
    page_range = range(start_page, end_page + 1)

    # ---- Forecast ----
    forecast = get_user_expense_forecast(request.user)

    context = {
        'expenses': page_obj,
        'labels': labels,
        'data': data,
        'categories': categories,
        'page_obj': page_obj,
        'page_range': page_range,
        'current_month_expected': f"₹{forecast['this_month_expected']}",
        'next_month_expected': f"₹{forecast['next_month_expected']}",
        'spent_so_far': f"₹{forecast['spent_so_far']}",
    }
    return render(request, 'finance/expense_log.html', context)

@login_required
@require_POST
def delete_selected_expenses(request):
    ids = request.POST.get("selected_ids", "")
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.isdigit()]
        Expense.objects.filter(id__in=id_list, user=request.user).delete()
    messages.success(request, "Selected expenses deleted successfully!")
    return redirect("expense_log")  # 👈 make sure this is the correct name of your expense list page

@login_required
def bulk_delete_expense(request):
    if request.method == "POST":
        Expense.objects.filter(user=request.user).delete()
    messages.success(request, "All expenses deleted successfully!")
    return redirect("expense_log")

@login_required
def income_history(request):
    process_recurring_transactions(request.user)
    incomes = Income.objects.filter(user=request.user).order_by('-date')
    categories = [choice[0] for choice in Income.CATEGORY_CHOICES]

    labels=[income.date.strftime('%Y-%m-%d') for income in incomes]
    data=[float(income.amount) for income in incomes]

    paginator = Paginator(incomes, 20)  # Show 20 incomes per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    #sliding window of 5 pages
    total_pages = paginator.num_pages
    current_page = page_obj.number
    window_size = 5
    start_page = max(current_page - 2, 1)
    end_page = min(start_page + window_size - 1, total_pages)
    if end_page - start_page < window_size - 1:
        start_page = max(end_page - window_size + 1, 1)
    page_range = range(start_page, end_page + 1)
    
    context={
        'incomes': page_obj,
        'labels': labels,
        'data': data,
        'categories': categories,
        'page_obj': page_obj,
        'page_range': page_range,
    }
    return render(request, 'finance/income_history.html', context)

@login_required
@require_POST
def delete_selected_incomes(request):
    ids = request.POST.get("selected_ids", "")
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.isdigit()]
        Income.objects.filter(id__in=id_list, user=request.user).delete()
    messages.success(request, "Selected incomes deleted successfully!")
    return redirect("income_history")

@login_required
def bulk_delete_income(request):
    if request.method == "POST":
        Income.objects.filter(user=request.user).delete()
    messages.success(request, "All incomes deleted successfully!")
    return redirect("income_history")

def process_recurring_transactions(user):
    today = timezone.now().date()

    # Current totals
    total_income = Income.objects.filter(user=user).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_expense = Expense.objects.filter(user=user).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Keep looping until nothing changes
    changed = True
    while changed:
        changed = False

        # ---- Process incomes ----
        incomes = RecurringIncome.objects.filter(user=user, next_due_date__lte=today)
        for rec in incomes:
            Income.objects.create(
                source=rec.source,
                amount=rec.amount,
                date=rec.next_due_date,
                category=rec.category,
                user=user
            )
            total_income += Decimal(rec.amount)
            rec.next_due_date = get_next_due_date(rec.next_due_date, rec.frequency)
            rec.save()
            changed = True  # something new was added

        # ---- Process expenses (pending or due) ----
        expenses = RecurringExpense.objects.filter(user=user, next_due_date__lte=today)
        for rec in expenses:
            if (total_expense + Decimal(rec.amount)) <= total_income:
                Expense.objects.create(
                    name=rec.name,
                    amount=rec.amount,
                    date=rec.next_due_date,
                    category=rec.category,
                    user=user
                )
                total_expense += Decimal(rec.amount)
                rec.next_due_date = get_next_due_date(rec.next_due_date, rec.frequency)
                rec.status = "active"
                rec.save()
                changed = True
            else:
                # mark as pending, retry in next loop if income comes later in same run
                rec.status = "pending"
                rec.save()

        # ---- Retry pending expenses ----
        pendings = RecurringExpense.objects.filter(user=user, status="pending")
        for rec in pendings:
            if (total_expense + Decimal(rec.amount)) <= total_income:
                Expense.objects.create(
                    name=rec.name,
                    amount=rec.amount,
                    date=rec.next_due_date,
                    category=rec.category,
                    user=user
                )
                total_expense += Decimal(rec.amount)
                rec.next_due_date = get_next_due_date(rec.next_due_date, rec.frequency)
                rec.status = "active"
                rec.save()
                changed = True

def retry_pending_expenses(user, total_income, total_expense):
    pending = RecurringExpense.objects.filter(user=user, status="pending").order_by("next_due_date")
    for rec in pending:
        if (total_expense + Decimal(rec.amount)) <= total_income:
            Expense.objects.create(
                name=rec.name,
                amount=rec.amount,
                date=rec.next_due_date,
                category=rec.category,
                user=user
            )
            total_expense += Decimal(rec.amount)
            rec.next_due_date = get_next_due_date(rec.next_due_date, rec.frequency)
            rec.status = "active"
            rec.save()


""" def process_recurring_transactions(user):
    today = timezone.now().date()

    # Process incomes
    for rec in RecurringIncome.objects.filter(user=user):
        while rec.next_due_date <= today:
            Income.objects.create(
                source=rec.source,
                amount=rec.amount,
                date=rec.next_due_date,
                category=rec.category,
                user=user
            )
            rec.next_due_date = get_next_due_date(rec.next_due_date, rec.frequency)
            rec.save()

    # Process expenses
    for rec in RecurringExpense.objects.filter(user=user):
        while rec.next_due_date <= today:
            Expense.objects.create(
                name=rec.name,
                amount=rec.amount,
                date=rec.next_due_date,
                category=rec.category,
                user=user
            )
            rec.next_due_date = get_next_due_date(rec.next_due_date, rec.frequency)
            rec.save() """
            
@login_required
def recurring_expense(request):
    if request.method == 'POST':
        form = RecurringExpenseForm(request.POST)
        if form.is_valid():
            rec_exp = form.save(commit=False)
            rec_exp.user = request.user
            rec_exp.next_due_date = rec_exp.start_date  # ensure proper Date object
            rec_exp.save()
        messages.success(request, "Recurring expense added successfully!")
        return redirect('recurring_expense')
    else:
        form = RecurringExpenseForm()
    
    process_recurring_transactions(request.user)
    expenses = RecurringExpense.objects.filter(user=request.user)

    category_totals = expenses.values('category').annotate(total=Sum('amount'))
    categories = [item['category'] for item in category_totals]
    chart_data = [float(item['total']) for item in category_totals]

    context = {
        'form': form,
        'expenses': expenses,
        'categories': categories,
        'chart_data': chart_data,
        'timezone': timezone.now(),
    }
    return render(request, 'finance/recurring_expense.html', context)

@login_required
def recurring_income(request):
    if request.method == 'POST':
        form = RecurringIncomeForm(request.POST)
        if form.is_valid():
            rec_inc = form.save(commit=False)
            rec_inc.user = request.user
            rec_inc.next_due_date = rec_inc.start_date  # ensure proper Date object
            rec_inc.save()
            messages.success(request, "Recurring income added successfully!")
            return redirect('recurring_income')
    else:
        form = RecurringIncomeForm()

    process_recurring_transactions(request.user)
    incomes = RecurringIncome.objects.filter(user=request.user)

    category_totals = incomes.values('category').annotate(total=Sum('amount'))
    categories = [item['category'] for item in category_totals]
    chart_data = [float(item['total']) for item in category_totals]

    context = {
        'form': form,
        'incomes': incomes,
        'categories': categories,
        'chart_data': chart_data,
        'timezone': timezone.now()
    }
    return render(request, 'finance/recurring_income.html', context)

@login_required
def edit_recurring_expense(request, id):
    expense = get_object_or_404(RecurringExpense, id=id, user=request.user)

    if request.method == "POST":
        form = RecurringExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "Recurring expense updated successfully!")
            return redirect("recurring_expense")
        else:
            messages.error(request, "Please correct the errors below.")

    # if GET, show prefilled form (only needed if you want standalone edit page)
    else:
        form = RecurringExpenseForm(instance=expense)

    return redirect("recurring_expense")
    
@login_required    
def delete_recurring_expense(request, id):
    expense = get_object_or_404(RecurringExpense, id=id, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, "Recurring expense deleted successfully!")
        return redirect('recurring_expense')
    
@login_required
def edit_recurring_income(request, id):
    income = get_object_or_404(RecurringIncome, id=id, user=request.user)

    if request.method == "POST":
        form = RecurringIncomeForm(request.POST, instance=income)
        if form.is_valid():
            form.save()
            messages.success(request, "Recurring income updated successfully!")
            return redirect("recurring_income")
        else:
            messages.error(request, "Please correct the errors below.")

    # if GET, show prefilled form (only needed if you want standalone edit page)
    else:
        form = RecurringIncomeForm(instance=income)

    return redirect("recurring_income")

@login_required
def delete_recurring_income(request, id):
    income = get_object_or_404(RecurringIncome, id=id, user=request.user)
    if request.method == 'POST':
        income.delete()
        messages.success(request, "Recurring income deleted successfully!")
        return redirect('recurring_income')

@login_required
def dashboard(request):
    # Before loading dashboard, process any due recurring transactions
    process_recurring_transactions(request.user)

    # Now dashboard works with normal Income & Expense only
    income_total = Income.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    expense_total = Expense.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Ensure values are Decimal
    income_total = Decimal(income_total)
    expense_total = Decimal(expense_total)

    # Calculate balance as Decimal
    balance = income_total - expense_total

    # Optionally, round to 2 decimal places for display
    balance = balance.quantize(Decimal('0.01'))
    income_total = income_total.quantize(Decimal('0.01'))
    expense_total = expense_total.quantize(Decimal('0.01'))

    last_income = Income.objects.filter(user=request.user).order_by('-date').first()
    last_expense = Expense.objects.filter(user=request.user).order_by('-date').first()

    if last_income and last_expense:
        last_transaction = last_income if last_income.date > last_expense.date else last_expense
    elif last_income:
        last_transaction = last_income
    elif last_expense:
        last_transaction = last_expense
    else:
        last_transaction = None
        
    today = timezone.now().date()
    # Get due recurring expenses (pending)
    due_expenses = RecurringExpense.objects.filter(user=request.user, next_due_date__lte=today, status__in=["active", "pending"]).order_by('next_due_date')

    # Monthly trends
    monthly_income = (
        Income.objects.filter(user=request.user).annotate(month=ExtractMonth('date')).values('month').annotate(total=Sum('amount')).order_by('month')
    )
    monthly_expense = (
        Expense.objects.filter(user=request.user).annotate(month=ExtractMonth('date')).values('month').annotate(total=Sum('amount')).order_by('month')
    )

    income_dict = {item['month']: float(item['total']) for item in monthly_income}
    expense_dict = {item['month']: float(item['total']) for item in monthly_expense}

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    income_data = [income_dict.get(i+1, 0) for i in range(12)]
    expense_data = [expense_dict.get(i+1, 0) for i in range(12)]

    # Weekly trends
    weekly_income = (
        Income.objects.filter(user=request.user).annotate(week=ExtractWeek('date')).values('week').annotate(total=Sum('amount')).order_by('week')
    )
    weekly_expense = (
        Expense.objects.filter(user=request.user).annotate(week=ExtractWeek('date')).values('week').annotate(total=Sum('amount')).order_by('week')
    )

    week_income_dict = {w['week']: float(w['total']) for w in weekly_income}
    week_expense_dict = {w['week']: float(w['total']) for w in weekly_expense}

    weeks = [f"Week {i}" for i in range(1, 53)]
    weekly_income_data = [week_income_dict.get(i, 0) for i in range(1, 53)]
    weekly_expense_data = [week_expense_dict.get(i, 0) for i in range(1, 53)]

    # Category-wise
    category_expenses = (
        Expense.objects.filter(user=request.user).values('category').annotate(total=Sum('amount')).order_by('-total')
    )
    category_labels = [c['category'] for c in category_expenses]
    category_values = [float(c['total']) for c in category_expenses]

    context = {
        "total_income": income_total,
        "total_expense": expense_total,
        "balance": balance,
        "months": months,
        "income_data": income_data,
        "expense_data": expense_data,
        "weeks": weeks,
        "weekly_income_data": weekly_income_data,
        "weekly_expense_data": weekly_expense_data,
        "category_labels": category_labels,
        "category_values": category_values,
        "last_transaction": last_transaction,
        "last_income": last_income,
        "last_expense": last_expense,
        "due_expenses": due_expenses
    }
    return render(request, "finance/dashboard.html", context)


