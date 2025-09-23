from django import forms
from .models import Category, Income, Expense, RecurringIncome, RecurringExpense
from django.utils import timezone

class BaseFinanceForm(forms.ModelForm):
    # Base form for Income and Expense to avoid duplication

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make all fields required except PK and end_date
        for field in self.fields:
            if field not in [self._meta.model._meta.pk.name, "end_date"]:
                self.fields[field].required = True

        # Handle category dropdown
        if 'category' in self.fields:
            model = self._meta.model
            # Keep the current choices if already set in child form (like ExpenseForm)
            if not getattr(self.fields['category'], '_custom_choices', False):
                self.fields['category'].choices = model.CATEGORY_CHOICES

        # Handle frequency dropdown
        if 'frequency' in self.fields:
            model = self._meta.model
            self.fields['frequency'].choices = model.FREQUENCY_CHOICES

class IncomeForm(BaseFinanceForm):
    class Meta:
        model = Income
        fields = ['source', 'amount', 'date', 'category']
        widgets = {
            'source': forms.TextInput(attrs={'placeholder': 'Enter source', 'class': 'input-field'}),
            'date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().date()}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': 'Enter amount'}),
        }

        
class ExpenseForm(BaseFinanceForm):
    class Meta:
        model = Expense
        fields = ['name', 'amount', 'date', 'category']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter name', 'class': 'input-field'}),
            'date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().date()}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': 'Enter amount'}),
            'category': forms.Select(attrs={'id': 'id_category'}),  # ensure consistent ID for JS if needed
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Define Auto-predict option
        auto_choice = ('Auto-predict', 'Auto-predict')

        # 2. Copy existing CATEGORY_CHOICES from Expense model
        original_choices = list(Expense.CATEGORY_CHOICES)

        # 3. Remove any existing Auto-predict to avoid duplicates
        original_choices = [c for c in original_choices if c[0] != 'Auto-predict']

        # 4. Prepend Auto-predict to the choices
        self.fields['category'].choices = [auto_choice] + original_choices

        # 5. Set default selected option to Auto-predict
        self.fields['category'].initial = 'Auto-predict'
        
class RecurringIncomeForm(BaseFinanceForm):
    class Meta:
        model = RecurringIncome
        fields = ['source', 'amount', 'frequency', 'category', 'start_date', 'end_date']
        widgets = {
            'source': forms.TextInput(attrs={'placeholder': 'Enter source', 'class': 'input-field'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': 'Enter amount'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().date()}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'end_date': 'End Date (optional)',
        }
        
class RecurringExpenseForm(BaseFinanceForm):
    class Meta:
        model = RecurringExpense
        fields = ['name', 'amount', 'frequency', 'category', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter name', 'class': 'input-field'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': 'Enter amount'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'value': timezone.now().date()}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'end_date': 'End Date (optional)',
        }
        
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'type']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter category name', 'class': 'input-field'}),
            'type': forms.Select(attrs={'class': 'select-field'}),
        }