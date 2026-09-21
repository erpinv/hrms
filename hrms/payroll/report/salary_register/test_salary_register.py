# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.salary_slip.test_salary_slip import make_payroll_period
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
from hrms.payroll.doctype.salary_structure.test_salary_structure import make_salary_structure
from hrms.payroll.report.salary_register.salary_register import execute
from hrms.tests.utils import HRMSTestSuite


class TestSalaryRegister(HRMSTestSuite):
	EMPLOYER_COMPONENT = "Test Register Employer PF"
	EMPLOYER_AMOUNT = 6000

	def setUp(self):
		make_payroll_period(company="_Test Company")
		frappe.db.set_single_value("Payroll Settings", "email_salary_slip_to_employee", 0)
		frappe.flags.pop("via_payroll_entry", None)

		if frappe.db.exists("Salary Component", self.EMPLOYER_COMPONENT):
			frappe.delete_doc("Salary Component", self.EMPLOYER_COMPONENT, force=True)
		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": self.EMPLOYER_COMPONENT,
				"salary_component_abbr": "TREPF",
				"type": "Employer Contribution",
			}
		).insert()

	def make_submitted_slip(self, email):
		employee = make_employee(email, company="_Test Company")
		structure = make_salary_structure(
			"Salary Structure Register EC",
			"Monthly",
			employee=employee,
			company="_Test Company",
			currency="INR",
			other_details={
				"employer_contributions": [
					{
						"salary_component": self.EMPLOYER_COMPONENT,
						"abbr": "TREPF",
						"amount": self.EMPLOYER_AMOUNT,
					}
				]
			},
		)
		slip = make_salary_slip(structure.name, employee=employee)
		slip.submit()
		return slip

	def get_report_row(self, slip):
		columns, data = execute(
			frappe._dict(
				company="_Test Company",
				from_date=slip.start_date,
				to_date=slip.end_date,
				currency="INR",
				docstatus="Submitted",
				employee=slip.employee,
			)
		)
		rows = [d for d in data if d["salary_slip_id"] == slip.name]
		self.assertEqual(len(rows), 1)
		return columns, rows[0]

	def test_employer_contribution_rows_do_not_break_report(self):
		slip = self.make_submitted_slip("register_ec@salary.com")
		self.assertEqual(len(slip.employer_contributions), 1)

		columns, row = self.get_report_row(slip)

		labels = [c["label"] for c in columns]
		fieldnames = [c["fieldname"] for c in columns]
		self.assertNotIn(self.EMPLOYER_COMPONENT, labels)
		self.assertNotIn(frappe.scrub(self.EMPLOYER_COMPONENT), fieldnames)
		self.assertNotIn(frappe.scrub(self.EMPLOYER_COMPONENT), row)

		# earnings and deductions from the structure are still reported
		self.assertIn("Basic Salary", labels)
		self.assertIn("Professional Tax", labels)

	def test_totals_exclude_employer_contributions(self):
		slip = self.make_submitted_slip("register_ec_totals@salary.com")
		_columns, row = self.get_report_row(slip)

		self.assertEqual(flt(row["gross_pay"], 2), flt(slip.gross_pay, 2))
		# total_loan_repayment only exists with the lending app installed
		self.assertEqual(
			flt(row["total_deduction"], 2),
			flt(slip.total_deduction, 2) + flt(slip.get("total_loan_repayment"), 2),
		)
		self.assertEqual(flt(row["net_pay"], 2), flt(slip.net_pay, 2))
