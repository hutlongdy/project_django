from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .models import (
    AcademicYear,
    AttendanceRecord,
    ClassSubject,
    Enrollment,
    Grade,
    Guardian,
    SchoolClass,
    Student,
    Subject,
    Teacher,
    UserProfile,
)


class SchoolRecordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
        )
        cls.other_year = AcademicYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        cls.school_class = SchoolClass.objects.create(
            name="Grade 1 A", grade_level=1, academic_year=cls.year
        )
        cls.teacher = Teacher.objects.create(
            first_name="Taylor", last_name="Teacher", email="taylor@example.com"
        )
        cls.school_class.homeroom_teacher = cls.teacher
        cls.school_class.save(update_fields=["homeroom_teacher"])
        cls.student = Student.objects.create(
            student_number="S-001",
            first_name="Sam",
            last_name="Lee",
            date_of_birth=date(2018, 1, 1),
            guardian_name="Parent Lee",
            guardian_phone="555-0100",
        )
        cls.enrollment = Enrollment.objects.create(
            student=cls.student,
            school_class=cls.school_class,
            academic_year=cls.year,
        )
        subject = Subject.objects.create(code="MATH", name="Mathematics")
        cls.class_subject = ClassSubject.objects.create(
            school_class=cls.school_class, subject=subject, teacher=cls.teacher
        )

    def test_student_cannot_have_two_enrollments_in_one_year(self):
        duplicate = Enrollment(
            student=self.student,
            school_class=self.school_class,
            academic_year=self.year,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_enrollment_year_must_match_class_year(self):
        enrollment = Enrollment(
            student=self.student,
            school_class=self.school_class,
            academic_year=self.other_year,
        )
        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_grade_must_belong_to_enrolled_class_and_fit_maximum(self):
        grade = Grade(
            enrollment=self.enrollment,
            class_subject=self.class_subject,
            assessment="Midterm",
            score=Decimal("101.00"),
            maximum_score=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError):
            grade.full_clean()

    def test_dashboard_requires_staff_login(self):
        response = self.client.get("/")

        self.assertRedirects(
            response, "/accounts/login/?next=/", fetch_redirect_response=False
        )

    def test_vercel_host_is_allowed(self):
        response = self.client.get("/", HTTP_HOST="bbu-django.vercel.app")

        self.assertEqual(response.status_code, 302)

    def test_admin_login_page_is_available_to_anonymous_users(self):
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)

    def test_login_password_field_has_accessible_show_hide_control(self):
        response = self.client.get("/accounts/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-password-toggle')
        self.assertContains(response, 'aria-controls="id_password"')
        self.assertContains(response, "my_app/password-toggle.js")

    def test_admin_user_form_includes_school_role_selection(self):
        admin_user = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="test-password"
        )
        self.client.force_login(admin_user)

        response = self.client.get("/admin/auth/user/add/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Office staff")
        self.assertContains(response, "Parent/guardian")

    def test_staff_dashboard_displays_school_summary(self):
        user = get_user_model().objects.create_user(
            username="schooladmin", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, "School management")
        self.assertContains(response, "Active students")
        self.assertContains(response, "2026-2027")

    def test_health_endpoint_is_available(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_office_staff_profile_grants_staff_dashboard_and_admin_access(self):
        user = get_user_model().objects.create_user(
            username="office", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.client.force_login(user)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        UserProfile.objects.get(user=user).delete()
        user.refresh_from_db()
        self.assertFalse(user.is_staff)

    def test_teacher_can_record_attendance_and_grades_for_assigned_class(self):
        user = get_user_model().objects.create_user(
            username="teacher", password="test-password"
        )
        UserProfile.objects.create(
            user=user, role=UserProfile.Role.TEACHER, teacher=self.teacher
        )
        self.client.force_login(user)

        attendance_response = self.client.post(
            "/attendance/",
            {
                "enrollment": self.enrollment.id,
                "date": "2026-10-12",
                "status": AttendanceRecord.Status.PRESENT,
                "note": "",
            },
        )
        grade_response = self.client.post(
            "/grades/",
            {
                "enrollment": self.enrollment.id,
                "class_subject": self.class_subject.id,
                "assessment": "Midterm",
                "score": "85",
                "maximum_score": "100",
                "assessed_on": "2026-10-12",
            },
        )

        self.assertRedirects(attendance_response, "/attendance/")
        self.assertRedirects(grade_response, "/grades/")
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        self.assertEqual(Grade.objects.count(), 1)

    def test_teacher_cannot_record_attendance_for_an_unassigned_class(self):
        other_class = SchoolClass.objects.create(
            name="Grade 2 A", grade_level=2, academic_year=self.year
        )
        other_student = Student.objects.create(
            student_number="S-OTHER",
            first_name="Other",
            last_name="Student",
            date_of_birth=date(2017, 1, 1),
            guardian_name="Other Parent",
            guardian_phone="555-0101",
        )
        other_enrollment = Enrollment.objects.create(
            student=other_student,
            school_class=other_class,
            academic_year=self.year,
        )
        user = get_user_model().objects.create_user(
            username="limitedteacher", password="test-password"
        )
        UserProfile.objects.create(
            user=user, role=UserProfile.Role.TEACHER, teacher=self.teacher
        )
        self.client.force_login(user)

        response = self.client.post(
            "/attendance/",
            {
                "enrollment": other_enrollment.id,
                "date": "2026-10-12",
                "status": AttendanceRecord.Status.PRESENT,
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_staff_can_scan_check_in_and_check_out(self):
        user = get_user_model().objects.create_user(
            username="attendance-staff", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)
        self.client.force_login(user)

        second_student = Student.objects.create(
            student_number="S-SECOND",
            first_name="Jordan",
            last_name="Park",
            date_of_birth=date(2017, 2, 1),
            guardian_name="Parent Park",
            guardian_phone="555-0104",
        )
        Enrollment.objects.create(
            student=second_student,
            school_class=self.school_class,
            academic_year=self.year,
        )

        check_in = self.client.post(
            "/attendance/scan/",
            {"student_number": self.student.student_number, "action": "auto"},
        )
        second_check_in = self.client.post(
            "/attendance/scan/",
            {"student_number": second_student.student_number, "action": "auto"},
        )
        check_out = self.client.post(
            "/attendance/scan/",
            {"student_number": self.student.student_number, "action": "auto"},
        )
        already_checked_out = self.client.post(
            "/attendance/scan/",
            {"student_number": self.student.student_number, "action": "auto"},
        )

        self.assertEqual(check_in.status_code, 200)
        self.assertEqual(second_check_in.status_code, 200)
        self.assertEqual(check_out.status_code, 200)
        self.assertEqual(already_checked_out.status_code, 409)
        self.assertEqual(check_in.json()["action"], "check_in")
        self.assertEqual(check_in.json()["next_action"], "check_out")
        self.assertEqual(second_check_in.json()["action"], "check_in")
        self.assertEqual(check_out.json()["action"], "check_out")
        self.assertEqual(check_out.json()["next_action"], "check_in")
        record = AttendanceRecord.objects.get(enrollment=self.enrollment)
        self.assertEqual(record.status, AttendanceRecord.Status.PRESENT)
        self.assertIsNotNone(record.checked_in_at)
        self.assertIsNotNone(record.checked_out_at)

    @override_settings(TIME_ZONE="Asia/Phnom_Penh")
    def test_scan_returns_current_local_times_for_live_attendance_table(self):
        user = get_user_model().objects.create_user(
            username="attendance-time-staff", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)
        self.client.force_login(user)

        check_in_time = datetime(
            2026, 11, 18, 14, 15, 30, tzinfo=datetime_timezone.utc
        )
        with (
            patch("my_app.views.timezone.localdate", return_value=date(2026, 11, 18)),
            patch("my_app.views.timezone.now", return_value=check_in_time),
        ):
            check_in = self.client.post(
                "/attendance/scan/",
                {"student_number": self.student.student_number, "action": "check_in"},
            )

        check_out_time = datetime(
            2026, 11, 18, 15, 22, 5, tzinfo=datetime_timezone.utc
        )
        with (
            patch("my_app.views.timezone.localdate", return_value=date(2026, 11, 18)),
            patch("my_app.views.timezone.now", return_value=check_out_time),
        ):
            check_out = self.client.post(
                "/attendance/scan/",
                {"student_number": self.student.student_number, "action": "check_out"},
            )

        self.assertEqual(check_in.json()["time"], "21:15:30")
        self.assertEqual(check_in.json()["checked_in_time"], "21:15")
        self.assertEqual(check_in.json()["checked_out_time"], "")
        self.assertEqual(check_in.json()["date"], "2026-11-18")
        self.assertEqual(check_in.json()["status"], "Present")
        self.assertEqual(check_in.json()["enrollment_id"], self.enrollment.pk)
        self.assertEqual(check_out.json()["time"], "22:22:05")
        self.assertEqual(check_out.json()["checked_in_time"], "21:15")
        self.assertEqual(check_out.json()["checked_out_time"], "22:22")

    def test_scan_rejects_checkout_before_checkin_and_duplicate_checkin(self):
        user = get_user_model().objects.create_user(
            username="attendance-office", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)
        self.client.force_login(user)
        scan = {
            "student_number": self.student.student_number,
            "action": "check_out",
        }

        early_checkout = self.client.post("/attendance/scan/", scan)
        scan["action"] = "check_in"
        check_in = self.client.post("/attendance/scan/", scan)
        duplicate_check_in = self.client.post("/attendance/scan/", scan)
        scan["action"] = "check_out"
        check_out = self.client.post("/attendance/scan/", scan)
        duplicate_check_out = self.client.post("/attendance/scan/", scan)

        self.assertEqual(early_checkout.status_code, 409)
        self.assertEqual(check_in.status_code, 200)
        self.assertEqual(duplicate_check_in.status_code, 409)
        self.assertEqual(check_out.status_code, 200)
        self.assertEqual(duplicate_check_out.status_code, 409)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_teacher_cannot_scan_student_outside_assigned_class(self):
        other_class = SchoolClass.objects.create(
            name="Grade 2 B", grade_level=2, academic_year=self.year
        )
        other_student = Student.objects.create(
            student_number="S-OUTSIDE",
            first_name="Outside",
            last_name="Student",
            date_of_birth=date(2017, 1, 1),
            guardian_name="Parent",
            guardian_phone="555-0103",
        )
        Enrollment.objects.create(
            student=other_student,
            school_class=other_class,
            academic_year=self.year,
        )
        user = get_user_model().objects.create_user(
            username="scan-limited-teacher", password="test-password"
        )
        UserProfile.objects.create(
            user=user, role=UserProfile.Role.TEACHER, teacher=self.teacher
        )
        self.client.force_login(user)

        response = self.client.post(
            "/attendance/scan/",
            {"student_number": other_student.student_number, "action": "check_in"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_staff_can_view_active_student_qr_code(self):
        user = get_user_model().objects.create_user(
            username="qr-office", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)
        self.client.force_login(user)

        response = self.client.get(f"/students/{self.student.id}/qr.svg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", response.content)

    def test_staff_can_open_attendance_scanner_and_printable_qr_list(self):
        user = get_user_model().objects.create_user(
            username="scanner-office", password="test-password"
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.OFFICE_STAFF)
        self.client.force_login(user)
        AttendanceRecord.objects.create(
            enrollment=self.enrollment,
            date=date(2026, 11, 18),
            status=AttendanceRecord.Status.PRESENT,
        )

        attendance_page = self.client.get("/attendance/")
        student_page = self.client.get("/students/")

        self.assertContains(attendance_page, "Scan student check-in or check-out")
        self.assertContains(attendance_page, "Ready to check in.")
        self.assertContains(attendance_page, "data-scan-toggle")
        self.assertNotContains(attendance_page, "data-scan-action")
        self.assertNotContains(attendance_page, "data-camera-start")
        self.assertContains(
            attendance_page, "my_app/attendance-scanner.js?v=20261118-2"
        )
        self.assertContains(attendance_page, "data-attendance-records")
        self.assertContains(attendance_page, "data-attendance-field")
        self.assertContains(attendance_page, "my_app/jsqr-1.4.0.js")
        self.assertContains(student_page, "Print QR cards")
        self.assertContains(student_page, f"QR code for {self.student.student_number}")

    def test_teacher_profile_requires_linked_teacher_record(self):
        user = get_user_model().objects.create_user(
            username="unlinkedteacher", password="test-password"
        )
        profile = UserProfile(user=user, role=UserProfile.Role.TEACHER)

        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_parent_only_sees_linked_students(self):
        guardian = Guardian.objects.create(
            first_name="Parent", last_name="Lee", phone="555-0100"
        )
        self.student.guardians.add(guardian)
        other_student = Student.objects.create(
            student_number="S-002",
            first_name="Other",
            last_name="Student",
            date_of_birth=date(2018, 2, 1),
            guardian_name="Other Parent",
            guardian_phone="555-0101",
        )
        user = get_user_model().objects.create_user(
            username="parent", password="test-password"
        )
        UserProfile.objects.create(
            user=user, role=UserProfile.Role.PARENT, guardian=guardian
        )
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, self.student.student_number)
        self.assertNotContains(response, other_student.student_number)

    def test_student_account_only_sees_its_own_dashboard(self):
        user = get_user_model().objects.create_user(
            username="student", password="test-password"
        )
        UserProfile.objects.create(
            user=user, role=UserProfile.Role.STUDENT, student=self.student
        )
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, self.student.student_number)
        self.assertContains(response, "Recent grades")

    def test_staff_can_admit_student_and_download_attendance_report(self):
        user = get_user_model().objects.create_user(
            username="registrar", password="test-password"
        )
        UserProfile.objects.create(
            user=user, role=UserProfile.Role.OFFICE_STAFF
        )
        self.client.force_login(user)

        response = self.client.post(
            "/students/add/",
            {
                "student_number": "S-NEW",
                "first_name": "New",
                "last_name": "Student",
                "date_of_birth": "2018-03-01",
                "guardian_name": "New Parent",
                "guardian_phone": "555-0102",
                "address": "",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, "/students/")
        self.assertTrue(Student.objects.filter(student_number="S-NEW").exists())
        report = self.client.get("/reports/attendance.csv")
        self.assertEqual(report.status_code, 200)
        self.assertIn("text/csv", report["Content-Type"])
