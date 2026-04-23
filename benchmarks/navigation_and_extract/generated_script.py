import rpakit


@rpakit.run_workflow("navigation_and_extract")
def run(employee_id: str, search_query: str) -> dict:
    """Navigate an internal portal, search for an employee, extract their department and salary information."""
    ui = rpakit.UI.attach("HR Portal - Intranet")

    # Navigate to Employees section
    nav_employees_selector = {
        "primary": {"method": "uia_automation_id", "value": "navEmployees"},
        "tertiary": {"method": "ocr_anchor", "text": "Employees"},
        "fallback": {"method": "coordinates", "x": 120, "y": 85},
        "label": "Employees",
        "control_type": "Hyperlink"
    }
    ui.click(nav_employees_selector)

    # Wait for search field to appear
    search_field_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtSearch"},
        "label": "Search field",
        "control_type": "Edit"
    }
    ui.wait_for(search_field_selector)

    # Fill search query
    search_input_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtSearch"},
        "tertiary": {"method": "ocr_anchor", "text": "Search employees..."},
        "fallback": {"method": "coordinates", "x": 500, "y": 150},
        "label": "Search employees",
        "control_type": "Edit"
    }
    ui.fill(search_input_selector, search_query)

    # Submit search (keyboard shortcut)
    ui.click(search_input_selector)
    rpakit.wait(0.3, reason="ensure focus before enter key")
    
    # Wait for results grid
    results_grid_selector = {
        "primary": {"method": "uia_automation_id", "value": "gridResults"},
        "label": "Results grid",
        "control_type": "DataGrid"
    }
    ui.wait_for(results_grid_selector)

    # Click first result row
    first_row_selector = {
        "primary": {"method": "uia_automation_id", "value": "row_0"},
        "tertiary": {"method": "ocr_anchor", "text": "Jane Smith"},
        "fallback": {"method": "coordinates", "x": 500, "y": 230},
        "label": "First result row",
        "control_type": "DataItem"
    }
    ui.click(first_row_selector)

    # Wait for employee details panel
    details_panel_selector = {
        "primary": {"method": "uia_automation_id", "value": "pnlDetails"},
        "label": "Employee detail panel",
        "control_type": "Pane"
    }
    ui.wait_for(details_panel_selector)

    # Click Compensation tab
    compensation_tab_selector = {
        "primary": {"method": "uia_automation_id", "value": "tabCompensation"},
        "tertiary": {"method": "ocr_anchor", "text": "Compensation"},
        "fallback": {"method": "coordinates", "x": 350, "y": 320},
        "label": "Compensation tab",
        "control_type": "TabItem"
    }
    ui.click(compensation_tab_selector)

    # Extract department
    department_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblDepartment"},
        "tertiary": {"method": "ocr_anchor", "text": "Department:"},
        "fallback": {"method": "coordinates", "x": 450, "y": 380},
        "label": "Department value",
        "control_type": "Text"
    }
    department = ui.read(department_selector)

    # Extract salary
    salary_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblSalary"},
        "tertiary": {"method": "ocr_anchor", "text": "Annual Salary:"},
        "fallback": {"method": "coordinates", "x": 450, "y": 420},
        "label": "Salary value",
        "control_type": "Text"
    }
    salary = ui.read(salary_selector)

    return {
        "department": department,
        "salary": salary
    }


if __name__ == "__main__":
    result = run(employee_id="EMP-2048", search_query="Jane Smith")
    print("Department:", result["department"])
    print("Salary:", result["salary"])