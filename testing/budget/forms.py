from django import forms
from .models import Budget, BudgetCategory
from decimal import Decimal
from django.db import models
from finance.models import Income, RecurringIncome, Expense
from django.db.models import Sum
from dateutil.relativedelta import relativedelta

FREQ_RELATIVE = {
    "daily": lambda d: d + relativedelta(days=1),
    "weekly": lambda d: d + relativedelta(weeks=1),
    "monthly": lambda d: d + relativedelta(months=1),
    "quarterly": lambda d: d + relativedelta(months=3),
    "biannually": lambda d: d + relativedelta(months=6),
    "annually": lambda d: d + relativedelta(years=1),
}

def calculate_recurring_total(start_date, end_date, user):
    total = Decimal("0.00")
    recurring_qs = RecurringIncome.objects.filter(user=user)  # user isolation
    for r in recurring_qs:
        freq = r.frequency.lower()
        next_date = r.next_due_date
        r_end = r.end_date or end_date
        
        while next_date < start_date:
            next_date = FREQ_RELATIVE.get(freq, lambda d: d)(next_date)
            
        while next_date <= end_date and next_date <= r_end:
            total += r.amount
            next_date = FREQ_RELATIVE.get(freq, lambda d: d)(next_date)
    return total

class BudgetForm(forms.ModelForm):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d', '%d-%m-%Y'], required=True, label="Start Date *"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d', '%d-%m-%Y'], required=True, label="End Date *"
    )

    class Meta:
        model = Budget
        fields = ["name", "total_amount", "start_date", "end_date"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Enter a Budget Name", "class": "form-input"}),
            "total_amount": forms.NumberInput(attrs={"placeholder": "Enter Total Amount", "class": "form-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)  # capture user
        super().__init__(*args, **kwargs)
           
    def clean(self):
        cleaned_data = super().clean()
        total_amount = cleaned_data.get("total_amount")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if total_amount and start_date and end_date and self.user:
            income_total = Income.objects.filter(
                user=self.user,
                date__range=[start_date, end_date]
            ).aggregate(total=Sum('amount'))['total'] or Decimal("0.00")

            recurring_total = calculate_recurring_total(start_date, end_date, self.user)

            available_income = income_total + recurring_total

            if total_amount > available_income:
                self.add_error(
                    "total_amount",
                    f"Budget cannot exceed total available income of the period: {available_income}"
                )

        return cleaned_data

class BudgetCategoryForm(forms.ModelForm):
    limit_type = forms.ChoiceField(
        choices=[("amount", "Amount"), ("percent", "Percentage of Budget")],
        required=True, initial="amount", label="Limit Type"
    )
    limit_value = forms.DecimalField(required=True, min_value=0, label="Limit (Amount or %)")

    class Meta:
        model = BudgetCategory
        fields = ["category"]

    def __init__(self, *args, **kwargs):
        self.budget = kwargs.pop("budget", None)
        super().__init__(*args, **kwargs)
        if 'category' in self.fields:
            self.fields['category'].choices = Expense.CATEGORY_CHOICES
        
        if not self.budget:
            return
        
        user = self.budget.user  # user comes from budget

        income_total = Income.objects.filter(
            user=user,
            date__range=[self.budget.start_date, self.budget.end_date]
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal("0.00")

        recurring_total = calculate_recurring_total(self.budget.start_date, self.budget.end_date, user)

        available_income = income_total + recurring_total
        
        existing_total = sum(c.limit for c in self.budget.categories.all())
        if self.instance.pk:
            existing_total -= self.instance.limit
        
        max_allowed = min(self.budget.total_amount - existing_total, available_income - existing_total)
        self.fields["limit_value"].widget.attrs["max"] = str(max_allowed)
        self.fields["limit_value"].help_text = f"Maximum allowed: {max_allowed}"
        
    def clean(self):
        cleaned_data = super().clean()
        limit_type = cleaned_data.get("limit_type")
        limit_value = cleaned_data.get("limit_value")
        category_name = cleaned_data.get("category")

        if not self.budget:
            raise forms.ValidationError("Budget context is required for category limits.")

        user = self.budget.user

        income_total = Income.objects.filter(
            user=user,
            date__range=[self.budget.start_date, self.budget.end_date]
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal("0.00")

        recurring_total = calculate_recurring_total(self.budget.start_date, self.budget.end_date, user)

        available_income = income_total + recurring_total

        if limit_type == "amount":
            cleaned_data["limit"] = limit_value
        elif limit_type == "percent":
            cleaned_data["limit"] = (limit_value / 100) * self.budget.total_amount
        else:
            cleaned_data["limit"] = Decimal("0.00")

        limit = cleaned_data.get("limit", Decimal("0.00"))

        if category_name:
            qs = self.budget.categories.filter(category__iexact=category_name.strip())
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "category",
                    f"The category '{category_name}' already exists in this budget."
                )
                
        existing_total = sum(c.limit for c in self.budget.categories.all())
        if self.instance.pk:
            existing_total -= self.instance.limit

        total_with_new = existing_total + (limit or 0)

        if total_with_new > self.budget.total_amount:
            self.add_error(
                "limit_value",
                f"Total category limits ({total_with_new}) cannot exceed "
                f"budget total ({self.budget.total_amount})."
            )

        if total_with_new > available_income:
            self.add_error(
                "limit_value",
                f"Total category limits ({total_with_new}) cannot exceed "
                f"available income ({available_income}) for this period."
            )

        return cleaned_data
