import frappe


def execute(filters=None):
	filters = filters or {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_data(filters):

	# =========================================================
	# FILTER VALUES
	# =========================================================

	values = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),

		"project": filters.get("project") or "",
		"project_like": "%" + (filters.get("project") or "") + "%",

		"customer_name": filters.get("customer_name") or "",
		"sales_order": filters.get("sales_order") or "",
		"sales_person": filters.get("sales_person") or "",
		"product_type": filters.get("product_type") or "",
		"region": filters.get("region") or "",

		"active_only": 1 if filters.get("active_only") else 0,
		"pending_only": 1 if filters.get("pending_only") else 0,

		"excluded_customer": "Central Ventilation Systems Co LLC",
	}

	# =========================================================
	# DATABASE QUERY
	#
	# NOTE: "Order Processing Request" has no region column of its
	# own. Region is looked up from the linked Project (matched on
	# opr.project = tabProject.name) since that is the only place
	# a "Region" field exists today.
	# =========================================================

	opr_rows = frappe.db.sql(
		"""
		SELECT
			opr.name AS opr_name,

			COALESCE(
				NULLIF(TRIM(opr.project), ''),
				'Project Not Specified'
			) AS project,

			COALESCE(
				NULLIF(TRIM(proj.region), ''),
				'Not Specified'
			) AS region,

			COALESCE(
				NULLIF(TRIM(opr.product_type1), ''),
				'Not Specified'
			) AS product_type,

			COALESCE(opr.total_sqm, 0)
				AS total_sqm,

			COALESCE(opr.total_no, 0)
				AS total_no,

			COALESCE(opr.total_straight_sqm, 0)
				AS total_straight_sqm,

			COALESCE(opr.total_straight_nos, 0)
				AS total_straight_nos,

			COALESCE(opr.total_fittings_sqm, 0)
				AS total_fittings_sqm,

			COALESCE(opr.total_fittings_nos, 0)
				AS total_fittings_nos,

			COALESCE(opr.total_sqm_produced, 0)
				AS total_sqm_produced,

			COALESCE(opr.total_nos_produced, 0)
				AS total_nos_produced,

			COALESCE(opr.remaining_sqm_production, 0)
				AS remaining_sqm_production,

			COALESCE(opr.remaining_nos_production, 0)
				AS remaining_nos_production,

			COALESCE(opr.total_sqm_delivered, 0)
				AS total_sqm_delivered,

			COALESCE(opr.total_nos_delivered, 0)
				AS total_nos_delivered,

			COALESCE(opr.remaining_sqm_delivery, 0)
				AS remaining_sqm_delivery,

			COALESCE(opr.remaining_nos_delivery, 0)
				AS remaining_nos_delivery,

			COALESCE(
				opr.remaining_produced_sqm_to_delivered,
				0
			) AS remaining_produced_sqm_to_delivered,

			COALESCE(
				opr.remaining_produced_no_to_delivered,
				0
			) AS remaining_produced_no_to_delivered,

			COALESCE(opr.remaining_value, 0)
				AS remaining_value

		FROM `tabOrder Processing Request` opr

		LEFT JOIN `tabProject` proj
			ON proj.name = opr.project

		WHERE opr.docstatus < 2

			/* Permanently exclude internal customer */
			AND COALESCE(opr.customer_name, '') <>
				%(excluded_customer)s

			AND (
				%(from_date)s IS NULL
				OR opr.date >= %(from_date)s
			)

			AND (
				%(to_date)s IS NULL
				OR opr.date <= %(to_date)s
			)

			AND (
				%(project)s = ''
				OR COALESCE(opr.project, '') LIKE %(project_like)s
			)

			AND (
				%(customer_name)s = ''
				OR opr.customer_name = %(customer_name)s
			)

			AND (
				%(sales_order)s = ''
				OR opr.sales_order = %(sales_order)s
			)

			AND (
				%(sales_person)s = ''
				OR opr.sales_person = %(sales_person)s
			)

			AND (
				%(product_type)s = ''
				OR opr.product_type1 = %(product_type)s
			)

			AND (
				%(region)s = ''
				OR COALESCE(proj.region, '') = %(region)s
			)

			AND (
				%(active_only)s = 0
				OR COALESCE(opr.workflow_state, '') NOT IN (
					'Completed',
					'Canceled',
					'Cancelled',
					'Draft',
					'Submitted for Approval',
					'Approved by General Manager',
					'On Hold',
					'Delivery Completed',
					'PO Verified'
				)
			)

			/*
			 * Pending filter:
			 * - SQM fields intentionally excluded
			 * - Checks remaining Nos and Remaining Value
			 */
			AND (
				%(pending_only)s = 0
				OR (
					COALESCE(
						opr.remaining_nos_production,
						0
					) <> 0

					OR COALESCE(
						opr.remaining_nos_delivery,
						0
					) <> 0

					OR COALESCE(
						opr.remaining_produced_no_to_delivered,
						0
					) <> 0

					OR COALESCE(
						opr.remaining_value,
						0
					) <> 0
				)
			)

		ORDER BY
			COALESCE(
				NULLIF(TRIM(opr.project), ''),
				'Project Not Specified'
			) ASC,

			COALESCE(
				NULLIF(TRIM(proj.region), ''),
				'Not Specified'
			) ASC,

			opr.name ASC
		""",
		values,
		as_dict=True,
	)

	# =========================================================
	# FIELDS TO TOTAL
	# =========================================================

	numeric_fields = [
		"total_sqm",
		"total_no",
		"total_straight_sqm",
		"total_straight_nos",
		"total_fittings_sqm",
		"total_fittings_nos",
		"total_sqm_produced",
		"total_nos_produced",
		"remaining_sqm_production",
		"remaining_nos_production",
		"total_sqm_delivered",
		"total_nos_delivered",
		"remaining_sqm_delivery",
		"remaining_nos_delivery",
		"remaining_produced_sqm_to_delivered",
		"remaining_produced_no_to_delivered",
		"remaining_value",
	]

	# =========================================================
	# GROUP OPRS BY PROJECT
	# =========================================================

	project_groups = {}
	project_order = []

	for opr in opr_rows:

		project_name = opr.get("project")

		if not project_name:
			project_name = "Project Not Specified"

		if project_name not in project_groups:
			project_groups[project_name] = []
			project_order.append(project_name)

		project_groups[project_name].append(opr)

	# =========================================================
	# INITIALISE TOTALS
	# =========================================================

	grand_total = {fieldname: 0.0 for fieldname in numeric_fields}

	rows = []

	# =========================================================
	# BUILD PROJECT TOTAL ROW + OPR DETAIL ROWS
	# =========================================================

	for project_name in project_order:

		project_total = {fieldname: 0.0 for fieldname in numeric_fields}

		project_oprs = project_groups.get(project_name) or []

		project_regions = []

		# -----------------------------------------------------
		# CALCULATE PROJECT TOTALS
		# -----------------------------------------------------

		for opr in project_oprs:

			region_name = opr.get("region") or "Not Specified"

			if region_name not in project_regions:
				project_regions.append(region_name)

			for fieldname in numeric_fields:

				value = opr.get(fieldname) or 0.0

				project_total[fieldname] = project_total.get(fieldname, 0.0) + value
				grand_total[fieldname] = grand_total.get(fieldname, 0.0) + value

		# -----------------------------------------------------
		# DETERMINE PROJECT REGION DISPLAY
		# -----------------------------------------------------

		project_region = ""

		if len(project_regions) == 1:
			project_region = project_regions[0]

		if len(project_regions) > 1:
			project_region = "Multiple"

		# -----------------------------------------------------
		# SINGLE PROJECT ROW WITH TOTALS
		# -----------------------------------------------------

		project_row = {
			"project_name": project_name,
			"region": project_region,
			"opr_name": "",
			"product_type": "",
			"indent": 0,
			"row_type": "project_total",
		}

		for fieldname in numeric_fields:
			project_row[fieldname] = project_total.get(fieldname, 0.0)

		rows.append(project_row)

		# -----------------------------------------------------
		# OPR DETAIL ROWS
		# -----------------------------------------------------

		for opr in project_oprs:

			detail_row = {
				"project_name": "",
				"region": opr.get("region"),
				"opr_name": opr.get("opr_name"),
				"product_type": opr.get("product_type"),
				"indent": 1,
				"row_type": "opr",
			}

			for fieldname in numeric_fields:
				detail_row[fieldname] = opr.get(fieldname) or 0.0

			rows.append(detail_row)

	# =========================================================
	# GRAND TOTAL
	# =========================================================

	grand_total_row = {
		"project_name": "Grand Total",
		"region": "",
		"opr_name": "",
		"product_type": "",
		"indent": 0,
		"row_type": "grand_total",
	}

	for fieldname in numeric_fields:
		grand_total_row[fieldname] = grand_total.get(fieldname, 0.0)

	rows.append(grand_total_row)

	return rows


