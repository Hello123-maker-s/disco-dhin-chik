# budget/models.py
from django.db import models
from django.conf import settings
from finance.models import Expense

class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets")
    name = models.CharField(max_length=100)
    total_amount = models.DecimalField(max_digits=21, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    is_zero_based = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def total_spent(self):
        expenses = Expense.objects.filter(user=self.user, date__range=[self.start_date, self.end_date])
        return sum(exp.amount for exp in expenses)

    def remaining(self):
        return self.total_amount - self.total_spent()


class BudgetCategory(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="categories")
    category = models.CharField(max_length=50, choices=Expense.CATEGORY_CHOICES)
    limit = models.DecimalField(max_digits=21, decimal_places=2)

    def __str__(self):
        return f"{self.category} ({self.budget.name})"

    def spent(self):
        expenses = Expense.objects.filter(user=self.budget.user, category=self.category, date__range=[self.budget.start_date, self.budget.end_date])
        return sum(exp.amount for exp in expenses)

    def remaining(self):
        return self.limit - self.spent()
