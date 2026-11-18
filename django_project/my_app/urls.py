from django.urls import path

from . import views


urlpatterns = [
    path("accounts/login/", views.login, name="login"),
    path("accounts/logout/", views.logout, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("students/", views.student_list, name="student-list"),
    path("students/add/", views.student_create, name="student-create"),
    path("students/<int:student_id>/edit/", views.student_update, name="student-update"),
    path("students/<int:student_id>/deactivate/", views.student_delete, name="student-delete"),
    path("students/<int:student_id>/qr.svg", views.student_qr_code, name="student-qr"),
    path("enrollments/", views.enrollment_list, name="enrollment-list"),
    path("enrollments/add/", views.enrollment_create, name="enrollment-create"),
    path("attendance/", views.attendance, name="attendance"),
    path("attendance/scan/", views.attendance_scan, name="attendance-scan"),
    path("grades/", views.grades, name="grades"),
    path("reports/", views.reports, name="reports"),
    path("reports/attendance.csv", views.attendance_csv, name="attendance-csv"),
    path("health/", views.health, name="health"),
]
