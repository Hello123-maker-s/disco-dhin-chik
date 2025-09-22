from django import forms
from .models import Category, Income, Expense, RecurringIncome, RecurringExpense
from django.utils import timezone

class BaseFinanceForm(forms.ModelForm):
    #Base form for Income and Expense to avoid duplication

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make all fields required
        for field in self.fields:
            if field not in [self._meta.model._meta.pk.name, "end_date"]:
                self.fields[field].required = True

        # Handle category dropdown (remove "---------" and default to first)
        if 'category' in self.fields:
            model = self._meta.model
            self.fields['category'].choices = model.CATEGORY_CHOICES
            
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
        }
        
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