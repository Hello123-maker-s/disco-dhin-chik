from django import forms
from .models import SavingsGoal, SavingsDeposit, AutoSavingsRule


class SavingsGoalForm(forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = ["name", "target_amount", "deadline", "priority"]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "target_amount": forms.NumberInput(attrs={"placeholder": "Enter Target Amount", "class": "form-input"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'priority' in self.fields:
            self.fields['priority'].choices = SavingsGoal.PRIORITY_CHOICES


class SavingsDepositForm(forms.ModelForm):
    class Meta:
        model = SavingsDeposit
        fields = ["goal", "amount"]
        widgets = {
            "amount": forms.NumberInput(attrs={"placeholder": "Enter Deposit Amount", "class": "form-input"}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # pass request.user from view
        super().__init__(*args, **kwargs)
        if user:
            self.fields['goal'].queryset = SavingsGoal.objects.filter(user=user)  # user isolation


class AutoSavingsRunForm(forms.ModelForm):  # fixed to ModelForm
    class Meta:
        model = AutoSavingsRule
        fields = ["goal", "percentage"]
        widgets = {
            "percentage": forms.NumberInput(attrs={"placeholder": "Enter Percentage", "class": "form-input"}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['goal'].queryset = SavingsGoal.objects.filter(user=user)  # user isolation


class AutoSavingsRuleForm(forms.ModelForm):
    class Meta:
        model = AutoSavingsRule
        fields = ["goal", "percentage", "frequency"]
        widgets = {
            "percentage": forms.NumberInput(attrs={"placeholder": "Enter Percentage", "class": "form-input"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['goal'].queryset = SavingsGoal.objects.filter(user=user)  # user isolation
            self.fields['frequency'].choices = AutoSavingsRule.FREQUENCY_CHOICES

