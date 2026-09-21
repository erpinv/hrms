# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt

import erpnext

DOCSTATUS = {"Draft": 0, "Submitted": 1, "Cancelled": 2}


def execute(filters=None):
	return EmployerContributionRegister(filters).run()


class EmployerContributionRegister:
	"""Employer contributions per slip, optionally paired with the employee's share of the same fund."""

	def __init__(self, filters):
		self.filters = frappe._dict(filters or {})
		self.company_currency = erpnext.get_company_currency(self.filters.company)
		self.currency = self.filters.currency or self.company_currency
		self.show_employee_share = cint(self.filters.show_employee_share)
		self.by_component = self.filters.group_by == "Salary Component"
		self.precision = frappe.get_precision("Salary Detail", "amount")

	def run(self):
		self.salary_slips = self.get_salary_slips()
		if not self.salary_slips:
			return [], []

		self.employer_amounts = self.get_amounts("employer_contributions", self.get_component_filter())
		self.components = sorted({c for amounts in self.employer_amounts.values() for c in amounts})
		if not self.components:
			return [], []

		# {employer component: deduction component carrying the employee's share}
		self.share_components = self.get_employee_share_components() if self.show_employee_share else {}
		self.share_amounts = (
			self.get_amounts("deductions", set(self.share_components.values()))
			if self.share_components
			else {}
		)
		self.totals = self.get_totals()

		if self.by_component:
			columns, data = self.get_component_columns(), self.get_component_data()
		else:
			columns, data = self.get_employee_columns(), self.get_employee_data()

		return columns, data, None, self.get_chart(), self.get_report_summary()

	# ---- employee view -------------------------------------------------

	def get_employee_columns(self):
		columns = [
			{
				"label": _("Salary Slip ID"),
				"fieldname": "salary_slip_id",
				"fieldtype": "Link",
				"options": "Salary Slip",
				"width": 150,
			},
			{
				"label": _("Employee"),
				"fieldname": "employee",
				"fieldtype": "Link",
				"options": "Employee",
				"width": 120,
			},
			{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 140},
			{
				"label": _("Department"),
				"fieldname": "department",
				"fieldtype": "Link",
				"options": "Department",
				"width": 120,
			},
			{
				"label": _("Branch"),
				"fieldname": "branch",
				"fieldtype": "Link",
				"options": "Branch",
				"width": 120,
			},
			{"label": _("Start Date"), "fieldname": "start_date", "fieldtype": "Date", "width": 100},
			{"label": _("End Date"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		]
		for component in self.components:
			columns.append(self.currency_column(component, frappe.scrub(component)))
		columns.append(
			self.currency_column(_("Total Employer Contribution"), "total_employer_contribution", 180)
		)

		if self.show_employee_share:
			for component in self.share_components:
				columns.append(
					self.currency_column(
						_("{0} (Employee Share)").format(component), self.share_fieldname(component), 160
					)
				)
			columns.append(self.currency_column(_("Total Employee Share"), "total_employee_share", 160))
			columns.append(self.currency_column(_("Total Remittance"), "total_remittance", 160))

		columns.append(self.hidden_currency_column())
		return columns

	def get_employee_data(self):
		data = []
		for slip in self.salary_slips:
			employer = self.employer_amounts.get(slip.name)
			if not employer:
				continue

			row = {
				"salary_slip_id": slip.name,
				"employee": slip.employee,
				"employee_name": slip.employee_name,
				"department": slip.department,
				"branch": slip.branch,
				"start_date": slip.start_date,
				"end_date": slip.end_date,
				"currency": self.currency,
			}
			for component in self.components:
				row[frappe.scrub(component)] = employer.get(component, 0)
			row["total_employer_contribution"] = self.round(sum(employer.values()))

			if self.show_employee_share:
				shares = self.share_amounts.get(slip.name, {})
				for component, deduction_component in self.share_components.items():
					row[self.share_fieldname(component)] = shares.get(deduction_component, 0)
				row["total_employee_share"] = self.round(sum(shares.values()))
				row["total_remittance"] = self.round(
					row["total_employer_contribution"] + row["total_employee_share"]
				)

			data.append(row)

		return data

	# ---- component view ------------------------------------------------

	def get_component_columns(self):
		columns = [
			{
				"label": _("Salary Component"),
				"fieldname": "salary_component",
				"fieldtype": "Link",
				"options": "Salary Component",
				"width": 200,
			},
			{"label": _("Employees"), "fieldname": "employees", "fieldtype": "Int", "width": 100},
			self.currency_column(_("Employer Amount"), "employer_amount", 160),
		]
		if self.show_employee_share:
			columns.extend(
				[
					{
						"label": _("Employee Share Component"),
						"fieldname": "employee_share_component",
						"fieldtype": "Link",
						"options": "Salary Component",
						"width": 200,
					},
					self.currency_column(_("Employee Share"), "employee_share", 160),
					self.currency_column(_("Total"), "total", 160),
				]
			)
		columns.append(self.hidden_currency_column())
		return columns

	def get_component_data(self):
		data = []
		for component in self.components:
			employees = {
				slip.employee
				for slip in self.salary_slips
				if self.employer_amounts.get(slip.name, {}).get(component)
			}
			row = {
				"salary_component": component,
				"employees": len(employees),
				"employer_amount": self.totals["by_component"].get(component, 0),
				"currency": self.currency,
			}
			if self.show_employee_share:
				deduction_component = self.share_components.get(component)
				share = self.totals["by_share_component"].get(deduction_component, 0)
				row.update(
					{
						"employee_share_component": deduction_component,
						"employee_share": share,
						"total": self.round(row["employer_amount"] + share),
					}
				)
			data.append(row)

		return data

	# ---- summary & chart -----------------------------------------------

	def get_totals(self):
		by_component = {}
		employees = set()
		for slip in self.salary_slips:
			for component, amount in self.employer_amounts.get(slip.name, {}).items():
				by_component[component] = self.round(by_component.get(component, 0) + amount)
				employees.add(slip.employee)

		by_share_component = {}
		for amounts in self.share_amounts.values():
			for component, amount in amounts.items():
				by_share_component[component] = self.round(by_share_component.get(component, 0) + amount)

		employer = self.round(sum(by_component.values()))
		employee_share = self.round(sum(by_share_component.values()))
		return frappe._dict(
			by_component=by_component,
			by_share_component=by_share_component,
			employer=employer,
			employee_share=employee_share,
			remittance=self.round(employer + employee_share),
			employees=len(employees),
		)

	def get_report_summary(self):
		summary = [
			self.summary_card(_("Total Employer Contribution"), self.totals.employer, "Blue"),
			{"label": _("Employees"), "value": self.totals.employees, "datatype": "Int"},
		]
		if self.show_employee_share:
			summary.append(self.summary_card(_("Total Employee Share"), self.totals.employee_share, "Orange"))
			summary.append(self.summary_card(_("Total Remittance"), self.totals.remittance, "Green"))
		return summary

	def get_chart(self):
		datasets = [
			{
				"name": _("Employer Contribution"),
				"values": [self.totals.by_component.get(c, 0) for c in self.components],
			}
		]
		if self.show_employee_share:
			datasets.append(
				{
					"name": _("Employee Share"),
					"values": [
						self.totals.by_share_component.get(self.share_components.get(c), 0)
						for c in self.components
					],
				}
			)
		return {
			"data": {"labels": self.components, "datasets": datasets},
			"type": "bar",
			"fieldtype": "Currency",
			"options": {"currency": self.currency},
		}

	# ---- helpers ---------------------------------------------------------

	def summary_card(self, label, value, indicator):
		return {
			"label": label,
			"value": value,
			"datatype": "Currency",
			"currency": self.currency,
			"indicator": indicator,
		}

	def currency_column(self, label, fieldname, width=140):
		return {
			"label": label,
			"fieldname": fieldname,
			"fieldtype": "Currency",
			"options": "currency",
			"width": width,
		}

	def hidden_currency_column(self):
		return {
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		}

	@staticmethod
	def share_fieldname(component):
		return f"{frappe.scrub(component)}_employee_share"

	def round(self, amount):
		return flt(amount, self.precision)

	def convert(self, amount, exchange_rate):
		# same convention as Salary Register: report in company currency unless a foreign one is selected
		if self.currency == self.company_currency:
			return flt(amount) * flt(exchange_rate)
		return flt(amount)

	def get_component_filter(self):
		return {self.filters.salary_component} if self.filters.salary_component else None

	# ---- queries ---------------------------------------------------------

	def get_salary_slips(self):
		ss = frappe.qb.DocType("Salary Slip")
		query = (
			frappe.qb.from_(ss)
			.select(
				ss.name,
				ss.employee,
				ss.employee_name,
				ss.department,
				ss.branch,
				ss.start_date,
				ss.end_date,
				ss.exchange_rate,
			)
			.where(ss.company == self.filters.company)
			.orderby(ss.employee, ss.start_date)
		)
		if self.filters.docstatus:
			query = query.where(ss.docstatus == DOCSTATUS[self.filters.docstatus])
		if self.filters.from_date:
			query = query.where(ss.start_date >= self.filters.from_date)
		if self.filters.to_date:
			query = query.where(ss.end_date <= self.filters.to_date)
		if self.currency != self.company_currency:
			query = query.where(ss.currency == self.currency)
		for fieldname in ("payroll_entry", "department", "branch", "employee"):
			if self.filters.get(fieldname):
				query = query.where(ss[fieldname] == self.filters[fieldname])

		return query.run(as_dict=True)

	def get_amounts(self, parentfield, components=None):
		"""Returns {salary slip: {salary component: amount}} for non-zero rows of the given table."""
		sd = frappe.qb.DocType("Salary Detail")
		query = (
			frappe.qb.from_(sd)
			.select(sd.parent, sd.salary_component, sd.amount)
			.where(sd.parent.isin([slip.name for slip in self.salary_slips]))
			.where(sd.parentfield == parentfield)
			.where(sd.amount != 0)
		)
		if components:
			query = query.where(sd.salary_component.isin(list(components)))

		exchange_rates = {slip.name: slip.exchange_rate for slip in self.salary_slips}
		amounts = {}
		for d in query.run(as_dict=True):
			slip_amounts = amounts.setdefault(d.parent, {})
			slip_amounts[d.salary_component] = self.round(
				slip_amounts.get(d.salary_component, 0) + self.convert(d.amount, exchange_rates[d.parent])
			)
		return amounts

	def get_employee_share_components(self):
		return dict(
			frappe.get_all(
				"Salary Component",
				filters={"name": ["in", self.components], "employee_share_component": ["is", "set"]},
				fields=["name", "employee_share_component"],
				as_list=True,
			)
		)
