from django.db import models 
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User


class SavingsGoal(models.Model):
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
        
    def progress(self):
        if self.target_amount == 0:
            return 0
        return round((self.current_amount / self.target_amount) * 100, 2)
    
    def remaining_amount(self):
        return max(self.target_amount - self.current_amount, 0)

    def is_completed(self):
        return self.current_amount >= self.target_amount

    def __str__(self):
        return f"{self.name} ({self.current_amount}/{self.target_amount})"


class SavingsDeposit(models.Model):
    goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, null=True, blank=True, related_name="deposits")
    amount = models.DecimalField(max_digits=21, decimal_places=2)
    date = models.DateField(default=timezone.now)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.goal:
            # Allow both deposits (+) and withdrawals (-)
            self.goal.current_amount = max(self.goal.current_amount + self.amount, 0)
            self.goal.save()

    def __str__(self):
        return f"{'Deposit' if self.amount >= 0 else 'Withdraw'} {abs(self.amount)} to {self.goal.name}"


class AutoSavingsRule(models.Model):
    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('biannually', 'Biannually'),
        ('annually', 'Annually'),
    ]
    goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, related_name="rules")
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Enter percentage (e.g. 20 for 20%)"
    )
    frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, default='monthly'
    )
    last_applied = models.DateField(null=True, blank=True)  # To avoid duplicate allocations

    def __str__(self):
        return f"{self.percentage}% → {self.goal.name} ({self.frequency})"

class SurplusTracker(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="surplus_tracker")
    last_surplus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)



 
