from django.urls import path
from . import views

urlpatterns = [
    path("", views.savings_dashboard, name="savings_dashboard"),

    # Goals
    path("goal/form/", views.goal_form, name="add_goal"),
    path("goal/form/<int:id>/", views.goal_form, name="edit_goal"),
    path("delete-selected/", views.delete_selected_goals, name="delete_selected_goals"),
    path("delete-all/", views.delete_all_goals, name="delete_all_goals"),
    path("goal/delete/<int:id>/", views.delete_goal, name="delete_goal"),

    # Deposits
    path("deposit/form/", views.deposit_form, name="add_deposit"),
    path("deposit/form/<int:id>/", views.deposit_form, name="edit_deposit"),
    #path("deposit/delete/<int:id>/", views.delete_deposit, name="delete_deposit"),
    
    path("auto-savings/", views.manage_auto_savings, name="manage_auto_savings"),
    path("auto-savings/edit/<int:edit_id>/", views.manage_auto_savings, name="edit_auto_savings_rule"),
    path("auto-savings/delete/<int:delete_id>/", views.manage_auto_savings, name="delete_auto_savings_rule"),
]


""" from django.urls import path
from . import views

urlpatterns = [
    path('', views.savings_dashboard, name='savings_dashboard'),
    path('goals/', views.list_goals, name='list_goals'),
    path('goals/create/', views.create_goal, name='create_goal'),
    path('goals/<int:goal_id>/', views.goal_detail, name='goal_detail'),
    path('goals/<int:goal_id>/edit/', views.edit_goal, name='edit_goal'),
    path('goals/<int:goal_id>/delete/', views.delete_goal, name='delete_goal'),
    path('transactions/add/', views.add_transaction, name='add_transaction'),
    path('categories/', views.manage_categories, name='manage_categories'),
    path('accounts/', views.accounts, name='accounts'),
    path('autosave/', views.autosave_settings, name='autosave_settings'),
    path('autosave/apply/', views.apply_autosave_now, name='apply_autosave_now'),
]
 """


""" from django.urls import path
from . import views

urlpatterns = [
    path("new/", views.new_goal, name="new_goal"),
    path("tracker/", views.goal_tracker, name="goal_tracker"),
    path("archive/", views.goal_archive, name="goal_archive"),
    path("charts/", views.savings_charts, name="savings_charts"),
    path("contribute/<int:goal_id>/", views.add_contribution, name="add_contribution"),
]
 """