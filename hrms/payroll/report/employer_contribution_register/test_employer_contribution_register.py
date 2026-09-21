# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import nowdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates
from hrms.payroll.doctype.payroll_entry.test_payroll_entry import make_payroll_entry
from hrms.payroll.doctype.salary_slip.test_salary_slip import (
	create_account,
	make_deduction_salary_component,
	make_earning_salary_component,
)
from hrms.payroll.doctype.salary_structure.test_salary_structure import (
	create_salary_structure_assignment,
	make_salary_structure,
)
from hrms.payroll.report.employer_contribution_register.employer_contribution_register import execute
from hrms.tests.test_utils import create_department
from hrms.tests.utils import HRMSTestSuite

EMPLOYER_PF = "Test Register Employer PF"
EMPLOYER_NPS = "Test Register Employer NPS"
EMPLOYEE_PF = "Test Register Employee PF"


class TestEmployerContributionRegister(HRMSTestSuite):
	def setUp(self):
		# create_account() returns None while creating, so the payroll accounts must exist
		# before the component helpers link them
		create_account("Salary", "_Test Company", "Indirect Expenses - _TC")
		create_account("Salary Deductions", "_Test Company", "Current Liabilities - _TC")
		make_earning_salary_component(setup=True, company_list=["_Test Company"])
		make_deduction_salary_component(setup=True, test_tax=False, company_list=["_Test Company"])

		frappe.db.set_value("Company", "_Test Company", "default_holiday_list", "_Test Holiday List")
		frappe.db.set_single_value("Payroll Settings", "email_salary_slip_to_employee", 0)
		frappe.db.set_single_value(
			"Payroll Settings", "process_payroll_accounting_entry_based_on_employee", 0
		)
		self.setup_payroll_payable_account()
		self.setup_components()

	def setup_payroll_payable_account(self):
		create_account("_Test Payroll Payable", "_Test Company", "Current Liabilities - _TC", "Payable")
		frappe.db.set_value("Account", "_Test Payroll Payable - _TC", "account_type", "Payable")
		frappe.db.set_value(
			"Company", "_Test Company", "default_payroll_payable_account", "_Test Payroll Payable - _TC"
		)

	def setup_components(self):
		create_account("Test Register EC Expense", "_Test Company", "Indirect Expenses - _TC")
		create_account("Test Register EC Payable", "_Test Company", "Current Liabilities - _TC")
		self.liability_account = "Test Register EC Payable - _TC"

		for component in (EMPLOYEE_PF, EMPLOYER_PF, EMPLOYER_NPS):
			if frappe.db.exists("Salary Component", component):
				frappe.delete_doc("Salary Component", component, force=True)

		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": EMPLOYEE_PF,
				"salary_component_abbr": "TREEPF",
				"type": "Deduction",
				"accounts": [{"company": "_Test Company", "account": "Salary Deductions - _TC"}],
			}
		).insert()

		for component, abbr, employee_share_component in (
			(EMPLOYER_PF, "TREPF", EMPLOYEE_PF),
			(EMPLOYER_NPS, "TRENPS", None),
		):
			frappe.get_doc(
				{
					"doctype": "Salary Component",
					"salary_component": component,
					"salary_component_abbr": abbr,
					"type": "Employer Contribution",
					"employee_share_component": employee_share_component,
					"accounts": [
						{
							"company": "_Test Company",
							"account": "Test Register EC Expense - _TC",
							"liability_account": self.liability_account,
						}
					],
				}
			).insert()

	def run_payroll(self):
		company = frappe.get_doc("Company", "_Test Company")
		department = create_department("EC Register Test")
		emp1 = make_employee("ec_register1@payroll.com", company=company.name, department=department)
		emp2 = make_employee("ec_register2@payroll.com", company=company.name, department=department)

		deductions = [
			*make_deduction_salary_component(test_tax=False),
			{"salary_component": EMPLOYEE_PF, "abbr": "TREEPF", "amount": 1800},
		]
		structure = make_salary_structure(
			"Test Salary Structure EC Register",
			"Monthly",
			emp1,
			company=company.name,
			currency=company.default_currency,
			deductions=deductions,
			other_details={
				"employer_contributions": [
					{"salary_component": EMPLOYER_PF, "abbr": "TREPF", "amount": 5000},
					{"salary_component": EMPLOYER_NPS, "abbr": "TRENPS", "amount": 2000},
				]
			},
		)
		create_salary_structure_assignment(
			emp2, structure.name, company=company.name, currency=company.default_currency
		)

		dates = get_start_end_dates("Monthly", nowdate())
		payroll_entry = make_payroll_entry(
			start_date=dates.start_date,
			end_date=dates.end_date,
			payable_account=company.default_payroll_payable_account,
			currency=company.default_currency,
			company=company.name,
			cost_center="Main - _TC",
			department=department,
		)
		filters = frappe._dict(
			company=company.name,
			from_date=dates.start_date,
			to_date=dates.end_date,
			currency=company.default_currency,
			payroll_entry=payroll_entry.name,
			docstatus="Submitted",
			show_employee_share=1,
		)
		return payroll_entry, filters

	def test_employee_view_matches_slip_rows(self):
		payroll_entry, filters = self.run_payroll()
		columns, data, _message, chart, summary = execute(filters)

		labels = [c["label"] for c in columns]
		self.assertIn(EMPLOYER_PF, labels)
		self.assertIn(EMPLOYER_NPS, labels)
		self.assertIn(f"{EMPLOYER_PF} (Employee Share)", labels)
		self.assertNotIn(f"{EMPLOYER_NPS} (Employee Share)", labels)

		self.assertEqual(len(data), 2)
		for row in data:
			slip = frappe.get_doc("Salary Slip", row["salary_slip_id"])
			self.assertEqual(slip.payroll_entry, payroll_entry.name)

			employer = {d.salary_component: d.amount for d in slip.employer_contributions}
			self.assertEqual(row["test_register_employer_pf"], employer[EMPLOYER_PF])
			self.assertEqual(row["test_register_employer_nps"], employer[EMPLOYER_NPS])
			self.assertEqual(row["total_employer_contribution"], 7000)

			employee_pf = next(d.amount for d in slip.deductions if d.salary_component == EMPLOYEE_PF)
			self.assertEqual(row["test_register_employer_pf_employee_share"], employee_pf)
			self.assertEqual(row["total_employee_share"], employee_pf)
			self.assertEqual(row["total_remittance"], 7000 + employee_pf)

		self.assertEqual(chart["data"]["labels"], [EMPLOYER_NPS, EMPLOYER_PF])
		self.assertEqual(chart["data"]["datasets"][0]["values"], [4000, 10000])
		self.assertEqual(chart["data"]["datasets"][1]["values"], [0, 3600])

		# the register reconciles with the Employer Contribution Journal Entry of the Payroll Entry
		journal_entry = frappe.db.get_value(
			"Journal Entry Account",
			{"account": self.liability_account, "reference_name": payroll_entry.name, "docstatus": 1},
			"parent",
		)
		self.assertTrue(journal_entry)
		total_credit = frappe.db.get_value("Journal Entry", journal_entry, "total_credit")
		employer_total = next(s["value"] for s in summary if s["label"] == "Total Employer Contribution")
		self.assertEqual(employer_total, total_credit)
		self.assertEqual(employer_total, 14000)

	def test_component_view(self):
		_payroll_entry, filters = self.run_payroll()
		filters.group_by = "Salary Component"
		_columns, data, _message, _chart, summary = execute(filters)

		rows = {d["salary_component"]: d for d in data}
		self.assertEqual(set(rows), {EMPLOYER_PF, EMPLOYER_NPS})

		self.assertEqual(rows[EMPLOYER_PF]["employees"], 2)
		self.assertEqual(rows[EMPLOYER_PF]["employer_amount"], 10000)
		self.assertEqual(rows[EMPLOYER_PF]["employee_share_component"], EMPLOYEE_PF)
		self.assertEqual(rows[EMPLOYER_PF]["employee_share"], 3600)
		self.assertEqual(rows[EMPLOYER_PF]["total"], 13600)

		self.assertEqual(rows[EMPLOYER_NPS]["employees"], 2)
		self.assertEqual(rows[EMPLOYER_NPS]["employer_amount"], 4000)
		self.assertIsNone(rows[EMPLOYER_NPS]["employee_share_component"])
		self.assertEqual(rows[EMPLOYER_NPS]["employee_share"], 0)
		self.assertEqual(rows[EMPLOYER_NPS]["total"], 4000)

		values = {s["label"]: s["value"] for s in summary}
		self.assertEqual(values["Total Employer Contribution"], 14000)
		self.assertEqual(values["Total Employee Share"], 3600)
		self.assertEqual(values["Total Remittance"], 17600)
		self.assertEqual(values["Employees"], 2)

	def test_employee_share_hidden_by_default(self):
		_payroll_entry, filters = self.run_payroll()
		filters.show_employee_share = 0
		columns, data, _message, chart, summary = execute(filters)

		fieldnames = [c["fieldname"] for c in columns]
		self.assertNotIn("total_employee_share", fieldnames)
		self.assertNotIn("total_remittance", fieldnames)
		self.assertNotIn("test_register_employer_pf_employee_share", fieldnames)
		self.assertEqual(len(chart["data"]["datasets"]), 1)
		self.assertEqual([s["label"] for s in summary], ["Total Employer Contribution", "Employees"])
		self.assertEqual(len(data), 2)
