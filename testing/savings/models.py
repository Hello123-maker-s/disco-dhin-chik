from django.db import models
from django.utils import timezone
from django.conf import settings
from decimal import Decimal


class SurplusTracker(models.Model):
    """
    Tracks the accumulated surplus for a user (excluding current month).
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_surplus = models.DecimalField(max_digits=21, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.user.username} Surplus Tracker"


class SavingsGoal(models.Model):
    """
    Represents a user's savings goal.
    """
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="savings_goals")
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=21, decimal_places=2)
    current_amount = models.DecimalField(max_digits=21, decimal_places=2, default=0)
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="Low")

    def progress(self) -> float:
        if self.target_amount == 0:
            return 0.0
        return round((self.current_amount / self.target_amount) * 100, 2)

    def remaining_amount(self) -> Decimal:
        return max(self.target_amount - self.current_amount, Decimal(0))

    def is_completed(self) -> bool:
        return self.current_amount >= self.target_amount

    def __str__(self):
        return f"{self.name} ({self.current_amount}/{self.target_amount})"


class SavingsDeposit(models.Model):
    """
    Represents a deposit applied to a goal.
    Automatically updates the goal's current_amount.
    """
    goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, null=True, blank=True, related_name="deposits")
    amount = models.DecimalField(max_digits=21, decimal_places=2)
    date = models.DateField(default=timezone.now)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.goal:
            self.goal.current_amount = max(self.goal.current_amount + self.amount, Decimal(0))
            self.goal.save()
            SavingsGoalHistory.objects.create(
                goal=self.goal,
                action="Deposit" if self.amount >= 0 else "Withdraw",
                amount=self.amount
            )

    def __str__(self):
        action = "Deposit" if self.amount >= 0 else "Withdraw"
        return f"{action} {abs(self.amount)} → {self.goal.name if self.goal else 'No Goal'}"


class AutoSavingsRule(models.Model):
    """
    Defines automatic savings rules for a specific goal.
    """
    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('biannually', 'Biannually'),
        ('annually', 'Annually'),
    ]

    goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, related_name="rules")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage of income to allocate (e.g., 20 for 20%)")
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
    last_applied = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.percentage}% → {self.goal.name} ({self.frequency})"


class SavingsGoalHistory(models.Model):
    """
    Keeps a log of goal-related actions (deposits, withdrawals, activations, deletions).
    """
    goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, related_name="history")
    action = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=21, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.goal.name}: {self.action} ({self.amount})"
