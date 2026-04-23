import rpakit
from rpakit import UI, run_workflow


@run_workflow("simple_form_fill")
def run(full_name: str, email: str, phone: str) -> dict:
    """Fill out a basic contact form with name, email, and phone fields, then submit."""
    ui = UI.attach("Contact Form - Web Browser")

    name_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtFullName"},
        "tertiary": {"method": "ocr_anchor", "text": "Full Name"},
        "fallback": {"method": "coordinates", "x": 400, "y": 220},
        "label": "Full Name",
        "control_type": "Edit"
    }
    
    email_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtEmail"},
        "tertiary": {"method": "ocr_anchor", "text": "Email Address"},
        "fallback": {"method": "coordinates", "x": 400, "y": 290},
        "label": "Email Address",
        "control_type": "Edit"
    }
    
    phone_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtPhone"},
        "tertiary": {"method": "ocr_anchor", "text": "Phone Number"},
        "fallback": {"method": "coordinates", "x": 400, "y": 360},
        "label": "Phone Number",
        "control_type": "Edit"
    }
    
    submit_selector = {
        "primary": {"method": "uia_automation_id", "value": "btnSubmit"},
        "tertiary": {"method": "ocr_anchor", "text": "Submit"},
        "fallback": {"method": "coordinates", "x": 400, "y": 440},
        "label": "Submit",
        "control_type": "Button"
    }

    ui.wait_for(name_selector)
    ui.fill(name_selector, full_name)

    ui.wait_for(email_selector)
    ui.fill(email_selector, email)

    ui.wait_for(phone_selector)
    ui.fill(phone_selector, phone)

    ui.wait_for(submit_selector)
    ui.click(submit_selector)

    return {}


if __name__ == "__main__":
    result = run(
        full_name="John Doe",
        email="john.doe@example.com",
        phone="+1-555-0123"
    )