def get_columns():
	return [
		{
			"label": "Project",
			"fieldname": "project_name",
			"fieldtype": "Data",
			"width": 300,
		},
		{
			"label": "Region",
			"fieldname": "region",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": "OPR #",
			"fieldname": "opr_name",
			"fieldtype": "Link",
			"options": "Order Processing Request",
			"width": 135,
		},
		{
			"label": "Product Type",
			"fieldname": "product_type",
			"fieldtype": "Data",
			"width": 210,
		},
		{
			"label": "Total OPR SQM",
			"fieldname": "total_sqm",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Total OPR Nos",
			"fieldname": "total_no",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Total Std SQM",
			"fieldname": "total_straight_sqm",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Total Std Nos",
			"fieldname": "total_straight_nos",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Total Fitt SQM",
			"fieldname": "total_fittings_sqm",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Total Fitt Nos",
			"fieldname": "total_fittings_nos",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Produced SQM",
			"fieldname": "total_sqm_produced",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Produced Nos",
			"fieldname": "total_nos_produced",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Rem. Production SQM",
			"fieldname": "remaining_sqm_production",
			"fieldtype": "Float",
			"precision": 2,
			"width": 135,
		},
		{
			"label": "Rem. Production Nos",
			"fieldname": "remaining_nos_production",
			"fieldtype": "Float",
			"precision": 2,
			"width": 135,
		},
		{
			"label": "Delivered SQM",
			"fieldname": "total_sqm_delivered",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Delivered Nos",
			"fieldname": "total_nos_delivered",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": "Rem. Delivery SQM",
			"fieldname": "remaining_sqm_delivery",
			"fieldtype": "Float",
			"precision": 2,
			"width": 125,
		},
		{
			"label": "Rem. Delivery Nos",
			"fieldname": "remaining_nos_delivery",
			"fieldtype": "Float",
			"precision": 2,
			"width": 125,
		},
		{
			"label": "Ready Dispatch SQM",
			"fieldname": "remaining_produced_sqm_to_delivered",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": "Ready Dispatch Nos",
			"fieldname": "remaining_produced_no_to_delivered",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": "Remaining Value",
			"fieldname": "remaining_value",
			"fieldtype": "Currency",
			"precision": 2,
			"width": 130,
		},
	]
