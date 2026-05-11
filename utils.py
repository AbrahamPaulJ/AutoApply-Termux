import os
import yaml
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_user_field(user, field):
    info_path = os.path.join(BASE_DIR, "Users", user, "info.yaml")
    with open(info_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get(field)

def generate_cl_prompt(user, raw_html):
    resume_path = os.path.join(BASE_DIR, "Users", user, "resume.txt")
    with open(resume_path, "r", encoding="utf-8") as f:
        json_resume = f.read()

    name = get_user_field(user, "name")
    email = get_user_field(user, "email")
    phone = get_user_field(user, "phone")
    address = get_user_field(user, "address")
    date = datetime.now().strftime("%d %B %Y")
    template = get_user_field(user, "cover_letter_prompt")

    return template.format(
        name=name,
        email=email,
        phone=phone,
        address=address,
        date=date,
        json_resume=json_resume,
        raw_html=raw_html
    )