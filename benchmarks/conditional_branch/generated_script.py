import rpakit


@rpakit.run_workflow("conditional_branch")
def run(expense_amount: str, expense_category: str) -> dict:
    ui = rpakit.UI.attach("Expense Tracker - Desktop")
    
    new_expense_selector = {
        "primary": {"method": "uia_automation_id", "value": "btnNewExpense"},
        "tertiary": {"method": "ocr_anchor", "text": "New Expense"},
        "fallback": {"method": "coordinates", "x": 150, "y": 60},
        "label": "New Expense",
        "control_type": "Button"
    }
    ui.click(new_expense_selector)
    
    amount_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtAmount"},
        "tertiary": {"method": "ocr_anchor", "text": "Amount ($)"},
        "fallback": {"method": "coordinates", "x": 400, "y": 180},
        "label": "Amount",
        "control_type": "Edit"
    }
    ui.fill(amount_selector, expense_amount)
    
    category_selector = {
        "primary": {"method": "uia_automation_id", "value": "cboCategory"},
        "tertiary": {"method": "ocr_anchor", "text": "Category"},
        "fallback": {"method": "coordinates", "x": 400, "y": 250},
        "label": "Category",
        "control_type": "ComboBox"
    }
    ui.select(category_selector, expense_category)
    
    amount_value = float(expense_amount)
    
    if amount_value > 1000:
        approval_selector = {
            "primary": {"method": "uia_automation_id", "value": "btnRequestApproval"},
            "tertiary": {"method": "ocr_anchor", "text": "Request Approval"},
            "fallback": {"method": "coordinates", "x": 400, "y": 400},
            "label": "Request Approval",
            "control_type": "Button"
        }
        ui.click(approval_selector)
    else:
        submit_selector = {
            "primary": {"method": "uia_automation_id", "value": "btnAutoApprove"},
            "tertiary": {"method": "ocr_anchor", "text": "Submit"},
            "fallback": {"method": "coordinates", "x": 400, "y": 400},
            "label": "Submit",
            "control_type": "Button"
        }
        ui.click(submit_selector)
    
    confirmation_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblConfirmation"},
        "tertiary": {"method": "ocr_anchor", "text": "Expense submitted"},
        "label": "Confirmation message",
        "control_type": "Text"
    }
    ui.wait_for(confirmation_selector)
    
    return {}